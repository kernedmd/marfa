# -*- coding: utf-8 -*-
r"""tests/test_hands_spec_doc.py — якоря ТЗ «Руки» (моторная кора).

ТЗ описывает найм UI-TARS-7B-DPO: формат действий, бюджет VRAM,
слуга по вызову, надзор стража. Якоря держат решения, а не список
функций: руки не думают, страж обязателен, VRAM-арифметика честна.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs" / "ТЗ_Руки_v1.md"


def _text() -> str:
    return DOC.read_text(encoding="utf-8")


def test_doc_exists():
    assert DOC.is_file(), "docs/ТЗ_Руки_v1.md пропало"


def test_roles_do_not_mix():
    """Главное разделение: мозг не жмёт, руки не думают, глаза не трогают."""
    t = _text()
    assert "Мозг не жмёт кнопки" in t
    assert "Руки не думают" in t
    assert "Глаза не трогают" in t


def test_action_format_is_fixed():
    """Шесть действий — меньше значит проще, мусор = отказ."""
    t = _text()
    for act in ("click(x, y)", "type('текст')", "scroll(direction)",
                "hotkey('ctrl+c')", "wait()", "finished()"):
        assert act in t, "пропало действие: " + act


def test_vram_math_is_honest():
    """Арифметика бюджета: вместе не влезают — руки по вызову."""
    t = _text()
    assert "8.4 ГБ" in t
    assert "НЕ ВЛЕЗАЮТ" in t
    assert "по вызову" in t


def test_mmproj_must_be_same_family():
    """Урок llama.cpp: чужой mmproj = mismatch n_embd, сервер не встанет."""
    t = _text()
    assert "mmproj" in t
    assert "mismatch" in t


def test_guard_is_mandatory():
    """Ни одного действия без стража; whitelist клавиш; секреты — бан."""
    t = _text()
    assert "СТРАЖ" in t
    assert "whitelist" in t.lower() or "Whitelist" in t
    assert "секрет" in t.lower()


def test_pixel_truth_survives():
    """Урок v1.5: состояние экрана проверяют пиксели, не мнение модели."""
    assert "пиксельн" in _text().lower()


def test_reception_stage_zero_measures_dialect():
    """Честность ТЗ: диалект координат не выдуман — измеряется на Р-0."""
    t = _text()
    assert "Р-0" in t
    assert "не выдумывает" in t or "сверяем" in t


def test_frozen_repo_is_recorded():
    """Репозиторий заархивирован — модель заморожена, это записано."""
    t = _text().lower()
    assert "заархивирован" in t
    assert re.search(r"заморожен|заморожена", t)
