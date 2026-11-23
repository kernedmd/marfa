# -*- coding: utf-8 -*-
"""core/birthdays.py — ДНИ РОЖДЕНИЯ (Ф16, 23.11): «др: Маша 5 мая».

Год не спрашиваем и не выдумываем (закон фактов №38): возраст — не
наше дело, дата — наше. «др: Имя 5 мая» / «др: Имя 05.05» — записать,
«дни рождения» — список по близости, «у кого др» — ближайшие 30 дней.
Сегодня — празднуем первой строкой.
"""
from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path

from core import config


def _file() -> Path:
    return Path(config.BIRTHDAYS_FILE)


def _load() -> list[dict]:
    try:
        items = json.loads(_file().read_text(encoding="utf-8"))
        return [it for it in items if isinstance(it, dict)] \
            if isinstance(items, list) else []
    except (OSError, ValueError):
        return []


def _save(items: list[dict]) -> None:
    _file().parent.mkdir(parents=True, exist_ok=True)
    _file().write_text(
        json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")


MONTHS = {
    "январь": 1, "января": 1, "февраль": 2, "февраля": 2,
    "март": 3, "марта": 3, "апрель": 4, "апреля": 4,
    "май": 5, "мая": 5, "июнь": 6, "июня": 6,
    "июль": 7, "июля": 7, "август": 8, "августа": 8,
    "сентябрь": 9, "сентября": 9, "октябрь": 10, "октября": 10,
    "ноябрь": 11, "ноября": 11, "декабрь": 12, "декабря": 12,
}

_RX_WORD = re.compile(
    r"^др\s*[:;]\s*(.+?)\s+(\d{1,2})\s+([а-яё]+)$", re.IGNORECASE)
_RX_NUM = re.compile(
    r"^др\s*[:;]\s*(.+?)\s+(\d{1,2})\.(\d{1,2})$", re.IGNORECASE)


def _month_name(m: int) -> str:
    return {1: "января", 2: "февраля", 3: "марта", 4: "апреля",
            5: "мая", 6: "июня", 7: "июля", 8: "августа",
            9: "сентября", 10: "октября", 11: "ноября",
            12: "декабря"}[m]


def parse_add(text: str):
    """«др: Маша 5 мая» / «др: Маша 05.05» → (имя, день, месяц) | None.

    Несуществующая дата (31 февраля) — (None, ошибка): честный отказ,
    не молчаливое «записала»."""
    t = str(text or "").strip()
    m = _RX_WORD.match(t)
    if m:
        name, d, mon = m.group(1).strip(), int(m.group(2)), m.group(3).lower()
        if mon not in MONTHS:
            return None
        return _valid(name, d, MONTHS[mon])
    m = _RX_NUM.match(t)
    if m:
        name, d, mon = m.group(1).strip(), int(m.group(2)), int(m.group(3))
        return _valid(name, d, mon)
    return None


def _valid(name: str, d: int, mon: int):
    try:
        dt.date(2024, mon, d)              # високосный год-эталон
    except ValueError:
        return (None, "такой даты не бывает: %d %s" % (d, _month_name(mon)))
    if not name or len(name) > 60:
        return (None, "имя не поняла")
    return (name, d, mon)


def add(text: str) -> str:
    parsed = parse_add(text)
    if parsed is None:
        return ("не поняла; скажи «др: Маша 5 мая» или «др: Маша 05.05» "
                "(год не нужен — возраст не моё дело)")
    if len(parsed) == 2:
        return parsed[1]                    # честная ошибка из _valid
    name, d, mon = parsed
    items = _load()
    if any(str(it.get("name", "")).lower() == name.lower() for it in items):
        return "у %s день рождения уже записан" % name
    items.append({"id": max([int(it.get("id", 0)) for it in items] or [0]) + 1,
                  "name": name, "day": d, "month": mon})
    _save(items)
    return "запомнила: %s — %d %s" % (name, d, _month_name(mon))


def _days_until(item: dict, today: dt.date) -> int:
    try:
        nxt = dt.date(today.year, int(item.get("month", 1)),
                      int(item.get("day", 1)))
    except ValueError:
        return 9999
    if nxt < today:
        nxt = dt.date(today.year + 1, int(item.get("month", 1)),
                      int(item.get("day", 1)))
    return (nxt - today).days


def render(today: dt.date = None) -> str:
    """«дни рождения» — по близости; сегодня — празднуем."""
    today = today or dt.date.today()
    items = _load()
    if not items:
        return "дней рождения не записано; записать: «др: Маша 5 мая»"
    rows = sorted((( _days_until(it, today), it) for it in items),
                  key=lambda p: p[0])
    lines = ["ДНИ РОЖДЕНИЯ:"]
    for left, it in rows:
        name = str(it.get("name", ""))[:40]
        date = "%d %s" % (int(it.get("day", 0)),
                          _month_name(int(it.get("month", 1))))
        if left == 0:
            lines.append("СЕГОДНЯ у %s — поздравь с днём рождения!" % name)
        elif left <= 30:
            lines.append("%s — %s (через %d дн.)" % (name, date, left))
        else:
            lines.append("%s — %s" % (name, date))
    return "\n".join(lines)


def upcoming(today: dt.date = None) -> str:
    """«у кого др» — ближайшие 30 дней или честное «далеко»."""
    today = today or dt.date.today()
    items = _load()
    if not items:
        return "дней рождения не записано; записать: «др: Маша 5 мая»"
    rows = sorted(((_days_until(it, today), it) for it in items),
                  key=lambda p: p[0])
    near = [(l, it) for l, it in rows if l <= 30]
    if not near:
        return ("в ближайшие 30 дней дней рождения нет — ближайший: "
                "%s, %d %s (через %d дн.)"
                % (rows[0][1].get("name", ""),
                   int(rows[0][1].get("day", 0)),
                   _month_name(int(rows[0][1].get("month", 1))), rows[0][0]))
    lines = []
    for left, it in near:
        if left == 0:
            lines.append("СЕГОДНЯ у %s — поздравь с днём рождения!"
                         % str(it.get("name", ""))[:40])
        else:
            lines.append("%s — через %d дн. (%d %s)"
                         % (str(it.get("name", ""))[:40], left,
                            int(it.get("day", 0)),
                            _month_name(int(it.get("month", 1)))))
    return "БЛИЖАЙШИЕ ДНИ РОЖДЕНИЯ:\n" + "\n".join(lines)
