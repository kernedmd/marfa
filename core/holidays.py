# -*- coding: utf-8 -*-
"""core/holidays.py — ПРАЗДНИКИ (Ф26, 23.11): «праздники» / «сегодня праздник?».

Государственные праздники России с фиксированной датой — в коде, не в
выдумке мозга (закон фактов). Переходящие (масленица, Пасха) дом НЕ
считает — честная оговорка, а не молчаливое притворство. «праздники» —
список года по датам, «сегодня праздник?» — про сегодня, «ближайший
праздник» — с отсчётом дней.
"""
from __future__ import annotations

import datetime as dt

# фиксированные нерабочие и большие даты (официальный календарь РФ)
FIXED = [                                    # (день, месяц, название)
    (1, 1, "Новый год"),
    (2, 1, "Новогодние каникулы"),
    (3, 1, "Новогодние каникулы"),
    (4, 1, "Новогодние каникулы"),
    (5, 1, "Новогодние каникулы"),
    (6, 1, "Новогодние каникулы"),
    (7, 1, "Рождество Христово"),
    (8, 1, "Новогодние каникулы"),
    (23, 2, "День защитника Отечества"),
    (8, 3, "Международный женский день"),
    (1, 5, "Праздник Весны и Труда"),
    (9, 5, "День Победы"),
    (12, 6, "День России"),
    (4, 11, "День народного единства"),
]
NOTE = ("календарь — государственные с фиксированной датой; "
        "переходящие (масленица, Пасха) не считаю — не выдумываю")

_MONTHS = {1: "января", 2: "февраля", 3: "марта", 4: "апреля",
           5: "мая", 6: "июня", 7: "июля", 8: "августа",
           9: "сентября", 10: "октября", 11: "ноября", 12: "декабря"}


def _next_date(day: int, month: int, today: dt.date) -> dt.date:
    try:
        d = dt.date(today.year, month, day)
    except ValueError:
        return dt.date(today.year + 1, month, 1)
    return d if d >= today else dt.date(today.year + 1, month, day)


def render_year(today: dt.date = None) -> str:
    """«праздники» — год по датам, будущие первыми."""
    today = today or dt.date.today()
    rows = sorted(FIXED, key=lambda h: _next_date(h[0], h[1], today))
    lines = ["ПРАЗДНИКИ (год по кругу):"]
    for day, month, name in rows:
        d = _next_date(day, month, today)
        left = (d - today).days
        when = "сегодня!" if left == 0 else "через %d дн." % left
        lines.append("%d %s — %s (%s)"
                     % (day, _MONTHS[month], name, when))
    lines.append("(" + NOTE + ")")
    return "\n".join(lines)


def today_check(today: dt.date = None) -> str:
    """«сегодня праздник?» — честно: да с названием или нет."""
    today = today or dt.date.today()
    hits = [name for day, month, name in FIXED
            if (day, month) == (today.day, today.month)]
    if hits:
        return "да — сегодня %s! (%s)" % (hits[0], NOTE)
    nxt = min(_next_date(d, m, today) for d, m, _ in FIXED)
    left = (nxt - today).days
    return ("нет; ближайший — %d %s, через %d дн. (%s)"
            % (nxt.day, _MONTHS[nxt.month], left, NOTE))


def nearest(today: dt.date = None) -> str:
    """«ближайший праздник» — дата, название и сколько ждать."""
    today = today or dt.date.today()
    best = min(FIXED, key=lambda h: _next_date(h[0], h[1], today))
    d = _next_date(best[0], best[1], today)
    left = (d - today).days
    when = "уже сегодня!" if left == 0 else "через %d дн." % left
    return "ближайший праздник: %s — %d %s (%s)" % (
        best[2], best[0], _MONTHS[best[1]], when)
