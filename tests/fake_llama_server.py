# -*- coding: utf-8 -*-
"""Мок llama-server на 127.0.0.1:<случайный порт> для офлайн-тестов (ТЗ 3.2).

Ведёт себя как настоящий llama-server в границах, нужных тестам:
GET /health → 200; POST /v1/chat/completions → canned-ответ.
"""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class FakeLlamaServer(ThreadingHTTPServer):
    """Порт 0 → ОС даст свободный порт. Поля можно менять из теста."""

    def __init__(self) -> None:
        super().__init__(("127.0.0.1", 0), FakeLlamaHandler)
        self.reply_content = json.dumps({"answer": "я здесь"}, ensure_ascii=False)
        self.script: list[str] = []   # если задан — ответы по порядку (для ретраев)
        self.reply_status = 200       # 500 имитирует брак сервера
        self.calls: list[dict] = []   # список входящих payload'ов
        self.usage_extra: dict = {}   # досказать в usage (промпт-токены и пр.)

    @property
    def base_url(self) -> str:
        host, port = self.server_address[:2]
        return f"http://{host}:{port}"


class FakeLlamaHandler(BaseHTTPRequestHandler):
    def log_message(self, *args) -> None:  # тишина в логах тестов
        pass

    def _send(self, obj: dict, status: int = 200) -> None:
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health":
            self._send({"status": "ok"})
        else:
            self._send({"error": "нет такого пути"}, 404)

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", 0))
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except json.JSONDecodeError:
            self._send({"error": "битый JSON"}, 400)
            return
        self.server.calls.append(payload)
        if self.server.reply_status != 200:
            self._send({"error": "внутренняя поломка"}, self.server.reply_status)
            return
        if self.server.script:
            content = self.server.script.pop(0)
        else:
            content = self.server.reply_content
        if isinstance(content, Exception):
            self._send({"error": str(content)}, 500)
            return
        usage = {"completion_tokens": max(1, len(content) // 3)}
        usage.update(self.server.usage_extra or {})
        self._send({
            "choices": [{"message": {"role": "assistant", "content": content}}],
            "usage": usage,
        })


def start_fake_brain() -> FakeLlamaServer:
    srv = FakeLlamaServer()
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    return srv
