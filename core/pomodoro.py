# -*- coding: utf-8 -*-
"""core/pomodoro.py — ПОМИДОР (Ф30, 23.11): «помидор» — 25 минут дела.

Классический помидор без претензий на методику: «помидор» / «помидор 15»
ставит звонок будильника (Ф10) на N минут (5..90), а счётчик начатых
помидоров за сегодня живёт отдельно — «помидоры» покажет. Начатый —
не обязательно завершённый: дом честно считает начинания, а не
притворяется контролёром усидчивости.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from core import config, reminders

DEFAULT_MIN = 25
MIN_MIN, MAX_MIN = 5, 90


def _file() -> Path:
    return Path(config.POMODORO_FILE)


def _load() -> dict:
    try:
        data = json.loads(_file().read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save(data: dict) -> None:
    _file().parent.mkdir(parents=True, exist_ok=True)
    _file().write_text(
        json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def start(minutes=None, now: dt.datetime = None) -> str:
    """«помидор N» — звонок через N минут + счётчик начатых."""
    now = now or dt.datetime.now()
    try:
        n = int(minutes) if minutes is not None else DEFAULT_MIN
    except (TypeError, ValueError):
        n = DEFAULT_MIN
    if not MIN_MIN <= n <= MAX_MIN:
        return ("помидор бывает от %d до %d минут — скажи «помидор 25»"
                % (MIN_MIN, MAX_MIN))
    plan = {"due": now + dt.timedelta(minutes=n),
            "text": "ПОМИДОР окончен — отдохни 5 минут",
            "when": "через %d минут" % n}
    ring = reminders.add(plan)
    data = _load()
    days = data.setdefault("days", {})
    today = now.strftime("%Y-%m-%d")
    days[today] = int(days.get(today, 0)) + 1
    _save(data)
    return "%s Сегодня помидоров: %d." % (ring, days[today])


def render(now: dt.datetime = None) -> str:
    """«помидоры» — счёт за сегодня."""
    now = now or dt.datetime.now()
    data = _load()
    n = int((data.get("days") or {}).get(now.strftime("%Y-%m-%d"), 0))
    if n == 0:
        return "сегодня помидоров нет; начать: «помидор» (25 минут)"
    return "сегодня помидоров: %d%s" % (
        n, " — хороший урожай" if n >= 4 else "")
