# -*- coding: utf-8 -*-
"""Тесты «сырые числа по-человечески» (Ф5, 23.11): урок живого лога —
[68621991936, 21075320832, 69.3, ...] без перевода — не ответ."""
import pytest

from core import humanize


# ---------- перевод чисел ----------

def test_ram_list_gets_byte_translation():
    """Тот самый список из лога: байты получают ГБ с честной оговоркой."""
    raw = "[68621991936, 21075320832, 69.3, 47546671104, 21075320832]"
    out = humanize.humanize_numbers(raw)
    assert raw in out                        # сырьё не спрятано
    assert "63.9 ГБ" in out                 # 68621991936 / 2**30
    assert "19.6 ГБ" in out                 # 21075320832 / 2**30
    assert "44.3 ГБ" in out                 # 47546671104 / 2**30
    assert "если это байты" in out          # оговорка честности
    assert "69.3" not in out.split("по-человечески")[1]   # мелкое не тронуто


def test_small_numbers_untouched():
    """Мелкие числа читаются и так: расшифровка не нужна."""
    out = humanize.humanize_numbers("ответ: 42, процентов 69.3, строк 100")
    assert out == "ответ: 42, процентов 69.3, строк 100"


def test_counters_get_millions():
    """Миллионы — серединка: может счётчик, может байты; честность —
    ОБА прочтения, Создатель выбирает. Гигабайты и выше — байты."""
    out = humanize.humanize_numbers("шагов: 3500000")
    assert "3.5 млн" in out
    assert "3.3 МБ" in out and "если это байты" in out


def test_versions_and_words_not_matched():
    """«v1234567» и «abc12345678» — части слов, не голые числа."""
    assert humanize.big_numbers("v1234567 и x12345678y") == []
    assert humanize.big_numbers("1.2345678") == []       # дробь


def test_unique_in_order_and_capped():
    """Дубли не повторяются, потолок 4 — расшифровка помощь, не лекция."""
    nums = humanize.big_numbers(
        "1111111 2222222 3333333 4444444 5555555 1111111")
    assert nums == [1111111, 2222222, 3333333, 4444444, 5555555]
    out = humanize.humanize_numbers(" ".join(str(n) for n in nums))
    assert "…" in out                       # за потолком — честное многоточие


def test_terabytes():
    out = humanize.humanize_numbers("диск: 2000398934016 байт")
    assert "1.8 ТБ" in out
