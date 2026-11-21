# -*- coding: utf-8 -*-
r"""tests/test_battery_report_button.py — статические проверки кнопки 88.

Кнопка-выручалка: сводка батареи по требованию, без нового прогона.
Урок 21.11 (батарея 13:37): шаг [3] кнопки 87 упал — файл
battery_report.py ещё не приехал из bundle, а Создателю нужна сводка.
Кнопка 88 честно говорит, чего не хватает, и не жгёт время.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BAT = ROOT / "scripts" / "88_battery_report.bat"


def _text() -> str:
    return BAT.read_text(encoding="utf-8")


def test_button_exists():
    assert BAT.is_file(), "кнопка scripts/88_battery_report.bat пропала"


def test_runs_report_not_battery():
    """Сводка — да, новая батарея — нет: минут не жжём."""
    t = _text()
    assert "scripts\\battery_report.py" in t
    assert "brain_battery.py" not in t


def test_missing_file_is_honest():
    """Нет battery_report.py — честная инструкция, а не питон-ошибка."""
    t = _text()
    assert "if not exist scripts\\battery_report.py" in t
    assert "80_sync_github.bat" in t          # как файл приедет


def test_finish_points_to_one_file():
    t = _text()
    assert "battery_report.txt" in t
    assert "pause" in t


def test_button_version_marked():
    """BTN_VER — семейная метка кнопок: версию видно в файле."""
    assert "BTN_VER 88.1" in _text()
