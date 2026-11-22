# -*- coding: utf-8 -*-
"""core/eyes.py — ГЛАЗА ДОМА (Г-1 принят, Г-2 — глаза в агенте, v2 — 22.11).

Сенсор зрения: Qwen2.5-VL-3B на порту 8083 (llama-server, CUDA). Мозг (8082)
про порт глаз не знает — агент сам ходит к сенсору за дескриптором экрана.

Правила, выжатые из приёмки Г-1 (tests/vision_smoke.py v1.1-v1.5):
- глаза ТОЛЬКО ЧИТАЮТ экран: ни курсора, ни кликов — это территория РУК
  под надзором стража;
- рабочая ширина кадра 1280 (8.8 с на GTX 1060, принято с отклонением);
- у каждого вопроса своя грамматика: дескриптору — SCHEMA ниже;
- сенсор — не парсер: ответ выковыривается из fences/текста (parse_json);
- состояние экрана проверяют ПИКСЕЛИ, а не мнение сенсора (урок v1.5).

v2 (22.11): «шуточно-фейковый» пример [11,22,33,44] + прямой запрет
копирования, description первой строкой, цепочка грамматик schema →
json_object → raw.

v3 (живой прогон v2, 22.11): антипопугай ПРОВАЛИЛСЯ — модель выдала
фейковый пример КАК РЕАЛЬНОСТЬ («Экран с текстом и кнопкой», оба
бокса [11,22,33,44], кнопка «пример-надпись», 148.2 с). Урок
эскалирован: 3B-модель копирует ЛЮБОЙ пример значений — в промптах
сенсора теперь НЕТ НИ ОДНОГО примера, поля описаны словами. И разводка
путей:
- ЧАТ («посмотри», «что ты видишь») — вообще без JSON: сенсор описывает
  экран живым текстом и цитирует надписи дословно; естественный ответ
  кончается EOS, а не упирается в лимит токенов; если сенсор по привычке
  ответил JSON — из него достаётся description;
- СТРУКТУРНЫЙ ДЕСКРИПТОР (для РУК и экзамена Р-0) — отдельный промпт
  без примера + честная геометрия: bbox обязан жить внутри кадра, что
  отправлен глазам (выдуманные боксы выбрасываются), а шаблонные
  значения («пример-надпись») бракуются на корню — Создателю честная
  ошибка, не фейк про экран.

Камера (22.11, просьба Создателя «онлайн-знакомство»): веб-камера —
второй источник зрения, «посмотри в камеру» / «посмотри на меня».
OpenCV ставится отдельно; нет его или нет камеры — честная ошибка.

Швы для тестов: _screenshot_b64 / _camera_b64 / _post_chat / health /
health_cached / _VISION_ERROR — tests/test_eyes.py подменяют их, реальный
сервер, камера и экран не нужны.
"""
from __future__ import annotations

import base64
import io
import json
import time
from typing import Optional, Tuple

import requests

from core import config

try:
    import mss
    from PIL import Image
    _MSS = getattr(mss, "MSS", mss.mss)   # mss.mss устарел в новых версиях
    _VISION_ERROR = None
except ImportError as e:
    _MSS = None
    _VISION_ERROR = "нет модуля зрения: %s (venv\\Scripts\\pip install mss pillow)" % e

EYES = "http://127.0.0.1:%d" % config.PORT_EYES
EYES_TIMEOUT = 240          # холодный старт CUDA ~50 с — не подрезаем
WORK_WIDTH = 1280           # рабочая точка Г-1: ~8.8 с на GTX 1060
CAMERA_WIDTH = 960          # камера: меньше токенов, лицу не нужен 1280

# Бюджеты генерации (уроки 132.6 с и 148.2 с): естественный текст
# кончается EOS задолго до лимита, но потолок держит руку на рубильнике.
SCREEN_MAX_TOKENS = 400     # чат: 3-6 предложений, не JSON-марафон
ELEMENTS_MAX_TOKENS = 500   # структурный дескриптор для рук

# ЧАТ: живое описание словами. Урок v3: JSON в чате — не сила 3B-модели,
# а описание картинки — её сладкая точка. Примеров значений НЕТ (урок
# v1/v2: любой пример будет списан), требований — словами.
SCREEN_PROMPT = (
    "Ты — зрение Марфы. Посмотри на скриншот и опиши словами, что на "
    "экране: какая программа или окно открыто (назови заголовок, если "
    "читается), о чём написано на экране, какие кнопки, поля и ссылки "
    "видны. ГЛАВНОЕ — ЧИТАЙ надписи и самые важные цитируй дословно. "
    "3-6 предложений по-русски, обычным текстом, без списков координат. "
    "Пиши только то, что реально видно; нечитаемое не выдумывай — скажи "
    "честно «не разберу»."
)

# СТРУКТУРНЫЙ ДЕСКРИПТОР: для РУК (экзамен Р-0 ищет Пуск по тексту
# элемента и bbox). Поля описаны словами, примера значений нет.
ELEMENTS_PROMPT = (
    "Ты — зрительный сенсор Марфы. Посмотри на скриншот и ответь строго "
    "одним JSON-объектом, без пояснений.\n"
    "Поля объекта:\n"
    "- description — 1-2 предложения по-русски, что происходит на экране;\n"
    "- active_window — заголовок активного окна;\n"
    "- elements — не больше 6 самых важных объектов интерфейса, у каждого "
    "поля: type (ровно одно слово: button, input, link, menu, text, icon "
    "или image), text (надпись, прочитанная с экрана дословно; не "
    "читается — пустая строка), bbox (массив из четырёх целых чисел — "
    "лево, верх, право, низ в пикселях ЭТОГО скриншота), confidence "
    "(число от 0 до 1).\n"
    "Правила: ЧИТАЙ надписи — элемент без прочитанного text почти "
    "бесполезен; не выдумывай — нечитаемому ставь confidence ниже 0.4; "
    "лучше меньше элементов, чем выдуманные. Отвечай только по реальному "
    "скриншоту, не по воображению."
)

SCHEMA = {
    "type": "object",
    "properties": {
        "description": {"type": "string"},
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
    },
    "required": ["elements"],
}

# Камера: тоже без примера значений (урок v3 касается и её — пример
# [11,22,33,44] стоял и здесь, «посмотри в камеру» ждала та же беда).
CAMERA_PROMPT = (
    "Ты — зрение Марфы, смотрящее в веб-камеру. Посмотри на кадр и "
    "ответь строго одним JSON-объектом, без пояснений.\n"
    "Поля объекта:\n"
    "- description — 2-4 предложения по-русски: кто и что в кадре;\n"
    "- objects — не больше 5 главных объектов, у каждого поля: name "
    "(слово-два по-русски, что это), bbox (массив из четырёх целых чисел — "
    "лево, верх, право, низ в пикселях ЭТОГО кадра), confidence (число "
    "от 0 до 1).\n"
    "Правила: это живая камера, не скриншот; людей описывай уважительно "
    "и по фактам (мужчина/женщина, во что одет, что делает), лица не "
    "идентифицируй и не выдумывай имён; не выдумывай того, чего нет — "
    "в кадре может быть и пусто."
)

CAMERA_SCHEMA = {
    "type": "object",
    "properties": {
        "description": {"type": "string"},
        "objects": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "bbox": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "minItems": 4,
                        "maxItems": 4,
                    },
                    "confidence": {"type": "number"},
                },
                "required": ["name"],
            },
        },
    },
    "required": ["description"],
}


def health() -> bool:
    """Жив ли сервер зрения (8083)."""
    try:
        return requests.get(EYES + "/health", timeout=5).status_code == 200
    except Exception:
        return False


_health_cache = (False, 0.0)


def health_cached(period: float = 30.0) -> bool:
    """Здоровье глаз с кэшем (Г-2.1). Мозговой трек узнаёт о глазах из
    состояния дома в КАЖДОМ сообщении — а HTTP-пинг по мёртвому порту
    стоит до 5 с тишины. Кэш на `period` секунд: панель остаётся быстрой,
    а Марфа всё равно в курсе, живы ли глаза. Свежесть важнее точности:
    минута устаревания для «посмотри в чат» ничего не решает."""
    global _health_cache
    ok, ts = _health_cache
    now = time.time()
    if ts and now - ts < period:
        return ok
    ok = health()
    _health_cache = (ok, now)
    return ok


def _screenshot_b64(width: int = WORK_WIDTH):
    """Снимок основного монитора -> PNG base64, ужатый до width (LANCZOS).

    mss снимает в физических пикселях монитора; глаза не трогают мышь,
    поэтому DPI-режим процесса здесь не нужен (в отличие от vision_smoke)."""
    with _MSS() as sct:
        raw = sct.grab(sct.monitors[1])
        img = Image.frombytes("RGB", raw.size, raw.rgb)
    scale = width / float(img.width)
    small = img.resize((width, max(1, round(img.height * scale))), Image.LANCZOS)
    buf = io.BytesIO()
    small.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode(), img.size, small.size


def _post_chat(body: dict) -> dict:
    """Единый шов HTTP: POST /v1/chat/completions к глазам."""
    r = requests.post(EYES + "/v1/chat/completions", json=body,
                      timeout=EYES_TIMEOUT)
    r.raise_for_status()
    return r.json()


def _ask(b64: str, prompt: str, schema: Optional[dict],
         max_tokens: int = ELEMENTS_MAX_TOKENS) -> Tuple[str, Optional[str]]:
    """Спросить глаза. Цепочка грамматик (урок 132 секунд):
    строгая схема → простой json_object → без грамматики.

    Если сервер отверг json_schema (мгновенный 400), но знает json_object
    («ответ — только JSON») — модель скована грамматикой и не разговаривает
    в пустоту до лимита токенов. Возвращает (текст ответа, какая грамматика
    сработала: "schema" / "json_object" / None).
    """
    attempts = []
    if schema:
        attempts.append(("schema",))
        attempts.append(("json_object",))
    attempts.append((None,))
    last = None
    for (grammar,) in attempts:
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
        if grammar == "schema":
            body["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "answer", "schema": schema},
            }
        elif grammar == "json_object":
            body["response_format"] = {"type": "json_object"}
        try:
            data = _post_chat(body)
            return data["choices"][0]["message"]["content"], grammar
        except Exception as e:
            last = e
    raise RuntimeError("глаза не ответили: %s" % last)


def parse_json(text: str) -> dict:
    """Сенсор — не парсер: JSON может лежать в ```fences```, сопровождаться
    текстом или хвостом. Выковыриваем первый сбалансированный {...} и парсим
    только его."""
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


def _clean_prose(text: str) -> str:
    """Ответ сенсора — в чат: снять мусор генерации (fences, префикс
    «Ответ:», обёртку из кавычек), оставить живой текст. Сенсор не
    парсер — а чат не помойка."""
    s = text.strip()
    if s.startswith("```"):
        s = s.strip("`").strip()
        for pre in ("json", "text"):
            if s.lower().startswith(pre):
                s = s[len(pre):].strip()
                break
    for pre in ("Ответ:", "Ответ:"):
        if s.startswith(pre):
            s = s[len(pre):].strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in "'\"«»":
        s = s[1:-1].strip()
    return s


# Урок v1→v2→v3: сначала модель списала [64,32,412,58], потом — «шуточный»
# [11,22,33,44] с «пример-надписью». В промптах примеров больше нет; эти
# значения в ответе значат одно: сенсор видит шаблон, а не экран.
_PARROT_TEXTS = ("пример-надпись",)


def _assert_no_parrot(d: dict) -> None:
    """Браковщик шаблонов: если в дескрипторе всплыл текст примера —
    ответ забракован. Создателю — честная ошибка, а не фейк про экран;
    архитектору — сигнал, что пример вернули в промпт."""
    els = d.get("elements") if isinstance(d, dict) else None
    for el in els or []:
        if isinstance(el, dict):
            t = str(el.get("text", "")).strip().lower()
            if any(m in t for m in _PARROT_TEXTS):
                raise ValueError(
                    "глаза вернули шаблон промпта, а не реальный экран — "
                    "ответ забракован; скажи «посмотри» ещё раз и сообщи "
                    "архитектору")


def _validate_elements(d: dict, size) -> dict:
    """Честная геометрия (урок v3): bbox обязан жить внутри кадра, что
    отправлен глазам, — x1<x2, y1<y2, в пределах ширины и высоты.
    Выдуманные боксы выбрасываются: они не попадут ни в чат, ни в прицел
    рук (Р-0 меряет диалект координат по этим цифрам)."""
    els = d.get("elements") if isinstance(d, dict) else None
    if not isinstance(els, list):
        if isinstance(d, dict):
            d["elements"] = []      # контракт: elements — всегда список
        return d
    w, h = int(size[0]), int(size[1])
    good = []
    for el in els:
        if not isinstance(el, dict):
            continue
        bbox = el.get("bbox")
        try:
            bbox = [int(v) for v in bbox]
        except (TypeError, ValueError):
            continue
        if not (len(bbox) == 4 and 0 <= bbox[0] < bbox[2] <= w
                and 0 <= bbox[1] < bbox[3] <= h):
            continue
        el["bbox"] = bbox
        good.append(el)
    d["elements"] = good[:8]
    return d


def describe(width: int = WORK_WIDTH) -> dict:
    """СТРУКТУРНЫЙ дескриптор экрана (для РУК и экзамена Р-0):
    description + active_window + elements. Промпт без единого примера
    значений (урок v3), геометрия проверена по отправленному кадру,
    шаблоны забракованы. Поднимает исключения (сервер, парс, шаблон) —
    безопасная обёртка для чата: describe_text()."""
    if _VISION_ERROR:
        raise RuntimeError("глаза не готовы: " + _VISION_ERROR)
    b64, _real, small = _screenshot_b64(width)
    out, _ = _ask(b64, ELEMENTS_PROMPT, SCHEMA,
                  max_tokens=ELEMENTS_MAX_TOKENS)
    d = parse_json(out)
    _assert_no_parrot(d)
    return _validate_elements(d, small)


def describe_text(width: int = WORK_WIDTH) -> str:
    """Глазами в чат: живое описание экрана, исключений не поднимает.

    v3: чат получает ЧЕЛОВЕЧЕСКИЙ текст — сенсор просит словами (читай
    надписи, цитируй дословно), без JSON-марафона: естественный ответ
    кончается EOS, а не упирается в лимит токенов (уроки 132.6 и 148.2 с).
    Если сенсор по привычке ответил JSON — достаётся description.
    Это ответ агента, а не модели — мозг молчит; но историю диалога видит
    мозг, так что «что на нём?» после «посмотри» он осмысляет уже
    человеческое описание, а не пересчёт боксов.
    """
    try:
        if _VISION_ERROR:
            return "глаза не готовы: " + _VISION_ERROR
        if not health():
            return ("глаза %d не отвечают — сервер зрения не запущен?"
                    % config.PORT_EYES)
        t0 = time.time()
        b64, _real, _small = _screenshot_b64(width)
        out, _ = _ask(b64, SCREEN_PROMPT, None,
                      max_tokens=SCREEN_MAX_TOKENS)
        secs = time.time() - t0
        prose = _clean_prose(out)
        if prose.startswith("{"):
            # сенсор по привычке ушёл в JSON — чату нужна суть, не сырьё
            try:
                d = parse_json(prose)
                prose = str(d.get("description") or d.get("summary")
                            or "").strip() or prose
            except Exception:
                pass
        if not prose:
            return ("глаза ответили пусто — честно: не поняли кадр, "
                    "скажи «посмотри» ещё раз")
        lines = ["Вижу: " + prose]
        tail = "(глаза думали %.1f с" % secs
        if secs > 45:
            tail += ("; медленно — первый взгляд после старта греет CUDA, "
                     "дальше быстрее")
        tail += ")"
        lines.append(tail)
        return "\n".join(lines)
    except Exception as e:
        return "глаза ошиблись: " + str(e)


# ---------------------------------------------------------------
# КАМЕРА — второй источник зрения (веб-камера Создателя, 22.11)
# ---------------------------------------------------------------

def _camera_b64(width: int = CAMERA_WIDTH) -> str:
    """Кадр с веб-камеры -> PNG base64, ужатый до width.

    OpenCV ставится отдельно (pip install opencv-python) — лениво:
    нет его или нет камеры — честная ошибка, не выдумка про «вижу».
    Устройство 0 — камера по умолчанию (у Создателя — веб-камера).
    """
    try:
        import cv2
    except ImportError as e:
        raise RuntimeError(
            "нет модуля камеры: %s (venv\\Scripts\\pip install "
            "opencv-python)" % e)
    cap = cv2.VideoCapture(0)
    try:
        if not cap.isOpened():
            raise RuntimeError(
                "камера не открылась — подключена ли веб-камера, не занята "
                "ли другим приложением (Skype/Zoom/Камера)?")
        ok, frame = cap.read()
        if not ok or frame is None:
            raise RuntimeError("камера не дала кадр — попробуй ещё раз")
        img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    finally:
        cap.release()
    scale = width / float(img.width)
    small = img.resize((width, max(1, round(img.height * scale))),
                       Image.LANCZOS)
    buf = io.BytesIO()
    small.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


# ---------------------------------------------------------------
# МОДУЛЬ КАМЕРЫ и ЖИВОЙ САМОТЕСТ (урок прогона 22.11: Создатель
# поставил opencv и спросил «проверь ещё раз, он появился» — а мозг
# ответил по памяти «всё ещё недоступна». Проверка камеры —
# ЭКСПЕРИМЕНТ, а не воспоминание: импорт, сенсор, настоящий кадр.)
# ---------------------------------------------------------------

def _cv2_import():
    """Есть ли OpenCV; возвращает версию или None (шов для тестов).

    Ленивый импорт в живом процессе ловит модуль, поставленный ПОСЛЕ
    старта дома (pip в соседнем окне) — каталог site-packages
    перечитывается при каждой попытке."""
    try:
        import cv2
        return getattr(cv2, "__version__", "?")
    except ImportError:
        return None


_cv2_cache = (None, 0.0)      # (версия или None, время проверки)


def camera_module_ok(period: float = 300.0) -> bool:
    """Есть ли модуль OpenCV (кэш: импорт стоит сотни миллисекунд).

    Для состояния дома и «изучи себя»: быстрый честный факт без
    будоражащего импорта в каждом сообщении. Живой тест камеры
    (модуль + сенсор + настоящий кадр) — camera_selftest()."""
    global _cv2_cache
    ver, ts = _cv2_cache
    now = time.time()
    if ver is not None and now - ts < period:
        return bool(ver)
    ver = _cv2_import()
    _cv2_cache = (ver, now)
    return bool(ver)


def camera_selftest() -> str:
    """«проверь камеру»: живая проверка в три шага — модуль, сенсор, кадр.

    Каждая ступень честна отдельно: модуль есть, но сенсор спит —
    говорим про сенсор; сенсор жив, но кадра нет — говорим про
    устройство. Без выдумок «всё ещё недоступна» по памяти.
    """
    lines = ["ПРОВЕРКА КАМЕРЫ (вживую, не по памяти):"]
    ver = _cv2_import()
    if not ver:
        return "\n".join(lines + [
            "- модуль opencv: НЕТ — поставить: venv\\Scripts\\pip install "
            "opencv-python",
            "  (ставил в другом окне? убедись, что это venv дома: "
            "C:\\Marfa\\venv\\Scripts\\pip.exe; после установки "
            "повтори «проверь камеру» — перезапуск не нужен)"])
    global _cv2_cache
    _cv2_cache = (ver, time.time())       # свежая правда — и в состояние дома
    lines.append("- модуль opencv: есть (%s)" % ver)
    if _VISION_ERROR:
        return "\n".join(lines + ["- глаза не готовы: " + _VISION_ERROR])
    if not health():
        return "\n".join(lines + [
            "- сенсор зрения %d не отвечает — камере нужен тот же сервер, "
            "что и глазам (скажи «доктор» или перезапусти дом)"
            % config.PORT_EYES])
    lines.append("- сенсор зрения: жив")
    try:
        t0 = time.time()
        b64 = _camera_b64()
        lines.append("- камера дала кадр: %.0f КБ за %.1f с — КАМЕРА ЖИВА: "
                     "«посмотри в камеру» покажет, кто передо мной"
                     % (len(b64) / 1024.0, time.time() - t0))
    except Exception as e:
        lines.append("- камера не дала кадр: %s" % e)
    return "\n".join(lines)


def describe_camera_text() -> str:
    """Глазами в веб-камеру: «посмотри в камеру» / «посмотри на меня» —
    онлайн-знакомство. Честная обёртка: исключений не поднимает."""
    try:
        if _VISION_ERROR:
            return "глаза не готовы: " + _VISION_ERROR
        if not health():
            return ("глаза %d не отвечают — сервер зрения не запущен? "
                    "Камере нужен тот же сенсор, что и экрану"
                    % config.PORT_EYES)
        t0 = time.time()
        b64 = _camera_b64()
        out, _ = _ask(b64, CAMERA_PROMPT, CAMERA_SCHEMA)
        d = parse_json(out)
        lines = []
        descr = str(d.get("description") or "").strip()
        if descr:
            lines.append("Вижу в камере: " + descr)
        objs = d.get("objects")
        if isinstance(objs, list) and objs:
            for i, ob in enumerate(objs[:5], 1):
                piece = "%d. %s" % (i, ob.get("name", "?"))
                if ob.get("confidence") is not None:
                    piece += " (%.2f)" % float(ob["confidence"])
                lines.append(piece)
        if not lines:
            return ("камера ответила пусто — честно: не поняла кадр "
                    "(попробуй ещё раз, света побольше)")
        lines.append("(камера думала %.1f с)" % (time.time() - t0))
        return "\n".join(lines)
    except Exception as e:
        return "камера не смогла: " + str(e)
