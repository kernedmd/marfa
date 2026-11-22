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


# ---------- СКОРОСТЬ v1: краткость — закон дома ----------

def test_speed_law_in_brain_prompt(agent):
    """«ответ через две минуты — очень долго»: мозг ВИДИТ закон
    краткости в каждом системном промпте (статично — KV-кэш цел)."""
    extra = agent._system_extra("привет")
    assert "ЗАКОН СКОРОСТИ" in extra
    assert "одно-четыре предложения" in extra


def test_brain_track_short_budget_and_tokens(agent, srv):
    """Чат-ответ: бюджет BRAIN_ANSWER_TOKENS + штамп несёт токены —
    по ним видно, кто съел время, если снова две минуты."""
    srv.reply_content = '{"answer": "кратко и по делу"}'
    r = agent.handle("привет, как дела?")
    assert r.source == "brain"
    assert srv.calls[-1]["max_tokens"] == config.BRAIN_ANSWER_TOKENS
    assert srv.calls[-1]["stream"] is True          # превью просилось
    assert isinstance(r.meta, dict) and r.meta["tok"] >= 1


# ---------- РУКИ v2.1 (23.11): живой язык — мозгу, шпаргалка — по просьбе ----------

def test_hands_natural_language_goes_to_brain(agent, srv):
    """Урок живого лога: «Руки проверить работу микрофона» билось в
    формат-ошибку рук. Живой язык — работа МОЗГА: руки не притворяются
    глухим форматом, задание уходит думать мозгу."""
    srv.reply_content = '{"answer": "проверю уши, минуту"}'
    r = agent.handle("Руки проверить работу микрофона")
    assert r.source == "brain" and len(srv.calls) == 1
    assert "проверю уши" in r.text


def test_hands_bare_and_help_are_friendly(agent, srv):
    """«руки» и «что умеют руки» — шпаргалка по-человечески, а не тот же
    формат-отказ (второй урок того же лога: на вопрос о руках рука
    отвечала примером формата)."""
    for msg in ("руки", "руки?", "руки помощь", "что умеют руки",
                "что ты можешь руками"):
        r = agent.handle(msg)
        assert r.source == "python" and r.tool_used == "hands_help", msg
        assert "нажми" in r.text and "буфер" in r.text, msg
        assert srv.calls == [], msg


def test_hands_known_verbs_still_direct(agent, srv, monkeypatch):
    """Настоящие задания рук не ушли мозгу: «нажми Пуск» — по-прежнему
    руки, мозг молчит (сухой режим честно скажет про кнопку 91)."""
    from core import motor
    called = []

    def fake_run(task):
        called.append(task)
        return "РУКИ — задание: %s [сухой режим]" % task

    monkeypatch.setattr(motor, "run", fake_run)
    r = agent.handle("руки нажми Пуск")
    assert r.source == "python" and r.tool_used == "hands"
    assert called and "Пуск" in called[0]
    assert srv.calls == []


def test_hands_looking_redirect_survives(agent, srv, monkeypatch):
    """«руки посмотри на меня» — честный редирект рук на глаза (урок
    22.11 жив и с новым маршрутом: неизвестный глагол с «посмотр» не
    уходит мозгу молча, а получает свою подсказку)."""
    from core import motor
    monkeypatch.setattr(motor, "run", lambda task: "РУКИ не смотрят — «посмотри»")
    r = agent.handle("руки посмотри на меня")
    assert r.source == "python" and r.tool_used == "hands"
    assert "не смотрят" in r.text
    assert srv.calls == []
