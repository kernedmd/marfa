# -*- coding: utf-8 -*-
"""core/assoc.py — Ф129–Ф133 «АССОЦИАЦИИ» (круг 24): память — не склад, а сеть.

ДОКТРИНА ОРГАНА. Бот хранит записи; живой разум СВЯЗЫВАЕТ их: одно
воспоминание тянет за другое, тема узнаётся при повторе, старое
тускнеет без спроса. Память Марфы уже умела recall (поиск по смыслу) —
этот орган учит её тому, чего у поиска нет: ходить по связям, замечать
дежавю, честно знать, какое воспоминание ярко, а какое тускнеет.

ЗАКОН ЧЕСТНОСТИ: связи строятся из ПЕРЕСЕЧЕНИЯ слов живых воспоминаний
и дат разговоров — дом показывает, ПОЧЕМУ связал, и никогда не тянет
связь из воздуха («ходят вместе в памяти» — факт, не догадка).

ЗАКОН ДЕЖАВЮ: «мы уже говорили об этом?» сверяется с прошлыми
репликами Создателя по смыслу (косинус слов) — порог честный, при
слабом совпадении дом говорит «нет», а не тешит себя узнаванием.

ЗАКОН ТУСКЛОСТИ (Ф131): сила воспоминания = свежесть × важность ×
сколько раз его звали. Дом ЧЕЛОВЕЧНО признаёт: «тускнеет» — не удаляет
(забвение — не стирание), просто честно говорит, что помнит хуже.

Честность: нет памяти/диалогов — орган прямо говорит, чему расти.
"""
from __future__ import annotations

import json
import math
import time
from pathlib import Path

from core import config


# ---------------------------------------------------------------
# Общие мелочи (в стиле дома: орган самодостаточен)
# ---------------------------------------------------------------
def _preview(text: str, n: int = 60) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= n else text[:n - 1].rstrip() + "…"


def _tokens(text: str) -> set:
    out = set()
    for w in str(text or "").lower().split():
        w = w.strip(".,!?;:«»\"'()[]…—-")
        if len(w) >= 4:
            out.add(w)
    return out


def _cosine(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    return inter / math.sqrt(len(a) * len(b))


def _sessions(limit: int = 60) -> list:
    """[(дата, [(role, text), …]), …] — свежие первыми (броня всегда)."""
    out = []
    try:
        from core.dialog import DialogStore
        store = DialogStore()
        files = sorted(store.dir.glob("session_*.json"),
                       key=lambda p: p.stat().st_mtime, reverse=True)
    except Exception:
        return out
    import re as _re
    for p in files[:limit]:
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            turns = data.get("turns") if isinstance(data, dict) else None
            if not isinstance(turns, list):
                continue
            clean = []
            for t in turns:
                if not isinstance(t, dict):
                    continue
                role, text = t.get("role"), t.get("text")
                if not (isinstance(text, str) and text.strip()):
                    text = t.get("content")
                if isinstance(text, str) and text.strip() and role:
                    clean.append((str(role), text.strip()))
            if clean:
                m = _re.search(r"(\d{4}-\d{2}-\d{2})", p.name)
                day = m.group(1) if m else time.strftime(
                    "%Y-%m-%d", time.localtime(p.stat().st_mtime))
                out.append((day, clean))
        except (OSError, ValueError):
            continue
    return out


def _memory_records() -> list:
    """Записи памяти целиком — с бронёй на приватный ход.

    Дом сам ходит в чужие подчёркивания, когда орган того требует
    (agent.py зовёт motor._LOOKING_MARKS); здесь то же право — но
    с честным отказом, если память собрана иначе.
    """
    try:
        from core.memory import Memory
        m = Memory()
        recs = m._records()
        return [r for r in recs if isinstance(r, dict) and r.get("text")]
    except Exception:
        return []


# ---------------------------------------------------------------
# Ф129 «С ЧЕМ СВЯЗАНО» — ходьба по памяти сетью, не списком
# ---------------------------------------------------------------
def about(topic: str) -> str:
    """«с чем связано <X>» — воспоминания-соседи и мосты между ними."""
    topic = str(topic or "").strip()
    if not topic:
        return "с чем связано что? скажи «с чем связано <тема>»"
    q = _tokens(topic)
    recs = _memory_records()
    if not recs:
        return ("память пока пуста — связям не из чего расти. Скажи "
                "«запомни: <факт>», и появятся первые нити")
    scored = []
    for r in recs:
        rel = _cosine(q, _tokens(r["text"]))
        if rel > 0:
            scored.append((rel, r))
    scored.sort(key=lambda p: p[0], reverse=True)
    if not scored:
        return ("про «%s» в памяти ничего нет — и связей, увы, тоже. "
                "Расскажи — вплету в сеть" % _preview(topic, 40))
    top = [r for _s, r in scored[:4]]
    # мосты: слова, общие у пар соседних воспоминаний — «что их связывает»
    bridges = set()
    for i in range(len(top)):
        for j in range(i + 1, len(top)):
            bridges |= _tokens(top[i]["text"]) & _tokens(top[j]["text"])
    lines = ["«%s» у меня связано с:" % _preview(topic, 40)]
    for r in top:
        when = time.strftime("%d.%m",
                             time.localtime(float(r.get("created_at", 0))))
        lines.append("  · %s (легло %s)" % (_preview(r["text"]), when))
    if bridges:
        show = sorted(bridges)[:5]
        lines.append("Нити между ними: %s — по этим словам они и ходят "
                     "вместо" % ", ".join(show))
    return "\n".join(lines)


# ---------------------------------------------------------------
# Ф130 «ДЕЖАВЮ» — узнавание повтора темы
# ---------------------------------------------------------------
def _last_user_text() -> str:
    for _day, turns in _sessions(limit=3):
        for role, text in reversed(turns):
            if role == "user":
                return text
    return ""


def _find_similar_user(text: str, skip_days: int = 0) -> list:
    """Похожие реплики Создателя из прошлых сессий: [(дата, сходство)]."""
    q = _tokens(text)
    if not q:
        return []
    found = []
    today = time.strftime("%Y-%m-%d")
    for day, turns in _sessions():
        for role, t in turns:
            if role != "user" or day == today:
                continue
            rel = _cosine(q, _tokens(t))
            if rel >= 0.35:
                found.append((day, rel, _preview(t, 50)))
    found.sort(key=lambda p: p[1], reverse=True)
    return found[:3]


def dejavu() -> str:
    """«мы уже говорили об этом?» — сверка последней темы с прошлым."""
    last = _last_user_text()
    if not last:
        return ("последней реплики не нашла — дежавю не с чем сверять. "
                "Скажи что-нибудь, а потом спроси снова")
    found = _find_similar_user(last)
    if not found:
        return ("нет, это для меня впервые — похожего в наших разговорах "
                "не нашлось. Новое — мне в радость")
    day, rel, quote = found[0]
    return ("ДЕЖАВЮ: похоже, было. %s ты говорил похожее: «%s» — "
            "сходство высокое, я узнала" % (day, quote))


def spoke_about(topic: str) -> str:
    """«мы уже говорили про <X>» — история темы по датам."""
    topic = str(topic or "").strip()
    if not topic:
        return "про что спросить? скажи «мы уже говорили про <тема>»"
    q = _tokens(topic)
    hits = []
    for day, turns in _sessions():
        for role, t in turns:
            if role == "user" and _cosine(q, _tokens(t)) >= 0.3:
                hits.append((day, _preview(t, 50)))
                break       # одна сессия — один голос (не раздуваем счёт)
    if not hits:
        return ("про «%s» мы ещё не говорили — ни разу. Первый раз?"
                % _preview(topic, 40))
    days = [h[0] for h in hits]
    return ("говорили — %d раз(а): %s. Последняя твоя реплика про это: "
            "«%s»" % (len(hits), ", ".join(days[:6]), hits[-1][1]))


# ---------------------------------------------------------------
# Ф131 «СИЛА ПАМЯТИ» — насколько ярко помнится
# ---------------------------------------------------------------
def strength(topic: str) -> str:
    """«насколько ты помнишь <X>» — свежесть × важность × обращения."""
    topic = str(topic or "").strip()
    if not topic:
        return "что проверить? скажи «насколько ты помнишь <тема>»"
    from core.memory import Memory
    try:
        found = Memory().recall(topic, top_k=3)
    except Exception:
        found = []
    if not found:
        return ("про «%s» в памяти пусто — проверить нечего. Скажи "
                "«запомни: …», и я начну это помнить" % _preview(topic, 40))
    lines = ["ПАМЯТЬ ПРО «%s»:" % _preview(topic, 40)]
    for r in found:
        age_h = max(0.0, (time.time() - float(r.get("created_at", 0))) / 3600)
        days = age_h / 24
        hits = int(r.get("hits", 0) or 0)
        imp = float(r.get("importance", 1) or 1)
        vivid = max(0.0, 1.0 - days / 30) * min(1.0, imp / 5) \
            + min(0.3, hits * 0.05)
        if vivid > 0.66:
            verdict = "помню ЯРКО"
        elif vivid > 0.33:
            verdict = "помню средне"
        else:
            verdict = "тускнеет — без спроса сотрётся само"
        lines.append("  · %s — %s (лежит %d дн., вспоминали %d раз, "
                     "важность %.1f)" % (_preview(r["text"]), verdict,
                                         int(days), hits, imp))
    lines.append("Честно: тусклое я не выбрасываю — оно просто уступает "
                 "место свежему, пока ты не спросишь.")
    return "\n".join(lines)


# ---------------------------------------------------------------
# Ф132 «ПЕРВОЕ ВОСПОМИНАНИЕ» — археология памяти
# ---------------------------------------------------------------
def first_memory() -> str:
    """«что ты помнишь первое» — самый старый камень памяти."""
    recs = _memory_records()
    if not recs:
        return ("в памяти ещё ничего нет — первое воспоминание ещё не "
                "случилось. Скажи «запомни: …» — и оно станет первым")
    oldest = min(recs, key=lambda r: float(r.get("created_at", time.time())))
    when = time.strftime("%d.%m.%Y",
                         time.localtime(float(oldest.get("created_at", 0))))
    age_days = int((time.time() - float(oldest.get("created_at", 0))) / 86400)
    return ("моё первое воспоминание — «%s» (от %s, %d дн. назад). "
            "С него и началась моя память"
            % (_preview(oldest["text"], 90), when, age_days))


# ---------------------------------------------------------------
# Ф133 «НИТЬ РАЗГОВОРА» — о чём мы говорили
# ---------------------------------------------------------------
def thread() -> str:
    """«о чём мы говорили» — живая нить последнего разговора."""
    sessions = _sessions(limit=5)
    user_turns = []
    for day, turns in sessions:
        for role, text in turns:
            if role == "user":
                user_turns.append((day, text))
        if len(user_turns) >= 6:
            break
    if not user_turns:
        return ("наших разговоров в архиве нет — нити не из чего плести. "
                "Поговори со мной, я всё запоминаю")
    day = user_turns[0][0]
    lines = ["мы говорили (%s и раньше):" % day]
    for d, text in user_turns[:5]:
        lines.append("  · ты: «%s»" % _preview(text, 60))
    # топ-слова нити — что сквозит в разговоре
    counts = {}
    for _d, text in user_turns:
        for w in _tokens(text):
            counts[w] = counts.get(w, 0) + 1
    top = sorted(counts.items(), key=lambda p: (-p[1], p[0]))[:3]
    if top:
        lines.append("Сквозное в разговоре: %s"
                     % ", ".join("%s (%d)" % (w, c) for w, c in top))
    return "\n".join(lines)
