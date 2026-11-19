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
from typing import Optional

from core import config


class BrainError(Exception):
    """Мозг не ответил или ответил не-JSON. Наверх уходит как честная ошибка."""


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

    def chat(self, messages: list, gen_tokens: Optional[int] = None) -> str:
        """Чат без JSON-дисциплины. max_tokens не выше бюджета генерации (0.3)."""
        cap = config.GENERATION_BUDGET_TOKENS
        mt = cap if gen_tokens is None else min(int(gen_tokens), cap)
        payload = {"messages": messages, "temperature": 0.3, "max_tokens": mt}
        data = self._post("/v1/chat/completions", payload)
        return data["choices"][0]["message"]["content"]

    # ---------- строгий JSON (ADR-002) ----------

    def ask_json(self, user_text: str, system_extra: str = "", retries: int = 2) -> dict:
        """Спросить мозг и получить dict. Брак -> повтор с укором -> фоллбэк/ошибка.

        ADR-002: JSON, завёрнутый в посторонний текст, НЕ спасается регулярками —
        только честный повтор. Выдумывать ответ вместо мозга запрещено.
        """
        messages = [
            {"role": "system", "content": (
                "Ты — Марфа, умный и верный ассистент. "
                "Ты должна отвечать пользователю строго в формате JSON: "
                "{\"answer\": \"твой текст\"} или "
                "{\"action\": {\"tool\": \"...\", \"args\": {...}}}. "
                "Не пиши ничего вне JSON. Если пользователь просто здоровается, "
                "поздоровайся в ответ внутри JSON.\n" + system_extra)},
            {"role": "user", "content": user_text},
        ]
        attempts = max(1, retries)
        for _ in range(attempts):
            payload = {
                "messages": messages,
                "temperature": 0.3,
                "max_tokens": config.GENERATION_BUDGET_TOKENS,
                "response_format": {"type": "json_object"},
            }
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
