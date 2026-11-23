# -*- coding: utf-8 -*-
"""Тесты цитаты из прочитанного (Ф9, 23.11)."""
from pathlib import Path

import pytest

from core import config, quote
from core.memory import Memory


@pytest.fixture()
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("MARFA_HOME", str(tmp_path))
    monkeypatch.setattr(config, "HOME_DIR", tmp_path)
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    yield tmp_path


def _mem(home):
    return Memory(data_dir=Path(config.DATA_DIR))


def test_no_library_is_honest(home):
    """Полка пуста — честная подсказка «почитай», не выдумка Конфуция."""
    text = quote.quote(memory=_mem(home))
    assert "нечего цитировать" in text and "почитай" in text


def test_quote_from_read_books(home):
    """Цитата — только из прочитанного, источник назван."""
    mem = _mem(home)
    mem.remember("Глава про стремление: Марфа хочет знать больше.",
                 tags=["библиотека", "доктрина"], importance=2.5)
    mem.remember("Обычное воспоминание без тега библиотеки",
                 tags=["ответ"], importance=1.0)
    for _ in range(10):
        text = quote.quote(memory=mem)
        assert "Глава про стремление" in text
        assert "доктрина" in text              # источник назван
        assert "Обычное воспоминание" not in text   # только полка


def test_long_quote_trimmed_at_word(home):
    mem = _mem(home)
    long_text = ("слово " * 200).strip()
    mem.remember(long_text, tags=["библиотека", "большая книга"],
                 importance=2.5)
    text = quote.quote(memory=mem)
    assert len(text) < 800                      # обрезано по-человечески
    assert text.endswith("…")


def test_dead_memory_is_honest(home):
    class Boom:
        def recent(self, *a, **kw):
            raise RuntimeError("база спит")

    text = quote.quote(memory=Boom())
    assert "нечего цитировать" in text          # честный ноль, не крах
