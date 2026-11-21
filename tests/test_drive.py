# -*- coding: utf-8 -*-
"""Тесты службы стремления (Круг Д, Д-5): тик, сердце, пятый слуга, панель.

Служба: один тик гоняет расписание (на реальных работах в tmp-доме),
щупает мозг и пишет сердце в data/drive_status.json. Старт дома
поднимает её пятой. Панель: /api/drive и приём ответов на вопросы.
"""
import datetime as dt
import json

import pytest

from core import config, drive


@pytest.fixture()
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("MARFA_HOME", str(tmp_path))
    monkeypatch.setattr(config, "HOME_DIR", tmp_path)
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(config, "QUEUE_FILE", tmp_path / "data" / "queue.json")
    monkeypatch.setattr(config, "QUESTIONS_FILE", tmp_path / "data" / "questions.json")
    monkeypatch.setattr(config, "SCHEDULE_STATE_FILE", tmp_path / "data" / "schedule_state.json")
    monkeypatch.setattr(config, "LIBRARIAN_STATE_FILE", tmp_path / "data" / "librarian_state.json")
    monkeypatch.setattr(config, "DRIVE_STATUS_FILE", tmp_path / "data" / "drive_status.json")
    monkeypatch.setattr(config, "DOCTOR_STATE_FILE", tmp_path / "data" / "doctor_state.json")
    monkeypatch.setattr(config, "EARS_STATUS_FILE", tmp_path / "data" / "ears_status.json")
    monkeypatch.setattr(config, "EARS_LOG_FILE", tmp_path / "logs" / "ears_log.jsonl")
    monkeypatch.setattr(config, "EVOLUTION_DIR", tmp_path / "data" / "evolution")
    monkeypatch.setattr(config, "BRAIN_URL", "http://127.0.0.1:1")   # мозг мёртв — честно
    config.ensure_dirs()
    (tmp_path / "docs").mkdir(exist_ok=True)
    yield tmp_path


# ---------- тик службы ----------

def test_one_tick_runs_schedule_and_writes_heartbeat(home):
    (home / "docs" / "chapter.md").write_text(
        "Глава про стремление. Марфа хочет знать больше.", encoding="utf-8")
    status = drive.one_tick(now=dt.datetime(2026, 11, 21, 12, 0))

    assert status["state"] == "ok"
    assert status["brain_ok"] is False                    # мозга нет в тесте
    assert status["brain_down_since"]                     # молчание зафиксировано
    # расписание отработало: план построен, полка прочитана
    assert (home / "data" / "plan_2026-11-21.json").exists()
    assert json.loads((home / "data" / "librarian_state.json").read_text(
        encoding="utf-8"))["files"]
    # сердце на диске
    on_disk = json.loads(config.DRIVE_STATUS_FILE.read_text(encoding="utf-8"))
    assert on_disk["ts"] == status["ts"]
    assert any(r["id"] == "librarian" and r["ok"] for r in on_disk["last_results"])


def test_one_tick_second_time_no_rerun(home):
    drive.one_tick(now=dt.datetime(2026, 11, 21, 12, 0))
    status2 = drive.one_tick(now=dt.datetime(2026, 11, 21, 12, 1))
    # минута прошла: очередь снова, остальное — по расписанию
    ids = [r["id"] for r in status2["last_results"]]
    assert "queue" in ids and "plan" not in ids


def test_brain_down_since_persisted(home):
    drive.one_tick(now=dt.datetime(2026, 11, 21, 12, 0))
    first = json.loads(config.DRIVE_STATUS_FILE.read_text(encoding="utf-8"))
    drive.one_tick(now=dt.datetime(2026, 11, 21, 12, 5))
    second = json.loads(config.DRIVE_STATUS_FILE.read_text(encoding="utf-8"))
    assert first["brain_down_since"] == second["brain_down_since"]   # отсчёт не сбрасывается


def test_serve_max_ticks(home, capsys):
    drive.serve(interval=0.01, max_ticks=2)
    out = capsys.readouterr().out
    assert "служба стремления" in out
    assert "тик 2" in out


def test_cli_tick(home, capsys):
    assert drive.main(["--tick"]) == 0
    assert "brain_ok" in capsys.readouterr().out


# ---------- пятый слуга старта дома ----------

def test_start_marfa_spawns_drive(monkeypatch, tmp_path):
    import start_marfa as sm

    p = tmp_path / "start_marfa.json"
    p.write_text(json.dumps({
        "brain_cmd": "run brain", "eyes_cmd": "run eyes",
        "panel_cmd": "run panel", "ears_cmd": "run ears",
        "drive_cmd": "run drive"}, ensure_ascii=False), encoding="utf-8")

    spawned = []
    monkeypatch.setattr(sm, "_alive", lambda port, path: True)   # HTTP-слуги живы
    monkeypatch.setattr(sm, "_ears_alive", lambda: True)
    monkeypatch.setattr(sm, "_drive_alive", lambda: False)       # стремление — нет
    monkeypatch.setattr(sm, "_spawn", lambda cmd: spawned.append(cmd))
    rc = sm.main(["--config", str(p)])
    assert rc == 0
    assert "run drive" in spawned


def test_start_marfa_drive_skipped_when_alive(monkeypatch, tmp_path):
    import start_marfa as sm

    p = tmp_path / "start_marfa.json"
    p.write_text(json.dumps({
        "brain_cmd": "b", "eyes_cmd": "e", "panel_cmd": "p",
        "ears_cmd": "er"}, ensure_ascii=False), encoding="utf-8")
    spawned = []
    monkeypatch.setattr(sm, "_alive", lambda port, path: True)
    monkeypatch.setattr(sm, "_ears_alive", lambda: True)
    monkeypatch.setattr(sm, "_drive_alive", lambda: True)
    monkeypatch.setattr(sm, "_spawn", lambda cmd: spawned.append(cmd))
    sm.main(["--config", str(p)])
    assert spawned == []                       # все живы — никого не трогаем


def test_drive_alive_by_heartbeat(monkeypatch, tmp_path):
    import start_marfa as sm
    f = tmp_path / "drive_status.json"
    monkeypatch.setattr(sm, "DRIVE_STATUS_FILE", f)
    assert sm._drive_alive() is False
    f.write_text(json.dumps({"ts": dt.datetime.now().isoformat(timespec="seconds")}),
                 encoding="utf-8")
    assert sm._drive_alive() is True
    old = (dt.datetime.now() - dt.timedelta(seconds=sm.DRIVE_FRESH_SECS + 60))
    f.write_text(json.dumps({"ts": old.isoformat(timespec="seconds")}),
                 encoding="utf-8")
    assert sm._drive_alive() is False
    f.write_text("мусор", encoding="utf-8")
    assert sm._drive_alive() is False


# ---------- панель ----------

def test_web_drive_and_question_answer(home, monkeypatch):
    import web.app as webapp
    from core.questions import QuestionBank

    QuestionBank().add("Когда микрофон?", source="уши")
    client = webapp.app.test_client()

    r = client.get("/api/drive")
    assert r.status_code == 200
    data = r.get_json()
    assert data["drive_alive"] in (True, False)
    assert any("микрофон" in q["text"] for q in data["questions"])

    r2 = client.post("/api/questions/answer",
                     json={"id": "q1", "text": "на следующей неделе"})
    assert r2.status_code == 200
    assert r2.get_json()["ok"] is True
    assert QuestionBank().open_items() == []

    # второй раз тот же вопрос — 404
    r3 = client.post("/api/questions/answer",
                     json={"id": "q1", "text": "ещё раз"})
    assert r3.status_code == 404

    # пустой ответ — 400
    r4 = client.post("/api/questions/answer", json={"id": "q2"})
    assert r4.status_code == 400
