# -*- coding: utf-8 -*-
"""tests/test_creator_gate.py — калитка Создателя: 9 проверок.

Контракт (ТЗ «вичка по-взрослому»):
  - без слова в .env калитка закрыта и никому об этом не сообщает;
  - слово короче 4 символов = не установлено;
  - точное совпадение по префиксу и границе слова, сравнение постоянного времени;
  - неверное слово — тишина, путь обычный;
  - сообщение со словом никогда не доходит до мозга (диспетчер отвечает сам);
  - хвост логов читает только файлы внутри logs/, наружу выйти нельзя.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import creator_gate  # noqa: E402

WORD = "севрюжина"   # тестовое слово: в боевом .env его нет и не будет


@pytest.fixture
def gate(monkeypatch):
    """Калитка с тестовым словом; тяжёлые команды подменены заглушками."""
    monkeypatch.setattr(creator_gate, "load_env", lambda: {creator_gate.ENV_KEY: WORD})
    captured = {"status": 0, "tests": 0}
    monkeypatch.setattr(creator_gate, "_cmd_status",
                        lambda: (captured.__setitem__("status", captured["status"] + 1) or "ОСМОТР"))
    monkeypatch.setattr(creator_gate, "_cmd_tests",
                        lambda: (captured.__setitem__("tests", captured["tests"] + 1) or "БАТАРЕЯ"))
    return captured


# ---------- закрытая калитка ----------

def test_gate_disabled_without_codeword(monkeypatch):
    monkeypatch.setattr(creator_gate, "load_env", lambda: {})
    assert creator_gate.check(WORD + " статус") == (False, None)
    assert creator_gate.check("статус") == (False, None)


def test_gate_ignores_short_codeword(monkeypatch):
    monkeypatch.setattr(creator_gate, "load_env",
                        lambda: {creator_gate.ENV_KEY: "abc"})
    assert creator_gate.check("abc статус") == (False, None)


# ---------- открытие только точным словом ----------

def test_gate_hit_on_exact_prefix(gate):
    hit, reply = creator_gate.check(WORD + " статус")
    assert hit is True and reply == "ОСМОТР"
    assert gate["status"] == 1


def test_gate_requires_word_boundary(gate):
    # слитное «словостатус» — не калитка: слово должно кончиться границей
    assert creator_gate.check(WORD + "статус") == (False, None)
    assert gate["status"] == 0


def test_gate_wrong_word_is_silent(gate):
    # неверное слово: тишина, команды не звались, подсказки нет
    assert creator_gate.check("селёдка статус") == (False, None)
    assert gate["status"] == 0


def test_gate_help_on_unknown_command(gate):
    hit, reply = creator_gate.check(WORD)
    assert hit is True and "статус" in reply
    hit, reply = creator_gate.check(WORD + " танцы")
    assert hit is True and "хвост" in reply   # подсказка, а не выдумка


# ---------- хвост логов ----------

def test_tail_reads_last_lines(gate, monkeypatch, tmp_path):
    logs = tmp_path / "sync"
    logs.mkdir()
    (logs / "sync_20261118_180641.txt").write_text(
        "строка1\nстрока2\nхвост дома\n", encoding="utf-8")
    monkeypatch.setattr(creator_gate.config, "LOGS_DIR", tmp_path)
    hit, reply = creator_gate.check(WORD + " хвост sync")
    assert hit is True and "хвост дома" in reply


def test_tail_cannot_escape_logs(gate, monkeypatch, tmp_path):
    # снаружи лежит секрет; просим «хвост ../secret» — наружу выйти нельзя
    secret = tmp_path / "secret.log"
    secret.write_text("СЕКРЕТ-НЕ-ЧИТАТЬ\n", encoding="utf-8")
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "безобидный.log").write_text("тут пусто\n", encoding="utf-8")
    monkeypatch.setattr(creator_gate.config, "LOGS_DIR", logs)
    hit, reply = creator_gate.check(WORD + " хвост ../secret")
    assert hit is True
    assert "СЕКРЕТ-НЕ-ЧИТАТЬ" not in reply   # путь наружу не собирается из строки


# ---------- интеграция с диспетчером ----------

def test_agent_routes_gate_before_brain(gate):
    from core.agent import Agent, Reply

    class FakeBrain:
        def __init__(self):
            self.calls = 0

        def ask_json(self, *a, **k):
            self.calls += 1
            return {"answer": "мозг говорил"}

    class FakeMemory:
        def recall(self, *a, **k):
            return []

    brain = FakeBrain()
    agent = Agent(brain=brain, memory=FakeMemory())
    reply = agent.handle(WORD + " статус")
    assert isinstance(reply, Reply)
    assert reply.tool_used == "creator_gate" and reply.text == "ОСМОТР"
    assert brain.calls == 0            # мозг слова не увидел


# ---------- №26: фильтр хвоста по подстроке ----------

@pytest.fixture()
def brain_logs(monkeypatch, tmp_path):
    """Свежайший brain-лог с вперемешку строками + сосед-приманка."""
    logs = tmp_path / "logs"
    logs.mkdir()
    brain_log = logs / "brain_20261123_120000.log"
    brain_log.write_text(
        "12:00:01 вопрос принят\n"
        "12:00:02 ERROR таймаут мозга 300 с\n"
        "12:00:03 ретрай\n"
        "12:00:04 ошибка: пустой ответ\n"
        "12:00:05 ответ выдан\n"
        "12:00:06 ОШИБКА контекст 4096\n",
        encoding="utf-8")
    old_brain = logs / "brain_20261118_010000.log"
    old_brain.write_text("ERROR из старого лога — не должен попасть\n",
                         encoding="utf-8")
    import os
    os.utime(old_brain, (1000000, 1000000))     # старый по mtime
    monkeypatch.setattr(creator_gate.config, "LOGS_DIR", logs)
    return brain_log


def test_tail_filter_by_substring(gate, brain_logs):
    """№26: «хвост brain ошибка» — только строки с «ошибка» из
    СВЕЖАЙШЕГО brain-лога, регистр не важен, приманки мимо."""
    hit, reply = creator_gate.check(WORD + " хвост brain ошибка")
    assert hit is True
    assert "найдено 2" in reply
    assert "ошибка: пустой ответ" in reply
    assert "ОШИБКА контекст" in reply        # регистр фильтра не важен
    assert "вопрос принят" not in reply      # мимо фильтра
    assert "из старого лога" not in reply    # свежайший, не старый
    assert "ретрай" not in reply
    # английское ERROR — не русское «ошибка»: фильтр — подстрока,
    # а не переводчик
    assert "ERROR таймаут" not in reply


def test_tail_filter_no_match_honest(gate, brain_logs):
    """Совпадений ноль — честно: сколько строк смотрели и что искали."""
    hit, reply = creator_gate.check(WORD + " хвост brain хомяк")
    assert hit is True
    assert "нет «хомяк»" in reply and "6 строках" in reply


def test_tail_without_filter_unchanged(gate, brain_logs):
    """Старое поведение цело: «хвост brain» — все последние строки.
    КРУГ 36 (ритуал продления): строк теперь с ЧИСЛОМ — сколько
    показали, честно видно и без фильтра."""
    hit, reply = creator_gate.check(WORD + " хвост brain")
    assert hit is True
    assert "вопрос принят" in reply and "ретрай" in reply
    assert "последние 6 строк" in reply


def test_tail_filter_multiword(gate, brain_logs):
    """Подстрока из нескольких слов — тоже фильтр."""
    hit, reply = creator_gate.check(WORD + " хвост brain пустой ответ")
    assert hit is True
    assert "пустой ответ" in reply
    assert "вопрос принят" not in reply


def test_tail_filter_cannot_escape_logs(gate, monkeypatch, tmp_path):
    """Побег невозможен и с фильтром: файлы ищутся СРЕДИ logs/ по имени,
    путь не склеивается из строки — снаружи не читается ничего."""
    secret = tmp_path / "secret.log"
    secret.write_text("СЕКРЕТ-НЕ-ЧИТАТЬ\n", encoding="utf-8")
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "безобидный.log").write_text("тут пусто\n", encoding="utf-8")
    monkeypatch.setattr(creator_gate.config, "LOGS_DIR", logs)
    for query in ("хвост ../secret пароль", "хвост ..\\..\\secret СЕКРЕТ",
                  "хвост /etc/passwd root"):
        hit, reply = creator_gate.check(WORD + " " + query)
        assert hit is True, query
        assert "СЕКРЕТ-НЕ-ЧИТАТЬ" not in reply, query
        assert "root:" not in reply, query


def test_tail_help_mentions_filter(gate):
    hit, reply = creator_gate.check(WORD)
    assert hit is True
    assert "подстрока" in reply and "фильтр" in reply
