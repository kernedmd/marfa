# -*- coding: utf-8 -*-
"""core/personcard.py — Ф54 «ЧТО ТЫ ПОМНИШЬ ОБО МНЕ» (день-9, 24.11):
визитка Создателя, собранная из органов — каждый в своей броне.

Один вопрос — а отвечают многие: знакомство (people), законы его руками
(rules), привычки и серии, дни рождения близких, настроение словом,
сколько мы говорили. Упавший орган строку пропускает — визитка жива
(закон №10 р3). Пустой дом честно пуст: «расскажи о себе — запомню».
"""
from __future__ import annotations

from pathlib import Path

from core import config


def _line(name: str, fn) -> str | None:
    """Орган в броне: упал — строки нет, визитка жива."""
    try:
        val = fn()
        return ("  · %s: %s" % (name, val)) if val else None
    except Exception:
        return None


def render() -> str:
    """«что ты помнишь обо мне» — визитка из первых рук органов."""
    lines = ["ЧТО Я ПОМНЮ О СОЗДАТЕЛЕ:"]

    def _name():
        from core import people
        n = people.get_name()
        if not n:
            return None
        met = people.met_on()
        return "%s%s" % (n, " (познакомились %s)" % met if met else "")

    def _rules():
        from core import rules
        items = rules._load()
        if not items:
            return None
        return "%d законов нашего дома, все — твоими словами" % len(items)

    def _habits():
        from core import habits
        data = habits._load()
        items = data.get("habits") or []
        if not items:
            return None
        names = [str(it.get("name", "?")) for it in items][:6]
        return "привычек %d (%s)" % (len(items), ", ".join(names))

    def _birthdays():
        from core import birthdays
        items = birthdays._load()
        if not items:
            return None
        return "дни рождения записаны для %d человек" % len(items)

    def _mood():
        from core import moodlog
        items = moodlog._load()
        if not items:
            return None
        last = items[-1]
        return "настроение «%s» (%s)" % (last.get("mood", "?"),
                                         last.get("ts", "?"))

    def _talk():
        from core import talkstats
        text = talkstats.render()
        for piece in text.splitlines():
            if "всего" in piece.lower():
                return piece.strip(" ·")
        return None

    parts = [lines[0]]
    for name, fn in (("как тебя зовут", _name),
                     ("законы дома", _rules),
                     ("быт", _habits),
                     ("близкие", _birthdays),
                     ("как ты", _mood),
                     ("наши разговоры", _talk)):
        got = _line(name, fn)
        if got:
            parts.append(got)
    if len(parts) == 1:
        return ("пока почти пусто: имени не знаю, законов нет, привычек "
                "нет. Скажи «меня зовут <имя>» и «запиши правило: <текст>» "
                "— визитка начнёт жить")
    parts.append("это всё — из органов дома, по первым рукам; ничего не "
                 "выдумала")
    return "\n".join(parts)
