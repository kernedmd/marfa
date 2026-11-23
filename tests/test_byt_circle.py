# -*- coding: utf-8 -*-
"""Тесты круга 1 «Быт и списки» (Ф11–Ф15, 23.11): заметки, покупки,
трекер времени, расходы, привычки."""
import datetime as dt

import pytest

from core import config, notes, shopping, worklog, expenses, habits


@pytest.fixture()
def home(tmp_path, monkeypatch):
    """Песочница круга 1: все файлы органов — только в tmp_path.

    Константы config.XXX_FILE вычисляются на импорте — патчим каждую
    явно (урок изоляции: общий DATA_DIR их не трогает)."""
    data = tmp_path / "data"
    monkeypatch.setattr(config, "HOME_DIR", tmp_path)
    monkeypatch.setattr(config, "DATA_DIR", data)
    for const, fname in (
            ("NOTES_FILE", "notes.json"),
            ("SHOPPING_FILE", "shopping.json"),
            ("WORKLOG_FILE", "worklog.json"),
            ("EXPENSES_FILE", "expenses.json"),
            ("HABITS_FILE", "habits.json")):
        monkeypatch.setattr(config, const, data / fname)
    yield tmp_path


NOW = dt.datetime(2026, 11, 23, 15, 0)
TODAY = dt.date(2026, 11, 23)


# ---------- Ф11 заметки ----------

def test_notes_add_and_list(home):
    assert "записала" in notes.add("купить хлеб")
    assert "купить хлеб" in notes.render()


def test_notes_empty_payload_hint(home):
    assert "что записать" in notes.add("")


def test_notes_erase_and_missing(home):
    notes.add("первая")
    notes.add("вторая")
    assert "стёрла" in notes.erase(1)
    assert "№1" not in notes.render()
    assert "нет" in notes.erase(99)


def test_notes_broken_file_honest_zero(home):
    config.NOTES_FILE.parent.mkdir(parents=True, exist_ok=True)
    config.NOTES_FILE.write_text("не json", encoding="utf-8")
    assert "заметок нет" in notes.render()


def test_notes_parse_boundaries():
    assert notes.parse("заметка: позвонить маме") == ("add", "позвонить маме")
    assert notes.parse("сотри заметку 2") == ("erase", 2)
    assert notes.parse("заметки") is None            # список — отдельно
    assert notes.parse("заметка у меня плохая") is None   # без двоеточия — разговор


def test_notes_cap_prunes_old(home, monkeypatch):
    monkeypatch.setattr(notes, "CAP", 3)
    for i in range(5):
        notes.add("заметка %d" % i)
    out = notes.add("шестая")
    assert "подрезала" in out
    assert "заметка 0" not in notes.render()
    assert "шестая" in notes.render()


# ---------- Ф12 покупки ----------

def test_shopping_add_split_and_list(home):
    out = shopping.add("молоко, хлеб и масло")
    assert "молоко" in out and "масло" in out
    assert "молоко" in shopping.render()


def test_shopping_add_duplicate_visible(home):
    shopping.add("молоко")
    assert "уже было" in shopping.add("молоко")


def test_shopping_bought_by_number_and_name(home):
    shopping.add("молоко")
    shopping.add("хлеб")
    assert "вычеркнула" in shopping.bought("2")
    assert "хлеб" not in shopping.render()
    assert "вычеркнула" in shopping.bought("молоко")
    assert "пуст" in shopping.render().lower()


def test_shopping_clear(home):
    shopping.add("молоко")
    assert "очистила (1" in shopping.clear()
    assert "пуст" in shopping.render().lower()


def test_shopping_parse_boundaries():
    assert shopping.parse("купи: молоко, хлеб")[0] == "add"
    assert shopping.parse("куплено 2") == ("bought", "2")
    assert shopping.parse("очисть покупки") == ("clear",)
    assert shopping.parse("купи слона побольше") is None   # без двоеточия — разговор
    assert shopping.parse("куплено молоко") == ("bought", "молоко")


# ---------- Ф13 трекер времени ----------

def test_worklog_start_stop_today(home):
    assert "засекла" in worklog.start("отчёт", NOW)
    assert "отчёт — " in worklog.stop(NOW + dt.timedelta(minutes=25))
    r = worklog.render(NOW + dt.timedelta(minutes=30))
    assert "отчёт" in r and "25 мин" in r


def test_worklog_new_start_closes_previous(home):
    worklog.start("первое", NOW)
    out = worklog.start("второе", NOW + dt.timedelta(minutes=10))
    assert "прошлое закрыла" in out and "10 мин" in out
    r = worklog.render(NOW + dt.timedelta(minutes=15))
    assert "первое" in r and "СЕЙЧАС: второе" in r


def test_worklog_stop_without_start(home):
    assert "нечего закрывать" in worklog.stop(NOW)


def test_worklog_only_today_shown(home):
    worklog.start("вчерашнее", NOW - dt.timedelta(days=1))
    worklog.stop(NOW - dt.timedelta(days=1) + dt.timedelta(minutes=5))
    worklog.start("сегодняшнее", NOW)
    worklog.stop(NOW + dt.timedelta(minutes=5))
    r = worklog.render(NOW)
    assert "сегодняшнее" in r and "вчерашнее" not in r


def test_worklog_hours_format(home):
    worklog.start("марафон", NOW)
    out = worklog.stop(NOW + dt.timedelta(minutes=95))
    assert "1 ч 35 мин" in out


# ---------- Ф14 расходы ----------

def test_expenses_add_finds_amount_anywhere(home):
    assert "200" in expenses.add("200 хлеб", NOW)
    assert "масло — 350" in expenses.add("масло 350 руб", NOW)


def test_expenses_add_without_amount_refuses(home):
    assert "сколько" in expenses.add("хлеб", NOW)


def test_expenses_render_today_and_week(home):
    expenses.add("200 хлеб", NOW)
    expenses.add("1000 чайник", NOW - dt.timedelta(days=3))
    r = expenses.render(NOW)
    assert "сегодня: 200" in r
    assert "за 7 дней: 1 200" in r or "за 7 дней: 1200" in r


def test_expenses_broken_file(home):
    config.EXPENSES_FILE.parent.mkdir(parents=True, exist_ok=True)
    config.EXPENSES_FILE.write_text("[", encoding="utf-8")
    assert "не записано" in expenses.render(NOW)


# ---------- Ф15 привычки ----------

def test_habits_add_mark_streak(home):
    habits.add("вода")
    assert "отметила" in habits.mark("вода", TODAY)
    assert "серия 1" in habits.render(TODAY)


def test_habits_mark_twice_a_day_honest(home):
    habits.add("вода")
    habits.mark("вода", TODAY)
    assert "уже отмечена" in habits.mark("вода", TODAY)


def test_habits_unknown_mark_suggests_add(home):
    assert "нет; завести" in habits.mark("зарядка", TODAY)


def test_habits_streak_survives_today_not_marked(home):
    habits.add("вода")
    for k in (2, 1):
        habits.mark("вода", TODAY - dt.timedelta(days=k))
    r = habits.render(TODAY)         # сегодня НЕ отмечено
    assert "серия 2 дн" in r and "[ ]" in r


def test_habits_duplicate_add_and_erase(home):
    habits.add("вода")
    assert "уже есть" in habits.add("вода")
    assert "стёрла" in habits.erase(1)
    assert "привычек нет" in habits.render(TODAY)
