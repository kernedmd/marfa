# -*- coding: utf-8 -*-
"""core/chance.py — СЛУЧАЙНЫЕ РЕШЕНИЯ (Ф7, 23.11): монетка, кубик, выбор.

Домашний организм решает мелочи честным жребием: «брось монетку»,
«кубик», «выбери: чай или кофе». Источник случайности — системный
secrets (не math.random: дом не играет в предсказуемость), ответ —
человеческий, с оговоркой честности («кубик сказал 4 — не я»).
"""
from __future__ import annotations

import secrets

COIN = ("орёл", "решка")
DICE_WORDS = {
    1: "один", 2: "два", 3: "три", 4: "четыре", 5: "пять", 6: "шесть",
}


def coin() -> str:
    """«брось монетку»: орёл или решка — 50/50, без философии."""
    side = COIN[secrets.randbelow(2)]
    return "Монетка упала: %s." % side


def dice(n: int = 6) -> str:
    """«кубик» / «кубик 20»: честный бросок N-гранника (4..20..100)."""
    n = int(n or 6)
    if not 2 <= n <= 100:
        return ("кубик бывает от 2 до 100 граней — %d не бывает; "
                "скажи «кубик 20»" % n)
    face = secrets.randbelow(n) + 1
    word = DICE_WORDS.get(face, str(face))
    return "Кубик (d%d) показал: %s." % (n, word)


def choose(options: list) -> str:
    """«выбери: а, б или в» — жребий из списка вариантов."""
    opts = [str(o).strip(" .!?") for o in options if str(o).strip()]
    if len(opts) < 2:
        return ("нужны хотя бы два варианта: «выбери: чай или кофе»")
    if len(set(o.lower() for o in opts)) < len(opts):
        return ("варианты повторяются — я выберу один и тот же; "
                "скажи два разных")
    pick = opts[secrets.randbelow(len(opts))]
    return "Жребий выбрал: %s." % pick


def rand_between(a: int, b: int) -> str:
    """Ф20: «число от 1 до 100» — честное случайное число в границах.

    Границы — разумные (до миллиарда: дом не играет в астрономию),
    перевёрнутые («от 10 до 1») — честный отказ, не молчаливый swap:
    Создатель знает, что спросил."""
    try:
        a, b = int(a), int(b)
    except (TypeError, ValueError):
        return "границы должны быть числами: «число от 1 до 100»"
    if not (-10**9 <= a <= 10**9 and -10**9 <= b <= 10**9):
        return "границы — в пределах миллиарда: «число от 1 до 100»"
    if a > b:
        return "от %d до %d не бывает — первое число больше второго" % (a, b)
    return "Случайное число от %d до %d: %d." % (a, b, secrets.randbelow(b - a + 1) + a)


def coin_times(n: int) -> str:
    """Ф21: «монетка 10 раз» — серия бросков со сводкой.

    Один бросок — «брось монетку»; серия — статистика: сколько орлов
    и решек выпало. Дом не играет в предсказуемость: secrets."""
    try:
        n = int(n)
    except (TypeError, ValueError):
        return "сколько раз? скажи «монетка 10 раз»"
    if not 2 <= n <= 100:
        return "серия бывает от 2 до 100 бросков — скажи «монетка 10 раз»"
    heads = sum(1 for _ in range(n) if secrets.randbelow(2) == 0)
    tails = n - heads
    return "%d монет: %d орлов, %d решек." % (n, heads, tails)


def parse_choose(text: str) -> list:
    """Разобрать «выбери: а, б или в» на варианты («или» и «,»)."""
    import re
    m = re.match(r"^выбер(?:и|ьте)\s*[:;,—-]?\s*(.+)$",
                 str(text or "").strip(), re.IGNORECASE)
    if not m:
        return []
    body = m.group(1).rstrip("?.!")
    parts = re.split(r"\s+или\s+|,|;", body, flags=re.IGNORECASE)
    return [p.strip() for p in parts if p.strip()]
