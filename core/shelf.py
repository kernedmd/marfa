# -*- coding: utf-8 -*-
"""core/shelf.py — «ПОЛКА» (Ф39, 23.11): что дом прочитал.

Библиотекарь читает дом раз в час молча — а Создатель не видит, ЧТО
уже легло в память. «полка» — честный список прочитанных файлов с
числом кусков; пустая полка — честная подсказка «почитай». Источник —
состояние библиотекаря (data/librarian_state.json), не выдумка.
"""
from __future__ import annotations

import json
from pathlib import Path

from core import config

TOP = 12


def _chunks(meta) -> int:
    """Куски из меты — с бронёй: мусор в JSON не роняет полку."""
    try:
        return int(meta.get("chunks", 0))
    except (TypeError, ValueError, AttributeError):
        return 0


def render() -> str:
    """«полка» — прочитанное библиотекарем."""
    try:
        data = json.loads(
            Path(config.LIBRARIAN_STATE_FILE).read_text(encoding="utf-8"))
        files = data.get("files") if isinstance(data, dict) else None
        if not isinstance(files, dict):
            files = {}
    except (OSError, ValueError):
        files = {}
    if not files:
        return ("полка пуста — библиотекарь читает раз в час, когда дом "
                "бодр; принудительно: «почитай»")
    rows = sorted(files.items(), key=lambda kv: -_chunks(kv[1]))
    total_chunks = sum(_chunks(v) for _, v in rows)
    lines = ["ПОЛКА (прочитано %d файлов, %d кусков в памяти):"
             % (len(rows), total_chunks)]
    for name, meta in rows[:TOP]:
        lines.append("- %s (%d кусков)" % (name, _chunks(meta)))
    if len(rows) > TOP:
        lines.append("… и ещё %d" % (len(rows) - TOP))
    return "\n".join(lines)
