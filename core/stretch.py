# -*- coding: utf-8 -*-
"""core/stretch.py — РАЗМИНКА (Ф29, 23.11): «разминка вкл» — каждый час.

Сидячая работа съедает спину и глаза; дом напоминает сам — по кругу
(Ф28): «разминка вкл» ставит ежечасное «встань, потянись, посмотри
вдаль», «разминка выкл» снимает, «разминка» — статус. Идемпотентно:
дважды «вкл» не плодит дублей (закон кнопок дома). Метка stretch=True
живёт в напоминании — орган находит своё и не трогает чужие.
"""
from __future__ import annotations

from core import reminders

MARKER = {"stretch": True}
WHAT = ("разомнись: встань, потяни спину, посмотри вдаль — минута живого "
        "тела лучше часа сидячего")


def enable() -> str:
    if reminders.has_marker("stretch", True):
        return "разминка уже включена — каждый час напомню"
    plan = {"rec": "hour",
            "due": __import__("datetime").datetime.now()
            + __import__("datetime").timedelta(hours=1),
            "hh": None, "mm": None, "text": WHAT}
    reminders.add_recurring(plan, marker=MARKER)
    return ("включила разминку: раз в час напомню встать и потянуться; "
            "выключить — «разминка выкл»")


def disable() -> str:
    if reminders.cancel_by_marker("stretch", True):
        return "разминка выключена — спина теперь твоя забота"
    return "разминка и не была включена"


def status() -> str:
    if reminders.has_marker("stretch", True):
        return "разминка включена — раз в час напомню встать и потянуться"
    return "разминка выключена; включить: «разминка вкл»"
