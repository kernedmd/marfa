# -*- coding: utf-8 -*-
"""core/agenda.py — «РАСПИСАНИЕ» (Ф36, 23.11): день дома одной командой.

Расписание живёт в коде (schedule.default_jobs), а Создатель его не
видит: «расписание» — честный список работ дома: когда что и что уже
сделано сегодня (по состоянию расписания — data/schedule_state.json).
Тихая внутренняя жизнь дома становится видимой — как эфир сделал
видимым думание.

УРОК КРУГА (день-8): «every» в job'ах расписания — СЕКУНДЫ (очередь=60,
доктор=300, библиотекарь=3600); первая ревизия читала их как минуты и
обещала «раз в 300 мин» между осмотрами доктора. Единицы — из
schedule.py, не из моих догадок; «по воскресеньям» — готовой формой
слова, а не швами основы и суффикса («по средуам» первой ревизии).
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from core import config
from core.schedule import default_jobs

# предложный падеж готовой формой: «по воскресеньям», «по средам»
_WEEKDAY_LOCATIVE = {0: "понедельникам", 1: "вторникам", 2: "средам",
                     3: "четвергам", 4: "пятницам", 5: "субботам",
                     6: "воскресеньям"}


def _safe_int(v, default: int) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _weekday_num(word: str) -> int:
    days = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
    w = str(word or "").lower()[:3]
    return days.index(w) if w in days else -1


def _when_human(j: dict) -> str:
    kind = j.get("kind", "")
    if kind == "daily":
        return "каждый день в %s" % j.get("at", "?")
    if kind == "interval":
        secs = _safe_int(j.get("every", 60), 60)
        if secs % 3600 == 0:
            h = secs // 3600
            return "раз в час" if h == 1 else "раз в %d ч" % h
        if secs >= 60:
            m = secs // 60
            return "раз в минуту" if m == 1 else "раз в %d мин" % m
        return "раз в %d с" % secs
    if kind == "weekly":
        wd = _WEEKDAY_LOCATIVE.get(_weekday_num(j.get("weekday", "")), "?")
        return "по %s в %s" % (wd, j.get("at", "?"))
    return str(kind or "?")


def _last_run(state: dict, job_id: str) -> str:
    """Последний прогон работы — человеческой строкой или ''."""
    try:
        ts = float((state.get(job_id) or {}).get("last", 0))
    except (TypeError, ValueError, AttributeError):
        return ""
    if ts <= 0:
        return ""
    return dt.datetime.fromtimestamp(ts).strftime("%d.%m %H:%M")


def render(now: dt.datetime = None) -> str:
    """«расписание» — что дом делает сам и когда."""
    now = now or dt.datetime.now()
    try:
        state = json.loads(
            Path(config.SCHEDULE_STATE_FILE).read_text(encoding="utf-8"))
        if not isinstance(state, dict):
            state = {}
    except (OSError, ValueError):
        state = {}            # битое состояние — работы всё равно известны
    lines = ["РАСПИСАНИЕ ДОМА (крутит служба стремления):"]
    for j in default_jobs():
        when = _when_human(j)
        last = _last_run(state, str(j.get("id", "")))
        if last and last.startswith(now.strftime("%d.%m")):
            today = "; сегодня было в %s" % last.split(" ")[1]
        elif last:
            today = "; было %s" % last
        else:
            today = ""
        lines.append("- %s — %s%s" % (j.get("what", "?"), when, today))
    lines.append("менять расписание — архитектору (core/schedule.py); "
                 "дом сообщает честно")
    return "\n".join(lines)
