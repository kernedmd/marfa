# -*- coding: utf-8 -*-
"""tests/test_web_eyes.py — №14 роадмапа 30: «кнопка глаз».

Снимок экрана по клику: превью + описание + время ответа. Контракт:

  - /api/eyes отдаёт {ok, description, preview, secs} одним JSON;
  - превью — настоящее маленькое JPEG (data:image/jpeg;base64,
    ширина ≤ 480 — картинка для Создателя, не для сенсора);
  - описание — живая проза, JSON-привычка сенсора достаётся
    description;
  - взгляд кнопки — тоже взгляд: кадр становится эталоном «что
    изменилось» (№3);
  - глаза мертвы/нет модуля/пустой ответ — 200 с ok=False и
    честной причиной: кнопка показывает правду, а не 500-ю;
  - на странице чата есть кнопка и JS-функция look(); описание
    экранируется esc() — сенсор тоже недоверенный источник текста.

Швы: _screenshot_b64 / _ask / health_cached / _VISION_ERROR.
"""
import base64
import io
import json
import sys
from pathlib import Path

import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import config, eyes  # noqa: E402
from web.app import app  # noqa: E402


@pytest.fixture()
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("MARFA_HOME", str(tmp_path))
    monkeypatch.setattr(config, "HOME_DIR", tmp_path)
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(config, "LOGS_DIR", tmp_path / "logs")
    monkeypatch.setattr(config, "GUARD_LOG_FILE",
                        tmp_path / "logs" / "guard_log.jsonl")
    config.ensure_dirs()
    yield tmp_path


@pytest.fixture()
def client(home, monkeypatch):
    app.config["TESTING"] = True
    return app.test_client()


def _png_b64(w=64, h=48) -> str:
    img = Image.new("RGB", (w, h), (90, 120, 150))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


def _see(monkeypatch, prose):
    monkeypatch.setattr(eyes, "_VISION_ERROR", None)
    monkeypatch.setattr(eyes, "health_cached", lambda period=30.0: True)
    monkeypatch.setattr(eyes, "_screenshot_b64",
                        lambda width=eyes.WORK_WIDTH:
                        (_png_b64(), (1920, 1080), (1280, 720)))
    monkeypatch.setattr(eyes, "_ask",
                        lambda b64, prompt, schema, max_tokens=400,
                        timeout=None: (prose, None))
    monkeypatch.setattr(eyes, "_last_frame", {})


# ---------- орган: взгляд с превью ----------

def test_glance_ok_structure(monkeypatch):
    _see(monkeypatch, "Открыт браузер с документацией дома")
    d = eyes.glance_with_preview()
    assert d["ok"] is True
    assert d["description"] == "Открыт браузер с документацией дома"
    assert d["secs"] >= 0
    assert d["preview"].startswith("data:image/jpeg;base64,")
    # превью — настоящее JPEG и маленькое
    raw = base64.b64decode(d["preview"].split(",", 1)[1])
    img = Image.open(io.BytesIO(raw))
    assert img.format == "JPEG"
    assert img.width <= eyes.GLANCE_PREVIEW_WIDTH


def test_glance_is_also_reference(monkeypatch):
    """Взгляд кнопки — тоже взгляд: эталон «что изменилось» обновился."""
    _see(monkeypatch, "рабочий стол")
    eyes.glance_with_preview()
    assert eyes._last_frame["b64"]                    # кадр запомнен


def test_glance_json_habit_falls_back(monkeypatch):
    """Сенсор по привычке ушёл в JSON — чату нужна суть, не сырьё."""
    _see(monkeypatch, '{"description": "открыт редактор кода"}')
    d = eyes.glance_with_preview()
    assert d["ok"] is True and d["description"] == "открыт редактор кода"


def test_glance_eyes_down_honest(monkeypatch):
    monkeypatch.setattr(eyes, "_VISION_ERROR", None)
    monkeypatch.setattr(eyes, "health_cached", lambda period=30.0: False)
    d = eyes.glance_with_preview()
    assert d["ok"] is False and "не отвечает" in d["error"]


def test_glance_no_module_honest(monkeypatch):
    monkeypatch.setattr(eyes, "_VISION_ERROR", "нет модуля зрения: x")
    d = eyes.glance_with_preview()
    assert d["ok"] is False and "не готовы" in d["error"]


def test_glance_empty_answer_honest(monkeypatch):
    _see(monkeypatch, "   ")
    d = eyes.glance_with_preview()
    assert d["ok"] is False and "пусто" in d["error"]


# ---------- маршрут панели ----------

def test_api_eyes_route_ok(client, monkeypatch):
    monkeypatch.setattr(eyes, "glance_with_preview",
                        lambda preview_width=eyes.GLANCE_PREVIEW_WIDTH: {
                            "ok": True, "description": "браузер открыт",
                            "preview": "data:image/jpeg;base64,AAA",
                            "secs": 9.1})
    r = client.get("/api/eyes")
    assert r.status_code == 200
    d = r.get_json()
    assert d["ok"] is True and d["description"] == "браузер открыт"
    assert d["preview"].startswith("data:image/jpeg;base64,")
    assert d["secs"] == 9.1


def test_api_eyes_route_down_is_200(client, monkeypatch):
    """Глаза мертвы — не 500-я, а 200 с честной причиной: кнопка
    показывает правду, красная страница — для поломок панели."""
    monkeypatch.setattr(eyes, "glance_with_preview",
                        lambda preview_width=eyes.GLANCE_PREVIEW_WIDTH: {
                            "ok": False, "error": "сенсор не отвечает"})
    r = client.get("/api/eyes")
    assert r.status_code == 200
    assert r.get_json()["ok"] is False


def test_api_eyes_route_crash_is_honest(client, monkeypatch):
    """Даже орган упал с исключением — маршрут не роняет панель."""
    def boom(preview_width=eyes.GLANCE_PREVIEW_WIDTH):
        raise RuntimeError("взорвалось")

    monkeypatch.setattr(eyes, "glance_with_preview", boom)
    r = client.get("/api/eyes")
    assert r.status_code == 200
    assert r.get_json()["ok"] is False


# ---------- страница чата ----------

def test_chat_page_has_eye_button(client):
    html = client.get("/chat").data.decode("utf-8")
    assert 'id="eye"' in html and "look()" in html
    assert "/api/eyes" in html
    # XSS-гигиена: описание сенсора проходит через esc()
    assert "esc(d.description)" in html
