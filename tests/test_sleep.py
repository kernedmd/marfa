# -*- coding: utf-8 -*-
"""Тесты СНА (23.11): окно ночи, «спи»/«проснись», история ночей,
пробуждение словом Создателя, синтез тихой ночи, короткие пробуждения."""
import datetime as dt

import pytest

from core import config
from core import sleep


@pytest.fixture()
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("MARFA_HOME", str(tmp_path))
    monkeypatch.setattr(config, "HOME_DIR", tmp_path)
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(config, "SLEEP_FILE", tmp_path / "data" / "sleep.json")
    config.ensure_dirs()
    yield tmp_path


NIGHT = dt.datetime(2026, 11, 23, 3, 0)        # воскресная ночь, внутри окна
DAY = dt.datetime(2026, 11, 23, 15, 0)         # день, вне окна
EVENING = dt.datetime(2026, 11, 23, 23, 0)     # вечер до окна


def test_window_night_day(home):
    assert sleep._in_window(NIGHT) is True
    assert sleep._in_window(DAY) is False
    assert sleep._in_window(EVENING) is False
    assert sleep.is_asleep(NIGHT) is True
    assert sleep.is_asleep(DAY) is False


def test_go_to_bed_and_wake_by_creator(home):
    # уложили днём — спит не по расписанию
    reply = sleep.go_to_bed(DAY, reason="Илья сказал спи")
    assert "легла" in reply
    woke_at = DAY + dt.timedelta(hours=2)
    assert sleep.is_asleep(woke_at - dt.timedelta(minutes=1)) is True
    # слово Создателя будит
    rec = sleep.wake_on_message(woke_at)
    assert rec is not None
    assert rec["hours"] == 2.0
    assert rec["why_wake"] == "Илья разбудил"
    assert sleep.is_asleep(woke_at) is False
    # ночь записана в историю
    assert sleep.nights_count() == 1
    assert sleep.slept_hours(woke_at) == 2.0


def test_forced_sleep_expires_at_morning(home):
    # уложили в 23:00 — до какого утра спит: до 07:00 СЛЕДУЮЩЕГО дня
    sleep.go_to_bed(EVENING)
    assert sleep.is_asleep(dt.datetime(2026, 11, 24, 6, 59)) is True
    # 07:00 и позже — уже не спит (граница утра честно кончилась)
    assert sleep.is_asleep(dt.datetime(2026, 11, 24, 7, 0)) is False


def test_short_wake_does_not_pollute_history(home):
    # слово в 01:40 (10 минут сна) — «проснулась на минуту», не ночь
    rec = sleep.wake(dt.datetime(2026, 11, 23, 1, 40), reason="Илья разбудил")
    assert rec is None                       # ночи не записано — только счётчик
    assert sleep.nights_count() == 0
    assert sleep.wakes_count() == 1
    # и организм вернулся в сон: окно ещё идёт
    assert sleep.is_asleep(dt.datetime(2026, 11, 23, 1, 41)) is True


def test_night_passes_by_itself(home):
    # организм жил до ночи (рождение — днём раньше), ночь прошла тихо:
    # утро — она не спит, ночь синтезировалась
    assert sleep.is_asleep(DAY) is False          # первое касание: born = 15:00
    morning = dt.datetime(2026, 11, 24, 7, 2)     # следующее утро
    assert sleep.is_asleep(morning) is False
    n = sleep.last_night(morning)
    assert n is not None
    assert n["bed"].startswith("2026-11-24T01:30")
    assert n["wake"].startswith("2026-11-24T07:00")
    assert abs(n["hours"] - 5.5) < 0.01
    assert n["why_wake"] == "ночь прошла"


def test_word_wake_cuts_night_morning_sews_it(home):
    # слово в 04:00 — записан кусок ночи 01:30–04:00, организм уснул снова
    rec = sleep.wake(dt.datetime(2026, 11, 23, 4, 0), reason="Илья разбудил")
    assert rec is not None and abs(rec["hours"] - 2.5) < 0.01
    morning = dt.datetime(2026, 11, 23, 7, 30)
    n = sleep.last_night(morning)
    # синтез: 2,5 ч до слова + 3 ч после (04:00–07:00) = целая ночь 5,5 ч
    assert abs(n["hours"] - 5.5) < 0.01
    assert n["why_wake"] == "ночь с пробуждениями"
    assert n["bed"].startswith("2026-11-23T01:30")
    # второе слово в 05:00 — кровать там, где уснула снова (04:00)
    sleep.wake(dt.datetime(2026, 11, 23, 5, 0), reason="Илья разбудил")
    assert sleep.nights_count() == 2
    n2 = sleep.last_night(morning)
    # 2,5 + 1,0 + 2,0 (05:00–07:00) = 5,5 ч — куски не двойнятся
    assert abs(n2["hours"] - 5.5) < 0.01


def test_forced_before_window_counted_from_forced(home):
    # уложена в 23:00, слов не было — утро собирает ночь с момента «спи»
    sleep.go_to_bed(EVENING)
    morning = dt.datetime(2026, 11, 24, 7, 30)
    n = sleep.last_night(morning)
    assert n is not None
    assert n["bed"].startswith("2026-11-23T23:00")
    assert abs(n["hours"] - 8.0) < 0.01


def test_already_in_window_no_double_forced(home):
    reply = sleep.go_to_bed(NIGHT)
    assert "уже сплю" in reply
    assert sleep.forced_reason(NIGHT) is None   # дубль не писался


def test_status_and_morning_texts(home):
    # организм родился днём — ночей ещё не видел, статус отдан uptime'у
    assert sleep.status_text(DAY) is None
    assert "ночей ещё не записано" in sleep.morning_text(DAY)
    # следующая ночь прошла тихо — утром правда сна на месте
    morning = dt.datetime(2026, 11, 24, 7, 30)
    st = sleep.status_text(morning)
    assert st is not None
    assert "не сплю с 07:00" in st and "5 ч 30 мин" in st
    m = sleep.morning_text(morning, dream="дом и тихие глаза")
    assert "выспалась" in m
    assert "снилось" in m


def test_short_night_quality_honest(home):
    # уложили днём, разбудили через 2 ч — утро честно скажет «короткой»
    sleep.go_to_bed(DAY)
    m = sleep.morning_text(DAY + dt.timedelta(hours=2))
    assert "ночь вышла короткой" in m


def test_broken_file_is_honest_day(home):
    (home / "data" / "sleep.json").write_text("{битый json", encoding="utf-8")
    assert sleep.is_asleep(DAY) is False
    assert sleep.nights_count() == 0
    assert sleep.status_text(DAY) is None


def test_state_line_variants(home):
    assert "ночей ещё не записано" in sleep.state_line(DAY)
    morning = dt.datetime(2026, 11, 24, 7, 30)
    assert "последняя ночь" in sleep.state_line(morning)
    sleep.go_to_bed(morning)
    assert "сейчас сплю" in sleep.state_line(morning)


def test_window_across_midnight(home, monkeypatch):
    # окно через полночь (23:00–06:00) — тоже обязано считаться честно
    monkeypatch.setattr(config, "SLEEP_WINDOW", ("23:00", "06:00"))
    sleep.is_asleep(dt.datetime(2026, 11, 23, 20, 0))   # рождение органа
    assert sleep._in_window(dt.datetime(2026, 11, 23, 23, 30)) is True
    assert sleep._in_window(dt.datetime(2026, 11, 24, 3, 0)) is True
    assert sleep._in_window(dt.datetime(2026, 11, 24, 6, 0)) is False
    assert sleep._in_window(dt.datetime(2026, 11, 24, 12, 0)) is False
    # и синтез ночи через полночь: легла 23:00, встала 06:00 = 7 ч
    morning = dt.datetime(2026, 11, 24, 9, 0)
    n = sleep.last_night(morning)
    assert n is not None
    assert n["bed"].startswith("2026-11-23T23:00")
    assert n["wake"].startswith("2026-11-24T06:00")
    assert abs(n["hours"] - 7.0) < 0.01


def test_history_capped(home):
    for i in range(40):
        bed = dt.datetime(2026, 10, 1, 23, 0) + dt.timedelta(days=i)
        morning = dt.datetime(2026, 10, 2, 6, 55) + dt.timedelta(days=i)
        sleep.go_to_bed(bed)
        sleep.wake(morning, reason="ночь прошла")
    assert sleep.nights_count() <= 30
