# -*- coding: utf-8 -*-
r"""tests/test_motor.py — РУКИ v2 «ЕДИНОЕ ЗРЕНИЕ» (ТЗ_Руки_v2, 22.11).

Якоря возвращения к дому: у рук НЕТ своей модели — они исполняют
координаты глаз (мастер-ТЗ §4/§8/§10.2); сервер зрения не гаснет и
VRAM не танцует (никакого ensure_server/release); задание разбирается
глаголом; элемент находится по ПРОЧИТАННОЙ надписи с уверенностью
≥ 0.6 (§10.3); клик — по центру валидированного bbox с масштабом;
страж-whitelist не пускает ни клавишу мимо списка; моторика — ТОЛЬКО
по резолюции Создателя (сухой режим по умолчанию); экзамен Р-0 v2
проверяет цепочку глаза→руки на живых пикселях.

Швы: _screenshot / _execute / enabled / describe_with_sizes (глаз) —
подменяются, реальный экран и мышь не трогаются.
"""
import base64
import io
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import config, motor  # noqa: E402
from safety import guard  # noqa: E402

REAL = (1920, 1080)          # реальный экран
SENT = (1280, 720)           # кадр, который видят глаза


@pytest.fixture
def home(tmp_path, monkeypatch):
    """Изолированный дом: руки не трогают реальные файлы станции."""
    monkeypatch.setattr(config, "HOME_DIR", tmp_path)
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(config, "LOGS_DIR", tmp_path / "logs")
    monkeypatch.setattr(config, "MODELS_DIR", tmp_path / "models")
    monkeypatch.setattr(config, "HANDS_ENABLED_FILE",
                        tmp_path / "data" / "hands_enabled.json")
    monkeypatch.setattr(config, "HANDS_LOG_FILE",
                        tmp_path / "logs" / "hands_log.jsonl")
    monkeypatch.setattr(config, "GUARD_LOG_FILE",
                        tmp_path / "logs" / "guard_log.jsonl")
    return tmp_path


# Пуск в координатах ОТПРАВЛЕННОГО кадра 1280×720 (экран 1920×1080):
# экран [0, 1040, 96, 1080] -> кадр [0, 693, 64, 720]; центр (32, 706)
# -> экран (48, 1059). Глаза v3 бракуют bbox вне кадра — фиксура честная.
DESCRIPTOR = {
    "description": "рабочий стол",
    "elements": [
        {"type": "button", "text": "Пуск",
         "bbox": [0, 693, 64, 720], "confidence": 0.9},
        {"type": "input", "text": "Поиск",
         "bbox": [80, 700, 300, 718], "confidence": 0.8},
    ],
}


def _armed_eyes(monkeypatch, descriptor=DESCRIPTOR, real=REAL, sent=SENT,
                alive=True):
    """Глаза в песочнице: сервер жив, дескриптор и размеры — из фикстуры."""
    from core import eyes
    monkeypatch.setattr(eyes, "_VISION_ERROR", None)
    monkeypatch.setattr(eyes, "health", lambda: alive)
    monkeypatch.setattr(eyes, "_screenshot_b64",
                        lambda width=1280: ("b64", real, sent))
    monkeypatch.setattr(eyes, "_post_chat",
                        lambda body: {"choices": [{"message": {"content":
                         json.dumps(descriptor, ensure_ascii=False)}}]})


# ---------- разбор задания словами (ТЗ 4) ----------

def test_parse_click_verbs():
    for phrase, target in (("нажми Пуск", "Пуск"),
                           ("кликни по Сохранить", "по Сохранить"),
                           ("щёлкни Пуск", "Пуск"),
                           ("открой Блокнот", "Блокнот"),
                           ("запусти Калькулятор", "Калькулятор")):
        plan = motor.parse_task(phrase)
        assert plan["verb"] == "click", phrase
        assert plan["target"] == target, phrase


def test_parse_ruki_prefix_stripped():
    """«руки, нажми Пуск» — слово «руки» не мешает глаголу."""
    plan = motor.parse_task("руки, нажми Пуск")
    assert plan["verb"] == "click" and plan["target"] == "Пуск"
    assert motor.parse_task("руки")["verb"] == "empty"


def test_parse_type_keeps_case():
    plan = motor.parse_task("напечатай Hello World")
    assert plan["verb"] == "type" and plan["text"] == "Hello World"


def test_parse_hotkey_forms():
    assert motor.parse_task("клавиши ctrl c") == {
        "verb": "hotkey", "combo": "ctrl+c"}
    assert motor.parse_task("сочетание ctrl+c") == {
        "verb": "hotkey", "combo": "ctrl+c"}
    assert motor.parse_task("нажми enter") == {
        "verb": "hotkey", "combo": "enter"}
    assert motor.parse_task("нажми клавиши alt tab") == {
        "verb": "hotkey", "combo": "alt+tab"}


def test_parse_scroll_directions():
    assert motor.parse_task("прокрути вверх")["direction"] == "up"
    assert motor.parse_task("листай вниз")["direction"] == "down"
    assert motor.parse_task("прокрути")["direction"] == "down"


def test_parse_garbage_is_unknown():
    plan = motor.parse_task("сделай красиво")
    assert plan["verb"] == "unknown"


# ---------- сверка текстов: задание ↔ надпись (ТЗ 4) ----------

def test_find_element_exact_and_kind_words():
    el = motor.find_element(DESCRIPTOR, "Пуск")
    assert el is not None and el["text"] == "Пуск"
    # «кнопку» — слово-указатель, снимается
    assert motor.find_element(DESCRIPTOR, "кнопку Пуск") is not None


def test_find_element_substring_both_ways():
    # цель ⊃ надпись: «нажми кнопку Пуска»
    assert motor.find_element(DESCRIPTOR, "кнопку Пуска") is not None
    # надпись ⊃ цель: «блокнот» ⊂ «Блокнот — Безымянный»
    d = {"elements": [{"type": "button", "text": "Блокнот — Безымянный",
                       "bbox": [1, 1, 9, 9], "confidence": 0.9}]}
    assert motor.find_element(d, "блокнот") is not None


def test_find_element_case_and_yo_normalized():
    d = {"elements": [{"type": "button", "text": "Ёлки",
                       "bbox": [1, 1, 9, 9], "confidence": 0.9}]}
    assert motor.find_element(d, "елки") is not None


def test_find_element_low_confidence_is_unknown():
    """§10.3: уверенность < 0.6 — элемент НЕИЗВЕСТЕН, кликать нельзя."""
    d = {"elements": [{"type": "button", "text": "Пуск",
                       "bbox": [1, 1, 9, 9], "confidence": 0.4}]}
    assert motor.find_element(d, "Пуск") is None
    # но для честного «вижу похоже, но не рискну» он находится без порога
    assert motor.find_element(d, "Пуск", min_conf=0.0) is not None


def test_find_element_no_bbox_skipped():
    d = {"elements": [{"type": "button", "text": "Пуск",
                       "confidence": 0.9}]}
    assert motor.find_element(d, "Пуск") is None


# ---------- координаты: центр bbox → экран (§10.2) ----------

def test_scale_point_frame_to_screen():
    assert motor.scale_point(640, 360, REAL, SENT) == (960, 540)
    assert motor.scale_point(0, 0, REAL, SENT) == (0, 0)
    # угол кадра — вне пиксельной сетки: клип держит точку ВНУТРИ экрана
    assert motor.scale_point(1280, 720, REAL, SENT) == (1919, 1079)
    # уменьшение кадра вдвое — правый край не выезжает за экран
    assert motor.scale_point(1279, 719, (640, 360), SENT) == (639, 359)


def test_click_point_is_bbox_center_scaled():
    el = DESCRIPTOR["elements"][0]
    assert motor.frame_center(el) == (32, 706)
    assert motor.click_point(el, REAL, SENT) == (48, 1059)


# ---------- СТРАЖ моторики (ТЗ 6: список — код, не мнение модели) ----------

def test_guard_click_inside_allowed(home):
    v = motor.guard_action("click", (960, 540), REAL)
    assert v.allowed() and v.level == "MEDIUM"


def test_guard_click_outside_denied(home):
    v = motor.guard_action("click", (6000, 6000), REAL)
    assert not v.allowed() and "краем" in v.reason


def test_guard_hotkey_whitelist(home):
    assert motor.guard_action("hotkey", ("ctrl+c",), REAL).allowed()
    bad = motor.guard_action("hotkey", ("alt+f4",), REAL)
    assert not bad.allowed() and "whitelist" in bad.reason


def test_guard_type_secrets_banned(home):
    guard.ensure_canaries()
    canary = guard.ensure_canaries()[0]
    v = motor.guard_action("type", ("see " + canary,), REAL)
    assert not v.allowed()


def test_guard_type_cyrillic_denied(home):
    v = motor.guard_action("type", ("привет",), REAL)
    assert not v.allowed() and "латиниц" in v.reason


def test_guard_type_too_long_denied(home):
    v = motor.guard_action("type", ("a" * (config.HANDS_TYPE_LIMIT + 1),),
                           REAL)
    assert not v.allowed()


def test_guard_scroll_low_risk(home):
    v = motor.guard_action("scroll", ("up",), REAL)
    assert v.allowed() and v.level == "LOW"


# ---------- резолюция Создателя: сухой режим по умолчанию ----------

def test_disabled_by_default(home):
    assert motor.enabled() is False


def test_enabled_by_creators_file(home):
    config.HANDS_ENABLED_FILE.parent.mkdir(parents=True, exist_ok=True)
    config.HANDS_ENABLED_FILE.write_text('{"resolution": "кнопка 91"}',
                                         encoding="utf-8")
    assert motor.enabled() is True


# ---------- единое зрение: НЕТ VRAM-танца ----------

def test_no_server_management_left():
    """Руки v2 не поднимают и не укладывают серверов: у них нет своей
    модели (мастер-ТЗ §4: хозяин VRAM — глаза, смена по расписанию)."""
    public = [n for n in dir(motor) if not n.startswith("__")]
    for gone in ("ensure_server", "release", "server_alive", "_spawn_server",
                 "_stop_llama", "_ask_hands", "parse_action", "dialect",
                 "map_point", "HANDS_PROMPT"):
        assert gone not in public, "v1 хвост: " + gone


def test_vram_dance_lives_only_in_vram_module():
    """Церемония заёма VRAM — у кодера (core/vram.py), не у рук."""
    from core import repair, vram
    assert callable(vram.stop_llama)
    assert not hasattr(motor, "_stop_llama")
    src = Path(repair.__file__).read_text(encoding="utf-8")
    assert "from core.vram import stop_llama" in src


# ---------- цикл задачи: один взгляд глаз — одно действие ----------

def test_run_dry_mode_plans_without_touching(home, monkeypatch):
    """Без резолюции Создателя мышь не трогается — только точка."""
    _armed_eyes(monkeypatch)
    touched = []
    monkeypatch.setattr(motor, "_execute",
                        lambda name, args: touched.append((name, args)))
    out = motor.run("нажми Пуск")
    assert "сухой режим" in out
    assert "кликнула бы в (48, 1059)" in out      # центр bbox × масштаб
    assert "«Пуск»" in out
    assert touched == []                          # мышь не тронута


def test_run_motor_mode_executes_and_verifies(home, monkeypatch):
    _armed_eyes(monkeypatch)
    config.HANDS_ENABLED_FILE.parent.mkdir(parents=True, exist_ok=True)
    config.HANDS_ENABLED_FILE.write_text('{"resolution": "91"}',
                                         encoding="utf-8")
    calls = []
    monkeypatch.setattr(motor, "_execute",
                        lambda name, args: calls.append((name, args))
                        or "кликнула (%d, %d)" % (args[0], args[1]))
    shots = [("b" * 10, REAL, SENT), ("a" * 10, REAL, SENT)]
    monkeypatch.setattr(motor, "_screenshot",
                        lambda: shots.pop(0))
    monkeypatch.setattr(motor, "_pixel_diff",
                        lambda b, a, box=None: 0.42)
    out = motor.run("нажми Пуск")
    assert calls == [("click", (48, 1059))]
    assert "кликнула (48, 1059)" in out
    assert "42%" in out and "замкнутый цикл" in out
    assert "сухой режим" not in out


def test_run_element_not_found_honest(home, monkeypatch):
    """Не вижу — честно: что глаза читают, тем и отвечаем."""
    _armed_eyes(monkeypatch)
    out = motor.run("нажми Корзина")
    assert "не видят" in out and "Корзина" in out
    assert "«Пуск»" in out and "«Поиск»" in out   # вот что видят глаза
    assert "посмотри" in out


def test_run_low_confidence_refused(home, monkeypatch):
    d = {"elements": [{"type": "button", "text": "Пуск",
                       "bbox": [1, 1, 9, 9], "confidence": 0.4}]}
    _armed_eyes(monkeypatch, descriptor=d)
    out = motor.run("нажми Пуск")
    assert "не рискнули" in out and "0.40" in out
    assert "кликнула бы" not in out


def test_run_eyes_down_no_self_heal(home, monkeypatch):
    """Глаза мертвы — честный отказ; руки НЕ поднимают свой сервер и
    НЕ рестартуют чужой (хозяин VRAM — глаза, «доктор» — его лечит)."""
    _armed_eyes(monkeypatch, alive=False)
    restarted = []
    monkeypatch.setattr("core.doctor.heal",
                        lambda ids: restarted.append(ids) or [])
    out = motor.run("нажми Пуск")
    assert "глаза" in out and "не отвечают" in out
    assert "доктор" in out
    assert restarted == []


def test_validated_geometry_never_leaves_screen(home, monkeypatch):
    """Инвариант единого зрения: bbox, проверенный глазами (живёт внутри
    кадра), после масштаба даёт точку ВНУТРИ экрана — безопасность по
    построению, а страж краёв остаётся последней линией обороны
    против ошибок кода (проверяется напрямую в guard-тестах)."""
    import random
    rnd = random.Random(42)
    for _ in range(200):
        sw = rnd.randint(640, 1920)
        sh = rnd.randint(360, 1200)
        rw = rnd.randint(640, 2560)
        rh = rnd.randint(480, 1440)
        x1, x2 = sorted(rnd.sample(range(0, sw), 2))
        y1, y2 = sorted(rnd.sample(range(0, sh), 2))
        el = {"bbox": [x1, y1, x2, y2]}
        px, py = motor.click_point(el, (rw, rh), (sw, sh))
        assert 0 <= px < rw and 0 <= py < rh, (el, (rw, rh), (sw, sh))


def test_run_unknown_task_gets_hint(home):
    out = motor.run("сделай красиво")
    assert "не поняли" in out and "нажми" in out


def test_run_empty_task_gets_hint(home):
    out = motor.run("руки")
    assert "задание" in out and "нажми" in out


def test_run_logs_to_hands_log(home, monkeypatch):
    _armed_eyes(monkeypatch)
    motor.run("нажми Пуск")
    log = [json.loads(l) for l in
           config.HANDS_LOG_FILE.read_text(encoding="utf-8").splitlines()]
    assert any(r.get("verb") == "click" and r.get("element") == "Пуск"
               and r.get("mode") == "dry" for r in log)


def test_run_type_dry_and_guard(home, monkeypatch):
    _armed_eyes(monkeypatch)      # печать глаз не требует, но пусть живут
    out = motor.run("напечатай hello")
    assert "СУХОЙ РЕЖИМ" in out and "hello" in out
    out2 = motor.run("напечатай привет")
    assert "СТРАЖ ОТКАЗАЛ" in out2 and "латиниц" in out2


def test_run_hotkey_whitelisted_and_not(home, monkeypatch):
    out = motor.run("клавиши ctrl+c")
    assert "СУХОЙ РЕЖИМ" in out and "ctrl+c" in out
    out2 = motor.run("клавиши alt+f4")
    assert "СТРАЖ ОТКАЗАЛ" in out2 and "whitelist" in out2


def test_run_redirects_looking_tasks(home, monkeypatch):
    """Урок живого прогона 22.11: «посмотри на меня» ушло РУКАМ —
    VRAM-танец впустую и клик в никуда. Руки не смотрят: редирект
    к глазам/камере, экран даже не спрашивается."""
    asked = []
    monkeypatch.setattr("core.eyes.describe_with_sizes",
                        lambda width=1280: asked.append(1) or ({}, REAL, SENT))
    out = motor.run("посмотри на меня")
    assert "РУКИ не смотрят" in out and "посмотри в камеру" in out
    assert asked == []
    for task in ("опиши что на экране", "прочитай надпись", "включи камеру"):
        assert "РУКИ не смотрят" in motor.run(task), task
    assert asked == []


# ---------- экзамен Р-0 v2: цепочка глаза→руки ----------

def test_exam_dry_reports_point(home, monkeypatch):
    _armed_eyes(monkeypatch)
    out = motor.exam()
    assert "ЭКЗАМЕН Р-0" in out
    assert "(48, 1059)" in out                    # центр бокса → экран
    assert "СУХОЙ РЕЖИМ" in out and "кнопка 91" in out


def test_exam_motor_clicks_verifies_and_closes_menu(home, monkeypatch):
    _armed_eyes(monkeypatch)
    config.HANDS_ENABLED_FILE.parent.mkdir(parents=True, exist_ok=True)
    config.HANDS_ENABLED_FILE.write_text('{"resolution": "91"}',
                                         encoding="utf-8")
    calls = []

    def fake_execute(name, args):
        calls.append(name)
        if name == "click":
            return "кликнула (%d, %d)" % (args[0], args[1])
        return "нажала %s" % args[0]

    monkeypatch.setattr(motor, "_execute", fake_execute)
    shots = [("b" * 10, REAL, SENT), ("a" * 10, REAL, SENT)]
    monkeypatch.setattr(motor, "_screenshot", lambda: shots.pop(0))
    monkeypatch.setattr(motor, "_pixel_diff",
                        lambda b, a, box=None: 0.25)
    out = motor.exam()
    assert calls == ["click", "hotkey"]           # клик + Esc (уборка)
    assert "ЦЕПОЧКА РАБОТАЕТ" in out and "25%" in out


def test_exam_click_did_not_change_screen(home, monkeypatch):
    _armed_eyes(monkeypatch)
    config.HANDS_ENABLED_FILE.parent.mkdir(parents=True, exist_ok=True)
    config.HANDS_ENABLED_FILE.write_text('{"resolution": "91"}',
                                         encoding="utf-8")
    monkeypatch.setattr(motor, "_execute", lambda name, args: "клик (шов)")
    shots = [("b" * 10, REAL, SENT), ("b" * 10, REAL, SENT)]
    monkeypatch.setattr(motor, "_screenshot", lambda: shots.pop(0))
    monkeypatch.setattr(motor, "_pixel_diff",
                        lambda b, a, box=None: 0.0)
    out = motor.exam()
    assert "не изменил экран" in out and "архитектору" in out


def test_exam_no_pusk_honest(home, monkeypatch):
    _armed_eyes(monkeypatch, descriptor={"elements": []})
    out = motor.exam()
    assert "не состоялся" in out


def test_exam_eyes_down_honest(home, monkeypatch):
    _armed_eyes(monkeypatch, alive=False)
    out = motor.exam()
    assert "не отвечают" in out or "не смогла" in out


# ---------- пиксельная сверка ----------

def _png_b64(color):
    buf = io.BytesIO()
    from PIL import Image
    Image.new("RGB", (50, 50), color).save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


def test_pixel_diff_identical_zero():
    b = _png_b64((255, 0, 0))
    assert motor._pixel_diff(b, b) == 0.0


def test_pixel_diff_change_detected():
    frac = motor._pixel_diff(_png_b64((255, 0, 0)), _png_b64((0, 0, 255)))
    assert frac == 1.0


def test_pixel_diff_bad_input_none():
    assert motor._pixel_diff("не-base64", "тоже") is None


# ---------- закон дома: якоря ----------

def test_law_anchors():
    """Дом держит курс: порог уверенности из мастер-ТЗ §10.3, whitelist
    без alt+f4, бюджета шагов больше нет — цикл одноточечный."""
    assert config.HANDS_MIN_CONFIDENCE == 0.6
    assert "alt+f4" not in config.HANDS_HOTKEY_WHITELIST
    assert "ctrl+c" in config.HANDS_HOTKEY_WHITELIST
    assert config.HANDS_TYPE_LIMIT <= 150


# ---------- агент передаёт задание ЦЕЛИКОМ (регрессия v2) ----------

def test_agent_hands_branch_keeps_the_verb():
    """Регрессия единого зрения: раньше агент срезал префикс («нажми
    Пуск» → мотор получал «Пуск» без глагола) — теперь глагол разбирают
    сами руки, значит в motor.run уходит задание ЦЕЛИКОМ. Проверяем
    ветку агента по исходнику (без поднятия Flask): текст до run()
    не обрезается."""
    import core.agent as agent_mod
    src = Path(agent_mod.__file__).read_text(encoding="utf-8")
    # ветка рук: полный текст t уходит в motor.run
    assert 'motor.run(t), "python", "hands"' in src
    assert 'motor.run(task)' not in src.split("Круг Р v2")[1].split("# САМОЛЕЧЕНИЕ")[0]


def test_parse_more_verbs():
    assert motor.parse_task("кликнуть по Пуску")["verb"] == "click"
    assert motor.parse_task("тыкни в Поиск")["verb"] == "click"
    assert motor.parse_task("введи hello")["verb"] == "type"
    assert motor.parse_task("скролли вверх")["direction"] == "up"


def test_run_click_by_po_prefix(home, monkeypatch):
    """«кликни по Сохранить» — предлог «по» не мешает сверке текстов."""
    d = {"elements": [{"type": "button", "text": "Сохранить",
                       "bbox": [100, 100, 200, 140], "confidence": 0.9}]}
    _armed_eyes(monkeypatch, descriptor=d, real=SENT, sent=SENT)
    out = motor.run("кликни по Сохранить")
    assert "кликнула бы в (150, 120)" in out


def test_dpi_aware_is_safe_outside_windows():
    """На чужой платформе (песочница архитектора) DPI-шов молчит."""
    assert motor._dpi_aware() is None


def test_hint_names_verbs():
    out = motor.run("сделай красиво")
    for word in ("нажми", "напечатай", "клавиши", "прокрути"):
        assert word in out, word


def test_parse_bare_verb_is_empty_not_garbage():
    """«нажми» без цели — подсказка, а не «не вижу ""»."""
    assert motor.parse_task("нажми")["verb"] == "empty"
    assert motor.parse_task("напечатай")["verb"] == "empty"


# ---------- честная пустота: _stats называет ПРИЧИНУ (22.11, вечер) ----------
# Урок живого прогона: «руки нажми Пуск» → «глаза не прочитали на
# экране ни одной надписи» — а ПОЧЕМУ пусто, дом промолчал. Пустота
# теперь приходит с диагнозом из _stats дескриптора глаз.

def test_seen_texts_geometry_failed_diagnosis():
    """Модель вернула элементы, но геометрия НЕ ПРОШЛА проверку кадра —
    отказ рук называет это лечимым заболеванием, а не «не вижу»."""
    d = {"elements": [], "_stats": {"raw": 3, "kept": 0, "dropped": 3}}
    s = motor._seen_texts(d)
    assert "3" in s and "не прошёл" in s and "архитектору" in s


def test_seen_texts_seen_but_not_read_diagnosis():
    """Объекты увидели, надписи — нет: «света/масштаба не хватило»,
    выход — «посмотри», там живое описание словами."""
    d = {"elements": [{"type": "icon", "text": "", "bbox": [1, 2, 3, 4]}],
         "_stats": {"raw": 2, "kept": 2, "dropped": 0}}
    s = motor._seen_texts(d)
    assert "2" in s and "не прочитали" in s and "посмотри" in s


def test_seen_texts_old_descriptor_still_honest():
    """Дескриптор без статистики (старый формат) — прежнее честное
    «ни одной надписи», без выдумок и без падения."""
    s = motor._seen_texts({"elements": []})
    assert "ни одной надписи" in s


def test_run_not_found_names_reason(home, monkeypatch):
    """Отказ рук несёт ДИАГНОЗ пустоты: Создатель (и архитектор) в
    следующем прогоне видит корень, а не угадывает по симптому."""
    _armed_eyes(monkeypatch, descriptor={"elements": [
        {"type": "button", "text": "Пуск", "bbox": [2000, 5, 3000, 99]},
        {"type": "text", "text": "иероглиф", "bbox": [0, 900, 100, 999]},
    ]})
    out = motor.run("нажми Пуск")
    assert "не видят" in out
    assert "не прошёл" in out and "2" in out     # вот причина пустоты


def test_exam_no_pusk_names_what_eyes_read(home, monkeypatch):
    """Экзамен тоже честен: Пуска нет — говорим, ЧТО глаза читали,
    а не только «не состоялся»."""
    _armed_eyes(monkeypatch, descriptor={"elements": [
        {"type": "input", "text": "Поиск", "bbox": [100, 690, 400, 715],
         "confidence": 0.9},
        {"type": "text", "text": "C:\\Marfa>", "bbox": [64, 32, 412, 58],
         "confidence": 0.8},
    ]})
    out = motor.exam()
    assert "не состоялся" in out
    assert "Глаза читают" in out and "Поиск" in out
