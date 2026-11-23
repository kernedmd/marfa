# -*- coding: utf-8 -*-
"""Тесты круга 5 «Разговор и память» (Ф31–Ф35)."""
import datetime as dt
import json

import pytest

from core import (config, talkstats, echo_search, dayroll, weekroll,
                  moodlog)
from core.dialog import DialogStore


@pytest.fixture()
def home(tmp_path, monkeypatch):
    data = tmp_path / "data"
    monkeypatch.setattr(config, "HOME_DIR", tmp_path)
    monkeypatch.setattr(config, "DATA_DIR", data)
    monkeypatch.setattr(config, "MOODLOG_FILE", data / "mood.json")
    monkeypatch.setattr(config, "POMODORO_FILE", data / "pomodoro.json")
    monkeypatch.setattr(config, "NOTES_FILE", data / "notes.json")
    monkeypatch.setattr(config, "SHOPPING_FILE", data / "shopping.json")
    monkeypatch.setattr(config, "WORKLOG_FILE", data / "worklog.json")
    monkeypatch.setattr(config, "EXPENSES_FILE", data / "expenses.json")
    monkeypatch.setattr(config, "HABITS_FILE", data / "habits.json")
    monkeypatch.setattr(config, "BIRTHDAYS_FILE", data / "birthdays.json")
    monkeypatch.setattr(config, "EVOLUTION_DIR", data / "evolution")
    return tmp_path


NOW = dt.datetime(2026, 11, 23, 15, 0)
TODAY = dt.date(2026, 11, 23)


def _dialog(home, rows):
    """Наполнить диалог: rows — [(role, text, ts)]."""
    store = DialogStore(data_dir=home / "data" / "dialog")
    for i, (role, text, ts) in enumerate(rows):
        rec = {"role": role, "text": text, "ts": ts}
        # append() ставит свой ts; пишем напрямую через файл
        path = store._path("main")
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {"turns": []}
        data["turns"].append(rec)
        path.write_text(json.dumps(data, ensure_ascii=False),
                        encoding="utf-8")


# ---------- Ф31 статистика разговора ----------

def test_talkstats_today_and_total(home):
    _dialog(home, [
        ("user", "привет, как дела", "23.11 10:00"),
        ("assistant", "жива", "23.11 10:01"),
        ("user", "ключи на столе", "22.11 09:00"),
    ])
    s = talkstats.collect(TODAY)
    assert s["today_user"] == 1 and s["today_marfa"] == 1
    assert s["today_words_user"] == 3
    assert s["total"] == 3
    r = talkstats.render(TODAY)
    assert "твоих реплик — 1" in r and "всего" in r


def test_talkstats_empty_and_other_day(home):
    _dialog(home, [("user", "вчера", "22.11 09:00")])
    assert "сегодня ещё не говорили" in talkstats.render(TODAY)
    assert "всего мы обменялись 1" in talkstats.render(dt.date(2026, 1, 1))


def test_talkstats_never_talked(home):
    assert "не разговаривали" in talkstats.render(TODAY)


# ---------- Ф32 что я говорил ----------

def test_echo_search_finds_user_turns_with_ts(home):
    _dialog(home, [
        ("user", "ключи оставил на столе", "23.11 10:00"),
        ("assistant", "ключи на столе — запомнила", "23.11 10:01"),
        ("user", "как погода", "23.11 11:00"),
    ])
    r = echo_search.search("ключи")
    assert "ТЫ ГОВОРИЛ" in r
    assert "ключи оставил на столе" in r
    assert "[23.11 10:00]" in r
    assert "запомнила" not in r            # ответы Марфы — мимо


def test_echo_search_empty_honest(home):
    _dialog(home, [("user", "привет", "23.11 10:00")])
    r = echo_search.search("кириллица-невидимка")
    assert "не слышала" in r


def test_echo_search_caps_at_five(home):
    _dialog(home, [("user", "п.repeat %d" % i, "23.11 10:0%d" % i)
                   for i in range(8)])
    r = echo_search.search("repeat")
    assert "… и ещё 3" in r


# ---------- Ф35 настроение ----------

def test_moodlog_add_and_render(home):
    assert "записала" in moodlog.add("отличное", NOW)
    moodlog.add("бодрое", NOW + dt.timedelta(hours=4))
    r = moodlog.render(NOW + dt.timedelta(hours=5))
    assert "бодрое" in r and "за сегодня записано 2" in r


def test_moodlog_empty_hint(home):
    assert "не записывал" in moodlog.render(NOW)


def test_moodlog_parse_requires_colon():
    assert moodlog.parse("настроение: супер")[0] == "add"
    assert moodlog.parse("настроение отличное") is None


def test_moodlog_broken_file(home):
    config.MOODLOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    config.MOODLOG_FILE.write_text("[[", encoding="utf-8")
    assert "не записывал" in moodlog.render(NOW)


# ---------- Ф33 как прошел день ----------

def test_dayroll_collects_organs(home):
    _dialog(home, [("user", "привет", "23.11 10:00"),
                   ("assistant", "жива", "23.11 10:01")])
    (home / "data").mkdir(parents=True, exist_ok=True)
    (home / "data" / "praise.json").write_text(
        json.dumps([{"ts": "2026-11-23T12:00:00", "what": "спасибо"}]),
        encoding="utf-8")
    from core import expenses, pomodoro, habits
    expenses.add("200 хлеб", NOW)
    pomodoro.start(25, NOW)
    habits.add("вода")
    habits.mark("вода", TODAY)
    r = dayroll.render(NOW)
    assert "разговор" in r and "похвала" in r
    assert "расходы" in r and "помидоры" in r and "привычки" in r


def test_dayroll_empty_day_honest(home):
    r = dayroll.render(NOW)
    assert "только начался" in r


# ---------- Ф34 итог недели ----------

def test_weekroll_dialog_and_pomodoro(home):
    _dialog(home, [("user", "раз", "23.11 10:00"),
                   ("user", "два", "22.11 10:00"),
                   ("user", "давно", "01.11 10:00")])
    from core import pomodoro
    pomodoro.start(25, NOW)
    pomodoro.start(25, NOW - dt.timedelta(days=2))
    r = weekroll.render(TODAY)
    assert "разговор: 2 реплик" in r
    assert "помидоров начато: 2" in r
    assert "01.11" not in r.split("разговор")[0]   # старое — мимо


def test_weekroll_empty_honest(home):
    r = weekroll.render(TODAY)
    assert "не нашлось" in r
