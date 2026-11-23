# -*- coding: utf-8 -*-
"""core/numeral.py — ПРОПИСЬ (Ф23, 23.11): «пропись 2026» → словами.

Числа в разговоре звучат словами, а интерфейсы дают цифры. Род
согласуется по правилам русского: «две тысячи», «один миллион»,
«двадцать одна тысяча» — а голое число остаётся мужского рода
(«двадцать один»). Целые от нуля до триллиона; дроби и прочее —
мозгу: прописывать их — работа смысла, не органов.
"""
from __future__ import annotations

import re

_WORDS = {
    1: ("один", "одна"), 2: ("два", "две"), 3: ("три", "три"),
    4: ("четыре", "четыре"), 5: ("пять", "пять"), 6: ("шесть", "шесть"),
    7: ("семь", "семь"), 8: ("восемь", "восемь"), 9: ("девять", "девять"),
}
_TEENS = {
    11: "одиннадцать", 12: "двенадцать", 13: "тринадцать",
    14: "четырнадцать", 15: "пятнадцать", 16: "шестнадцать",
    17: "семнадцать", 18: "восемнадцать", 19: "девятнадцать",
}
_TENS = {
    10: "десять", 20: "двадцать", 30: "тридцать", 40: "сорок",
    50: "пятьдесят", 60: "шестьдесят", 70: "семьдесят",
    80: "восемьдесят", 90: "девяносто",
}
_HUNDREDS = {
    100: "сто", 200: "двести", 300: "триста", 400: "четыреста",
    500: "пятьсот", 600: "шестьсот", 700: "семьсот",
    800: "восемьсот", 900: "девятьсот",
}


def _triplet_words(n: int, feminine: bool) -> list:
    """0..999 → слова; feminine — для разряда тысяч (одна, две)."""
    out: list = []
    h, rest = divmod(n, 100)
    if h:
        out.append(_HUNDREDS[h * 100])
    if 11 <= rest <= 19:
        out.append(_TEENS[rest])
        return out
    t, u = divmod(rest, 10)
    if t:
        out.append(_TENS[t * 10])
    if u:
        out.append(_WORDS[u][1 if feminine else 0])
    return out


def _plural_scale(n: int, forms) -> str:
    """n + форма: 1 рубль / 2 рубля / 5 рублей (для тысяч/миллионов)."""
    if n % 10 == 1 and n % 100 != 11:
        return forms[0]
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return forms[1]
    return forms[2]


def words(n: int) -> str:
    """Целое число прописью. 0..999 999 999 999; минус честно читается."""
    n = int(n)
    if n < 0:
        return "минус " + words(-n)
    if n == 0:
        return "ноль"
    if n > 999_999_999_999:
        raise ValueError("больше триллиона — скажи архитектору расширить")
    scales = ((1_000_000_000, ("миллиард", "миллиарда", "миллиардов"), False),
              (1_000_000, ("миллион", "миллиона", "миллионов"), False),
              (1_000, ("тысяча", "тысячи", "тысяч"), True))
    parts: list = []
    rest = n
    for scale, forms, feminine in scales:
        count, rest = divmod(rest, scale)
        if count:
            parts.extend(_triplet_words(count, feminine))
            parts.append(_plural_scale(count, forms))
    if rest or not parts:
        parts.extend(_triplet_words(rest, False))
    return " ".join(parts)


def parse(text: str) -> str:
    """«пропись 2026» / «пропись -42» — ответ или честный отказ."""
    m = re.match(r"^пропис[ья]\s+(-?\d{1,15})$", str(text or "").strip(),
                 re.IGNORECASE)
    if not m:
        return "пропись умеет целые числа: «пропись 2026» (дроби — мозгу)"
    n = int(m.group(1))
    try:
        return words(n)
    except ValueError as e:
        return str(e)
