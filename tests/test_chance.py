# -*- coding: utf-8 -*-
"""Тесты случайных решений (Ф7, 23.11): монетка, кубик, жребий."""
import pytest

from core import chance


def test_coin_two_sides_only():
    for _ in range(30):
        assert chance.coin() in ("Монетка упала: орёл.",
                                 "Монетка упала: решка.")


def test_coin_is_fair_enough():
    """50/50 без философии: за 200 бросков обе стороны выпадают."""
    sides = set()
    for _ in range(200):
        sides.add(chance.coin())
    assert sides == {"Монетка упала: орёл.", "Монетка упала: решка."}


def test_dice_range_and_words():
    for _ in range(60):
        out = chance.dice(6)
        assert any(w in out for w in ("один", "два", "три", "четыре",
                                      "пять", "шесть"))
        assert "d6" in out
    assert "d20" in chance.dice(20)
    assert "d100" in chance.dice(100)


def test_dice_absurd_sides_rejected():
    assert "не бывает" in chance.dice(1)
    assert "не бывает" in chance.dice(1000)


def test_choose_picks_from_list():
    opts = ["чай", "кофе"]
    for _ in range(20):
        out = chance.choose(opts)
        assert out in ("Жребий выбрал: чай.", "Жребий выбрал: кофе.")


def test_choose_needs_two_distinct():
    assert "два варианта" in chance.choose(["чай"])
    assert "повторяются" in chance.choose(["чай", "чай", "Чай"])


def test_parse_choose_variants():
    assert chance.parse_choose("выбери: чай или кофе") == ["чай", "кофе"]
    assert chance.parse_choose("Выбери: пиццу, суши или борщ") == \
        ["пиццу", "суши", "борщ"]
    assert chance.parse_choose("выбери") == []
    assert chance.parse_choose("что выбрать?") == []
