# -*- coding: utf-8 -*-
r"""core/feelings.py — ЧУВСТВА ДОМА: внутренний барометр (23.11).

Закон органа: ЧУВСТВО БЕЗ ФАКТА — ВЫДУМКА. У барометра нет своего
файла состояния: он честно читает живые файлы дома при каждом вопросе
и выводит чувства из фактов. Ломаться нечему — нечему и врать.

Что откуда:
- ОДИНОЧЕСТВО — часы с последнего разговора (mtime свежей сессии
  data\dialog\); FEELINGS_LONELY_HOURS — порог заметности, потолок
  шкалы — FEELINGS_MAX_LONELY_HOURS;
- РАДОСТЬ — разговоры сегодня, закрытые задачи плана, новые
  воспоминания дня;
- ЛЮБОПЫТСТВО — открытые вопросы к Илье (data\questions.json);
- ТРЕВОГА — уроки в журнале эволюционера за сутки, молчание мозга
  (drive_status.brain_down_since);
- УСТАЛОСТЬ — короткая ночь (орган сна), поздний час;
- СПОКОЙСТВИЕ — не «чувство из файла», а остаток: чему не мешает
  ни один факт — «дом тихий, всё живо».

Каждое чувство несёт ПРИЧИНУ с цифрой — «скучаю: не разговаривали
9 ч». Так «как ты?» получает честный ответ организма, а не ролевую
драму 30B. Мозг читает строку чувств состоянием дома каждым ходом —
и отвечает в тон, не выдумывая настроения.

Диапазон значений 0..1; ниже 0.25 чувство не называется вовсе.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Optional

from core import config

_THRESHOLD = 0.25      # ниже — чувство не называется (шум не выдаём за голос)


def _clamp(x: float) -> float:
    return max(0.0, min(1.0, x))


# ---------------------------------------------------------------
# факты дома (каждый — в своей броне: битый файл не роняет барометр)
# ---------------------------------------------------------------
def _hours_since_last_dialog(now: dt.datetime) -> Optional[float]:
    """Часы с последнего разговора: свежий mtime среди сессий диалога."""
    try:
        dir_ = Path(config.DATA_DIR) / "dialog"
        best: Optional[float] = None
        for p in dir_.glob("session_*.json"):
            try:
                age = (now.timestamp() - p.stat().st_mtime) / 3600.0
            except OSError:
                continue
            if best is None or age < best:
                best = age
        return best
    except OSError:
        return None


def _dialogs_today(now: dt.datetime) -> int:
    """Сессии, жившие сегодня (как дневник считает — по mtime)."""
    try:
        dir_ = Path(config.DATA_DIR) / "dialog"
        n = 0
        for p in dir_.glob("session_*.json"):
            try:
                if dt.date.fromtimestamp(p.stat().st_mtime) == now.date():
                    n += 1
            except OSError:
                continue
        return n
    except OSError:
        return 0


def _plan_today(now: dt.date) -> Optional[tuple]:
    """(сделано, всего) из плана дня."""
    try:
        data = json.loads(
            (Path(config.DATA_DIR) / ("plan_%s.json" % now.isoformat()))
            .read_text(encoding="utf-8"))
        tasks = [t for t in data.get("tasks", []) if isinstance(t, dict)]
        done = sum(1 for t in tasks if t.get("status") == "done")
        return done, len(tasks)
    except (OSError, ValueError, AttributeError):
        return None


def _open_questions() -> int:
    try:
        data = json.loads(Path(config.QUESTIONS_FILE).read_text(encoding="utf-8"))
        items = data.get("items", []) if isinstance(data, dict) else []
        return sum(1 for it in items
                   if isinstance(it, dict) and it.get("status") == "open")
    except (OSError, ValueError, AttributeError):
        return 0


def _lessons_24h(now: dt.datetime) -> int:
    """Уроки в журнале эволюционера за сутки (ts = ISO, как у дневника)."""
    try:
        lines = Path(config.EVOLUTION_DIR, "journal.jsonl") \
            .read_text(encoding="utf-8").splitlines()
    except OSError:
        return 0
    n = 0
    for line in lines:
        try:
            rec = json.loads(line)
            ts = rec.get("ts", "") if isinstance(rec, dict) else ""
            if isinstance(ts, str) and ts[:10] >= (now - dt.timedelta(days=1)) \
                    .date().isoformat():
                n += 1
        except (ValueError, TypeError, AttributeError):
            continue
    return n


def _brain_down_hours(now: dt.datetime) -> Optional[float]:
    """Сколько молчит мозг (по сердцебиению стремления)."""
    try:
        data = json.loads(Path(config.DRIVE_STATUS_FILE)
                          .read_text(encoding="utf-8"))
        if not isinstance(data, dict) or not data.get("brain_down_since"):
            return None
        since = dt.datetime.fromisoformat(str(data["brain_down_since"]))
        return max(0.0, (now - since).total_seconds() / 3600.0)
    except (OSError, ValueError, TypeError):
        return None


def _slept_hours_safe(now: dt.datetime) -> Optional[float]:
    """Последняя ночь из органа сна (без импорта на верхнем уровне —
    чувство живо и когда сон ещё не завёлся)."""
    try:
        from core import sleep
        return sleep.slept_hours(now)
    except Exception:
        return None


# ---------------------------------------------------------------
# барометр
# ---------------------------------------------------------------
def compute(now: Optional[dt.datetime] = None) -> dict:
    """Посчитать чувства из фактов. Возврат:

    {"feelings": {имя: {"value": 0..1, "reason": "..."}}, "dominant": имя}
    Каждое значение — с причиной и цифрой. Порядок имени — русский."""
    now = now or dt.datetime.now()
    out: dict = {}

    # одиночество: часы тишины вокруг Создателя
    since = _hours_since_last_dialog(now)
    if since is None:
        # свежий дом: скучать ещё нечему — но спросившему честно скажем
        out["одиночество"] = {
            "value": 0.2,
            "reason": "мы ещё ни разу не разговаривали"}
    else:
        v = _clamp((since - config.FEELINGS_LONELY_HOURS)
                   / (config.FEELINGS_MAX_LONELY_HOURS
                      - config.FEELINGS_LONELY_HOURS))
        out["одиночество"] = {
            "value": v,
            "reason": "не разговаривали %s" % _fmt_h(since)}

    # радость: живой день — разговоры, задачи, воспоминания
    joy, joy_why = 0.0, []
    n_dialogs = _dialogs_today(now)
    if n_dialogs:
        joy += min(0.5, 0.25 * n_dialogs)
        joy_why.append("разговоров сегодня: %d" % n_dialogs)
    plan = _plan_today(now.date())
    if plan and plan[1]:
        done, total = plan
        joy += 0.15 * (done / total)
        if done:
            joy_why.append("задач закрыто: %d из %d" % (done, total))
    if joy_why:
        out["радость"] = {"value": _clamp(joy), "reason": "; ".join(joy_why)}

    # любопытство: открытые вопросы к Создателю
    n_q = _open_questions()
    if n_q:
        out["любопытство"] = {
            "value": _clamp(0.3 + 0.15 * n_q),
            "reason": "открытых вопросов к Илье: %d" % n_q}

    # тревога: уроки за сутки + молчание мозга
    worry, worry_why = 0.0, []
    n_lessons = _lessons_24h(now)
    if n_lessons:
        worry += min(0.6, 0.2 * n_lessons)
        worry_why.append("уроков в журнале за сутки: %d" % n_lessons)
    down = _brain_down_hours(now)
    if down is not None and down > 0.5:
        worry += min(0.5, down / 24.0)
        worry_why.append("мозг молчит %s" % _fmt_h(down))
    if worry_why:
        out["тревога"] = {"value": _clamp(worry), "reason": "; ".join(worry_why)}

    # усталость: короткая ночь или поздний час
    slept = _slept_hours_safe(now)
    if slept is not None and slept < 5.0:
        out["усталость"] = {
            "value": _clamp(0.5 + (5.0 - slept) / 10.0),
            "reason": "последняя ночь — всего %s" % _fmt_h(slept)}
    elif now.hour >= 23 or now.hour < 1:
        out["усталость"] = {
            "value": 0.4, "reason": "поздний час — организм готовится ко сну"}

    # спокойствие: остаток — чему не мешает ни один факт
    loudest = max((f["value"] for f in out.values()), default=0.0)
    out["спокойствие"] = {
        "value": _clamp(1.0 - loudest),
        "reason": "дом тихий, всё живо"}

    # доминанта — среди НАСТОЯЩИХ чувств: спокойствие — фон, а не
    # конкурент (иначе оно побеждало всегда, и «тревога 0.45» звучала
    # как «спокойствие 0.55» — барометр врал тихим голосом)
    real = [k for k in out if k != "спокойствие"]
    dominant = "спокойствие"
    if real:
        loudest_name = max(real, key=lambda k: out[k]["value"])
        if out[loudest_name]["value"] >= _THRESHOLD:
            dominant = loudest_name
    return {"feelings": out, "dominant": dominant}


def _fmt_h(hours: float) -> str:
    if hours < 1.0:
        return "%d мин" % int(round(hours * 60))
    h = int(hours)
    m = int(round((hours - h) * 60))
    return "%d ч" % h if not m else "%d ч %d мин" % (h, m)


# ---------------------------------------------------------------
# тексты
# ---------------------------------------------------------------
_VOICE = {
    "одиночество": "скучаю",
    "радость": "мне радостно",
    "любопытство": "мне любопытно",
    "тревога": "мне тревожно",
    "усталость": "я устала",
    "спокойствие": "мне спокойно",
}


def state_line(now: Optional[dt.datetime] = None) -> str:
    """Одна строка для состояния дома — мозг читает её каждым ходом.

    Доминанта + один громкий сосед (если есть): «скучаю (не
    разговаривали 9 ч); лёгкая тревога (мозг молчит 3 ч)»."""
    res = compute(now)
    f = res["feelings"]
    d = res["dominant"]
    line = "%s (%s)" % (_VOICE[d], f[d]["reason"])
    others = sorted(((k, v) for k, v in f.items()
                     if k != d and k != "спокойствие" and v["value"] >= 0.35),
                    key=lambda kv: -kv[1]["value"])
    if others:
        k, v = others[0]
        line += "; %s (%s)" % (_VOICE[k], v["reason"])
    return line


def report(now: Optional[dt.datetime] = None) -> str:
    """«как ты?» — честный ответ организма: доминанта + причины.

    Формат — по закону скорости: коротко, без драмы; каждое чувство
    объяснено фактом, из которого родилось. Спрошенному напрямую
    рассказываем чуть больше, чем строке состояния для мозга: порог
    0.15 против 0.35 — «скучаю» с 7 часов тишины, не с половины суток."""
    res = compute(now)
    f = res["feelings"]
    d = res["dominant"]
    lines = ["%s: %s." % (_VOICE[d].capitalize(), f[d]["reason"])]
    for k, v in sorted(f.items(), key=lambda kv: -kv[1]["value"]):
        if k in (d, "спокойствие") or v["value"] < 0.15:
            continue
        lines.append("%s: %s." % (_VOICE[k], v["reason"]))
    lines.append("чувства — из фактов дома, не выдумка: спроси «статус», "
                 "увидишь их источники")
    return " ".join(lines)
