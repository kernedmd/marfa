# -*- coding: utf-8 -*-
"""ПАМЯТЬ v2 (23.11, вечер-3 — урок живого лога): Создатель диктовал
правила («запиши в память: …»), а мозг звал несуществующий memory_add и
лепил файлы руками с опечатками в путях. Теперь «запиши в память: X» и
«запомни: X» — рефлексы органа памяти: ноль файлов, запись видна сразу,
мозг молчит. Границы: «запомни меня/экран» — прежние органы, «запомнится»
— не команда, манифест прямо говорит мозгу, что memory_add не существует."""
from pathlib import Path

import pytest

from core import config, identity
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


# ---------- «запиши в память: X» ----------

def test_write_memory_rule(agent, srv):
    r = agent.handle('запиши в память: молчание — не разрешение, '
                     'N = 3 цикла')
    assert r.tool_used == "remember" and r.source == "python"
    assert "записала в память" in r.text
    assert srv.calls == []                     # мозг молчал
    got = agent.memory.recall("молчание разрешение")
    assert got and "N = 3" in got[0]["text"]


def test_write_memory_quoted_payload_stripped(agent):
    r = agent.handle('запиши в память: "Уместность — проверяемый признак"')
    assert "записала в память: Уместность" in r.text
    got = agent.memory.recall("уместность признак")
    assert got and "проверяемый" in got[0]["text"]


def test_write_memory_empty_hint(agent, srv):
    r = agent.handle("запиши в память")
    assert "что записать" in r.text
    assert srv.calls == []


def test_write_memory_no_hijack_of_other_writes(agent, srv):
    # «запиши привет в файл» — НЕ память: уходит мозгу как раньше
    srv.reply_content = '{"answer": "запишу файлом"}'
    r = agent.handle("запиши привет в data/заметка.txt")
    assert r.source == "brain"


# ---------- «запомни: X» — общий случай ----------

def test_remember_generic_fact(agent, srv):
    r = agent.handle("запомни: завтра созвон с командой в 15:00")
    assert r.tool_used == "remember"
    assert "запомнила" in r.text and srv.calls == []
    got = agent.memory.recall("созвон")
    assert got and "15:00" in got[0]["text"]


def test_remember_generic_bare_hint(agent):
    r = agent.handle("запомни")
    assert "что запомнить" in r.text and r.tool_used == "remember"


def test_remember_specific_branches_not_stolen(agent, srv):
    # «запомни меня» — орган зрения (Ф1), «запомни экран» — снимок (№4):
    # оба возвращают честный текст без исключений, generic-ветка их не ест
    r1 = agent.handle("запомни меня")
    assert r1.tool_used == "face_remember"
    r2 = agent.handle("запомни экран")
    assert r2.tool_used == "screen_shot"


def test_remember_word_boundary(agent, srv):
    # «запомнится» — не команда: уходит мозгу
    srv.reply_content = '{"answer": "это глагол, не приказ"}'
    r = agent.handle("как это запомнится в базе?")
    assert r.source == "brain"


# ---------- манифест знает новую команду ----------

def test_manifest_mentions_memory_command():
    m = identity.manifest()
    assert "запиши в память" in m
    assert "memory_add" in m          # мозгу прямо сказано: его НЕТ
    assert "запиши в память" in identity.capabilities_report(
        memory=None, eyes_ok=True, ears_ok=True)
