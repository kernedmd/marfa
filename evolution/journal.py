# -*- coding: utf-8 -*-
"""evolution/journal.py — ЖУРНАЛ УРОКОВ (Эволюционер v0, Круг Д).

Каждый сбой дома — событие с датой и сортом: страж-отказ,
неизвестный инструмент, мозг недоступен, расписание-сбой, прочее.
Файл: data/evolution/journal.jsonl (правило 6.6: логи — истина).

Дальше по карте: дневник ошибок -> правила генома (№21-28 бэклога,
после вердикта батареи). Сейчас — только честная фактура:
- log_lesson(): записать событие;
- digest(): сколько каких уроков за N дней (для дневника и панели);
- recent(): последние события (для «чему учишься?»).
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Optional

from core import config

KINDS = ("страж-отказ", "неизвестный-инструмент", "мозг-недоступен",
         "расписание-сбой", "ошибка-глаз", "ошибка-ушей", "прочее")


def journal_path() -> Path:
    return config.EVOLUTION_DIR / "journal.jsonl"


def log_lesson(kind: str, text: str, context: str = "") -> bool:
    """Записать урок. Неизвестный сорт — «прочее». Файл не рвёт дом."""
    if kind not in KINDS:
        kind = "прочее"
    rec = {"ts": dt.datetime.now().isoformat(timespec="seconds"),
           "kind": kind, "text": str(text)[:500]}
    if context:
        rec["context"] = str(context)[:200]
    try:
        p = journal_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        return True
    except OSError:
        return False


def _read_all() -> list[dict]:
    try:
        lines = journal_path().read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out = []
    for line in lines:
        try:
            rec = json.loads(line)
            if isinstance(rec, dict):
                out.append(rec)
        except ValueError:
            continue
    return out


def recent(limit: int = 20) -> list[dict]:
    return _read_all()[-limit:]


def digest(days: int = 7, now: Optional[dt.datetime] = None) -> dict:
    """Сколько каких уроков за последние N дней."""
    now = now or dt.datetime.now()
    horizon = (now - dt.timedelta(days=days)).isoformat(timespec="seconds")
    counts: dict[str, int] = {}
    for rec in _read_all():
        if str(rec.get("ts", "")) >= horizon:
            counts[rec.get("kind", "прочее")] = \
                counts.get(rec.get("kind", "прочее"), 0) + 1
    return counts
