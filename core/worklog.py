# -*- coding: utf-8 -*-
"""core/worklog.py — ТРЕКЕР ВРЕМЕНИ (Ф13, 23.11): «начал: отчёт» … «закончил».

«Чем я занимался весь день?» — вопрос, на который память не отвечает:
у дел нет времени в RAG. «начал: X» открывает дело (двоеточие
обязательно — «начал думать о вечном» — разговор), «закончил» /
«завершил» закрывает активное, «чем занимался» — сегодняшний журнал с
минутами. Одно дело одновременно: новое «начал:» закрывает прежнее с
честной строкой (человек не делает два дела сразу — и дом не будет).
"""
from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path

from core import config

CAP = 500


def _file() -> Path:
    return Path(config.WORKLOG_FILE)


def _load() -> dict:
    try:
        data = json.loads(_file().read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("sessions"), list):
            return data
    except (OSError, ValueError):
        pass
    return {"sessions": []}


def _save(data: dict) -> None:
    _file().parent.mkdir(parents=True, exist_ok=True)
    _file().write_text(
        json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def _fmt_min(minutes: int) -> str:
    if minutes < 60:
        return "%d мин" % max(1, minutes)
    return "%d ч %d мин" % (minutes // 60, minutes % 60)


def _close(data: dict, now: dt.datetime) -> str:
    """Закрыть активное дело; вернуть человеческую строку или ''."""
    act = data.get("active")
    if not isinstance(act, dict):
        return ""
    try:
        start = dt.datetime.fromisoformat(str(act.get("start", "")))
    except ValueError:
        data["active"] = None
        return ""
    minutes = int((now - start).total_seconds() // 60)
    data["active"] = None
    data["sessions"].append({"what": str(act.get("what", ""))[:200],
                             "start": act.get("start"),
                             "end": now.isoformat(timespec="seconds")})
    if len(data["sessions"]) > CAP:
        data["sessions"] = data["sessions"][-CAP:]
    return "%s — %s" % (str(act.get("what", "дело"))[:80], _fmt_min(minutes))


def start(what: str, now: dt.datetime = None) -> str:
    """«начал: X» — открыть дело; прежнее закрывается честно."""
    now = now or dt.datetime.now()
    name = str(what or "").strip()[:200]
    if not name:
        return "что начал? скажи «начал: отчёт»"
    data = _load()
    closed = _close(data, now)
    data["active"] = {"what": name,
                      "start": now.isoformat(timespec="seconds")}
    _save(data)
    out = "засекла: %s" % name
    if closed:
        out += " (прошлое закрыла: %s)" % closed
    return out


def stop(now: dt.datetime = None) -> str:
    """«закончил» — закрыть активное дело."""
    now = now or dt.datetime.now()
    data = _load()
    closed = _close(data, now)
    if not closed:
        return "нечего закрывать — начать: «начал: отчёт»"
    _save(data)
    return "закрыла: " + closed


def render(now: dt.datetime = None) -> str:
    """«чем занимался» — сегодняшний журнал."""
    now = now or dt.datetime.now()
    data = _load()
    today = now.strftime("%Y-%m-%d")
    rows = []
    for s in data["sessions"]:
        try:
            start = dt.datetime.fromisoformat(str(s.get("start", "")))
        except ValueError:
            continue
        if start.strftime("%Y-%m-%d") != today:
            continue
        try:
            end = dt.datetime.fromisoformat(str(s.get("end", "")))
        except ValueError:
            continue
        minutes = int((end - start).total_seconds() // 60)
        rows.append("%s — %s" % (str(s.get("what", "дело"))[:80],
                                 _fmt_min(minutes)))
    lines = []
    act = data.get("active")
    if isinstance(act, dict):
        try:
            start = dt.datetime.fromisoformat(str(act.get("start", "")))
            minutes = int((now - start).total_seconds() // 60)
            lines.append("СЕЙЧАС: %s (уже %s)"
                         % (str(act.get("what", ""))[:80], _fmt_min(minutes)))
        except ValueError:
            pass
    if rows:
        lines.append("СЕГОДНЯ:")
        lines.extend("- " + r for r in rows)
    if not lines:
        return ("дел сегодня не записано; начать: «начал: отчёт», "
                "закончить — «закончил»")
    return "ЧЕМ ЗАНИМАЛСЯ:\n" + "\n".join(lines)
