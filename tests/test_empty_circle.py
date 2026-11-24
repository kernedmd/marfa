# -*- coding: utf-8 -*-
"""Круг 14 «ПУСТОЙ ОТВЕТ» (день-12, 24.11 вечер — живой лог Создателя):

«Марфа, вернись к файлу урок1.json. Одно слово: почему или проверка?
…» — 37,9 с · мозг · 21 ток · промпт 4423, и «мозг вернулся с пустым
ответом дважды». 21 ток генерации — и ни слова Создателю: мозг
ОТВЕТИЛ, но дом не прочитал (или ответа действительно не было —
журнал не говорил КАК). Круг лечит КЛАСС пустоты, не симптом:

- Ф81 «ЧЕСТНАЯ ПУСТОТА»: brain-журнал несёт сырую улику (raw) при
  «пустом ответе» и «не-json»; BrainClient.last_raw — улика агенту;
  честный сбой в чате показывает, ЧТО прислал мозг, не только
  обещание «хвост brain покажет»;
- Ф82 «УКОЛ ЗНАЕТ БОЛЕЗНЬ»: пустой укол читает улику и называет
  модель конкретную ошибку (русский ключ / null / пустая строка) +
  закон ключа в преамбуле ask_json — до болезни, а не после;
- Ф83 «ПЕРЕВОДЧИК КЛЮЧА»: валидный JSON с чужим ключом («ответ»,
  «response», «reply», «text») читается домом — за ОДНУ генерацию,
  без минуты ретрая; неизвестные ключи — мимо, телепатии нет.
"""
import json
from pathlib import Path

import pytest

from core import config
from core.agent import Agent, _nudge_empty_for, _salvage_answer
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
    monkeypatch.setattr(config, "BRAIN_LOG_FILE",
                        tmp_path / "logs" / "brain_log.jsonl")
    monkeypatch.setattr(config, "GUARD_LOG_FILE",
                        tmp_path / "logs" / "guard_log.jsonl")
    monkeypatch.setattr(config, "CANARIES_FILE",
                        tmp_path / "data" / "canaries.json")
    monkeypatch.setattr(config, "DOCTRINE_FILE",
                        tmp_path / "data" / "creator_doctrine.json")
    monkeypatch.setattr(config, "GENOME_FILE",
                        tmp_path / "data" / "context_genome.json")
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


def _last_empty_log_line() -> dict:
    """Последняя строка brain-журнала с меткой «пустой ответ»."""
    lines = (Path(config.BRAIN_LOG_FILE)
             .read_text(encoding="utf-8").strip().splitlines())
    for line in reversed(lines):
        rec = json.loads(line)
        if rec.get("note") == "пустой ответ":
            return rec
    raise AssertionError("в журнале нет строки «пустой ответ»")


# ---------- Ф81: улика в журнале и на клиенте ----------

def test_brain_log_carries_raw_evidence(agent, srv):
    """«пустой ответ» без сырой улики — телепатия: 21 ток сгорел, а
    ЧТО прислал мозг — null? пустые кавычки? русский ключ? — журнал
    молчал. Теперь raw лежит рядом с note (живой лог 24.11)."""
    srv.script = ['{"answer": null}', '{"answer": "живой ответ"}']
    agent.handle("откуда ты взяла дату?")
    rec = _last_empty_log_line()
    assert rec["raw"] == '{"answer": null}'


def test_brain_log_raw_only_when_noted(agent, srv):
    """Честный ответ журналом не раздувается: raw — только по поводу
    (пусто/не-json), каждый ход разговора не дублируется сырой копией."""
    srv.reply_content = '{"answer": "нормальный ответ"}'
    agent.handle("расскажи о законах дома")
    lines = Path(config.BRAIN_LOG_FILE).read_text(encoding="utf-8").splitlines()
    for line in lines:
        assert "raw" not in json.loads(line)


def test_client_last_raw_survives_parse(agent, srv):
    """Улика доступна агенту сразу после генерации — до разбора и
    ретрая: укол (Ф82) читает её, а не гадает."""
    srv.reply_content = '{"ответ": "проверка"}'
    agent.handle("почему или проверка?")
    assert agent.brain.last_raw == '{"ответ": "проверка"}'


# ---------- Ф82: укол знает болезнь ----------

def test_nudge_names_russian_key(agent, srv):
    """Улик — русский ключ: укол обязан сказать, ЧТО было не так
    (общий «ответь по существу» лечил наугад — вторая попытка
    повторяла первую)."""
    # «ответ» есть, но пустой null — спастись нельзя, укол зовёт
    srv.script = ['{"ответ": null}', '{"answer": "живой ответ"}']
    agent.handle("почему или проверка?")
    second_user = srv.calls[1]["messages"][-1]["content"]
    assert "ПУСТОЙ" in second_user            # база анти-эхо цела
    assert "латиницей" in second_user         # диагноз назван
    assert "русским ключом" in second_user


def test_nudge_names_null(agent, srv):
    """Улик — null: укол зовёт null по имени, формат — в том же
    сообщении (одна попытка чинит конкретное)."""
    srv.script = ['{"answer": null}', '{"answer": "живой ответ"}']
    r = agent.handle("проверь системное время")
    assert r.text == "живой ответ"
    second_user = srv.calls[1]["messages"][-1]["content"]
    assert "null" in second_user and "непустое" in second_user


def test_nudge_names_empty_string(agent, srv):
    """Улик — пустая строка: своя формулировка, не чужая."""
    srv.script = ['{"answer": ""}', '{"answer": "живой ответ"}']
    r = agent.handle("откуда ты взяла дату?")
    assert r.text == "живой ответ"
    second_user = srv.calls[1]["messages"][-1]["content"]
    assert "пустой строкой" in second_user


def test_preamble_teaches_the_key_law(agent, srv):
    """Закон ключа — в преамбуле ask_json (до болезни): «answer»
    латиницей, значение непустое. Статично — KV-кэш цел."""
    srv.reply_content = '{"answer": "нормально"}'
    agent.handle("расскажи о законах дома")
    system = srv.calls[0]["messages"][0]["content"]
    assert "латиницей" in system and "null — не ответ" in system


def test_nudge_unit_diagnoses_from_raw():
    """Укол — чистая функция от улики: три болезни, три диагноза."""
    assert "русским ключом" in _nudge_empty_for('{"ответ": null}')
    assert "null" in _nudge_empty_for('{"answer": null}')
    assert "пустой строкой" in _nudge_empty_for('{"answer": ""}')
    base = _nudge_empty_for("")
    assert "ПУСТОЙ" in base and "латиницей" in base  # база+формат всегда


# ---------- Ф83: переводчик ключа ----------

def test_salvage_russian_key_one_generation(agent, srv):
    """Живой лог: «почему или проверка?» — 21 ток и «пустой ответ».
    Мозг ОТВЕТИЛ под чужим ключом — дом читает, ход не сгорает,
    вторая генерация не нужна (СКОРОСТЬ: минута ретрая не платится)."""
    srv.reply_content = '{"ответ": "проверка"}'
    r = agent.handle("почему или проверка?")
    assert r.text == "проверка"
    assert len(srv.calls) == 1                # без переспроса


def test_salvage_english_aliases(agent, srv):
    """Известные алиасы читаются все — модель не обязана помнить
    русский, чтобы быть понятой. Вопрос каждый раз новый — память
    ответов (Ф41) не подменяет проверку живого хода."""
    for i, key in enumerate(("response", "reply", "text")):
        srv.script = ['{"%s": "живой ответ %d"}' % (key, i)]
        before = len(srv.calls)
        r = agent.handle("проверь системное время, попытка %d" % i)
        assert r.text == "живой ответ %d" % i, key
        assert len(srv.calls) - before == 1, key


def test_salvage_skips_empty_alias_and_finds_next():
    """Пустой алиас — не ответ: перебор идёт дальше по списку."""
    d = {"answer": "", "response": "", "reply": "нашлось"}
    assert _salvage_answer(d) == "нашлось"


def test_salvage_ignores_unknown_keys(agent, srv):
    """«мысль»/«заметка» — не алиасы: телепатией дом не занимается,
    честный путь — укол и переспрос."""
    srv.script = ['{"мысль": "глубокая"}', '{"answer": "живой ответ"}']
    r = agent.handle("проверь системное время")
    assert r.text == "живой ответ"
    assert len(srv.calls) == 2                # спасать было нечем — укол


def test_salvage_never_touches_actions(agent, srv):
    """Действие — не пустота: переводчик не перехватывает маршрут
    инструментов (даже если tool-JSON несёт поле «text»)."""
    srv.script = ['{"action": {"tool": "check_brackets", '
                  '"args": {"text": "()"}}}']
    r = agent.handle("проверь скобки через мозг")
    assert r.tool_used == "check_brackets"
    assert len(srv.calls) == 1


def test_salvage_normal_answer_untouched():
    """Ответ на месте — спасать нечего: переводчик молчит."""
    assert _salvage_answer({"answer": "живой"}) == ""


# ---------- Ф81+Ф83: честный сбой несёт улику ----------

def test_honest_failure_carries_evidence(agent, srv):
    """Дважды пусто — сбой честен И ГОВОРЯЩ: что прислал мозг видно
    в чате сразу, не только через «хвост brain пустой ответ»."""
    srv.script = ['{"answer": null}', '{"answer": "   "}']
    r = agent.handle("почему ты не ответила на прошлый вопрос?")
    assert "пустым ответом" in r.text          # якоря анти-эхо целы
    assert "хвост brain" in r.text
    assert '{"answer": "   "}' in r.text       # улика последней попытки


def test_honest_failure_long_evidence_capped(agent, srv):
    """Улика длинного брака режется — сбой читаем, чат не тонет."""
    huge = '{"answer": null, "note": "%s"}' % ("мусор " * 200)
    srv.script = [huge, '{"answer": ""}']
    r = agent.handle("почему ты не ответила на прошлый вопрос?")
    ev_start = r.text.find("последней попытке:")
    assert ev_start > 0
    assert len(r.text) - ev_start < 400        # срез 160 симв + вводка
