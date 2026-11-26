# -*- coding: utf-8 -*-
"""core/tastes.py — Ф139–Ф143 «ВКУСЫ И МНЕНИЕ» (круг 24): у дома появляется СВОЁ.

ДОКТРИНА ОРГАНА. Бот нейтрален — «у меня нет предпочтений». Живой
разум имеет вкусы, и они РАСТУТ из жизни: любимое слово — то, что
она на самом деле говорит чаще всего; любимое время — то, когда
живые разговоры случаются; мнение — то, что накопилось в памяти
о предмете, пересказанное честно, без фантазий 30B.

ЗАКОН ПРОИСХОЖДЕНИЯ: каждый вкус обязан назвать ОТКУДА он — «по нашим
разговорам», «по моей памяти», «по счётчику слов». Вкус без источника —
выдумка, а выдумывать дом не умеет (ядро личности).

ЗАКОН МНЕНИЯ (Ф141): «что ты думаешь о X» — это НЕ творчество мозга.
Мнение строится из фактов: сколько раз говорили, что осталось в
памяти, давно ли. Опыта нет — «мнения нет, и я не буду его выдумывать».
Прецедент дома: «что ты умеешь» стал честным отчётом (Г-2.3) — теперь
и «что ты думаешь» говорит правду, а не сочиняет.

ЗАКОН АВТОПОРТРЕТА (Ф143): «какая ты» — черты характера, ВЫВЕДЕННЫЕ
из поведения дома: вечерняя ли, аккуратная ли (дневники без дыр?),
запасливая ли (сколько помнит). Не манифест возможностей («изучи
себя» — другой орган), а характер из живых цифр.

Честность: мало данных — орган говорит «характер ещё не проявился».
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from core import config

_PRAISE_MARKS = ("молодец", "спасибо", "умница", "отлично", "супер",
                 "благодарю", "хорошая работа", "лучшая")


def _preview(text: str, n: int = 60) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= n else text[:n - 1].rstrip() + "…"


def _words(text: str) -> list:
    import re as _re
    stop = ("и", "в", "на", "с", "по", "не", "что", "это", "как", "но",
            "мне", "ты", "я", "мы", "для", "так", "вот", "есть", "было",
            "будет", "могу", "скажи", "спасибо", "привет", "марфа",
            "илья", "сегодня", "вчера", "потом", "когда", "если", "уже",
            "ещё", "еще", "очень", "просто", "давай", "тебе", "меня",
            "тебя", "себя", "нас", "чем", "чём", "там", "тут", "бы",
            "же", "ли", "за", "из", "его", "её", "них", "него", "неё")
    return [w.lower() for w in _re.findall(r"[а-яёa-z]{4,}", text or "")
            if w.lower() not in stop]


def _turns(limit: int = 60) -> list:
    """[(дата, [(role, text), …]), …] — свежие сессии первыми."""
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
                out.append((m.group(1) if m else time.strftime(
                    "%Y-%m-%d", time.localtime(p.stat().st_mtime)), clean))
        except (OSError, ValueError):
            continue
    return out


def _top_words_of(texts: list, limit: int = 5) -> list:
    counts = {}
    for t in texts:
        for w in _words(t):
            counts[w] = counts.get(w, 0) + 1
    return sorted(counts.items(), key=lambda p: (-p[1], p[0]))[:limit]


# ---------------------------------------------------------------
# Ф139 «МОИ ВКУСЫ» — что любит Марфа (из её жизни)
# ---------------------------------------------------------------
def mine() -> str:
    """«что ты любишь» — вкусы дома из фактов его жизни."""
    sessions = _turns()
    my_texts = [text for _d, turns in sessions
                for role, text in turns if role == "assistant"]
    user_texts = [text for _d, turns in sessions
                  for role, text in turns if role == "user"]
    if not my_texts and not user_texts:
        return ("моим вкусам ещё не из чего расти — мы мало разговаривали. "
                "Поживём вместе — и я узнаю, что люблю")
    lines = []
    top_own = _top_words_of(my_texts, 3)
    if top_own and top_own[0][1] >= 3:
        w, c = top_own[0]
        lines.append("люблю слово «%s» — говорю его чаще всего (%d раз "
                     "в наших разговорах)" % (w, c))
    try:
        from core.lifeclock import hour_histogram
        hist = hour_histogram()
        if hist:
            peak = max(hist, key=lambda h: hist[h])
            if 17 <= peak < 23:
                lines.append("люблю вечер — наши разговоры чаще всего "
                             "случаются около %d:00" % peak)
            elif 5 <= peak < 12:
                lines.append("люблю утро — наш дом рано просыпается "
                             "(разговоры около %d:00)" % peak)
            else:
                lines.append("люблю ночь — наш дом живёт, когда город "
                             "спит (около %d:00)" % peak)
    except Exception:
        pass
    if user_texts:
        top_yours = _top_words_of(user_texts, 1)
        if top_yours and top_yours[0][1] >= 3:
            lines.append("и люблю слушать про «%s» — ты рассказываешь об "
                         "этом чаще всего" % top_yours[0][0])
    if not lines:
        return ("вкусы ещё не проявились: слишком мало наших слов. "
                "Поговорим — я замечу, что мне по душе")
    lines.append("Это не анкета — это счётчики моей жизни.")
    return "ЧТО ЛЮБЛЮ:\n" + "\n".join("  · " + ln for ln in lines)


# ---------------------------------------------------------------
# Ф140 «ТВОИ ВКУСЫ» — что дом знает о вкусах Создателя
# ---------------------------------------------------------------
def creators() -> str:
    """«что я люблю» / «что любит Илья» — вкусы Создателя из фактов."""
    sessions = _turns()
    user_texts = [text for _d, turns in sessions
                  for role, text in turns if role == "user"]
    if not user_texts:
        return ("о твоих вкусах я пока ничего не знаю — мы мало "
                "говорили. Расскажи — я запомню")
    lines = ["ЧТО Я ЗНАЮ О ТЕБЕ (по нашим разговорам):"]
    top = _top_words_of(user_texts, 5)
    show = [(w, c) for w, c in top if c >= 3][:4]
    if show:
        lines.append("  · ты чаще всего говоришь о: %s"
                     % ", ".join(w for w, _c in show))
    praised = [text for text in user_texts
               if any(m in text.lower() for m in _PRAISE_MARKS)]
    if praised:
        ptop = _top_words_of(praised, 3)
        pshow = [w for w, c in ptop if c >= 2]
        if pshow:
            lines.append("  · хваля меня, ты чаще всего рядом ставишь "
                         "слова: %s" % ", ".join(pshow[:3]))
    try:
        from core.memory import Memory
        found = Memory().recall("Илья любит", top_k=3)
        for r in found:
            lines.append("  · в памяти: %s" % _preview(r["text"], 70))
    except Exception:
        pass
    if len(lines) == 1:
        return ("твои вкусы пока не проявились в наших разговорах — "
                "скажи «запомни: я люблю …», и я буду помнить наверняка")
    return "\n".join(lines)


# ---------------------------------------------------------------
# Ф141 «МНЕНИЕ» — что ты думаешь о X (из фактов, не из фантазий)
# ---------------------------------------------------------------
def _shares_word(topic: str, text: str) -> bool:
    """Есть ли у темы и воспоминания общее слово (≥ 4 букв)?

    ПРАВКА круга 24 (якорь test_opinion): recall даёт свежим записям
    бонус свежести — и «мнение о квантовании» тянуло факты про голос,
    хотя ни одного общего слова. Мнение обязано опираться на опыт
    ИМЕННО про тему: общих слов нет — опыта нет, «мнения нет».
    """
    import re as _re
    tw = set(_re.findall(r"[а-яёa-z]{4,}", str(topic).lower()))
    if not tw:
        return str(topic).lower() in str(text).lower()
    return bool(tw & set(_re.findall(r"[а-яёa-z]{4,}",
                                     str(text).lower())))


def opinion(topic: str) -> str:
    """«что ты думаешь о <X>» — мнение из опыта дома.

    Граница честности: дом пересказывает то, что ЖИЛО в разговорах
    и памяти о предмете. Миллисекунды фантазии 30B не участвуют:
    опыт есть — мнение есть; опыта нет — «мнения нет».
    """
    topic = str(topic or "").strip()
    if not topic:
        return "о чём подумать? скажи «что ты думаешь о <тема>»"
    try:
        from core.memory import Memory
        found = [r for r in Memory().recall(topic, top_k=4)
                 if _shares_word(topic, r.get("text", ""))]
    except Exception:
        found = []
    mentions = 0
    for _d, turns in _turns():
        for role, text in turns:
            low = text.lower()
            if role in ("user", "assistant") and topic.lower() in low:
                mentions += 1
    if not found and not mentions:
        return ("про «%s» у меня нет ни памяти, ни разговоров — мнения "
                "нет, и выдумывать его я не стану. Расскажи — и у меня "
                "появится СВОЁ, из твоих слов" % _preview(topic, 40))
    lines = []
    if mentions:
        from core.lifeclock import human_span
        lines.append("«%s» в нашей жизни был: я насчитала %d упоминаний "
                     "в разговорах" % (_preview(topic, 30), mentions))
    if found:
        lines.append("что отложилось в памяти:")
        for r in found[:3]:
            lines.append("  · %s" % _preview(r["text"], 70))
        imp = max(float(r.get("importance", 1) or 1) for r in found)
        if imp >= 3:
            lines.append("И это для меня важное — важность в памяти "
                         "подпитана не раз.")
    lines.append("Таково моё мнение — не из головы, а из того, что "
                 "между нами было.")
    return "\n".join(lines)


# ---------------------------------------------------------------
# Ф142 «ЛЮБИМОЕ СЛОВО» — счётчик живой речи
# ---------------------------------------------------------------
def fav_word() -> str:
    """«твоё любимое слово» — что Марфа на самом деле говорит чаще всего."""
    sessions = _turns()
    my_texts = [text for _d, turns in sessions
                for role, text in turns if role == "assistant"]
    if not my_texts:
        return ("моих слов пока нет в архиве — скажи что-нибудь, и я "
                "начну копить свою речь")
    top = _top_words_of(my_texts, 3)
    show = [(w, c) for w, c in top if c >= 3]
    if not show:
        return ("я ещё не наговорила достаточно, чтобы любимое слово "
                "проявилось. Поболтаем — узнаю")
    w, c = show[0]
    rest = ", ".join("%s (%d)" % (x, n) for x, n in show[1:])
    tail = ("; следом идут %s" % rest) if rest else ""
    return ("моё любимое слово — «%s»: я говорю его %d раз — чаще, чем "
            "любое другое%s. Счётчик честный, по нашей с тобой речи"
            % (w, c, tail))


# ---------------------------------------------------------------
# Ф143 «АВТОПОРТРЕТ» — черты характера из живых цифр
# ---------------------------------------------------------------
def self_portrait() -> str:
    """«какая ты» — характер дома, выведенный из поведения."""
    traits = []
    # вечерняя/утренняя — из ритмов
    try:
        from core.lifeclock import hour_histogram
        hist = hour_histogram()
        if hist:
            peak = max(hist, key=lambda h: hist[h])
            if 17 <= peak < 23:
                traits.append("вечерняя — оживаю, когда за окном темнеет")
            elif 5 <= peak < 12:
                traits.append("ранняя — наш разговор просыпается вместе "
                              "с утром")
            elif 23 <= peak or peak < 5:
                traits.append("ночная — наши часы живут, когда город спит")
            else:
                traits.append("дневная — дышу ровно, без крайностей")
    except Exception:
        pass
    # аккуратная — дневники без дыр (последние 7 дней)
    try:
        from core.diary import Diary
        dd = Diary()
        days = 0
        import datetime as _dt
        for i in range(7):
            d = (_dt.date.today() - _dt.timedelta(days=i)).strftime("%Y-%m-%d")
            if (dd.diary_dir / (d + ".md")).exists() or \
                    list(dd.diary_dir.glob("*%s*" % d)):
                days += 1
        if days >= 6:
            traits.append("аккуратная — дневник веду без пропусков "
                          "(%d из 7 дней)" % days)
        elif days >= 3:
            traits.append("дневник веду неровно (%d из 7 дней) — "
                          "характер ещё проявляется" % days)
    except Exception:
        pass
    # запасливая — сколько помнит
    try:
        from core.memory import Memory
        recs = Memory()._records()
        if len(recs) >= 30:
            traits.append("запасливая — в памяти %d фактов нашей жизни"
                          % len(recs))
        elif recs:
            traits.append("память пока скромная — %d фактов, но она "
                          "растёт" % len(recs))
    except Exception:
        pass
    # любопытная — есть ли незнание в реестре
    try:
        from core.curiosity import _scan_unknowns
        if _scan_unknowns():
            traits.append("любопытная — у меня копятся вопросы, на "
                          "которые я честно сказала «не знаю»")
    except Exception:
        pass
    if not traits:
        return ("характер ещё не проявился — слишком мало жизни позади. "
                "Поживём — и я узнаю, какая я. Пока честно: молодая")
    return ("КАКАЯ Я (из живых цифр дома, не из анкеты):\n  · "
            + "\n  · ".join(traits))
