# -*- coding: utf-8 -*-
"""core/context.py — Ф51 «ИЕРАРХИЧЕСКИЙ КОНТЕКСТ» (ТЗ 3.1, 0.3, ADR-005).

Контекст 8192 — терапия Этапа 2 (§15, 23.11: живой промпт дорос до
4143 ток и сервер молча резал ЯДРО). День-11 «диета» (24.11): бюджет
промпта 5500, история (Ф53) до 1000 ЕДЕТ ПОВЕРХ — отдельными
сообщениями; генерация 768. Закон честен втроём:
5500 + 1000 + 768 = 7268 <= 8192.

Иерархия (при нехватке бюджета режем СНИЗУ ВВЕРХ):
  L0 доктрина        — нерушима, не режется никогда (Раздел 7);
  L1 состояние дома  — время, RAM, квант (короткое, не режется);
  L2 правила генома  — режем целиком с конца, никогда не разрезаем правило;
  L2.5 уроки-законы  — ядерные правила журнала уроков (круг 20, Ф112):
                        свой потолок, те же законы резки, что у L2;
  L3 RAG-воспоминания — режем целиком с конца по слабейшей релевантности;
  L4 история диалога — приходит из core/history.py (Ф53), не более 1000 токенов.

Ф77 «СТАБИЛЬНЫЙ ПРЕФИКС» (день-11): агент собирает здесь ТОЛЬКО
статику (ядро+стройный манифест+законы+доктрина) — сообщение-система
не меняется от хода к ходу, KV-кэш llama-server живёт. Состояние и
RAG (меняются каждый ход) уехали в хвостовой контекст хода
(core/agent._turn_context) — до подвижных частей контекста.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from core import config

# Внутри промпта 6500: история <= 1000, на иерархию остаётся <= 5500
HIERARCHY_BUDGET = config.PROMPT_BUDGET_TOKENS - config.HISTORY_BUDGET_TOKENS


@dataclass
class ContextReport:
    """Прозрачность: что вошло в промпт, что обрезалось (правило 6.6 — логи правды)."""
    prompt_tokens: int = 0
    level_tokens: dict = field(default_factory=dict)
    dropped: list = field(default_factory=list)


def _fit_block(title: str, body: str, remaining: int, report: ContextReport,
               level: str, splittable_lines: Optional[list[str]] = None) -> str:
    """Вписать блок в остаток бюджета. Цельные строки не разрезаем — режем целиком.

    День-11: ПУСТОЕ тело — блока нет вовсе (заголовок без содержания —
    мусор в промпте: Ф77 оставляет состояние пустым в статичной системе).
    """
    header = f"[{title}]"
    if not (body or "").strip() and not splittable_lines:
        return ""
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
                 core: str = "",
                 lessons_rules: Optional[list[str]] = None
                 ) -> tuple[str, ContextReport]:
    """Собрать системный промпт по иерархии с гарантией бюджета (0.3).

    Возвращает (промпт, отчёт). История (Ф53) вписывается первой из остатка —
    у неё свой жёсткий лимит 1000; иерархия занимает остальное.

    H8 аудита: core — статичное нерушимое ядро ДО доктрины (личность,
    манифест, закон скорости): агент сводит свой промпт сюда, и бюджет
    перестаёт быть пожеланием. Ядро не режется никогда; ядро+доктрина
    не влезают в бюджет — ЧП дома (ValueError), а не молчаливое
    переполнение.
    """
    report = ContextReport()
    if budget > config.PROMPT_BUDGET_TOKENS:
        raise ValueError("бюджет промпта выше закона %d — 0.3"
                         % config.PROMPT_BUDGET_TOKENS)

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

    # L2.5: УРОКИ-ЗАКОНЫ (круг 20, Ф112) — ядерные правила журнала
    # уроков: «ошибка -> урок -> правило -> проверка» доезжает до
    # мозга в каждом ходе. Свой потолок (диета: правило — не трактат)
    # поверх остатка; законы резки — как у генома: ЦЕЛЫЕ правила, с
    # конца, никогда не разрезаем (полузакон опаснее отсутствия).
    # Пусто — блока нет вовсе (Ф77: заголовок без содержания — мусор).
    if lessons_rules:
        cap = min(remaining, config.LESSONS_PROMPT_CAP_TOKENS)
        block = _fit_block("УРОКИ-ЗАКОНЫ — из ошибок дома, читаю до действия",
                           "", cap, report, "L2_lessons",
                           splittable_lines=["- " + r for r in lessons_rules])
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
