# -*- coding: utf-8 -*-
"""core/answercache.py — Ф41 «ПАМЯТЬ ОТВЕТОВ» (день-9, 24.11): «Помню —
уже отвечала».

Фронт 1 (скорость — единственная жалоба Создателя): мозг на CPU думает
десятками секунд, а повторный вопрос — не новая задача для организма.
Человек, спросивший дважды, получает ответ сразу: «Я же говорила…».
Так и дом: вопрос, который мозг уже честно отвечал, Марфа вспоминает
мгновенно — с честной строкой возраста в первой строке.

Это НЕ тихий кэш: честность — первая строка ответа («Помню — уже
отвечала N ч назад:»). Создатель видит, что ответ из памяти, и волен
переспросить иначе («ответь иначе» — обход памяти один ход).

ЧТО НЕ ПОМНИТСЯ (границы честности):
- ответы с действиями (за ними стоит сделанное — повторять слова без
  дела значит врать о мире);
- ответы об ошибках («мозг недоступен», сбои) — болезнь не souvenir;
- пустые и эхо-ответы (анти-эхо v3 уже их не выпускает).
Свежесть — TTL: старше 6 часов вопрос снова уходит мозгу (вчерашний
«который час» не имеет права вспоминаться). Потолок 200: дом не
слоновья память, старые записи подрезаются снизу.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Optional

from core import config

# обход памяти: «ответь иначе» гасит ОДИН следующий lookup
_bypass = {"on": False}


def _file() -> Path:
    """data/answer_cache.json — ЛЕНИВО от DATA_DIR (закон органов каждого
    хода, как reminders): песочница теста, патчившая DATA_DIR, получает
    свою память, живой дом — свою."""
    return Path(config.DATA_DIR) / "answer_cache.json"


def _norm(text: str) -> str:
    """Нормализация вопроса: регистр, пробелы, хвостовая пунктуация.
    «Статус?» и «статус» — один вопрос; внутренняя пунктуация — часть
    смысла и остаётся."""
    t = re.sub(r"\s+", " ", str(text or "").strip().lower())
    return t.rstrip("!.?…;:,. ").strip()


def _load() -> dict:
    try:
        rec = json.loads(_file().read_text(encoding="utf-8"))
        return rec if isinstance(rec, dict) else {}
    except (OSError, ValueError):
        return {}


def _save(items: dict) -> None:
    try:
        _file().parent.mkdir(parents=True, exist_ok=True)
        _file().write_text(
            json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError:
        pass  # память не записалась — разговор живёт дальше


def _age_human(secs: float) -> str:
    """Возраст по-человечески: «только что», «N мин назад», «N ч назад»."""
    if secs < 180:
        return "только что"
    if secs < 3600:
        return "%d мин назад" % max(1, round(secs / 60))
    return "%d ч назад" % max(1, round(secs / 3600))


def lookup(text: str, now: Optional[float] = None) -> Optional[str]:
    """Вспомнить ответ на вопрос. None — не помню (или устарело).

    Попадание считает hit (для «энергии дома»); просроченное — честно
    забывается на месте, а не живёт до следующей чистки.
    """
    if _bypass["on"]:
        _bypass["on"] = False   # обход одноразов: «ответь иначе» — один ход
        return None
    key = _norm(text)
    if not key:
        return None
    now = now if now is not None else time.time()
    items = _load()
    rec = items.get(key)
    if not isinstance(rec, dict):
        return None
    try:
        ts = float(rec.get("ts", 0))
    except (TypeError, ValueError):
        ts = 0.0
    age = now - ts
    if age < 0 or age > config.ANSWER_CACHE_TTL_SEC:
        items.pop(key, None)
        _save(items)
        return None
    try:
        rec["hits"] = int(rec.get("hits", 0)) + 1
    except (TypeError, ValueError):
        rec["hits"] = 1
    items[key] = rec
    _save(items)
    answer = str(rec.get("answer") or "").strip()
    if not answer:
        return None
    return "Помню — уже отвечала (%s):\n\n%s" % (_age_human(age), answer)


def store(text: str, answer: str) -> bool:
    """Запомнить ответ мозга на вопрос. Возвращает True, если легло в
    память. Пустой ответ, пустой вопрос и вопросы-романы (>400 символов
    нормализованных) не запоминаются: у памяти — достоинство."""
    key = _norm(text)
    ans = str(answer or "").strip()
    if not key or not ans or len(key) > 400:
        return False
    items = _load()
    # чистка устаревшего — заодно (ленивая, без отдельной службы)
    now = time.time()
    for k in [k for k, v in items.items()
              if not isinstance(v, dict)
              or now - float(v.get("ts", 0) or 0) > config.ANSWER_CACHE_TTL_SEC]:
        items.pop(k, None)
    items[key] = {"answer": ans, "ts": now, "hits": 0}
    if len(items) > config.ANSWER_CACHE_CAP:
        # подрезка: старейшие по ts — прочь, честно считаем сколько
        for k, _ts in sorted(((k, float(v.get("ts", 0) or 0))
                              for k, v in items.items()),
                             key=lambda p: p[1])[:len(items) - config.ANSWER_CACHE_CAP]:
            items.pop(k, None)
    _save(items)
    return True


def bypass() -> str:
    """«ответь иначе»: следующий вопрос идёт к мозгу, минуя память."""
    _bypass["on"] = True
    return ("Хорошо — в этот раз спрошу у мозга заново: повтори тот же "
            "вопрос, и я отвечу по-другому")


def forget_all() -> str:
    """«забудь ответы»: память ответов чистится целиком."""
    n = len(_load())
    _save({})
    if not n:
        return "память ответов и так пуста — мне нечего забывать"
    return "забыла все %d запомненных ответов — теперь каждый вопрос " \
           "идёт к мозгу" % n


def stats() -> dict:
    """Счёт для «энергии дома» (Ф45): сколько записей и попаданий."""
    items = _load()
    hits = 0
    for v in items.values():
        if isinstance(v, dict):
            try:
                hits += int(v.get("hits", 0))
            except (TypeError, ValueError):
                pass
    return {"entries": len(items), "hits": hits}


# ---------- разбор команд (границы — закон р3) ----------

def parse(text: str):
    """Разобрать команды памяти ответов. ('forget',) / None."""
    t = str(text or "").strip().lower()
    if t in ("забудь ответы", "забудь свои ответы", "забудь что отвечала"):
        return ("forget",)
    return None
