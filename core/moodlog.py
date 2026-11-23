# -*- coding: utf-8 -*-
"""core/moodlog.py — НАСТРОЕНИЕ СОЗДАТЕЛЯ (Ф35, 23.11): «настроение: отличное».

Настроение дома — барометр из фактов; а настроение Создателя — его
собственные слова, и записывать их — не оценивать. «настроение: X» —
записать (дважды в день можно: утро и вечер — разные), «моё
настроение» — последнее и счёт за сегодня. Анализ тональности без
мозга — выдумка: дом записывает и показывает, а понимает — разговором.
"""
from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path

from core import config

CAP = 500


def _file() -> Path:
    return Path(config.MOODLOG_FILE)


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


def add(text: str, now: dt.datetime = None) -> str:
    """«настроение: отличное» — записать слово Создателя как есть."""
    now = now or dt.datetime.now()
    what = str(text or "").strip()[:120]
    if not what:
        return "какое настроение? скажи «настроение: отличное»"
    items = _load()
    items.append({"text": what,
                  "day": now.strftime("%Y-%m-%d"),
                  "ts": now.strftime("%d.%m %H:%M")})
    if len(items) > CAP:
        items = items[-CAP:]
    _save(items)
    return "записала твоё настроение: «%s»" % what


def render(now: dt.datetime = None) -> str:
    """«моё настроение» — последнее и сколько записано сегодня."""
    now = now or dt.datetime.now()
    items = _load()
    if not items:
        return "настроение ещё не записывал; скажи «настроение: отличное»"
    last = items[-1]
    today = [it for it in items if it.get("day") == now.strftime("%Y-%m-%d")]
    tail = ""
    if len(today) > 1:
        tail = "; за сегодня записано %d" % len(today)
    return "последнее (%s): «%s»%s" % (last.get("ts", ""),
                                       last.get("text", ""), tail)


def parse(text: str):
    """('add', текст) для «настроение: X» / None."""
    m = re.match(r"^настроение\s*[:;]\s*(.+)$", str(text or "").strip(),
                 re.IGNORECASE | re.DOTALL)
    if m:
        return ("add", m.group(1).strip())
    return None
