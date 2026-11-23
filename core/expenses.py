# -*- coding: utf-8 -*-
"""core/expenses.py — РАСХОДЫ (Ф14, 23.11): «расход: 200 хлеб».

Домашняя бухгалтерия на честном минимуме: «расход: <число> <что>» —
записать (число ищется первым в тексте, «руб/р/₽» снимаются),
«расходы» — сегодня и за 7 дней. Не калькулятор бюджета, а память о
мелких тратах: «куда ушли деньги» — вопрос недели. Потолок 1000
записей. Битый файл — честный ноль.
"""
from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path

from core import config

CAP = 1000


def _file() -> Path:
    return Path(config.EXPENSES_FILE)


def _load() -> list[dict]:
    try:
        items = json.loads(_file().read_text(encoding="utf-8"))
        return [it for it in items if isinstance(it, dict)] \
            if isinstance(items, list) else []
    except (OSError, ValueError):
        return []


def _save(items: list[dict]) -> None:
    _file().parent.mkdir(parents=True, exist_ok=True)
    _file().write_text(
        json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")


_RX_MONEY = re.compile(r"(\d+(?:[.,]\d{1,2})?)")


def add(payload: str, now: dt.datetime = None) -> str:
    """«расход: 200 хлеб» — сумма первая в тексте; без суммы — отказ."""
    now = now or dt.datetime.now()
    text = str(payload or "").strip()
    m = _RX_MONEY.search(text)
    if not m:
        return "сколько? скажи «расход: 200 хлеб» (сумма первой или где угодно)"
    amount = float(m.group(1).replace(",", "."))
    if amount <= 0:
        return "сумма должна быть больше нуля"
    what = text.replace(m.group(1), "", 1)
    what = re.sub(r"\b(?:руб(?:лей|я)?|р|₽)\b", "", what,
                  flags=re.IGNORECASE).strip(" ,.-")
    what = what or "без названия"
    items = _load()
    items.append({"amount": round(amount, 2), "text": what[:120],
                  "day": now.strftime("%Y-%m-%d"),
                  "ts": now.strftime("%d.%m %H:%M")})
    if len(items) > CAP:
        items = items[-CAP:]
    _save(items)
    return "записала расход: %s — %.0f руб (без копеек в отчёте не потеряю)" \
        % (what, amount)


def _sum(items: list[dict], days: set) -> tuple[float, int]:
    total, n = 0.0, 0
    for it in items:
        if str(it.get("day", "")) in days:
            try:
                total += float(it.get("amount", 0))
            except (TypeError, ValueError):
                continue
            n += 1
    return total, n


def render(now: dt.datetime = None) -> str:
    """«расходы» — сегодня, 7 дней, последние пять."""
    now = now or dt.datetime.now()
    items = _load()
    if not items:
        return "расходов не записано; записать: «расход: 200 хлеб»"
    today = {now.strftime("%Y-%m-%d")}
    week = {(now - dt.timedelta(days=k)).strftime("%Y-%m-%d")
            for k in range(7)}
    t_sum, t_n = _sum(items, today)
    w_sum, w_n = _sum(items, week)
    lines = ["РАСХОДЫ:",
             "сегодня: %s руб (%d записей)" % (_fmt_money(t_sum), t_n),
             "за 7 дней: %s руб (%d записей)" % (_fmt_money(w_sum), w_n)]
    tail = [it for it in items if str(it.get("day", "")) in week][-5:]
    if tail:
        lines.append("последние:")
        for it in tail:
            try:
                amt = float(it.get("amount", 0))
            except (TypeError, ValueError):
                continue
            lines.append("- %s: %s руб — %s"
                         % (it.get("ts", ""), _fmt_money(amt),
                            str(it.get("text", ""))[:60]))
    return "\n".join(lines)


def _fmt_money(v: float) -> str:
    s = ("%.2f" % v).rstrip("0").rstrip(".")
    return s.replace(".", ",")
