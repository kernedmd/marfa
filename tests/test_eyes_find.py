# -*- coding: utf-8 -*-
"""tests/test_eyes_find.py — №2 роадмапа 30: «найди на экране».

Поиск элемента по описанию — лестница зон со своим апскейлом (урок
v1.4: мелкая надпись в целом кадре теряется, в увеличенной четверти
читается). Контракт:

  - целый кадр нашёл → надпись, центр ЭКРАНА, рамка, уверенность;
  - честная геометрия в каждой зоне: выдуманный bbox выбрасывается
    и в целом кадре, и в зоне — в прицел ответа не попадает;
  - не нашёл в целом кадре → 4 четверти, каждая увеличена до
    рабочей ширины; координаты зоны честно переводятся в координаты
    экрана (обратно апскейлу и сдвигу);
  - один бюджет времени на ВСЮ лестницу (H5), а не 5×240 с;
  - не нашла — говорит, что глаза ЧИТАЮТ; глаза мертвы/нет модуля —
    честный отказ без исключений;
  - команда агента «найди на экране <что>» не будит мозг.

Швы: _screenshot_b64 / _zone_b64 / _ask / health / _VISION_ERROR —
реальный сервер, экран и камера не нужны.
"""
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import agent, eyes  # noqa: E402


def _see(monkeypatch, content, real=(1920, 1080), small=(1280, 720)):
    """Глаза на целый кадр отвечают content; экран и зоны подменены
    (зона по умолчанию — рамка 1280×720, чтобы тесты целого кадра
    не зависели от лестницы)."""
    monkeypatch.setattr(eyes, "_VISION_ERROR", None)
    monkeypatch.setattr(eyes, "health", lambda: True)
    monkeypatch.setattr(eyes, "_screenshot_b64",
                        lambda width=eyes.WORK_WIDTH:
                        ("b64-whole", real, small))
    monkeypatch.setattr(eyes, "_ask",
                        lambda b64, prompt, schema, max_tokens=500,
                        timeout=None: (content, "schema"))
    monkeypatch.setattr(eyes, "_zone_b64",
                        lambda b64, box, width=eyes.WORK_WIDTH:
                        ("b64-zone", (width, width // 2)))


def _agent(monkeypatch, answer):
    class FakeBrain:
        calls = 0

        def ask_json(self, *a, **kw):
            self.calls += 1
            return {"answer": "мозг"}

    class FakeMemory:
        def recall(self, *a, **kw):
            return []

    monkeypatch.setattr(eyes, "find_on_screen", lambda q: answer)
    return agent.Agent(brain=FakeBrain(), memory=FakeMemory())


# ---------- поиск в целом кадре ----------

def test_find_whole_frame_hit(monkeypatch):
    content = ('{"description": "рабочий стол", "elements": ['
               '{"type": "button", "text": "Пуск", "bbox": [0, 350, 64, 360],'
               ' "confidence": 0.9}]}')
    _see(monkeypatch, content)
    text = eyes.find_on_screen("Пуск")
    assert "Нашла «Пуск»" in text
    assert "центр экрана" in text and "уверенность глаз 0.90" in text
    # центр = середина бокса в масштабе экрана: кадр 1280x720 → экран
    # 1920x1080 (×1.5): бокс [0,350,64,360] → экран [0,525,96,540],
    # центр (48, 532)
    assert "центр экрана (48, 532)" in text
    assert "руки нажми Пуск" in text          # находка сразу кормит руки


def test_find_query_normalized(monkeypatch):
    """«кнопку Пуск» и «ПУСК» — тот же поиск: род элемента снимается."""
    content = ('{"elements": [{"type": "button", "text": "Пуск", '
               '"bbox": [10, 10, 20, 20], "confidence": 0.8}]}')
    _see(monkeypatch, content)
    assert "Нашла «Пуск»" in eyes.find_on_screen("кнопку Пуск")


def test_find_low_confidence_not_a_hit(monkeypatch):
    """Неуверенный элемент — НЕИЗВЕСТЕН: поиск не выдаёт мусор за находку."""
    content = ('{"elements": [{"type": "button", "text": "Пуск", '
               '"bbox": [10, 10, 20, 20], "confidence": 0.2}]}')
    _see(monkeypatch, content)
    assert eyes.find_on_screen("Пуск").startswith("Не нашла")


def test_find_garbage_bbox_rejected_everywhere(monkeypatch):
    """Выдуманная геометрия бракуется и в целом кадре, и в зонах:
    честный «не нашла» с причиной, а не фейк про экран."""
    bad = ('{"elements": [{"type": "button", "text": "Пуск", '
           '"bbox": [1300, 700, 1400, 710], "confidence": 0.95}]}')
    _see(monkeypatch, bad)
    zones = []

    def fake_zone(b64, box, width=eyes.WORK_WIDTH):
        zones.append(box)
        return ("b64-zone", (width, width // 2))

    monkeypatch.setattr(eyes, "_zone_b64", fake_zone)
    text = eyes.find_on_screen("Пуск")
    assert text.startswith("Не нашла")
    assert "не прошёл проверку координат" in text   # причина из _stats
    assert len(zones) == 4                          # лестница работала


# ---------- лестница зон и обратная карта координат ----------

def test_find_zone_ladder_backmaps_coordinates(monkeypatch):
    """Целый кадр пуст → 4 четверти, каждая увеличена. Координаты зоны
    честно возвращаются в координаты экрана: центр не может уехать из
    своей четверти. Кадр 1280×720, экран 1920×1080, попадание — в
    последней зоне (правая нижняя четверть 640,360,1280,720), апскейл
    ×2 → зона 1280×720, бокс в зоне [640,360,1280,720]."""
    whole = '{"elements": []}'
    _see(monkeypatch, whole)
    zone_hit = ('{"elements": [{"type": "button", "text": "Сканер", '
                '"bbox": [640, 360, 1280, 720], "confidence": 0.6}]}')
    asks = []

    def fake_ask(b64, prompt, schema, max_tokens=500, timeout=None):
        asks.append((b64, timeout))
        assert timeout is not None and timeout > 0   # H5: бюджет общий
        return (zone_hit if b64 == "b64-zone-rb" else whole, "schema")

    monkeypatch.setattr(eyes, "_ask", fake_ask)
    seen_zones = []

    def fake_zone(b64, box, width=eyes.WORK_WIDTH):
        assert b64 == "b64-whole"
        seen_zones.append(box)
        tag = "rb" if box == (640, 360, 1280, 720) else "x"
        return ("b64-zone-%s" % tag, (1280, 720))     # 640×360 × 2

    monkeypatch.setattr(eyes, "_zone_b64", fake_zone)
    text = eyes.find_on_screen("Сканер")
    assert "Нашла «Сканер»" in text
    assert "нижняя правая четверть" in text          # где нашли — названо
    # обратная карта: центр зоны (960, 540) → /2 → (480, 270) в четверти
    # → +(640, 360) → (1120, 630) кадра → ×1.5 → экран (1680, 945)
    assert "центр экрана (1680, 945)" in text
    assert len(seen_zones) == 4                       # лестница прошла все
    assert len(asks) == 5                             # кадр + 4 зоны


def test_find_zone_confidence_gate_lower(monkeypatch):
    """В зоне верим чуть шире (элемент крупнее), но не мусору: 0.2 — мимо."""
    _see(monkeypatch, '{"elements": []}')
    zone_miss = ('{"elements": [{"type": "button", "text": "Сканер", '
                 '"bbox": [10, 10, 20, 20], "confidence": 0.2}]}')

    def fake_ask(b64, prompt, schema, max_tokens=500, timeout=None):
        return (zone_miss if b64 == "b64-zone"
                else '{"elements": []}', "schema")

    monkeypatch.setattr(eyes, "_ask", fake_ask)
    monkeypatch.setattr(eyes, "_zone_b64",
                        lambda b64, box, width=eyes.WORK_WIDTH:
                        ("b64-zone", (width, width // 2)))
    assert eyes.find_on_screen("Сканер").startswith("Не нашла")


def test_find_deadline_stops_ladder(monkeypatch):
    """H5: у лестницы ОДИН бюджет — после него честный отказ, а не
    пятый вопрос по 240 с."""
    _see(monkeypatch, '{"elements": []}')
    monkeypatch.setattr(eyes, "FIND_TOTAL_SEC", -1.0)   # время вышло
    text = eyes.find_on_screen("Сканер")
    assert "время поиска вышло" in text


# ---------- честные отказы ----------

def test_find_eyes_down_honest(monkeypatch):
    monkeypatch.setattr(eyes, "_VISION_ERROR", None)
    monkeypatch.setattr(eyes, "health", lambda: False)
    assert "не отвечают" in eyes.find_on_screen("Пуск")


def test_find_no_module_honest(monkeypatch):
    monkeypatch.setattr(eyes, "_VISION_ERROR", "нет модуля зрения: x")
    assert "глаза не готовы" in eyes.find_on_screen("Пуск")


def test_find_empty_query_hint():
    assert "что найти?" in eyes.find_on_screen("")


def test_find_not_found_lists_what_eyes_read(monkeypatch):
    content = ('{"elements": [{"type": "text", "text": "Chrome", '
               '"bbox": [10, 10, 200, 30], "confidence": 0.9}]}')
    _see(monkeypatch, content)
    monkeypatch.setattr(eyes, "_zone_b64",
                        lambda b64, box, width=eyes.WORK_WIDTH:
                        ("b64-zone", (width, width // 2)))
    text = eyes.find_on_screen("Сканер")
    assert text.startswith("Не нашла")
    assert "«Chrome»" in text                     # что читают — названо


# ---------- команда агента ----------

def test_agent_find_command(monkeypatch):
    a = _agent(monkeypatch, "Нашла «Пуск»: центр экрана (48, 532)")
    for msg in ("найди на экране Пуск", "Найди на экране: Пуск!",
                "поищи на экране кнопку Пуск", "где на экране Пуск?"):
        r = a.handle(msg)
        assert r.tool_used == "find", msg
        assert r.source == "python", msg
        assert r.text.startswith("Нашла"), msg
        assert a.brain.calls == 0, msg             # мозг молчит


def test_agent_find_without_query_hints(monkeypatch):
    a = _agent(monkeypatch, "не важно")
    r = a.handle("найди на экране")
    assert r.tool_used == "find" and "что найти?" in r.text


def test_agent_find_phrase_is_not_command(monkeypatch):
    """«найди на экране» — команда; «найди мне смысл» — речь, к мозгу."""
    a = _agent(monkeypatch, "не важно")
    assert a.handle("найди мне смысл жизни").tool_used != "find"
    assert a.brain.calls == 1


def test_agent_find_fast_crash_falls_to_brain(monkeypatch):
    """Броня №4 раунда 3: упавший поиск не роняет чат — говорит мозг."""
    a = _agent(monkeypatch, "не важно")

    def boom(q):
        raise RuntimeError("сенсор упал")

    monkeypatch.setattr(eyes, "find_on_screen", boom)
    r = a.handle("найди на экране Пуск")
    assert r.source == "brain" and a.brain.calls == 1
