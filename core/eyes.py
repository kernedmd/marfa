# -*- coding: utf-8 -*-
"""core/eyes.py — ГЛАЗА ДОМА (Г-1 принят, Г-2 — глаза в агенте).

Сенсор зрения: Qwen2.5-VL-3B на порту 8083 (llama-server, CUDA). Мозг (8082)
про порт глаз не знает — агент сам ходит к сенсору за дескриптором экрана.

Правила, выжатые из приёмки Г-1 (tests/vision_smoke.py v1.1-v1.5):
- глаза ТОЛЬКО ЧИТАЮТ экран: ни курсора, ни кликов — это территория РУК
  под надзором стража;
- рабочая ширина кадра 1280 (8.8 с на GTX 1060, принято с отклонением);
- у каждого вопроса своя грамматика: дескриптору — SCHEMA ниже;
- сенсор — не парсер: ответ выковыривается из fences/текста (parse_json);
- состояние экрана проверяют ПИКСЕЛИ, а не мнение сенсора (урок v1.5).

Швы для тестов: _screenshot_b64 / _post_chat / health / health_cached /
_VISION_ERROR — tests/test_eyes.py подменяет их, реальный сервер и экран
не нужны.
"""
from __future__ import annotations

import base64
import io
import json
import time
from typing import Optional, Tuple

import requests

try:
    import mss
    from PIL import Image
    _MSS = getattr(mss, "MSS", mss.mss)   # mss.mss устарел в новых версиях
    _VISION_ERROR = None
except ImportError as e:
    _MSS = None
    _VISION_ERROR = "нет модуля зрения: %s (venv\\Scripts\\pip install mss pillow)" % e

EYES = "http://127.0.0.1:8083"
EYES_TIMEOUT = 240          # холодный старт CUDA ~50 с — не подрезаем
WORK_WIDTH = 1280           # рабочая точка Г-1: ~8.8 с на GTX 1060

PROMPT = (
    "Ты — зрительный сенсор интерфейсов. Опиши экран строго одним JSON, "
    "одной строкой, без пояснений.\n"
    'Пример ответа: {"active_window":"Командная строка","elements":'
    '[{"type":"text","text":"C:\\Marfa>","bbox":[64,32,412,58],"confidence":0.9}],'
    '"summary":"рабочий стол с окнами"}\n'
    'Поле type — ровно ОДНО слово из: button, input, link, menu, text, icon, '
    "image. Перечисление через | в ответе запрещено.\n"
    "Правила: bbox — пиксели входного изображения [x1,y1,x2,y2]; "
    "не выдумывай элементы; нечитаемое — confidence меньше 0.4; лучше меньше "
    "элементов, чем выдуманные; НЕ БОЛЕЕ 10 элементов — только самые крупные "
    "и заметные."
)

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
         max_tokens: int = 1500) -> Tuple[str, bool]:
    """Спросить глаза. Сначала с response_format/json_schema; если сервер
    грамматику не знает (или запрос упал) — повтор без грамматики.
    Возвращает (текст ответа, была ли принята схема)."""
    attempts = [schema, None] if schema else [None]
    last = None
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
        try:
            data = _post_chat(body)
            return data["choices"][0]["message"]["content"], bool(sch)
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
    """Дескриптор экрана: active_window + elements + summary.
    Поднимает исключения (сервер, парс) — безопасная обёртка для чата:
    describe_text()."""
    if _VISION_ERROR:
        raise RuntimeError("глаза не готовы: " + _VISION_ERROR)
    b64, _real, _small = _screenshot_b64(width)
    out, _ = _ask(b64, PROMPT, SCHEMA)
    return parse_json(out)


def describe_text(width: int = WORK_WIDTH) -> str:
    """Глазами в чат: честный текст для панели, исключений не поднимает.
    Это ответ агента, а не модели — мозг молчит."""
    try:
        if _VISION_ERROR:
            return "глаза не готовы: " + _VISION_ERROR
        if not health():
            return "глаза 8083 не отвечают — сервер зрения не запущен?"
        t0 = time.time()
        d = describe(width)
        secs = time.time() - t0
        if not isinstance(d.get("elements"), list):
            return ("глаза ответили, но без списка элементов — "
                    "зафиксируй в протоколе")
        lines = []
        aw = d.get("active_window")
        if aw:
            lines.append("Активное окно: " + str(aw))
        for i, el in enumerate(d.get("elements", [])[:10], 1):
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
        if s:
            lines.append("Сводка: " + str(s))
        head = "Вижу экран, %d элементов:" % len(d.get("elements", []))
        return "\n".join([head] + lines) + "\n(глаза думали %.1f с)" % secs
    except Exception as e:
        return "глаза ошиблись: " + str(e)
