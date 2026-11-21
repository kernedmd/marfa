# -*- coding: utf-8 -*-
r"""tests/test_run_tests_button.py — статические проверки кнопки тестов v2.

Урок Ильи 21.11: run_tests.bat закрывал окно сразу после прогона —
ошибки было не прочитать, протокол терялся. v2: пауза в конце,
итог отдельными строками, полный протокол каждого прогона —
в logs\tests_last.txt. Урок 13:37 (кнопка руками + файл в bundle)
покрыт честной веткой: новый bat со старым ps1 предупреждает.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BAT = ROOT / "scripts" / "run_tests.bat"
PS1 = ROOT / "scripts" / "run_tests.ps1"


def _bat() -> str:
    return BAT.read_text(encoding="utf-8")


def _ps1() -> str:
    return PS1.read_text(encoding="utf-8-sig")


def test_button_exists():
    assert BAT.is_file(), "кнопка scripts/run_tests.bat пропала"
    assert PS1.is_file(), "движок scripts/run_tests.ps1 пропал"


def test_window_does_not_close():
    """Главный урок: окно остаётся открытым, пока не нажата клавиша."""
    t = _bat()
    assert "pause" in t
    assert "Нажми любую клавишу" in t


def test_verdict_is_readable():
    """Итог крупными строками: прошли / есть падения, а не мелькающий хвост."""
    t = _bat()
    assert "ТЕСТЫ ПРОШЛИ" in t
    assert "ЕСТЬ ПАДЕНИЯ" in t
    assert "%EC%" in t


def test_full_log_is_written():
    """Протокол не теряется, даже если окно закрылось само."""
    t = _ps1()
    assert "tests_last.txt" in t
    assert "Out-File" in t
    # питон в трубе пишет по-русски, а не кракозябрами локальной кодировки
    assert "PYTHONIOENCODING" in t
    # stderr (например, «No module named pytest») вливается в протокол,
    # а не роняет ps1 (в _common EAP=Stop)
    assert "2>&1" in t
    assert "cmd /c" in t


def test_ps1_is_utf8_bom():
    """Русский в ps1: Windows PowerShell 5.1 без BOM читает как ANSI."""
    raw = PS1.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf"), "ps1 должен быть UTF-8 с BOM"


def test_tests_live_in_temp_home():
    """Тесты гоняются во временном доме — настоящий дом не трогаем."""
    assert "marfa_dev" in _ps1()
    assert "MARFA_HOME" in _ps1()


def test_honest_branch_when_ps1_not_arrived():
    """Урок 13:37: bat руками + ps1 в bundle. Честное предупреждение,
    а не молчаливый обман («протокола нет» вместо пустого ожидания)."""
    t = _bat()
    assert 'findstr /C:"tests_last"' in t
    assert "80_sync_github.bat" in t


def test_button_version_marked():
    """BTN_VER — семейная метка кнопок: версию видно в файле."""
    assert "BTN_VER RT.2" in _bat()
