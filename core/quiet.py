# -*- coding: utf-8 -*-
"""core/quiet.py — №27 «ТИХИЙ ЧАС»: лог панели режется до ошибок.

Чат опрашивает /api/progress каждые 1,5 с — консоль панели печатает
доступ-строку на КАЖДЫЙ запрос («GET /api/progress 200»), и живой
дом шумит сотнями строк в минуту. Резолюция Создателя «тишина»:
access-лог werkzeug молчит, ошибки остаются (молчаливая поломка —
хуже шумной). «Не тишина» возвращает.

Резолюция живёт в data/quiet.json и переживает рестарт панели:
web/app применяет её на старте (apply_saved). Файл битый/нет —
дом ГОВОРИТ (тишина без воли Создателя — не тишина, а сбой).
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path

from core import config

PANEL_LOGGER = "werkzeug"      # access-лог Flask: строка на каждый запрос


def _logger() -> logging.Logger:
    return logging.getLogger(PANEL_LOGGER)


def set_quiet(on: bool) -> str:
    """Включить/выключить тихий час (воля Создателя, одной фразой).

    Уровень логгера — сразу (эффект в той же консоли), резолюция —
    в data/quiet.json (переживает рестарт). Файл не записался —
    тишина всё равно действует до рестарта: воля важнее бухгалтерии.
    """
    _logger().setLevel(logging.ERROR if on else logging.INFO)
    try:
        p = Path(config.QUIET_FILE)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(
            {"quiet": bool(on), "ts": time.strftime("%Y-%m-%d %H:%M:%S")},
            ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass
    if on:
        return ("Тихий час: лог панели режу до ошибок — доступ-строки "
                "«GET /api/progress 200» молчат, ошибки остаются слышны. "
                "Вернуть — «не тишина»")
    return ("Говорю снова: доступ-лог панели на месте (каждый запрос — "
            "строка). Утихомирить — «тишина»")


def is_quiet() -> bool:
    """Тихий час по резолюции из data/quiet.json (без чтения логгера:
    уровень — следствие воли, а не наоборот)."""
    try:
        rec = json.loads(Path(config.QUIET_FILE).read_text(encoding="utf-8"))
        return bool(rec.get("quiet")) if isinstance(rec, dict) else False
    except (OSError, ValueError):
        return False


def apply_saved() -> bool:
    """Применить сохранённую резолюцию (старт панели, рестарт службы).
    Возвращает фактическое состояние. Битый файл — дом говорит:
    тишина без воли Создателя — не тишина, а сбой."""
    on = is_quiet()
    _logger().setLevel(logging.ERROR if on else logging.INFO)
    return on
