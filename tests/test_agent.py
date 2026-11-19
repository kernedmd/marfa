# -*- coding: utf-8 -*-
"""Тесты диспетчера (ТЗ 3.1): быстрые команды → Python, остальное → 30B."""
import json
from pathlib import Path

import pytest

from core import config
from core.agent import Agent, Reply, load_doctrine
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
    return Agent(brain=BrainClient(brain_url=srv.base_url), memory=mem, doctrine="Тестовая доктрина")


# ---------- быстрые команды: Python, мозг молчит ----------
def test_fast_brackets(agent, srv):
    r = agent.handle("скобки (a[1]{x})")
    assert "баланс: ОК" in r.text and r.tool_used == "check_brackets"
    assert srv.calls == []            # к 30B не ходили — 0 сек
    assert r.source == "python"


def test_fast_calc(agent, srv):
    r = agent.handle("вычисли (12 + 8) * 3")
    assert r.text == "60" and srv.calls == []


def test_fast_calc_not_math_goes_to_brain(agent, srv):
    srv.reply_content = '{"answer": "спроси у калькулятора"}'
    r = agent.handle("вычисли как жить")
    assert r.source == "brain" and len(srv.calls) == 1


def test_fast_remember(agent, srv):
    r = agent.handle("помни квант по умолчанию Q4_K_M")
    assert r.tool_used == "remember" and "запомнила" in r.text
    got = agent.memory.recall("квант по умолчанию")
    assert got and "Q4_K_M" in got[0]["text"]


def test_fast_recall(agent):
    agent.memory.remember("веб-панель живёт на 5001")
    r = agent.handle("вспомни веб-панель")
    assert "5001" in r.text and r.tool_used == "recall"


def test_fast_time_and_status(agent, srv):
    assert agent.handle("время").source == "python"
    r = agent.handle("статус")
    assert "Состояние дома" in r.text and srv.calls == []


# ---------- мозговой трек ----------
def test_brain_answer(agent, srv):
    srv.reply_content = '{"answer": "Контекст 4096 — закон доктрины"}'
    r = agent.handle("какой максимальный контекст?")
    assert r.text == "Контекст 4096 — закон доктрины" and r.source == "brain"


def test_brain_action_write_file(agent, srv):
    """{"action"} → руки. Путь и содержимое СТРАЖ проверяет внутри рук."""
    srv.reply_content = ('{"action": {"tool": "write_file", "args": '
                         '{"path": "data/заметка.txt", "content": "привет от мозга"}}}')
    r = agent.handle("запиши привет в data/заметка.txt")
    assert r.tool_used == "write_file" and "записано" in r.text
    assert (config.DATA_DIR / "заметка.txt").read_text(encoding="utf-8") == "привет от мозга"


def test_brain_action_guard_denies_outside(agent, srv):
    """Мозг просит записать вне дома → СТРАЖ отказывает, агент не падает.
    Путь платформонезависимый: соседняя папка рядом с домом."""
    import json
    outside = str(config.HOME_DIR.parent / "evil.txt")
    srv.reply_content = json.dumps(
        {"action": {"tool": "write_file", "args": {"path": outside, "content": "нет"}}},
        ensure_ascii=False,
    )
    r = agent.handle("запиши вне дома")
    assert r.tool_used == "write_file"
    assert "СТРАЖ" in r.text or "отказал" in r.text


def test_brain_unknown_tool(agent, srv):
    srv.reply_content = '{"action": {"tool": "format_c", "args": {}}}'
    r = agent.handle("отформатируй всё")
    assert "неизвестный инструмент" in r.text


def test_brain_down_honest(agent, monkeypatch):
    monkeypatch.setattr(agent.brain, "url", "http://127.0.0.1:1")
    r = agent.handle("длинный вопрос, требующий размышлений")
    assert "мозг недоступен" in r.text and r.source == "fallback"


# ---------- контекст ----------
def test_doctrine_and_rag_injected(agent, srv):
    """В промпт попадают доктрина, состояние и RAG-воспоминания (3.1)."""
    agent.memory.remember("дом Марфа живёт в C:\\Marfa")
    srv.reply_content = '{"answer": "принято"}'
    agent.handle("напомни, где живёт дом")
    sys_msg = next(m for m in srv.calls[-1]["messages"] if m["role"] == "system")
    assert "Тестовая доктрина" in sys_msg["content"]
    assert "Состояние дома" in sys_msg["content"]
    assert "C:\\Marfa" in sys_msg["content"]


def test_doctrine_file_loaded(home):
    import json
    (config.DATA_DIR / "creator_doctrine.json").write_text(
        json.dumps({"doctrine": "Я — Марфа. Служу Илье."}, ensure_ascii=False), encoding="utf-8")
    assert "Служу Илье" in load_doctrine()


def test_doctrine_missing_falls_back(home):
    assert "Марфа" in load_doctrine()  # каркасный минимум, не фантазия
