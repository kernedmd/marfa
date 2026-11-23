# -*- coding: utf-8 -*-
"""ДОМ №39 «обращение и составной ход» (23.11, вечер-3 — урок живого
лога): Илья говорит с Марфой по имени — «Марфа, время» — а имя уводило
команду в двухминутный мозговой трек; «Доброе утро, что тебе снилось?»
не совпало ни с будильником, ни с командой сна — и утро началось с
уверенного «не знаю». Обращение снимается, слово пробуждения стало
префиксом с разбором продолжения; не-команда уходит мозгу целиком."""
from pathlib import Path

import pytest

from core import config
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


# ---------- обращение по имени ----------

def test_vocative_fast_command(agent, srv):
    r = agent.handle("Марфа, время")
    assert r.tool_used == "time" and r.source == "python"
    assert srv.calls == []                    # двухминутный трек не понадобился


def test_vocative_case_and_dash(agent, srv):
    assert agent.handle("МАРФА, статус").tool_used == "status"
    assert agent.handle("Марфа - привет").tool_used == "greet"


def test_vocative_memory_payload_keeps_case(agent):
    r = agent.handle("Марфа, запиши в память: Правило N3 живо")
    assert "Правило N3 живо" in r.text        # регистр payload не потерян


def test_bare_name_goes_to_brain(agent, srv):
    srv.reply_content = '{"answer": "я здесь"}'
    r = agent.handle("Марфа")
    assert r.source == "brain" and r.text == "я здесь"


def test_vocative_non_command_brain_sees_everything(agent, srv):
    srv.reply_content = '{"answer": "слышу тебя"}'
    r = agent.handle("Марфа, расскажи про законы дома")
    assert r.source == "brain"
    sent = srv.calls[0]["messages"][-1]["content"]
    assert sent == "Марфа, расскажи про законы дома"   # целиком, без обрезки


def test_word_boundary_no_stripping(agent, srv):
    # «марфария» — не обращение; «запомнится» — не команда: мозг
    srv.reply_content = '{"answer": "ок"}'
    assert agent.handle("Марфария красивое имя").source == "brain"


# ---------- составной ход пробуждения ----------

def test_morning_with_dream_question(agent, srv):
    r = agent.handle("Доброе утро, что тебе снилось?")
    assert r.tool_used == "dream"             # вопрос услышан, не «не знаю»
    assert srv.calls == []                     # мозг не будили
    assert "снов" in r.text.lower()            # честный ответ органа сна


def test_morning_plain_still_morning(agent, srv):
    r = agent.handle("доброе утро")
    assert r.tool_used == "sleep"


def test_morning_non_command_falls_to_report(agent, srv):
    r = agent.handle("Доброе утро, как спалось?")
    assert r.tool_used == "sleep"              # утренний отчёт и отвечает
    assert srv.calls == []


def test_wake_with_fast_tail(agent, srv):
    r = agent.handle("проснись и проверь уши")
    assert r.tool_used == "ears_selftest"      # «и» снят, команда услышана
    assert srv.calls == []


def test_morning_punctuated(agent, srv):
    r = agent.handle("доброе утро!")
    assert r.tool_used == "sleep"


# ---------- ведущий союз «И» (диктовка правил, вечер-3 доучка) ----------

def test_leading_and_memory_dictation(agent):
    r = agent.handle('И запиши в память: если команда известна, но '
                     'контекст изменился — я не выполняю автоматически')
    assert r.tool_used == "remember"
    got = agent.memory.recall("контекст изменился")
    assert got and "автоматически" in got[0]["text"]


def test_leading_and_non_command_brain_sees_original(agent, srv):
    srv.reply_content = '{"answer": "думаю"}'
    r = agent.handle("И что дальше со всем этим делать?")
    assert r.source == "brain"
    sent = srv.calls[0]["messages"][-1]["content"]
    assert sent == "И что дальше со всем этим делать?"   # целиком, без обрезки
