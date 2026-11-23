# -*- coding: utf-8 -*-
"""core/weight.py — «ВЕС ДОМА» (Ф38, 23.11): сколько весит что.

«вес дома» — размеры папок дома по-человечески (модели честно
доминируют — это их право); «вес data» — конкретная полка. Осмотр
только читает (os.walk + stat), недоступное пропускает молча.
"""
from __future__ import annotations

import os
from pathlib import Path

from core import config

TOP = 8


def _dir_size(p: Path) -> tuple[int, int]:
    """(байты, файлы) рекурсивно; ошибки — мимо."""
    total, files = 0, 0
    for dirpath, _dirnames, filenames in os.walk(p):
        for fn in filenames:
            try:
                total += os.path.getsize(os.path.join(dirpath, fn))
                files += 1
            except OSError:
                continue
    return total, files


def _fmt(n: float) -> str:
    for unit in ("Б", "КБ", "МБ", "ГБ", "ТБ"):
        if n < 1024 or unit == "ТБ":
            s = ("%d" % n) if unit == "Б" else ("%.1f" % n)
            return s.replace(".", ",") + " " + unit
        n /= 1024.0
    return "?"


def render(target: str = None) -> str:
    """«вес дома» / «вес data» — топ папок по тяжести."""
    root = Path(config.HOME_DIR)
    if target:
        raw = str(target).strip()
        if raw in ("дом", "дома"):
            target = None               # весь дом
        elif not raw or "/" in raw or "\\" in raw or ".." in raw:
            # разделители и «..» — не части имени: отказ ДО чистки,
            # дом наружу не выходит и не притворяется, что понял
            return "какую папку? скажи «вес data» или «вес дома»"
        else:
            target = raw
    if target:
        p = root / target
        if not p.is_dir():
            return "папки «%s» в доме нет" % target
        size, files = _dir_size(p)
        return "«%s» весит %s (%d файлов)" % (target, _fmt(size), files)
    rows = []
    for child in sorted(root.iterdir()):
        if child.is_dir():
            size, files = _dir_size(child)
            if size:
                rows.append((size, files, child.name))
    if not rows:
        return "дом пуст — нечего взвешивать"
    rows.sort(reverse=True)
    total = sum(r[0] for r in rows)
    lines = ["ВЕС ДОМА: %s всего" % _fmt(total), "тяжёлые этажи:"]
    for size, files, name in rows[:TOP]:
        lines.append("- %s — %s (%d файлов)" % (name, _fmt(size), files))
    lines.append("модели и venv — самые тяжёлые: это нормально, "
                 "они — тело дома")
    return "\n".join(lines)
