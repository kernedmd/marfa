# -*- coding: utf-8 -*-
"""tests/test_eyes_snapshot.py — №4 роадмапа 30: «запомни экран».

Зрительная память дома: снимок PNG + .json-сайдкар (описание, окно,
элементы, размеры) в data\\screenshots\\ + строка в память дома с
тегом «экран». «вспомни экран» находит её обычным recall — экран
становится воспоминанием, а не мгновением. Контракт:

  - один взгляд: снимок и описание из ОДНОГО кадра (эталон №3 —
    тот же байт-в-байт), а не два «посмотри»;
  - PNG настоящий (открывается PIL), сайдкар читается JSON'ом;
  - строка памяти несёт время и описание, тег «экран»;
  - память споткнулась — файлы целы, отказ честен в ответе;
  - глаза не готовы — честный отказ без файлов-пустышек;
  - команда агента «запомни экран» не будит мозг.
"""
import base64
import io
import json
import sys
import time
from pathlib import Path

import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import agent, config, eyes  # noqa: E402


def _png_b64(w=8, h=6, color=(10, 20, 30)) -> str:
    img = Image.new("RGB", (w, h), color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


DESCRIPTOR = {
    "description": "Открыт браузер с документацией",
    "active_window": "Блокнот",
    "elements": [
        {"type": "button", "text": "Пуск", "bbox": [0, 350, 64, 360],
         "confidence": 0.9},
        {"type": "text", "text": "заголовок страницы", "bbox": [10, 10, 300, 40],
         "confidence": 0.8},
    ],
}


class FakeMemory:
    def __init__(self):
        self.rows = []

    def remember(self, text, tags=None, importance=1.0, **kw):
        self.rows.append({"text": text, "tags": tags or [],
                          "importance": importance})

    def recall(self, query, top_k=3):
        return [{"text": r["text"]} for r in self.rows
                if query.lower() in r["text"].lower()][:top_k]


@pytest.fixture()
def seeing(monkeypatch, tmp_path):
    """Глаза видят DESCRIPTOR; снимок — настоящий PNG; дом — tmp_path."""
    monkeypatch.setenv("MARFA_HOME", str(tmp_path))
    monkeypatch.setattr(config, "HOME_DIR", tmp_path)
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(config, "SCREENSHOTS_DIR", tmp_path / "data" / "screenshots")
    b64 = _png_b64()
    monkeypatch.setattr(eyes, "_VISION_ERROR", None)
    monkeypatch.setattr(eyes, "_screenshot_b64",
                        lambda width=eyes.WORK_WIDTH:
                        (b64, (1920, 1080), (1280, 720)))
    monkeypatch.setattr(eyes, "_ask",
                        lambda b64q, prompt, schema, max_tokens=500,
                        timeout=None: (json.dumps(DESCRIPTOR), "schema"))
    yield b64


# ---------- файлы и память ----------

def test_snapshot_creates_png_and_sidecar(seeing, monkeypatch, tmp_path):
    mem = FakeMemory()
    text = eyes.save_snapshot(memory=mem)
    shots = list((tmp_path / "data" / "screenshots").glob("screen_*.png"))
    assert len(shots) == 1, text
    png = shots[0]
    sidecar = png.with_suffix(".json")
    assert sidecar.is_file()
    # PNG настоящий: открывается и имеет размер кадра
    img = Image.open(png)
    assert img.size == (8, 6)
    # сайдкар читается и несёт описание и элементы
    d = json.loads(sidecar.read_text(encoding="utf-8"))
    assert d["description"] == DESCRIPTOR["description"]
    assert d["active_window"] == "Блокнот"
    assert d["elements"] and d["png"] == png.name
    assert d["screen_size"] == [1920, 1080]


def test_snapshot_memory_line_recallable(seeing):
    mem = FakeMemory()
    eyes.save_snapshot(memory=mem)
    assert mem.rows, "строка памяти не легла"
    row = mem.rows[0]
    assert "экран" in row["tags"]
    assert "Открыт браузер" in row["text"] and "читаю" in row["text"]
    # «вспомни экран» находит: recall по слову «экран»
    found = mem.recall("экран")
    assert found and "Открыт браузер" in found[0]["text"]


def test_snapshot_one_glance_consistent(seeing, monkeypatch):
    """Снимок и описание — из ОДНОГО взгляда: PNG байт-в-байт равен кадру,
    что видел дескриптор (эталон №3)."""
    mem = FakeMemory()
    eyes.save_snapshot(memory=mem)
    assert eyes._last_frame["b64"] == seeing   # эталон — тот же кадр


def test_snapshot_same_second_unique_names(seeing, monkeypatch, tmp_path):
    """Два снимка в одну секунду не затирают друг друга (суффикс _1)."""
    mem = FakeMemory()
    eyes.save_snapshot(memory=mem)
    eyes.save_snapshot(memory=mem)
    pngs = list((tmp_path / "data" / "screenshots").glob("screen_*.png"))
    assert len(pngs) == 2
    sidecars = list((tmp_path / "data" / "screenshots").glob("screen_*.json"))
    assert len(sidecars) == 2


def test_snapshot_memory_down_files_alive(seeing):
    """Память споткнулась — файлы целы, отказ честен в ответе."""

    class BrokenMemory:
        def remember(self, *a, **kw):
            raise RuntimeError("chroma упал")

    text = eyes.save_snapshot(memory=BrokenMemory())
    assert "в память не легло" in text
    assert "снимок" in text and "целы" in text


def test_snapshot_no_vision_module_honest(monkeypatch):
    monkeypatch.setattr(eyes, "_VISION_ERROR", "нет модуля зрения: x")
    assert eyes.save_snapshot(memory=None).startswith("глаза не готовы")


def test_snapshot_eyes_error_honest(monkeypatch):
    monkeypatch.setattr(eyes, "_VISION_ERROR", None)
    monkeypatch.setattr(eyes, "describe_with_sizes",
                        lambda width=eyes.WORK_WIDTH:
                        (_ for _ in ()).throw(RuntimeError("сервер молчит")))
    assert "не смогла запомнить" in eyes.save_snapshot(memory=None)


# ---------- команда агента ----------

def test_agent_command_remember_screen(monkeypatch, seeing):
    class FakeBrain:
        calls = 0

        def ask_json(self, *a, **kw):
            self.calls += 1
            return {"answer": "мозг"}

    mem = FakeMemory()
    a = agent.Agent(brain=FakeBrain(), memory=mem)
    for msg in ("запомни экран", "запомни этот экран", "сохрани экран",
                "запомни экран?"):
        r = a.handle(msg)
        assert r.tool_used == "screen_shot", msg
        assert r.source == "python", msg
        assert a.brain.calls == 0, msg
    assert len(mem.rows) == 4                     # каждый раз в память


def test_agent_snapshot_crash_falls_to_brain(monkeypatch):
    """Броня №4 р3: орган упал — чат жив, говорит мозг."""
    class FakeBrain:
        calls = 0

        def ask_json(self, *a, **kw):
            self.calls += 1
            return {"answer": "мозг"}

    class FakeMemory:
        def recall(self, *a, **kw):
            return []

    def boom(memory=None):
        raise RuntimeError("глаза рассыпались")

    monkeypatch.setattr(eyes, "save_snapshot", boom)
    a = agent.Agent(brain=FakeBrain(), memory=FakeMemory())
    r = a.handle("запомни экран")
    assert r.source == "brain" and a.brain.calls == 1
