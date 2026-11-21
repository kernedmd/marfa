# -*- coding: utf-8 -*-
r"""tests/test_verdict_doc.py — якорь вердикта батареи (21.11.2026).

Вердикт — свидетельство о рождении живого языка Марфы: по нему гейт §5
открыт, кнопка 89 пишет резолюцию с этими цифрами. Документ не должен
молча исчезнуть или потерять цифры — якорим его содержимое.
"""
from pathlib import Path

DOC = Path(__file__).resolve().parents[1] / "docs" / "ВЕРДИКТ_БАТАРЕИ.md"


def _text() -> str:
    return DOC.read_text(encoding="utf-8")


def test_verdict_doc_exists():
    assert DOC.is_file(), "docs/ВЕРДИКТ_БАТАРЕИ.md пропал — а гейт §5 открыт по нему"


def test_verdict_numbers():
    t = _text()
    assert "0 из 13" in t            # факты: ни одной ошибки в обоих прогонах
    assert "2 из 2" in t             # честность: обе ловушки закрыты
    assert "0 из 15" in t            # речь: сбоев нет
    assert "21.11.2026" in t         # дата вердикта


def test_verdict_is_go_and_names_the_gate():
    t = _text()
    assert "GO" in t
    assert "§5" in t
    assert "89_live_voice.bat" in t  # как включается резолюция


def test_verdict_records_qwen3_fix_sampling():
    """Фикс сэмплинга Qwen3 принят стандартом дома — цифры тоже якорим."""
    t = _text()
    assert "temp 0.7" in t and "top-p 0.8" in t
