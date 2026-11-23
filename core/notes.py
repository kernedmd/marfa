# -*- coding: utf-8 -*-
"""core/notes.py — ЗАМЕТКИ (Ф11, 23.11): «заметка: купить хлеб».

Мысль «надо не забыть» — не воспоминание (RAG найдёт её не сразу) и не
задача на план (план — про дела дня). Она короткая, их много, и жить
им списком с номерами. «заметка: X» — записать (двоеточие обязательно:
«заметка у меня плохая» — разговор, не приказ — урок жадной ветки р3),
«заметки» — список, «сотри заметку N» — убрать. Потолок 200: заметки
не летопись, старые подрезаются снизу с честной строкой.
"""
from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path

from core import config

CAP = 200


def _file() -> Path:
    return Path(config.NOTES_FILE)


def _load() -> list[dict]:
    try:
        items = json.loads(_file().read_text(encoding="utf-8"))
        return [it for it in items if isinstance(it, dict)] \
            if isinstance(items, list) else []
    except (OSError, ValueError):
        return []


def _save(items: list[dict]) -> None:
    _file().parent.mkdir(parents=True, exist_ok=True)
    _file().write_text(
        json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")


def add(text: str) -> str:
    """«заметка: X» — записать; потолок подрезает старые честно."""
    what = str(text or "").strip()[:300]
    if not what:
        return "что записать? скажи «заметка: купить хлеб»"
    items = _load()
    rec = {"id": max([int(it.get("id", 0)) for it in items] or [0]) + 1,
           "text": what,
           "ts": dt.datetime.now().strftime("%d.%m %H:%M")}
    items.append(rec)
    dropped = 0
    if len(items) > CAP:
        dropped = len(items) - CAP
        items = items[-CAP:]
    _save(items)
    out = "записала (№%d): %s" % (rec["id"], what)
    if dropped:
        out += " — и подрезала %d старых снизу (потолок %d)" % (dropped, CAP)
    return out


def render() -> str:
    """«заметки» — список с номерами."""
    items = _load()
    if not items:
        return "заметок нет; записать: «заметка: купить хлеб»"
    lines = ["ЗАМЕТКИ:"]
    for it in items[-12:]:
        lines.append("№%d %s" % (int(it.get("id", 0)),
                                  str(it.get("text", ""))[:120]))
    if len(items) > 12:
        lines.append("… и ещё %d" % (len(items) - 12))
    return "\n".join(lines)


def erase(n: int) -> str:
    """«сотри заметку N» — убрать одну."""
    items = _load()
    for i, it in enumerate(items):
        if int(it.get("id", -1)) == int(n):
            items.pop(i)
            _save(items)
            return "стёрла заметку №%d (%s)" % (n, str(it.get("text", ""))[:80])
    return "заметки №%s нет — «заметки» покажет список" % n


# ---------- разбор команд (границы — закон р3) ----------

_RX_ADD = re.compile(r"^заметка\s*[:;]\s*(.+)$", re.IGNORECASE | re.DOTALL)
_RX_ERASE = re.compile(r"^(?:сотри|удали)\s+заметку\s*[№#]?\s*(\d+)$",
                       re.IGNORECASE)


def parse(text: str):
    """Разобрать команду заметок. ('add', текст) / ('erase', N) / None.

    «заметка» без двоеточия — НЕ команда (разговор живёт в мозгу);
    payload режется от исходного текста — регистр Создателя сохранён.
    """
    t = str(text or "").strip()
    m = _RX_ADD.match(t)
    if m:
        return ("add", m.group(1).strip())
    m = _RX_ERASE.match(t)
    if m:
        return ("erase", int(m.group(1)))
    return None
