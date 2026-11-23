# -*- coding: utf-8 -*-
"""core/reminders.py — БУДИЛЬНИК ДОМА (Ф10, 23.11): «напомни через 10 минут».

Урок живого дома: «напомни» улетало в мозг и растворялось — у мозга
нет часов действия, у дома есть. Напоминание живёт в
data\\reminders.json и ДОЖИДАЕТСЯ Создателя в чате: любая следующая
реплика выносит его первой строкой (у панели нет канала «постучать
первой» — честная граница, а не притворство). «напоминания» — список,
«отменить напоминание №» — отмена.

Время: «через N минут/часов/секунд» или «в ЧЧ:ММ» (сегодня, а если
прошло — завтра). Часы Создателя, не сервера-песочницы: now приходит
снаружи, тесты подменяют.
"""
from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path
from typing import Optional

from core import config


def reminders_file() -> Path:
    return Path(config.DATA_DIR) / "reminders.json"


def _load() -> list[dict]:
    try:
        items = json.loads(reminders_file().read_text(encoding="utf-8"))
        return [it for it in items if isinstance(it, dict)] \
            if isinstance(items, list) else []
    except (OSError, ValueError):
        return []


def _save(items: list[dict]) -> None:
    reminders_file().parent.mkdir(parents=True, exist_ok=True)
    reminders_file().write_text(
        json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")


def _next_id(items: list[dict]) -> int:
    return max([int(it.get("id", 0)) for it in items] or [0]) + 1


# ---------- разбор времени ----------

_RX_IN = re.compile(
    r"^напомни\s+через\s+(\d{1,4})\s*(секунд\w*|минут\w*|час\w*|день|дня|дней|дню|дн\w*)\s*"
    r"[:;,—-]?\s*(.*)$", re.IGNORECASE | re.DOTALL)
_RX_AT = re.compile(
    r"^напомни\s+(?:в|во)\s+(\d{1,2})(?::(\d{2}))?\s*[:;,—-]?\s*(.*)$",
    re.IGNORECASE | re.DOTALL)


def parse(text: str, now: Optional[dt.datetime] = None) -> Optional[dict]:
    """«напомни через N минут: X» / «напомни в 14:30 X» → план или None.

    Возвращает {"due": datetime, "text": str, "when": человеческое}.
    Пустой текст напоминания — тоже план: «напомни через 5 минут» без
    слов — просто «привет, время вышло» (как кухонный таймер).
    """
    now = now or dt.datetime.now()
    t = str(text or "").strip()

    m = _RX_IN.match(t)
    if m:
        n = int(m.group(1))
        unit = m.group(2).lower()
        if unit.startswith("секунд"):
            delta = dt.timedelta(seconds=n)
        elif unit.startswith("минут"):
            delta = dt.timedelta(minutes=n)
        elif unit.startswith("час"):
            delta = dt.timedelta(hours=n)
        else:                                   # дни
            delta = dt.timedelta(days=n)
        due = now + delta
        what = m.group(3).strip(" :;,")
        return {"due": due, "text": what,
                "when": "через %d %s" % (n, unit)}

    m = _RX_AT.match(t)
    if m:
        hh = int(m.group(1))
        mm = int(m.group(2) or 0)
        if not (0 <= hh <= 23 and 0 <= mm <= 59):
            return None
        due = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
        if due <= now:
            due += dt.timedelta(days=1)         # «в 8:00» вечером — завтра в 8
        what = m.group(3).strip(" :;,")
        return {"due": due, "text": what,
                "when": "в " + due.strftime("%H:%M")}
    return None


# ---------- операции ----------

def add(plan: dict) -> str:
    """Записать напоминание по плану из parse()."""
    items = _load()
    rec = {"id": _next_id(items),
           "text": str(plan.get("text") or "").strip()[:300],
           "due": plan["due"].isoformat(timespec="seconds"),
           "when": str(plan.get("when") or ""),
           "fired": False}
    items.append(rec)
    _save(items)
    what = rec["text"] or "время вышло"
    return ("Напомню (%s): «%s». Скажешь что угодно в чате — вынесу "
            "первой строкой; список — «напоминания»." % (rec["when"], what))


def due(now: Optional[dt.datetime] = None, mark: bool = True) -> list[dict]:
    """Назвонившие напоминания (due <= now, ещё не отданные).

    mark=True — помечает отданными сразу (одно напоминание звонит
    один раз; двойной звонок хуже молчания)."""
    now = now or dt.datetime.now()
    items = _load()
    hit: list[dict] = []
    for it in items:
        if it.get("fired"):
            continue
        try:
            due_at = dt.datetime.fromisoformat(str(it.get("due", "")))
        except ValueError:
            continue
        if due_at <= now:
            hit.append(it)
            if mark:
                it["fired"] = True
    if mark and hit:
        _save(items)
    return hit


def due_note(now: Optional[dt.datetime] = None) -> str:
    """Строка для чата: «НАПОМИНАНИЕ: …» — или пусто."""
    hit = due(now, mark=True)
    if not hit:
        return ""
    lines = []
    for it in hit[:3]:
        what = str(it.get("text") or "").strip() or "время вышло"
        lines.append("НАПОМИНАНИЕ (%s): %s" % (it.get("when", "по будильнику"),
                                               what))
    if len(hit) > 3:
        lines.append("… и ещё %d напоминаний — «напоминания» покажет" % (len(hit) - 3))
    return "\n".join(lines)


def active(now: Optional[dt.datetime] = None) -> list[dict]:
    """Живые (не прозвоневшие) напоминания — для «напоминания»."""
    now = now or dt.datetime.now()
    out = []
    for it in _load():
        if it.get("fired"):
            continue
        try:
            due_at = dt.datetime.fromisoformat(str(it.get("due", "")))
        except ValueError:
            continue
        left = (due_at - now).total_seconds()
        out.append(dict(it, _left=left))
    out.sort(key=lambda r: r["_left"])
    return out


def render_active(now: Optional[dt.datetime] = None) -> str:
    """«напоминания»: список живых с остатком времени."""
    items = active(now)
    if not items:
        return ("напоминаний нет; завести: «напомни через 10 минут: перевернуть "
                "котлеты» или «напомни в 20:00 выключить чайник»")
    lines = []
    for it in items:
        what = str(it.get("text") or "").strip() or "просто таймер"
        left = it["_left"]
        if left <= 0:
            lines.append("№%d %s — уже пора (прозвонит при следующей реплике)"
                         % (it.get("id", 0), what))
        elif left < 3600:
            lines.append("№%d %s — через %d мин"
                         % (it.get("id", 0), what, int(round(left / 60)) or 1))
        else:
            lines.append("№%d %s — через %d ч %d мин"
                         % (it.get("id", 0), what, int(left // 3600),
                            int((left % 3600) / 60)))
    return "НАПОМИНАНИЯ:\n" + "\n".join(lines)


def cancel(n: int) -> str:
    """«отменить напоминание №N»."""
    items = _load()
    for it in items:
        if int(it.get("id", -1)) == int(n) and not it.get("fired"):
            it["fired"] = True
            _save(items)
            return "отменила напоминание №%d (%s)" % (
                n, str(it.get("text") or "таймер")[:80])
    return "напоминания №%s среди живых нет — «напоминания» покажет список" % n
