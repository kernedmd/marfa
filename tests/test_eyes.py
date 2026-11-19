# -*- coding: utf-8 -*-
"""tests/test_eyes.py — Г-2/Г-2.1: глаза дома в агенте (8083, только чтение).

Глаза — сенсор: _screenshot_b64 / _post_chat / health / _VISION_ERROR —
швы, тесты подменяют их, реальный сервер и экран не нужны. Агентный маршрут
«посмотри» не будит мозг; граница слова обязательна («посмотрим» — не команда).
Г-2.1: мозг узнаёт о глазах из состояния дома (health_cached, без пинга
в каждом сообщении).
"""
import json as _json
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import agent, eyes  # noqa: E402

DESCRIPTOR = {
    "active_window": "Командная строка",
    "elements": [
        {"type": "text", "text": "C:\\Marfa>", "bbox": [64, 32, 412, 58],
         "confidence": 0.9},
        {"type": "button", "text": "Пуск", "bbox": [0, 1048, 48, 1096],
         "confidence": 0.9},
    ],
    "summary": "рабочий стол с окнами",
}


def _fake_sees(monkeypatch, content):
    """Глаза «видят»: экран и сервер подменены, ответ — content."""
    monkeypatch.setattr(eyes, "_VISION_ERROR", None)
    monkeypatch.setattr(eyes, "_screenshot_b64",
                        lambda width=eyes.WORK_WIDTH:
                        ("b64", (1920, 1080), (1280, 720)))
    monkeypatch.setattr(eyes, "health", lambda: True)
    monkeypatch.setattr(eyes, "_post_chat",
                        lambda body: {"choices": [{"message":
                                                   {"content": content}}]})


# ---------- парсер сенсора ----------

def test_parse_json_plain():
    assert eyes.parse_json('{"a": 1}') == {"a": 1}


def test_parse_json_fenced():
    assert eyes.parse_json('```json\n{"a": 1}\n```') == {"a": 1}


def test_parse_json_text_and_tail():
    dirty = 'Вот ответ: {"a": {"b": 2}} и хвост'
    assert eyes.parse_json(dirty) == {"a": {"b": 2}}


def test_parse_json_garbage_raises():
    with pytest.raises(ValueError):
        eyes.parse_json("тут нет json")


# ---------- _ask: грамматика и фолбэк ----------

def test_ask_schema_accepted(monkeypatch):
    seen = []

    def fake_post(body):
        seen.append("response_format" in body)
        return {"choices": [{"message": {"content": "ок"}}]}

    monkeypatch.setattr(eyes, "_post_chat", fake_post)
    out, ok = eyes._ask("b64", "промпт", {"type": "object"}, 10)
    assert out == "ок" and ok is True and seen == [True]


def test_ask_schema_fallback(monkeypatch):
    """Сервер не знает грамматики (или упал) — повтор без неё."""
    seen = []

    def fake_post(body):
        seen.append("response_format" in body)
        if body.get("response_format"):
            raise RuntimeError("400")
        return {"choices": [{"message": {"content": '{"found": true}'}}]}

    monkeypatch.setattr(eyes, "_post_chat", fake_post)
    out, ok = eyes._ask("b64", "промпт", {"type": "object"}, 10)
    assert out == '{"found": true}' and ok is False and seen == [True, False]


def test_ask_all_attempts_dead(monkeypatch):
    def boom(body):
        raise RuntimeError("timeout")

    monkeypatch.setattr(eyes, "_post_chat", boom)
    with pytest.raises(RuntimeError):
        eyes._ask("b64", "промпт", {"type": "object"}, 10)


# ---------- describe / describe_text ----------

def test_describe_ok(monkeypatch):
    _fake_sees(monkeypatch, _json.dumps(DESCRIPTOR, ensure_ascii=False))
    d = eyes.describe()
    assert d["active_window"] == "Командная строка"
    assert d["elements"][1]["type"] == "button"


def test_describe_fenced_answer(monkeypatch):
    _fake_sees(monkeypatch,
               "```json\n" + _json.dumps(DESCRIPTOR, ensure_ascii=False) + "\n```")
    assert eyes.describe()["summary"] == "рабочий стол с окнами"


def test_describe_text_readable(monkeypatch):
    _fake_sees(monkeypatch, _json.dumps(DESCRIPTOR, ensure_ascii=False))
    text = eyes.describe_text()
    assert "Командная строка" in text
    assert "Пуск" in text
    assert "button" in text
    assert "рабочий стол" in text
    assert "глаза думали" in text


def test_describe_text_eyes_down(monkeypatch):
    monkeypatch.setattr(eyes, "_VISION_ERROR", None)
    monkeypatch.setattr(eyes, "health", lambda: False)
    text = eyes.describe_text()
    assert "8083" in text and "не отвечают" in text


def test_describe_text_server_error(monkeypatch):
    monkeypatch.setattr(eyes, "_VISION_ERROR", None)
    monkeypatch.setattr(eyes, "health", lambda: True)

    def boom(body):
        raise RuntimeError("timeout")

    monkeypatch.setattr(eyes, "_post_chat", boom)
    text = eyes.describe_text()
    assert "глаза ошиблись" in text


def test_describe_text_no_module(monkeypatch):
    monkeypatch.setattr(eyes, "_VISION_ERROR", "нет модуля mss")
    text = eyes.describe_text()
    assert "глаза не готовы" in text


def test_describe_text_without_elements(monkeypatch):
    _fake_sees(monkeypatch, '{"summary": "пусто"}')
    text = eyes.describe_text()
    assert "без списка элементов" in text


# ---------- агентный маршрут «посмотри» ----------

class FakeBrain:
    def __init__(self):
        self.calls = 0

    def ask_json(self, *a, **k):
        self.calls += 1
        return {"answer": "ок"}


class FakeMemory:
    def remember(self, text):
        pass

    def recall(self, query, top_k=3):
        return []


def _agent(monkeypatch, seen_text):
    monkeypatch.setattr(eyes, "describe_text",
                        lambda width=eyes.WORK_WIDTH: seen_text)
    return agent.Agent(brain=FakeBrain(), memory=FakeMemory())


def test_agent_posmotri(monkeypatch):
    a = _agent(monkeypatch, "Вижу экран, 2 элементов:")
    r = a.handle("посмотри")
    assert r.source == "python" and r.tool_used == "eyes"
    assert r.text.startswith("Вижу")
    assert a.brain.calls == 0          # мозг молчит


def test_agent_posmotri_variants(monkeypatch):
    a = _agent(monkeypatch, "Вижу")
    for msg in ("посмотри на экран", "Посмотри, что там",
                "что на экране", "опиши экран"):
        assert a.handle(msg).tool_used == "eyes", msg


def test_agent_word_boundary(monkeypatch):
    """«посмотрим» и «не смотри» — не команды глазам, идём к мозгу."""
    a = _agent(monkeypatch, "Вижу")
    for msg in ("посмотрим, как дела", "не смотри туда"):
        r = a.handle(msg)
        assert r.tool_used != "eyes", msg
        assert a.brain.calls == 1
        a.brain.calls = 0


def test_agent_eyes_down_still_fast(monkeypatch):
    """Глаза не отвечают — честный текст, мозг всё равно не будим."""
    a = _agent(monkeypatch, "глаза 8083 не отвечают — сервер зрения не запущен?")
    r = a.handle("что на экране")
    assert r.tool_used == "eyes" and "не отвечают" in r.text
    assert a.brain.calls == 0


# ---------- Г-2.1: мозг знает о глазах ----------

def test_health_cached(monkeypatch):
    """Кэш: второй вызов за период не пингует порт."""
    monkeypatch.setattr(eyes, "_health_cache", (False, 0.0))
    calls = []
    monkeypatch.setattr(eyes, "health", lambda: (calls.append(1) or True))
    assert eyes.health_cached() is True
    assert eyes.health_cached() is True          # из кэша, без пинга
    assert len(calls) == 1


def test_health_cached_expires(monkeypatch):
    """Через период кэш устаревает — снова пинг."""
    monkeypatch.setattr(eyes, "_health_cache", (True, time.time() - 31.0))
    monkeypatch.setattr(eyes, "health", lambda: False)
    assert eyes.health_cached() is False


def test_house_state_tells_brain_about_eyes(monkeypatch):
    """Мозг читает состояние дома — и знает про глаза и «посмотри»."""
    monkeypatch.setattr(eyes, "health_cached", lambda period=30.0: True)
    s = agent._house_state()
    assert "8083" in s and "посмотри" in s and "жив" in s


def test_house_state_eyes_down(monkeypatch):
    monkeypatch.setattr(eyes, "health_cached", lambda period=30.0: False)
    s = agent._house_state()
    assert "не запущен" in s and "зрения сейчас нет" in s
