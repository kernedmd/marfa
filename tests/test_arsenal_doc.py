# -*- coding: utf-8 -*-
r"""tests/test_arsenal_doc.py — якоря описи арсенала моделей.

Инвентаризация C:\Marfa\models от Создателя (21.11). Документ — не
список файлов, а решения: кто в строю, кто кандидат, кто спит и почему.
Якоря держат главное: мозг не меняется, мост ушей стал возможен,
модели входят в дом по одному.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs" / "АРСЕНАЛ_МОДЕЛЕЙ.md"


def _text() -> str:
    return DOC.read_text(encoding="utf-8")


def test_doc_exists():
    assert DOC.is_file(), "опись docs/АРСЕНАЛ_МОДЕЛЕЙ.md пропала"


def test_brain_is_not_replaced():
    """Главное решение: мозг остаётся Qwen3-30B-Q4_K_M (вердикт 21.11)."""
    t = _text()
    assert "Qwen3-30B-A3B-Q4_K_M" in t
    assert "вердикт" in t.lower()
    assert "не меняется" in t


def test_in_service_named():
    """Пятеро работающих названы поимённо."""
    t = _text()
    for name in ("vosk-model-small-ru-0.22",   # уши-сторож
                 "Qwen2.5-VL-3B-Instruct",      # глаза
                 "Qwen2.5-3B-Instruct"):        # студент
        assert name in t


def test_whisper_bridge_is_the_prize():
    """Находка дня: whisper large-v3-turbo уже в чулане — мост ушей
    из «планов» стал делом за кодом."""
    t = _text()
    assert "large-v3-turbo" in t
    assert "мост" in t.lower()


def test_one_at_a_time_discipline():
    """Правило арсенала: по одному, найм = фишка по карте с тестом."""
    t = _text().lower()
    assert "по одному" in t
    assert "зелёный тест" in t or "зеленый тест" in t


def test_mysteries_are_honest():
    """Неопознанное честно названо неопознанным, а не выдумано."""
    import re
    flat = re.sub(r"\s+", " ", _text().lower())
    assert "не опознана" in flat
    assert "опознать" in flat
