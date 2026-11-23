# -*- coding: utf-8 -*-
"""core/talkstats.py — СТАТИСТИКА РАЗГОВОРА (Ф31, 23.11): «сколько мы говорили».

Штампы «N с · ток» живут на каждом ответе, а общая картина — нигде:
сколько реплик и слов было сегодня, сколько всего. Диалоги — первые
руки (data/dialog), год в штампе хода «dd.mm HH:MM» выводим сами
(декабрь→январь переносится честно). Мозг молчит: это бухгалтерия,
не мысли.
"""
from __future__ import annotations

import datetime as dt

from core.dialog import DialogStore


def _day_key(ts: str, today: dt.date) -> bool:
    """Штамп хода «dd.mm HH:MM» — сегодня ли (год выводим по соседству)."""
    try:
        d, m = str(ts).split(" ")[0].split(".")[:2]
        return int(d) == today.day and int(m) == today.month
    except (ValueError, IndexError):
        return False


def collect(today: dt.date = None) -> dict:
    """Реплики и слова: сегодня и всего, по всем сессиям."""
    today = today or dt.date.today()
    store = DialogStore()
    out = {"today_user": 0, "today_marfa": 0,
           "today_words_user": 0, "today_words_marfa": 0,
           "total": 0}
    for sid in store.sessions():
        for t in store.turns(sid):
            text = str(t.get("text") or "")
            words = len(text.split())
            out["total"] += 1
            if not _day_key(str(t.get("ts") or ""), today):
                continue
            if t.get("role") == "user":
                out["today_user"] += 1
                out["today_words_user"] += words
            else:
                out["today_marfa"] += 1
                out["today_words_marfa"] += words
    return out


def render(today: dt.date = None) -> str:
    """«сколько мы говорили» — сегодняшний снимок и всего."""
    s = collect(today)
    if s["today_user"] == 0 and s["today_marfa"] == 0:
        if s["total"] == 0:
            return "мы ещё не разговаривали — начни первый разговор"
        return ("сегодня ещё не говорили; всего мы обменялись %d репликами"
                % s["total"])
    return ("сегодня: твоих реплик — %d (%s слов), моих — %d (%s слов); "
            "всего за жизнь дома — %d реплик"
            % (s["today_user"], _fmt(s["today_words_user"]),
               s["today_marfa"], _fmt(s["today_words_marfa"]),
               s["total"]))


def _fmt(n: int) -> str:
    return "{:,}".format(n).replace(",", " ")
