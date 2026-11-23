# -*- coding: utf-8 -*-
"""core/translit.py — ТРАНСЛИТ (Ф24, 23.11): «транслит: Привет» → Privet.

Логины, домены и формы не любят кириллицу — а фраза приходит по-русски.
Таблица — практичная (одна буква → одна/две латинских), регистр
сохраняется («Привет, Марфа» → «Privet, Marfa»), латиница и цифры
проезжают как есть. Обратного перевода нет честно: «zh» может быть и
«ж», и «зх» — угадывать не будем.
"""
from __future__ import annotations

import re

TABLE = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e",
    "ё": "yo", "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k",
    "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r",
    "с": "s", "т": "t", "у": "u", "ф": "f", "х": "kh", "ц": "ts",
    "ч": "ch", "ш": "sh", "щ": "sch", "ъ": "", "ы": "y", "ь": "",
    "э": "e", "ю": "yu", "я": "ya",
}


def translit(text: str) -> str:
    """Кириллица → латиница; регистр и прочие символы сохраняются."""
    out = []
    for ch in str(text or ""):
        low = ch.lower()
        if low in TABLE:
            tr = TABLE[low]
            out.append(tr.capitalize() if ch.isupper() else tr)
        else:
            out.append(ch)
    return "".join(out)


def parse(text: str) -> str:
    """«транслит: <текст>» — ответ; без двоеточия — не команда."""
    m = re.match(r"^транслит\s*[:;]\s*(.+)$", str(text or "").strip(),
                 re.IGNORECASE | re.DOTALL)
    if not m:
        return "что перевести? скажи «транслит: Привет»"
    return translit(m.group(1).strip())
