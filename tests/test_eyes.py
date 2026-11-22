# -*- coding: utf-8 -*-
"""tests/test_eyes.py — Г-2/Г-2.1: глаза дома в агенте (8083, только чтение).

Глаза — сенсор: _screenshot_b64 / _camera_b64 / _post_chat / health /
_VISION_ERROR — швы, тесты подменяют их, реальный сервер, камера и экран
не нужны. Агентный маршрут «посмотри» не будит мозг; граница слова
обязательна («посмотрим» — не команда). Г-2.1: мозг узнаёт о глазах из
состояния дома (health_cached, без пинга в каждом сообщении).

v2 (22.11, урок живого прогона «один пустой элемент [64,32,412,58]»):
промпт-антипопугай (модель СПИСАЛА пример из промпта — больше примеру
нечего списывать), описание первой строкой, цепочка грамматик
schema → json_object → raw, камера — второй источник зрения.
"""
import json as _json
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import agent, eyes  # noqa: E402

DESCRIPTOR = {
    "description": "Открыт браузер с чатом и проводник с моделями",
    "active_window": "Командная строка",
    "elements": [
        {"type": "text", "text": "C:\\Marfa>", "bbox": [64, 32, 412, 58],
         "confidence": 0.9},
        {"type": "button", "text": "Пуск", "bbox": [0, 1048, 48, 1096],
         "confidence": 0.9},
    ],
    "summary": "рабочий стол с окнами",
}

OLD_DESCRIPTOR = {          # без description — как отвечал сенсор до v2
    "active_window": "Командная строка",
    "elements": DESCRIPTOR["elements"],
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


# ---------- _ask: цепочка грамматик schema → json_object → raw ----------

def test_ask_schema_accepted(monkeypatch):
    seen = []

    def fake_post(body):
        seen.append(body.get("response_format", {}).get("type"))
        return {"choices": [{"message": {"content": "ок"}}]}

    monkeypatch.setattr(eyes, "_post_chat", fake_post)
    out, grammar = eyes._ask("b64", "промпт", {"type": "object"}, 10)
    assert out == "ок" and grammar == "schema" and seen == ["json_schema"]


def test_ask_json_object_second_chance(monkeypatch):
    """Сервер отверг строгую схему, но знает простую «только JSON» —
    модель скована грамматикой и не rambling до лимита токенов."""
    seen = []

    def fake_post(body):
        fmt = body.get("response_format", {}).get("type")
        seen.append(fmt)
        if fmt == "json_schema":
            raise RuntimeError("400")
        return {"choices": [{"message": {"content": '{"found": true}'}}]}

    monkeypatch.setattr(eyes, "_post_chat", fake_post)
    out, grammar = eyes._ask("b64", "промпт", {"type": "object"}, 10)
    assert out == '{"found": true}' and grammar == "json_object"
    assert seen == ["json_schema", "json_object"]


def test_ask_all_attempts_dead(monkeypatch):
    def boom(body):
        raise RuntimeError("timeout")

    monkeypatch.setattr(eyes, "_post_chat", boom)
    with pytest.raises(RuntimeError):
        eyes._ask("b64", "промпт", {"type": "object"}, 10)


def test_ask_budget_bounds_rambling():
    """Урок 132 секунд: бюджет генерации подрезан — 800, не 1500."""
    import inspect
    sig = inspect.signature(eyes._ask)
    assert sig.parameters["max_tokens"].default == 800


# ---------- промпт-антипопугай (урок живого прогона 22.11) ----------

def test_prompt_has_no_parrotable_example():
    """Живые глаза списали bbox [64,32,412,58] из примера промпта.
    Теперь пример — шуточно-фейковые [11,22,33,44] + прямой запрет."""
    assert "[64,32,412,58]" not in eyes.PROMPT
    assert "[11,22,33,44]" in eyes.PROMPT
    assert "НЕ копируй" in eyes.PROMPT


def test_prompt_demands_reading_text():
    """Главное требование v2: ЧИТАТЬ надписи — элемент без текста бесполезен."""
    assert "ЧИТАЙ" in eyes.PROMPT
    assert "description" in eyes.SCHEMA["properties"]


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
    assert "Вижу: " in text                     # описание первой строкой
    assert "браузер" in text                    # человеческое описание
    assert "Командная строка" in text
    assert "Пуск" in text
    assert "button" in text
    assert "глаза думали" in text


def test_describe_text_old_answer_still_readable(monkeypatch):
    """Сенсор без description (старый диалект) — сводка встаёт первой
    строкой, элементы на месте: совместимость без падения."""
    _fake_sees(monkeypatch, _json.dumps(OLD_DESCRIPTOR, ensure_ascii=False))
    text = eyes.describe_text()
    assert text.startswith("Вижу: рабочий стол")
    assert "Пуск" in text and "глаза думали" in text


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


# ---------- камера: второй источник зрения ----------

def _fake_camera(monkeypatch, content):
    monkeypatch.setattr(eyes, "_VISION_ERROR", None)
    monkeypatch.setattr(eyes, "health", lambda: True)
    monkeypatch.setattr(eyes, "_camera_b64", lambda width=960: "b64cam")
    monkeypatch.setattr(eyes, "_post_chat",
                        lambda body: {"choices": [{"message":
                                                   {"content": content}}]})


def test_camera_describes_human(monkeypatch):
    _fake_camera(monkeypatch, _json.dumps({
        "description": "Перед камерой мужчина в свитере, смотрит в экран",
        "objects": [{"name": "человек", "bbox": [1, 2, 3, 4],
                     "confidence": 0.9}]}, ensure_ascii=False))
    text = eyes.describe_camera_text()
    assert text.startswith("Вижу в камере:")
    assert "мужчина" in text and "камера думала" in text


def test_camera_honest_when_empty(monkeypatch):
    _fake_camera(monkeypatch, '{"description": ""}')
    assert "пусто" in eyes.describe_camera_text()


def test_camera_no_opencv_honest(monkeypatch):
    monkeypatch.setattr(eyes, "_VISION_ERROR", None)
    monkeypatch.setattr(eyes, "health", lambda: True)

    def no_cv2(width=960):
        raise RuntimeError("нет модуля камеры: No module named 'cv2' "
                           "(venv\\Scripts\\pip install opencv-python)")

    monkeypatch.setattr(eyes, "_camera_b64", no_cv2)
    text = eyes.describe_camera_text()
    assert "камера не смогла" in text
    assert "opencv-python" in text          # Создателю — что ставить


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


def test_agent_chto_ty_vidish_is_command(monkeypatch):
    """Урок 22.11: Создатель спрашивает «что ты видишь?» — это и есть
    команда глазам, а не повод отвечать «дай команду посмотри»."""
    a = _agent(monkeypatch, "Вижу")
    for msg in ("что ты видишь", "Что ты видишь?",
                "что видишь", "что ты видишь сейчас"):
        r = a.handle(msg)
        assert r.tool_used == "eyes", msg
        assert a.brain.calls == 0, msg


def test_agent_camera_command(monkeypatch):
    """«Посмотри в камеру» / «посмотри на меня» — камера, не экран:
    ветка камеры обязана стоять ДО экранной (начинается с «посмотри »)."""
    a = _agent(monkeypatch, "Вижу экран")
    monkeypatch.setattr(eyes, "describe_camera_text",
                        lambda: "Вижу в камере: мужчина")
    for msg in ("посмотри в камеру", "включи камеру", "кто в камере",
                "посмотри на меня"):
        r = a.handle(msg)
        assert r.tool_used == "camera", msg
        assert a.brain.calls == 0, msg


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
