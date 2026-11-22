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

v2 (урок живого прогона 22.11: «посмотри» → один пустой элемент
[64, 32, 412, 58] за 132.6 с): 3B-модель СПИСАЛА пример из промпта —
тот самый bbox стоял в примере формата. Три лекарства:
- промпт-антипопугай: пример с шуточно-фейковыми значениями [11,22,33,44]
  и прямой запрет копирования; главное требование — ЧИТАТЬ надписи;
- описание по-человечески: поле description (2-4 предложения) первой
  строкой ответа, элементы — подробность, а не сам ответ;
- цепочка грамматик schema → json_object → без грамматики: если сервер
  отверг строгую схему, но знает простую «ответ — только JSON» — модель
  не разговаривает в пустоту до лимита токенов (132 с rambling).

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

PROMPT = (
    "Ты — зрительный сенсор Марфы. Посмотри на скриншот и ответь строго "
    "одним JSON-объектом, одной строкой, без пояснений.\n"
    'Формат: {"description":"2-4 предложения по-русски — что происходит '
    'на экране","active_window":"заголовок активного окна","elements":'
    '[{"type":"button","text":"пример-надпись","bbox":[11,22,33,44],'
    '"confidence":0.5}],"summary":"короткая сводка"}\n'
    "Правила:\n"
    "- ГЛАВНОЕ: ЧИТАЙ надписи с экрана и пиши их в поле text каждого "
    "элемента — элемент без прочитанной надписи почти бесполезен.\n"
    "- type — ровно одно слово из: button, input, link, menu, text, icon, "
    "image. Перечисление через | в ответе запрещено.\n"
    "- bbox — пиксели ЭТОГО скриншота [x1,y1,x2,y2].\n"
    "- Не более 8 элементов — только самые важные. Не выдумывай: "
    "нечитаемое — confidence меньше 0.4; лучше меньше элементов, чем "
    "выдуманные.\n"
    "- Значения в примере формата (пример-надпись, [11,22,33,44]) — "
    "выдуманные шуточные; НЕ копируй их в ответ, смотри на реальный "
    "скриншот."
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
        "summary": {"type": "string"},
    },
    "required": ["elements"],
}

CAMERA_PROMPT = (
    "Ты — зрение Марфы, смотрящее в веб-камеру. Опиши кадр строго одним "
    "JSON-объектом, одной строкой, без пояснений.\n"
    'Формат: {"description":"2-4 предложения по-русски: кто и что в кадре",'
    '"objects":[{"name":"человек","bbox":[11,22,33,44],"confidence":0.9}]}\n'
    "Правила: это живая камера, не скриншот; людей описывай уважительно и "
    "по фактам (мужчина/женщина, во что одет, что делает), лица не "
    "идентифицируй и не выдумывай имён; объектов не более 5; не выдумывай "
    "того, чего нет; bbox — пиксели этого кадра. Значения в примере — "
    "выдуманные, НЕ копируй их."
)


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
         max_tokens: int = 800) -> Tuple[str, Optional[str]]:
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


def describe(width: int = WORK_WIDTH) -> dict:
    """Дескриптор экрана: description + active_window + elements + summary.
    Поднимает исключения (сервер, парс) — безопасная обёртка для чата:
    describe_text()."""
    if _VISION_ERROR:
        raise RuntimeError("глаза не готовы: " + _VISION_ERROR)
    b64, _real, _small = _screenshot_b64(width)
    out, _ = _ask(b64, PROMPT, SCHEMA)
    return parse_json(out)


def describe_text(width: int = WORK_WIDTH) -> str:
    """Глазами в чат: честный текст для панели, исключений не поднимает.
    Это ответ агента, а не модели — мозг молчит. v2: первой строкой —
    человеческое описание (description/summary), элементы — подробность."""
    try:
        if _VISION_ERROR:
            return "глаза не готовы: " + _VISION_ERROR
        if not health():
            return ("глаза %d не отвечают — сервер зрения не запущен?"
                    % config.PORT_EYES)
        t0 = time.time()
        d = describe(width)
        secs = time.time() - t0
        if not isinstance(d.get("elements"), list):
            return ("глаза ответили, но без списка элементов — "
                    "зафиксируй в протоколе")
        lines = []
        descr = str(d.get("description") or d.get("summary") or "").strip()
        if descr:
            lines.append("Вижу: " + descr)
        aw = d.get("active_window")
        if aw:
            lines.append("Активное окно: " + str(aw))
        els = d.get("elements", [])
        lines.append("Элементы (%d):" % len(els))
        for i, el in enumerate(els[:10], 1):
            piece = "%d. [%s]" % (i, el.get("type", "?"))
            txt = el.get("text")
            if txt:
                piece += " «%s»" % txt
            if el.get("bbox"):
                piece += " %s" % el["bbox"]
            if el.get("confidence") is not None:
                piece += " (%.2f)" % float(el["confidence"])
            lines.append(piece)
        s = d.get("summary")
        if s and str(s) != descr:
            lines.append("Сводка: " + str(s))
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
        out, _ = _ask(b64, CAMERA_PROMPT, None)
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
