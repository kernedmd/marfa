# -*- coding: utf-8 -*-
"""core/shores.py — Ф48 «БЕРЕГА» (день-9, 24.11): дисциплина вторых
берегов — в чате, без консоли.

Этап 0 мастер-ТЗ назвал вторые берега (GitHub + бандлы) спасением дома,
но у дисциплины нет часов: «незакоммиченного 12 файлов, последний коммит
двое суток назад» — так теряют дома. «берега» спрашивает у git прямо:
что в дереве не сохранено, когда последний коммит, — и говорит честно:
дом чист (тишина и вторые берега при нём) или дом течёт (кнопка 80 —
синк, петля v1.8).

git — по месту жительства дома (config.HOME_DIR); git нет/сломался —
честный отказ, панель не притворяется контролером версий.
"""
from __future__ import annotations

import datetime as dt
import subprocess
from pathlib import Path

from core import config

GIT_TIMEOUT_SEC = 15
UNCOMMITTED_CAP = 5        # сколько путей назвать поимённо


def _git(args: list[str]) -> tuple[int, str]:
    """Спросить git о доме. (код, вывод) — exceptions наружу не идут:
    git сам себе голова, дом — нет."""
    try:
        r = subprocess.run(
            ["git", "-C", str(Path(config.HOME_DIR))] + args,
            capture_output=True, text=True, timeout=GIT_TIMEOUT_SEC)
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except (OSError, subprocess.TimeoutExpired):
        return 1, ""


def _age_human(hours: float) -> str:
    if hours < 1:
        return "только что"
    if hours < 48:
        return "%d ч назад" % round(hours)
    return "%d дн назад" % round(hours / 24)


def render() -> str:
    """«берега» — сохранён ли дом: незакоммиченное + последний коммит."""
    code, out = _git(["status", "--porcelain"])
    if code != 0 and not out.strip():
        return ("git в доме не отвечает — берега не проверить из чата. "
                "Кнопка 84 (доктор) смотрит глубже")
    dirty = [l.strip() for l in out.splitlines() if l.strip()]
    code2, last = _git(["log", "-1", "--format=%cd|%h",
                        "--date=format:%Y-%m-%d %H:%M"])
    lines = ["БЕРЕГА ДОМА:"]
    if not dirty:
        lines.append("  · рабочее дерево чистое — всё сохранено")
    else:
        shown = dirty[:UNCOMMITTED_CAP]
        lines.append("  · НЕ СОХРАНЕНО: %d файлов" % len(dirty))
        for s in shown:
            lines.append("      %s" % s[:90])
        if len(dirty) > UNCOMMITTED_CAP:
            lines.append("      … и ещё %d" % (len(dirty) - UNCOMMITTED_CAP))
    if code2 == 0 and "|" in last:
        when, _, h = last.strip().partition("|")
        try:
            ts = dt.datetime.strptime(when.strip(), "%Y-%m-%d %H:%M")
            age = (dt.datetime.now() - ts).total_seconds() / 3600
            lines.append("  · последний коммит %s (%s, %s)"
                         % (h.strip() or "?", _age_human(age), when.strip()))
        except ValueError:
            lines.append("  · последний коммит: %s" % last.strip()[:60])
    else:
        lines.append("  · историю коммитов не прочёл — git молчит")
    if dirty:
        lines.append("дом течёт — кнопка 80 (синк) сохранит и увезёт на "
                     "берега: GitHub + бандл архитектору")
    else:
        lines.append("тишина в дереве — так и живут вторые берега")
    return "\n".join(lines)
