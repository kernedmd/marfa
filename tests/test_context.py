# -*- coding: utf-8 -*-
"""Тесты Ф51 «иерархический контекст» (ТЗ 3.1, 0.3): бюджет 6500 (терапия §15 — контекст 8192, промпт перестал резаться), иерархия, прозрачность."""
import pytest

from core import config
from core.context import build_system, ContextReport, HIERARCHY_BUDGET

DOCTRINE = "Я — Марфа. Служу Илье. Правила жизни дома: семь правил ТЗ Раздела 6."


def test_constants_law():
    """0.3 + терапия §15: иерархия получает 6500 - 1000 = 5500 токенов промпта."""
    assert HIERARCHY_BUDGET == 5500
    assert config.PROMPT_BUDGET_TOKENS + config.GENERATION_BUDGET_TOKENS <= config.CONTEXT_TOKENS


def test_small_context_fits():
    prompt, rep = build_system(
        doctrine=DOCTRINE,
        state_text="Состояние: 2026-11-12 09:00; RAM 41%; квант Q4_K_M",
        genome_rules=["не коммитить без теста", "откат вместо «починю потом»"],
        rag_memories=["дом живёт в C:\\Marfa", "веб-панель на 5001"],
    )
    assert rep.prompt_tokens <= config.PROMPT_BUDGET_TOKENS
    assert "Марфа" in prompt and "5001" in prompt and "Состояние" in prompt
    assert rep.dropped == []
    assert rep.level_tokens["L0_doctrine"] >= 1


def test_rag_trimmed_first_doctrine_survives():
    """Переполнение: RAG режется с конца, доктрина и состояние нерушимы."""
    many_memories = [f"воспоминание номер {i}: " + "деталь " * 40 for i in range(120)]
    prompt, rep = build_system(
        doctrine=DOCTRINE,
        state_text="Состояние: RAM 41%",
        genome_rules=["правило генома 1"],
        rag_memories=many_memories,
    )
    assert rep.prompt_tokens <= config.PROMPT_BUDGET_TOKENS
    assert DOCTRINE in prompt                      # доктрина выжила
    assert "Состояние: RAM 41%" in prompt          # состояние выжило
    assert "воспоминание номер 0:" in prompt       # сильнейшее вошло
    assert rep.dropped and any("L3_rag" in d for d in rep.dropped)


def test_genome_trimmed_whole_rules():
    """Правила генома режутся ЦЕЛИКОМ с конца — не разрезается само правило."""
    rules = [f"правило {i}: " + "требование " * 30 for i in range(60)]
    prompt, rep = build_system(
        doctrine=DOCTRINE, state_text="Состояние: ок",
        genome_rules=rules, rag_memories=[],
    )
    assert rep.prompt_tokens <= config.PROMPT_BUDGET_TOKENS
    assert "правило 0:" in prompt
    # каждое вошедшее правило целиком
    for line in prompt.splitlines():
        if line.startswith("- правило"):
            assert line.rstrip().endswith("требование требование")


def test_history_inside_own_budget():
    """История (Ф53) вписывается в свои 1000, не отбирает место у доктрины."""
    history = "\n".join(f"Илья: сообщение {i}; Марфа: ответ {i}." for i in range(200))
    prompt, rep = build_system(
        doctrine=DOCTRINE, state_text="RAM 30%", genome_rules=[],
        rag_memories=["что-то важное"], history_text=history,
    )
    assert rep.prompt_tokens <= config.PROMPT_BUDGET_TOKENS
    assert "что-то важное" in prompt  # RAG не выжат историей


def test_oversized_doctrine_is_house_incident():
    """Раздел 7: доктрина нерушима — раздувшуюся не режем, а поднимаем тревогу."""
    huge = "доктрина " * 5000
    with pytest.raises(ValueError):
        build_system(doctrine=huge, state_text="s", genome_rules=[], rag_memories=[])


def test_budget_above_law_rejected():
    """Просить больше 6500 — нарушение 0.3, отказ."""
    with pytest.raises(ValueError):
        build_system(doctrine=DOCTRINE, state_text="s", genome_rules=[], budget=7000)
