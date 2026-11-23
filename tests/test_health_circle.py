# -*- coding: utf-8 -*-
"""Тесты круга 4 «Время и здоровье» (Ф26–Ф30): праздники, время в городе,
круговые напоминания, разминка, помидор."""
import datetime as dt

import pytest

from core import config, reminders, holidays, worldtime, stretch, pomodoro


@pytest.fixture()
def home(tmp_path, monkeypatch):
    data = tmp_path / "data"
    monkeypatch.setattr(config, "HOME_DIR", tmp_path)
    monkeypatch.setattr(config, "DATA_DIR", data)
    monkeypatch.setattr(config, "POMODORO_FILE", data / "pomodoro.json")
    yield tmp_path


NOW = dt.datetime(2026, 11, 23, 15, 0)      # понедельник
TODAY = dt.date(2026, 11, 23)


# ---------- Ф26 праздники ----------

def test_holidays_today_yes_and_no():
    assert "День народного единства" in holidays.today_check(dt.date(2026, 11, 4))
    out = holidays.today_check(TODAY)
    assert "нет" in out and "через" in out


def test_holidays_year_list_and_nearest():
    r = holidays.render_year(TODAY)
    assert "День России" in r and "переходящие" in r
    assert "ближайший праздник: Новый год" in holidays.nearest(TODAY)
    assert "День народного единства" in holidays.nearest(dt.date(2026, 11, 1))


def test_holidays_new_year_boundary():
    out = holidays.today_check(dt.date(2026, 1, 7))
    assert "Рождество" in out


# ---------- Ф27 время в городе ----------

def test_worldtime_known_city():
    out = worldtime.time_in("токио", dt.datetime(2026, 11, 23, 12, 0,
                                                 tzinfo=dt.timezone.utc))
    assert "21:00" in out and "Токио" in out


def test_worldtime_russian_fallback_constant_shift(monkeypatch):
    import builtins
    real_import = builtins.__import__

    def no_zoneinfo(name, *a, **k):
        if name == "zoneinfo":
            raise ImportError("нет базы")
        return real_import(name, *a, **k)
    monkeypatch.setattr(builtins, "__import__", no_zoneinfo)
    out = worldtime.time_in("владивосток", dt.datetime(2026, 11, 23, 12, 0,
                                                       tzinfo=dt.timezone.utc))
    assert "23:00" in out and "не переводит часы" in out
    assert "во Владивостоке" in out


def test_worldtime_unknown_city_refuses_with_menu():
    out = worldtime.time_in("паиж")
    assert "не знаю" in out and "Токио" in out


def test_worldtime_foreign_city_without_tzdata_honest(monkeypatch):
    import builtins
    real_import = builtins.__import__

    def no_zoneinfo(name, *a, **k):
        if name == "zoneinfo":
            raise ImportError("нет базы")
        return real_import(name, *a, **k)
    monkeypatch.setattr(builtins, "__import__", no_zoneinfo)
    out = worldtime.time_in("лондон", dt.datetime(2026, 11, 23, 12, 0,
                                                  tzinfo=dt.timezone.utc))
    assert "выдумывать" in out


# ---------- Ф28 круговые напоминания ----------

def test_recurring_parse_day_and_hour(home):
    plan = reminders.parse_recurring("напоминай каждый день в 20:00: чай", NOW)
    assert plan["rec"] == "day" and plan["hh"] == 20 and plan["text"] == "чай"
    assert plan["due"] == NOW.replace(hour=20, minute=0)
    plan2 = reminders.parse_recurring("напоминай каждый час: пей воду", NOW)
    assert plan2["rec"] == "hour" and plan2["text"] == "пей воду"
    assert reminders.parse_recurring("напомни через 5 минут", NOW) is None


def test_recurring_past_time_starts_tomorrow(home):
    plan = reminders.parse_recurring("напоминай каждый день в 08:00: зарядка",
                                     NOW)          # 15:00 сейчас
    assert plan["due"].date() == NOW.date() + dt.timedelta(days=1)
    assert plan["due"].hour == 8


def test_recurring_rings_and_shifts_not_dies(home):
    plan = reminders.parse_recurring("напоминай каждый час: вода", NOW)
    reminders.add_recurring(plan)
    hit = reminders.due(NOW + dt.timedelta(minutes=61), mark=True)
    assert len(hit) == 1 and "вода" in hit[0]["text"]
    # не умерло: следующий круг на подходе
    active = reminders.active(NOW + dt.timedelta(minutes=61))
    assert active and active[0].get("rec") == "hour"
    # и снова звонит через час
    hit2 = reminders.due(NOW + dt.timedelta(minutes=122), mark=True)
    assert len(hit2) == 1


def test_recurring_daily_skips_missed_night(home):
    plan = reminders.parse_recurring("напоминай каждый день в 09:00: кофе",
                                     dt.datetime(2026, 11, 22, 20, 0))
    reminders.add_recurring(plan)
    # пришли через 2 дня: оба пропущенных круга проскакивают молча,
    # звонок один, следующий — завтра
    hit = reminders.due(dt.datetime(2026, 11, 24, 12, 0), mark=True)
    assert len(hit) == 1
    assert hit[0]["due"].startswith("2026-11-25T09:00")


def test_recurring_render_marks_circle(home):
    plan = reminders.parse_recurring("напоминай каждый день в 20:00: чай", NOW)
    reminders.add_recurring(plan)
    assert "ПО КРУГУ" in reminders.render_active(NOW)


def test_cancel_by_marker(home):
    plan = reminders.parse_recurring("напоминай каждый час: вода", NOW)
    reminders.add_recurring(plan, marker={"stretch": True})
    assert reminders.has_marker("stretch", True)
    assert reminders.cancel_by_marker("stretch", True) is True
    assert reminders.has_marker("stretch", True) is False


# ---------- Ф29 разминка ----------

def test_stretch_enable_disable_idempotent(home):
    assert "включила" in stretch.enable()
    assert "уже включена" in stretch.enable()
    assert "включена" in stretch.status()
    assert "выключена" in stretch.disable()
    assert "не была" in stretch.disable()
    assert "выключена; включить" in stretch.status()


def test_stretch_reminder_is_hourly(home):
    stretch.enable()
    active = reminders.active(NOW)
    assert any(it.get("stretch") and it.get("rec") == "hour" for it in active)


# ---------- Ф30 помидор ----------

def test_pomodoro_start_rings_and_counts(home):
    out = pomodoro.start(25, NOW)
    assert "Напомню" in out and "помидоров: 1" in out
    assert "помидоров: 1" in pomodoro.render(NOW)
    pomodoro.start(15, NOW)
    assert "помидоров: 2" in pomodoro.render(NOW)


def test_pomodoro_bounds(home):
    assert "от 5 до 90" in pomodoro.start(2, NOW)
    assert "от 5 до 90" in pomodoro.start(120, NOW)


def test_pomodoro_empty_day_honest(home):
    assert "нет" in pomodoro.render(NOW)
