# -*- coding: utf-8 -*-
"""Тесты Ф97 «монитор»: пороги 85/92, журнал переходов, панель web 5001."""
import json
import pytest
from unittest.mock import patch

from core import config
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
    # ухо живо и слышало зов
    config.EARS_STATUS_FILE.write_text(
        json.dumps({"ts": "2026-11-20T12:01:00", "sensor": "ears",
                    "state": "ok",
                    "last_wake": "11:59 | марфа включи свет"}),
        encoding="utf-8")
    data = client.get("/api/status").get_json()["ears"]
    assert data["state"] == "ok"
    assert "марфа включи свет" in data["last_wake"]
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