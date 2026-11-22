# -*- coding: utf-8 -*-
"""Тесты «план дня» одной командой (Ф8, 23.11)."""
import datetime as dt
import json
from pathlib import Path

import pytest

from core import config, dayplan
from core.autonomy import DayPlanner, save_queue


@pytest.fixture()
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("MARFA_HOME", str(tmp_path))
    monkeypatch.setattr(config, "HOME_DIR", tmp_path)
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(config, "QUEUE_FILE", tmp_path / "data" / "queue.json")
    yield tmp_path


def test_no_plan_is_honest(home):
    """Плана нет — честно: строится в 08:00, добавить сейчас — «задача:»."""
    text = dayplan.today_plan(now=dt.datetime(2026, 11, 23, 15, 0))
    assert "ещё нет" in text and "задача:" in text
    assert "08:00" in text


def test_plan_with_progress(home):
    planner = DayPlanner(data_dir=Path(config.DATA_DIR))
    day = dt.date(2026, 11, 23)
    planner.plan_path(day).parent.mkdir(parents=True, exist_ok=True)
    planner.plan_path(day).write_text(json.dumps({
        "tasks": [
            {"id": "t1", "title": "прочитать главу", "status": "done"},
            {"id": "t2", "title": "проверить уши", "status": "todo"},
            {"id": "t3", "title": "подвести день", "status": "in_progress"},
        ]}, ensure_ascii=False), encoding="utf-8")
    text = dayplan.today_plan(now=dt.datetime(2026, 11, 23, 15, 0))
    assert "1 из 3 сделано" in text
    assert "[x] прочитать главу" in text
    assert "[ ] проверить уши" in text
    assert "[→] подвести день" in text


def test_queue_shown_as_future(home):
    save_queue([{"id": "q1", "title": "поставить whisper", "priority": "low"}])
    text = dayplan.today_plan(now=dt.datetime(2026, 11, 23, 15, 0))
    assert "В ОЧЕРЕДИ" in text and "whisper" in text and "low" in text


def test_broken_plan_falls_to_queue(home):
    """Битый план — не крах: честно про очередь (каждый блок в броне)."""
    day = dt.date(2026, 11, 23)
    p = Path(config.DATA_DIR) / ("plan_%s.json" % day.isoformat())
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("не json", encoding="utf-8")
    save_queue([{"id": "q1", "title": "задача из очереди", "priority": "normal"}])
    text = dayplan.today_plan(now=dt.datetime(2026, 11, 23, 15, 0))
    assert "очеред" in text.lower() and "задача из очереди" in text
