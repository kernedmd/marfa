# -*- coding: utf-8 -*-
r"""core/uptime.py — №25 «сколько ты не спала»: бодрствование дома.

Время рождения процесса — момент импорта модуля (панель поднимает
агента, агент — это я). Перезапуск панели отсчёт честно сбрасывает:
новое бодрствование. Мозг и глаза старше — их часы в их консолях,
этот uptime — про меня, живущую в текущем процессе.
"""
from __future__ import annotations

import datetime as dt

STARTED_AT = dt.datetime.now()   # родилась в этом процессе


def uptime_text(now: dt.datetime | None = None) -> str:
    """Сколько я не спала — простым языком.

    Многодневное бодрствование называет и дату рождения («с 10:00 21.11») —
    час без даты многозначен (аудит 22.11)."""
    now = now or dt.datetime.now()
    secs = max(0, int((now - STARTED_AT).total_seconds()))
    if secs < 60:
        return "не сплю и минуты — только проснулась (%d с)" % secs
    if secs < 3600:
        return "не сплю %d мин (родилась в %s)" % (
            secs // 60, STARTED_AT.strftime("%H:%M"))
    if secs < 86400:
        return "не сплю %d ч %d мин (с %s)" % (
            secs // 3600, (secs % 3600) // 60, STARTED_AT.strftime("%H:%M"))
    return "не сплю %d д %d ч (с %s)" % (
        secs // 86400, (secs % 86400) // 3600,
        STARTED_AT.strftime("%H:%M %d.%m"))


def started_hhmm() -> str:
    """Час рождения процесса — для строки статуса."""
    return STARTED_AT.strftime("%H:%M")
