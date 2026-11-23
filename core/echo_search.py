# -*- coding: utf-8 -*-
"""core/echo_search.py — «ЧТО Я ГОВОРИЛ» (Ф32, 23.11): поиск по репликам Создателя.

«Что я говорил про ключи?» — вопрос о СВОИХ словах, не о памяти Марфы:
RAG помнит смыслами, а тут — дословный поиск по ходам Создателя во
всех сессиях. Находки — с датой и именем сессии; много — честное
«и ещё N». «что я говорил» без «про» — подсказка, не угадывание.
"""
from __future__ import annotations

from core.dialog import DialogStore

CAP = 5


def search(query: str) -> str:
    """«что я говорил про X» — цитаты реплик Создателя с датой."""
    q = str(query or "").strip().lower()
    if not q:
        return "что искать? скажи «что я говорил про ключи»"
    store = DialogStore()
    hits: list[tuple[str, str, str]] = []      # (ts, session, text)
    total = 0
    for sid in store.sessions():
        for t in store.turns(sid):
            if t.get("role") != "user":
                continue
            text = str(t.get("text") or "")
            if q in text.lower():
                total += 1
                if len(hits) < CAP:
                    hits.append((str(t.get("ts") or ""), sid,
                                 text.strip()[:160]))
    if not hits:
        return ("в наших разговорах слова «%s» от тебя не слышала — "
                "может, говорила я? вспомни: «вспомни %s»" % (q, q))
    lines = ["ТЫ ГОВОРИЛ:"]
    for ts, sid, text in hits:
        lines.append("- [%s] %s" % (ts or "без даты", text))
    if total > CAP:
        lines.append("… и ещё %d" % (total - CAP))
    return "\n".join(lines)
