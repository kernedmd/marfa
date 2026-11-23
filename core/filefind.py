# -*- coding: utf-8 -*-
"""core/filefind.py — «НАЙДИ ФАЙЛ» (Ф37, 23.11): поиск по имени в доме.

«найди файл отчет» — имена файлов дома (без чтения содержимого):
читай-только, без выхода за HOME_DIR (СТРАЖ не нужен — мы и не ходим
наружу), тяжёлые чуланы (models, venv, llama.cpp, .git) пропускаются
честно — там имена знает их хозяин. Потолок 20 находок, сортировка по
свежести, размер по-человечески.
"""
from __future__ import annotations

import datetime as dt
import os
from pathlib import Path

from core import config

SKIP_DIRS = {".git", "__pycache__", "venv", "models", "llama.cpp",
             "node_modules", ".pytest_cache", "python311", "_trash",
             "patches", "screenshots", "backup"}
MAX_DEPTH = 5
CAP = 20


def _fmt_size(n: int) -> str:
    for unit in ("Б", "КБ", "МБ", "ГБ"):
        if n < 1024 or unit == "ГБ":
            return ("%d %s" % (n, unit)) if unit == "Б" \
                else ("%.1f %s" % (n, unit)).replace(".", ",")
        n /= 1024.0
    return "%d ГБ" % n


def find(pattern: str) -> str:
    """«найди файл X» — имена внутри дома; пусто — честное «нет»."""
    q = str(pattern or "").strip().lower()
    if not q:
        return "что искать? скажи «найди файл отчет»"
    hits: list[tuple[float, str, int]] = []
    root = Path(config.HOME_DIR)
    base_depth = len(root.parts)
    for dirpath, dirnames, filenames in os.walk(root):
        cur = Path(dirpath)
        if len(cur.parts) - base_depth >= MAX_DEPTH:
            dirnames[:] = []
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            if q in fn.lower():
                try:
                    st = (cur / fn).stat()
                    hits.append((st.st_mtime,
                                 str((cur / fn).relative_to(root)),
                                 st.st_size))
                except OSError:
                    continue
                if len(hits) >= CAP * 3:
                    break
    if not hits:
        return ("файлов с «%s» в доме не нашла (чуланы models/venv не "
                "смотрела — там хозяйничает их хозяин)" % pattern)
    hits.sort(reverse=True)
    lines = ["НАЙДЕНО (%d, свежие сверху):" % min(len(hits), CAP)]
    for mtime, rel, size in hits[:CAP]:
        when = dt.datetime.fromtimestamp(mtime).strftime("%d.%m.%Y")
        lines.append("- %s (%s, %s)" % (rel, when, _fmt_size(size)))
    if len(hits) > CAP:
        lines.append("… и ещё %d" % (len(hits) - CAP))
    return "\n".join(lines)
