# -*- coding: utf-8 -*-
"""Тесты Ф75 «расписание» + Эволюционер v0 «журнал уроков» (Круг Д).

Расписание: daily/weekly/interval, идемпотентность (один день — один
запуск), падение работы не роняет тик, состояние переживает рестарт.
Журнал: запись/чтение/дайджест, проводы агента в уроки.
"""
import datetime as dt
import json

import pytest

from core import config
from core.schedule import Scheduler, job
from evolution import journal


@pytest.fixture()
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("MARFA_HOME", str(tmp_path))
    monkeypatch.setattr(config, "HOME_DIR", tmp_path)
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(config, "SCHEDULE_STATE_FILE", tmp_path / "data" / "schedule_state.json")
    monkeypatch.setattr(config, "EVOLUTION_DIR", tmp_path / "data" / "evolution")
    monkeypatch.setattr(config, "EARS_LOG_FILE", tmp_path / "logs" / "ears_log.jsonl")
    config.ensure_dirs()
    yield tmp_path


@pytest.fixture()
def sched(home):
    return Scheduler()


# ---------- расписание ----------

def test_daily_job_runs_once_per_day(sched):
    ran = []
    j = job("t", "daily", at="08:00", what="тест", run=lambda: ran.append(1))
    at8 = dt.datetime(2026, 11, 21, 8, 0)
    assert sched.due(at8, [j]) == [j]              # пора
    res = sched.tick(at8, [j])
    assert res[0]["ok"] and len(ran) == 1
    assert sched.due(dt.datetime(2026, 11, 21, 9, 30), [j]) == []   # второй раз — нет
    assert sched.due(dt.datetime(2026, 11, 22, 8, 1), [j]) == [j]   # завтра — снова


def test_daily_job_not_due_before_slot(sched):
    j = job("t", "daily", at="08:00", what="тест", run=lambda: None)
    assert sched.due(dt.datetime(2026, 11, 21, 7, 59), [j]) == []
    # но вчерашний незапущенный — догоняет сегодня
    assert sched.due(dt.datetime(2026, 11, 21, 12, 0), [j]) == [j]


def test_interval_job(sched):
    calls = []
    j = job("t", "interval", every=60, what="тест", run=lambda: calls.append(1))
    t0 = dt.datetime(2026, 11, 21, 10, 0, 0)
    sched.tick(t0, [j])
    assert len(calls) == 1
    assert sched.due(t0 + dt.timedelta(seconds=30), [j]) == []
    assert sched.due(t0 + dt.timedelta(seconds=61), [j]) == [j]


def test_weekly_job_only_on_day(sched):
    j = job("t", "weekly", weekday="sun", at="23:00", what="тест",
            run=lambda: None)
    # 21.11.2026 — суббота. Состояния нет: ближайшее прошлое вс 23:00 (15.11)
    # не отработано — честный догон, работа пора.
    sat = dt.datetime(2026, 11, 21, 12, 0)
    assert sched.due(sat, [j]) == [j]
    sched.tick(sat, [j])
    # новое вхождение — завтра вс 22.11 23:00: до него тишина
    assert sched.due(dt.datetime(2026, 11, 22, 22, 59), [j]) == []
    assert sched.due(dt.datetime(2026, 11, 22, 23, 1), [j]) == [j]
    sched.tick(dt.datetime(2026, 11, 22, 23, 1), [j])
    # всю следующую неделю — не пора
    assert sched.due(dt.datetime(2026, 11, 27, 23, 1), [j]) == []
    assert sched.due(dt.datetime(2026, 11, 29, 23, 1), [j]) == [j]  # следующее вс


def test_failing_job_does_not_break_tick(sched):
    def boom():
        raise RuntimeError("хлопок")

    ok_ran = []
    jobs = [job("bad", "interval", every=60, what="падает", run=boom),
            job("good", "interval", every=60, what="живёт",
                run=lambda: ok_ran.append(1))]
    res = sched.tick(dt.datetime(2026, 11, 21, 10, 0), jobs)
    by_id = {r["id"]: r for r in res}
    assert by_id["bad"]["ok"] is False and "хлопок" in by_id["bad"]["error"]
    assert by_id["good"]["ok"] is True and len(ok_ran) == 1


def test_state_survives_restart(sched, home):
    calls = []
    j = job("t", "daily", at="08:00", what="тест", run=lambda: calls.append(1))
    sched.tick(dt.datetime(2026, 11, 21, 8, 0), [j])
    # новый объект (рестарт службы) — читает то же состояние
    sched2 = Scheduler()
    assert sched2.due(dt.datetime(2026, 11, 21, 10, 0), [j]) == []
    assert len(calls) == 1


def test_broken_state_file_is_fresh_start(sched, home):
    config.SCHEDULE_STATE_FILE.write_text("{битый", encoding="utf-8")
    j = job("t", "interval", every=60, what="тест", run=lambda: None)
    assert sched.due(dt.datetime(2026, 11, 21, 10, 0), [j]) == [j]


def test_job_with_now_gets_tick_time(sched, home):
    """Урок 22.11: работа с параметром now живёт во времени ТИКА, а не
    реальных часов. План, построенный по сегодняшним часам в момент
    фиктивного «вчера», — работа из другого дня; тест, зелёный только
    в свою дату, — не тест (та же болезнь, что и с портами 21.11)."""
    seen = []

    def careful(now):
        seen.append(now)

    j = job("t-now", "daily", at="08:00", what="видит время тика",
            run=careful)
    tick_at = dt.datetime(2026, 11, 21, 9, 0)
    sched.tick(tick_at, [j])
    assert seen == [tick_at]

    plain = []
    j2 = job("t-plain", "interval", every=60, what="без now — как раньше",
             run=lambda: plain.append(1))
    sched.tick(tick_at, [j2])
    assert plain == [1]


# ---------- журнал уроков ----------

def test_lesson_written_and_read(home):
    assert journal.log_lesson("мозг-недоступен", "таймаут 120 с") is True
    recs = journal.recent()
    assert recs and recs[-1]["kind"] == "мозг-недоступен"
    assert "таймаут" in recs[-1]["text"]
    assert recs[-1]["ts"].startswith("20")


def test_unknown_kind_becomes_other(home):
    journal.log_lesson("пришельцы", "нечто")
    assert journal.recent()[-1]["kind"] == "прочее"


def test_digest_counts_by_kind(home):
    journal.log_lesson("страж-отказ", "путь вне дома")
    journal.log_lesson("страж-отказ", "снова путь")
    journal.log_lesson("мозг-недоступен", "спит")
    d = journal.digest(days=7)
    assert d.get("страж-отказ") == 2 and d.get("мозг-недоступен") == 1


def test_agent_brain_failure_is_a_lesson(home):
    """Мозг упал — урок записан, дом ответил честно, не упал."""
    from core.agent import Agent

    class DeadBrain:
        def ask_json(self, *a, **k):      # noqa: ANN002, ANN003
            raise RuntimeError("нет ответа от 8082")

    agent = Agent(brain=DeadBrain(), memory=None, doctrine="")
    reply = agent.handle("расскажи о законах дома")
    assert "мозг недоступен" in reply.text
    kinds = [r["kind"] for r in journal.recent()]
    assert "мозг-недоступен" in kinds


def test_agent_unknown_tool_is_a_lesson(home):
    from core.agent import Agent

    class WeirdBrain:
        def ask_json(self, *a, **k):      # noqa: ANN002, ANN003
            return {"action": {"tool": "телепорт", "args": {}}}

    agent = Agent(brain=WeirdBrain(), memory=None, doctrine="")
    reply = agent.handle("перенеси меня")
    assert "неизвестный инструмент" in reply.text
    kinds = [r["kind"] for r in journal.recent()]
    assert "неизвестный-инструмент" in kinds
