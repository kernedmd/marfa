# -*- coding: utf-8 -*-
"""web/app.py — ПАНЕЛЬ ДОМА (ТЗ 2.2): 5001, порт 5000 не трогаем.

Восстановлена 2026-11-18 по контракту tests/test_monitor_web.py (канон v9.3):
/ — панель с RAM (Ф97), /api/status — машина (ram + brain + аудит СТРАЖА),
/api/chat — разговор с агентом, /chat — страница чата.
"""
from __future__ import annotations

from pathlib import Path

import json
from flask import Flask, jsonify, request

from core import config
from core.agent import Agent
from core.brain import BrainClient
from safety.log_audit import audit
from sensors.monitor import RAMMonitor

app = Flask(__name__)
PORT_WEB = config.PORT_WEB

PANEL_HTML = """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<title>Марфа — панель дома</title>
<style>
  body { font-family: system-ui, sans-serif; background: #10141c; color: #e8eaf0;
         max-width: 720px; margin: 40px auto; padding: 0 16px; }
  h1 { font-size: 22px; } h2 { font-size: 17px; margin-top: 28px; color: #9fc1ff; }
  .card { background: #181e2a; border: 1px solid #2a3244; border-radius: 10px;
          padding: 14px 18px; margin: 10px 0; }
  .ok { color: #7fd88f; } .warn { color: #e6c86e; } .crit { color: #ff7f7f; }
  a { color: #9fc1ff; }
</style>
</head>
<body>
<h1>Марфа — панель дома</h1>

<h2>Память RAM (Ф97)</h2>
<div class="card" id="ram">бюджет дома: 44 из 64 ГБ (пороги Ф97: 85/92). Замер...</div>

<h2>Мозг (30B, порт 8082)</h2>
<div class="card" id="brain">проверяю...</div>

<h2>Уши (сторож имени «Марфа»)</h2>
<div class="card" id="ears">прислушиваюсь...</div>

<h2>СТРАЖ (аудит логов, Ф81)</h2>
<div class="card" id="guard">проверяю цепочку...</div>

<h2>Чат</h2>
<div class="card"><a href="/chat">Открыть чат с Марфой</a></div>

<p>Порядок дома: панель — 5001, мозг — 8082, порт 5000 не трогаем.</p>

<script>
function cls(level) { return level === "CRIT" ? "crit" : (level === "WARN" ? "warn" : "ok"); }
fetch("/api/status").then(r => r.json()).then(s => {
  const ram = s.ram;
  document.getElementById("ram").innerHTML =
    "занято <b>" + ram.used_gb + " из " + ram.total_gb + " ГБ (" + ram.pct + "%)</b>, " +
    "уровень <b class='" + cls(ram.level) + "'>" + ram.level + "</b> " +
    "(бюджет 44 из 64, пороги Ф97: " + ram.warn_pct + "/" + ram.crit_pct + ")";
  const b = s.brain;
  document.getElementById("brain").innerHTML = b.healthy
    ? "<b class='ok'>жив</b> (" + b.url + ")"
    : "<b class='crit'>не отвечает</b> (" + b.url + ") — грузится или выключен";
  const e = s.ears;
  if (e.state === "ok") {
    document.getElementById("ears").innerHTML =
      "<b class='ok'>слушают</b>" +
      (e.last_wake ? " — последний зов: " + e.last_wake : " — имени ещё не слышали");
  } else if (e.state === "no_mic") {
    document.getElementById("ears").innerHTML =
      "<b class='warn'>ждут микрофон</b> — воткни или выбери устройством ввода";
  } else if (e.state === "no_model") {
    document.getElementById("ears").innerHTML =
      "<b class='warn'>модель ушей не найдена</b> — нажми scripts\\85_fix_ears.bat";
  } else if (e.state === "no_sounddevice") {
    document.getElementById("ears").innerHTML =
      "<b class='warn'>нет sounddevice</b> — pip install sounddevice в venv Марфы";
  } else {
    document.getElementById("ears").innerHTML =
      "<b class='crit'>служба ушей не отвечает</b> — поднимается со стартом дома";
  }
  document.getElementById("guard").innerHTML =
    "вердикт: <b class='" + (s.guard_audit_verdict === "OK" ? "ok" : "crit") + "'>" +
    s.guard_audit_verdict + "</b>";
}).catch(e => {
  document.getElementById("ram").textContent = "статус недоступен: " + e;
});
</script>
</body>
</html>
"""


def _brain_health() -> dict:
    try:
        return {"healthy": BrainClient().health(), "url": config.BRAIN_URL}
    except Exception:
        return {"healthy": False, "url": config.BRAIN_URL}


def _ears_state() -> dict:
    """Состояние ушей — из статус-файла службы (data\\ears_status.json).

    Файла нет — служба ещё не поднималась (или дом только что встал):
    честный state=down, панель не врёт и не падает.
    """
    try:
        rec = json.loads(Path(config.EARS_STATUS_FILE).read_text(encoding="utf-8"))
        return {"state": rec.get("state", "down"),
                "last_wake": rec.get("last_wake", ""),
                "ts": rec.get("ts", "")}
    except (OSError, ValueError):
        return {"state": "down", "last_wake": "", "ts": ""}


@app.get("/health")
def health():
    return jsonify({"status": "ok", "port": PORT_WEB})


@app.get("/api/status")
def api_status():
    ram = RAMMonitor().sample()
    return jsonify({
        "ram": ram,
        "brain": _brain_health(),
        "ears": _ears_state(),
        "guard_audit_verdict": audit()["verdict"],
    })


@app.get("/")
def panel():
    return PANEL_HTML


@app.post("/api/chat")
def api_chat():
    data = request.get_json(force=True, silent=True) or {}
    text = data.get("text", "").strip()
    if not text:
        return jsonify({"error": "empty"}), 400
    try:
        reply = Agent().handle(text)
        return jsonify({"reply": reply.text})
    except Exception as e:
        return jsonify({"reply": "Ошибка: " + str(e)}), 500


@app.get("/chat")
def chat_page():
    chat_path = Path(__file__).parent / "templates" / "chat.html"
    return chat_path.read_text(encoding="utf-8")


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=PORT_WEB, debug=False)
