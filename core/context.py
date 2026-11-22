# -*- coding: utf-8 -*-
"""core/context.py — Ф51 «ИЕРАРХИЧЕСКИЙ КОНТЕКСТ» (ТЗ 3.1, 0.3, ADR-005).

Контекст 4096 — закон, больше нельзя. Бюджет промпта 3072, внутри него
сжатая история (Ф53) не более 1000, генерация 768 (3072+768 <= 4096).

Иерархия (при нехватке бюджета режем СНИЗУ ВВЕРХ):
  L0 доктрина        — нерушима, не режется никогда (Раздел 7);
  L1 состояние дома  — время, RAM, квант (короткое, не режется);
  L2 правила генома  — режем целиком с конца, никогда не разрезаем правило;
  L3 RAG-воспоминания — режем целиком с конца по слабейшей релевантности;
  L4 история диалога — приходит из core/history.py (Ф53), не более 1000 токенов.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from core import config

# Внутри промпта 3072: история <= 1000, на иерархию остаётся <= 2072
HIERARCHY_BUDGET = config.PROMPT_BUDGET_TOKENS - config.HISTORY_BUDGET_TOKENS


@dataclass
class ContextReport:
    """Прозрачность: что вошло в промпт, что обрезалось (правило 6.6 — логи правды)."""
    prompt_tokens: int = 0
    level_tokens: dict = field(default_factory=dict)
    dropped: list = field(default_factory=list)


def _fit_block(title: str, body: str, remaining: int, report: ContextReport,
               level: str, splittable_lines: Optional[list[str]] = None) -> str:
    """Вписать блок в остаток бюджета. Цельные строки не разрезаем — режем целиком."""
    header = f"[{title}]"
    if splittable_lines is None:
        need = config.token_estimate(header + "\n" + body)
        if need <= remaining:
            report.level_tokens[level] = report.level_tokens.get(level, 0) + need
            return header + "\n" + body + "\n"
        report.dropped.append(f"{level}: блок {need} ток > остатка {remaining}")
        return ""

    kept, need_total = [], config.token_estimate(header)
    for line in splittable_lines:
        need = config.token_estimate(line) + 1
        if need_total + need > remaining:
            report.dropped.append(f"{level}: отброшено {len(splittable_lines) - len(kept)} строк")
            break
        kept.append(line)
        need_total += need
    if not kept:
        report.dropped.append(f"{level}: ничего не влезло")
        return ""
    report.level_tokens[level] = report.level_tokens.get(level, 0) + need_total
    return header + "\n" + "\n".join(kept) + "\n"


def build_system(doctrine: str, state_text: str, genome_rules: list[str],
                 rag_memories: Optional[list[str]] = None,
                 history_text: str = "",
                 budget: int = config.PROMPT_BUDGET_TOKENS,
                 core: str = "") -> tuple[str, ContextReport]:
    """Собрать системный промпт по иерархии с гарантией бюджета (0.3).

    Возвращает (промпт, отчёт). История (Ф53) вписывается первой из остатка —
    у неё свой жёсткий лимит 1000; иерархия занимает остальное.

    H8 аудита: core — статичное нерушимое ядро ДО доктрины (личность,
    манифест, закон скорости): агент сводит свой промпт сюда, и бюджет
    3072 перестаёт быть пожеланием. Ядро не режется никогда; ядро+доктрина
    не влезают в бюджет — ЧП дома (ValueError), а не молчаливое переполнение.
    """
    report = ContextReport()
    if budget > config.PROMPT_BUDGET_TOKENS:
        raise ValueError("бюджет промпта выше закона 3072 — 0.3")

    # L0: доктрина нерушима (Раздел 7). Слишком длинная доктрина — ЧП дома.
    core = (core or "").strip()
    c_tok = config.token_estimate(core)
    d_tok = config.token_estimate(doctrine)
    if d_tok > HIERARCHY_BUDGET // 2:
        raise ValueError(f"доктрина раздулась до {d_tok} ток — нарушение Раздела 7, чинить руками Ильи")
    l0 = ((core + "\n\n" + doctrine.strip()) if core else doctrine.strip())
    l0_tok = c_tok + d_tok + (1 if core else 0)
    # Ф53-резерв: история заказана — её 1000 неприкосновенны, ядро+доктрина
    # обязаны влезть БЕЗ них
    reserve = config.HISTORY_BUDGET_TOKENS if history_text else 0
    if l0_tok > budget - reserve:
        raise ValueError(
            f"ядро+доктрина {l0_tok} ток не влезают в бюджет {budget} "
            f"(минус {reserve} на историю) — ЧП дома, чинить руками Ильи")
    if core:
        report.level_tokens["L0_core"] = c_tok
    report.level_tokens["L0_doctrine"] = d_tok
    parts = [l0]
    used = l0_tok

    remaining = budget - used
    # L1: состояние (короткое)
    block = _fit_block("СОСТОЯНИЕ ДОМА", state_text, remaining, report, "L1_state")
    used += config.token_estimate(block)
    parts.append(block)
    remaining = budget - used

    # L2: геном — целиком правило, режем с конца
    block = _fit_block("ПРАВИЛА ГЕНОМА", "", remaining, report, "L2_genome",
                       splittable_lines=["- " + r for r in genome_rules])
    used += config.token_estimate(block)
    parts.append(block)
    remaining = budget - used

    # L3: RAG — целиком воспоминание, режем с конца (слабейшие внизу списка)
    block = _fit_block("ПАМЯТЬ (RAG)", "", remaining, report, "L3_rag",
                       splittable_lines=["- " + m for m in (rag_memories or [])])
    used += config.token_estimate(block)
    parts.append(block)
    remaining = budget - used

    # L4: сжатая история Ф53 — свой лимит, иначе последняя.
    # K1 аудита: блок ВЫЧИСЛЯЛСЯ, считался в used и level_tokens — но не
    # ложился в parts. Отчёт говорил «история включена», а её не было.
    if history_text:
        h_budget = min(config.HISTORY_BUDGET_TOKENS, remaining)
        block = _fit_block("ИСТОРИЯ", history_text, h_budget, report, "L4_history")
        used += config.token_estimate(block)
        parts.append(block)

    prompt = "\n".join(p for p in parts if p)
    report.prompt_tokens = config.token_estimate(prompt)
    if report.prompt_tokens > budget:
        raise ValueError(f"промпт {report.prompt_tokens} ток превысил бюджет {budget} — баг сборки")
    return prompt, report
