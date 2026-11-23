# -*- coding: utf-8 -*-
"""ДОМ №40 «ПРАВИЛА ДОМА» (23.11, ночь — хвост коучинга Создателя):
Илья диктовал законы торможения в живом разговоре («Молчание — не
разрешение», «N = 3»), а на вопрос «кто применяет правило — ты или я?»
Марфа ответила «ui_action». Теперь правило — ЗАКОН с АВТОРОМ (Создатель)
и ИСПОЛНИТЕЛЕМ (Марфа): «запиши правило: X» — рефлекс, «правила» —
список с ролями и датой, «правило <№>» — один закон, «отмени
правило <№>» — снятие. Границы против жадной ветки: вопрос «Правило
N = 3 — помнишь?» (без двоеточия) — мозгу, «запомни правило» ловится
раньше общего «запомни», «правила» (множественное) — список, не запись."""
import json
import time
from pathlib import Path

import pytest

from core import config, identity, rules
from core.agent import Agent
from core.brain import BrainClient
from core.memory import Memory
from safety import guard
from tests.fake_llama_server import start_fake_brain


@pytest.fixture()
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("MARFA_HOME", str(tmp_path))
    monkeypatch.setattr(config, "HOME_DIR", tmp_path)
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(config, "RULES_FILE", tmp_path / "data" / "rules.json")
    monkeypatch.setattr(config, "GUARD_LOG_FILE", tmp_path / "logs" / "guard_log.jsonl")
    monkeypatch.setattr(config, "CANARIES_FILE", tmp_path / "data" / "canaries.json")
    monkeypatch.setattr(config, "DOCTRINE_FILE", tmp_path / "data" / "creator_doctrine.json")
    monkeypatch.setattr(config, "GENOME_FILE", tmp_path / "data" / "context_genome.json")
    monkeypatch.setattr(guard, "_LOG", None)
    config.ensure_dirs()
    yield tmp_path


@pytest.fixture()
def srv(monkeypatch, home):
    server = start_fake_brain()
    monkeypatch.setattr(config, "BRAIN_URL", server.base_url)
    yield server
    server.shutdown()


@pytest.fixture()
def agent(srv):
    mem = Memory(data_dir=Path(config.DATA_DIR))
    return Agent(brain=BrainClient(brain_url=srv.base_url), memory=mem,
                 doctrine="Тестовая доктрина")


# ---------- запись: автор, исполнитель, живая дата ----------

def test_save_rule_roles_and_live_date(agent, srv):
    r = agent.handle("запиши правило: Молчание — не разрешение. "
                     "Если ответа нет 3 цикла — не действую")
    assert r.tool_used == "rules" and r.source == "python"
    assert srv.calls == []                     # мозг молчал
    assert "правило №1 записано" in r.text
    assert "Автор — Илья" in r.text           # Создатель диктует
    assert "исполнитель" in r.text            # исполнитель назван
    rec = json.loads(Path(config.RULES_FILE).read_text(encoding="utf-8"))
    law = rec["rules"][0]
    assert law["author"] == "Илья"
    assert law["executor"] == "Марфа"
    assert law["created"] == time.strftime("%d.%m.%Y")   # живые часы, не «2023»
    assert "Молчание" in law["text"]


def test_save_rule_dual_write_to_memory(agent):
    agent.handle("запиши правило: уместность — проверяемый признак")
    got = agent.memory.recall("уместность признак")
    assert got and "проверяемый" in got[0]["text"]
    assert "правило" in (got[0].get("tags") or [])


def test_save_rule_duplicate_honest(agent):
    agent.handle("запиши правило: молчание — не разрешение")
    r = agent.handle("запиши правило: Молчание — не разрешение")
    assert "уже есть" in r.text
    assert rules.count() == 1                 # номер не растёт


def test_save_rule_empty_hint(agent, srv):
    r = agent.handle("запиши правило")
    assert "что за правило" in r.text
    assert srv.calls == []
    assert rules.count() == 0


def test_zapomni_rule_is_rules_not_remember(agent):
    r = agent.handle("запомни правило: не выдумываю причины, которых не видела")
    assert r.tool_used == "rules"             # не общий «запомни»
    assert rules.count() == 1
    # общий «запомни:» живёт как раньше — память, не законы
    r2 = agent.handle("запомни: завтра созвон в 10")
    assert r2.tool_used == "remember"
    assert rules.count() == 1


def test_new_rule_prefix(agent):
    agent.handle("новое правило: сначала смотрю, потом нажимаю")
    assert rules.count() == 1


# ---------- список, показ, отмена ----------

def test_rules_listing_with_roles(agent):
    agent.handle("запиши правило: Молчание — не разрешение")
    r = agent.handle("правила")
    assert "Законы нашего дома — 1" in r.text
    assert "автор Илья, исполнитель Марфа" in r.text
    assert "Молчание" in r.text


def test_rules_empty_honest(agent, srv):
    r = agent.handle("какие правила")
    assert "правил ещё нет" in r.text
    assert srv.calls == []                    # не выдумка «у меня нет правил» мозгом


def test_rule_show_single(agent):
    agent.handle("запиши правило: молчание — не разрешение")
    r = agent.handle("правило 1")
    assert "№1" in r.text and "молчание" in r.text.lower()
    r2 = agent.handle("правило №7")
    assert "№7 нет" in r2.text


def test_cancel_rule_honest(agent):
    agent.handle("запиши правило: сначала смотрю, потом нажимаю")
    r = agent.handle("отмени правило №1")
    assert "снято" in r.text and rules.count() == 0
    r2 = agent.handle("отмени правило №1")
    assert "не было" in r2.text


# ---------- границы против жадной ветки (урок р3) ----------

def test_rule_question_goes_to_brain(agent, srv):
    # «Правило N = 3 — помнишь?» — вопрос о законе, без двоеточия:
    # не запись, а живой разговор с мозгом
    srv.reply_content = '{"answer": "помню, диктовал Илья"}'
    r = agent.handle("Правило N = 3 — помнишь?")
    assert r.source == "brain"
    assert rules.count() == 0


def test_rules_plural_is_listing_not_save(agent):
    r = agent.handle("правила дома")
    assert r.tool_used == "rules" and "правил ещё нет" in r.text
    assert rules.count() == 0


def test_memory_command_untouched(agent):
    # «запиши в память» — прежний орган, правила его не подменяют
    r = agent.handle("запиши в память: факт без роли исполнителя")
    assert r.tool_used == "remember"
    assert rules.count() == 0


# ---------- броня органа ----------

def test_broken_file_honest_zero(agent):
    Path(config.RULES_FILE).write_text("{битый json", encoding="utf-8")
    r = agent.handle("правила")
    assert "правил ещё нет" in r.text         # честный ноль, не крах чата


def test_state_line_only_when_laws_exist(home):
    assert rules.state_line() == ""           # нет законов — нет шума
    rules.save("молчание — не разрешение")
    line = rules.state_line()
    assert "правила дома: 1 закон" in line
    assert "исполнитель" in line


def test_manifest_and_selfknowledge_know_rules():
    m = identity.manifest()
    assert "ПРАВИЛА ДОМА" in m
    assert "исполнителем" in m
    assert "запиши правило" in m
    fast = " ".join(identity.FAST_COMMANDS)
    assert "запиши правило" in fast and "отмени правило" in fast
    report = identity.capabilities_report(memory=None, eyes_ok=True,
                                          ears_ok=True)
    assert "Правила дома" in report
