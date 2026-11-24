# -*- coding: utf-8 -*-
"""core/dayplan.py — «ПЛАН ДНЯ» ОДНОЙ КОМАНДОЙ (Ф8, 23.11).

Планировщик живёт своей жизнью в 08:00 (служба стремления), но Создатель
видел план только из консоли. Домашний организм отвечает на «план дня»
прямо в чате: сегодняшний план с прогрессом, вчерашние хвосты и очередь
завтрашнего — один честный снимок, мозг молчит.
"""
from __future__ import annotations

import datetime as dt

from core.autonomy import DayPlanner, load_queue

_STATUS_MARK = {
    "done": "[x]",
    "cancelled": "[—]",
    "in_progress": "[→]",
    "todo": "[ ]",
}


def _render_task(t: dict) -> str:
    mark = _STATUS_MARK.get(str(t.get("status", "todo")), "[ ]")
    title = str(t.get("title", "без названия"))
    return "%s %s" % (mark, title)


def today_plan(now: dt.datetime = None) -> str:
    """«план дня»: план + очередь, по-человечески.

    Плана ещё нет — честно: «строится в 08:00, добавить сейчас —
    «задача: <текст>»». Каждый блок в своей броне: битый план —
    про очередь, пустая очередь — про план.
    """
    now = now or dt.datetime.now()
    planner = DayPlanner()
    plan = planner.load_plan(now.date())
    lines = []

    if plan:
        tasks = [t for t in plan.get("tasks", [])
                 if isinstance(t, dict)]
        done = sum(1 for t in tasks if t.get("status") == "done")
        head = "ПЛАН НА СЕГОДНЯ (%s):" % now.strftime("%d.%m")
        if tasks:
            head += " %d из %d сделано" % (done, len(tasks))
        lines.append(head)
        for t in tasks[:12]:
            lines.append("- " + _render_task(t))
        if len(tasks) > 12:
            lines.append("… и ещё %d" % (len(tasks) - 12))
    else:
        lines.append("Плана на сегодня ещё нет — строится в 08:00 службой "
                     "стремления. Добавить прямо сейчас: «задача: <текст>», "
                     "потом скажи «план дня» ещё раз.")

    queue = load_queue()
    open_q = [t for t in queue
              if isinstance(t, dict) and t.get("status") != "done"]
    if open_q:
        lines.append("В ОЧЕРЕДИ (войдут в следующие планы):")
        for t in open_q[:6]:
            pr = str(t.get("priority", "normal"))
            lines.append("- %s (%s)" % (t.get("title", "?"), pr))
        if len(open_q) > 6:
            lines.append("… и ещё %d" % (len(open_q) - 6))
    if not plan and not open_q:
        lines.append("Очередь пуста: «задача: <текст>» — и завтрашний план "
                     "наполнится.")
    return "\n".join(lines)


def tomorrow_plan(now: dt.datetime = None) -> str:
    """Ф93 «ЧТО ЗАВТРА» (день-13, круг 16): завтра глазами сегодня.

    Честность по построению: завтрашний план строится службой
    стремления в 08:00 ЗАВТРА — раньше его не существует, и рисовать
    его сегодня нельзя (закон фактов). Что честно известно сегодня:
    незакрытые задачи сегодняшнего плана (перенос К6 переедут сами)
    и открытая очередь (войдёт в строительство). Пусто и там и там —
    завтра начинается чистым листом, и это тоже правда.
    """
    now = now or dt.datetime.now()
    planner = DayPlanner()
    plan = planner.load_plan(now.date())
    open_tasks = []
    if plan:
        open_tasks = [t for t in plan.get("tasks", [])
                      if isinstance(t, dict)
                      and t.get("status") not in ("done", "cancelled")]
    queue = [t for t in load_queue()
             if isinstance(t, dict) and t.get("status") == "pending"]
    tomorrow = (now.date() + dt.timedelta(days=1)).strftime("%d.%m")
    lines = ["ЗАВТРА (%s):" % tomorrow]
    if open_tasks:
        lines.append("переедет с сегодня (не закрыто):")
        for t in open_tasks[:10]:
            lines.append("  " + _render_task(t))
        if len(open_tasks) > 10:
            lines.append("  … и ещё %d" % (len(open_tasks) - 10))
    if queue:
        lines.append("из очереди войдёт в план: %d задач" % len(queue))
    if not open_tasks and not queue:
        lines.append("открытых задач нет — завтра начинается чистым листом")
    lines.append("План построю в 08:00 сама (служба стремления); "
                 "добавить сейчас: «задача: <текст>»")
    return "\n".join(lines)
