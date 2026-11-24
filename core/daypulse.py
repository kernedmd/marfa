# -*- coding: utf-8 -*-
"""core/daypulse.py — Ф85 «ПУЛЬС ДНЯ» (день-13, круг 15): тело организма
в живых цифрах.

Живой лог Создателя (24.11): «солнце» за 91,3 с · 9 ток · промпт 4416 —
цифры ЕХАЛИ в штампе каждого ответа и в brain_log.jsonl, но разговором
они не становились: «как ты?» отвечала ДУША (чувства из фактов —
одиночество, план, похвалы), а ТЕЛО (сколько ходов, какой медианы
секунды, были ли пустые ответы, тяжелее ли сегодня чем на неделе) —
молчало. Организм, который не знает своего пульса, — не организм:
врач видит кардиограмму, а не слушает «наверное, нормально».

Пульс честен по построению:
- пустой журнал — «мозг сегодня молчал», а не нули-обман;
- дрейф скорости требует ХОДОВ (меньше 3 — «мало ходов», без спекуляций);
- каждая цифра — из brain_log.jsonl, ничего не выдумано (закон фактов).

Ф87 «дрейф скорости» — живой брат Ф44: тот меряет деградацию по
прогонам батареи, этот — по живым ходам дня (медиана сегодня против
медианы прошлой недели; хуже на 30% — честное «тяжелее»).
"""
from __future__ import annotations

import datetime as dt
import json
import statistics
from pathlib import Path
from typing import Optional

from core import config

# порог дрейфа скорости, % (тот же порядок, что Ф44 по батарее)
DRIFT_WARN_PCT = 30
# меньше ходов — дрейф не считаем: три «секунды» не статистика
DRIFT_MIN_TURNS = 3
# сколько пустых/не-json за сутки будят шрамы в хвосте хода (Ф88)
SCAR_THRESHOLD = 2
# шрамы — одна строка, не трактат: хвост хода дорог (урок диеты)
SCAR_CAP_CHARS = 200


def _read_records() -> list[dict]:
    """Живые строки мозгового журнала; битые JSON пропускаются молча —
    журнал не орган дыхания, пульс не должен падать от кривой строки."""
    try:
        p = Path(config.BRAIN_LOG_FILE)
        if not p.exists():
            return []
        out: list[dict] = []
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if isinstance(rec, dict):
                out.append(rec)
        return out
    except OSError:
        return []


def _day_of(rec: dict) -> Optional[dt.date]:
    """Дата строки журнала по штампу «ГГГГ-ММ-ДД …»; битый штамп — None."""
    ts = str(rec.get("ts") or "")
    try:
        return dt.date.fromisoformat(ts[:10])
    except ValueError:
        return None


def _parse_ts(rec: dict) -> Optional[dt.datetime]:
    ts = str(rec.get("ts") or "")
    try:
        return dt.datetime.strptime(ts[:19], "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def _secs(rec: dict) -> Optional[float]:
    v = rec.get("secs")
    if isinstance(v, (int, float)):
        return float(v)
    return None


def _empty_note(rec: dict) -> bool:
    """Пустой ответ или не-json — обе беды суток: ответ не дошёл."""
    return str(rec.get("note") or "") in ("пустой ответ", "не-json")


def _collect_window(records: list[dict],
                    first_day: dt.date,
                    last_day: Optional[dt.date] = None) -> dict:
    """Механика окна дней: ходы, медиана/макс секунд, токены, пустые."""
    last_day = last_day or first_day
    in_win = [r for r in records
              if (d := _day_of(r)) is not None and first_day <= d <= last_day]
    secs = [s for s in (_secs(r) for r in in_win) if s is not None]
    ptok = sum(int(r.get("prompt_tokens") or 0) for r in in_win
               if isinstance(r.get("prompt_tokens"), (int, float)))
    ctok = sum(int(r.get("completion_tokens") or 0) for r in in_win
               if isinstance(r.get("completion_tokens"), (int, float)))
    think = sum(int(r.get("think_chars") or 0) for r in in_win
                if isinstance(r.get("think_chars"), (int, float)))
    return {
        "turns": len(in_win),
        "answered": sum(1 for r in in_win if r.get("ok")),
        "empty": sum(1 for r in in_win if _empty_note(r)),
        "secs": secs,
        "median": statistics.median(secs) if secs else None,
        "max": max(secs) if secs else None,
        "total": sum(secs),
        "ptok": ptok,
        "ctok": ctok,
        "think": think,
    }


def collect(now: Optional[dt.datetime] = None) -> dict:
    """Пульс СЕГОДНЯ — всё, что мозг сделал за день, в одних числах."""
    now = now or dt.datetime.now()
    return _collect_window(_read_records(), now.date())


def week_baseline(now: Optional[dt.datetime] = None) -> dict:
    """Опора дрейфа: ПРОШЛЫЕ 7 дней до сегодня (сегодня не входит —
    иначе медленный день тянул бы базу сам за собой)."""
    now = now or dt.datetime.now()
    return _collect_window(_read_records(),
                           now.date() - dt.timedelta(days=7),
                           now.date() - dt.timedelta(days=1))


def _fmt1(x: Optional[float]) -> str:
    return ("%.1f" % x).replace(".", ",") if x is not None else "?"


def _plural_turns(n: int) -> str:
    if n % 10 == 1 and n % 100 != 11:
        return "ход"
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return "хода"
    return "ходов"


def drift_line(now: Optional[dt.datetime] = None) -> str:
    """Ф87 «ДРЕЙФ СКОРОСТИ»: сегодня против прошлой недели.

    Живой брат Ф44 (деградация по батарее): там здоровье меряют
    контрольные прогоны, здесь — настоящие ходы Создателя. Мало ходов
    (меньше 3 сегодня или в базе) — честное «мало ходов», без диагноза
    из двух точек: три секунды — не статистика.
    """
    now = now or dt.datetime.now()
    today = collect(now)
    week = week_baseline(now)
    if today["turns"] < DRIFT_MIN_TURNS or week["turns"] < DRIFT_MIN_TURNS:
        return "дрейф: мало ходов для честного сравнения"
    if not today["median"] or not week["median"]:
        return "дрейф: мало ходов для честного сравнения"
    pct = (today["median"] - week["median"]) / week["median"] * 100
    if pct >= DRIFT_WARN_PCT:
        return ("дрейф: тело тяжелее — медиана %s с против %s с "
                "за прошлую неделю (+%d%%)" % (_fmt1(today["median"]),
                                               _fmt1(week["median"]), int(pct)))
    if pct <= -DRIFT_WARN_PCT:
        return ("дрейф: тело легче — медиана %s с против %s с "
                "за прошлую неделю (−%d%%)" % (_fmt1(today["median"]),
                                               _fmt1(week["median"]),
                                               int(-pct)))
    return "дрейф: в норме (медиана %s с против %s с за неделю)" % (
        _fmt1(today["median"]), _fmt1(week["median"]))


def render(now: Optional[dt.datetime] = None) -> str:
    """Полный пульс дня — разговорный, но каждая цифра из журнала."""
    now = now or dt.datetime.now()
    p = collect(now)
    if not p["turns"]:
        return ("Пульс дня: мозг сегодня молчал — ни одного хода в "
                "журнале. Тело отдыхало.")
    lines = ["Пульс дня (%s):" % now.strftime("%d.%m.%Y"),
             "ходов мозга — %d (%s), ответило слово в слово — %d"
             % (p["turns"], _plural_turns(p["turns"]), p["answered"])]
    if p["secs"]:
        lines.append("секунды: медиана %s · худший %s · всего %.0f с "
                     "(это %s мин мышления)"
                     % (_fmt1(p["median"]), _fmt1(p["max"]),
                        p["total"], _fmt1(p["total"] / 60)))
    if p["ptok"] or p["ctok"]:
        lines.append("токены: промпт %d · генерация %d%s"
                     % (p["ptok"], p["ctok"],
                        (" · думание %d симв" % p["think"]) if p["think"] else ""))
    if p["empty"]:
        lines.append("пустых ответов — %d (дом показал улику в чате, "
                     "«хвост brain пустой ответ» — вещдок)" % p["empty"])
    else:
        lines.append("пустых ответов нет")
    lines.append(drift_line(now))
    return "\n".join(lines)


def body_line(now: Optional[dt.datetime] = None) -> str:
    """Тело одной строкой — для «как ты» и зеркал (статус/изучи себя).

    Душа и тело — разные врачи: feelings.report() говорит про
    настроение, эта строка — про железо и секунды. Обе правды
    ездят вместе, но не притворяются друг другом.
    """
    now = now or dt.datetime.now()
    p = collect(now)
    if not p["turns"]:
        return "тело: сегодня молчало — мозг не делал ни одного хода"
    parts = ["%d %s" % (p["turns"], _plural_turns(p["turns"]))]
    if p["median"] is not None:
        parts.append("медиана %s с" % _fmt1(p["median"]))
    parts.append("пустых ответов %d" % p["empty"])
    return "тело: " + ", ".join(parts)


def scars_block(now: Optional[dt.datetime] = None) -> Optional[str]:
    """Ф88 «ШРАМЫ В ХВОСТ»: если за сутки мозг возвращал пустые
    ответы — хвост хода напоминает закон ключа ДО новой беды.

    Ф82 лечит пустоту ПОСЛЕ улики (укол-диагност на ретрае); Ф88 —
    ПРОФИЛАКТИКА: шрамы суток едят одной строкой в каждый ход дня,
    и к вечеру мозг уже не кладёт ответ под русский ключ. Порог 2:
    единичный случай — шум, серия — болезнь. Чистые сутки — блок
    молчит: хвост хода дорог (урок диеты), расплачиваться строкой
    за хорошее поведение — расточительство.
    """
    now = now or dt.datetime.now()
    horizon = now - dt.timedelta(hours=24)
    records = _read_records()
    fresh = [r for r in records
             if (t := _parse_ts(r)) is not None and t >= horizon]
    n = sum(1 for r in fresh if _empty_note(r))
    if n < SCAR_THRESHOLD:
        return None
    text = ("ШРАМЫ СУТОК (дом видит по журналу — не повторяй): за "
            "последние сутки %d пустых ответов. Закон ключа: ответ — "
            "только в поле «answer» латиницей, значение — непустой "
            "текст; null, пустая строка и русский ключ «ответ» — не "
            "ответ." % n)
    return text[:SCAR_CAP_CHARS]


# ---------- круг 16 «ИТОГ ДНЯ» (Ф90-Ф93) ----------

def today_memories(memory, now: Optional[dt.datetime] = None,
                   limit: int = 10) -> list[str]:
    """Ф91 «ЧТО ЗАПОМНИЛА СЕГОДНЯ»: записи памяти, рождённые сегодня.

    Память живёт годами, а день — это день: Создатель спрашивает не
    «что ты помнишь» (это recall), а «что НОВОГО легло сегодня».
    Источник — created_at живых записей; битые даты честно мимо
    (урок recent: дайджест строится из честных дат, а не из мусора).
    """
    now = now or dt.datetime.now()
    midnight = dt.datetime.combine(now.date(), dt.time.min).timestamp()
    try:
        recs = memory.recent(midnight, limit=limit)
    except Exception:
        return []
    out = []
    for rec in recs:
        text = str(rec.get("text") or "").strip()
        if not text:
            continue
        tags = rec.get("tags") or []
        if tags:
            out.append("%s (%s)" % (text, ", ".join(str(t) for t in tags)))
        else:
            out.append(text)
    return out


def week_render(now: Optional[dt.datetime] = None) -> str:
    """Ф92 «ТЕЛО В ДОКЛАДЕ»: неделя организма против предыдущей —
    для еженедельного доклада архитектора (№29).

    Доклад архитектора видел тесты, коммиты, диск и канон — всё это
    про ДОМ; про ТЕЛО (живые ходы, медиана, пустые ответы) доклад
    молчал. Неделя против недели — честный тренд: одна медленная
    суббота не диагноз, две недели подряд — дрейф, о котором Создатель
    обязан знать раньше, чем почувствует.
    """
    now = now or dt.datetime.now()
    records = _read_records()
    this = _collect_window(records, now.date() - dt.timedelta(days=6),
                           now.date())
    prev = _collect_window(records, now.date() - dt.timedelta(days=13),
                           now.date() - dt.timedelta(days=7))
    if not this["turns"] and not prev["turns"]:
        return "живых ходов за две недели нет — журнал мозга пуст"
    parts = ["неделя: %d %s" % (this["turns"], _plural_turns(this["turns"]))]
    if this["median"] is not None:
        parts.append("медиана %s с" % _fmt1(this["median"]))
    if this["empty"]:
        parts.append("пустых ответов %d" % this["empty"])
    if this["ptok"] or this["ctok"]:
        parts.append("токены: промпт %d · генерация %d"
                     % (this["ptok"], this["ctok"]))
    out = "; ".join(parts)
    if this["turns"] and prev["turns"] and this["median"] and prev["median"]:
        pct = (this["median"] - prev["median"]) / prev["median"] * 100
        if pct >= DRIFT_WARN_PCT:
            out += ("; ТЯЖЕЛЕЕ прошлой недели на %d%% (медиана %s с — "
                    "взгляни, что изменилось)" % (int(pct), _fmt1(prev["median"])))
        elif pct <= -DRIFT_WARN_PCT:
            out += "; легче прошлой недели на %d%%" % int(-pct)
    return out
