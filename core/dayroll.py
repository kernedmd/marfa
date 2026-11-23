# -*- coding: utf-8 -*-
"""core/dayroll.py — «КАК ПРОШЁЛ ДЕНЬ» (Ф33, 23.11): сводка дня из фактов.

Дневник (№8) пишет Марфа о себе; эта сводка — про БЫТ дня Создателя:
разговор, похвала, привычки, расходы, помидоры, настроение. Всё
механически, из первых рук органов; пустой день — честное «только
начался», а не выдуманный рассказ (закон фактов).
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from core import config


def _praise_today(today: dt.date) -> int:
    try:
        items = json.loads(
            (Path(config.DATA_DIR) / "praise.json").read_text(encoding="utf-8"))
        return sum(1 for it in items if isinstance(it, dict)
                   and str(it.get("ts", "")).startswith(today.isoformat()))
    except (OSError, ValueError):
        return 0


def render(now: dt.datetime = None) -> str:
    """«как прошел день» — факты дня по органам, каждый в своей броне."""
    now = now or dt.datetime.now()
    today = now.date()
    sections: list[tuple[str, list[str]]] = []

    # разговор
    try:
        from core import talkstats
        s = talkstats.collect(today)
        if s["today_user"] or s["today_marfa"]:
            sections.append(("разговор", [
                "реплик: твоих %d, моих %d" % (s["today_user"],
                                                s["today_marfa"])]))
    except Exception:
        pass

    # похвала
    try:
        n = _praise_today(today)
        if n:
            sections.append(("похвала", ["ты хвалил меня %d раз" % n]))
    except Exception:
        pass

    # привычки
    try:
        from core import habits
        data = habits._load()
        done = []
        for h in data["habits"]:
            days = set(habits._load()["marks"].get(str(h.get("id", "")), []))
            if today.strftime("%Y-%m-%d") in days:
                done.append(str(h.get("text", ""))[:40])
        if done:
            sections.append(("привычки", ["отмечено: " + ", ".join(done)]))
    except Exception:
        pass

    # расходы
    try:
        from core import expenses
        items = expenses._load()
        today_s = [it for it in items
                   if it.get("day") == today.strftime("%Y-%m-%d")]
        if today_s:
            total = sum(float(it.get("amount", 0)) for it in today_s)
            sections.append(("расходы", [
                "%d записей на %s руб" % (len(today_s),
                                          ("%.2f" % total).rstrip("0.")
                                          .rstrip(".").replace(".", ","))]))
    except Exception:
        pass

    # помидоры
    try:
        from core import pomodoro
        data = pomodoro._load()
        n = int((data.get("days") or {}).get(today.strftime("%Y-%m-%d"), 0))
        if n:
            sections.append(("помидоры", ["начато: %d" % n]))
    except Exception:
        pass

    # настроение Создателя
    try:
        from core import moodlog
        items = moodlog._load()
        todays = [it for it in items
                  if it.get("day") == today.strftime("%Y-%m-%d")]
        if todays:
            sections.append(("настроение", [
                "«%s» (%s)" % (todays[-1].get("text", ""),
                               todays[-1].get("ts", ""))]))
    except Exception:
        pass

    if not sections:
        return ("день только начался — фактов ещё нет; вечером я напишу "
                "дневник сама («подведи день»), а пока — «чем занимался»")
    lines = ["КАК ПРОШЁЛ ДЕНЬ (%s):" % today.strftime("%d.%m.%Y")]
    for name, rows in sections:
        lines.append("%s: %s" % (name, "; ".join(rows)))
    return "\n".join(lines)
