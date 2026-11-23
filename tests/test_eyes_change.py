# -*- coding: utf-8 -*-
"""tests/test_eyes_change.py — №3 роадмапа 30: «что изменилось».

Пиксельная сверка двух кадров (урок v1.5: истину говорят пиксели,
не мнение сенсора). Контракт:

  - каждый взгляд («посмотри», «найди», дескриптор для рук)
    запоминает кадр-эталон;
  - «что изменилось» снимает свежий кадр и сверяет ПОПИКСЕЛЬНО:
    порог 5% — «заметно/несущественно», ГДЕ изменилось — сетка 3×3
    по-человечески («правый верх», «центр»);
  - сравнились — свежий кадр становится новым эталоном;
  - эталона нет — честная подсказка, а не выдумка «ничего не менялось»;
  - сервер зрения НЕ нужен (чистые пиксели), а модуля зрения нет —
    честный отказ;
  - команда агента «что изменилось» не будит мозг.

Швы: _screenshot_b64 / _last_frame / _VISION_ERROR.
"""
import base64
import io
import sys
import time
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import agent, eyes  # noqa: E402


def _png_b64(img: Image.Image) -> str:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


def _white(w=120, h=80) -> Image.Image:
    return Image.new("RGB", (w, h), (240, 240, 240))


def _with_square(w=120, h=80, box=(30, 20, 90, 60), color=(0, 0, 0)):
    img = _white(w, h)
    for y in range(box[1], box[3]):
        for x in range(box[0], box[2]):
            img.putpixel((x, y), color)
    return img


def _see_frames(monkeypatch, fresh_b64, width=120):
    """Свежий снимок экрана — fresh_b64 (снимок и есть: пиксели)."""
    monkeypatch.setattr(eyes, "_VISION_ERROR", None)
    monkeypatch.setattr(eyes, "_screenshot_b64",
                        lambda w=eyes.WORK_WIDTH:
                        (fresh_b64, (1920, 1080), (w, int(w * 0.6666))))


def _agent(monkeypatch, answer):
    class FakeBrain:
        calls = 0

        def ask_json(self, *a, **kw):
            self.calls += 1
            return {"answer": "мозг"}

    class FakeMemory:
        def recall(self, *a, **kw):
            return []

    monkeypatch.setattr(eyes, "whats_changed_text", lambda: answer)
    return agent.Agent(brain=FakeBrain(), memory=FakeMemory())


# ---------- эталон и честные отказы ----------

def test_no_reference_honest_hint(monkeypatch):
    monkeypatch.setattr(eyes, "_last_frame", {})
    monkeypatch.setattr(eyes, "_VISION_ERROR", None)
    text = eyes.whats_changed_text()
    assert "не запоминала" in text and "посмотри" in text


def test_no_vision_module_honest(monkeypatch):
    monkeypatch.setattr(eyes, "_VISION_ERROR", "нет модуля зрения: x")
    assert "глаза не готовы" in eyes.whats_changed_text()


def test_glance_remembers_frame(monkeypatch):
    """«посмотри» = новый эталон: кадр и время запоминаются."""
    monkeypatch.setattr(eyes, "_last_frame", {})
    monkeypatch.setattr(eyes, "_VISION_ERROR", None)
    monkeypatch.setattr(eyes, "health", lambda: True)
    monkeypatch.setattr(eyes, "_ask",
                        lambda b64, prompt, schema, max_tokens=400,
                        timeout=None: ("экран с окном", None))
    monkeypatch.setattr(eyes, "_screenshot_b64",
                        lambda width=eyes.WORK_WIDTH:
                        ("ETHALON", (1920, 1080), (1280, 720)))
    eyes.describe_text()
    assert eyes._last_frame["b64"] == "ETHALON"
    assert eyes._last_frame["size"] == (1280, 720)
    assert time.time() - eyes._last_frame["ts"] < 5


def test_find_also_remembers_frame(monkeypatch):
    """Поиск — тоже взгляд: его кадр становится эталоном."""
    monkeypatch.setattr(eyes, "_last_frame", {})
    monkeypatch.setattr(eyes, "_VISION_ERROR", None)
    content = ('{"elements": [{"type": "button", "text": "Пуск", '
               '"bbox": [10, 10, 20, 20], "confidence": 0.9}]}')
    monkeypatch.setattr(eyes, "health", lambda: True)
    monkeypatch.setattr(eyes, "_screenshot_b64",
                        lambda width=eyes.WORK_WIDTH:
                        ("FIND-B64", (1920, 1080), (1280, 720)))
    monkeypatch.setattr(eyes, "_ask",
                        lambda b64, prompt, schema, max_tokens=500,
                        timeout=None: (content, "schema"))
    monkeypatch.setattr(eyes, "_zone_b64",
                        lambda b64, box, width=eyes.WORK_WIDTH:
                        ("zone", (width, width // 2)))
    eyes.find_on_screen("Пуск")
    assert eyes._last_frame["b64"] == "FIND-B64"


# ---------- сверка ----------

def test_changed_above_threshold(monkeypatch):
    """25% кадра стало чёрным — «изменился заметно», процент честный,
    место названо по-человечески (квадрат 60×40 из 120×80 = 25%)."""
    old = _png_b64(_white())
    new = _png_b64(_with_square(box=(30, 20, 90, 60)))
    _see_frames(monkeypatch, new)
    monkeypatch.setattr(eyes, "_last_frame",
                        {"b64": old, "size": (120, 80),
                         "ts": time.time() - 600})
    text = eyes.whats_changed_text()
    assert "изменился заметно" in text
    assert "25.0%" in text
    assert "центр" in text                     # где — по сетке 3×3
    assert "10 мин" in text                    # возраст эталона честен


def test_changed_below_threshold(monkeypatch):
    """0,1% кадра — ниже порога 5%: «существенных изменений нет»,
    но процент виден — не ноль и не выдумка."""
    old = _png_b64(_white())
    new = _png_b64(_with_square(box=(0, 0, 4, 3)))
    _see_frames(monkeypatch, new)
    monkeypatch.setattr(eyes, "_last_frame",
                        {"b64": old, "size": (120, 80),
                         "ts": time.time() - 30})
    text = eyes.whats_changed_text()
    assert "существенных изменений нет" in text
    assert "30 с" in text


def test_where_named_by_grid(monkeypatch):
    """Чёрный квадрат в правом верхнем углу — место названо."""
    old = _png_b64(_white())
    new = _png_b64(_with_square(box=(96, 0, 120, 26)))
    _see_frames(monkeypatch, new)
    monkeypatch.setattr(eyes, "_last_frame",
                        {"b64": old, "size": (120, 80),
                         "ts": time.time() - 5})
    text = eyes.whats_changed_text()
    assert "правый верх" in text


def test_fresh_frame_becomes_reference(monkeypatch):
    """Сверка обновляет эталон: второй вопрос «что изменилось» сравнит
    уже со свежим кадром — старая правда не застревает."""
    old = _png_b64(_white())
    new = _png_b64(_with_square(box=(30, 20, 90, 60)))
    _see_frames(monkeypatch, new)
    monkeypatch.setattr(eyes, "_last_frame",
                        {"b64": old, "size": (120, 80),
                         "ts": time.time() - 60})
    eyes.whats_changed_text()
    assert eyes._last_frame["b64"] == new      # эталон переехал


def test_sizes_differ_resized_honestly(monkeypatch):
    """Кадры разных размеров — свежий приводится к эталону: картинка
    та же, изменений нет, а не «не смогла сравнить»."""
    old = _png_b64(_white(120, 80))
    new = _png_b64(_white(240, 160))
    _see_frames(monkeypatch, new)
    monkeypatch.setattr(eyes, "_last_frame",
                        {"b64": old, "size": (120, 80),
                         "ts": time.time() - 60})
    text = eyes.whats_changed_text()
    assert "существенных изменений нет" in text


def test_broken_reference_honest(monkeypatch):
    """Битый эталон (не PNG) — честное «не смогла сравнить», без
    выдуманного нуля изменений."""
    _see_frames(monkeypatch, _png_b64(_white()))
    monkeypatch.setattr(eyes, "_last_frame",
                        {"b64": "не-png-мусор", "size": (120, 80),
                         "ts": time.time() - 60})
    assert "не смогла сравнить" in eyes.whats_changed_text()


# ---------- команда агента ----------

def test_agent_command_changed(monkeypatch):
    a = _agent(monkeypatch, "С прошлого взгляда (5 мин назад) существенных "
                            "изменений нет: 0,4% кадра")
    for msg in ("что изменилось", "что изменилось?", "что изменилось на экране",
                "что поменялось"):
        r = a.handle(msg)
        assert r.tool_used == "changed", msg
        assert r.source == "python", msg
        assert a.brain.calls == 0, msg


def test_agent_changed_crash_falls_to_brain(monkeypatch):
    """Броня №4 р3: сверка упала — чат жив, говорит мозг."""
    a = _agent(monkeypatch, "не важно")

    def boom():
        raise RuntimeError("пиксели рассыпались")

    monkeypatch.setattr(eyes, "whats_changed_text", boom)
    r = a.handle("что изменилось")
    assert r.source == "brain" and a.brain.calls == 1
