# -*- coding: utf-8 -*-
"""core/brain.py — МОЗГ ДОМА (ТЗ 3.2, ADR-002): клиент 8082, строгий JSON, фоллбэк.

Восстановлен 2026-11-18 по контракту tests/test_brain.py (канон v9.3):
- chat(): обычный трек, генерация не выше бюджета 768 (0.3);
- ask_json(): строгий JSON, при браке — повтор с укором, regex-спасение ЗАПРЕЩЕНО;
- фоллбэк №37: провайдер с available()/ask() подставляется снаружи (GigaChat);
- usage_tokens(): честный расход из сырого ответа сервера.
"""
from __future__ import annotations

import json
import urllib.request
from pathlib import Path
from typing import Optional

from core import config


class BrainError(Exception):
    """Мозг не ответил или ответил не-JSON. Наверх уходит как честная ошибка."""


# ---------------------------------------------------------------
# №9 «Темперамент из доктрины»: настроение Марфы читается из
# data/creator_doctrine.json (поле mood), а не зашито в код.
# Создатель может сделать её живее (temperature выше) или строже
# (ниже) правкой одного файла — без правки кода дома.
# Нет файла / нет поля / брак — характер по умолчанию: 0.3.
# ---------------------------------------------------------------
DEFAULT_TEMPERATURE = 0.3


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

    # ---------- транспорт ----------

    def _post(self, path: str, payload: dict) -> dict:
        """POST JSON к llama-server. Любая поломка -> BrainError."""
        req = urllib.request.Request(
            self.url + path,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
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
        mt = cap if gen_tokens is None else min(int(gen_tokens), cap)
        mood = mood_params()
        temp = (float(temperature) if temperature is not None
                else mood.get("temperature", DEFAULT_TEMPERATURE))
        payload = {"messages": messages, "temperature": temp, "max_tokens": mt}
        top_p_val = (float(top_p) if top_p is not None
                     else mood.get("top_p"))
        if top_p_val is not None:
            payload["top_p"] = top_p_val
        data = self._post("/v1/chat/completions", payload)
        return data["choices"][0]["message"]["content"]

    # ---------- строгий JSON (ADR-002) ----------

    def ask_json(self, user_text: str, system_extra: str = "", retries: int = 2,
                 history: Optional[list] = None) -> dict:
        """Спросить мозг и получить dict. Брак -> повтор с укором -> фоллбэк/ошибка.

        ADR-002: JSON, завёрнутый в посторонний текст, НЕ спасается регулярками —
        только честный повтор. Выдумывать ответ вместо мозга запрещено.
        №10: history — прошлые ходы [{role, content}], вставляются ПОСЛЕ
        системного промпта и ДО нового сообщения: префиксный KV-кэш цел,
        разговор не рвётся.
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
            if isinstance(t, dict) and t.get("role") in ("user", "assistant") \
                    and isinstance(t.get("content"), str) and t["content"].strip():
                messages.append({"role": t["role"], "content": t["content"]})
        messages.append({"role": "user", "content": user_text})
        attempts = max(1, retries)
        mood = mood_params()   # №9: характер — из доктрины Создателя
        for _ in range(attempts):
            payload = {
                "messages": messages,
                "temperature": mood.get("temperature", DEFAULT_TEMPERATURE),
                "max_tokens": config.GENERATION_BUDGET_TOKENS,
                "response_format": {"type": "json_object"},
            }
            if "top_p" in mood:
                payload["top_p"] = mood["top_p"]
            data = self._post("/v1/chat/completions", payload)
            raw = data["choices"][0]["message"]["content"]
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
