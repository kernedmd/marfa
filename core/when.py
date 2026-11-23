# -*- coding: utf-8 -*-
"""core/when.py — «КОГДА И СКОЛЬКО» (Ф17-Ф19, 23.11): вопросы о датах.

У мозга нет честного календаря (закон фактов №38: год выдумывается от
бедности) — а у дома есть. Три фишки одним органом:
- Ф17 «сколько до 31 декабря» — обратный отсчёт в днях (даты: «нового
  года», «8 марта», «31.12», «2027-01-01»); прошедшие в этом году —
  честно считаем до ближайших будущих;
- Ф18 «сколько прошло с 1 сентября» — сколько дней минуло (дата без
  года — ближайшая прошедшая);
- Ф19 «какой день недели 31 декабря» — день недели даты.
"""
from __future__ import annotations

import datetime as dt
import re

MONTHS = {
    "январь": 1, "января": 1, "февраль": 2, "февраля": 2,
    "март": 3, "марта": 3, "апрель": 4, "апреля": 4,
    "май": 5, "мая": 5, "июнь": 6, "июня": 6,
    "июль": 7, "июля": 7, "август": 8, "августа": 8,
    "сентябрь": 9, "сентября": 9, "октябрь": 10, "октября": 10,
    "ноябрь": 11, "ноября": 11, "декабрь": 12, "декабря": 12,
}
MONTH_NAMES = {1: "января", 2: "февраля", 3: "марта", 4: "апреля",
               5: "мая", 6: "июня", 7: "июля", 8: "августа",
               9: "сентября", 10: "октября", 11: "ноября", 12: "декабря"}
WEEKDAYS = ("понедельник", "вторник", "среда", "четверг", "пятница",
            "суббота", "воскресенье")

_RX_ISO = re.compile(r"(\d{4})-(\d{2})-(\d{2})")
_RX_DM = re.compile(r"(\d{1,2})\.(\d{1,2})(?:\.(\d{4}))?")
_RX_DWORD = re.compile(r"(\d{1,2})\s+([а-яё]+)(?:\s+(\d{4}))?")


def _parse_date(s: str, now: dt.date) -> dt.date | None:
    """Дата из текста: 2027-01-01 / 31.12[.2027] / 31 декабря / нового года."""
    t = str(s or "").strip().lower().rstrip("?.!")
    if re.match(r"^нов(?:ого|ый)\s+год", t):
        nxt = dt.date(now.year, 1, 1)
        return nxt if nxt > now else dt.date(now.year + 1, 1, 1)
    m = _RX_ISO.search(t)
    if m:
        try:
            return dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    m = _RX_DM.search(t)
    if m:
        d, mon = int(m.group(1)), int(m.group(2))
        year = int(m.group(3)) if m.group(3) else None
        try:
            if year:
                return dt.date(year, mon, d)
            cand = dt.date(now.year, mon, d)
            return cand
        except ValueError:
            return None
    m = _RX_DWORD.search(t)
    if m and m.group(2) in MONTHS:
        d, mon = int(m.group(1)), MONTHS[m.group(2)]
        year = int(m.group(3)) if m.group(3) else now.year
        try:
            return dt.date(year, mon, d)
        except ValueError:
            return None
    return None


def _next_occurrence(d: dt.date, now: dt.date) -> dt.date:
    """Дата без года — ближайшая БУДУЩАЯ (8 марта прошло — считаем до следующего)."""
    if d.year == now.year and d < now:
        try:
            return d.replace(year=now.year + 1)
        except ValueError:                  # 29 февраля
            return dt.date(now.year + 5, d.month, 1)
    return d


def _past_occurrence(d: dt.date, now: dt.date) -> dt.date:
    """Дата без года — ближайшая ПРОШЛАЯ (для «сколько прошло»)."""
    if d.year == now.year and d > now:
        return d.replace(year=now.year - 1)
    return d


def until(text: str, now: dt.date = None) -> str:
    """Ф17: «сколько до X» — дни до даты (без года — до ближайшей будущей).

    Принимает и полную команду, и голую дату: известные префиксы
    («сколько до», «сколько дней до») снимаются."""
    now = now or dt.date.today()
    payload = re.sub(r"^сколько\s+(?:дней\s+)?до\s+", "",
                     str(text or "").strip().lower(), flags=re.IGNORECASE)
    d = _parse_date(payload, now)
    if d is None:
        return ("дату не поняла; скажи «сколько до 31 декабря», "
                "«сколько до 8 марта» или «сколько до 2027-01-01»")
    d = _next_occurrence(d, now)
    days = (d - now).days
    if days == 0:
        return "это сегодня — %s" % _human(d, now)
    return "до %s — %d %s (%s)" % (_human(d, now), days, _plural(days),
                                   WEEKDAYS[d.weekday()])


def since(text: str, now: dt.date = None) -> str:
    """Ф18: «сколько прошло с X» — дни от даты (без года — ближайшая прошедшая)."""
    now = now or dt.date.today()
    payload = re.sub(r"^сколько\s+(?:дней\s+)?прошло\s+(?:с|со)\s+", "",
                     str(text or "").strip().lower(), flags=re.IGNORECASE)
    d = _parse_date(payload, now)
    if d is None:
        return ("дату не поняла; скажи «сколько прошло с 1 сентября» "
                "или «сколько прошло с 2026-09-01»")
    d = _past_occurrence(d, now)
    days = (now - d).days
    if days < 0:
        return "эта дата ещё не наступила — про будущее спроси «сколько до»"
    if days == 0:
        return "это сегодня"
    return "с %s прошло %d %s" % (_human(d, now), days, _plural(days))


def weekday(text: str, now: dt.date = None) -> str:
    """Ф19: «какой день недели X» — без года считаем текущим годом."""
    now = now or dt.date.today()
    payload = re.sub(r"^какой\s+день\s+недели\s+", "",
                     str(text or "").strip().lower(), flags=re.IGNORECASE)
    d = _parse_date(payload, now)
    if d is None:
        return ("дату не поняла; скажи «какой день недели 31 декабря» "
                "или «какой день недели 08.03.2027»")
    note = ""
    if d.year == now.year and d < now:
        note = " (в этом году уже прошло)"
    return "%s — %s%s" % (_human(d, now), WEEKDAYS[d.weekday()], note)


def _human(d: dt.date, now: dt.date = None) -> str:
    now = now or dt.date.today()
    tail = "" if d.year == now.year else " %d" % d.year
    return ("%d %s" % (d.day, MONTH_NAMES[d.month]) + tail).strip()


def _plural(n: int) -> str:
    if n % 10 == 1 and n % 100 != 11:
        return "день"
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return "дня"
    return "дней"
