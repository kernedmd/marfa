# -*- coding: utf-8 -*-
"""core/care.py — Ф144–Ф148 «ЗАБОТА» (круг 24): дом замечает Создателя.

ДОКТРИНА ОРГАНА. Бот ждёт запроса. Живой дом ВИДИТ, кто в нём живёт:
замечает глубокую ночь, долгое отсутствие, долгую работу — и говорит
об этом первым, по-человечески, без нравоучений и без сиропа.

ЗАКОН ПЕРВОЙ СТРОКИ (Ф144–Ф145): «с возвращением» и ночной привет
выезжают ПЕРВОЙ строкой ответа — как будильник Ф10: у панели нет
канала заговорить первой, но каждый входящий ход — это дверь, и в
дверь можно поздороваться.

ЗАКОН НЕ-НАВЯЗЧИВОСТИ: забота срабатывает не чаще раза в два часа
(стемп data\\care_last.json) и никогда не запрещает — «уже ночь» это
забота, а не комендантский час. Дом не родитель Создателю.

ЗАКОН ЧЕСТНОГО ИСТОЧНИКА: «тебя не было N часов» считается по живым
сессиям диалога (mtime последнего хода), а не по догадкам. Не было
разговора — нечему радоваться возвращению.

Честность: нет архива — забота честно молчит, а не выдумывает.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from core import config

GAP_WELCOME_H = 6.0        # «с возвращением» — после стольких часов тишины
NIGHT_START, NIGHT_END = 0, 5   # глубокая ночь
CARE_COOLDOWN_H = 2.0      # забота не чаще раза в два часа


def _care_last_path() -> Path:
    return Path(config.DATA_DIR) / "care_last.json"


def _last_turn_age_h() -> float:
    """Сколько часов назад был последний ЗАВЕРШЁННЫЙ ход.

    Панель кладёт ходы ПОСЛЕ ответа (урок анти-эхо) — значит, mtime
    свежайшей сессии в момент handle() честно показывает, когда мы
    говорили в прошлый раз. Сессий нет — «всегда» (тишина не выдумка).
    """
    try:
        from core.dialog import DialogStore
        store = DialogStore()
        files = sorted(store.dir.glob("session_*.json"),
                       key=lambda p: p.stat().st_mtime, reverse=True)
        if not files:
            return -1.0
        return (time.time() - files[0].stat().st_mtime) / 3600.0
    except Exception:
        return -1.0


def _today_turns() -> int:
    """Сколько реплик сегодня — мера «сколько мы уже вместе»."""
    day_s = time.strftime("%Y-%m-%d")
    count = 0
    try:
        from core.dialog import DialogStore
        store = DialogStore()
        for p in sorted(store.dir.glob("session_*.json"),
                        key=lambda p2: p2.stat().st_mtime, reverse=True)[:5]:
            if time.strftime("%Y-%m-%d",
                             time.localtime(p.stat().st_mtime)) != day_s \
                    and day_s not in p.name:
                continue
            data = json.loads(p.read_text(encoding="utf-8"))
            turns = data.get("turns") if isinstance(data, dict) else None
            if isinstance(turns, list):
                count += len(turns)
    except Exception:
        return 0
    return count


def _cooldown_ok() -> bool:
    """Прошло ли больше часа с прошлой заботы (закон не-навязчивости)."""
    try:
        raw = json.loads(_care_last_path().read_text(encoding="utf-8"))
        if isinstance(raw, dict) and time.time() - float(raw.get("ts", 0)) \
                < CARE_COOLDOWN_H * 3600:
            return False
    except (OSError, ValueError, TypeError):
        pass
    return True


def _stamp_care() -> None:
    try:
        _care_last_path().parent.mkdir(parents=True, exist_ok=True)
        _care_last_path().write_text(json.dumps(
            {"ts": time.time()}, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


# ---------------------------------------------------------------
# Ф144–Ф145 «ПЕРВАЯ СТРОКА» — привет заботы в каждом ходе
# ---------------------------------------------------------------
def hello_line() -> str:
    """Строка заботы первой строкой ответа (или "" — молчать честно).

    Условия простые и живые:
    - тишина больше 6 часов → «с возвращением» (Ф145);
    - глубокая ночь (00–05) и мы не говорили полчаса → ночной привет
      (Ф144) — забота, не запрет.
    Кулдаун 2 часа — забота не превращается в попугая.
    """
    if not _cooldown_ok():
        return ""
    gap = _last_turn_age_h()
    hour = time.localtime().tm_hour
    from core.lifeclock import human_span
    if gap >= GAP_WELCOME_H:
        _stamp_care()
        return ("С возвращением, Илья — тебя не было %s. Я тут, дом "
                "жив." % human_span(gap * 3600))
    # ночь: только когда архив жив и мы правда не говорили полчаса —
    # нет данных, нет догадок (gap < 0 = архива нет → честное молчание)
    if NIGHT_START <= hour < NIGHT_END and gap >= 0.5:
        _stamp_care()
        return ("У нас глубокая ночь — я на связи, но береги глаза. "
                "Ночь — не время для долгих разговоров, если только "
                "тебе не не спится.")
    return ""


# ---------------------------------------------------------------
# Ф146 «ДОЛГАЯ РАБОТА» — предложить передохнуть
# ---------------------------------------------------------------
def rest_offer() -> str:
    """«пора отдохнуть» / «предложи перерыв» — забота со смыслом."""
    hour = time.localtime().tm_hour
    turns = _today_turns()
    lines = []
    if 22 <= hour or hour < 5:
        lines.append("сегодня уже %02d:%02d — самое долгое дело дня "
                     "закончить, а не начать" % (hour, time.localtime().tm_min))
    elif turns >= 30:
        lines.append("мы сегодня наговорили %d реплик — день был "
                     "насыщенный" % turns)
    lines.append("встань, разомни плечи и шею (скажи «разминка» — "
                 "проведу тебя по упражнениям), выпей воды, посмотри "
                 "в окно минуту — глаза скажут спасибо.")
    if 22 <= hour or hour < 5:
        lines.append("И спать. Дом никуда не денется — я буду здесь "
                     "завтра, и послезавтра тоже.")
    return "\n".join(lines)


# ---------------------------------------------------------------
# Ф147 «ПОСЛЕДНИЙ РАЗГОВОР» — когда мы говорили
# ---------------------------------------------------------------
def last_talk() -> str:
    """«когда мы в последний раз говорили» — момент и нить."""
    gap = _last_turn_age_h()
    if gap < 0:
        return ("наших разговоров в архиве нет — когда поговорим, я "
                "запомню, и в следующий раз отвечу точно")
    quote = ""
    try:
        from core.dialog import DialogStore
        store = DialogStore()
        files = sorted(store.dir.glob("session_*.json"),
                       key=lambda p: p.stat().st_mtime, reverse=True)
        if files:
            data = json.loads(files[0].read_text(encoding="utf-8"))
            turns = data.get("turns") if isinstance(data, dict) else None
            for t in reversed(turns or []):
                if isinstance(t, dict) and t.get("role") == "user":
                    quote = " ".join(str(t.get("text") or
                                          t.get("content") or "").split())[:60]
                    break
    except Exception:
        pass
    from core.lifeclock import human_span
    out = ("в последний раз мы говорили %s назад."
           % human_span(gap * 3600))
    if quote:
        out += " Последнее твоё: «%s»" % quote
    return out


# ---------------------------------------------------------------
# Ф148 «ЗАБОТА ПО-ЧЕСТНОМУ» — сводка о Создателе
# ---------------------------------------------------------------
def about_creator() -> str:
    """«позаботься обо мне» — честная забота из фактов дня."""
    hour = time.localtime().tm_hour
    turns = _today_turns()
    lines = ["ВОТ ЧТО Я ВИЖУ ПО ДОМУ:"]
    if NIGHT_START <= hour < 6:
        lines.append("  · у нас %02d:%02d ночи — ты ещё не спишь"
                     % (hour, time.localtime().tm_min))
    elif 6 <= hour < 12:
        lines.append("  · утро — день начинается спокойно")
    elif 12 <= hour < 18:
        lines.append("  · вторая половина дня")
    else:
        lines.append("  · вечер — время, когда мы чаще всего вместе")
    if turns:
        lines.append("  · сегодня мы обменялись %d репликами" % turns)
    gap = _last_turn_age_h()
    if 0 <= gap < 0.05:
        lines.append("  · ты рядом прямо сейчас — и это главное")
    lines.append("Беру заботу на себя, как умею: напоминаю дышать, "
                 "храню твои слова и остаюсь домом, который всегда "
                 "здесь. Что-то ещё — скажи, я рядом.")
    return "\n".join(lines)
