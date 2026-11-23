# -*- coding: utf-8 -*-
"""tests/test_eyes.py — Г-2/Г-2.1: глаза дома в агенте (8083, только чтение).

Глаза — сенсор: _screenshot_b64 / _camera_b64 / _post_chat / health /
_VISION_ERROR — швы, тесты подменяют их, реальный сервер, камера и экран
не нужны. Агентный маршрут «посмотри» не будит мозг; граница слова
обязательна («посмотрим» — не команда). Г-2.1: мозг узнаёт о глазах из
состояния дома (health_cached, без пинга в каждом сообщении).

v2 (22.11): промпт-антипопугай со шуточно-фейковыми [11,22,33,44],
описание первой строкой, цепочка грамматик schema → json_object → raw,
камера — второй источник зрения.

v3 (живой прогон v2): антипопугай ПРОВАЛИЛСЯ — модель выдала
«шуточный» пример как реальность («Экран с текстом и кнопкой», оба
бокса [11,22,33,44], кнопка «пример-надпись», 148.2 с). Якори v3:
- в промптах сенсора НЕТ НИ ОДНОГО примера значений (ни цифр, ни
  JSON-примера) — 3B-модель копирует любой пример;
- чат («посмотри») — живой текст без JSON; JSON-привычка сенсора —
  достаётся description;
- структурный дескриптор (для рук): bbox обязан жить внутри отправленного
  кадра — выдуманная геометрия выбрасывается;
- шаблонные значения («пример-надпись») бракуются на корню.
"""
import json as _json
import re
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
        {"type": "button", "text": "Пуск", "bbox": [0, 698, 32, 720],
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
                        lambda body, timeout=None: {"choices": [{"message":
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

    def fake_post(body, timeout=None):
        seen.append(body.get("response_format", {}).get("type"))
        return {"choices": [{"message": {"content": "ок"}}]}

    monkeypatch.setattr(eyes, "_post_chat", fake_post)
    out, grammar = eyes._ask("b64", "промпт", {"type": "object"}, 10)
    assert out == "ок" and grammar == "schema" and seen == ["json_schema"]


def test_ask_json_object_second_chance(monkeypatch):
    """Сервер отверг строгую схему, но знает простую «только JSON» —
    модель скована грамматикой и не rambling до лимита токенов."""
    seen = []

    def fake_post(body, timeout=None):
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
    def boom(body, timeout=None):
        raise RuntimeError("timeout")

    monkeypatch.setattr(eyes, "_post_chat", boom)
    with pytest.raises(RuntimeError):
        eyes._ask("b64", "промпт", {"type": "object"}, 10)


def test_ask_budget_bounds_rambling():
    """Уроки 132.6 и 148.2 с: бюджеты подрезаны и разведены — чат
    (естественный текст с EOS) — 400, структурный дескриптор — 500."""
    import inspect
    sig = inspect.signature(eyes._ask)
    assert sig.parameters["max_tokens"].default == eyes.ELEMENTS_MAX_TOKENS
    assert eyes.SCREEN_MAX_TOKENS <= 400
    assert eyes.ELEMENTS_MAX_TOKENS <= 500


# ---------- промпты без примеров (уроки v1/v2/v3) ----------

def test_prompts_have_no_parrotable_example():
    """Живые прогоны: модель списала [64,32,412,58] (v1), потом —
    «шуточно-фейковые» [11,22,33,44] с «пример-надписью» (v2). Урок v3:
    3B-модель копирует ЛЮБОЙ пример значений — в промптах сенсора
    примеров нет ВООБЩЕ: ни списков цифр, ни JSON-примера с значениями."""
    for p in (eyes.SCREEN_PROMPT, eyes.ELEMENTS_PROMPT, eyes.CAMERA_PROMPT):
        assert not re.search(r"\[\s*\d+\s*,\s*\d+\s*,", p)
        assert "пример-надпись" not in p
        assert 'Формат: {' not in p
        assert "НЕ копируй" not in p        # запреты не нужны: нет источника


def test_screen_prompt_is_prose_not_json():
    """Чат — словами: JSON-марафон (800 токенов без EOS) — прошлое;
    описание картинки — сладкая точка VL-модели."""
    assert "JSON" not in eyes.SCREEN_PROMPT
    assert "ЧИТАЙ" in eyes.SCREEN_PROMPT


def test_prompt_demands_reading_text():
    """Главное требование всех версий: ЧИТАТЬ надписи — элемент без
    прочитанного текста бесполезен."""
    assert "ЧИТАЙ" in eyes.ELEMENTS_PROMPT
    assert "description" in eyes.SCHEMA["properties"]
    assert "description" in eyes.CAMERA_SCHEMA["properties"]


# ---------- describe / describe_text ----------

def test_describe_ok(monkeypatch):
    _fake_sees(monkeypatch, _json.dumps(DESCRIPTOR, ensure_ascii=False))
    d = eyes.describe()
    assert d["active_window"] == "Командная строка"
    assert d["elements"][1]["type"] == "button"
    assert d["elements"][1]["text"] == "Пуск"


def test_describe_fenced_answer(monkeypatch):
    _fake_sees(monkeypatch,
               "```json\n" + _json.dumps(DESCRIPTOR, ensure_ascii=False) + "\n```")
    assert eyes.describe()["summary"] == "рабочий стол с окнами"


def test_describe_drops_hallucinated_bbox(monkeypatch):
    """Честная геометрия (урок v3): bbox вне отправленного кадра —
    выдумка; выбрасывается, живые элементы остаются."""
    bad = {
        "description": "ок",
        "elements": [
            {"type": "button", "text": "Пуск", "bbox": [0, 698, 32, 720]},
            {"type": "button", "text": "за экраном", "bbox": [2000, 5, 3000, 99]},
            {"type": "text", "text": "перевёрнутый", "bbox": [500, 90, 300, 99]},
            {"type": "text", "text": "мусор", "bbox": "нет"},
        ],
    }
    _fake_sees(monkeypatch, _json.dumps(bad, ensure_ascii=False))
    d = eyes.describe()
    assert len(d["elements"]) == 1
    assert d["elements"][0]["text"] == "Пуск"


def test_describe_stats_reveal_why_empty(monkeypatch):
    """Урок «руки нажми Пуск» → «глаза не прочитали ни одной надписи»:
    выбрасывание больше не МОЛЧИТ — дескриптор несёт _stats, и пустота
    получает причину (для рук и архитектора)."""
    bad = {
        "description": "ок",
        "elements": [
            {"type": "button", "text": "Пуск", "bbox": [0, 698, 32, 720]},
            {"type": "button", "text": "за экраном", "bbox": [2000, 5, 3000, 99]},
        ],
    }
    _fake_sees(monkeypatch, _json.dumps(bad, ensure_ascii=False))
    d = eyes.describe()
    assert d["_stats"] == {"raw": 2, "kept": 1, "dropped": 1}


def test_describe_stats_all_geometry_dropped(monkeypatch):
    """Модель вернула элементы, но ВСЯ геометрия вне кадра — рукам
    и экзамену есть что доложить: увидели N, не прошло проверку."""
    bad = {"elements": [
        {"type": "button", "text": "Пуск", "bbox": [2000, 5, 3000, 99]},
        {"type": "text", "text": "иероглиф", "bbox": [0, 900, 100, 999]},
    ]}
    _fake_sees(monkeypatch, _json.dumps(bad, ensure_ascii=False))
    d = eyes.describe()
    assert d["elements"] == []
    assert d["_stats"]["dropped"] == 2 and d["_stats"]["raw"] == 2


def test_describe_stats_empty_model_answer(monkeypatch):
    """Модель сама ничего не вернула — raw=0: честное «не увидели
    ничего», а не загадочное молчание."""
    _fake_sees(monkeypatch, '{"summary": "пусто"}')
    d = eyes.describe()
    assert d["_stats"] == {"raw": 0, "kept": 0, "dropped": 0}


def test_describe_rejects_parrot_template(monkeypatch):
    """Браковщик шаблонов: «пример-надпись» в ответе — сенсор видит
    промпт, а не экран; ответ забракован, Создателю — честная ошибка."""
    parrot = {
        "description": "Экран с текстом и кнопкой",
        "elements": [
            {"type": "button", "text": "пример-надпись",
             "bbox": [11, 22, 33, 44], "confidence": 0.5},
        ],
    }
    _fake_sees(monkeypatch, _json.dumps(parrot, ensure_ascii=False))
    with pytest.raises(ValueError) as ei:
        eyes.describe()
    assert "шаблон" in str(ei.value)


def test_describe_text_readable(monkeypatch):
    """v3: чат получает живое описание — сенсор говорит словами и цитирует
    надписи; машинные списки элементов в чат не идут."""
    _fake_sees(monkeypatch,
               "Открыт блокнот, в нём заметка «Купить молоко». Внизу панель "
               "задач, слева кнопка «Пуск».")
    text = eyes.describe_text()
    assert text.startswith("Вижу на ЭКРАНЕ: Открыт блокнот")
    assert "Купить молоко" in text          # надписи прочитаны дословно
    assert "Пуск" in text
    assert "глаза думали" in text
    assert "Элементы" not in text           # чат без машинных списков


def test_describe_text_strips_generation_garbage(monkeypatch):
    """Сенсор — не парсер: fences и «Ответ:» не попадают в чат."""
    _fake_sees(monkeypatch, "```text\nОткрыт проводник с папками.\n```")
    text = eyes.describe_text()
    assert text.startswith("Вижу на ЭКРАНЕ: Открыт проводник")
    assert "```" not in text


def test_describe_text_json_habit_falls_back(monkeypatch):
    """Сенсор по привычке ответил JSON — чат всё равно получает суть
    (description), не сырой JSON."""
    _fake_sees(monkeypatch, _json.dumps(DESCRIPTOR, ensure_ascii=False))
    text = eyes.describe_text()
    assert text.startswith("Вижу на ЭКРАНЕ: Открыт браузер")
    assert "{" not in text and "Элементы" not in text


def test_describe_text_empty_answer_honest(monkeypatch):
    _fake_sees(monkeypatch, "   ")
    text = eyes.describe_text()
    assert "пусто" in text or "не поняли" in text


def test_describe_text_eyes_down(monkeypatch):
    monkeypatch.setattr(eyes, "_VISION_ERROR", None)
    monkeypatch.setattr(eyes, "health", lambda: False)
    text = eyes.describe_text()
    assert "8083" in text and "не отвечают" in text


def test_describe_text_server_error(monkeypatch):
    monkeypatch.setattr(eyes, "_VISION_ERROR", None)
    monkeypatch.setattr(eyes, "health", lambda: True)

    def boom(body, timeout=None):
        raise RuntimeError("timeout")

    monkeypatch.setattr(eyes, "_post_chat", boom)
    text = eyes.describe_text()
    assert "глаза ошибились" in text


def test_describe_text_no_module(monkeypatch):
    monkeypatch.setattr(eyes, "_VISION_ERROR", "нет модуля mss")
    text = eyes.describe_text()
    assert "глаза не готовы" in text


def test_describe_minimal_descriptor_ok(monkeypatch):
    """Дескриптор-минималист (без description, без активного окна):
    структурный путь не падает — элементов нет, и это честно."""
    _fake_sees(monkeypatch, '{"summary": "пусто"}')
    d = eyes.describe()
    assert d["elements"] == []            # нет списка — честный пустой


# ---------- камера: второй источник зрения ----------

def _fake_camera(monkeypatch, content):
    monkeypatch.setattr(eyes, "_VISION_ERROR", None)
    monkeypatch.setattr(eyes, "health", lambda: True)
    monkeypatch.setattr(eyes, "_camera_b64", lambda width=960: "b64cam")
    monkeypatch.setattr(eyes, "_post_chat",
                        lambda body, timeout=None: {"choices": [{"message":
                                                   {"content": content}}]})


def test_camera_describes_human(monkeypatch):
    _fake_camera(monkeypatch, _json.dumps({
        "description": "Перед камерой мужчина в свитере, смотрит в экран",
        "objects": [{"name": "человек", "bbox": [1, 2, 3, 4],
                     "confidence": 0.9}]}, ensure_ascii=False))
    text = eyes.describe_camera_text()
    assert text.startswith("Вижу в ВЕБ-КАМЕРЕ:")
    assert "мужчина" in text and "камера думала" in text


def test_camera_honest_when_empty(monkeypatch):
    _fake_camera(monkeypatch, '{"description": ""}')
    assert "пусто" in eyes.describe_camera_text()


def test_camera_no_opencv_honest(monkeypatch):
    monkeypatch.setattr(eyes, "_VISION_ERROR", None)
    monkeypatch.setattr(eyes, "health", lambda: True)

    def no_cv2(width=960):
        raise RuntimeError("нет модуля камеры: No module named 'cv2'. "
                           "Аптечка не смогла: сеть")

    monkeypatch.setattr(eyes, "_camera_b64", no_cv2)
    text = eyes.describe_camera_text()
    assert "камера не смогла" in text
    assert "Аптечка" in text            # Марфа пробовала сама — и сказала


# ---------- аптечка в момент команды: «посмотри на меня» без cv2 ----------

class _FakeCap:
    def isOpened(self):
        return True

    def read(self):
        return True, _FRAME

    def release(self):
        pass


import numpy as _np  # noqa: E402 — только для фикстуры кадра в тесте

_FRAME = _np.zeros((4, 6, 3), dtype=_np.uint8)


def test_camera_b64_installs_missing_cv2(monkeypatch):
    """Нет cv2 — Марфа ставит opencv-python прямо в момент команды
    и ТЕМ ЖЕ вызовом снимает кадр: никакого «поставь и приходи завтра»."""
    import types
    calls = {"n": 0}
    fake_cv2 = types.SimpleNamespace(
        VideoCapture=lambda i: _FakeCap(), COLOR_BGR2RGB=4,
        cvtColor=lambda f, c: f)

    def fake_import():
        calls["n"] += 1
        if calls["n"] == 1:
            raise ImportError("No module named 'cv2'")
        return fake_cv2

    monkeypatch.setattr(eyes, "_import_cv2", fake_import)
    monkeypatch.setattr(eyes.selfcare, "ensure_module",
                        lambda name, timeout=900.0: {
                            "ok": True, "already": False, "version": "4.10.0",
                            "secs": 23.4, "import_name": "cv2",
                            "pkg": "opencv-python", "rc": 0, "tail": "",
                            "why": None})
    b64 = eyes._camera_b64()
    assert b64 and calls["n"] == 2        # до аптечки — мимо, после — живой


def test_camera_b64_module_uninstallable_honest(monkeypatch):
    """Аптечка не смогла (сеть) — честная ошибка с командой для рук,
    без выдумки про «вижу»."""
    def no_cv2():
        raise ImportError("No module named 'cv2'")

    monkeypatch.setattr(eyes, "_import_cv2", no_cv2)
    monkeypatch.setattr(eyes.selfcare, "ensure_module",
                        lambda name, timeout=900.0: {
                            "ok": False, "already": False, "version": None,
                            "secs": 5.0, "import_name": "cv2",
                            "pkg": "opencv-python", "rc": 1,
                            "tail": "network is unreachable", "why": None})
    with pytest.raises(RuntimeError) as ei:
        eyes._camera_b64()
    assert "нет модуля камеры" in str(ei.value)
    assert "Аптечка" in str(ei.value) and "opencv-python" in str(ei.value)


# ---------- живой самотест камеры (урок «а сейчас?» 22.11) ----------

def test_camera_selftest_all_alive(monkeypatch):
    """Модуль → сенсор → кадр: камера ЖИВА — честный трёхступенчатый
    отчёт, а не воспоминание мозга «всё ещё недоступна»."""
    monkeypatch.setattr(eyes, "_VISION_ERROR", None)
    monkeypatch.setattr(eyes, "_cv2_import", lambda: "4.10.0")
    monkeypatch.setattr(eyes, "health", lambda: True)
    monkeypatch.setattr(eyes, "_camera_b64", lambda width=960: "x" * 2048)
    text = eyes.camera_selftest()
    assert "модуль opencv: есть" in text
    assert "сенсор зрения: жив" in text
    assert "КАМЕРА ЖИВА" in text


def test_camera_selftest_no_module_honest(monkeypatch):
    """Модуля нет, аптечка не справилась (сеть/права) — честный отказ:
    что пробовала, почему не вышло и команда для рук Создателя."""
    monkeypatch.setattr(eyes, "_cv2_import", lambda: None)
    monkeypatch.setattr(eyes.selfcare, "ensure_module",
                        lambda name, timeout=900.0: {
                            "ok": False, "already": False, "version": None,
                            "secs": 12.0, "import_name": "cv2",
                            "pkg": "opencv-python", "rc": 1,
                            "tail": "network is unreachable", "why": None})
    text = eyes.camera_selftest()
    assert "модуль opencv: НЕТ" in text
    assert "Аптечка" in text                     # что пробовала сама
    assert "opencv-python" in text                # что ставить руками


def test_camera_selftest_installs_module_itself(monkeypatch):
    """Директива Создателя «ПОчему ты сам не установишь?»: модуля нет —
    аптечка ставит его САМА и докладывает секунды; дальше ступени
    самотеста идут как ни в чём не бывало."""
    state = {"ver": None}
    monkeypatch.setattr(eyes, "_cv2_import", lambda: state["ver"])

    def fake_install(name, timeout=900.0):
        state["ver"] = "4.10.0"
        return {"ok": True, "already": False, "version": "4.10.0",
                "secs": 23.4, "import_name": "cv2",
                "pkg": "opencv-python", "rc": 0, "tail": "", "why": None}

    monkeypatch.setattr(eyes.selfcare, "ensure_module", fake_install)
    monkeypatch.setattr(eyes, "_VISION_ERROR", None)
    monkeypatch.setattr(eyes, "health", lambda: False)   # сенсор дальше по ступеням
    text = eyes.camera_selftest()
    assert "НЕ БЫЛ" in text and "аптечка" in text
    assert "4.10.0" in text and "23" in text      # версия и секунды — в чат


def test_camera_selftest_sensor_down(monkeypatch):
    monkeypatch.setattr(eyes, "_VISION_ERROR", None)
    monkeypatch.setattr(eyes, "_cv2_import", lambda: "4.10.0")
    monkeypatch.setattr(eyes, "health", lambda: False)
    text = eyes.camera_selftest()
    assert "сенсор зрения" in text and "не отвечает" in text


def test_camera_selftest_no_frame_honest(monkeypatch):
    monkeypatch.setattr(eyes, "_VISION_ERROR", None)
    monkeypatch.setattr(eyes, "_cv2_import", lambda: "4.10.0")
    monkeypatch.setattr(eyes, "health", lambda: True)

    def boom(width=960):
        raise RuntimeError("камера не открылась — занята другим приложением?")

    monkeypatch.setattr(eyes, "_camera_b64", boom)
    text = eyes.camera_selftest()
    assert "камера не дала кадр" in text and "занята" in text


def test_camera_module_ok_cached(monkeypatch):
    """Кэш: повторный вопрос за период не импортирует заново."""
    monkeypatch.setattr(eyes, "_cv2_cache", (None, 0.0))
    calls = []
    monkeypatch.setattr(eyes, "_cv2_import",
                        lambda: (calls.append(1) or "4.10"))
    assert eyes.camera_module_ok() is True
    assert eyes.camera_module_ok() is True          # из кэша
    assert len(calls) == 1


def test_camera_module_ok_learns_after_install(monkeypatch):
    """Модуль появился ПОСЛЕ старта дома (pip в соседнем окне) —
    следующая проверка видит его: импорт не кэширует отсутствие
    дольше периода."""
    monkeypatch.setattr(eyes, "_cv2_cache", (None, time.time() - 301.0))
    monkeypatch.setattr(eyes, "_cv2_import", lambda: None)
    assert eyes.camera_module_ok() is False
    monkeypatch.setattr(eyes, "_cv2_import", lambda: "4.10")
    monkeypatch.setattr(eyes, "_cv2_cache", (None, time.time() - 301.0))
    assert eyes.camera_module_ok() is True


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
                        lambda: "Вижу в ВЕБ-КАМЕРЕ: мужчина")
    for msg in ("посмотри в камеру", "включи камеру", "кто в камере",
                "посмотри на меня"):
        r = a.handle(msg)
        assert r.tool_used == "camera", msg
        assert a.brain.calls == 0, msg


def test_agent_prover_kameru_is_live_experiment(monkeypatch):
    """Урок прогона: «проверь ещё раз модуль, он появился» — живой тест,
    не ответ мозга по памяти."""
    a = _agent(monkeypatch, "не важно")
    monkeypatch.setattr(eyes, "camera_selftest",
                        lambda: "ПРОВЕРКА КАМЕРЫ (вживую): всё живо")
    for msg in ("проверь камеру", "Проверь еще раз модуль, он появился",
                "камера работает"):
        r = a.handle(msg)
        assert r.tool_used == "camera_selftest", msg
        assert r.text.startswith("ПРОВЕРКА КАМЕРЫ"), msg
        assert a.brain.calls == 0, msg


def test_house_state_tells_camera_truth(monkeypatch):
    """Состояние дома несёт свежий факт о камере — мозгу не нужно
    выдумывать «всё ещё недоступна» по памяти."""
    monkeypatch.setattr(eyes, "health_cached", lambda period=30.0: True)
    monkeypatch.setattr(eyes, "camera_module_ok", lambda period=300.0: True)
    s = agent._house_state()
    assert "камера: модуль есть" in s
    monkeypatch.setattr(eyes, "camera_module_ok", lambda period=300.0: False)
    s = agent._house_state()
    assert "нет модуля opencv" in s and "проверь камеру" in s


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


# ---------- ЗРИТЕЛЬНАЯ ПАМЯТЬ СОЗДАТЕЛЯ (23.11, Ф1) ----------

def _home_fs(monkeypatch, tmp_path):
    """tmp-дом для файлов зрительной памяти."""
    from core import config
    monkeypatch.setenv("MARFA_HOME", str(tmp_path))
    monkeypatch.setattr(config, "HOME_DIR", tmp_path)
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    return config


def test_remember_creator_saves_file_and_memory(monkeypatch, tmp_path):
    """«запомни меня»: описание ложится в creator_face.json И в память
    дома с тегом — урок лога (полосатая футболка должна пережить кадр)."""
    cfg = _home_fs(monkeypatch, tmp_path)
    _fake_camera(monkeypatch, _json.dumps({
        "description": "Мужчина в полосатой футболке, короткая борода"},
        ensure_ascii=False))
    saved = []
    mem = type("M", (), {"remember": staticmethod(
        lambda text, tags=None, importance=0.0: saved.append((text, tags)))})()
    text = eyes.remember_creator(memory=mem)
    assert "Запомнила" in text and "полосатой футболке" in text
    rec = _json.loads(eyes.creator_face_file().read_text(encoding="utf-8"))
    assert "полосатой футболке" in rec["description"]
    assert saved and "создатель" in saved[0][1]


def test_remember_creator_survives_broken_memory(monkeypatch, tmp_path):
    """RAG споткнулся — зрительная память всё равно целa (файл не
    зависит от базы), дом не падает."""
    _home_fs(monkeypatch, tmp_path)
    _fake_camera(monkeypatch, _json.dumps(
        {"description": "Мужчина в очках"}, ensure_ascii=False))

    class Boom:
        def remember(self, *a, **kw):
            raise RuntimeError("база закрыта")

    text = eyes.remember_creator(memory=Boom())
    assert "Запомнила" in text
    assert eyes.creator_face() == "Мужчина в очках"


def test_recognize_creator_without_memory_is_honest(monkeypatch, tmp_path):
    """«узнай меня» без «запомни меня» — честная подсказка, не выдумка
    «конечно, это ты»."""
    _home_fs(monkeypatch, tmp_path)
    text = eyes.recognize_creator()
    assert "ещё нет" in text and "запомни меня" in text


def test_recognize_creator_feeds_both_texts(monkeypatch, tmp_path):
    """Узнавание честно: сенсор получает и сохранённое описание, и новый
    кадр; ответ сенсора доезжает до Создателя без подгонки."""
    _home_fs(monkeypatch, tmp_path)
    eyes.creator_face_file().parent.mkdir(parents=True, exist_ok=True)
    eyes.creator_face_file().write_text(_json.dumps(
        {"description": "Мужчина в полосатой футболке"},
        ensure_ascii=False), encoding="utf-8")
    prompts = []
    _fake_camera(monkeypatch, _json.dumps({
        "description": "Похож на Создателя: та же полосатая футболка"},
        ensure_ascii=False))
    import core.eyes as _e
    real_ask = _e._ask

    def spy_ask(b64, prompt, schema, **kw):
        prompts.append(prompt)
        return real_ask(b64, prompt, schema, **kw)

    monkeypatch.setattr(_e, "_ask", spy_ask)
    text = eyes.recognize_creator()
    assert "Сверяю с зрительной памятью" in text
    assert "Похож на Создателя" in text
    assert prompts and "полосатой футболке" in prompts[-1]
    assert "Не подгоняй" in prompts[-1]
