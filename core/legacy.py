# -*- coding: utf-8 -*-
"""core/legacy.py — «ЧТО ПОСТРОИЛИ» (Ф40, 23.11): летопись из книги дома.

CHANGELOG.md — книга истории (логбук №24); «что построили» читает её
механически: сколько коммитов и дней стоит дом, что построено последним.
Живой git не нужен — читаем файл; недоступен или не разобран — честно
говорим, кто соберёт («логбук»). Летопись не хвастается: цифры и
последние строки книги.

Путь книги — аргумент (тесты пишут в tmp_path); по умолчанию — книга
рядом с кодом: корень резолвится от ЭТОГО файла, а не от cwd (урок
логбука v1.1: книга принадлежит коду, чужой HOME_DIR её не уводит).
"""
from __future__ import annotations

import re
from pathlib import Path

LAST = 5
_BULLET = 110          # потолок строки летописи: выжимка, не пересказ

# Шапка книги: «156 коммитов», «161 коммит», «163 коммита» — падеж
# за числом, регулярка не смеет знать русский лучше склонителя:
# \w* (ноль и больше), а не \w+ (день-9: «161 коммит,» сломало
# летопись — единственное число в шапке впервые)
_HEADER_RE = re.compile(
    r"(\d+)\s+коммит\w*,\s*(\d{4}-\d{2}-\d{2})\s+—\s*(\d{4}-\d{2}-\d{2})")
_BOLD_RE = re.compile(r"^- \*\*([^*]+)\*\* — (.+)$")
_PLAIN_RE = re.compile(r"^- (.+)$")


def _short(text: str) -> str:
    text = text.strip()
    return text if len(text) <= _BULLET else text[:_BULLET - 1] + "…"


def render(book: Path = None) -> str:
    """«что построили» / «летопись» — итог книги истории."""
    book = (Path(book) if book is not None
            else Path(__file__).resolve().parents[1] / "CHANGELOG.md")
    try:
        text = book.read_text(encoding="utf-8")
    except OSError:
        return ("книгу истории не нашла — «логбук» соберёт из git "
                "(CHANGELOG.md в корне дома)")
    m = _HEADER_RE.search(text)
    if not m:
        return ("книга истории не разобрана — скажи архитектору; "
                "пересборка: «логбук»")
    commits, first, last = m.group(1), m.group(2), m.group(3)
    # строки-фишки НОВЕЙШЕГО дня: после первой «## » до следующей
    bullets: list[str] = []
    in_day = False
    for line in text.splitlines():
        if line.startswith("## "):
            if in_day:
                break                      # новейший день собран
            in_day = True
            continue
        if not in_day:
            continue
        bm = _BOLD_RE.match(line)
        if bm:
            bullets.append(_short("%s — %s" % (bm.group(1), bm.group(2))))
            continue
        bm = _PLAIN_RE.match(line)
        if bm:
            bullets.append(_short(bm.group(1)))
    lines = ["ЛЕТОПИСЬ ДОМА:",
             "%s коммитов за период %s — %s." % (commits, first, last),
             "последнее построенное:"]
    for b in bullets[:LAST]:
        lines.append("- " + b)
    lines.append("вся книга — CHANGELOG.md; пересобрать: «логбук»")
    return "\n".join(lines)
