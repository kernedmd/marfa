# -*- coding: utf-8 -*-
"""ДОМ №38 «часы в состоянии» (23.11, вечер-3 — урок живого лога): Марфа
вписала в файл памяти timestamp «23.11.2023_15:34» — год выдуман от
бедности: у промпта не было источника времени. Теперь дата, время и день
недели — ПЕРВОЙ строкой состояния дома, а ЗАКОН ФАКТОВ в манифесте
запрещает выдумывать год и причины ошибок («нет разрешения»), которых
инструмент не возвращал."""
import datetime as dt
import re
from pathlib import Path

import pytest

from core import config, identity
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


_WEEKDAYS = ("понедельник", "вторник", "среда", "четверг", "пятница",
             "суббота", "воскресенье")


def test_state_starts_with_live_clock():
    s = _house_state()
    # «Состояние дома на воскресенье 23.11.2026 15:34 (…): мозг …»
    m = re.match(r"^Состояние дома на (%s) (\d{2}\.\d{2}\.(\d{4}) \d{2}:\d{2}) "
                 r"\(время и дата" % "|".join(_WEEKDAYS), s)
    assert m, "нет живых часов в первой строке: " + s[:120]
    now = dt.datetime.now()
    assert m.group(1) == _WEEKDAYS[now.weekday()]
    assert int(m.group(3)) == now.year          # год настоящий, не 2023


def test_status_command_carries_clock(agent, srv):
    r = agent.handle("статус")
    assert r.tool_used == "status" and srv.calls == []
    assert re.search(r"Состояние дома на \w+ \d{2}\.\d{2}\.\d{4} \d{2}:\d{2}",
                     r.text)


def test_brain_prompt_carries_clock(agent, srv):
    srv.reply_content = '{"answer": "вижу время в состоянии"}'
    agent.handle("какое сегодня число?")
    # день-11 (Ф77): часы живут в ХВОСТЕ ХОДА — сообщении Создателя,
    # не в системе (система статична ради KV-кэша). Закон №38 жив:
    # выдумывать год неоткуда — время читается каждым ходом
    user_msg = srv.calls[0]["messages"][-1]["content"]
    assert re.search(r"Состояние дома на \w+ \d{2}\.\d{2}\.\d{4} \d{2}:\d{2}",
                     user_msg)


def test_manifest_law_of_facts():
    m = identity.manifest()
    assert "ЗАКОН ФАКТОВ" in m
    assert "не выдумывай год" in m
    # выдуманное «нет разрешения» запрещено поимённо
    assert "нет разрешения" in m
