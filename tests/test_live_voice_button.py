# -*- coding: utf-8 -*-
r"""tests/test_live_voice_button.py — кнопка 89 + сценарий резолюции.

Кнопка 89 — церемония включения живого языка: показывает цифры
вердикта, спрашивает подтверждение и пишет data/live_voice.json.
Сценарий live_voice_resolution.py делает работу; кнопка — интерфейс
Создателя. Проверяем текст кнопки и работу сценария в тестовом доме.
"""
import importlib.util
import json
import sys
from pathlib import Path

import pytest

from core import config

ROOT = Path(__file__).resolve().parents[1]
BAT = ROOT / "scripts" / "89_live_voice.bat"
SCRIPT = ROOT / "scripts" / "live_voice_resolution.py"


def _text() -> str:
    return BAT.read_text(encoding="utf-8")


def _load_script():
    spec = importlib.util.spec_from_file_location("live_voice_resolution", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("MARFA_HOME", str(tmp_path))
    monkeypatch.setattr(config, "HOME_DIR", tmp_path)
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(config, "LIVE_VOICE_FILE",
                        tmp_path / "data" / "live_voice.json")
    config.ensure_dirs()
    yield tmp_path


# ---------- кнопка ----------

def test_button_exists():
    assert BAT.is_file(), "кнопка scripts/89_live_voice.bat пропала"


def test_button_shows_verdict_numbers():
    """Цифры вердикта — в церемонии: Создатель решает, глядя на факты."""
    t = _text()
    assert "13 из 13" in t
    assert "2 из 2" in t


def test_button_asks_confirmation():
    t = _text()
    assert "choice /C 12" in t
    assert "if errorlevel 2" in t            # «Нет» — ничего не меняет


def test_button_runs_resolution_script():
    t = _text()
    assert "live_voice_resolution.py" in t
    assert "pause" in t


def test_button_version_marked():
    assert "BTN_VER 89.1" in _text()


# ---------- сценарий ----------

def test_write_resolution_file(home):
    mod = _load_script()
    rec = mod.write_resolution()
    p = home / "data" / "live_voice.json"
    assert p.exists()
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data["enabled"] is True
    assert "13/13" in data["basis"]          # основание — вердикт батареи
    assert rec == data


def test_main_dead_brain_still_writes_resolution(home, capsys, monkeypatch):
    """Мозг спит — резолюция всё равно записана, выход честный."""
    mod = _load_script()

    class DeadClient:
        def health(self):
            return False

    import core.brain as brain_mod
    monkeypatch.setattr(brain_mod, "BrainClient", DeadClient)
    rc = mod.main([])
    out = capsys.readouterr().out
    assert rc == 0
    assert (home / "data" / "live_voice.json").exists()
    assert "спит" in out
    assert "21:00" in out                    # когда рассказ придёт сам


def test_main_alive_brain_prints_first_voice(home, capsys, monkeypatch):
    mod = _load_script()

    class AliveClient:
        def health(self):
            return True

    import core.brain as brain_mod

    class StoryBrain:
        def health(self):
            return True

        def chat(self, messages, gen_tokens=None, temperature=None,
                 top_p=None):
            return "Сегодня я следила за домом, и дом был цел."

    monkeypatch.setattr(brain_mod, "BrainClient", StoryBrain)
    rc = mod.main([])
    out = capsys.readouterr().out
    assert rc == 0
    assert "следила за домом" in out         # первый рассказ — на экран
    diary = (home / "data" / "diary").exists()
    assert diary or "дневник не собрался" in out


def test_extract_voice_section():
    mod = _load_script()
    text = ("# Дневник Марфы — 2026-11-21\n\n## План дня\nЗадач: 1.\n\n"
            "## Живой рассказ\nДом жил тихо.\n\n*(рассказала сама)*\n\n"
            "## Что хочу завтра\n- спать")
    assert mod._extract_voice(text) == "Дом жил тихо.\n\n*(рассказала сама)*"
