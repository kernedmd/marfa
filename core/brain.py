# -*- coding: utf-8 -*-
"""core/brain.py — МОЗГ ДОМА (ТЗ 3.2, ADR-002): клиент 8082, строгий JSON, фоллбэк.

Восстановлен 2026-11-18 по контракту tests/test_brain.py (канон v9.3):
- chat(): обычный трек, генерация не выше бюджета 768 (0.3);
- ask_json(): строгий JSON, при браке — повтор с укором, regex-спасение ЗАПРЕЩЕНО;
- фоллбэк №37: провайдер с available()/ask() подставляется снаружи (GigaChat);
- usage_tokens(): честный расход из сырого ответа сервера.

СКОРОСТЬ v1 (22.11, доклад Создателя «ответ через две минуты — это очень
долго»): у чат-ответа — СВОЙ бюджет первого захода (BRAIN_ANSWER_TOKENS,
320): краткий ответ на CPU стоит ~40 с, а не две минуты. Обрезанный
JSON — не приговор: повтор уходит с полным бюджетом (обрезка — одна
из причин брака, лечится местом, а не укором). Стрим: ask_json(on_text)
печатает ответ в эфир ЖИВЬЁМ — чат видит рождение текста по мере
генерации, а не после последнего токена.
"""
from __future__ import annotations

import json
import re
import urllib.request
from pathlib import Path
from typing import Callable, Optional

from core import config


class BrainError(Exception):
    """Мозг не ответил или ответил не-JSON. Наверх уходит как честная ошибка."""


def _extract_content(data) -> str:
    """H6 аудита: сервер вернул 200 с телом без choices ("error", пустой
    список) — это BrainError с честным диагнозом, а не KeyError.
    «Мозг недоступен» и «мозг ответил криво» — разные болезни, разное
    лечение: вторая лечится ретраем, первая — доктором."""
    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as e:
        raise BrainError("мозг вернул ответ без choices (%s): %s"
                         % (type(e).__name__, str(data)[:200]))


# ---------------------------------------------------------------
# №9 «Темперамент из доктрины»: настроение Марфы читается из
# data/creator_doctrine.json (поле mood), а не зашито в код.
# Создатель может сделать её живее (temperature выше) или строже
# (ниже) правкой одного файла — без правки кода дома.
# Нет файла / нет поля / брак — характер по умолчанию: 0.3.
# ---------------------------------------------------------------
DEFAULT_TEMPERATURE = 0.3

# Qwen3 умеет «думать вслух» блоками <think>…</think> ДО ответа.
# Грамматика json_object обычно не пускает их в генерацию, но не все
# сборки сервера держат грамматику: пустой think-блок перед JSON —
# самый дешёвый способ угробить парс и заплатить минутой ретрая.
# Стриппер — страховка, не режим.
_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)


def _strip_think(raw: str) -> str:
    """Убрать think-блоки Qwen3 — JSON остаётся чистым."""
    return _THINK_RE.sub("", raw or "").strip()


def mood_params() -> dict:
    """Темперамент из доктрины Создателя. Валидно — берём, брак — молча дефолт.

    Формат в creator_doctrine.json:
        {"doctrine": "...", "mood": {"temperature": 0.6, "top_p": 0.8}}
    Границы здравого смысла: temperature 0.05..2.0, top_p 0.05..1.0 —
    всё, что вне, считаем опечаткой и игнорируем ЦЕЛИКОМ (полумеры
    из битого файла опаснее дефолта).
    """
    try:
        raw = Path(config.DOCTRINE_FILE).read_text(encoding="utf-8")
        mood = (json.loads(raw) or {}).get("mood")
        if not isinstance(mood, dict):
            return {}
        t = float(mood.get("temperature", DEFAULT_TEMPERATURE))
        if not (0.05 <= t <= 2.0):
            return {}
        out = {"temperature": t}
        if "top_p" in mood:
            p = float(mood["top_p"])
            if 0.05 <= p <= 1.0:
                out["top_p"] = p
        return out
    except Exception:   # нет файла, битый JSON, не те типы — дефолт
        return {}


class BrainClient:
    def __init__(self, brain_url: str = "") -> None:
        # brain_url: переопределение для тестов (фальшивый сервер);
        # пустая строка -> адрес из закона дома (core/config.py).
        self.url = brain_url or config.BRAIN_URL
        self.fallback = None  # провайдер фоллбэка (№37): available() + ask(prompt)
        # последний честный расход (usage ответа) — для штампа «N ток»
        self.last_usage: dict = {}

    # ---------- транспорт ----------

    def _post(self, path: str, payload: dict) -> dict:
        """POST JSON к llama-server. Любая поломка -> BrainError.

        Таймаут — из закона дома (BRAIN_TIMEOUT_SEC, 300 с): Pascal-мозг
        честно думает минутами, обрывать его на 120-й секунде — ложь
        (урок переписки 22.11: «изучи себя» обрывалось ровно так).
        """
        req = urllib.request.Request(
            self.url + path,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(
                    req, timeout=config.BRAIN_TIMEOUT_SEC) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except BrainError:
            raise
        except Exception as e:
            raise BrainError(str(e))

    # ---------- доступность ----------

    def health(self) -> bool:
        try:
            with urllib.request.urlopen(self.url + "/health", timeout=5) as r:
                return r.status == 200
        except Exception:
            return False

    # ---------- стрим (СКОРОСТЬ v1): ответ печатается живьём ----------

    def _post_stream(self, path: str, payload: dict,
                     on_text: Callable[[str], None]) -> dict:
        """POST со стримом SSE: дельты текста летят в on_text ПО МЕРЕ
        генерации — чат показывает рождение ответа, не тишину.

        Возвращает тот же словарь, что _post (content собран из дельт).
        Сервер проигнорировал "stream" и ответил обычным JSON — читаем
        целиком и зовём on_text один раз: превью всё равно состоится,
        пусть и разом (фоллбэк-честность, фейк-сервер тестов живёт так).
        Поломка on_text НЕ рвёт запрос: превью — косметика, мышление —
        работа (закон эфира).
        """
        body = dict(payload)
        body["stream"] = True
        body["stream_options"] = {"include_usage": True}
        req = urllib.request.Request(
            self.url + path,
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(
                    req, timeout=config.BRAIN_TIMEOUT_SEC) as resp:
                chunks: list = []
                usage: dict = {}
                sse = False
                raw_lines: list = []
                for line in resp:
                    raw_lines.append(line)
                    text_line = line.decode("utf-8", errors="replace").strip()
                    if not text_line.startswith("data:"):
                        continue
                    sse = True
                    data_str = text_line[5:].strip()
                    if data_str == "[DONE]":
                        continue
                    try:
                        obj = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(obj.get("usage"), dict) and obj["usage"]:
                        usage = obj["usage"]
                    try:
                        delta = obj["choices"][0].get("delta") or {}
                    except (IndexError, KeyError, TypeError, AttributeError):
                        continue
                    piece = delta.get("content") or ""
                    if piece:
                        chunks.append(piece)
                        try:
                            on_text("".join(chunks))
                        except Exception:
                            pass      # превью сломалось — ответ живёт
                if not sse:
                    data = json.loads(
                        b"".join(raw_lines).decode("utf-8", errors="replace"))
                    content = _extract_content(data)
                    try:
                        on_text(content)
                    except Exception:
                        pass
                    return data
                return {"choices": [{"message": {
                            "role": "assistant",
                            "content": "".join(chunks)}}],
                        "usage": usage}
        except BrainError:
            raise
        except Exception as e:
            raise BrainError(str(e))

    # ---------- обычный чат ----------

    def chat(self, messages: list, gen_tokens: Optional[int] = None,
             temperature: Optional[float] = None,
             top_p: Optional[float] = None) -> str:
        """Чат без JSON-дисциплины. max_tokens не выше бюджета генерации (0.3).

        Температура: явный аргумент > настроение из доктрины (№9) > 0.3.
        top_p (фикс сэмплинга Qwen3, живой язык): явный аргумент >
        настроение из доктрины > параметр не шлётся вовсе.
        """
        cap = config.GENERATION_BUDGET_TOKENS
        # M1 аудита: gen_tokens=0/-1 не превращается в max_tokens=0
        # (сервер вернул бы пустоту или ошибку) — нижняя граница 1
        mt = cap if gen_tokens is None else max(1, min(int(gen_tokens), cap))
        mood = mood_params()
        temp = (float(temperature) if temperature is not None
                else mood.get("temperature", DEFAULT_TEMPERATURE))
        payload = {"messages": messages, "temperature": temp, "max_tokens": mt}
        top_p_val = (float(top_p) if top_p is not None
                     else mood.get("top_p"))
        if top_p_val is not None:
            payload["top_p"] = top_p_val
        data = self._post("/v1/chat/completions", payload)
        return _extract_content(data)

    # ---------- строгий JSON (ADR-002) ----------

    def ask_json(self, user_text: str, system_extra: str = "", retries: int = 2,
                 history: Optional[list] = None,
                 max_tokens: Optional[int] = None,
                 on_text: Optional[Callable[[str], None]] = None) -> dict:
        """Спросить мозг и получить dict. Брак -> повтор с укором -> фоллбэк/ошибка.

        ADR-002: JSON, завёрнутый в посторонний текст, НЕ спасается регулярками —
        только честный повтор. Выдумывать ответ вместо мозга запрещено.
        №10: history — прошлые ходы [{role, content}], вставляются ПОСЛЕ
        системного промпта и ДО нового сообщения: префиксный KV-кэш цел,
        разговор не рвётся.

        СКОРОСТЬ v1: max_tokens — бюджет ПЕРВОГО захода (чат Марфы живёт
        на BRAIN_ANSWER_TOKENS: краткость — часть закона дома); повторы
        уходят с полным бюджетом — обрезанный JSON лечится местом.
        on_text — стрим-превью: текст летит в эфир по мере генерации.
        """
        messages = [
            {"role": "system", "content": (
                "Ты — Марфа, умный и верный ассистент. "
                "Ты должна отвечать пользователю строго в формате JSON: "
                "{\"answer\": \"твой текст\"} или "
                "{\"action\": {\"tool\": \"...\", \"args\": {...}}}. "
                "Не пиши ничего вне JSON. Если пользователь просто здоровается, "
                "поздоровайся в ответ внутри JSON.\n" + system_extra)},
        ]
        for t in (history or []):   # только user/assistant, мусор — мимо
            if not (isinstance(t, dict) and t.get("role") in ("user", "assistant")):
                continue
            content = t.get("content")
            if not (isinstance(content, str) and content.strip()):
                # H9 (раунд 2): DialogStore.turns отдаёт text — это тоже
                # валидная история, а не «мусор мимо»
                content = t.get("text")
            if isinstance(content, str) and content.strip():
                messages.append({"role": t["role"], "content": content})
        messages.append({"role": "user", "content": user_text})
        attempts = max(1, retries)
        mood = mood_params()   # №9: характер — из доктрины Создателя
        first_cap = (config.GENERATION_BUDGET_TOKENS if max_tokens is None
                     else min(int(max_tokens), config.GENERATION_BUDGET_TOKENS))
        for i in range(attempts):
            payload = {
                "messages": messages,
                "temperature": mood.get("temperature", DEFAULT_TEMPERATURE),
                "max_tokens": (first_cap if i == 0
                               else config.GENERATION_BUDGET_TOKENS),
                "response_format": {"type": "json_object"},
            }
            if "top_p" in mood:
                payload["top_p"] = mood["top_p"]
            if on_text is not None:
                data = self._post_stream("/v1/chat/completions", payload, on_text)
            else:
                data = self._post("/v1/chat/completions", payload)
            raw = _extract_content(data)
            raw = _strip_think(raw)
            usage = data.get("usage")
            if isinstance(usage, dict):
                self.last_usage = {
                    "prompt_tokens": int(usage.get("prompt_tokens") or 0),
                    "completion_tokens": int(usage.get("completion_tokens") or 0),
                }
            try:
                out = json.loads(raw)
                if isinstance(out, dict):
                    return out
            except (json.JSONDecodeError, TypeError):
                pass
            # брак: укор и повтор тем же разговором
            messages = messages + [
                {"role": "assistant", "content": raw},
                {"role": "user", "content": (
                    "Твой прошлый ответ не был валидным JSON. "
                    "Ответь ещё раз строго валидным JSON, без текста вокруг.")},
            ]
        # все попытки дали брак: фоллбэк №37, если он есть и жив
        fb = getattr(self, "fallback", None)
        if fb is not None and fb.available():
            return {"answer": fb.ask(user_text), "source": "fallback"}
        raise BrainError("мозг не дал валидный JSON за " + str(attempts) + " попыток")

    # ---------- usage ----------

    @staticmethod
    def usage_tokens(raw: dict) -> int:
        """Честный расход токенов из сырого ответа llama-server."""
        usage = (raw or {}).get("usage") or {}
        try:
            return int(usage.get("completion_tokens", 0))
        except (TypeError, ValueError):
            return 0
