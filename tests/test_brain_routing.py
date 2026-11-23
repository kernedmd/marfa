# -*- coding: utf-8 -*-
"""МАРШРУТ ДЕЙСТВИЯ v2 + ЖУРНАЛ МОЗГА (23.11, ночь — техническая мысль
Создателя: «возможно, её выход маршрутизируется не туда: она пишет
ответ, но в чат приходит эхо вызова»). Разбор по штампам живого лога
показал: те два «ui_action» прошли ПУТЁМ ОТВЕТА (штамп «179 ток»
ставится только там) — ответ мозга буквально был «ui_action», а
остальные токены съело невидимое думание. Но мысль Создателя нашла
НАСТОЯЩИЙ latent-баг: если мозг даёт answer И action вместе —
диспетчер молча выбрасывал answer, Создатель видел только результат
инструмента. Здесь якоря обеих правок: ответ не выбрасывается, штамп
токенов честен на обоих путях, и ЖУРНАЛ МОЗГА logs/brain_log.jsonl
записывает каждую генерацию (токены, думание, ответ целиком) — вопрос
«что она сгенерировала на N токенов» теперь проверяем командой
«хвост brain <подстрока>»."""
import json
from pathlib import Path

import pytest

from core import config
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


# ---------- маршрут «ответ + действие»: ответ не выбрасываем ----------

def test_answer_plus_action_both_shown(agent, srv):
    # гипотеза Создателя: мозг пишет ответ И зовёт инструмент —
    # прежде answer молча выбрасывался, в чат шло только эхо вызова
    srv.usage_extra = {"prompt_tokens": 3743}
    srv.reply_content = json.dumps({
        "answer": "Проверяю скобки в твоём тексте.",
        "action": {"tool": "check_brackets",
                   "args": {"text": "(())"}},
    }, ensure_ascii=False)
    r = agent.handle("проверь скобки (())")
    assert r.source == "brain"
    assert r.tool_used == "check_brackets"
    # ОБА: слова Марфы ПЕРВЫЕ, результат инструмента следом
    assert r.text.startswith("Проверяю скобки в твоём тексте.")
    assert "баланс" in r.text.lower() and "ок" in r.text.lower()
    # штамп токенов честен и на пути действия
    assert isinstance(r.meta, dict) and r.meta.get("tok")
    assert r.meta.get("ptok") == 3743


def test_action_only_still_clean(agent, srv):
    # действие без ответа — прежнее поведение: только результат
    srv.reply_content = json.dumps({
        "action": {"tool": "check_brackets", "args": {"text": "(()"}},
    }, ensure_ascii=False)
    r = agent.handle("проверь скобки (()")
    assert r.tool_used == "check_brackets"
    assert r.text.strip()          # результат есть
    assert "None" not in r.text    # и в нём нет мусора от пустого answer


# ---------- журнал мозга: «что она сгенерировала» — проверяемо ----------

def test_brain_log_records_answer_and_action(agent, srv):
    srv.usage_extra = {"prompt_tokens": 3612}
    srv.reply_content = json.dumps({
        "answer": "Сначала посмотрю, потом нажму.",
        "action": {"tool": "check_brackets", "args": {"text": "[]"}},
    }, ensure_ascii=False)
    agent.handle("проверь скобки []")
    log = Path(config.BRAIN_LOG_FILE)
    assert log.is_file()
    last = json.loads(log.read_text(encoding="utf-8").strip().splitlines()[-1])
    assert last["kind"] == "ask_json"
    assert last["ok"] is True
    assert last["answer"] == "Сначала посмотрю, потом нажму."
    assert "check_brackets" in (last["action"] or "")
    assert last["completion_tokens"] > 0
    assert last["prompt_tokens"] == 3612
    assert last["secs"] >= 0.0


def test_brain_log_shows_invisible_thinking(agent, srv):
    # разгадка «179 ток»: думание срезается и не показывается, но
    # журнал обязан его ВИДЕТЬ — think_chars отличает невидимое
    # думание от пропавшего ответа
    srv.reply_content = ('<think>думаю долго и незаметно про правило N3, '
                         'границы уместности и молчание — это невидимые '
                         'токены, которые Создатель ждёт как ответ</think>'
                         '{"answer": "готово"}')
    r = agent.handle("как дела?")
    assert r.text == "готово"
    last = json.loads(Path(config.BRAIN_LOG_FILE)
                      .read_text(encoding="utf-8").strip().splitlines()[-1])
    assert last["think_chars"] > 40
    assert last["answer"] == "готово"


def test_brain_log_marks_empty_answer(agent, srv):
    srv.reply_content = json.dumps({"answer": ""}, ensure_ascii=False)
    agent.handle("расскажи о законах дома")
    last = json.loads(Path(config.BRAIN_LOG_FILE)
                      .read_text(encoding="utf-8").strip().splitlines()[-1])
    assert last["note"] == "пустой ответ"     # фильтр «хвост brain пустой ответ» найдёт


def test_brain_log_marks_bad_json(agent, srv):
    srv.reply_content = "просто текст без json"
    agent.handle("расскажи о законах дома")
    lines = Path(config.BRAIN_LOG_FILE).read_text(encoding="utf-8").splitlines()
    assert any(json.loads(l)["note"] == "не-json" for l in lines)


def test_tail_brain_promise_is_real(agent, srv):
    # анти-эхо обещает «скажи „хвост brain пустой ответ“ — покажу лог»:
    # калитка обязана найти журнал по части имени
    from core import creator_gate
    srv.reply_content = json.dumps({"answer": "Смотрю на экран."},
                                   ensure_ascii=False)
    agent.handle("расскажи о законах дома")   # мозговой трек, не рефлекс
    out = creator_gate._cmd_tail("brain")
    assert "brain_log" in out
    assert "Смотрю на экран" in out


# ---------- живой лог 23.11: «ui_action» как ответ — виден в журнале ----------

def test_literal_ui_action_answer_is_logged_verbatim(agent, srv):
    # те два хода: штамп «179 ток» доказывает путь ответа — answer
    # буквально был «ui_action». Журнал теперь хранит это слово честно:
    # «хвост brain ui_action» покажет Создателю, что скрывалось за токенами
    srv.reply_content = json.dumps({"answer": "ui_action"},
                                   ensure_ascii=False)
    r = agent.handle("кто применяет правило?")
    assert r.text == "ui_action"      # это ответ, не эхо маршрута
    last = json.loads(Path(config.BRAIN_LOG_FILE)
                      .read_text(encoding="utf-8").strip().splitlines()[-1])
    assert last["answer"] == "ui_action"
    assert last["action"] is None     # действия НЕ БЫЛО — чистый ответ
