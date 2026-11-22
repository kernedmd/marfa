# -*- coding: utf-8 -*-
"""Тесты Ф97 «монитор»: пороги 85/92, журнал переходов, панель web 5001."""
import json
import pytest
from pathlib import Path
from unittest.mock import patch

from core import config
from core.dialog import DialogStore
from sensors.monitor import RAMMonitor, classify
from web.app import app, PORT_WEB


@pytest.fixture()
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("MARFA_HOME", str(tmp_path))
    monkeypatch.setattr(config, "HOME_DIR", tmp_path)
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(config, "LOGS_DIR", tmp_path / "logs")
    monkeypatch.setattr(config, "MONITOR_STATUS_FILE", tmp_path / "data" / "monitor_status.json")
    monkeypatch.setattr(config, "MONITOR_LOG_FILE", tmp_path / "logs" / "monitor_log.jsonl")
    monkeypatch.setattr(config, "GUARD_LOG_FILE", tmp_path / "logs" / "guard_log.jsonl")
    monkeypatch.setattr(config, "EARS_STATUS_FILE", tmp_path / "data" / "ears_status.json")
    config.ensure_dirs()
    yield tmp_path


def test_classify_thresholds():
    assert classify(50.0) == "OK"
    assert classify(84.9) == "OK"
    assert classify(85.0) == "WARN"
    assert classify(91.9) == "WARN"
    assert classify(92.0) == "CRIT"
    assert classify(97.0) == "CRIT"


def test_sample_synthetic(home):
    snap = RAMMonitor(snapshot=lambda: (44.0, 64.0))
    s = snap.observe()
    assert s["pct"] == 68.8 and s["level"] == "OK"
    assert s["total_gb"] == 64.0 and s["budget_plan_gb"] == 44


def test_status_file_written(home):
    snap = RAMMonitor(snapshot=lambda: (58.0, 64.0))
    snap.observe()
    data = json.loads((config.MONITOR_STATUS_FILE).read_text(encoding="utf-8"))
    assert data["level"] == "WARN" and data["pct"] == pytest.approx(90.6)


def test_level_transitions_logged(home):
    values = [(44.0, 64.0), (58.0, 64.0), (60.0, 64.0), (44.0, 64.0)]
    it = iter(values)
    snap = RAMMonitor(snapshot=lambda: next(it))
    for _ in values:
        snap.observe()
    events = snap.history()
    levels = [e["level"] for e in events]
    assert levels == ["WARN", "CRIT", "OK"]


def test_history_empty_without_events(home):
    snap = RAMMonitor(snapshot=lambda: (10.0, 64.0))
    snap.observe()
    assert snap.history() == []


@pytest.fixture()
def client(home, monkeypatch):
    monkeypatch.setattr("web.app.PORT_WEB", config.PORT_WEB)
    app.config["TESTING"] = True
    return app.test_client()


def test_health_endpoint(client):
    r = client.get("/health")
    assert r.status_code == 200
    data = r.get_json()
    assert data["status"] == "ok" and data["port"] == 5001


def test_panel_renders(client, home):
    r = client.get("/")
    assert r.status_code == 200
    html = r.data.decode("utf-8")
    assert "Марфа — панель дома" in html
    assert "Память RAM (Ф97)" in html
    assert "5000 не трогаем" in html
    assert "44 из 64" in html
    assert "Уши (сторож имени «Марфа»)" in html   # карточка ушей на панели


def test_api_status(client, home):
    r = client.get("/api/status")
    assert r.status_code == 200
    data = r.get_json()
    assert data["ram"]["level"] in ("OK", "WARN", "CRIT")
    assert "brain" in data and data["brain"]["healthy"] in (True, False)
    assert data["guard_audit_verdict"] in ("OK", "TAMPERED")
    assert data["ears"]["state"] == "down"          # службы ещё нет — честно


def test_api_status_reports_ears_states(client, home):
    """Карточка ушей читает статус-файл службы: панель не врёт."""
    from web.app import _ears_state
    # служба ждёт микрофон (Z440 без микрофона)
    config.EARS_STATUS_FILE.write_text(
        json.dumps({"ts": "2026-11-20T12:00:00", "sensor": "ears",
                    "state": "no_mic", "error": "Error querying device -1"}),
        encoding="utf-8")
    r = client.get("/api/status")
    assert r.get_json()["ears"]["state"] == "no_mic"
    assert "device -1" in r.get_json()["ears"]["error"]   # ПРИЧИНА доезжает
    # ухо живо и слышало зов
    config.EARS_STATUS_FILE.write_text(
        json.dumps({"ts": "2026-11-20T12:01:00", "sensor": "ears",
                    "state": "ok", "device": "HD WebCam Mic",
                    "last_wake": "11:59 | марфа включи свет"}),
        encoding="utf-8")
    data = client.get("/api/status").get_json()["ears"]
    assert data["state"] == "ok"
    assert "марфа включи свет" in data["last_wake"]
    assert data["device"] == "HD WebCam Mic"   # v2: каким устройством слушают
    # мусор в файле — панель не падает, честный down
    config.EARS_STATUS_FILE.write_text("не json", encoding="utf-8")
    assert _ears_state()["state"] == "down"


def test_brain_health_reported_down(client, home):
    """Мозг не поднят — панель честно говорит «не отвечает», не врёт."""
    with patch("core.brain.BrainClient.health", return_value=False):
        r = client.get("/api/status")
        assert r.get_json()["brain"]["healthy"] is False


def test_port_web_is_not_forbidden():
    assert PORT_WEB == 5001
    assert PORT_WEB != config.PORT_FORBIDDEN


# ---------- №13: живой статус-виджет ----------

def test_api_health_all_three_services(client, home):
    """/api/health отдаёт все три службы одной точкой — как требует №13."""
    with patch("core.brain.BrainClient.health", return_value=True), \
         patch("core.eyes.health_cached", return_value=False):
        data = client.get("/api/health").get_json()
    assert data["panel"] is True            # панель отвечает — она жива
    assert data["brain"] is True            # мозг поднят
    assert data["eyes"] is False            # глаза честно молчат (не врёт)


def test_api_health_brain_down(client, home):
    with patch("core.brain.BrainClient.health", return_value=False), \
         patch("core.eyes.health_cached", return_value=True):
        data = client.get("/api/health").get_json()
    assert data["brain"] is False and data["eyes"] is True


def test_chat_page_has_widget_dots(client, home):
    """Шапка чата: три точки (панель/мозг/глаза) и опрос раз в 30 с."""
    html = client.get("/chat").data.decode("utf-8")
    for w in ("w-panel", "w-brain", "w-eyes"):
        assert w in html
    assert "setInterval(refreshWidgets, 30000)" in html


# ---------- №16: день/ночь ----------

def test_day_night_toggle_on_both_pages(client, home):
    """Переключатель на обеих страницах, выбор в localStorage."""
    chat = client.get("/chat").data.decode("utf-8")
    assert "marfa-theme" in chat and "toggleTheme" in chat and "body.light" in chat
    panel = client.get("/").data.decode("utf-8")
    assert "marfa-theme" in panel and "toggleTheme" in panel and "body.light" in panel


# ---------- №12: Markdown в ответах ----------

def test_api_chat_returns_safe_html(client, home, monkeypatch):
    """/api/chat прикладывает готовый HTML: жирный — <b>, тег мозга — мёртв."""
    import web.app as webapp
    from core.agent import Reply

    class FakeAgent:
        def handle(self, text, history=None):
            return Reply("итог: **42** и <script>хрень</script>")

    monkeypatch.setattr(webapp, "Agent", lambda: FakeAgent())
    monkeypatch.setattr(webapp, "DIALOGS", DialogStore(home / "data" / "dialog"))
    data = client.post("/api/chat", json={"text": "вопрос", "session": "md1"}).get_json()
    assert data["reply"].startswith("итог")
    assert "<b>42</b>" in data["html"]
    assert "<script>" not in data["html"]
    assert "&lt;script&gt;" in data["html"]


def test_api_dialog_html_only_for_marfa(client, home, monkeypatch):
    """История: HTML — только ответам Марфы, ходы Ильи — чистый текст."""
    import web.app as webapp
    monkeypatch.setattr(webapp, "DIALOGS", DialogStore(home / "data" / "dialog"))
    webapp.DIALOGS.append("md2", "user", "моя **реплика**")
    webapp.DIALOGS.append("md2", "assistant", "ответ со **списком**:\n- пункт")
    turns = client.get("/api/dialog/md2").get_json()["turns"]
    assert turns[0]["html"] == ""                       # Илья — текстом
    assert "<b>списком</b>" in turns[1]["html"]
    assert "<li>пункт</li>" in turns[1]["html"]


def test_stale_chat_copy_removed():
    """Раздел 8 протокола: у страницы чата одно имя, одно место."""
    assert not (Path(__file__).resolve().parents[1] / "web" / "chat.html").exists()


# ---------- ЭФИР: время и «что происходит» в самом чате ----------

def test_api_progress_idle_busy_last(client, home):
    """Живой ход и штамп последнего — одной точкой, для чата и панели."""
    from core import progress
    progress.reset()
    data = client.get("/api/progress").get_json()
    assert data["busy"] is False and data["stage"] == ""
    progress.begin("walk1")
    progress.stage("глаза читают экран…")
    data = client.get("/api/progress?session=walk1").get_json()
    assert data["busy"] is True
    assert data["stage"] == "глаза читают экран…"
    assert data["mine"] is True
    assert data["elapsed"] >= 0.0
    progress.finish(secs=3.2, source="brain")
    data = client.get("/api/progress").get_json()
    assert data["busy"] is False
    assert data["last"]["secs"] == 3.2
    assert data["last"]["source"] == "мозг"
    progress.reset()


def test_api_progress_bad_session_still_answers(client, home):
    """Плохое имя сессии в query — эфир отвечает без фильтра, не падает."""
    r = client.get("/api/progress?session=" + "точки.нет с пробелом")
    assert r.status_code == 200
    assert r.get_json()["busy"] is False


def test_api_chat_returns_secs_and_writes_stamp(client, home, monkeypatch):
    """Ответ со штампом «N с · кто отвечал»; штамп — и в память диалога."""
    import web.app as webapp
    from core.agent import Reply

    class FakeAgent:
        def handle(self, text, history=None):
            return Reply("готово", source="brain")

    monkeypatch.setattr(webapp, "Agent", lambda: FakeAgent())
    monkeypatch.setattr(webapp, "DIALOGS", DialogStore(home / "data" / "dialog"))
    data = client.post("/api/chat",
                       json={"text": "вопрос", "session": "air1"}).get_json()
    assert isinstance(data["secs"], (int, float))
    assert data["secs"] >= 0.0
    assert data["source"] == "brain"
    assert data["source_label"] == "мозг"
    turns = webapp.DIALOGS.turns("air1")
    assert turns[1]["meta"]["secs"] == data["secs"]   # F5 не сотрёт время
    assert turns[1]["meta"]["src"] == "brain"


def test_api_chat_error_releases_air(client, home, monkeypatch):
    """Панель упала посреди хода — эфир освобождён, «вечно занята» не бывает."""
    import web.app as webapp

    class BoomAgent:
        def handle(self, text, history=None):
            raise RuntimeError("панель сломалась")

    monkeypatch.setattr(webapp, "Agent", lambda: BoomAgent())
    monkeypatch.setattr(webapp, "DIALOGS", DialogStore(home / "data" / "dialog"))
    from core import progress
    progress.reset()
    r = client.post("/api/chat", json={"text": "вопрос", "session": "air9"})
    assert r.status_code == 500
    assert progress.snapshot()["busy"] is False
    progress.reset()


def test_api_dialog_returns_stamps(client, home, monkeypatch):
    """История несёт штампы: после F5 время ответов остаётся в чате."""
    import web.app as webapp
    monkeypatch.setattr(webapp, "DIALOGS", DialogStore(home / "data" / "dialog"))
    webapp.DIALOGS.append("air2", "user", "вопрос")
    webapp.DIALOGS.append("air2", "assistant", "ответ",
                          meta={"secs": 7.7, "src": "brain"})
    webapp.DIALOGS.append("air2", "user", "ещё вопрос")
    webapp.DIALOGS.append("air2", "assistant", "старый ответ без мета")
    turns = client.get("/api/dialog/air2").get_json()["turns"]
    assert turns[1]["secs"] == 7.7
    assert turns[1]["src_label"] == "мозг"
    assert turns[3]["secs"] is None               # до эфира — без штампа, не падает
    assert turns[0]["secs"] is None               # ходы Ильи — без штампов


def test_chat_page_shows_live_progress(client, home):
    """Чат: секундомер думания + живая стадия + штамп времени."""
    html = client.get("/chat").data.decode("utf-8")
    assert "/api/progress" in html
    assert "think-stage" in html and "think-secs" in html   # индикатор думания
    assert "addStamp" in html                               # штамп под ответом
    assert "thinkingBox" in html


def test_panel_has_now_card(client, home):
    """Панель: карточка «Сейчас делает» — чем занята Марфа без консоли."""
    html = client.get("/").data.decode("utf-8")
    assert 'id="now"' in html
    assert "Сейчас делает" in html
    assert "/api/progress" in html