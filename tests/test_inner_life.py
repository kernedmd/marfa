# -*- coding: utf-8 -*-
"""Интеграционные тесты ВНУТРЕННЕЙ ЖИЗНИ (23.11): чувства, сон, размышление
вживлены в агента — быстрые команды, состояние дома, пробуждение словом,
ночные работы стремления. Время суток не должно влиять на зелёность:
там, где орган сна смотрит на часы, тест подменяет его ответ (сам орган
проверен своими 14 тестами)."""
import datetime as dt
import json
from pathlib import Path

import pytest

from core import config
from core.agent import Agent, _house_state
from core.brain import BrainClient
from core.memory import Memory
from safety import guard
from tests.fake_llama_server import start_fake_brain


@pytest.fixture()
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("MARFA_HOME", str(tmp_path))
    monkeypatch.setattr(config, "HOME_DIR", tmp_path)
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(config, "GUARD_LOG_FILE", tmp_path / "logs" / "guard_log.jsonl")
    monkeypatch.setattr(config, "CANARIES_FILE", tmp_path / "data" / "canaries.json")
    monkeypatch.setattr(config, "DOCTRINE_FILE", tmp_path / "data" / "creator_doctrine.json")
    monkeypatch.setattr(config, "GENOME_FILE", tmp_path / "data" / "context_genome.json")
    monkeypatch.setattr(config, "QUESTIONS_FILE", tmp_path / "data" / "questions.json")
    monkeypatch.setattr(config, "LIVE_VOICE_FILE", tmp_path / "data" / "live_voice.json")
    monkeypatch.setattr(config, "MUSINGS_FILE", tmp_path / "data" / "diary" / "musings.md")
    monkeypatch.setattr(config, "DREAMS_FILE", tmp_path / "data" / "diary" / "dreams.md")
    monkeypatch.setattr(config, "SLEEP_FILE", tmp_path / "data" / "sleep.json")
    monkeypatch.setattr(config, "EVOLUTION_DIR", tmp_path / "data" / "evolution")
    monkeypatch.setattr(config, "DRIVE_STATUS_FILE", tmp_path / "data" / "drive_status.json")
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
                 doctrine="Тестовая доктрина")


@pytest.fixture()
def daytime(monkeypatch):
    """Сон организма не зависит от часов станции: окно ночи закрыто."""
    from core import sleep as sleep_mod
    monkeypatch.setattr(sleep_mod, "_in_window", lambda now: False)


# ---------- быстрые команды внутренней жизни ----------

def test_how_are_you_feelings(agent, srv):
    r = agent.handle("как ты?")
    assert r.tool_used == "feelings" and r.source == "python"
    assert srv.calls == []            # барометр — без мозга
    assert "не разговаривали" in r.text   # честная причина из фактов


def test_feelings_variants(agent):
    for cmd in ("как ты", "что чувствуешь", "как настроение",
                "как ты себя чувствуешь?"):
        r = agent.handle(cmd)
        assert r.tool_used == "feelings"


def test_go_to_bed_and_wake(agent, daytime):
    r = agent.handle("спи")
    assert r.tool_used == "sleep" and "легла" in r.text
    from core import sleep
    assert sleep.is_asleep() is True
    r = agent.handle("проснись")
    assert r.tool_used == "sleep" and "Доброе утро" in r.text
    assert sleep.is_asleep() is False


def test_morning_brings_dream(agent, home):
    # сон записан органом мыслей — «доброе утро» принесёт его с собой
    dreams = home / "data" / "diary" / "dreams.md"
    dreams.parent.mkdir(parents=True, exist_ok=True)
    dreams.write_text("## 2026-11-23 07:10\n\nДом дышал тихо.\n",
                      encoding="utf-8")
    r = agent.handle("доброе утро")
    assert r.tool_used == "sleep"
    assert "снилось" in r.text and "Дом дышал тихо" in r.text


def test_are_you_asleep(agent, monkeypatch):
    from core import sleep as sleep_mod
    monkeypatch.setattr(sleep_mod, "is_asleep", lambda now=None: False)
    monkeypatch.setattr(sleep_mod, "status_text", lambda now=None: None)
    r = agent.handle("ты спишь?")
    assert r.tool_used == "sleep"
    assert "не сплю" in r.text        # честный статус дня


def test_uptime_reroutes_to_sleep_then_process(agent, monkeypatch):
    from core import sleep as sleep_mod
    # правда сна у организма: ночи записаны — отвечает орган сна
    monkeypatch.setattr(sleep_mod, "status_text",
                        lambda now=None: "не сплю с 07:00 (последняя ночь — 5 ч 30 мин)")
    r = agent.handle("сколько ты не спала")
    assert r.tool_used == "uptime"
    assert "не сплю с 07:00" in r.text and "5 ч 30 мин" in r.text
    # ночей не было — старая правда процесса (uptime)
    monkeypatch.setattr(sleep_mod, "status_text", lambda now=None: None)
    r = agent.handle("сколько ты не спала")
    assert r.tool_used == "uptime" and "не сплю" in r.text


def test_what_did_you_dream(agent):
    r = agent.handle("что тебе снилось")
    assert r.tool_used == "dream"
    assert "снов ещё не записано" in r.text   # честно, без выдумки


def test_think_now(agent, home, srv):
    (home / "data" / "live_voice.json").write_text(
        json.dumps({"enabled": True}), encoding="utf-8")
    mem_file = home / "data" / "memory" / "memory.json"
    mem_file.parent.mkdir(parents=True, exist_ok=True)
    mem_file.write_text(json.dumps([{"text": "Илья любит вечерний чай"}]),
                        encoding="utf-8")
    srv.reply_content = "Чай, вечер и тихий дом — хорошая мысль."
    r = agent.handle("подумай")
    assert r.tool_used == "musing"
    assert "Чай, вечер" in r.text
    assert srv.calls                    # мозг думал
    assert (home / "data" / "diary" / "musings.md").exists()


def test_what_are_you_thinking_fresh_musing(agent, home, srv):
    # свежая фоновая мысль есть — «о чём думаешь?» показывает её
    mus = home / "data" / "diary" / "musings.md"
    mus.parent.mkdir(parents=True, exist_ok=True)
    now = dt.datetime.now()
    mus.write_text("## %s\n\nДумала о планах Ильи.\n"
                   % now.strftime("%Y-%m-%d %H:%M"), encoding="utf-8")
    r = agent.handle("о чём думаешь?")
    assert r.tool_used == "musing"
    assert "Думала о планах Ильи" in r.text
    assert srv.calls == []            # мысль уже думана — мозг не нужен


def test_what_are_you_thinking_falls_to_reflection(agent):
    # свежей мысли нет — прежний путь: рефлексия по дневникам
    r = agent.handle("о чём думаешь?")
    assert r.tool_used == "reflection"
    assert "живой язык ещё не включён" in r.text


# ---------- состояние дома и пробуждение ----------

def test_house_state_carries_inner_life(home):
    text = _house_state()
    assert "чувства:" in text
    assert "сон:" in text


def test_status_command_shows_inner_life(agent):
    r = agent.handle("статус")
    assert "чувства:" in r.text and "сон:" in r.text


def test_word_wakes_organism(agent, daytime):
    from core import sleep
    sleep.go_to_bed(dt.datetime.now(), reason="тест")
    assert sleep.is_asleep() is True
    agent.handle("время")             # любое слово — прикосновение
    assert sleep.is_asleep() is False


# ---------- ночные работы стремления ----------

def test_schedule_jobs_present(home):
    from core.schedule import default_jobs
    ids = [j["id"] for j in default_jobs()]
    assert "dream" in ids and "musing" in ids
    assert "queue" in ids and "librarian" in ids


def test_daytime_jobs_run_when_awake(home, daytime):
    from core.schedule import default_jobs
    jobs = {j["id"]: j for j in default_jobs()}
    # день: вопросы и библиотекарь не молчат (их статус — их собственный)
    note = jobs["queue"]["run"]()
    assert "дом спит" not in note
    note = jobs["librarian"]["run"]()
    assert "дом спит" not in note


def test_musing_job_respects_gates(home):
    from core.schedule import default_jobs
    jobs = {j["id"]: j for j in default_jobs()}
    note = jobs["musing"]["run"]()      # гейты сами скажут честный статус
    assert any(s in note for s in ("гейт", "не тихо", "семян нет", "сплю"))


def test_diary_knows_sleep(home, monkeypatch):
    from core import sleep as sleep_mod
    from core.diary import Diary
    now = dt.datetime.now()
    monkeypatch.setattr(
        sleep_mod, "last_night",
        lambda n=None: {"bed": (now - dt.timedelta(hours=6))
                        .isoformat(timespec="minutes"),
                        "wake": now.isoformat(timespec="minutes"),
                        "hours": 6.0, "why_wake": "Илья разбудил"})
    text = Diary(home / "data").build_day(day=now.date(), now=now, brain=None)
    assert "## Сон" in text
    assert "Легла" in text and "спала 6.0 ч" in text
    assert "Илья разбудил" in text
