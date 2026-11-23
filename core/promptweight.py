# -*- coding: utf-8 -*-
"""core/promptweight.py — Ф43 «ВЕС ПРОМПТА» (день-9, 24.11).

Фронт 1: скорость. Штамп «N с · мозг · N ток · промпт M» уже показывает
диагноз каждого хода, но Создателю нужна ЦЕЛАЯ картина: из чего промпт
состоит и сколько в нём свободно. «вес промпта» собирает её из двух
источников разной честности:

- ЖУРНАЛ МОЗГА (истина): последний ход нёс столько-то ток промпта —
  число от сервера, не оценка;
- РАСКЛАДКА ПО СЛОЯМ (оценка): ядро+манифест+законы, состояние дома,
  воспоминания RAG, история — считаются по тем же функциям, из которых
  агент собирает промпт. Оценка честно подписана «оценка»: токенайзер
  Qwen считает не так, как chars/4, но порядок величин верен.

Лечение читается из ответа: большой промпт = долгий ПРЕФИКС ответа
(мозг пересчитывает его каждый ход без KV-кэша; с Ф42 — один раз).
"""
from __future__ import annotations

import json
from pathlib import Path

from core import config

# эмпирика для русского текста в токенайзерах Qwen: ~3,6-4 симв/ток.
# Честная ОЦЕНКА, не истина — подпись «оценка» в ответе обязательна.
CHARS_PER_TOKEN = 3.8


def _est_tokens(text: str) -> int:
    """Оценка токенов текста (русская речь)."""
    return _est_tokens_from_chars(len(str(text or "")))


def _est_tokens_from_chars(chars: int) -> int:
    """Оценка токенов по ДЛИНЕ текста в символах."""
    return max(1, round(int(chars) / CHARS_PER_TOKEN))


def _last_brain_prompt_tokens() -> int | None:
    """Истина от сервера: prompt_tokens последнего хода из журнала
    мозга. Журнала/строки/поля нет — None (честно, не ноль)."""
    try:
        lines = Path(config.BRAIN_LOG_FILE).read_text(
            encoding="utf-8").splitlines()
    except OSError:
        return None
    for line in reversed(lines):
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if not isinstance(rec, dict):
            continue
        try:
            v = int(rec.get("ptok") or 0)
        except (TypeError, ValueError):
            v = 0
        if v > 0:
            return v
    return None


def _layers() -> list[tuple[str, int]]:
    """Оценка слоёв контекста теми же кусками, что собирает агент
    (день-11, Ф77): СТАТИЧНЫЙ ПРЕФИКС (личность+стройный манифест+
    законы+доктрина — не меняется от хода к ходу, KV-кэш живёт) и
    ПОДВИЖНЫЙ ХВОСТ ХОДА (состояние+RAG — читается заново каждым
    ходом). Каждый слой в своей броне: упавший орган не роняет ответ,
    слой считается пустым (и честно подписывается)."""
    out: list[tuple[str, int]] = []
    try:
        from core import agent as _agent
        from core import identity
        static = _agent.IDENTITY + "\n\n" + identity.manifest_slim() \
            + "\n\n" + _agent.SPEED_LAW + "\n\n" + _agent.TONE_LAW
        out.append(("статичный префикс: личность, стройный манифест, "
                    "законы", len(static)))
    except Exception:
        out.append(("статичный префикс (не собрался — орган спит)", 0))
    try:
        from core import agent as _agent
        out.append(("доктрина Создателя (тоже статична — в префиксе)",
                    len(_agent.load_doctrine())))
    except Exception:
        out.append(("доктрина (не собралась)", 0))
    try:
        from core import agent as _agent
        out.append(("хвост хода: состояние дома (часы, органы) + RAG — "
                    "перечитывается каждым ходом",
                    len(_agent._house_state())))
    except Exception:
        out.append(("хвост хода (не собрался)", 0))
    return out


def render() -> str:
    """«вес промпта» — картина одним ответом: истина журнала + оценка
    слоёв + бюджет + как это лечится."""
    lines = ["ВЕС ПРОМПТА:"]
    real = _last_brain_prompt_tokens()
    if real is not None:
        lines.append("последний ход нёс %d ток промпта — истина от "
                     "сервера (журнал мозга)" % real)
    else:
        lines.append("журнал мозга ещё пуст — ходов к мозгу не было "
                     "(или он ещё не думал); покажу только оценку слоёв")
    layers = _layers()
    total_est = 0
    for name, chars in layers:
        tok = _est_tokens_from_chars(chars)
        total_est += tok
        lines.append("  · %s — ~%d ток (оценка)" % (name, tok))
    lines.append("  · история диалога — до %d ток, отдельными сообщениями "
                 "поверх системы; прошлые дни — выжимкой (Ф79)"
                 % config.HISTORY_BUDGET_TOKENS)
    budget = config.PROMPT_BUDGET_TOKENS
    lines.append("итого ~%d ток из бюджета %d (+ история до %d, + вопрос)"
                 % (total_est, budget, config.HISTORY_BUDGET_TOKENS))
    lines.append("статичный префикс — KV-кэш сервера: платится один раз "
                "за сессию. Перечитывается каждым ходом только хвост: "
                "состояние+RAG+свежие ходы истории — диета дня-11 (Ф77). "
                "Большой хвост = долгий ПРЕФИКС ответа.")
    return "\n".join(lines)
