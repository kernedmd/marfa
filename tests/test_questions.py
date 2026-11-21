# -*- coding: utf-8 -*-
"""Тесты инициативы (Круг Д): банк вопросов Создателю + такт Ф74.

Марфа хочет знать: зависшие задачи, глухие уши, молчащий мозг —
вопросы; ответ Ильи — в память. Дедуп: один вопрос не плодится.
"""
import datetime as dt
import json

import pytest

from core import config
from core.agent import Agent
from core.autonomy import add_task, load_queue
from core.questions import QuestionBank


@pytest.fixture()
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("MARFA_HOME", str(tmp_path))
    monkeypatch.setattr(config, "HOME_DIR", tmp_path)
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(config, "QUEUE_FILE", tmp_path / "data" / "queue.json")
    monkeypatch.setattr(config, "QUESTIONS_FILE", tmp_path / "data" / "questions.json")
    monkeypatch.setattr(config, "DRIVE_STATUS_FILE", tmp_path / "data" / "drive_status.json")
    monkeypatch.setattr(config, "EARS_STATUS_FILE", tmp_path / "data" / "ears_status.json")
    monkeypatch.setattr(config, "EARS_LOG_FILE", tmp_path / "logs" / "ears_log.jsonl")
    config.ensure_dirs()
    yield tmp_path


@pytest.fixture()
def bank(home):
    return QuestionBank()


# ---------- банк ----------

def test_add_open_answer(bank):
    q = bank.add("Когда будет микрофон?", source="уши")
    assert q and q["id"] == "q1" and q["status"] == "open"
    assert len(bank.open_items()) == 1
    got = bank.answer("q1", "закажу на неделе")
    assert got["status"] == "answered" and got["answer"] == "закажу на неделе"
    assert bank.open_items() == []


def test_dedupe_open_question(bank):
    assert bank.add("Один и тот же вопрос?", source="тест") is not None
    assert bank.add("Один и тот же  вопрос?", source="тест") is None  # тот же — мимо
    assert len(bank.open_items()) == 1
    bank.answer(bank.open_items()[0]["id"], "да")
    assert bank.add("Один и тот же вопрос?", source="тест") is not None  # закрытый можно заново


def test_answer_unknown_id(bank):
    assert bank.answer("q99", "что-то") is None
    assert bank.answer("q1", "   ") is None


def test_bank_survives_restart(home):
    QuestionBank().add("Вопрос из прошлой жизни?", source="тест")
    assert len(QuestionBank().open_items()) == 1


# ---------- такт: дом рассказывает, чего не хватает ----------

def test_tick_stale_queue_task(bank, home):
    add_task("старая задача про дрова")
    p = home / "data" / "queue.json"
    data = json.loads(p.read_text(encoding="utf-8"))
    data["tasks"][0]["created_at"] = "2026-11-10T09:00:00"   # 11 дней как висит
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    asked = bank.tick(now=dt.datetime(2026, 11, 21, 12, 0))
    assert any("дрова" in q for q in asked)
    assert len(bank.open_items()) == 1

    # второй такт — дедуп: не плодим
    assert bank.tick(now=dt.datetime(2026, 11, 21, 12, 1)) == []


def test_tick_queue_dedupe_cancels_duplicates(bank, home):
    add_task("дубль задачи")
    add_task("дубль задачи")
    add_task("дубль задачи")
    bank.tick(now=dt.datetime(2026, 11, 21, 12, 0))
    pending = [t for t in load_queue() if t["status"] == "pending"]
    cancelled = [t for t in load_queue() if t["status"] == "cancelled"]
    assert len(pending) == 1 and len(cancelled) == 2


def test_tick_fresh_task_no_question(bank, home):
    add_task("свежая задача")
    assert bank.tick(now=dt.datetime.now()) == []


def test_tick_ears_silent_long(bank, home):
    (home / "data" / "ears_status.json").write_text(json.dumps({
        "ts": (dt.datetime.now() - dt.timedelta(hours=30)).isoformat(timespec="seconds"),
        "state": "no_mic"}), encoding="utf-8")
    asked = bank.tick()
    assert any("микрофон" in q for q in asked)


def test_tick_ears_recent_no_question(bank, home):
    (home / "data" / "ears_status.json").write_text(json.dumps({
        "ts": dt.datetime.now().isoformat(timespec="seconds"),
        "state": "no_mic"}), encoding="utf-8")
    assert bank.tick() == []


def test_tick_brain_down_long(bank, home):
    (home / "data" / "drive_status.json").write_text(json.dumps({
        "ts": dt.datetime.now().isoformat(timespec="seconds"),
        "brain_down_since": (dt.datetime.now() - dt.timedelta(hours=3)).isoformat(timespec="seconds")}),
        encoding="utf-8")
    asked = bank.tick()
    assert any("Мозг молчит" in q for q in asked)


# ---------- команды в чате ----------

class NoBrain:
    def ask_json(self, *a, **k):          # noqa: ANN002, ANN003
        raise AssertionError("мозг не должен просыпаться")


def test_agent_lists_and_answers_questions(home):
    QuestionBank().add("Когда микрофон?", source="уши")
    agent = Agent(brain=NoBrain(), memory=None, doctrine="")

    r1 = agent.handle("что хотела спросить")
    assert r1.source == "python" and "Когда микрофон?" in r1.text

    r2 = agent.handle("ответ 1: в декабре")
    assert "Запомнила" in r2.text and "в декабре" in r2.text
    assert QuestionBank().open_items() == []


def test_agent_answer_with_memory(home):
    QuestionBank().add("Какой квант оставляем?", source="тест")

    class MemStub:
        def __init__(self):
            self.remembered = None

        def remember(self, text, **kw):            # noqa: ANN003
            self.remembered = text
            return {"id": "x"}

    mem = MemStub()
    agent = Agent(brain=NoBrain(), memory=mem, doctrine="")
    agent.handle("ответ 1: Q4_K_M остаётся")
    assert "Q4_K_M остаётся" in mem.remembered
    assert "Какой квант оставляем?" in mem.remembered


def test_agent_bad_question_number(home):
    QuestionBank().add("единственный вопрос", source="тест")
    agent = Agent(brain=NoBrain(), memory=None, doctrine="")
    r = agent.handle("ответ 5: мимо")
    assert "вопроса №5 нет" in r.text
