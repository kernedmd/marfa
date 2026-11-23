# -*- coding: utf-8 -*-
"""core/diaryday.py — Ф53 «ДНЕВНИК ЗА ДАТУ» (день-9, 24.11).

Дневник пишется каждый вечер (21:00, №8) — но читать его можно было
только «как прошёл день» (сегодня). «что было 20 ноября» и «дневник
за вчера» открывают ГЛУБИНУ архива: дом помнит не только сегодняшний
вечер. Даты — как их говорит Создатель: «вчера», «позавчера», «20
ноября», «20.11», «20.11.2026», ISO. Дневника нет — честно: какие
вечера вообще записаны (ближайшие три, свежие сверху).
"""
from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

from core import config

SHOW_LINES = 40          # сколько строк вечера показывать

_MONTHS = {
    "января": 1, "февраля": 2, "марта": 3, "апреля": 4, "мая": 5,
    "июня": 6, "июля": 7, "августа": 8, "сентября": 9, "октября": 10,
    "ноября": 11, "декабря": 12,
}


def _diary_dir() -> Path:
    return Path(config.DATA_DIR) / "diary"


def _known_days() -> list:
    try:
        return sorted((p.stem for p in _diary_dir().glob("*.md")),
                      reverse=True)
    except OSError:
        return []


def parse_date(payload: str, today: dt.date = None) -> dt.date | None:
    """Разобрать дату из разговора. None — не разобралась (не выдумываем).

    Форматы: «вчера», «позавчера», «20 ноября» (год — текущий),
    «20.11», «20.11.2026», «2026-11-20»."""
    t = str(payload or "").strip().lower().rstrip("?.!")
    today = today or dt.date.today()
    if t in ("вчера", ):
        return today - dt.timedelta(days=1)
    if t in ("позавчера", ):
        return today - dt.timedelta(days=2)
    if t in ("сегодня", "этот день"):
        return today
    m = re.match(r"^(\d{1,2})[\s]+([а-яё]+)$", t)
    if m and m.group(2) in _MONTHS:
        try:
            return dt.date(today.year, _MONTHS[m.group(2)], int(m.group(1)))
        except ValueError:
            return None            # 31 февраля — не дата, честный отказ
    m = re.match(r"^(\d{1,2})\.(\d{1,2})(?:\.(\d{4}))?$", t)
    if m:
        year = int(m.group(3)) if m.group(3) else today.year
        try:
            return dt.date(year, int(m.group(2)), int(m.group(1)))
        except ValueError:
            return None
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", t)
    if m:
        try:
            return dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    return None


def _human(day: dt.date) -> str:
    return day.strftime("%d.%m.%Y")


def render(day: dt.date) -> str:
    """«что было <дата>» — вечер из дневника."""
    path = _diary_dir() / (day.isoformat() + ".md")
    if not path.is_file():
        known = _known_days()
        hint = ""
        if known:
            hint = "; записаны вечера: %s" % ", ".join(known[:3])
        return ("дневника за %s нет — этот вечер не записывался%s. "
                "Сегодняшний вечер — «как прошёл день»" % (_human(day), hint))
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as e:
        return "не смогла прочитать дневник за %s: %s" % (_human(day), e)
    shown = [l for l in lines if l.strip()][:SHOW_LINES]
    out = ["ВЕЧЕР %s:" % _human(day)]
    out.extend("  " + l for l in shown)
    if len([l for l in lines if l.strip()]) > SHOW_LINES:
        out.append("  … и ещё %d строк — файл data/diary/%s.md"
                   % (len(lines) - SHOW_LINES, day.isoformat()))
    return "\n".join(out)
