# -*- coding: utf-8 -*-
r"""web/app.py — ЛОКАЛЬНАЯ ПАНЕЛЬ МАРФЫ, порт 5001 (ТЗ 2.3, 2.2).

Порт 5000 НЕ ТРОГАЕМ (правило 6.4). Панель показывает: RAM-статус Ф97,
здоровье мозга 8082, последние события СТРАЖА (Ф81-совместимо), план дня.
Запуск: scripts\start_marfa.bat  или  python -m web.app
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path

from flask import Flask, jsonify

from core import config
from core.autonomy import DayPlanner
from safety.log_audit import audit
from sensors.monitor import RAMMonitor

app = Flask(__name__)
PORT_WEB = config.PORT_WEB          # 5001; здесь и только здесь Flask слушает


def _brain_health() -> dict:
    """Жив ли llama-server (короткий таймаут — панель не должна виснуть)."""
    try:
        with urllib.request.urlopen(config.BRAIN_URL + "/health", timeout=2) as resp:
            return {"healthy": resp.status == 200, "url": config.BRAIN_URL}
    except Exception:  # noqa: BLE001 — любые сетевые причины = "нет"
        return {"healthy": False, "url": config.BRAIN_URL}


def _guard_tail(limit: int = 10) -> list[dict]:
    path = Path(config.GUARD_LOG_FILE)
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines()[-limit:]:
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return list(reversed(out))


@app.get("/health")
def health():
    return jsonify({"status": "ok", "port": PORT_WEB})


@app.get("/api/status")
def api_status():
    monitor = RAMMonitor()
    status = monitor.observe()
    return jsonify({
        "ram": status,
        "brain": _brain_health(),
        "guard_tail": _guard_tail(),
        "guard_audit_verdict": audit().get("verdict"),
        "plan_today": DayPlanner().load_plan(),
    })


@app.get("/")
def panel():
    status = RAMMonitor().observe()
    brain = _brain_health()
    plan = DayPlanner().load_plan()
    ram_color = {"OK": "#2e7d32", "WARN": "#ef6c00", "CRIT": "#c62828"}[status["level"]]
    ram_fill = min(100.0, status["pct"])
    tasks = "".join(
        f"<li>{t['title']} <small>({t.get('priority')}, {t.get('status')})</small></li>"
        for t in (plan or {}).get("tasks", [])[:15]
    ) or "<li>задач нет</li>"
    carry = "".join(f"<li>{c}</li>" for c in (plan or {}).get("carry_over", [])) or "<li>переносов нет</li>"
    guard_rows = "".join(
        f"<tr><td>{e.get('ts')}</td><td>{e.get('level')}</td><td>{e.get('rule')}</td>"
        f"<td>{e.get('reason')}</td></tr>"
        for e in _guard_tail()
    ) or "<tr><td colspan='4'>событий нет</td></tr>"
    audit_verdict = audit().get("verdict")
    # Урок 13.11.2026 (коммит 28): в выражении f-string нельзя «\» на Python 3.11
    # (машина Z440) — PEP 701 разрешил только с 3.12, поэтому песочница разработчика
    # не видела падение, а pytest у пользователя рапортовал «1 error during collection».
    # Текст состояния мозга считаем ДО шаблона: в f-выражении остаётся только имя.
    brain_state = ("здоров" if brain["healthy"] else
                   "<b style='color:#c62828'>НЕ ОТВЕЧАЕТ</b> — см. scripts\\start_llama_server.bat")

    return f"""<!doctype html><html lang="ru"><head><meta charset="utf-8">
<title>Марфа — панель дома</title><style>
body{{font-family:Arial,sans-serif;background:#f4f4f8;margin:0;padding:24px;color:#222}}
h1{{font-size:26px}} h2{{font-size:18px;margin-top:28px}}
.card{{background:#fff;border-radius:8px;padding:16px 20px;box-shadow:0 1px 4px rgba(0,0,0,.12);max-width:860px}}
.bar{{background:#e0e0e0;border-radius:6px;height:22px;overflow:hidden}}
.bar>div{{height:100%;background:{ram_color};width:{ram_fill}%}}
.mono{{font-family:Consolas,monospace;font-size:13px}}
table{{border-collapse:collapse;width:100%;font-size:13px}}
td,th{{border:1px solid #ddd;padding:4px 8px;text-align:left}}
small{{color:#666}}</style></head><body>
<h1>Марфа — панель дома</h1>
<div class="card">
  <h2>Память RAM (Ф97)</h2>
  <div class="bar"><div></div></div>
  <p><b style="color:{ram_color}">{status["level"]}</b> — {status["used_gb"]} ГБ из
     {status["total_gb"]} ГБ ({status["pct"]}%) · тревога ≥{status["warn_pct"]}%, критично ≥{status["crit_pct"]}%
     · план дома 44 из 64 ГБ (0.1) · замер {status["ts"]}</p>
  <h2>Мозг (30B на CPU)</h2>
  <p>{brain_state} <small>({brain["url"]}, порт 8082, --mlock, контекст 4096)</small></p>
  <h2>План дня (Ф71)</h2>
  <ul>{tasks}</ul>
  <h2>Перенос со вчера</h2><ul>{carry}</ul>
  <h2>СТРАЖ — последние события (аудит: {audit_verdict})</h2>
  <table><tr><th>время</th><th>уровень</th><th>правило</th><th>причина</th></tr>{guard_rows}</table>
  <h2>Служба</h2>
  <p class="mono">web: порт {PORT_WEB} (5000 не трогаем — 6.4) · квант: {config.DEFAULT_QUANT} ·
     контекст {config.CONTEXT_TOKENS} (0.3) · audit: python -m safety.log_audit</p>
</div></body></html>"""


if __name__ == "__main__":  # pragma: no cover — запуск на Z440
    assert PORT_WEB != config.PORT_FORBIDDEN, "порт 5000 запрещён правилом 6.4"
    app.run(host="127.0.0.1", port=PORT_WEB, debug=False)
