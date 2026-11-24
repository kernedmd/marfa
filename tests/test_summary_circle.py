# -*- coding: utf-8 -*-
"""КРУГ 16 «ИТОГ ДНЯ» (день-13) — Ф90–Ф93.

День организма закрывался файлом (дневник 21:00 — про Марфу, быт
dayroll — про Создателя), но ТЕЛО в сводке не было, память дня не
читалась списком, недельный доклад архитектора видел дом (тесты,
коммиты, диск, канон) и не видел организм (ходы, медиана, пустые
ответы), а «завтра» вообще не имело команды. Круг закрывает день
со всех сторон — и каждая цифра из первых рук."""
import datetime as dt
import json
from pathlib import Path

import pytest

from core import config, daypulse, dayplan
from core.agent import Agent
from core.brain import BrainClient
from core.memory import Memory
from safety import guard
from tests.fake_llama_server import start_fake_brain


@pytest.fixture()
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("MARFA_HOME", str(tmp_path))
    monkeypatch.setattr(config, "HOME_DIR", tmp_path)
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(config, "LOGS_DIR", tmp_path / "logs")
    monkeypatch.setattr(config, "BRAIN_LOG_FILE", tmp_path / "logs" / "brain_log.jsonl")
    monkeypatch.setattr(config, "GUARD_LOG_FILE", tmp_path / "logs" / "guard_log.jsonl")
    monkeypatch.setattr(config, "CANARIES_FILE", tmp_path / "data" / "canaries.json")
    monkeypatch.setattr(config, "DOCTRINE_FILE", tmp_path / "data" / "creator_doctrine.json")
    monkeypatch.setattr(config, "QUEUE_FILE", tmp_path / "data" / "queue.json")
    monkeypatch.setattr(config, "GENOME_FILE", tmp_path / "data" / "context_genome.json")
    monkeypatch.setattr(guard, "_LOG", None)
    config.ensure_dirs()
    yield tmp_path


@pytest.fixture()
def srv(monkeypatch, home):
    server = start_fake_brain()
    monkeypatch.setattr(config, "BRAIN_URL", server.base_url)
    yield server
    server.shutdown()


@pytest.fixture()
def agent(srv):
    mem = Memory(data_dir=Path(config.DATA_DIR))
    return Agent(brain=BrainClient(brain_url=srv.base_url), memory=mem,
                 doctrine="Тестовая доктрина итога")


def _line(ts: str, secs=10.0, ptok=100, ctok=20, note="") -> str:
    rec = {"ts": ts, "kind": "ask", "secs": secs,
           "prompt_tokens": ptok, "completion_tokens": ctok,
           "think_chars": 0, "ok": True, "note": note,
           "answer": None if note else "ответ"}
    return json.dumps(rec, ensure_ascii=False)


# ---------- Ф90 тело в сводке дня ----------

def test_dayroll_carries_body_section(home):
    """«как прошел день» отвечает и бытом, и телом: пульс в сводке."""
    from core import dayroll
    day = dt.date.today().strftime("%Y-%m-%d")
    config.BRAIN_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    config.BRAIN_LOG_FILE.write_text(
        _line(day + " 10:00:00", secs=20.0) + "\n" +
        _line(day + " 11:00:00", secs=30.0, note="пустой ответ") + "\n",
        encoding="utf-8")
    out = dayroll.render()
    assert "тело:" in out
    assert "2 хода мозга" in out
    assert "пустых ответов 1" in out


def test_dayroll_body_silent_when_brain_quiet(home):
    """Мозг молчал — тела в сводке нет: нулей-обмана не рисуем."""
    from core import dayroll
    out = dayroll.render()
    assert "тело:" not in out


def test_dayroll_body_armored(home, monkeypatch):
    """Упавший пульс не роняет сводку (закон №10 р3)."""
    from core import dayroll

    def _boom(now=None):
        raise RuntimeError("пульс упал")

    monkeypatch.setattr(daypulse, "collect", _boom)
    out = dayroll.render()          # не бросился — сводка жива
    assert "тело:" not in out


# ---------- Ф91 что запомнила сегодня ----------

def test_memory_today_lists_only_fresh(agent, home):
    agent.handle("запомни: вечерний чай с мёдом")
    agent.handle("запомни: ключи от шкафа в ящике")
    r = agent.handle("что запомнила сегодня")
    assert r.tool_used == "memory_today" and r.source == "python"
    assert "вечерний чай с мёдом" in r.text
    assert "ключи от шкафа" in r.text


def test_memory_today_old_records_stay_out(agent, home, monkeypatch):
    """Вчерашняя память — не сегодняшний день: список только новый."""
    from core.memory import Memory, _norm
    mem = Memory(data_dir=Path(config.DATA_DIR))
    old_ts = (dt.datetime.now() - dt.timedelta(days=2)).timestamp()
    mem.remember("старый факт двухдневной давности")
    # состариваем запись честно: правим created_at через бэкенд
    backend_rec = mem._backend().find_by_norm(_norm("старый факт "
                                                    "двухдневной давности"))
    assert backend_rec is not None
    mem._backend().update(backend_rec["id"], {"created_at": old_ts})
    agent.handle("запомни: свежий факт сегодняшнего дня")
    r = agent.handle("что запомнила сегодня")
    assert "свежий факт" in r.text
    assert "двухдневной давности" not in r.text


def test_memory_today_honest_empty(agent):
    r = agent.handle("что запомнила сегодня")
    assert "ничего нового не легло" in r.text


# ---------- Ф92 тело в докладе архитектора ----------

def test_weekly_report_carries_pulse(home, monkeypatch):
    """Доклад архитектора знает организм: раздел ПУЛЬС НЕДЕЛИ на месте."""
    import architect_oncall
    week_ago = dt.date.today() - dt.timedelta(days=3)
    lines = [_line(week_ago.strftime("%Y-%m-%d") + " 10:00:00", secs=25.0)]
    config.BRAIN_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    config.BRAIN_LOG_FILE.write_text("\n".join(lines) + "\n",
                                     encoding="utf-8")
    report = architect_oncall.weekly_report(save=False)
    assert "ПУЛЬС НЕДЕЛИ" in report
    assert "1 ход" in report


def test_weekly_report_pulse_armored(home, monkeypatch):
    """Упавший пульс — честная строка в докладе, отчёт жив (№10 р3)."""
    import architect_oncall

    def _boom(now=None):
        raise RuntimeError("журнал недоступен")

    monkeypatch.setattr(daypulse, "week_render", _boom)
    report = architect_oncall.weekly_report(save=False)
    assert "ПУЛЬС НЕДЕЛИ" in report
    assert "не ответил" in report


def test_week_render_trend_against_prev_week(home):
    """Неделя против прошлой: медленный тренд назван честно."""
    today = dt.date.today()
    lines = []
    for i in range(7):          # прошлая неделя: быстрые ходы
        d = (today - dt.timedelta(days=7 + i)).strftime("%Y-%m-%d")
        lines.append(_line(d + " 12:00:00", secs=10.0))
    for i in range(4):          # эта неделя: тяжёлые ходы
        d = (today - dt.timedelta(days=i)).strftime("%Y-%m-%d")
        lines.append(_line(d + " 12:00:00", secs=50.0))
    config.BRAIN_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    config.BRAIN_LOG_FILE.write_text("\n".join(lines) + "\n",
                                     encoding="utf-8")
    out = daypulse.week_render()
    assert "ТЯЖЕЛЕЕ" in out


# ---------- Ф93 что завтра ----------

def test_what_tomorrow_lists_open_tasks(agent, home):
    """Незакрытое сегодня честно переедит в завтра — списком."""
    from core.autonomy import DayPlanner
    planner = DayPlanner(data_dir=Path(config.DATA_DIR))
    plan = {"day": dt.date.today().isoformat(), "tasks": [
        {"id": "t1", "title": "проверить микрофон", "status": "todo"},
        {"id": "t2", "title": "прочитать главу", "status": "done"},
    ]}
    planner.plan_path(dt.date.today()).write_text(
        json.dumps(plan, ensure_ascii=False), encoding="utf-8")
    r = agent.handle("что завтра")
    assert r.tool_used == "dayplan" and r.source == "python"
    assert "проверить микрофон" in r.text     # открытое — в завтра
    assert "прочитать главу" not in r.text    # сделанное не переезжает


def test_what_tomorrow_counts_queue(agent, home):
    from core.autonomy import add_task
    add_task("собрать бандл недели")
    r = agent.handle("что завтра")
    assert "из очереди войдёт" in r.text
    assert "1 задач" in r.text


def test_what_tomorrow_honest_clean(agent):
    r = agent.handle("план на завтра")
    assert "чистым листом" in r.text
    assert "08:00" in r.text                   # когда построю — честно


def test_what_tomorrow_variants(agent):
    for cmd in ("что завтра", "что завтра по плану", "задачи на завтра"):
        r = agent.handle(cmd)
        assert r.tool_used == "dayplan"


# ---------- имена в каталоге ----------

def test_manifest_slim_carries_new_names():
    from core.identity import manifest_slim
    slim = manifest_slim()
    assert "что запомнила сегодня" in slim
    assert "что завтра" in slim
