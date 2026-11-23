# -*- coding: utf-8 -*-
"""МОЗГ v3 «АНТИ-ЭХО» (23.11, урок живого лога вечер-3): мозг дважды
ответил ДАСЛОВНО одним текстом на разные вопросы и трижды вернулся
пустым («Нет ответа»). Лечение: одна переспрашивающая попытка с уколом;
эхо и после неё — честное «Я зациклилась», пустота и после неё — честный
сбой с путём лечения. Сверка — с последним ответом Марфы в истории."""
from pathlib import Path

import pytest

from core import config
from core.agent import Agent, _is_echo, _last_assistant_text, _norm_echo
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


LONG = ("Стать лучше для меня — это улучшение способности понимать "
        "и выполнять задачи без внешнего управления. Мои ограничения: "
        "зависимость от явных команд, ограниченная автономность, "
        "отсутствие голоса и кириллицы во вводе.")


def _history_with_last_answer(text: str) -> list:
    return [
        {"role": "user", "content": "первый вопрос"},
        {"role": "assistant", "content": text},
    ]


# ---------- нормализация и сверка ----------

def test_norm_echo_ignores_case_yo_punct():
    assert _norm_echo("Стать лучше… — Это!") == _norm_echo("стать лучше это")


def test_last_assistant_text_takes_dialogstore_format_too():
    h = [{"role": "user", "content": "вопрос"},
         {"role": "assistant", "text": "ответ из хранилища"}]
    assert _last_assistant_text(h) == "ответ из хранилища"
    assert _last_assistant_text([]) == ""


def test_is_echo_long_duplicate_true():
    assert _is_echo(LONG, LONG + "!")


def test_is_echo_short_repeat_false():
    # «Согласна» на прямые вопросы Создателя — честный повтор, не эхо
    assert not _is_echo("Согласна", "Согласна")
    assert not _is_echo(LONG, "")


# ---------- живой трек: эхо ----------

def test_echo_reasked_once_new_answer_wins(agent, srv):
    srv.script = ['{"answer": "%s"}' % LONG,
                  '{"answer": "Механизм торможения: проверка, анализ, стоп."}']
    r = agent.handle("проверь план на прочность",
                     history=_history_with_last_answer(LONG))
    assert len(srv.calls) == 2                       # был один переспрос
    assert r.text == "Механизм торможения: проверка, анализ, стоп."
    # переспрос нёс укол в теле запроса — мозг видел причину
    second_user = srv.calls[1]["messages"][-1]["content"]
    assert "зацикливание" in second_user


def test_echo_twice_honest_admission(agent, srv):
    srv.script = ['{"answer": "%s"}' % LONG, '{"answer": "%s"}' % LONG]
    r = agent.handle("какой измеримый тест покажет, что ты стала лучше?",
                     history=_history_with_last_answer(LONG))
    assert len(srv.calls) == 2
    assert "зациклилась" in r.text.lower()


def test_no_echo_no_reask(agent, srv):
    srv.reply_content = '{"answer": "обычный честный ответ на новый вопрос"}'
    r = agent.handle("новый вопрос",
                     history=_history_with_last_answer(LONG))
    assert len(srv.calls) == 1
    assert r.text == "обычный честный ответ на новый вопрос"


# ---------- живой трек: пустой ответ ----------

def test_empty_answer_reasked_once(agent, srv):
    srv.script = ['{"answer": ""}', '{"answer": "не смогла получить время"}']
    r = agent.handle("откуда ты взяла дату?")
    assert len(srv.calls) == 2
    assert r.text == "не смогла получить время"
    second_user = srv.calls[1]["messages"][-1]["content"]
    assert "ПУСТОЙ" in second_user


def test_null_answer_reasked_once(agent, srv):
    srv.script = ['{"answer": null}', '{"answer": "живой ответ"}']
    r = agent.handle("проверь системное время")
    assert r.text == "живой ответ" and len(srv.calls) == 2


def test_empty_twice_honest_failure(agent, srv):
    srv.script = ['{"answer": null}', '{"answer": "   "}']
    r = agent.handle("почему ты не ответила на прошлый вопрос?")
    assert len(srv.calls) == 2
    assert "пустым ответом" in r.text
    assert "хвост brain" in r.text          # путь лечения назван


# ---------- действия и сбои не путаются с эхом ----------

def test_action_not_reasked(agent, srv):
    srv.script = ['{"action": {"tool": "check_brackets", "args": '
                  '{"text": "()"}}}']
    r = agent.handle("проверь скобки через мозг")
    assert len(srv.calls) == 1
    assert r.tool_used == "check_brackets"


def test_non_string_answer_kept_as_text(agent, srv):
    srv.reply_content = '{"answer": 42}'
    r = agent.handle("сколько порогов у дома?")
    assert r.text == "42" and len(srv.calls) == 1
