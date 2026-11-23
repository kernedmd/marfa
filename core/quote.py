# -*- coding: utf-8 -*-
"""core/quote.py — ЦИТАТА ИЗ ПРОЧИТАННОГО (Ф9, 23.11).

Библиотекарь читает полку дома и складывает куски в память с тегами
«библиотека». «цитата» достаёт случайный кусок из прочитанного — не
из интернета и не из выдумки: дом цитирует только то, что сам читал.
Источник называется честно (файл, откуда кусок), длина — по-человечески.
"""
from __future__ import annotations

import secrets
from typing import Optional

from core import config

_TAG = "библиотека"


def _library_records(memory) -> list[dict]:
    """Записи с тегом «библиотека» — что дом реально прочитал."""
    if memory is None:
        return []
    try:
        recs = memory.recent(since_ts=0.0, limit=500)
    except Exception:
        return []
    out = []
    for r in recs:
        tags = r.get("tags")
        if isinstance(tags, list) and _TAG in [str(t) for t in tags]:
            out.append(r)
        elif isinstance(tags, str) and _TAG in tags:
            out.append(r)
    return out


def _source_of(rec: dict) -> str:
    """Откуда кусок: второй тег — имя файла полки."""
    tags = rec.get("tags")
    if isinstance(tags, list):
        others = [str(t) for t in tags if str(t) != _TAG]
        if others:
            return others[0]
    return "полка дома"


def quote(memory=None) -> str:
    """«цитата»: случайный кусок из прочитанных книг.

    Полка пуста — честная подсказка («почитай» наполняет), не выдумка
    «как говорил Конфуций». Выбор — secrets, не math.random.
    """
    recs = _library_records(memory)
    if not recs:
        return ("из прочитанного пока нечего цитировать — скажи «почитай», "
                "библиотекарь наполнит полку, и цитаты появятся")
    rec = recs[secrets.randbelow(len(recs))]
    text = str(rec.get("text", "")).strip()
    if len(text) > 600:
        text = text[:600].rsplit(" ", 1)[0] + "…"
    return "Из прочитанного (%s):\n\n%s" % (_source_of(rec), text)
