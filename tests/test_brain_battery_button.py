# -*- coding: utf-8 -*-
r"""tests/test_brain_battery_button.py — статические проверки кнопки 87.

Батарея — ключ Этапа 1 (ROADMAP_v9_4): решает, можно ли Марфе живой
язык (гейт §5). Кнопка гоняет два прогона одной модели и собирает
сводку. Работает на Z440 (cmd.exe), на станции не запускается —
проверяем текст файла, как у кнопок 80/86.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BAT = ROOT / "scripts" / "87_brain_battery.bat"


def _text() -> str:
    return BAT.read_text(encoding="utf-8")


def test_button_exists():
    assert BAT.is_file(), "кнопка scripts/87_brain_battery.bat пропала"


def test_checks_brain_before_burn():
    """Мозг проверяется ДО прогонов: 10-25 минут в пустоту — не по-домашнему."""
    t = _text()
    assert "8082/health" in t
    assert "start_llama_server.bat" in t  # честная инструкция, если мозг спит


def test_two_runs_with_qwen3_fix():
    """Прогон «как есть» + прогон с фиксом сэмплинга Qwen3 (temp 0.7, top-p 0.8)."""
    t = _text()
    assert "--tag %TAGV%-default" in t
    assert "--tag %TAGV%-fix --temp 0.7 --top-p 0.8" in t


def test_model_choice_builds_tag():
    """Выбор [4]/[6] задаёт тег q4km/q6km — вторая пара прогонов без консоли."""
    t = _text()
    assert "choice /C 46" in t
    assert "TAGV=q6km" in t and "TAGV=q4km" in t


def test_dead_brain_midrun_stops():
    """Мозг замолчал посреди прогона — честная остановка, а не «продолжаю»."""
    t = _text()
    assert t.count("if errorlevel 2") >= 2  # оба прогона охраняются


def test_summary_one_file_finish():
    """Финал — сводка одним файлом: Создатель несёт в чат ровно один файл."""
    t = _text()
    assert "battery_report.py" in t
    assert "battery_report.txt" in t
    assert "pause" in t
