# -*- coding: utf-8 -*-
"""evolution/lessons.py — ЖУРНАЛ УРОКОВ И ПРАВИЛ (круг 20, Ф112-Ф113).

Родился на дому (день-13): C:\\Marfa\\journal\\lessons.json — свод
правил (R1-R10) и уроков (1-8), эволюция из ошибок. До круга 20 журнал
был складом: механизм эволюции падал на отсутствующей папке
(WinError 3 — «системе не удаётся найти указанный путь»), правила не
грузились в промпт, и цикл «ошибка -> урок -> правило -> проверка»
обрывался на «правило»: урок без применения — просто история.

Круг 20 замыкает цикл двумя законами:
- Ф113 САМОРОЖДЕНИЕ: ensure_file() создаёт папку и скелет, ТОЛЬКО если
  файла нет (старт панели + любое чтение органа). СУЩЕСТВУЮЩИЙ файл не
  трогаем НИКОГДА — лечим отсутствие пути, а не перезаписываем
  незнание: контент Создателя неприкосновенен;
- Ф112 УРОКИ В ХОДЕ: ядерная пятёрка правил (R1, R2, R4, R5, R7 —
  закон в config.LESSONS_CORE_IDS) грузится в системный промпт КАЖДОГО
  хода (agent._static_system): правило читается ДО действия, а не
  после краша. Остальные правила — рабочие, по теме (будущий шаг).

Формат файла (дом, день-13): author/executor в шапке (правило №40:
автор закона != исполнитель); rules — «что делать»: id + rule (короткое
правило) + logic (почему) + check (как применить); lessons — «что
случилось»: topic + error + rule (ссылка) + logic. Правило без логики —
склад фактов; логика без проверки — теория; урок без привязки к
правилу — просто история.

Диета день-11: в промпт едет директива и проверка (rule + check);
логика (почему) — в файле, для человека и архитектора. Правило — не
трактат. Сверх потолка блока (config.LESSONS_PROMPT_CAP_TOKENS)
режем ЦЕЛЫЕ правила с конца, никогда не разрезаем правило —
полузакон опаснее его отсутствия (закон L2 генома).
"""
from __future__ import annotations

import json
from pathlib import Path

from core import config

EXECUTOR = "Марфа"          # кто читает правила до действия и отвечает


def lessons_path() -> Path:
    """Путь к органу — лениво от config (закон песочниц: тесты дома
    не протекают в живой журнал, как reminders и answer_cache)."""
    return Path(config.LESSONS_FILE)


def _skeleton() -> dict:
    """Скелет пустого органа: шапка по правилу №40 (автор — Создатель,
    исполнитель — Марфа) и пустые секции. Только для РОЖДЕНИЯ файла:
    никакая перезапись существующего недопустима (Ф113)."""
    return {"author": "Илья", "executor": EXECUTOR,
            "rules": [], "lessons": []}


def ensure_file() -> bool:
    """Саморождение органа: папка + скелет, ТОЛЬКО если файла нет.

    Урок дня-13: путь был прописан в конфиге, папки не было — читатель
    падал с WinError 3. Теперь орган рождается сам: старт панели и
    каждое чтение. Битый существующий файл НЕ трогаем (лечение
    отсутствия, не перезапись незнания) — load() честно скажет
    архитектору. Возврат: True — создал, False — уже был или не смог
    (не крах: чтение ниже деградирует в пустоту с уроком).
    """
    try:
        p = lessons_path()
        if p.exists():
            return False
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(_skeleton(), ensure_ascii=False,
                                indent=1), encoding="utf-8")
        return True
    except OSError:
        return False


def _tell_architect(text: str) -> None:
    """Урок в журнал событий (правило 6.6: логи — истина). Журнал
    событий сам упал — молчим: один орган не тянет за собой другой."""
    try:
        from evolution import journal
        journal.log_lesson("прочее", text)
    except Exception:
        pass


def load() -> dict:
    """Читать журнал: словарь с rules/lessons (может быть пустым).

    Файла нет — самопочинка ensure_file (WinError 3 закрыт законом, а
    не везением); битый JSON — честная пустота + урок архитектору:
    упавший орган не роняет ход, а говорит о себе (закон №10 р3).
    """
    ensure_file()
    try:
        raw = lessons_path().read_text(encoding="utf-8")
    except OSError:
        return {"rules": [], "lessons": []}
    try:
        rec = json.loads(raw)
    except ValueError:
        _tell_architect("уроки: lessons.json битый — читаю как пустой, "
                        "расскажи архитектору")
        return {"rules": [], "lessons": []}
    if not isinstance(rec, dict):
        _tell_architect("уроки: lessons.json не словарь — читаю как "
                        "пустой, расскажи архитектору")
        return {"rules": [], "lessons": []}
    return rec


def _norm_id(v) -> str:
    """Нормальный вид id правила: R1, без регистра и пробелов —
    «r1 » и «R1» один закон (журнал пишет человек, не парсер)."""
    return str(v or "").strip().upper()


def core_rules() -> list[dict]:
    """Ядерная пятёрка журнала — в каноническом порядке закона
    (config.LESSONS_CORE_IDS), не в порядке файла.

    Чего в файле нет — пропускаем: журнал растёт, ядро не обязано быть
    полным в каждый момент (R7 может ещё не родиться). Битое правило
    (без текста) — не правило, пропускаем тоже.
    """
    rec = load()
    rules = rec.get("rules")
    if not isinstance(rules, list):
        return []
    by_id: dict[str, dict] = {}
    for r in rules:
        if isinstance(r, dict):
            rid = _norm_id(r.get("id"))
            if rid:
                by_id[rid] = r
    out: list[dict] = []
    for want in config.LESSONS_CORE_IDS:
        r = by_id.get(_norm_id(want))
        if r and str(r.get("rule") or r.get("text") or "").strip():
            out.append(r)
    return out


def prompt_lines() -> list[str]:
    """Ядерные правила строками промпта: «R1: текст — проверка: …».

    Диета день-11: директива + проверка; логика (почему) остаётся в
    файле — человеку. Поле text понимаем как синоним rule (журнал
    диктуется Создателем, формат мягкий). Разрезания правил НЕТ:
    длинное правило либо едет целиком, либо не едет вовсе (решает
    потолок блока в build_system, закон L2).
    """
    out: list[str] = []
    for r in core_rules():
        rid = _norm_id(r.get("id"))
        text = str(r.get("rule") or r.get("text") or "").strip()
        check = str(r.get("check") or "").strip()
        line = "%s: %s" % (rid, text)
        if check:
            line += " — проверка: %s" % check
        out.append(line)
    return out


def stats_line() -> str:
    """Строка для панели и статуса: сколько правил и уроков живёт.
    Пустой журнал — пустая строка (№38: каждая строка состояния стоит
    токенов, пустому органу в эфире делать нечего)."""
    rec = load()
    rules = rec.get("rules")
    lessons = rec.get("lessons")
    n_rules = len(rules) if isinstance(rules, list) else 0
    n_lessons = len(lessons) if isinstance(lessons, list) else 0
    if n_rules <= 0 and n_lessons <= 0:
        return ""
    return ("журнал уроков: %d правил, %d уроков; ядерные — в каждом "
            "моём ходе" % (n_rules, n_lessons))
