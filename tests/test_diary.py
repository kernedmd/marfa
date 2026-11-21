# -*- coding: utf-8 -*-
"""Тесты №8 «вечерний дневник»: механический каркас фактов дня.

Гейт §5: дневник строится из файлов дома, LLM-саммари нет —
больной мозг не пишет истину (место помечено, включится резолюцией).
"""
import datetime as dt
import json
import os

import pytest

from core import config
from core.diary import Diary


@pytest.fixture()
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("MARFA_HOME", str(tmp_path))
    monkeypatch.setattr(config, "HOME_DIR", tmp_path)
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(config, "EARS_LOG_FILE", tmp_path / "logs" / "ears_log.jsonl")
    config.ensure_dirs()
    yield tmp_path


DAY = dt.date(2026, 11, 21)


def _mk_plan(home, day, tasks, carry=None):
    (home / "data" / ("plan_%s.json" % day.isoformat())).write_text(json.dumps({
        "date": day.isoformat(), "tasks": tasks,
        "carry_over": carry or []}, ensure_ascii=False), encoding="utf-8")


def _mk_dialog(home, name, turns):
    p = home / "data" / "dialog" / ("session_%s.json" % name)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"session": name, "turns": turns},
                            ensure_ascii=False), encoding="utf-8")
    os.utime(p, (dt.datetime(2026, 11, 21, 18, 0).timestamp(),) * 2)


def test_full_day_diary(home):
    _mk_plan(home, DAY, [
        {"id": "t1", "title": "проверить уши", "status": "done"},
        {"id": "t2", "title": "прочитать главу", "status": "pending"},
    ], carry=["[с вчера] доделать тесты"])
    _mk_dialog(home, "evening", [
        {"role": "user", "text": "Марфа, как дела с памятью?"},
        {"role": "assistant", "text": "в порядке"},
        {"role": "user", "text": "ещё вопрос"},
    ])
    (home / "logs").mkdir(exist_ok=True)
    with (home / "logs" / "ears_log.jsonl").open("w", encoding="utf-8") as f:
        f.write(json.dumps({"ts": "2026-11-21T10:00:00", "event": "wake"}) + "\n")
        f.write(json.dumps({"ts": "2026-11-21T11:00:00", "event": "wake"}) + "\n")
        f.write(json.dumps({"ts": "2026-11-20T10:00:00", "event": "wake"}) + "\n")

    text = Diary(home / "data").build_day(day=DAY,
                                          now=dt.datetime(2026, 11, 21, 21, 0))
    p = home / "data" / "diary" / "2026-11-21.md"
    assert p.exists()
    assert "Дневник Марфы — 2026-11-21" in text
    assert "Задач: 2, сделано: 1" in text
    assert "прочитать главу" in text                 # не закрытая — видна
    assert "как дела с памятью" in text              # тема разговора
    assert "звучало 2 раз" in text                   # только сегодняшний зов
    assert "Что хочу завтра" in text
    assert "закрыть: прочитать главу" in text
    # гейт §5: живой рассказ помечен, но НЕ выдуман
    assert "вердикта батареи" in text
    assert "LLM" not in text or "гейт" in text


def test_quiet_day_diary(home):
    text = Diary(home / "data").build_day(day=DAY,
                                          now=dt.datetime(2026, 11, 21, 21, 0))
    assert "поговорить с Ильёй — день прошёл молча" in text


def test_done_day_no_invented_wants(home):
    """День прожит, дела закрыты — Марфа не выдумывает заботу (честность)."""
    _mk_plan(home, DAY, [{"id": "t1", "title": "всё сделано", "status": "done"}])
    _mk_dialog(home, "evening", [{"role": "user", "text": "спокойной ночи"}])
    text = Diary(home / "data").build_day(day=DAY,
                                          now=dt.datetime(2026, 11, 21, 21, 0))
    assert "не выдумывать заботу" in text


def test_rebuild_same_day_replaces(home):
    d = Diary(home / "data")
    t1 = d.build_day(day=DAY, now=dt.datetime(2026, 11, 21, 21, 0))
    _mk_plan(home, DAY, [{"id": "t9", "title": "вечерняя задача", "status": "pending"}])
    t2 = d.build_day(day=DAY, now=dt.datetime(2026, 11, 21, 23, 0))
    assert "вечерняя задача" in t2 and "вечерняя задача" not in t1
    files = list((home / "data" / "diary").glob("*.md"))
    assert len(files) == 1                            # один день — один файл


def test_last_diary(home):
    d = Diary(home / "data")
    assert d.last_diary() is None
    d.build_day(day=DAY, now=dt.datetime(2026, 11, 21, 21, 0))
    d.build_day(day=DAY + dt.timedelta(days=1),
                now=dt.datetime(2026, 11, 22, 21, 0))
    assert d.last_diary() == "2026-11-22"


def test_agent_command_builds_diary(home, monkeypatch):
    """«подведи день» — быстрая команда: мозг молчит, дневник собирается."""
    from core.agent import Agent

    class NoBrain:
        def ask_json(self, *a, **k):      # noqa: ANN002, ANN003
            raise AssertionError("мозг не должен просыпаться")

    agent = Agent(brain=NoBrain(), memory=None, doctrine="")
    reply = agent.handle("подведи день")
    assert reply.source == "python" and reply.tool_used == "diary"
    assert (home / "data" / "diary" / "2026-11-21.md").exists() or \
           "Дневник Марфы" in reply.text
    assert "Дневник Марфы" in reply.text
