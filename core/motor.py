# -*- coding: utf-8 -*-
r"""core/motor.py — РУКИ ДОМА: моторная кора по вызову (ТЗ_Руки_v1, 22.11).

Четвёртый слуга-разум — UI-TARS-7B-DPO (порт 8084). Доктрина ролей:
МОЗГ НЕ ЖМЁТ КНОПКИ, руки не думают, глаза не трогают. Создатель и мозг
дают ЗАДАНИЕ, UI-TARS превращает его в действие (click/type/scroll/
hotkey/wait/finished), СТРАЖ одобряет каждое действие, пиксельный дифф
докладывает, изменился ли экран.

VRAM-арифметика (главный урок ТЗ): глаза 3.0 + руки 5.4 = 8.4 ГБ > 6 ГБ —
вместе не живут. Поэтому руки — СЛУГА ПО ВЫЗОВУ: пока задачи нет, модель
спит на диске; пришла задача — глаза присели, руки поднялись, сделали,
руки легли, глаза вернулись (зеркально автодоктору: тот всегда начеку,
эти спят и встают).

Моторика (реальные клики и печать) включается ТОЛЬКО резолюцией
Создателя — data\hands_enabled.json, кнопка 91_hands_gate.bat. Без неё —
СУХОЙ РЕЖИМ: руки смотрят на экран, называют действие и координаты, но
мышь не трогают. Экзамен Р-0 («руки, экзамен») работает в обоих режимах:
он только СВЕРЯЕТ координаты UI-TARS с боксом Пуска из дескриптора глаз —
диалект координат не выдумываем, а измеряем.

Швы для тестов (tests/test_motor.py подменяет): _screenshot / _ask_hands /
_spawn_server / _stop_llama / _execute — реальный сервер, экран и мышь
не нужны.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import subprocess
import time
from pathlib import Path
from typing import Optional

import requests

from core import config
from safety import guard

# Протокол моторики (ТЗ 3, подтверждено внешними источниками): строго
# шесть действий. Промпт английский — модель обучена на английских
# инструкциях; задание Создателя можно писать по-русски.
HANDS_PROMPT = (
    "You are a GUI agent. Look at the screenshot and the task. "
    "Reply with EXACTLY ONE action, nothing else. Actions:\n"
    "click(x, y) | type('text') | scroll(up) | scroll(down) | "
    "hotkey('ctrl+c') | wait() | finished()\n"
    "x, y are pixel coordinates in THIS screenshot. "
    "Do not invent other actions.\n\n"
    "Task: "
)

# Порядок важен: finished/wait без аргументов не должны перехватывать
# click; ищем ПЕРВОЕ распознанное действие — UI-TARS может добавить
# рассуждение до него (Thought: ... Action: click(...)).
_ACT_PATTERNS = [
    ("click", re.compile(r"\bclick\s*\(\s*(\d+)\s*,\s*(\d+)\s*\)")),
    ("finished", re.compile(r"\bfinished\s*\(\s*\)", re.IGNORECASE)),
    ("wait", re.compile(r"\bwait\s*\(\s*\)")),
    ("type", re.compile(r"\btype\s*\(\s*['\"](.*)['\"]\s*\)", re.S)),
    ("scroll", re.compile(r"\bscroll\s*\(\s*(up|down)\s*\)", re.IGNORECASE)),
    ("hotkey", re.compile(r"\bhotkey\s*\(\s*['\"]([^'\"]+)['\"]\s*\)",
                          re.IGNORECASE)),
]


# ---------------------------------------------------------------
# Резолюция Создателя и живость слуги
# ---------------------------------------------------------------

def enabled() -> bool:
    """Включена ли моторика: data\\hands_enabled.json (кнопка 91).

    Воля Создателя живёт в data/ (в git не попадает) — как резолюция
    живого языка. Файл есть — руки двигают мышью; файла нет — сухой
    режим: план без движения. Код НИКОГДА не пишет этот файл сам.
    """
    return Path(config.HANDS_ENABLED_FILE).is_file()


def server_alive() -> bool:
    """Жив ли сервер рук (8084)."""
    try:
        return requests.get(config.HANDS_URL + "/health",
                            timeout=3).status_code == 200
    except Exception:
        return False


# ---------------------------------------------------------------
# Слуга по вызову: подъём и укладывание (VRAM-танец с глазами)
# ---------------------------------------------------------------

def _find_model() -> Optional[tuple]:
    """Найти тело и проектор UI-TARS в чулане. Точных имён нет — ищем
    по шаблону (имена в чулане могли измениться). Нет — None, честно."""
    m, p = config.HANDS_MODEL, config.HANDS_MMPROJ
    if m.is_file() and p.is_file():
        return m, p
    bodies = sorted(config.MODELS_DIR.glob("UI-TARS*Q4*.gguf"))
    projs = sorted(config.MODELS_DIR.glob("UI-TARS*mmproj*.gguf"))
    if bodies and projs:
        return bodies[0], projs[0]
    return None


def _spawn_server(model: Path, mmproj: Path) -> None:
    """Поднять сервер рук в отдельной консоли — как старт дома."""
    cmd = ('llama.cpp\\llama-server.exe -m "%s" --mmproj "%s" '
           "-ngl 99 -c %d -t 2 --temp 0.1 --host 127.0.0.1 --port %d"
           % (model, mmproj, config.HANDS_CTX_TOKENS, config.PORT_HANDS))
    subprocess.Popen(cmd, shell=True, cwd=str(config.HOME_DIR),
                     creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0))


def _stop_llama(port: int) -> bool:
    """Уложить llama-server на порту (psutil — уже в доме, Ф97).

    Ищем процесс, в чьей командной строке есть llama-server и этот порт
    (токен равен номеру порта точно, «8192» за «8083» не примется).
    """
    try:
        import psutil
    except ImportError:
        return False
    killed = False
    for proc in psutil.process_iter(["pid", "cmdline"]):
        try:
            cl = [str(c) for c in (proc.info.get("cmdline") or [])]
            if (any("llama-server" in c for c in cl)
                    and str(port) in cl):
                proc.terminate()
                killed = True
        except Exception:
            continue
    return killed


def ensure_server(wait_secs: Optional[float] = None) -> tuple:
    """Поднять слуга рук: (жив ли, честная сводка действий).

    VRAM-танец (ТЗ 4): если глаза живы — присаживаем их: 6 ГБ на двоих
    не хватает, а задача рук важнее взгляда на секунды. Глаза вернёт
    release() после задачи.
    """
    wait_secs = config.HANDS_START_WAIT_SECS if wait_secs is None else wait_secs
    if server_alive():
        return True, "руки уже на посту"
    pair = _find_model()
    if pair is None:
        return False, ("модели рук нет в чулане: жду %s и %s в %s — "
                       "проверь, доехали ли файлы"
                       % (config.HANDS_MODEL.name, config.HANDS_MMPROJ.name,
                          config.MODELS_DIR))
    model, mmproj = pair
    notes = []
    if _stop_llama(config.PORT_EYES):
        notes.append("глаза присели (VRAM 6 ГБ: двоим не хватит)")
    try:
        _spawn_server(model, mmproj)
        notes.append("руки поднимаются (Q4 с NVMe — десятки секунд)")
    except Exception as e:
        return False, "; ".join(notes) + "; не поднялись: %s" % e
    deadline = time.time() + wait_secs
    while time.time() < deadline:
        if server_alive():
            notes.append("руки на посту")
            return True, "; ".join(notes)
        time.sleep(3.0)
    return False, "; ".join(notes) + " — не ожили за %.0f с, смотри консоль рук" % wait_secs


def release() -> str:
    """Руки ложатся, глаза возвращаются — VRAM снова принадлежит зрению.

    Глаза поднимаем той же командой, которой их лечит доктор
    (start_marfa.json → eyes_cmd): одна истина о том, как слуга оживает.
    """
    stopped = _stop_llama(config.PORT_HANDS)
    note = "руки легли; " if stopped else "рук на посту не было; "
    try:
        from core import doctor
        actions = doctor.heal(["eyes"])
        note += "; ".join(a.replace("глаза 8083: ", "") for a in actions)
    except Exception as e:
        note += "глаза не поднять: %s" % e
    return note


# ---------------------------------------------------------------
# Парсер действий (ТЗ 3: мусор = честный отказ, не «лучший гесс»)
# ---------------------------------------------------------------

def parse_action(text: str) -> dict:
    """Первое распознанное действие в ответе модели.

    {"name": click/type/scroll/hotkey/wait/finished, "args": (...), "raw": ...}
    Ничего не узнали — {"name": "unknown"}: руки откажутся честно.
    """
    for name, rx in _ACT_PATTERNS:
        m = rx.search(text or "")
        if m:
            return {"name": name, "args": m.groups(), "raw": m.group(0)}
    return {"name": "unknown", "args": (),
            "raw": (text or "").strip()[:200]}


def scale_point(x: int, y: int, real_size, sent_size) -> tuple:
    """Координаты скриншота -> пиксели реального экрана.

    Модель видит СЖАТЫЙ кадр (шириной sent_size[0]); мышь живёт в
    реальном разрешении (real_size[0]). Без масштабирования клик ушёл
    бы в левый верхний угол — это и есть «диалект координат» из ТЗ.
    """
    if not sent_size or not sent_size[0] or not real_size:
        return int(x), int(y)
    kx = float(real_size[0]) / float(sent_size[0])
    ky = float(real_size[1]) / float(sent_size[1])
    return int(round(x * kx)), int(round(y * ky))


# ---------------------------------------------------------------
# СТРАЖ моторики (ТЗ 6): whitelist — код, не мнение модели
# ---------------------------------------------------------------

def guard_action(act: dict, real_size, sent_size) -> guard.Verdict:
    """Вердикт стража на ОДНО действие рук."""
    name = act["name"]
    if name == "unknown":
        return guard.Verdict("HIGH", "deny",
                             "руки не поняли действие: %s" % act["raw"][:120],
                             "hands.parse")
    if name == "click":
        x, y = scale_point(int(act["args"][0]), int(act["args"][1]),
                           real_size, sent_size)
        if not (0 <= x < real_size[0] and 0 <= y < real_size[1]):
            return guard.Verdict("HIGH", "deny",
                                 "клик за краем экрана (%d, %d)" % (x, y),
                                 "hands.bounds")
        return guard.Verdict("MEDIUM", "allow",
                             "клик (%d, %d)" % (x, y), "hands.click")
    if name == "type":
        text = act["args"][0] or ""
        if len(text) > config.HANDS_TYPE_LIMIT:
            return guard.Verdict("HIGH", "deny",
                                 "печать длиннее %d символов"
                                 % config.HANDS_TYPE_LIMIT, "hands.type.len")
        v = guard.check_secrets(text)
        if not v.allowed():
            return v
        if any(ord(c) > 127 for c in text):
            return guard.Verdict("HIGH", "deny",
                                 "печать кириллицы/не-латиницы пока не умею "
                                 "(Круг Р-4: буфер обмена)", "hands.type.charset")
        return guard.Verdict("MEDIUM", "allow",
                             "печать %d символов" % len(text), "hands.type")
    if name == "hotkey":
        key = (act["args"][0] or "").strip().lower()
        if key not in config.HANDS_HOTKEY_WHITELIST:
            return guard.Verdict("HIGH", "deny",
                                 "сочетание «%s» не в whitelist (№19)" % key,
                                 "hands.hotkey.whitelist")
        return guard.Verdict("MEDIUM", "allow", "hotkey %s" % key,
                             "hands.hotkey")
    # scroll / wait / finished — простые, без координат и текста
    return guard.Verdict("LOW", "allow", name, "hands.simple")


# ---------------------------------------------------------------
# Исполнение (pyautogui — лениво, честная ошибка без него)
# ---------------------------------------------------------------

def _execute(act: dict, real_size, sent_size) -> str:
    """Исполнить одобренное действие. Возвращает честную сводку."""
    try:
        import pyautogui
    except ImportError as e:
        return ("не исполнила: нет pyautogui (%s) — "
                "venv\\Scripts\\pip install pyautogui" % e)
    name = act["name"]
    if name == "click":
        x, y = scale_point(int(act["args"][0]), int(act["args"][1]),
                           real_size, sent_size)
        pyautogui.click(x, y)
        return "кликнула (%d, %d)" % (x, y)
    if name == "type":
        text = act["args"][0] or ""
        pyautogui.write(text, interval=0.02)
        return "напечатала %d символов" % len(text)
    if name == "scroll":
        up = act["args"][0].lower() == "up"
        pyautogui.scroll(300 if up else -300)
        return "прокрутила %s" % ("вверх" if up else "вниз")
    if name == "hotkey":
        parts = [p.strip() for p in act["args"][0].lower().split("+")
                 if p.strip()]
        pyautogui.hotkey(*parts)
        return "нажала %s" % "+".join(parts)
    if name == "wait":
        time.sleep(1.0)
        return "подождала секунду"
    return ""


# ---------------------------------------------------------------
# Пиксельная сверка (урок v1.5: истину говорят пиксели)
# ---------------------------------------------------------------

def _pixel_diff(before_b64: str, after_b64: str, box=None) -> Optional[float]:
    """Доля изменившихся пикселей (0..1) в области клика.

    None — сравнить не смогли (нет PIL / разные размеры): честно не
    выдумываем «изменилось». diff > 30 по яркости считаем изменением.
    """
    try:
        import io as _io
        import base64 as _b64
        from PIL import Image
        a = Image.open(_io.BytesIO(_b64.b64decode(before_b64))).convert("RGB")
        b = Image.open(_io.BytesIO(_b64.b64decode(after_b64))).convert("RGB")
        if box:
            pad = 24
            box = (max(0, box[0] - pad), max(0, box[1] - pad),
                   min(a.width, box[2] + pad), min(a.height, box[3] + pad))
            a, b = a.crop(box), b.crop(box)
        if a.size != b.size:
            return None
        from PIL import ImageChops
        diff = ImageChops.difference(a, b).convert("L")
        hist = diff.histogram()
        changed = sum(hist[30:])
        return changed / float(a.width * a.height)
    except Exception:
        return None


# ---------------------------------------------------------------
# Лог действий (правило 6.6: логи — истина)
# ---------------------------------------------------------------

def _log_act(rec: dict) -> None:
    try:
        p = Path(config.HANDS_LOG_FILE)
        p.parent.mkdir(parents=True, exist_ok=True)
        rec = dict(rec)
        rec.setdefault("ts", dt.datetime.now().isoformat(timespec="seconds"))
        with p.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except OSError:
        pass


def _lesson(kind: str, text: str) -> None:
    try:
        from evolution.journal import log_lesson
        log_lesson(kind, text)
    except Exception:
        pass


# ---------------------------------------------------------------
# Швы HTTP и экрана (тесты подменяют)
# ---------------------------------------------------------------

def _screenshot():
    """Скриншот для рук — тем же инструментом, что и глаза."""
    from core import eyes
    if eyes._VISION_ERROR:
        raise RuntimeError("глаза не готовы: " + eyes._VISION_ERROR)
    return eyes._screenshot_b64(eyes.WORK_WIDTH)


def _ask_hands(task: str, b64: str, max_tokens: int = 400) -> str:
    """Один вопрос моторной коре: скриншот + задание → текст действия."""
    body = {
        "model": "ui-tars",
        "temperature": 0.1,
        "top_p": 0.8,
        "max_tokens": max_tokens,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "image_url",
                 "image_url": {"url": "data:image/png;base64," + b64}},
                {"type": "text", "text": HANDS_PROMPT + task},
            ],
        }],
    }
    r = requests.post(config.HANDS_URL + "/v1/chat/completions",
                      json=body, timeout=config.HANDS_TIMEOUT_SEC)
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


# ---------------------------------------------------------------
# Цикл задачи (ТЗ 5) и экзамен Р-0 (ТЗ 7)
# ---------------------------------------------------------------

def run(task: str, max_steps: Optional[int] = None) -> str:
    """Выполнить задание руками: замкнутый цикл скриншот → действие.

    Каждый шаг: скриншот → UI-TARS → парсер → СТРАЖ → (исполнить |
    сухой режим) → пиксельная сверка. Бюджеты: шаги и секунды (ТЗ 6:
    зависла — честный отказ, не вечный цикл). В конце слуга ложится,
    глаза возвращаются.
    """
    max_steps = config.HANDS_MAX_STEPS if max_steps is None else max_steps
    task = (task or "").strip().strip(",;:.! ")
    if not task:
        return ("руки ждут задание: «руки нажми Пуск». "
                "Экзамен координат — «руки, экзамен»")
    mode = ("моторика ВКЛЮЧЕНА (резолюция Создателя)" if enabled()
            else "сухой режим: план без кликов (включить — кнопка 91)")
    ok, note = ensure_server()
    if not ok:
        _log_act({"task": task, "ok": False, "note": note})
        return ("РУКИ — задание «%s» НЕ начато: %s" % (task, note))
    lines = ["РУКИ — задание: %s [%s]" % (task, mode), note]
    started = time.time()
    done = False
    try:
        for step in range(1, max_steps + 1):
            if time.time() - started > config.HANDS_TASK_BUDGET_SEC:
                lines.append("бюджет %d с кончился — честно останавливаюсь, "
                             "задание не завершено"
                             % config.HANDS_TASK_BUDGET_SEC)
                break
            b64, real, sent = _screenshot()
            raw = _ask_hands(task, b64)
            act = parse_action(raw)
            v = guard_action(act, real, sent)
            guard.decide(v, {"tool": "ui_action", "task": task, "step": step})
            _log_act({"task": task, "step": step, "action": act["raw"],
                      "verdict": v.to_dict(), "mode":
                      "motor" if enabled() else "dry"})
            if not v.allowed():
                lines.append("шаг %d: %s — СТРАЖ ОТКАЗАЛ: %s"
                             % (step, act["raw"], v.reason))
                _lesson("руки-страж", "%s: %s" % (task, v.reason))
                return "\n".join(lines + [release()])
            if act["name"] == "finished":
                lines.append("шаг %d: finished() — задание выполнено"
                             % step)
                done = True
                break
            lines.append("шаг %d: %s" % (step, act["raw"]))
            if act["name"] == "wait":
                time.sleep(1.0)
                lines.append("  подождала секунду")
                continue
            if enabled():
                lines.append("  " + _execute(act, real, sent))
                if act["name"] == "click":
                    x, y = int(act["args"][0]), int(act["args"][1])
                    b64_after, _, _ = _screenshot()
                    frac = _pixel_diff(b64, b64_after, (x - 8, y - 8,
                                                        x + 8, y + 8))
                    if frac is not None:
                        lines.append("  сверка пикселей: у клика изменилось "
                                     "%.0f%% кадра" % (frac * 100))
            else:
                lines.append("  (сухой режим: не трогаю — включить кнопкой 91)")
        else:
            lines.append("лимит %d шагов кончился, finished() не прозвучало — "
                         "честно: задание не завершено" % max_steps)
    except Exception as e:
        lines.append("ошибка цикла рук: %s" % e)
        _lesson("руки-ошибка", "%s: %s" % (task, e))
    finally:
        lines.append(release())
    _log_act({"task": task, "ok": done, "steps": len(lines)})
    return "\n".join(lines)


def exam() -> str:
    """Р-0 (ТЗ 7): живой экзамен — сверка диалекта координат.

    Глаза говорят, где Пуск (дескриптор, bbox); руки целятся туда же
    (UI-TARS, click). Обе системы смотрят на ОДИН кадр одной ширины —
    координаты сравнимы напрямую. Кликов нет: экзамен только смотрит.
    Пуск не виден — честно «не состоялся» (меню Пуска должно быть на
    экране: наведи мышь на панель задач или нажми Win, потом «руки,
    экзамен»).
    """
    lines = ["ЭКЗАМЕН РУК (Р-0): сверка координат с дескриптором глаз"]
    try:
        from core import eyes
        if eyes._VISION_ERROR:
            return "\n".join(lines + ["глаза не готовы: " + eyes._VISION_ERROR])
        d = eyes.describe()
    except Exception as e:
        return "\n".join(lines + ["не смогла спросить глаза: %s" % e])
    el = None
    for cand in d.get("elements", []):
        t = str(cand.get("text", "")).lower()
        if "пуск" in t or "start" in t:
            el = cand
            break
    if el is None:
        return "\n".join(
            lines + ["глаза не нашли Пуск в дескрипторе — экзамен не "
                     "состоялся: открой меню Пуска (клавиша Win) и скажи "
                     "«руки, экзамен» ещё раз"])
    bbox = el.get("bbox") or [0, 0, 0, 0]
    lines.append("глаза: «%s» в %s (уверенность %s)"
                 % (el.get("text"), bbox, el.get("confidence", "?")))
    ok, note = ensure_server()
    if not ok:
        return "\n".join(lines + [note, "руки не поднялись — экзамен не состоялся"])
    try:
        b64, real, sent = _screenshot()
        raw = _ask_hands("click the Start button (Пуск)", b64)
        act = parse_action(raw)
        if act["name"] != "click":
            _log_act({"exam": True, "action": act["raw"], "ok": False})
            return "\n".join(
                lines + ["руки ответили не кликом: %s — экзамен не состоялся"
                         % act["raw"], release()])
        x, y = int(act["args"][0]), int(act["args"][1])
        inside = (bbox[0] <= x <= bbox[2] and bbox[1] <= y <= bbox[3])
        cx, cy = (bbox[0] + bbox[2]) // 2, (bbox[1] + bbox[3]) // 2
        dist = int(((x - cx) ** 2 + (y - cy) ** 2) ** 0.5)
        lines.append("руки целились в (%d, %d) — %s (до центра бокса %d px)"
                     % (x, y, "ПОПАДАНИЕ" if inside else "мимо", dist))
        verdict = ("диалект координат подтверждён — моторику можно включать "
                   "(кнопка 91), если Создатель доверяет" if inside else
                   "координаты НЕ совпали — диалект другой: НЕ включай "
                   "моторику, калибруем (скажи архитектору цифры выше)")
        lines.append("вердикт Р-0: " + verdict)
        _log_act({"exam": True, "eyes_bbox": bbox, "hands_point": [x, y],
                  "inside": inside, "dist": dist})
        _lesson("руки-экзамен", "%s: %s" % ((x, y), verdict))
        return "\n".join(lines + [release()])
    except Exception as e:
        return "\n".join(lines + ["ошибка экзамена: %s" % e, release()])
