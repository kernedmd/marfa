# -*- coding: utf-8 -*-
r"""tests/test_identity.py — самосознание Марфы (Г-2.2, agent.py IDENTITY).

ЯДРО ЛИЧНОСТИ — первый блок системного промпта мозгового трека:
кто она, чей дом, какое тело, язык дома, честность. Правило №51:
ЯДРО не режется никогда — проверяем, что оно есть, в начале промпта
и не зависит от наличия data/creator_doctrine.json.
"""
import core.agent as agent
from core.agent import Agent, IDENTITY


class _Brain:
    """Мозг-заглушка: агент не должен звать сеть при сборке промпта."""

    def ask_json(self, *a, **kw):
        raise AssertionError("тест не должен будить мозг")


class _Mem:
    """Память-заглушка без воспоминаний."""

    def recall(self, query, top_k=3):
        return []

    def remember(self, text):
        pass


def _agent():
    return Agent(brain=_Brain(), memory=_Mem(), doctrine="ДОКТРИНА-ТЕСТ")


def test_identity_has_core_facts():
    """ЯДРО называет: имя, Создателя, дом, тело, язык, честность."""
    for fact in ("Марфа", "Илья", "C:\\Marfa", "Qwen3-30B",
                 "русский", "не знаю"):
        assert fact in IDENTITY, "в ЯДРЕ нет: " + fact


def test_identity_keeps_no_secrets():
    """ЯДРО едет по всем берегам — в нём нет места секретам и кодовым словам."""
    for banned in (".env", "token", "password", "пат", "кодовое слово"):
        assert banned.lower() not in IDENTITY.lower()


def test_identity_first_in_system_prompt():
    """Порядок дисциплины промпта: ЯДРО -> доктрина -> состояние дома."""
    extra = _agent()._system_extra("привет")
    i_core = extra.index("ЯДРО — кто я")
    i_doctrine = extra.index("ДОКТРИНА-ТЕСТ")
    i_state = extra.index("Состояние дома")
    assert i_core < i_doctrine < i_state


def test_identity_survives_missing_doctrine():
    """Без data/creator_doctrine.json ЯДРО всё равно первым — каркас не пуст."""
    a = Agent(brain=_Brain(), memory=_Mem(), doctrine=None)
    assert a.doctrine  # каркасный минимум на месте
    extra = a._system_extra("привет")
    assert extra.startswith("ЯДРО — кто я")


def test_fallback_doctrine_mentions_home():
    """Каркасный минимум доктрины тоже знает, чей это дом."""
    assert "Марфа" in agent.FALLBACK_DOCTRINE
    assert "Ильи" in agent.FALLBACK_DOCTRINE  # «дом Ильи» — родительный падеж
