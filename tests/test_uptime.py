# -*- coding: utf-8 -*-
r"""tests/test_uptime.py — №25 «сколько ты не спала»: бодрствование.

Отсчёт — рождение процесса (панель). Перезапуск — новое бодрствование,
честно. Статус дома тоже знает, с какого часа я не сплю.
"""
import datetime as dt

import pytest

import core.uptime as uptime
from core import config


@pytest.fixture()
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("MARFA_HOME", str(tmp_path))
    monkeypatch.setattr(config, "HOME_DIR", tmp_path)
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    config.ensure_dirs()
    yield tmp_path


def test_uptime_fresh_process():
    now = dt.datetime.now()
    uptime.STARTED_AT = now - dt.timedelta(seconds=30)
    text = uptime.uptime_text(now=now)
    assert "не сплю" in text


def test_uptime_minutes():
    now = dt.datetime.now()
    uptime.STARTED_AT = now - dt.timedelta(minutes=25)
    assert "25 мин" in uptime.uptime_text(now=now)


def test_uptime_hours():
    now = dt.datetime.now()
    uptime.STARTED_AT = now - dt.timedelta(hours=5, minutes=32)
    assert "5 ч 32 мин" in uptime.uptime_text(now=now)


def test_agent_command_how_long_awake(home, monkeypatch):
    # день-13: якорь против ночи — в окне сна организм честно спит
    # и «не сплю» не говорит; тест зелёный в любой час станции
    from core import sleep as sleep_mod
    monkeypatch.setattr(sleep_mod, "_in_window", lambda now: False)
    from core.agent import Agent
    r = Agent(brain=None, memory=None, doctrine="").handle(
        "сколько ты не спала")
    assert r.source == "python" and r.tool_used == "uptime"
    assert "не сплю" in r.text


def test_status_mentions_awake_since(home):
    from core.agent import Agent
    r = Agent(brain=None, memory=None, doctrine="").handle("статус")
    assert r.tool_used == "status"
    assert "не сплю с" in r.text
