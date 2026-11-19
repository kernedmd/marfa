# -*- coding: utf-8 -*-
"""tests/test_status.py — тесты чистых функций marfa_status и sync_and_test.

Гейт батареи не нарушают: ничего не пишут в память/доктрину, проверяют
только форматирование, пороги Ф97 и то, что .env-значения не утекают.
"""
from __future__ import annotations

import threading
import http.server
import socket

import marfa_status as st


# ---------- fmt_gb ----------

def test_fmt_gb_rounds_to_tenth():
    assert st.fmt_gb(1024 ** 3) == 1.0
    assert st.fmt_gb(18.63 * 1024 ** 3) == 18.6
    assert st.fmt_gb(0) == 0.0


# ---------- ram_verdict (Ф97: 85/92) ----------

def test_ram_verdict_green_zone():
    assert st.ram_verdict(53.0) == st.OK
    assert st.ram_verdict(84.9) == st.OK


def test_ram_verdict_warn_and_crit_boundaries():
    assert st.ram_verdict(85.0) == st.WARN     # граница тревоги входит
    assert st.ram_verdict(91.9) == st.WARN
    assert st.ram_verdict(92.0) == st.FAIL    # граница крита входит
    assert st.ram_verdict(99.0) == st.FAIL


# ---------- parse_porcelain ----------

def test_parse_porcelain_counts_lines():
    sample = " M web/app.py\n?? notes.txt\nA  core/new.py\n\n"
    assert st.parse_porcelain(sample) == 3
    assert st.parse_porcelain("") == 0


# ---------- env_key_names: Ф105, значения не утекают ----------

def test_env_key_names_names_only_never_values():
    secret_value = "ghp_SUPERSECRETTOKEN1234567890"
    text = (
        "# комментарий\n"
        "ROUTERAI_API_KEY=" + secret_value + "\n"
        "MARFA_ARCHITECT_MODEL=deepseek/deepseek-v4-pro-0813\n"
        "пустая строка выше игнорируется\n"
    )
    names = st.env_key_names(text)
    assert names == ["MARFA_ARCHITECT_MODEL", "ROUTERAI_API_KEY"]
    joined = " ".join(names)
    assert secret_value not in joined              # значение не попало
    assert "deepseek" not in joined                # и это тоже значение


# ---------- probe: живой HTTP против мёртвого порта ----------

def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class _OKHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802 — так требует http.server
        self.send_response(200)
        self.end_headers()

    def log_message(self, *args):  # не шумим в вывод pytest
        pass


def test_probe_real_server_and_dead_port():
    port = _free_port()
    srv = http.server.HTTPServer(("127.0.0.1", port), _OKHandler)
    t = threading.Thread(target=srv.handle_request, daemon=True)
    t.start()
    try:
        assert st.probe("http://127.0.0.1:" + str(port) + "/", timeout=3) is True
    finally:
        srv.server_close()
    dead = _free_port()  # никто не слушает
    assert st.probe("http://127.0.0.1:" + str(dead) + "/", timeout=1) is False
