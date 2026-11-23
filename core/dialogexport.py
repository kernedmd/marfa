# -*- coding: utf-8 -*-
"""core/dialogexport.py — Ф55 «СОХРАНИ РАЗГОВОР» (день-9, 24.11):
экспорт сессии диалога в Markdown — data/exports/.

Разговоры живут в data/dialog/session_*.json (переживают рестарт
панели) — но читать JSON человеку неудобно, а беседа бывает стоит
сохранения. «сохрани наш разговор» берёт СВЕЖАЙШУЮ сессию (по времени
файла) и раскладывает её в Markdown: реплики с ролями, штампы времени
и секунд думания — как это видел чат. «разговоры» — список экспортов.

Экспорт — копия, не переезд: сессия остаётся где жила.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from core import config

ROLE_LABELS = {"user": "Илья", "assistant": "Марфа"}
SHOW_CAP = 500            # потолок реплик в экспорте: марафоны честно режем


def _dialog_dir() -> Path:
    return Path(config.DATA_DIR) / "dialog"


def _exports_dir() -> Path:
    return Path(config.EXPORTS_DIR)


def _latest_session() -> Path | None:
    """Свежайшая сессия по времени файла — «наш» разговор это та,
    что жил последней."""
    try:
        cands = sorted(_dialog_dir().glob("session_*.json"),
                       key=lambda p: p.stat().st_mtime, reverse=True)
        return cands[0] if cands else None
    except OSError:
        return None


def _turns(path: Path) -> list:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        turns = data.get("turns", []) if isinstance(data, dict) else []
        return [t for t in turns
                if isinstance(t, dict) and t.get("role") in ROLE_LABELS]
    except (OSError, ValueError):
        return []


def export() -> str:
    """«сохрани наш разговор» — свежайшая сессия → data/exports/*.md."""
    src = _latest_session()
    if src is None:
        return ("незаконченных разговоров не нашла в data/dialog/ — "
                "сохранять нечего. Мы просто ещё не говорили?")
    turns = _turns(src)
    if not turns:
        return ("сессия %s пуста — реплик нет, экспортировать нечего"
                % src.stem)
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M")
    out_dir = _exports_dir()
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        # уникальность имени: дважды за минуту — суффикс
        target = out_dir / ("dialog_%s.md" % stamp)
        i = 1
        while target.exists():
            i += 1
            target = out_dir / ("dialog_%s_%d.md" % (stamp, i))
        shown = turns[-SHOW_CAP:]
        skipped = len(turns) - len(shown)
        lines = ["# Разговор Ильи и Марфы",
                 "",
                 "*экспорт %s · сессия %s · %d реплик%s*"
                 % (dt.datetime.now().strftime("%d.%m.%Y %H:%M"),
                    src.stem[len("session_"):], len(turns),
                    (" · первые %d подрезаны" % skipped) if skipped else ""),
                 ""]
        for t in shown:
            who = ROLE_LABELS.get(t.get("role"), "?")
            when = str(t.get("ts") or "")
            meta = t.get("meta") if isinstance(t.get("meta"), dict) else {}
            note = ""
            if meta.get("secs") is not None:
                note = " · %.1f с" % float(meta.get("secs") or 0)
            if meta.get("src"):
                note += " · %s" % meta.get("src")
            lines.append("**%s** (%s%s):" % (who, when, note))
            lines.append("")
            lines.append(str(t.get("text") or ""))
            lines.append("")
        target.write_text("\n".join(lines), encoding="utf-8")
        return ("разговор сохранён: %s (%d реплик%s) — лежит в data/exports/"
                "и переживает всё" % (target.name, len(turns),
                                      ", старые подрезаны" if skipped else ""))
    except OSError as e:
        return "не смогла записать экспорт: %s" % e


def list_exports() -> str:
    """«разговоры» — список сохранённых экспортов."""
    try:
        items = sorted(_exports_dir().glob("dialog_*.md"),
                       key=lambda p: p.stat().st_mtime, reverse=True)
    except OSError:
        items = []
    if not items:
        return ("сохранённых разговоров нет — «сохрани наш разговор» "
                "уложит свежайшую сессию в data/exports/")
    lines = ["СОХРАНЁННЫЕ РАЗГОВОРЫ (последние %d):" % min(len(items), 8)]
    for p in items[:8]:
        size = p.stat().st_size
        kb = "%.1f КБ" % (size / 1024) if size >= 1024 else "%d Б" % size
        when = dt.datetime.fromtimestamp(p.stat().st_mtime)
        lines.append("  · %s — %s, %s" % (p.name, kb,
                                          when.strftime("%d.%m %H:%M")))
    if len(items) > 8:
        lines.append("  … и ещё %d" % (len(items) - 8))
    return "\n".join(lines)
