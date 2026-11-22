# -*- coding: utf-8 -*-
r"""tests/test_motor.py — РУКИ ДОМА: моторная кора по вызову (ТЗ_Руки_v1).

Якоря лечения 22.11 («руки собраны и обучены — почему не подключены»):
парсер действий строг (мусор = отказ, не «лучший гесс»), страж-whitelist
не пускает ни клавишу мимо списка, моторика — ТОЛЬКО по резолюции
Создателя (сухой режим по умолчанию), координаты масштабируются из
кадра модели в пиксели экрана (диалект координат), бюджет задачи не
даёт крутиться вечно, экзамен Р-0 сверяет руки с глазами.

Швы: _screenshot / _ask_hands / ensure_server / release / _stop_llama /
_spawn_server — подменяются, реальный сервер, экран и мышь не трогаются.
"""
import json
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import config, motor  # noqa: E402
from safety import guard  # noqa: E402

REAL = (1920, 1080)          # реальный экран
SENT = (1280, 720)           # кадр, который видит модель


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
    monkeypatch.setattr(config, "HANDS_MODEL",
                        tmp_path / "models" / "UI-TARS-7B-DPO.Q4_K_M.gguf")
    monkeypatch.setattr(config, "HANDS_MMPROJ",
                        tmp_path / "models" / "UI-TARS-7B-DPO.mmproj-f16.gguf")
    monkeypatch.setattr(config, "GUARD_LOG_FILE",
                        tmp_path / "logs" / "guard_log.jsonl")
    return tmp_path


# ---------- парсер действий (ТЗ 3) ----------

def test_parse_all_six_actions():
    assert motor.parse_action("click(640, 360)")["name"] == "click"
    assert motor.parse_action("type('hello')")["name"] == "type"
    assert motor.parse_action("scroll(up)")["name"] == "scroll"
    assert motor.parse_action("scroll(DOWN)")["name"] == "scroll"
    assert motor.parse_action("hotkey('ctrl+c')")["name"] == "hotkey"
    assert motor.parse_action("wait()")["name"] == "wait"
    assert motor.parse_action("finished()")["name"] == "finished"


def test_parse_click_coordinates():
    act = motor.parse_action("click(100, 200)")
    assert act["args"] == ("100", "200")


def test_parse_after_thought():
    """UI-TARS может рассуждать до действия — берём действие из хвоста."""
    act = motor.parse_action("Thought: нужно нажать меню. Action: click(10, 20)")
    assert act["name"] == "click" and act["args"] == ("10", "20")


def test_parse_garbage_is_unknown():
    """Мусор = честный отказ: никакой «лучший гесс» (ТЗ 3)."""
    act = motor.parse_action("я бы нажал куда-нибудь влево")
    assert act["name"] == "unknown"
    assert "влево" in act["raw"]


# ---------- масштаб координат (диалект из ТЗ, измеряется на Р-0) ----------

def test_scale_point_screenshot_to_screen():
    x, y = motor.scale_point(640, 360, REAL, SENT)
    assert (x, y) == (960, 540)           # 1280x720 -> 1920x1080


def test_scale_point_zero_and_edge():
    assert motor.scale_point(0, 0, REAL, SENT) == (0, 0)
    assert motor.scale_point(1280, 720, REAL, SENT) == (1920, 1080)


# ---------- СТРАЖ моторики (ТЗ 6: список — код, не мнение модели) ----------

def test_guard_click_inside_allowed(home):
    v = motor.guard_action({"name": "click", "args": ("640", "360"),
                            "raw": "click(640, 360)"}, REAL, SENT)
    assert v.allowed()


def test_guard_click_outside_denied(home):
    # (4000, 4000) в кадре модели -> (6000, 6000) на экране: за краем
    v = motor.guard_action({"name": "click", "args": ("4000", "4000"),
                            "raw": ""}, REAL, SENT)
    assert not v.allowed() and "краем" in v.reason


def test_guard_hotkey_whitelist(home):
    ok = motor.guard_action({"name": "hotkey", "args": ("ctrl+c",),
                             "raw": ""}, REAL, SENT)
    assert ok.allowed()
    bad = motor.guard_action({"name": "hotkey", "args": ("alt+f4",),
                              "raw": ""}, REAL, SENT)
    assert not bad.allowed() and "whitelist" in bad.reason


def test_guard_type_secrets_banned(home):
    """Секреты не печатаются — канарейки и токены банятся на парсинге."""
    guard.ensure_canaries()
    canary = guard.ensure_canaries()[0]
    v = motor.guard_action({"name": "type", "args": ("see " + canary,),
                            "raw": ""}, REAL, SENT)
    assert not v.allowed()


def test_guard_type_cyrillic_denied(home):
    v = motor.guard_action({"name": "type", "args": ("привет",),
                            "raw": ""}, REAL, SENT)
    assert not v.allowed() and "латиниц" in v.reason


def test_guard_type_too_long_denied(home):
    v = motor.guard_action(
        {"name": "type", "args": ("a" * (config.HANDS_TYPE_LIMIT + 1),),
         "raw": ""}, REAL, SENT)
    assert not v.allowed()


def test_guard_unknown_denied(home):
    v = motor.guard_action({"name": "unknown", "args": (), "raw": "мусор"},
                           REAL, SENT)
    assert not v.allowed()


def test_guard_simple_actions_low_risk(home):
    for name, args in (("scroll", ("up",)), ("wait", ()), ("finished", ())):
        v = motor.guard_action({"name": name, "args": args, "raw": ""},
                               REAL, SENT)
        assert v.allowed() and v.level == "LOW", name


# ---------- резолюция Создателя: сухой режим по умолчанию ----------

def test_disabled_by_default(home):
    assert motor.enabled() is False


def test_enabled_by_creators_file(home):
    config.HANDS_ENABLED_FILE.parent.mkdir(parents=True, exist_ok=True)
    config.HANDS_ENABLED_FILE.write_text('{"resolution": "кнопка 91"}',
                                         encoding="utf-8")
    assert motor.enabled() is True


# ---------- слуга по вызову: VRAM-танец ----------

def test_ensure_server_model_missing_honest(home):
    ok, note = motor.ensure_server(wait_secs=0.1)
    assert ok is False and "чулане" in note


def test_ensure_server_vram_dance(home, monkeypatch):
    """Глаза живы — присели; модель есть — руки поднялись."""
    config.MODELS_DIR.mkdir(parents=True, exist_ok=True)
    config.HANDS_MODEL.write_bytes(b"x")
    config.HANDS_MMPROJ.write_bytes(b"x")
    stopped, spawned, alive = [], [], []

    def fake_stop(port):
        stopped.append(port)
        return port == config.PORT_EYES

    monkeypatch.setattr(motor, "_stop_llama", fake_stop)

    def spawn(m, p):
        spawned.append(m.name)
        alive.append(1)                      # сервер ожил после спавна

    monkeypatch.setattr(motor, "_spawn_server", spawn)
    monkeypatch.setattr(motor, "server_alive", lambda: bool(alive))

    ok, note = motor.ensure_server(wait_secs=5.0)
    assert ok is True
    assert stopped == [config.PORT_EYES]         # глаза присели
    assert spawned == [config.HANDS_MODEL.name]  # руки поднялись
    assert "присели" in note


def test_release_stops_hands_and_heals_eyes(home, monkeypatch):
    calls = []
    monkeypatch.setattr(motor, "_stop_llama",
                        lambda port: calls.append(port) or True)
    monkeypatch.setattr("core.doctor.heal",
                        lambda ids: calls.append("heal:" + ids[0]) or
                        ["глаза 8083: поднимаю"])
    note = motor.release()
    assert calls[0] == config.PORT_HANDS
    assert "heal:eyes" in calls
    assert "поднимаю" in note


# ---------- цикл задачи ----------

def _armed(monkeypatch, actions, mode_dry=True):
    """Руки в песочнице: сервер жив, экран один и тот же, действия — сценарий."""
    monkeypatch.setattr(motor, "server_alive", lambda: True)
    monkeypatch.setattr(motor, "ensure_server", lambda wait_secs=None: (True, "на посту"))
    monkeypatch.setattr(motor, "release", lambda: "руки легли (шов)")
    monkeypatch.setattr(motor, "_screenshot",
                        lambda: ("b64", REAL, SENT))
    seq = list(actions)
    monkeypatch.setattr(motor, "_ask_hands", lambda task, b64: seq.pop(0))
    if mode_dry:
        monkeypatch.setattr(motor, "enabled", lambda: False)
    else:
        monkeypatch.setattr(motor, "enabled", lambda: True)
        monkeypatch.setattr(motor, "_execute",
                            lambda act, real, sent: "исполнила: %s" % act["raw"])
    return seq


def test_run_dry_mode_plans_without_touching(home, monkeypatch):
    """Без резолюции Создателя мышь не трогается — только план."""
    _armed(monkeypatch, ["click(640, 360)", "finished()"], mode_dry=True)
    out = motor.run("нажми Пуск")
    assert "сухой режим" in out
    assert "click(640, 360)" in out
    assert "finished()" in out and "выполнено" in out
    assert "не трогаю" in out


def test_run_motor_mode_executes(home, monkeypatch):
    _armed(monkeypatch, ["click(640, 360)", "finished()"], mode_dry=False)
    out = motor.run("нажми Пуск")
    assert "исполнила: click(640, 360)" in out
    assert "сухой режим" not in out


def test_run_guard_denial_stops_and_reports(home, monkeypatch):
    _armed(monkeypatch, ["click(9999, 9999)"], mode_dry=True)
    out = motor.run("кликни в угол вселенной")
    assert "СТРАЖ ОТКАЗАЛ" in out
    assert "краем экрана" in out


def test_run_step_budget_is_honest(home, monkeypatch):
    """Лимит шагов кончился, finished() не прозвучал — честный отказ,
    не вечный цикл (ТЗ 6)."""
    _armed(monkeypatch, ["wait()"] * 20, mode_dry=True)
    monkeypatch.setattr(config, "HANDS_MAX_STEPS", 3)
    out = motor.run("вечная задача")
    assert "лимит 3 шагов" in out
    assert "не завершено" in out


def test_run_empty_task_gets_hint(home):
    out = motor.run("")
    assert "задание" in out


def test_run_server_not_up_honest(home, monkeypatch):
    monkeypatch.setattr(motor, "ensure_server",
                        lambda wait_secs=None: (False, "модели рук нет"))
    out = motor.run("нажми Пуск")
    assert "НЕ начато" in out and "модели рук нет" in out


def test_run_logs_to_hands_log(home, monkeypatch):
    """Правило 6.6: каждое действие — строка в лог, логи — истина."""
    _armed(monkeypatch, ["click(10, 20)", "finished()"], mode_dry=True)
    motor.run("тест")
    log = [json.loads(l) for l in
           config.HANDS_LOG_FILE.read_text(encoding="utf-8").splitlines()]
    assert any(r.get("action") == "click(10, 20)" for r in log)
    assert all(r.get("mode") == "dry" for r in log if "action" in r)


# ---------- экзамен Р-0 (ТЗ 7) ----------

# Пуск в координатах ОТПРАВЛЕННОГО кадра 1280×720 (экран 1920×1080 / 1.5):
# экран [0, 1040, 96, 1080] -> кадр [0, 693, 64, 720]. Урок v3 глаз:
# bbox обязан жить внутри кадра — валидатор глаз бракует всё за краем.
DESCRIPTOR_PUSK = {
    "description": "рабочий стол",
    "elements": [{"type": "button", "text": "Пуск",
                  "bbox": [0, 693, 64, 720], "confidence": 0.9}],
}


def test_exam_hit(home, monkeypatch):
    """Координаты рук попали в бокс Пуска из дескриптора глаз —
    диалект подтверждён, моторику можно включать."""
    monkeypatch.setattr(motor, "server_alive", lambda: True)
    monkeypatch.setattr(motor, "ensure_server", lambda wait_secs=None: (True, "на посту"))
    monkeypatch.setattr(motor, "release", lambda: "руки легли (шов)")
    monkeypatch.setattr(motor, "_screenshot", lambda: ("b64", SENT, SENT))
    monkeypatch.setattr(motor, "_ask_hands",
                        lambda task, b64: "click(32, 706)")
    from core import eyes
    monkeypatch.setattr(eyes, "_VISION_ERROR", None)
    monkeypatch.setattr(eyes, "_screenshot_b64",
                        lambda width=1280: ("b64", SENT, SENT))
    monkeypatch.setattr(eyes, "_post_chat",
                        lambda body: {"choices": [{"message": {"content":
                         json.dumps(DESCRIPTOR_PUSK, ensure_ascii=False)}}]})
    out = motor.exam()
    assert "ПОПАДАНИЕ" in out
    assert "подтверждён" in out


def test_exam_miss_reports_numbers(home, monkeypatch):
    monkeypatch.setattr(motor, "server_alive", lambda: True)
    monkeypatch.setattr(motor, "ensure_server", lambda wait_secs=None: (True, "на посту"))
    monkeypatch.setattr(motor, "release", lambda: "руки легли (шов)")
    monkeypatch.setattr(motor, "_screenshot", lambda: ("b64", SENT, SENT))
    monkeypatch.setattr(motor, "_ask_hands",
                        lambda task, b64: "click(600, 300)")
    from core import eyes
    monkeypatch.setattr(eyes, "_VISION_ERROR", None)
    monkeypatch.setattr(eyes, "_screenshot_b64",
                        lambda width=1280: ("b64", SENT, SENT))
    monkeypatch.setattr(eyes, "_post_chat",
                        lambda body: {"choices": [{"message": {"content":
                         json.dumps(DESCRIPTOR_PUSK, ensure_ascii=False)}}]})
    out = motor.exam()
    assert "мимо" in out and "НЕ совпали" in out


def test_exam_hallucinated_pusk_bbox_dropped(home, monkeypatch):
    """Урок v3 (честная геометрия): глаза назвали Пуск за краем кадра —
    валидатор выбросил бокс, экзамен честно не состоялся, а не мерял
    диалект по выдуманным цифрам."""
    monkeypatch.setattr(motor, "server_alive", lambda: True)
    monkeypatch.setattr(motor, "ensure_server", lambda wait_secs=None: (True, "на посту"))
    monkeypatch.setattr(motor, "release", lambda: "руки легли (шов)")
    hallucinated = {
        "description": "рабочий стол",
        "elements": [{"type": "button", "text": "Пуск",
                      "bbox": [0, 1040, 96, 1096], "confidence": 0.9}],
    }
    from core import eyes
    monkeypatch.setattr(eyes, "_VISION_ERROR", None)
    monkeypatch.setattr(eyes, "_screenshot_b64",
                        lambda width=1280: ("b64", SENT, SENT))
    monkeypatch.setattr(eyes, "_post_chat",
                        lambda body: {"choices": [{"message": {"content":
                         json.dumps(hallucinated, ensure_ascii=False)}}]})
    out = motor.exam()
    assert "не состоялся" in out or "не нашли Пуск" in out


def test_exam_no_pusk_honest(home, monkeypatch):
    monkeypatch.setattr(motor, "release", lambda: "шов")
    from core import eyes
    monkeypatch.setattr(eyes, "_VISION_ERROR", None)
    monkeypatch.setattr(eyes, "_screenshot_b64",
                        lambda width=1280: ("b64", SENT, SENT))
    monkeypatch.setattr(eyes, "_post_chat",
                        lambda body: {"choices": [{"message": {"content":
                         json.dumps({"elements": []})}}]})
    out = motor.exam()
    assert "не состоялся" in out


# ---------- пиксельная сверка ----------

def _png_b64(color):
    import base64
    import io
    from PIL import Image
    buf = io.BytesIO()
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
    assert config.PORT_HANDS == 8084
    assert config.HANDS_MAX_STEPS <= 10          # бюджет не расползается
    assert "alt+f4" not in config.HANDS_HOTKEY_WHITELIST
    assert "ctrl+c" in config.HANDS_HOTKEY_WHITELIST
    assert motor.HANDS_PROMPT.count("click(x, y)") == 1
    assert "finished()" in motor.HANDS_PROMPT
