# -*- coding: utf-8 -*-
"""web/app.py — ПАНЕЛЬ ДОМА (ТЗ 2.2): 5001, порт 5000 не трогаем.

Восстановлена 2026-11-18 по контракту tests/test_monitor_web.py (канон v9.3):
/ — панель с RAM (Ф97), /api/status — машина (ram + brain + аудит СТРАЖА),
/api/chat — разговор с агентом, /chat — страница чата.
"""
from __future__ import annotations

from pathlib import Path

import datetime as dt
import json
import time

from flask import Flask, jsonify, request

from core import config, progress
from core.agent import Agent
from core.brain import BrainClient
from core.dialog import DialogStore, _safe_session
from core.questions import QuestionBank
from safety.log_audit import audit
from sensors.monitor import RAMMonitor
from web.markdown_render import to_safe_html

app = Flask(__name__)
PORT_WEB = config.PORT_WEB
DIALOGS = DialogStore()          # №10/№11: память разговора живёт в доме

PANEL_HTML = """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<title>Марфа — панель дома</title>
<style>
  body { font-family: system-ui, sans-serif; background: var(--bg); color: var(--text);
         max-width: 720px; margin: 40px auto; padding: 0 16px;
         --bg:#10141c; --card:#181e2a; --border:#2a3244; --text:#e8eaf0; --h:#9fc1ff; }
  body.light { --bg:#f4f6fa; --card:#ffffff; --border:#d0d7de; --text:#1f2328; --h:#3b5b8f; }
  h1 { font-size: 22px; } h2 { font-size: 17px; margin-top: 28px; color: var(--h); }
  .card { background: var(--card); border: 1px solid var(--border); border-radius: 10px;
          padding: 14px 18px; margin: 10px 0; }
  .ok { color: #7fd88f; } .warn { color: #e6c86e; } .crit { color: #ff7f7f; }
  a { color: var(--h); }
  #theme { float: right; padding: 6px 12px; font-size: 13px; background: var(--card); color: var(--text);
           border: 1px solid var(--border); border-radius: 8px; cursor: pointer; }
</style>
</head>
<body>
<button id="theme" onclick="toggleTheme()" title="сменить оформление">день</button>
<h1>Марфа — панель дома</h1>

<h2>Сейчас делает</h2>
<div class="card" id="now">спрашиваю у дома...</div>

<h2>Память RAM (Ф97)</h2>
<div class="card" id="ram">бюджет дома: 44 из 64 ГБ (пороги Ф97: 85/92). Замер...</div>

<h2>Мозг (30B, порт 8082)</h2>
<div class="card" id="brain">проверяю...</div>

<h2>Уши (сторож имени «Марфа»)</h2>
<div class="card" id="ears">прислушиваюсь...</div>

<h2>Стремление (план, вопросы, чтение)</h2>
<div class="card" id="drive">спрашиваю у дома...</div>

<h2>СТРАЖ (аудит логов, Ф81)</h2>
<div class="card" id="guard">проверяю цепочку...</div>

<h2>Чат</h2>
<div class="card"><a href="/chat">Открыть чат с Марфой</a></div>

<p>Порядок дома: панель — 5001, мозг — 8082, порт 5000 не трогаем.</p>

<script>
function cls(level) { return level === "CRIT" ? "crit" : (level === "WARN" ? "warn" : "ok"); }
function esc(s) { return String(s == null ? "" : s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;")
    .replace(/>/g, "&gt;").replace(/"/g, "&quot;"); }
// эфир: чем занята Марфа прямо сейчас — без консоли и без угадывания
function fmtSecs(x) { return (Math.round(x * 10) / 10).toString().replace(".", ","); }
function refreshNow() {
  fetch("/api/progress").then(r => r.json()).then(p => {
    const el = document.getElementById("now");
    if (p.busy) {
      let s = "<b class='ok'>занята</b>: " + esc(p.stage) +
              " <small>(уже " + fmtSecs(p.elapsed) + " с)</small>";
      if (p.sid && !p.mine) s += " <small>— отвечает в другом разговоре</small>";
      el.innerHTML = s;
    } else {
      let s = "свободна — жду в <a href='/chat'>чате</a>";
      if (p.last && p.last.secs) {
        s = "последний ответ: <b>" + fmtSecs(p.last.secs) + " с</b> (" +
            esc(p.last.source) + ", " + esc(p.last.ts) + ") — " + s;
      }
      el.innerHTML = s;
    }
  }).catch(() => {});
}
setInterval(refreshNow, 5000);
refreshNow();
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
      (e.device ? " («" + e.device + "»)" : "") +
      (e.last_wake ? " — последний зов: " + e.last_wake : " — имени ещё не слышали");
  } else if (e.state === "no_mic") {
    document.getElementById("ears").innerHTML =
      "<b class='warn'>микрофон не найден или занят</b> — воткни камеру/микрофон; " +
      "служба перебирает устройства сама и проснётся" +
      (e.error ? "<br><small>" + e.error + "</small>" : "");
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
fetch("/api/drive").then(r => r.json()).then(d => {
  const el = document.getElementById("drive");
  const alive = d.drive_alive;
  let html = alive
    ? "<b class='ok'>жива</b> — план, дневник, вопросы, чтение"
    : "<b class='crit'>служба не отвечает</b> — поднимется со стартом дома";
  if (d.plan && d.plan.open) {
    html += "<br>План на " + d.plan.date + ": открыто " + d.plan.open + " из " + d.plan.total;
  }
  if (d.questions && d.questions.length) {
    html += "<br><b>Хочет спросить:</b>";
    d.questions.forEach(q => {
      html += "<br>• " + q.text.replace(/</g, '&lt;') +
              " <input id='ans-" + q.id + "' placeholder='ответ...' size='12'>" +
              " <button onclick=\"answer('" + q.id + "')\">ответить</button>";
    });
  } else {
    html += "<br>Открытых вопросов нет";
  }
  if (d.last_diary) {
    html += "<br>Последний дневник: " + d.last_diary;
  }
  const lessons = d.lessons_7d || 0;
  if (lessons) {
    html += "<br>Уроков за неделю: " + lessons;
  }
  el.innerHTML = html;
}).catch(e => {
  document.getElementById("drive").textContent = "стремление недоступно: " + e;
});
function answer(qid) {
  const inp = document.getElementById("ans-" + qid);
  const text = (inp && inp.value || "").trim();
  if (!text) return;
  fetch("/api/questions/answer", {
    method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({id: qid, text: text})
  }).then(() => location.reload());
}
function applyTheme(t) {
  document.body.className = (t === "light") ? "light" : "";
  const b = document.getElementById("theme");
  if (b) b.textContent = (t === "light") ? "ночь" : "день";
  localStorage.setItem("marfa-theme", t);
}
function toggleTheme() {
  applyTheme(document.body.className === "light" ? "dark" : "light");
}
applyTheme(localStorage.getItem("marfa-theme") || "dark");
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
                "device": rec.get("device", ""),
                "error": str(rec.get("error", ""))[:160],
                "ts": rec.get("ts", "")}
    except (OSError, ValueError):
        return {"state": "down", "last_wake": "", "device": "", "error": "",
                "ts": ""}


@app.get("/health")
def health():
    return jsonify({"status": "ok", "port": PORT_WEB})


@app.get("/api/health")
def api_health():
    """№13: живой статус-виджет — все три службы одной точкой.

    Шапка чата опрашивает раз в 30 с: панель (сама), мозг (8082),
    глаза (8083, кэшированный пинг — мёртвый порт не тормозит страницу).
    """
    from core.eyes import health_cached
    return jsonify({
        "status": "ok",
        "port": PORT_WEB,
        "panel": True,
        "brain": _brain_health()["healthy"],
        "eyes": health_cached(),
    })


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
    """№10/№11: разговор с сессией. Панель держит имя сессии в localStorage,
    дом — ходы в data/dialog/: F5 и рестарт панели разговор не рвут.

    ЭФИР (22.11, вечер-4): ход начинается begin'ом, заканчивается
    finish'ом — чат живьём показывает стадию и секунды (опрос
    /api/progress), ответ приходит со штампом «N с · кто отвечал»,
    штамп ложится и в память диалога: «сколько думала» переживает F5.
    """
    data = request.get_json(force=True, silent=True) or {}
    text = (data.get("text") or "").strip()
    if not text:
        return jsonify({"error": "empty"}), 400
    try:
        session = _safe_session(str(data.get("session") or "default"))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    history = DialogStore.render_messages(DIALOGS.turns(session))
    progress.begin(session)
    t0 = time.time()
    try:
        reply = Agent().handle(text, history=history)
    except Exception as e:
        progress.finish(source="")
        return jsonify({"reply": "Ошибка: " + str(e)}), 500
    secs = round(time.time() - t0, 1)
    progress.finish(secs=secs, source=reply.source)
    # СКОРОСТЬ v1: сколько токенов напечатал мозг — в штамп и в память
    # диалога: «40,2 с · мозг · 84 ток». Снова две минуты? По токенам
    # сразу видно, кто съел время: декод (много ток) или промпт/ретрай.
    # Аудит-2: и ПРОМПТ-токены тоже (метка ptok) — штамп «165,8 с ·
    # мозг · 273 ток · промпт 2100» отличает долгий декод от долгого
    # префикса без всякой консоли
    tok = None
    ptok = None
    if isinstance(getattr(reply, "meta", None), dict):
        try:
            tok = int(reply.meta.get("tok")) or None
        except (TypeError, ValueError):
            tok = None
        try:
            ptok = int(reply.meta.get("ptok")) or None
        except (TypeError, ValueError):
            ptok = None
    meta = {"secs": secs, "src": reply.source}
    if tok:
        meta["tok"] = tok
    if ptok:
        meta["ptok"] = ptok
    DIALOGS.append(session, "user", text)          # ходы — после ответа:
    DIALOGS.append(session, "assistant", reply.text,  # неудача не портит память
                   meta=meta)
    # №12: готовый безопасный HTML — панель не доверяет мозгу ни байтом
    return jsonify({"reply": reply.text, "html": to_safe_html(reply.text),
                    "session": session, "secs": secs,
                    "source": reply.source, "tok": tok, "ptok": ptok,
                    "source_label": progress.source_label(reply.source)})


@app.get("/api/progress")
def api_progress():
    """Эфир дома: чем Марфа занята прямо сейчас и сколько уже думает.

    Чат опрашивает ежесекундно при ответе, панель — раз в 5 с.
    Сессия не обязательна: панель спрашивает «вообще», эфир отвечает
    без привязки к разговору. Плохое имя сессии — просто без фильтра.
    """
    sid = str(request.args.get("session") or "")
    try:
        sid = _safe_session(sid)
    except ValueError:
        sid = ""
    return jsonify(progress.snapshot(sid))


@app.get("/api/dialog/<session>")
def api_dialog(session):
    """История сессии для страницы чата (переживает F5).

    №12: ответам Марфы прилагается безопасный HTML (сервер экранировал
    всё до разметки); ходы Ильи остаются текстом — их и рендерить нечем.
    Эфир: штампы времени (secs + src_label) едут с ходами Марфы —
    старые записи без штаммов читаются как раньше.
    """
    try:
        sid = _safe_session(session)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    turns = DIALOGS.turns(sid)
    out = []
    for t in turns:
        meta = t.get("meta") if isinstance(t.get("meta"), dict) else {}
        tok = meta.get("tok")
        ptok = meta.get("ptok")
        out.append({"role": t["role"], "text": t["text"],
                    "html": to_safe_html(t["text"]) if t["role"] == "assistant" else "",
                    "secs": meta.get("secs"),
                    "tok": int(tok) if isinstance(tok, (int, float)) else None,
                    "ptok": int(ptok) if isinstance(ptok, (int, float)) else None,
                    "src_label": progress.source_label(str(meta.get("src", "")))
                    if meta.get("secs") is not None else ""})
    return jsonify({"session": sid, "turns": out})


# ---------- Круг Д: стремление ----------

def _drive_alive() -> bool:
    """Сердце службы стремления свежее (3 такта)?"""
    try:
        rec = json.loads(Path(config.DRIVE_STATUS_FILE).read_text(encoding="utf-8"))
        ts = dt.datetime.fromisoformat(rec["ts"])
        return (dt.datetime.now() - ts).total_seconds() <= 180
    except (OSError, ValueError, KeyError):
        return False


@app.get("/api/drive")
def api_drive():
    """Карточка стремления: план дня, вопросы, дневник, уроки."""
    from core.autonomy import DayPlanner
    from core.diary import Diary
    from evolution.journal import digest as journal_digest

    plan = DayPlanner().load_plan() or {}
    tasks = [t for t in plan.get("tasks", []) if isinstance(t, dict)]
    open_n = sum(1 for t in tasks if t.get("status") != "done")
    try:
        lessons = sum(journal_digest(7).values())
    except Exception:
        lessons = 0
    return jsonify({
        "drive_alive": _drive_alive(),
        "plan": {"date": plan.get("date", ""), "total": len(tasks),
                 "open": open_n,
                 "titles": [t.get("title", "") for t in tasks
                            if t.get("status") != "done"][:8]},
        "questions": QuestionBank().open_items(),
        "last_diary": Diary().last_diary(),
        "lessons_7d": lessons,
    })


@app.post("/api/questions/answer")
def api_questions_answer():
    """Илья отвечает на вопрос Марфы — ответ сразу в память."""
    data = request.get_json(force=True, silent=True) or {}
    qid = str(data.get("id") or "").strip()
    text = str(data.get("text") or "").strip()
    if not qid or not text:
        return jsonify({"error": "нужны id и text"}), 400
    item = QuestionBank().answer(qid, text)
    if item is None:
        return jsonify({"error": "вопрос не найден или уже закрыт"}), 404
    try:
        from core.memory import Memory
        Memory().remember("Илья ответил на «%s»: %s" % (item["text"], text),
                          tags=["ответ"], importance=3.5)
    except Exception:
        pass                      # память спотыкается — ответ всё равно принят
    return jsonify({"ok": True, "question": item["text"], "answer": text})


@app.get("/chat")
def chat_page():
    chat_path = Path(__file__).parent / "templates" / "chat.html"
    return chat_path.read_text(encoding="utf-8")


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=PORT_WEB, debug=False)
