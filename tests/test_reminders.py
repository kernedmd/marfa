# -*- coding: utf-8 -*-
"""Тесты будильника дома (Ф10, 23.11): «напомни через N минут»."""
import datetime as dt
import json
from pathlib import Path

import pytest

from core import config, reminders


@pytest.fixture()
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("MARFA_HOME", str(tmp_path))
    monkeypatch.setattr(config, "HOME_DIR", tmp_path)
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    yield tmp_path


NOW = dt.datetime(2026, 11, 23, 15, 0)


# ---------- разбор времени ----------

def test_parse_in_minutes():
    plan = reminders.parse("напомни через 10 минут: перевернуть котлеты", NOW)
    assert plan["due"] == NOW + dt.timedelta(minutes=10)
    assert plan["text"] == "перевернуть котлеты"
    assert plan["when"] == "через 10 минут"


def test_parse_in_hours_seconds_days():
    assert reminders.parse("напомни через 2 часа: чай", NOW)["due"] \
        == NOW + dt.timedelta(hours=2)
    assert reminders.parse("напомни через 30 секунд: проверить", NOW)["due"] \
        == NOW + dt.timedelta(seconds=30)
    assert reminders.parse("напомни через 1 день: день рождения", NOW)["due"] \
        == NOW + dt.timedelta(days=1)


def test_parse_at_time_today_and_tomorrow():
    plan = reminders.parse("напомни в 20:00 выключить чайник", NOW)
    assert plan["due"] == NOW.replace(hour=20, minute=0)
    assert plan["text"] == "выключить чайник"
    # «в 8:00» в 15:00 — уже прошло, значит завтра
    plan2 = reminders.parse("напомни в 8:00 зарядка", NOW)
    assert plan2["due"].date() == NOW.date() + dt.timedelta(days=1)
    assert plan2["due"].hour == 8


def test_parse_absurd_time_not_matched():
    assert reminders.parse("напомни в 25:00 что-то", NOW) is None
    assert reminders.parse("напомни про день города", NOW) is None


def test_parse_without_text_is_timer():
    """«напомни через 5 минут» без слов — просто таймер, не отказ."""
    plan = reminders.parse("напомни через 5 минут", NOW)
    assert plan is not None and plan["text"] == ""


# ---------- жизнь напоминаний ----------

def test_add_and_fire_once(home):
    r = reminders.add(reminders.parse("напомни через 1 минуту: тест", NOW))
    assert "Напомню" in r and "тест" in r
    # раньше срока — молчит
    assert reminders.due_note(NOW + dt.timedelta(seconds=30)) == ""
    # время вышло — звонит
    note = reminders.due_note(NOW + dt.timedelta(minutes=2))
    assert "НАПОМИНАНИЕ" in note and "тест" in note
    # и только один раз: двойной звонок хуже молчания
    assert reminders.due_note(NOW + dt.timedelta(minutes=3)) == ""


def test_active_list_and_cancel(home):
    reminders.add(reminders.parse("напомни через 5 минут: первое", NOW))
    reminders.add(reminders.parse("напомни через 10 минут: второе", NOW))
    text = reminders.render_active(NOW + dt.timedelta(minutes=1))
    assert "первое" in text and "второе" in text and "№1" in text and "№2" in text
    r = reminders.cancel(1)
    assert "отменила" in r and "первое" in r
    text2 = reminders.render_active(NOW + dt.timedelta(minutes=1))
    assert "первое" not in text2 and "второе" in text2
    assert "среди живых нет" in reminders.cancel(99)


def test_empty_list_is_hint(home):
    text = reminders.render_active()
    assert "напоминаний нет" in text and "напомни через" in text


def test_broken_file_not_crash(home):
    reminders.reminders_file().parent.mkdir(parents=True, exist_ok=True)
    reminders.reminders_file().write_text("мусор", encoding="utf-8")
    assert reminders.due_note() == ""
    assert "напоминаний нет" in reminders.render_active()
