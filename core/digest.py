# -*- coding: utf-8 -*-
"""core/digest.py — «ЧТО НОВОГО» (Ф4, 23.11): дайджест жизни дома за отсутствие.

Урок живого лога: Создатель возвращается — «разговор продолжается» и
одна «Поняла». А дом ЖИЛ: думал в тишине, спал и видел сны, читал
книги, копил воспоминания. Дайджест собирает всё, что случилось с
последнего разговора, из первых рук — каждый орган в своей броне
(закон №10 р3): упавший орган — честная строка «не ответил», отчёт жив.
"""
from __future__ import annotations

import datetime as dt
from typing import Optional

from core.greet import _plural_hours


def _since_ts(dialog, now: dt.datetime) -> Optional[dt.datetime]:
    if dialog is None:
        return None
    try:
        return dialog.last_user_activity()
    except Exception:
        return None


def _line_thoughts() -> Optional[str]:
    """Свежая фоновая мысль (организм думал в тишине)."""
    try:
        from core import musing
        fresh = musing.render_last()
        if fresh:
            return "думала: " + fresh.replace("\n", " ")[:300]
    except Exception:
        return None
    return None


def _line_dream() -> Optional[str]:
    """Последний сон — если спала, снилось."""
    try:
        from core import musing
        got = musing.last_dream()
        if got:
            return "снилось: " + str(got[1]).replace("\n", " ")[:300]
    except Exception:
        return None
    return None


def _line_memories(memory, since: Optional[dt.datetime]) -> Optional[str]:
    """Новые воспоминания с последнего разговора."""
    if memory is None or since is None:
        return None
    try:
        recs = memory.recent(since.timestamp(), limit=3)
        if not recs:
            return None
        texts = [str(r.get("text", ""))[:90] for r in recs if r.get("text")]
        if not texts:
            return None
        head = "запомнила новое" if len(texts) == 1 \
            else "запомнила нового: %d записи" % len(texts)
        return head + ": " + "; ".join(texts)
    except Exception:
        return None


def _line_questions() -> Optional[str]:
    """Открытые вопросы — организм хочет знать."""
    try:
        from core.questions import QuestionBank
        items = QuestionBank().open_items()
        if items:
            return ("хотела спросить: %s (ответь: «ответ <номер>: ...»)"
                    % str(items[0]["text"])[:160])
    except Exception:
        return None
    return None


def what_is_new(dialog=None, memory=None,
                now: Optional[dt.datetime] = None) -> str:
    """«что нового»: жизнь дома с последнего разговора Создателя.

    Отсутствие честно (нет истории — «мы ещё не разговаривали»);
    каждый орган — в своей броне; тишина всех органов — тоже честный
    ответ («всё было тихо, я просто работала»), а не выдумка дел.
    """
    now = now or dt.datetime.now()
    since = _since_ts(dialog, now)
    lines = []
    if since is None:
        lines.append("Мы ещё не разговаривали — всё, что расскажу, из "
                     "самой первой встречи.")
    else:
        mins = (now - since).total_seconds() / 60.0
        if mins >= 60:
            lines.append("Пока тебя не было (%s):" % _plural_hours(int(mins / 60)))
        else:
            lines.append("Только что разговаривали — вот что успело случиться:")

    got_any = False
    for line in (_line_thoughts(), _line_dream(),
                 _line_memories(memory, since), _line_questions()):
        if line:
            lines.append("- " + line)
            got_any = True
    if not got_any:
        lines.append("- всё было тихо: я просто работала и ждала тебя. "
                     "«подумай» — подумаю сейчас, «почитай» — прочту новое.")
    return "\n".join(lines)
