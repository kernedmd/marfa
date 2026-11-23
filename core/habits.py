# -*- coding: utf-8 -*-
"""core/habits.py — ПРИВЫЧКИ (Ф15, 23.11): «отметь: вода» … «привычки».

Привычка — дело повторяющееся, и её сила — в серии дней. «привычка: X»
— завести, «отметь: X» — отметиться сегодня (раз в день; второй раз —
честное «уже отмечено»), «привычки» — список с сериями ([x] сегодня
отмечено, [ ] ещё нет), «сотри привычку N» — убрать. Серия считается
подряд идущими днями; сегодняшний день без отметки не рвёт серию —
вечер ещё не кончился (честный подсчёт: серия «до вчера» жива).
"""
from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path

from core import config


def _file() -> Path:
    return Path(config.HABITS_FILE)


def _load() -> dict:
    try:
        data = json.loads(_file().read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("habits"), list) \
                and isinstance(data.get("marks"), dict):
            return data
    except (OSError, ValueError):
        pass
    return {"habits": [], "marks": {}}


def _save(data: dict) -> None:
    _file().parent.mkdir(parents=True, exist_ok=True)
    _file().write_text(
        json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def _day(d: dt.date) -> str:
    return d.strftime("%Y-%m-%d")


def _find(data: dict, what: str):
    low = str(what or "").lower().strip()
    for h in data["habits"]:
        if str(h.get("text", "")).lower() == low:
            return h
    return None


def add(what: str) -> str:
    """«привычка: вода» — завести; дубль — честное «уже есть»."""
    name = str(what or "").strip()[:80]
    if not name:
        return "какую привычку завести? скажи «привычка: вода»"
    data = _load()
    if _find(data, name):
        return "привычка «%s» уже есть" % name
    hid = max([int(h.get("id", 0)) for h in data["habits"]] or [0]) + 1
    data["habits"].append({"id": hid, "text": name})
    _save(data)
    return "завела привычку: %s — отмечай «отметь: %s»" % (name, name)


def mark(what: str, now: dt.date = None) -> str:
    """«отметь: вода» — отметиться сегодня (раз в день)."""
    now = now or dt.date.today()
    name = str(what or "").strip()[:80]
    if not name:
        return "что отметить? скажи «отметь: вода»"
    data = _load()
    h = _find(data, name)
    if h is None:
        return ("привычки «%s» нет; завести: «привычка: %s»" % (name, name))
    hid = str(h["id"])
    days = data["marks"].setdefault(hid, [])
    today = _day(now)
    if today in days:
        return "«%s» сегодня уже отмечена — два раза не считается" % name
    days.append(today)
    _save(data)
    streak = _streak(set(days), now)
    return "отметила: %s — серия %d дн." % (name, streak)


def _streak(days: set, today: dt.date) -> int:
    """Подряд идущие дни, заканчивающиеся сегодня или вчера."""
    n = 0
    d = today
    if _day(d) not in days:
        d -= dt.timedelta(days=1)      # сегодня ещё не отмечено — жива ли вчерашняя серия
    while _day(d) in days:
        n += 1
        d -= dt.timedelta(days=1)
    return n


def render(now: dt.date = None) -> str:
    """«привычки» — список с сериями и статусом сегодня."""
    now = now or dt.date.today()
    data = _load()
    if not data["habits"]:
        return "привычек нет; завести: «привычка: вода»"
    today = _day(now)
    lines = ["ПРИВЫЧКИ:"]
    for h in data["habits"]:
        days = set(data["marks"].get(str(h.get("id", "")), []))
        done = today in days
        streak = _streak(days, now)
        lines.append("%s %s — серия %d дн."
                     % ("[x]" if done else "[ ]",
                        str(h.get("text", ""))[:60], streak))
    return "\n".join(lines)


def erase(n: int) -> str:
    """«сотри привычку N» — убрать вместе с отметками."""
    data = _load()
    for i, h in enumerate(data["habits"]):
        if int(h.get("id", -1)) == int(n):
            data["habits"].pop(i)
            data["marks"].pop(str(h.get("id", "")), None)
            _save(data)
            return "стёрла привычку «%s»" % str(h.get("text", ""))[:60]
    return "привычки №%s нет — «привычки» покажет список" % n
