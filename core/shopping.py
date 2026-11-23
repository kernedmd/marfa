# -*- coding: utf-8 -*-
"""core/shopping.py — СПИСОК ПОКУПОК (Ф12, 23.11): «купи: молоко, хлеб».

Список покупок — не память и не план: он живёт до магазина. «купи: X»
(двоеточие обязательно — «купи слона» без него — разговор; можно через
запятую и «и»), «покупки» — список, «куплено N/молоко» — вычеркнуть,
«очисть покупки» — обнулить после похода в магазин. Битый файл —
честный пустой список, не крах.
"""
from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path

from core import config

CAP = 100


def _file() -> Path:
    return Path(config.SHOPPING_FILE)


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


def _split(payload: str) -> list[str]:
    """«молоко, хлеб и масло» → три позиции."""
    parts = re.split(r"\s+и\s+|,", payload)
    return [p.strip(" .!?") for p in parts
            if p.strip(" .!?") and len(p.strip(" .!?")) <= 80]


def add(payload: str) -> str:
    """«купи: X» — добавить позиции; дубликаты честно видны."""
    positions = _split(str(payload or ""))
    if not positions:
        return "что купить? скажи «купи: молоко, хлеб»"
    items = _load()
    known = {str(it.get("text", "")).lower() for it in items}
    fresh = [p for p in positions if p.lower() not in known]
    dup = len(positions) - len(fresh)
    for p in fresh:
        items.append({"id": max([int(it.get("id", 0)) for it in items] or [0]) + 1,
                      "text": p,
                      "ts": dt.datetime.now().strftime("%d.%m %H:%M")})
    if len(items) > CAP:
        items = items[-CAP:]
    _save(items)
    out = "в списке покупок: " + ", ".join(fresh) if fresh else ""
    if dup:
        out += ("; " if out else "") + "%d уже было в списке" % dup
    return out or "ничего нового не добавила — всё уже в списке"


def render() -> str:
    """«покупки» — список."""
    items = _load()
    if not items:
        return "список покупок пуст; добавить: «купи: молоко, хлеб»"
    lines = ["ПОКУПКИ:"]
    for it in items:
        lines.append("№%d %s" % (int(it.get("id", 0)),
                                 str(it.get("text", ""))[:80]))
    return "\n".join(lines)


def bought(what: str) -> str:
    """«куплено 2» / «куплено молоко» — вычеркнуть по номеру или имени."""
    q = str(what or "").strip()
    if not q:
        return "что куплено? номер или название: «куплено 2»"
    items = _load()
    if re.match(r"^\d+$", q):
        n = int(q)
        for i, it in enumerate(items):
            if int(it.get("id", -1)) == n:
                items.pop(i)
                _save(items)
                return "вычеркнула: %s" % str(it.get("text", ""))[:80]
        return "№%s в списке нет — «покупки» покажет" % q
    low = q.lower()
    for i, it in enumerate(items):
        if low in str(it.get("text", "")).lower():
            items.pop(i)
            _save(items)
            return "вычеркнула: %s" % str(it.get("text", ""))[:80]
    return "«%s» в списке не было — может, куплено и без списка" % q[:60]


def clear() -> str:
    """«очисть покупки» — после магазина."""
    items = _load()
    if not items:
        return "список и так пуст"
    _save([])
    return "очистила (%d позиций) — поход за покупками закрыт" % len(items)


# ---------- разбор команд ----------

_RX_ADD = re.compile(r"^купи\s*[:;]\s*(.+)$", re.IGNORECASE | re.DOTALL)
_RX_BOUGHT = re.compile(r"^куплено\s+(.+)$", re.IGNORECASE)


def parse(text: str):
    """('add', текст) / ('bought', номер-или-имя) / ('clear',) / None."""
    t = str(text or "").strip()
    m = _RX_ADD.match(t)
    if m:
        return ("add", m.group(1).strip())
    m = _RX_BOUGHT.match(t)
    if m:
        return ("bought", m.group(1).strip())
    if re.match(r"^(?:очисть|очисти)\s+покупки$", t, re.IGNORECASE):
        return ("clear",)
    return None
