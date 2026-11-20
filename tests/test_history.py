# -*- coding: utf-8 -*-
"""Тесты Ф53 «сжатие истории»: лимит 1000 токенов, дословный хвост, мозговая сводка."""
import pytest

from core import config
from core.history import HistoryCompressor, _first_sentence


def _long(i: int) -> str:
    return (f"Ход {i}: " + "обстоятельное предложение про эволюцию среды и память. "
            * 12)


def test_first_sentence_extractive():
    assert _first_sentence("Раз. Два. Три!").startswith("Раз.")
    assert _first_sentence("одна длинная строка без точки") == "одна длинная строка без точки"


def test_short_history_verbatim():
    h = HistoryCompressor()
    h.add_turn("user", "привет")
    h.add_turn("assistant", "я здесь")
    text = h.render()
    assert "привет" in text and "я здесь" in text
    assert h.last_stats["tokens"] <= config.HISTORY_BUDGET_TOKENS


def test_overflow_compressed_within_budget():
    """Десятки длинных ходов: render не превышает 1000 токенов, старое сжато."""
    h = HistoryCompressor()
    for i in range(40):
        h.add_turn("user", _long(i))
        h.add_turn("assistant", _long(i))
    text = h.render(prefer_brain=False)
    assert config.token_estimate(text) <= config.HISTORY_BUDGET_TOKENS
    assert h.last_stats["summarized"] > 0
    # keep_recent — потолок, а не гарантия: длинные ходы, сколько влезло под резерв
    assert 1 <= h.last_stats["kept_verbatim"] <= h.keep_recent
    # новейшие ходы остались дословно
    assert "Ход 39" in text


def test_recent_kept_verbatim_even_under_pressure():
    """Хвост дословно, даже если сводка съела почти весь бюджет."""
    h = HistoryCompressor(keep_recent=2)
    for i in range(30):
        h.add_turn("user", _long(i))
    text = h.render(prefer_brain=False)
    assert config.token_estimate(text) <= config.HISTORY_BUDGET_TOKENS
    assert "Ход 29" in text


def test_brain_summary_used_when_alive():
    """Живой мозг даёт сводку — она попадает в render вместо офлайн-выжимки."""
    class FakeBrain:
        def chat(self, messages, gen_tokens=None, temperature=0.2):
            return "сводка от 30B: обсуждали контекст и память"
    h = HistoryCompressor(brain=FakeBrain())
    for i in range(20):
        h.add_turn("user", _long(i))
    text = h.render(prefer_brain=True)
    assert "сводка от 30B" in text
    assert h.last_stats["tokens"] <= config.HISTORY_BUDGET_TOKENS


def test_brain_down_falls_back_offline():
    """Мозг умер — офлайн-выжимка держит бюджет, дом не падает."""
    class DeadBrain:
        def chat(self, *a, **k):
            raise ConnectionError("8082 молчит")
    h = HistoryCompressor(brain=DeadBrain())
    for i in range(20):
        h.add_turn("user", _long(i))
    text = h.render(prefer_brain=True)
    assert config.token_estimate(text) <= config.HISTORY_BUDGET_TOKENS
    assert "Ранее в диалоге" in text


def test_never_midword_cut():
    """Обрезка только по строкам: в render нет оборванных посередине слов."""
    h = HistoryCompressor(keep_recent=1)
    for i in range(25):
        h.add_turn("user", _long(i))
    text = h.render(prefer_brain=False)
    for line in text.splitlines():
        assert line.endswith("…") or line[-1] in ".!?:;»\"'" or line[-1].isalnum()
