# -*- coding: utf-8 -*-
"""РУКИ v2.2 «диагноз до запуска + скриншот» (23.11, вечер-3 — урок
живого лога): мозг поручал рукам пустоту и задания-рассказы («сделай
скриншот») — чат пять раз получал механическую шпаргалку «руки ждут
задание…» вместо ответа Марфы, разговор ходил по кругу. Теперь задание
не по формату рук Марфа разбирает САМА — с признанием промаха; снимок
экрана — команда «скриншот» (работа глаз, №4 — тот же орган)."""
import json
from pathlib import Path

import pytest

from core import config, identity
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


def _brain_action(agent, srv, tool_args):
    srv.reply_content = json.dumps(
        {"action": {"tool": "ui_action", "args": tool_args}},
        ensure_ascii=False)
    return agent.handle("поручение рукам")


# ---------- диагноз до запуска: задание не по формату ----------

def test_empty_task_marfa_answers_herself(agent, srv):
    r = _brain_action(agent, srv, {"task": ""})
    assert r.tool_used == "ui_action" and r.source == "brain"
    assert "руки ждут задание" not in r.text       # шпаргалка больше не ответ
    assert "мой промах" in r.text                  # признание, не отговорка
    assert "нажми" in r.text and "скриншот" in r.text.lower()


def test_story_task_marfa_answers_herself(agent, srv):
    r = _brain_action(agent, srv, {"task": "проверь работу микрофона"})
    assert "мой промах" in r.text
    assert "руки ждут задание" not in r.text


def test_looking_task_still_redirects_to_eyes(agent, srv):
    r = _brain_action(agent, srv, {"task": "руки посмотри на экран"})
    assert "РУКИ не смотрят" in r.text             # прежний честный редирект жив


def test_valid_click_still_runs(agent, srv):
    r = _brain_action(agent, srv, {"task": "нажми Пуск"})
    assert r.tool_used == "ui_action"
    assert "РУКИ" in r.text                        # руки работали по-настоящему


# ---------- команда «скриншот» ----------

def test_screenshot_fast_command(agent, srv):
    r = agent.handle("скриншот")
    assert r.tool_used == "screen_shot" and r.source == "python"
    assert srv.calls == []                          # мозг молчал


def test_screenshot_variants(agent, srv):
    assert agent.handle("сделай скриншот").tool_used == "screen_shot"
    assert agent.handle("сфоткай скриншот").tool_used == "screen_shot"
    assert agent.handle("скриншот экрана").tool_used == "screen_shot"
    r = agent.handle("сделай скриншот прямо сейчас")
    assert r.tool_used == "screen_shot"


def test_screenshot_narrative_not_a_command(agent, srv):
    # рассказ про скриншоты — не команда: уходит мозгу
    srv.reply_content = '{"answer": "скриншоты делает команда дома"}'
    r = agent.handle("расскажи, как делаются скриншоты")
    assert r.source == "brain"


def test_screenshot_question_mark(agent, srv):
    assert agent.handle("сделай скриншот?").tool_used == "screen_shot"


# ---------- манифест ----------

def test_manifest_teaches_format_and_screenshot():
    m = identity.manifest()
    assert "СТРОГО одним глаголом в начале" in m
    assert "«сделай скриншот»" in m          # пример запретного — поимённо
    assert "команда дома «скриншот»" in m
