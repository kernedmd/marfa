# -*- coding: utf-8 -*-
r"""tests/test_sync_trace.py — статические проверки кнопки 86_sync_trace.bat.

Диагност прогона 12:25 (21.11.2026): кнопка 80 запустилась, но до приёма
bundle не дошла — что случилось в окне, никто не записал. Кнопка 86 гоняет
80 с полным логом: даже при зависании последняя строка logs\sync_trace.log
показывает шаг. Кнопки работают на Z440 (cmd.exe), на станции не
запускаются — поэтому проверяем текст файла, как у кнопки 80.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BAT = ROOT / "scripts" / "86_sync_trace.bat"


def _text() -> str:
    return BAT.read_text(encoding="utf-8")


def test_button_exists():
    assert BAT.is_file(), "кнопка scripts/86_sync_trace.bat пропала"


def test_runs_button_80_with_auto():
    """Гоняет кнопку 80 в режиме /auto: пауз внутри нет, всё течёт в лог."""
    assert "scripts\\80_sync_github.bat /auto" in _text()


def test_log_captures_everything():
    """Весь вывод прогона — в logs\\sync_trace.log, с кодом завершения."""
    t = _text()
    assert "sync_trace.log" in t
    assert "2>&1" in t
    assert "ERRORLEVEL" in t


def test_window_does_not_vanish():
    """Финальная пауза и хвост лога в окне — Создатель видит финал прогона."""
    t = _text()
    assert "pause" in t
    assert "Get-Content" in t


def test_lives_in_home():
    """Кнопка работает из корня дома C:\\Marfa — как все кнопки дома."""
    assert "cd /d C:\\Marfa" in _text()


def test_hang_is_survivable():
    """Урок прогона 12:25: при зависании лог уже на диске — кнопка об этом говорит."""
    t = _text()
    assert "НЕ закрывать" in t
    assert "панель задач" in t


def test_bat_line_endings_pinned():
    """Урок первой поставки кнопки 86: файл, скачанный напрямую с LF-концами
    строк, cmd.exe рубит посреди строк ('xist', 'ace.log' — десинх парсера
    UTF-8+LF). .gitattributes прибивает *.bat к CRLF: любая доставка кнопки
    через git (checkout, bundle) получает виндовые концы строк автоматом.
    Прямые ссылки из песочницы архитектору конвертировать руками."""
    ga = ROOT / ".gitattributes"
    assert ga.is_file(), ".gitattributes пропал: концы строк кнопок не закреплены"
    assert "*.bat text eol=crlf" in ga.read_text(encoding="utf-8")
