# -*- coding: utf-8 -*-
"""tests/test_clean_home.py — анти-мусор: скан и перенос наследия v9.3.

Чистильщик грузится по пути (имя файла начинается с цифры быть не должно,
а scripts/ — не пакет), поэтому importlib. Дом подменяется MARFA_HOME
на временную копию — реальный дом не трогается.
"""
import importlib.util
import sys
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "clean_home.py"
_spec = importlib.util.spec_from_file_location("clean_home", _SCRIPT)
ch = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ch)


def _names(moves):
    return {p.name for p in moves}


def _rels(root, moves):
    return {str(p.relative_to(root)).replace("\\", "/") for p in moves}


# ---------- скан корня ----------

def test_scan_finds_root_junk(tmp_path):
    h = tmp_path / "home"
    h.mkdir()
    for n in ["40", "fix.py", "marfa.md", "heal.py", "marfa.zip"]:
        (h / n).write_text("x", encoding="utf-8")
    (h / "Старт_Марфа.bat").write_text("live", encoding="utf-8")
    (h / ".env").write_text("secret", encoding="utf-8")
    (h / "start_marfa.py").write_text("live", encoding="utf-8")
    moves, _reports = ch.scan(h)
    assert {"40", "fix.py", "marfa.md", "heal.py", "marfa.zip"} <= _names(moves)
    assert "Старт_Марфа.bat" not in _names(moves)
    assert ".env" not in _names(moves)
    assert "start_marfa.py" not in _names(moves)


def test_scan_roadmap_conditional(tmp_path):
    """Корневой ROADMAP_30.md уезжает только когда канон приехал в docs/."""
    h = tmp_path / "home"
    h.mkdir()
    (h / "ROADMAP_30.md").write_text("root copy", encoding="utf-8")
    moves, _r = ch.scan(h)
    assert "ROADMAP_30.md" not in _names(moves)      # docs/ копии нет — остаётся
    (h / "docs").mkdir()
    (h / "docs" / "ROADMAP_30.md").write_text("canon", encoding="utf-8")
    moves, _r = ch.scan(h)
    assert "ROADMAP_30.md" in _names(moves)          # канон есть — корень лишний


# ---------- скан по дереву ----------

def test_scan_patterns_inside_code(tmp_path):
    h = tmp_path / "home"
    h.mkdir()
    (h / "core").mkdir()
    (h / "core" / "agent.py").write_text("live", encoding="utf-8")
    (h / "core" / "agent.py.bak").write_text("old", encoding="utf-8")
    (h / "core" / "memory.py.v3_broken").write_text("broken", encoding="utf-8")
    (h / "core" / "__pycache__").mkdir()
    (h / "core" / "__pycache__" / "x.pyc").write_text("pyc", encoding="utf-8")
    moves, _r = ch.scan(h)
    rels = _rels(h, moves)
    assert "core/agent.py.bak" in rels
    assert "core/memory.py.v3_broken" in rels
    assert any("__pycache__" in r for r in rels)
    assert "core/agent.py" not in rels


def test_scan_skips_heavy_dirs(tmp_path):
    h = tmp_path / "home"
    h.mkdir()
    (h / "models").mkdir()
    (h / "models" / "brain.gguf").write_text("m", encoding="utf-8")
    (h / "logs").mkdir()
    (h / "logs" / "x.log").write_text("l", encoding="utf-8")
    moves, _r = ch.scan(h)
    assert moves == []


def test_scan_trivial_dirs(tmp_path):
    """evolution/growth с одними __init__.py — пустышки, уезжают."""
    h = tmp_path / "home"
    h.mkdir()
    (h / "evolution").mkdir()
    (h / "evolution" / "__init__.py").write_text("", encoding="utf-8")
    (h / "growth").mkdir()
    (h / "growth" / "__init__.py").write_text("", encoding="utf-8")
    (h / "safety").mkdir()
    (h / "safety" / "guard.py").write_text("real code", encoding="utf-8")
    moves, _r = ch.scan(h)
    assert {"evolution", "growth"} <= _names(moves)
    assert "safety" not in _names(moves)


# ---------- перенос ----------

def test_apply_moves_and_protects(tmp_path):
    h = tmp_path / "home"
    h.mkdir()
    (h / "models").mkdir()
    (h / "models" / "big.gguf").write_text("m", encoding="utf-8")
    (h / "40").write_text("junk", encoding="utf-8")
    (h / "_backup_heal").mkdir()
    (h / "_backup_heal" / "old.txt").write_text("b", encoding="utf-8")
    moves, _r = ch.scan(h)
    done, errors = ch.apply_moves(h, moves)
    assert not errors and len(done) == len(moves)
    assert not (h / "40").exists()
    assert not (h / "_backup_heal").exists()
    assert (h / "models" / "big.gguf").exists()          # тяжёлое не тронуто
    resurrected = list((h / "_trash").rglob("40"))
    assert resurrected
    assert resurrected[0].read_text(encoding="utf-8") == "junk"


def test_bundle_reported_not_moved(tmp_path):
    """Bundle — история: только доклад, никогда не переносится."""
    h = tmp_path / "home"
    h.mkdir()
    (h / "marfa.bundle").write_bytes(b"BUNDLE")
    (h / "incoming").mkdir()
    (h / "incoming" / "fresh.bundle").write_bytes(b"FRESH")
    moves, reports = ch.scan(h)
    assert "marfa.bundle" not in _names(moves)
    assert any(p.name == "marfa.bundle" for p, _m in reports)
    assert not any(p.parent.name == "incoming" for p, _m in reports)
