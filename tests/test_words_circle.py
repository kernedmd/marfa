# -*- coding: utf-8 -*-
"""Тесты круга 3 «Случай и слова» (Ф20–Ф25)."""
import re

import pytest

from core import chance, password, numeral, units
from core import translit as translit_mod


# ---------- Ф20 случайное число ----------

def test_rand_between_in_range():
    for _ in range(20):
        out = chance.rand_between(1, 100)
        n = int(re.search(r": (\d+)\.", out).group(1))
        assert 1 <= n <= 100
        assert "от 1 до 100" in out


def test_rand_between_reversed_refuses():
    assert "не бывает" in chance.rand_between(10, 1)


def test_rand_between_absurd_refuses():
    assert "миллиарда" in chance.rand_between(1, 10**12)


def test_rand_between_negative_ok():
    out = chance.rand_between(-5, 5)
    n = int(re.search(r": (-?\d+)\.", out).group(1))
    assert -5 <= n <= 5


# ---------- Ф21 монетка N раз ----------

def test_coin_times_counts_add_up():
    out = chance.coin_times(10)
    heads = int(re.search(r"(\d+) орлов", out).group(1))
    tails = int(re.search(r"(\d+) решек", out).group(1))
    assert heads + tails == 10
    assert "10 монет" in out


def test_coin_times_bounds():
    assert "от 2 до 100" in chance.coin_times(1)
    assert "от 2 до 100" in chance.coin_times(101)
    assert "сколько раз" in chance.coin_times("много")


# ---------- Ф22 пароль ----------

def test_password_default_length_and_alphabet():
    out = password.generate()
    pwd = out.split("\n")[0]
    assert len(pwd) == 16
    assert all(c in password.ALPHABET for c in pwd)


def test_password_custom_length():
    pwd = password.generate(24).split("\n")[0]
    assert len(pwd) == 24


def test_password_bounds_clamped_honestly():
    assert "подняла до 8" in password.generate(3)
    assert "укоротила до 64" in password.generate(100)


def test_password_honest_journal_warning():
    assert "журнале диалога" in password.generate()


def test_password_no_ambiguous_chars():
    for _ in range(10):
        pwd = password.generate(32).split("\n")[0]
        assert not set(pwd) & set("0O1lI|")


# ---------- Ф23 пропись ----------

def test_numeral_simple_and_complex():
    assert numeral.words(0) == "ноль"
    assert numeral.words(5) == "пять"
    assert numeral.words(2026) == "две тысячи двадцать шесть"
    assert numeral.words(21) == "двадцать один"
    assert numeral.words(1000001) == "один миллион один"
    assert numeral.words(-42) == "минус сорок два"


def test_numeral_feminine_thousands():
    assert numeral.words(2001) == "две тысячи один"
    assert numeral.words(21000) == "двадцать одна тысяча"


def test_numeral_teens_and_billions():
    assert numeral.words(12) == "двенадцать"
    assert numeral.words(19) == "девятнадцать"
    assert "миллиарда" in numeral.words(2_000_000_000)


def test_numeral_parse_and_refusals():
    assert numeral.parse("пропись 2026") == "две тысячи двадцать шесть"
    assert "целые" in numeral.parse("пропись 3.14")
    assert "целые" in numeral.parse("пропись двести")
    assert "триллиона" in numeral.parse("пропись 9999999999999")


# ---------- Ф24 транслит ----------

def test_translit_basic_and_case():
    assert translit_mod.translit("Привет") == "Privet"
    assert translit_mod.translit("Марфа") == "Marfa"
    assert translit_mod.translit("Ёлка Юра") == "Yolka Yura"


def test_translit_passthrough():
    assert translit_mod.translit("OK 100%") == "OK 100%"


def test_translit_parse_requires_colon():
    assert translit_mod.parse("транслит: здравствуй") == "zdravstvuy"
    assert "что перевести" in translit_mod.parse("транслит")


# ---------- Ф25 конвертер ----------

def test_units_length():
    out = units.convert(5, "км", "мили")
    assert "3,11" in out or "3,107" in out or "3,1069" in out


def test_units_weight():
    assert "72" in units.convert(72, "кг", "кг")
    out = units.convert(1, "кг", "фунт")
    assert "2,20" in out or "2,205" in out


def test_units_data():
    assert "1024" in units.convert(1, "мб", "кб")


def test_units_temperature():
    assert "68" in units.convert(20, "c", "f")
    assert "0" in units.convert(32, "f", "c")
    assert "273,15" in units.convert(0, "c", "k") or "273" in units.convert(0, "c", "k")


def test_units_cross_family_refuses():
    out = units.convert(5, "кг", "км")
    assert "не поняла вторую единицу" in out


def test_units_unknown_refuses_with_menu():
    out = units.convert(5, "версты", "мили")
    assert "не знаю таких единиц" in out and "миля" in out


def test_units_parse_comma_decimal():
    assert "5500" in units.parse("переведи 5,5 км в м")
    assert "не поняла" in units.parse("переди 5 км")
