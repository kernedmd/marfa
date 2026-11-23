# -*- coding: utf-8 -*-
"""core/password.py — ГЕНЕРАТОР ПАРОЛЕЙ (Ф22, 23.11): «пароль» / «пароль 20».

Источник — secrets (дом не играет в предсказуемость), алфавит без
двусмысленных символов (0/O, 1/l/I — чтобы пароль можно было прочитать
вслух и переписать без слёз). Честность органа: пароль остаётся в
чате и журнале диалога — для по-настоящему важного Создатель меняет
его после использования; дом не притворяется шифровальщиком.
"""
from __future__ import annotations

import secrets

# без 0, O, 1, l, I, |, O — двусмысленные прочь; без пробелов и кавычек
ALPHABET = ("abcdefghjkmnpqrstuvwxyz"
            "ABCDEFGHJKLMNPQRSTUVWXYZ"
            "23456789"
            "!@#$%^&*-_+=")
DEFAULT_LEN = 16
MIN_LEN, MAX_LEN = 8, 64


def generate(n: int = DEFAULT_LEN) -> str:
    """«пароль N» — длина 8..64; абсурд честно ограничивается."""
    try:
        n = int(n)
    except (TypeError, ValueError):
        n = DEFAULT_LEN
    note = ""
    if n < MIN_LEN:
        n, note = MIN_LEN, " (короткое подняла до %d — короче небезопасно)" % MIN_LEN
    elif n > MAX_LEN:
        n, note = MAX_LEN, " (длинное укоротила до %d — длиннее не запомнить)" % MAX_LEN
    pwd = "".join(secrets.choice(ALPHABET) for _ in range(n))
    return "%s%s\n\nЧестно: пароль остался в чате и журнале диалога — " \
           "для важного смени его после использования." % (pwd, note)
