# -*- coding: utf-8 -*-
"""Тесты круга 2 «Календарь» (Ф16–Ф19): дни рождения, когда и сколько."""
import datetime as dt

import pytest

from core import config, birthdays, when


@pytest.fixture()
def home(tmp_path, monkeypatch):
    data = tmp_path / "data"
    monkeypatch.setattr(config, "HOME_DIR", tmp_path)
    monkeypatch.setattr(config, "DATA_DIR", data)
    monkeypatch.setattr(config, "BIRTHDAYS_FILE", data / "birthdays.json")
    yield tmp_path


TODAY = dt.date(2026, 11, 23)          # понедельник


# ---------- Ф16 дни рождения ----------

def test_birthday_add_word_and_numeric(home):
    assert "запомнила: Маша — 5 мая" in birthdays.add("др: Маша 5 мая")
    assert "запомнила: Петя — 3 ноября" in birthdays.add("др: Петя 03.11")


def test_birthday_add_rejects_impossible_date(home):
    out = birthdays.add("др: Маша 31 февраля")
    assert "не бывает" in out


def test_birthday_add_requires_format(home):
    assert "не поняла" in birthdays.add("др: Маша")
    assert birthdays.add("др: Маша 5 мая")
    assert "уже записан" in birthdays.add("др: Маша 12 мая")


def test_birthday_today_is_first_line(home):
    birthdays.add("др: Маша 23 ноября")
    r = birthdays.render(TODAY)
    assert "СЕГОДНЯ у Маша" in r
    assert "поздравь" in birthdays.upcoming(TODAY)


def test_birthday_upcoming_30_days_and_far(home):
    birthdays.add("др: Маша 1 декабря")     # через 8 дней
    birthdays.add("др: Петя 1 марта")       # далеко
    up = birthdays.upcoming(TODAY)
    assert "Маша" in up and "через 8 дн." in up
    assert "Петя" not in up
    assert "Петя" in birthdays.render(TODAY)


def test_birthday_broken_file(home):
    config.BIRTHDAYS_FILE.parent.mkdir(parents=True, exist_ok=True)
    config.BIRTHDAYS_FILE.write_text("}{", encoding="utf-8")
    assert "не записано" in birthdays.render(TODAY)


# ---------- Ф17 сколько до ----------

def test_until_new_year():
    assert "39 дней" in when.until("сколько до нового года", TODAY)
    assert "1 января" in when.until("сколько до нового года", TODAY)


def test_until_date_words_and_numbers():
    assert "8 марта" in when.until("сколько до 8 марта", TODAY)
    assert "25 дней" in when.until("сколько до 18 декабря", TODAY)
    assert "2 дня" in when.until("сколько до 25.11", TODAY)


def test_until_past_date_counts_next_year():
    out = when.until("сколько до 8 марта", TODAY)
    assert "2027" in out


def test_until_iso_format():
    out = when.until("сколько до 2027-01-01", TODAY)
    assert "39 дней" in out and "пятница" in out


def test_until_unknown_date_hint():
    assert "не поняла" in when.until("сколько до Москвы", TODAY)


# ---------- Ф18 сколько прошло ----------

def test_since_september():
    assert "83 дня" in when.since("сколько прошло с 1 сентября", TODAY)


def test_since_future_date_honest():
    out = when.since("сколько прошло с 2027-01-01", TODAY)
    assert "не наступила" in out


def test_since_today():
    assert "сегодня" in when.since("сколько прошло с 23.11", TODAY)


# ---------- Ф19 день недели ----------

def test_weekday_known_dates():
    assert "четверг" in when.weekday("какой день недели 31 декабря", TODAY)
    assert "понедельник" in when.weekday("какой день недели 8 марта 2027", TODAY)
    assert "понедельник" in when.weekday("какой день недели 23 ноября", TODAY)


def test_weekday_past_this_year_notes_honestly():
    out = when.weekday("какой день недели 8 марта", TODAY)
    assert "уже прошло" in out and "воскресенье" in out


def test_weekday_unknown_hint():
    assert "не поняла" in when.weekday("какой день недели победы", TODAY)
