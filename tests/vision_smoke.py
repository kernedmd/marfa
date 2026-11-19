# -*- coding: utf-8 -*-
"""Марфа — Г-1, дымовой тест глаз (8083) при работающем мозге (8082). v1.5

Запуск из корня дома:
    venv\\Scripts\\python.exe tests\\vision_smoke.py
Опции:
    --width 1600     ширина снимка для VLM (1280 — план Б по скорости)
    --click-start    полный замкнутый цикл: клик по «Пуск» + проверка меню
Зависимости: venv\\Scripts\\pip install mss pyautogui

v1.4 — калибровка «Пуск» доведена по урокам прогонов. В родном размере
(полный кадр, 29 с, и полоса 1920x448) 3B-сенсор честно отвечал «не
вижу»: логотип «Пуска» 48 px для него мал. Видал он кнопку только когда
сервер сам растягивал кадр до --image-min-tokens 1024 (полоса v1.2) —
но тогда же y-координаты приходили мусором, за пределы кадра. Вывод:
увеличиваем полосу задачи СВОИМИ руками (LANCZOS): боковые зоны
960x112 -> 3x (1234 токена), полоса целиком -> 2x (1097 токенов) —
итог всегда >= 1024 токенов, сервер не пересчитывает ничего, а
координаты делим на коэффициент сами. x вне кадра — зона бракуется;
y вне кадра при честном x — прижимаем к панели задачи с громким
сообщением (проверку клика всё равно делает меню). Полный кадр из
калибровки убран: медленный и слепой. Проверка меню после клика —
родная полоса 1920x840 вместо ресайза до 1600 (ресайз однажды дал
ложное «закрыто» на открытом меню).
v1.5 — вердикт замкнутого цикла теперь выносит ПИКСЕЛЬНАЯ СВЕРКА
до/после клика (полоса 1920x840, порог 5%) — земная истина без сенсора:
сенсор меню дважды отвечал «закрыто», один раз точно ложно (скриншот
Создателя доказал открытое меню). Мнение сенсора стало вторичным;
если клик экран не изменил — один повтор правее (кнопка шире логотипа).

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
from PIL import Image, ImageChops

try:
    import mss
except ImportError:
    sys.exit("Нет модуля mss: venv\\Scripts\\pip install mss")

# mss.mss устарел (DeprecationWarning) — в новых версиях класс зовётся MSS
_MSS = getattr(mss, "MSS", mss.mss)

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
    "Ты — зрительный сенсор интерфейсов. Опиши экран строго одним JSON, одной строкой, без пояснений.\n"
    'Пример ответа: {"active_window":"Командная строка","elements":'
    '[{"type":"text","text":"C:\\Marfa>","bbox":[64,32,412,58],"confidence":0.9}],'
    '"summary":"рабочий стол с окнами"}\n'
    'Поле type — ровно ОДНО слово из: button, input, link, menu, text, icon, image. '
    "Перечисление через | в ответе запрещено.\n"
    "Правила: bbox — пиксели входного изображения [x1,y1,x2,y2]; не выдумывай элементы; "
    "нечитаемое — confidence меньше 0.4; лучше меньше элементов, чем выдуманные; "
    "НЕ БОЛЕЕ 10 элементов — только самые крупные и заметные."
)

START_PROMPT = (
    "Это нижняя полоса экрана — панель задач Windows, сильно УВЕЛИЧЕННАЯ. "
    "Найди кнопку «Пуск» — квадратный логотип Windows из четырёх секторов; "
    "она занимает почти всю высоту полосы и стоит у левого края полосы "
    "или ближе к её центру. "
    "Ответь строго одним JSON без пояснений: "
    '{"found":true,"bbox":[x1,y1,x2,y2],"confidence":0.0}. '
    'Если кнопки не видно: {"found":false,"bbox":null,"confidence":0}. '
    "Координаты — в пикселях ЭТОГО увеличенного изображения. Не выдумывай."
)

MENU_PROMPT = (
    "Это нижняя часть экрана Windows сразу после клика. Открыто ли сейчас "
    "меню «Пуск» — большая панель со строкой поиска и списком программ? "
    'Ответь строго одним JSON: {"menu_open": true} или {"menu_open": false}.'
)

# Схема для вопроса «где Пуск» — свои ворота под свой вопрос, иначе
# грамматика дескриптора заставляет глаза перечислять все кнопки подряд.
START_SCHEMA = {
    "type": "object",
    "properties": {
        "found": {"type": "boolean"},
        "bbox": {
            "anyOf": [
                {"type": "array", "items": {"type": "integer"},
                 "minItems": 4, "maxItems": 4},
                {"type": "null"},
            ],
        },
        "confidence": {"type": "number"},
    },
    "required": ["found", "bbox", "confidence"],
}

MENU_SCHEMA = {
    "type": "object",
    "properties": {"menu_open": {"type": "boolean"}},
    "required": ["menu_open"],
}

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
    with _MSS() as sct:
        raw = sct.grab(sct.monitors[1])  # основной монитор, физические пиксели
        img = Image.frombytes("RGB", raw.size, raw.rgb)
    scale = width / img.width
    small = img.resize((width, round(img.height * scale)), Image.LANCZOS)
    buf = io.BytesIO()
    small.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode()
    return b64, img.size, small.size


def zone_image(x0, y0, x1, y1):
    """Кроп региона экрана в РОДНОМ разрешении (пиксели = экран)."""
    with _MSS() as sct:
        raw = sct.grab(sct.monitors[1])
        img = Image.frombytes("RGB", raw.size, raw.rgb)
    return img.crop((x0, y0, min(x1, img.width), min(y1, img.height)))


def zone_b64(img, k=1):
    """Снимок -> PNG/base64; k > 1 — увеличение СВОИМИ руками (LANCZOS).

    Урок v1.2/v1.3: в родном размере логотип «Пуск» (48 px) для 3B-сенсора
    мал — честный ответ «не вижу»; а когда кадр растягивал САМ сервер
    (--image-min-tokens 1024), y-координаты приходили мусором. Поэтому
    увеличиваем сами и сами же делим координаты на k. Чтобы сервер не
    пересчитывал кадр, итог должен быть >= 1024 токенов зрения:
    (w/28)*(h/28) >= 1024, т.е. w*h >= 802816 пикселей."""
    if k > 1:
        img = img.resize((img.width * k, img.height * k), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode(), img.size


def crop_zone(x0, y0, x1, y1, k=1):
    """Кроп региона + (не)обязательное увеличение. Уроки — в zone_b64."""
    return zone_b64(zone_image(x0, y0, x1, y1), k)


def pixel_diff(a, b, thr=16):
    """Пиксельная сверка двух снимков — земная истина без сенсора.

    Возвращает (доля изменившихся пикселей, bbox области изменения).
    PNG без потерь: меняется только то, что реально изменилось на экране.
    Меню «Пуск» занимает ~ треть полосы 1920x840; курсор и подсветка
    кнопки — доли процента; порог 5% разделяет их с запасом."""
    diff = ImageChops.difference(a, b).convert("L")
    mask = diff.point(lambda v: 255 if v > thr else 0)
    hist = mask.histogram()
    changed = hist[255] if len(hist) > 255 else 0
    return changed / float(a.width * a.height), mask.getbbox()


def ask_eyes(b64, prompt, max_tokens=1500, schema=SCHEMA):
    """Запрос к глазам. Сначала с response_format/json_schema; если сервер
    отклонил (код >= 400) или схемы нет — без грамматики, дальше парсер-фолбэк.
    ВАЖНО: у каждого вопроса своя схема (schema=None — совсем без схемы):
    чужая грамматика заставляет сенсор отвечать не на тот вопрос."""
    attempts = [schema, None] if schema else [None]
    for sch in attempts:
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
        if sch:
            body["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "answer", "schema": sch},
            }
        r = requests.post(EYES + "/v1/chat/completions", json=body, timeout=240)
        if sch and r.status_code >= 400:
            print("  response_format отклонён сервером (код %s) — "
                  "повтор без грамматики" % r.status_code)
            continue
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"], bool(sch)
    raise RuntimeError("глаза не ответили")


def parse_json(text):
    """Разбор ответа глаз. Глаза — сенсор, не парсер: JSON может быть обёрнут
    в ```fences```, сопровождаться текстом или иметь хвост. Выковыриваем первый
    сбалансированный {...} и парсим только его."""
    clean = text.strip()
    if clean.startswith("```"):
        clean = clean.strip("`").strip()
        if clean.startswith("json"):
            clean = clean[4:]
    try:
        return json.loads(clean)
    except Exception:
        pass
    start = clean.find("{")
    if start < 0:
        raise ValueError("в ответе нет JSON: " + clean[:120])
    depth = 0
    for i in range(start, len(clean)):
        if clean[i] == "{":
            depth += 1
        elif clean[i] == "}":
            depth -= 1
            if depth == 0:
                return json.loads(clean[start:i + 1])
    raise ValueError("JSON не закрылся: " + clean[start:start + 120])


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


def calibrate_start(click=False):
    """Калибровка «Пуск»: глаза -> координаты -> мышь.

    Хроника уроков (для протокола Г-1):
    v1.1: весь экран, ужатый до 1600 — логотип ~40 px, сенсор: «не вижу».
    v1.2: полоса 1920x112 в родном размере — сервер сам растянул её до
          1024 токенов; кнопку ВИДЕЛ (x всегда честный), но y приходил
          мусором, за пределы кадра.
    v1.3: родные кадры без пересчётов (полный 1920x1080, полоса 1920x448)
          — сенсор честно сказал «не вижу»: 48 px для 3B маловато.
    v1.4: логотип должен быть КРУПНЫМ, но пересчитывать его должен Марфа,
          а не сервер. Полоса задачи 1920x112, увеличенная своими руками:
          левая половина 960x112 -> 3x, центр -> 3x, полоса целиком -> 2x.
          Итог всегда >= 1024 токенов — сервер кадр не трогает.
    v1.5: прогон v1.4 нашёл логотип честно (центр (23, 1060), conf 0.99),
          клик ушёл в кнопку — а сенсор меню снова сказал «закрыто».
          Вердикт цикла переведён на пиксельную сверку до/после клика:
          земная истина не зависит от настроения сенсора.
    Гигиена координат: x вне кадра — зона бракуется; y вне кадра при
    честном x — прижимаем к панели задачи (нижние 40% полосы) и ГРОМКО
    об этом сообщаем; итоговый клик всё равно проверяет меню."""
    print("\n--- Калибровка «Пуск» (полоса задачи, увеличенная своими руками) ---")
    with _MSS() as sct:
        mon = sct.monitors[1]
        W, H = mon["width"], mon["height"]

    strip_h = 112  # панель задачи (48 px при 100% DPI) + запас до 150% DPI
    zw = 960       # ширина боковой зоны поиска
    zones = [
        (0, H - strip_h, zw, 3, "левая половина полосы, 3x"),
        ((W - zw) // 2, H - strip_h, zw, 3, "центр полосы, 3x"),
        (0, H - strip_h, W, 2, "полоса целиком, 2x"),
    ]
    hit = None
    for zx, zy, zw_, k, label in zones:
        b64, (bw, bh) = crop_zone(zx, zy, zx + zw_, H, k)
        print("%s: кадр %dx%d, ~%d токенов — жди терпеливо..."
              % (label, bw, bh, bw * bh // 784))
        t0 = time.time()
        try:
            out, _ = ask_eyes(b64, START_PROMPT, max_tokens=200,
                              schema=START_SCHEMA)
            d = parse_json(out)
        except Exception as e:
            print("   ответ не разобран (%s)" % e)
            continue
        print("   ответ за %.1f с" % (time.time() - t0))
        if not d.get("found"):
            print("   сенсор говорит: «Пуск не вижу»")
            continue
        bbox = d.get("bbox")
        if not (isinstance(bbox, list) and len(bbox) == 4):
            print("   found=true, а bbox нет — мусор, мышь не двигаю")
            continue
        x1, x2 = sorted((bbox[0], bbox[2]))
        y1, y2 = sorted((bbox[1], bbox[3]))
        x_ok = -bw * 0.05 <= x1 and x2 <= bw * 1.05 and x2 - x1 > 0
        y_ok = -bh * 0.05 <= y1 and y2 <= bh * 1.05 and y2 - y1 > 0
        if x_ok and y_ok:
            hit = (zx, zy, k, [x1, y1, x2, y2],
                   "bbox целиком в кадре — координаты честные",
                   d.get("confidence"))
            break
        if x_ok:
            cy = min(max((y1 + y2) / 2.0, bh * 0.6), bh * 0.95)
            hit = (zx, zy, k, [x1, cy - 24 * k, x2, cy + 24 * k],
                   "x принят, y сенсора МУСОР (%s, %s) — прижат к панели "
                   "задачи, нижние 40%% полосы" % (bbox[1], bbox[3]),
                   d.get("confidence"))
            break
        print("   bbox %s вылезает за кадр %dx%d и по x — брак, "
              "следующая зона" % (bbox, bw, bh))

    if not hit:
        print("Пуск не найден ни в одной зоне — зафиксируй в протоколе Г-1, "
              "дальше не идём")
        return
    zx, zy, k, bbox, note, conf = hit
    cx = int(round(zx + (bbox[0] + bbox[2]) / 2.0 / k))
    cy = int(round(zy + (bbox[1] + bbox[3]) / 2.0 / k))
    print("координаты: %s; физический центр (%d, %d); confidence: %s"
          % (note, cx, cy, conf))

    try:
        import pyautogui
        pyautogui.FAILSAFE = True
    except ImportError:
        print("pyautogui нет — наведение мыши пропущено "
              "(venv\\Scripts\\pip install pyautogui)")
        return
    # DPI: процесс DPI-aware, снимок и мышь говорят в физических пикселях;
    # если pyautogui видит другое разрешение — пересчитываем в его координаты.
    pw, ph = pyautogui.size()
    if (pw, ph) != (W, H):
        print("ВНИМАНИЕ: мышь видит %dx%d, снимок %dx%d — пересчёт координат"
              % (pw, ph, W, H))
        cx = int(round(cx * pw / float(W)))
        cy = int(round(cy * ph / float(H)))
    if cy < ph - 160:
        print("ПОДОЗРИТЕЛЬНО: центр кнопки (%d, %d) дальше 160 px от нижней "
              "кромки — у «Пуска» место у кромки; проверь глазами, прежде "
              "чем верить сенсору" % (cx, cy))
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
    # --- Клик + земная истина: пиксельная сверка до/после -----------------
    # Сенсор меню дважды сказал «закрыто» (один раз — точно ложно, скриншот
    # Создателя доказал открытое меню). Поэтому вердикт выносят пиксели:
    # меню занимает ~ треть полосы 1920x840, курсор и подсветка — доли
    # процента; порог 5% разделяет их с запасом. Мнение сенсора вторично.
    menu_h = 840  # 28*30; 1920x840 ~ 2057 токенов — апскейла нет
    before = zone_image(0, H - menu_h, W, H)  # «до»: курсор уже на кнопке
    pyautogui.click()
    time.sleep(2.5)
    after = zone_image(0, H - menu_h, W, H)
    frac, box = pixel_diff(before, after)
    print("пиксельная сверка до/после клика: изменено %.1f%% полосы %dx%d"
          % (frac * 100.0, after.width, after.height))
    if frac < 0.05:
        print("   меньше 5% — клик экран не изменил; повтор правее "
              "(кнопка шире логотипа)")
        pyautogui.moveTo(cx + 24, cy, duration=0.4)
        pyautogui.click()
        time.sleep(2.5)
        after = zone_image(0, H - menu_h, W, H)
        frac, box = pixel_diff(before, after)
        print("пиксельная сверка после повтора: изменено %.1f%%"
              % (frac * 100.0))
    menu_like = bool(box) and box[0] <= 4 and box[3] >= after.height - 4
    if box:
        print("   область изменения: %s%s" % (box,
              " — прижата к левому нижнему углу, профиль меню «Пуск»"
              if menu_like else ""))
    if frac >= 0.05 and menu_like:
        print("ЗАМКНУТЫЙ ЦИКЛ РАБОТАЕТ: взгляд -> координаты -> клик -> "
              "экран изменился (земная истина, пиксели не врут)")
    elif frac >= 0.05:
        print("экран изменился на %.1f%%, но область не у левого нижнего "
              "угла — не похоже на меню «Пуск»; сверь глазами и зафиксируй "
              "в протоколе Г-1" % (frac * 100.0))
    else:
        print("клик не изменил экран — координаты мимо кнопки; "
              "зафиксируй в протоколе Г-1")
    # Мнение сенсора — вторично к пиксельной сверке
    b642, _ = zone_b64(after)
    out2 = ""
    try:
        out2, _s = ask_eyes(b642, MENU_PROMPT, max_tokens=100, schema=MENU_SCHEMA)
        menu = parse_json(out2)
        print("глаза после клика:", menu)
        if bool(menu.get("menu_open")) != (frac >= 0.05):
            print("   расхождение с пиксельной сверкой — пиксели побеждают; "
                  "зафиксируй в протоколе Г-1")
    except Exception as e:
        print("глаза после клика: сбой (%s); сырой хвост: %s" % (e, out2[:200]))
    pyautogui.press("esc")
    print("нажат Esc — меню закрыто (рабочий стол чист)")


def main():
    print("vision_smoke: v1.5")  # баннер: сразу видно, свежий ли файл
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

    passes = [r]

    # Совет №3: Pascal без тензорных ядер — если медленно, автоповтор на 1280
    if r["t_ask"] > 8 and args.width > 1280:
        print("\n--- Медленнее 8 с: автоповтор на ширине 1280 (план Б, совет №3) ---")
        r2 = describe(1280)
        passes.append(r2)
        print("1280: ответ %.1f с против %.1f с на %d; JSON: %s"
              % (r2["t_ask"], r["t_ask"], args.width, r2["ok"]))
        if r2["data"]:
            for el in r2["data"].get("elements", [])[:6]:
                print("  ", el)

    calibrate_start(click=args.click_start)

    best = min(passes, key=lambda p: p["t_ask"])  # рабочая точка глаз
    print("\n--- Самопроверка по критериям Г-1 ---")
    print("JSON валиден: %s" % ("да" if all(p["data"] for p in passes) else "НЕТ"))
    print("время ответа <= 8 с: %s (%.1f с на ширине %d — рабочая точка)"
          % ("да" if best["t_ask"] <= 8 else "НЕТ", best["t_ask"], best["width"]))
    if best["t_ask"] > 8:
        print("   отклонение +%.1f с к критерию — решение Создателя: "
              "принять с отклонением или дожать сервер" % (best["t_ask"] - 8))
    print("живость 30B, VRAM и RAM проверь вручную: критерии 1-4, nvidia-smi")


if __name__ == "__main__":
    main()
