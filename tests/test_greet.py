# -*- coding: utf-8 -*-
"""Тесты живого приветствия (Ф3) и дайджеста «что нового» (Ф4), 23.11."""
import datetime as dt
import json
from pathlib import Path

import pytest

from core import config, digest, greet
from core.dialog import DialogStore
from core.memory import Memory


@pytest.fixture()
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("MARFA_HOME", str(tmp_path))
    monkeypatch.setattr(config, "HOME_DIR", tmp_path)
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    yield tmp_path


# ---------- часть суток и плюрализация ----------

def test_part_of_day():
    assert greet._part_of_day(dt.datetime(2026, 11, 23, 8)) == "Доброе утро"
    assert greet._part_of_day(dt.datetime(2026, 11, 23, 14)) == "Добрый день"
    assert greet._part_of_day(dt.datetime(2026, 11, 23, 20)) == "Добрый вечер"
    assert greet._part_of_day(dt.datetime(2026, 11, 23, 2)) == "Доброй ночи"


def test_plural_hours_russian():
    assert greet._plural_hours(1) == "1 час"
    assert greet._plural_hours(2) == "2 часа"
    assert greet._plural_hours(5) == "5 часов"
    assert greet._plural_hours(21) == "21 час"


# ---------- приветствие ----------

def test_greeting_names_and_absence(home):
    ds = DialogStore()
    ds.append("s1", "user", "привет")
    # штамп пишется «сейчас» — отсутствие < 10 минут, не считаем
    text = greet.greeting_text(dialog=ds)
    assert any(text.startswith(w) for w in ("Доброе", "Добрый", "Доброй"))
    assert "Илья" in text            # канон дома, файла знакомства нет
    assert "не виделись" not in text  # только что общались


def test_greeting_with_known_name(home):
    from core import people
    people.set_name("Мария")
    text = greet.greeting_text(dialog=None)
    assert "Мария" in text


def test_greeting_first_meeting_is_honest(home):
    text = greet.greeting_text(dialog=DialogStore())
    assert "не разговаривали" in text


def test_greeting_long_absence(home):
    ds = DialogStore()
    # ручная сессия со старым штампом: 5 часов назад
    old = (dt.datetime.now() - dt.timedelta(hours=5)).strftime("%d.%m %H:%M")
    ds.dir.mkdir(parents=True, exist_ok=True)
    (ds.dir / "session_old.json").write_text(json.dumps(
        {"session": "old", "turns": [{"role": "user", "text": "привет",
                                      "ts": old}]}, ensure_ascii=False),
        encoding="utf-8")
    text = greet.greeting_text(dialog=ds)
    assert "не виделись 5 часов" in text


# ---------- dialog.last_user_activity ----------

def test_last_user_activity_year_wrap(home):
    """Декабрьский штамп в январе: год выводится назад, отсутствие не
    превращается в «11 месяцев спустя» из-за границы года."""
    ds = DialogStore()
    now = dt.datetime.now()
    stamp = (now - dt.timedelta(days=1)).strftime("%d.%m %H:%M")
    ds.dir.mkdir(parents=True, exist_ok=True)
    (ds.dir / "session_x.json").write_text(json.dumps(
        {"session": "x", "turns": [
            {"role": "assistant", "text": "ранний ответ", "ts": stamp},
            {"role": "user", "text": "вопрос", "ts": stamp}]},
        ensure_ascii=False), encoding="utf-8")
    got = ds.last_user_activity()
    assert got is not None
    assert abs((now - got).total_seconds() - 86400) < 120


def test_last_user_activity_broken_files_ignored(home):
    ds = DialogStore()
    ds.dir.mkdir(parents=True, exist_ok=True)
    (ds.dir / "session_bad.json").write_text("не json", encoding="utf-8")
    (ds.dir / "session_ok.json").write_text(json.dumps(
        {"session": "ok", "turns": [
            {"role": "user", "text": "привет", "ts": "мусор"}]},
        ensure_ascii=False), encoding="utf-8")
    assert ds.last_user_activity() is None


# ---------- memory.recent ----------

def test_memory_recent_since(home):
    mem = Memory(data_dir=Path(config.DATA_DIR))
    mem.remember("старый факт", importance=1.0)
    since = dt.datetime.now().timestamp()   # граница: до — старое, после — новое
    mem.remember("новый факт", importance=1.0)
    got = mem.recent(since, limit=5)
    texts = [r["text"] for r in got]
    assert "новый факт" in texts
    assert "старый факт" not in texts


# ---------- дайджест ----------

def test_digest_first_meeting(home):
    text = digest.what_is_new(dialog=DialogStore(), memory=None)
    assert "ещё не разговаривали" in text


def test_digest_honest_silence(home):
    """Все органы молчат — честная тишина, не выдумка дел."""
    ds = DialogStore()
    old = (dt.datetime.now() - dt.timedelta(hours=3)).strftime("%d.%m %H:%M")
    ds.dir.mkdir(parents=True, exist_ok=True)
    (ds.dir / "session_old.json").write_text(json.dumps(
        {"session": "old", "turns": [{"role": "user", "text": "привет",
                                      "ts": old}]}, ensure_ascii=False),
        encoding="utf-8")
    text = digest.what_is_new(dialog=ds, memory=None)
    assert "Пока тебя не было" in text
    assert "тихо" in text


def test_digest_shows_new_memory(home):
    ds = DialogStore()
    old = (dt.datetime.now() - dt.timedelta(hours=2)).strftime("%d.%m %H:%M")
    ds.dir.mkdir(parents=True, exist_ok=True)
    (ds.dir / "session_old.json").write_text(json.dumps(
        {"session": "old", "turns": [{"role": "user", "text": "привет",
                                      "ts": old}]}, ensure_ascii=False),
        encoding="utf-8")
    mem = Memory(data_dir=Path(config.DATA_DIR))
    mem.remember("прочитала главу про стремление", importance=2.0)
    text = digest.what_is_new(dialog=ds, memory=mem)
    assert "запомнила" in text and "стремление" in text


def test_digest_survives_dead_organs(home):
    """Каждый орган в своей броне: упавший — честная строка, отчёт жив."""
    ds = DialogStore()

    class DeadDialog:
        def last_user_activity(self):
            raise RuntimeError("файлы пропали")

    text = digest.what_is_new(dialog=DeadDialog(), memory=None)
    assert "не разговаривали" in text        # честный ноль, не крах
