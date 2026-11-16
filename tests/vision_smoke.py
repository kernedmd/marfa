# -*- coding: utf-8 -*-
"""Марфа — Г-1, дымовой тест глаз (8083) при работающем мозге (8082). v1.1

Запуск из корня дома:
    venv\\Scripts\\python.exe tests\\vision_smoke.py
Опции:
    --width 1600     ширина снимка для VLM (1280 — план Б по скорости)
    --click-start    полный замкнутый цикл: клик по «Пуск» + проверка меню
Зависимости: venv\\Scripts\\pip install mss pyautogui

Совет №1 — JSON по грамматике: каждый запрос несёт response_format/json_schema;
если сборка сервера его не знает, поле игнорируется и работает парсер-фолбэк.
Совет №2 — DPI: процесс делается DPI-aware, снимок и мышь говорят в физических
пикселях; тест «Пуск» проверяет пересчёт координат снимка в физические.
Совет №3 — Pascal/ViT: если ответ дольше 8 с, тест сам повторяет проход на 1280.
"""
import argparse
import base64
import ctypes
import io
import json
import sys
import time

import requests
from PIL import Image

try:
    import mss
except ImportError:
    sys.exit("Нет модуля mss: venv\\Scripts\\pip install mss")

# --- DPI-awareness: физические пиксели для снимка И мыши (совет №2) --------
if sys.platform == "win32":
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # per-monitor aware
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

BRAIN = "http://127.0.0.1:8082"
EYES = "http://127.0.0.1:8083"

PROMPT = (
    "Ты — зрительный сенсор интерфейсов. Опиши экран строго одним JSON без пояснений:\n"
    '{"active_window":"...","elements":[{"type":"button|input|link|menu|text|icon|image",'
    '"text":"...","bbox":[x1,y1,x2,y2],"confidence":0.0}],"summary":"одно предложение"}\n'
    "Правила: bbox в пикселях входного изображения; не выдумывай элементы; "
    "нечитаемое — confidence меньше 0.4; лучше меньше элементов, чем выдуманные."
)

START_PROMPT = (
    "Найди на панели задач кнопку «Пуск» (левый нижний угол, логотип Windows). "
    "Ответь строго одним JSON без пояснений: "
    '{"found":true,"bbox":[x1,y1,x2,y2],"confidence":0.0}. '
    'Если кнопки не видно: {"found":false,"bbox":null,"confidence":0}. '
    "Координаты — в пикселях входного изображения. Не выдумывай."
)

MENU_PROMPT = (
    "Посмотри на экран. Открыто ли сейчас меню «Пуск» (панель со списком программ)? "
    'Ответь строго JSON: {"menu_open": true} или {"menu_open": false}.'
)

# --- Схема дескриптора для response_format (совет №1) ----------------------
SCHEMA = {
    "type": "object",
    "properties": {
        "active_window": {"type": "string"},
        "elements": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "type": {"type": "string"},
                    "text": {"type": "string"},
                    "bbox": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "minItems": 4,
                        "maxItems": 4,
                    },
                    "confidence": {"type": "number"},
                },
                "required": ["type", "bbox"],
            },
        },
        "summary": {"type": "string"},
    },
    "required": ["elements"],
}


def health(url):
    try:
        return requests.get(url + "/health", timeout=5).status_code == 200
    except Exception:
        return False


def screenshot(width):
    with mss.mss() as sct:
        raw = sct.grab(sct.monitors[1])  # основной монитор, физические пиксели
        img = Image.frombytes("RGB", raw.size, raw.rgb)
    scale = width / img.width
    small = img.resize((width, round(img.height * scale)), Image.LANCZOS)
    buf = io.BytesIO()
    small.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode()
    return b64, img.size, small.size


def ask_eyes(b64, prompt, max_tokens=1500):
    """Запрос к глазам. Сначала с response_format/json_schema; если сервер
    отклонил (код >= 400) — повтор без грамматики, дальше парсер-фолбэк."""
    for use_schema in (True, False):
        body = {
            "model": "vlm",
            "temperature": 0.1,
            "top_p": 0.8,
            "max_tokens": max_tokens,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "image_url",
                     "image_url": {"url": "data:image/png;base64," + b64}},
                    {"type": "text", "text": prompt},
                ],
            }],
        }
        if use_schema:
            body["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "screen_descriptor", "schema": SCHEMA},
            }
        r = requests.post(EYES + "/v1/chat/completions", json=body, timeout=240)
        if use_schema and r.status_code >= 400:
            print("  response_format отклонён сервером (код %s) — "
                  "повтор без грамматики" % r.status_code)
            continue
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"], use_schema
    raise RuntimeError("глаза не ответили")


def parse_json(text):
    clean = text.strip()
    if clean.startswith("```"):
        clean = clean.strip("`").strip()
        if clean.startswith("json"):
            clean = clean[4:]
    return json.loads(clean)


def describe(width):
    """Один проход: снимок -> дескриптор. Возвращает метрики и данные."""
    t0 = time.time()
    b64, real, small = screenshot(width)
    t_shot = time.time() - t0
    t0 = time.time()
    out, schema_ok = ask_eyes(b64, PROMPT)
    t_ask = time.time() - t0
    try:
        data = parse_json(out)
        ok = "ВАЛИДНЫЙ" if isinstance(data.get("elements"), list) else "БЕЗ elements"
    except Exception as e:
        data, ok = None, "НЕВАЛИДНЫЙ (%s)" % e
    return dict(width=width, real=real, small=small, t_shot=t_shot, t_ask=t_ask,
                data=data, ok=ok, schema_ok=schema_ok, raw=out)


def calibrate_start(width, click=False):
    """Совет №2: DPI и координаты. Находим «Пуск», пересчитываем центр bbox
    в физические координаты, наводим мышь; с click=True — замкнутый цикл."""
    print("\n--- Калибровка «Пуск» (совет №2: DPI и координаты) ---")
    b64, real, small = screenshot(width)
    try:
        out, _ = ask_eyes(b64, START_PROMPT, max_tokens=100)
        d = parse_json(out)
    except Exception as e:
        print("калибровка: ответ не разобран (%s)" % e)
        return
    if not d.get("found"):
        print("Пуск не найден глазами — проверь панель задач вручную; "
              "для Г-1 не критично, но отметить")
        return
    bbox = d["bbox"]
    cx_v = (bbox[0] + bbox[2]) / 2.0
    cy_v = (bbox[1] + bbox[3]) / 2.0
    kx = real[0] / float(small[0])
    ky = real[1] / float(small[1])
    cx, cy = int(round(cx_v * kx)), int(round(cy_v * ky))
    print("bbox VLM: %s (пространство снимка %s)" % (bbox, small))
    print("центр: снимок (%d, %d) -> физические (%d, %d); коэффициенты %.3f / %.3f"
          % (cx_v, cy_v, cx, cy, kx, ky))
    try:
        import pyautogui
        pyautogui.FAILSAFE = True
    except ImportError:
        print("pyautogui нет — наведение мыши пропущено "
              "(venv\\Scripts\\pip install pyautogui)")
        return
    try:
        pyautogui.moveTo(cx, cy, duration=0.6)
    except Exception as e:
        print("moveTo не удался (%s) — проверь координаты вручную" % e)
        return
    print("мышь наведена на (%d, %d) — проверь глазами: курсор на кнопке «Пуск»?"
          % (cx, cy))
    if not click:
        print("полный цикл (клик + проверка меню): перезапусти с --click-start")
        return
    pyautogui.click()
    time.sleep(2.0)
    b642, real2, small2 = screenshot(width)
    try:
        out2, _ = ask_eyes(b642, MENU_PROMPT, max_tokens=50)
        print("глаза после клика:", parse_json(out2))
    except Exception:
        print("глаза после клика (сырой ответ):", out2[:200])
    pyautogui.press("esc")
    print("нажат Esc — меню закрыто (рабочий стол чист)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--width", type=int, default=1600,
                    help="ширина снимка для VLM: 1600 (умолчание), 1280, 1920")
    ap.add_argument("--click-start", action="store_true",
                    help="клик по «Пуск» + проверка меню (замкнутый цикл)")
    args = ap.parse_args()

    print("мозг 8082:", "жив" if health(BRAIN) else "НЕ ОТВЕЧАЕТ (продолжаем)")
    if not health(EYES):
        print("глаза 8083: НЕ ОТВЕЧАЮТ — остановка")
        sys.exit(1)
    print("глаза 8083: живы")

    r = describe(args.width)
    print("снимок: %s -> %s, %.2f с" % (r["real"], r["small"], r["t_shot"]))
    print("ответ глаз: %.1f с; response_format: %s"
          % (r["t_ask"],
             "принят сервером" if r["schema_ok"] else "НЕ принят (фолбэк-парсер)"))
    print("JSON:", r["ok"])
    if r["data"]:
        for el in r["data"].get("elements", [])[:12]:
            print("  ", el)
    else:
        print("СЫРОЙ ОТВЕТ:\n", r["raw"][:2000])

    # Совет №3: Pascal без тензорных ядер — если медленно, автоповтор на 1280
    if r["t_ask"] > 8 and args.width > 1280:
        print("\n--- Медленнее 8 с: автоповтор на ширине 1280 (план Б, совет №3) ---")
        r2 = describe(1280)
        print("1280: ответ %.1f с против %.1f с на %d; JSON: %s"
              % (r2["t_ask"], r["t_ask"], args.width, r2["ok"]))
        if r2["data"]:
            for el in r2["data"].get("elements", [])[:6]:
                print("  ", el)

    calibrate_start(args.width, click=args.click_start)

    print("\n--- Самопроверка по критериям Г-1 ---")
    print("JSON валиден: %s" % ("да" if r["data"] else "НЕТ"))
    print("время ответа <= 8 с: %s (%.1f с)"
          % ("да" if r["t_ask"] <= 8 else "НЕТ", r["t_ask"]))
    print("живость 30B, VRAM и RAM проверь вручную: критерии 1-4, nvidia-smi")


if __name__ == "__main__":
    main()
