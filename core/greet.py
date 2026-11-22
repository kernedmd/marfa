# -*- coding: utf-8 -*-
"""core/greet.py — ЖИВОЕ ПРИВЕТСТВИЕ (Ф3, 23.11): «привет» — рефлекс, не шаблон.

Урок живого лога: каждое «привет» мозг встречал «Здравствуйте! Как я
могу вам помочь?» — сухо и одинаково. Домашний организм здоровается
как человек: время суток, имя (круг знакомства), сколько не виделись
(файлы диалога — из первых рук, не из выдумки). Мозг молчит: в
приветствии нечего думать, всё уже знает дом.
"""
from __future__ import annotations

import datetime as dt
from typing import Optional

from core import people


def _part_of_day(now: dt.datetime) -> str:
    """Часть суток по-человечески: утро/день/вечер/ночь."""
    h = now.hour
    if 5 <= h < 12:
        return "Доброе утро"
    if 12 <= h < 18:
        return "Добрый день"
    if 18 <= h < 23:
        return "Добрый вечер"
    return "Доброй ночи"


def _absence_text(since: Optional[dt.datetime],
                  now: dt.datetime) -> Optional[str]:
    """Сколько мы не виделись — человеческими словами; только что — None."""
    if since is None:
        return "мы ещё не разговаривали — приятно познакомиться"
    mins = (now - since).total_seconds() / 60.0
    if mins < 10:
        return None                      # только что общались — не считаем
    if mins < 60:
        return "не виделись %d минут" % int(mins)
    hours = mins / 60.0
    if hours < 24:
        return "не виделись %s" % _plural_hours(int(round(hours)))
    days = int(hours // 24)
    if days == 1:
        return "не виделись сутки"
    return "не виделись %d дней" % days


def _plural_hours(n: int) -> str:
    """Русская плюрализация часов: 1 час / 2 часа / 5 часов."""
    if n % 10 == 1 and n % 100 != 11:
        return "%d час" % n
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return "%d часа" % n
    return "%d часов" % n


def greeting_text(dialog=None, now: Optional[dt.datetime] = None) -> str:
    """«привет» одной командой: время суток + имя + отсутствие.

    dialog — DialogStore дома (для «сколько не виделись»); нет —
    приветствие живёт и без него. Имя — из круга знакомства (Ф2);
    файла нет — Создатель по канону дома: Илья.
    """
    now = now or dt.datetime.now()
    name = None
    try:
        name = people.get_name()
    except Exception:
        name = None
    name = name or "Илья"
    parts = [_part_of_day(now) + ", " + name + "!"]
    if dialog is not None:
        try:
            since = dialog.last_user_activity()
        except Exception:
            since = None
        absence = _absence_text(since, now)
        if absence:
            parts.append(absence + ".")
    parts.append("Я на месте, дом работает — говори, я слушаю.")
    return " ".join(parts)
