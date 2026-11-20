# -*- coding: utf-8 -*-
"""Тесты Ф71 «планировщик дня»: план в 08:00, очередь, перенос, идемпотентность."""
import datetime as dt
import json

import pytest

from core import config
from core.autonomy import DayPlanner, add_task, load_queue


@pytest.fixture()
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("MARFA_HOME", str(tmp_path))
    monkeypatch.setattr(config, "HOME_DIR", tmp_path)
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(config, "QUEUE_FILE", tmp_path / "data" / "queue.json")
    config.ensure_dirs()
    yield tmp_path


@pytest.fixture()
def planner(home):
    return DayPlanner()


def test_empty_day_plan(planner):
    plan = planner.build_plan(day=dt.date(2026, 11, 12), now=dt.datetime(2026, 11, 12, 8, 0))
    assert plan["date"] == "2026-11-12"
    assert plan["tasks"] == []
    assert any("QLoRA" in w["what"] for w in plan["windows"])   # 0.4: окно ночью
    assert any("план дня" in w["what"] for w in plan["windows"])
    assert plan["feature_slots"] == 1   # 12.11.2026 — четверг, будний день


def test_weekend_no_feature_slots(planner):
    plan = planner.build_plan(day=dt.date(2026, 11, 15), now=dt.datetime(2026, 11, 15, 8, 0))
    assert plan["feature_slots"] == 0   # воскресенье: фишки не внедряем


def test_plan_idempotent(planner):
    p1 = planner.build_plan(day=dt.date(2026, 11, 12))
    p2 = planner.build_plan(day=dt.date(2026, 11, 12))
    assert p1 == p2                    # за день один план
    files = list(planner.data_dir.glob("plan_*.json"))
    assert len(files) == 1


def test_queue_tasks_sorted_and_capped(planner):
    add_task("мелочь", "low")
    add_task("срочно", "high")
    add_task("обычное", "normal")
    plan = planner.build_plan(day=dt.date(2026, 11, 12))
    titles = [t["title"] for t in plan["tasks"]]
    assert titles[0] == "срочно" and titles[-1] == "мелочь"
    assert plan["date"] == "2026-11-12"


def test_carry_over_from_yesterday(planner):
    yesterday = dt.date(2026, 11, 11)
    add_task("законченная задача")
    add_task("висит задача")
    plan_y = planner.build_plan(day=yesterday)
    assert len(plan_y["tasks"]) == 2
    planner.mark_task(plan_y["tasks"][0]["id"], "done", day=yesterday)
    plan_today = planner.build_plan(day=dt.date(2026, 11, 12))
    assert not any("законченная" in c for c in plan_today["carry_over"])  # done не переезжает
    assert any("висит" in c for c in plan_today["carry_over"])


def test_pending_only_carry_over(planner):
    """Неотмеченная (pending) задача вчера — переезжает."""
    yesterday = dt.date(2026, 11, 11)
    add_task("висяк")
    planner.build_plan(day=yesterday)
    planner2 = planner.build_plan(day=dt.date(2026, 11, 12))
    assert any("висяк" in c for c in planner2["carry_over"])


def test_should_run_respects_8am(planner):
    at7 = dt.datetime(2026, 11, 12, 7, 59)
    at8 = dt.datetime(2026, 11, 12, 8, 0)
    assert planner.should_run(at7) is False
    assert planner.should_run(at8) is True
    planner.tick(at8)                           # построили
    assert planner.should_run(at8) is False     # второй раз не нужно


def test_tick_returns_none_before_plan_hour(planner):
    assert planner.tick(dt.datetime(2026, 11, 12, 6, 0)) is None


def test_broken_queue_does_not_crash(planner, home):
    (config.QUEUE_FILE).write_text("{битый json", encoding="utf-8")
    plan = planner.build_plan(day=dt.date(2026, 11, 12))
    assert plan["tasks"] == []                  # дом выжил, план построен


def test_load_queue_missing_file(planner):
    assert load_queue(config.QUEUE_FILE.parent / "нет_такой.json") == []
