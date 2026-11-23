# -*- coding: utf-8 -*-
"""core/weekroll.py — «ИТОГ НЕДЕЛИ» (Ф34, 23.11): семь дней одним ответом.

Недельная сводка из первых рук: уроки дома (журнал архитектора),
разговор (реплики за 7 дней — по штампам «dd.mm», год выводим
перечислением последних семи дней), похвала, помидоры, расходы.
Механика без LLM: итог недели — факты, а выводы Создатель сделает сам
или спросит у мозга, который увидит эти цифры в разговоре.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from core import config


def _days_set(now: dt.date, k: int = 7) -> set:
    return {(now - dt.timedelta(days=i)).strftime("%d.%m")
            for i in range(k)}


def _week_days_iso(now: dt.date, k: int = 7) -> set:
    return {(now - dt.timedelta(days=i)).strftime("%Y-%m-%d")
            for i in range(k)}


def _turns_week(now: dt.date) -> tuple[int, int]:
    """Реплики за 7 дней по штампам «dd.mm» (год — перечислением дней)."""
    from core.dialog import DialogStore
    marks = _days_set(now)
    store = DialogStore()
    user_n = total = 0
    for sid in store.sessions():
        for t in store.turns(sid):
            ts = str(t.get("ts") or "")
            if not ts:
                continue
            head = ts.split(" ")[0]
            if head in marks:
                total += 1
                if t.get("role") == "user":
                    user_n += 1
    return user_n, total


def _praise_week(now: dt.date) -> int:
    try:
        items = json.loads(
            (Path(config.DATA_DIR) / "praise.json").read_text(encoding="utf-8"))
        days = _week_days_iso(now)
        return sum(1 for it in items if isinstance(it, dict)
                   and str(it.get("ts", ""))[:10] in days)
    except (OSError, ValueError):
        return 0


def _sum_week(days_iso: set, loader) -> tuple[int, float]:
    try:
        items = loader()
    except Exception:
        return 0, 0.0
    n, total = 0, 0.0
    for it in items:
        if isinstance(it, dict) and str(it.get("day", "")) in days_iso:
            n += 1
            try:
                total += float(it.get("amount", 0))
            except (TypeError, ValueError):
                pass
    return n, total


def _pomodoro_week(days_iso: set) -> int:
    try:
        data = json.loads(Path(config.POMODORO_FILE).read_text(encoding="utf-8"))
        days = data.get("days") or {}
        return sum(int(v) for k, v in days.items() if k in days_iso)
    except (OSError, ValueError, AttributeError):
        return 0


def render(now: dt.date = None) -> str:
    """«итог недели» — семь дней цифрами."""
    now = now or dt.date.today()
    days_iso = _week_days_iso(now)
    lines = ["ИТОГ НЕДЕЛИ (%s — %s):"
             % ((now - dt.timedelta(days=6)).strftime("%d.%m"),
                now.strftime("%d.%m"))]

    # уроки дома
    try:
        from evolution.journal import digest
        d = digest(7)
        if d:
            top = sorted(d.items(), key=lambda kv: -kv[1])[:3]
            lines.append("уроки дома: %d (%s)"
                         % (sum(d.values()),
                            ", ".join("%s ×%d" % kv for kv in top)))
    except Exception:
        pass

    # разговор
    try:
        user_n, total = _turns_week(now)
        if total:
            lines.append("разговор: %d реплик (твоих %d)" % (total, user_n))
    except Exception:
        pass

    # похвала
    praise = _praise_week(now)
    if praise:
        lines.append("ты хвалил меня: %d раз" % praise)

    # расходы и помидоры — каждый в своей броне
    try:
        from core import expenses
        n, total = _sum_week(days_iso, expenses._load)
        if n:
            lines.append("расходы: %d записей на %s руб"
                         % (n, ("%.2f" % total).rstrip("0").rstrip(".")
                            .replace(".", ",")))
    except Exception:
        pass
    pom = _pomodoro_week(days_iso)
    if pom:
        lines.append("помидоров начато: %d" % pom)

    if len(lines) == 1:
        return ("за неделю фактов не нашлось — мы только начинаем; "
                "заполняй день organами («расход:», «отметь:», «помидор»), "
                "и через неделю здесь будет итог")
    return "\n".join(lines)
