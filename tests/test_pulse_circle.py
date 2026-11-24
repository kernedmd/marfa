# -*- coding: utf-8 -*-
"""КРУГ 15 «ПУЛЬС ДОМА» (день-13) — Ф85–Ф89 + починка полей бухгалтерии.

Живой лог Createля (24.11): «солнце» за 91,3 с · 9 ток · промпт 4416 —
цифры ехали в штампах и brain_log.jsonl, но разговором не становились:
«как ты?» отвечала ДУША (чувства из фактов), а ТЕЛО (ходы, медиана
секунд, пустые ответы, дрейф против недели) молчало. Организм, не
знающий своего пульса, — не организм.

Разведка круга вскрыла и жука бухгалтерии: energy читала «ctok», а
promptweight — «ptok»; живой журнал с рождения (23.11) пишет
«completion_tokens»/«prompt_tokens» — на живой станции токи ответов
всегда были нулём, а истина сервера — None. Якорь годами проверял
опечатку фикстуры против опечатки источника (урок дня-10 повторился).

Фишки круга: Ф85 пульс дня (refлекс, мозг молчит), Ф86 душа и тело
(«как ты?» отвечает обоими), Ф87 дрейф скорости (сегодня против
недели, живой брат Ф44), Ф88 шрамы в хвосте (профилактика закона
ключа в сутках с серией пустых), Ф89 пульс в зеркалах (статус,
изучи себя, имя в манифесте)."""
import datetime as dt
import json
import time
from pathlib import Path

import pytest

from core import config, daypulse, energy, promptweight
from core.agent import Agent
from core.brain import BrainClient
from core.identity import manifest_slim
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
                 doctrine="Тестовая доктрина пульса")


def _line(ts: str, secs=10.0, ptok=100, ctok=20, note="", ok=True) -> str:
    """Строка журнала ЖИВОЙ формы — как пишет _log_brain_call."""
    rec = {"ts": ts, "kind": "ask", "secs": secs,
           "prompt_tokens": ptok, "completion_tokens": ctok,
           "think_chars": 0, "ok": ok, "note": note,
           "answer": None if note else "ответ"}
    return json.dumps(rec, ensure_ascii=False)


def _today() -> dt.datetime:
    return dt.datetime.now()


# ---------- Ф85 пульс дня ----------

def test_pulse_empty_day_honest(home):
    """Журнала нет — «молчал», а не нули-обман (закон фактов)."""
    out = daypulse.render()
    assert "молчал" in out
    assert "0 ходов" not in out


def test_pulse_collect_today_only(home):
    """Пульс считает только сегодняшний день; вчерашний — мимо."""
    now = _today()
    yesterday = (now - dt.timedelta(days=1)).strftime("%Y-%m-%d")
    lines = [
        _line(now.strftime("%Y-%m-%d") + " 09:00:00", secs=10.0, ptok=100, ctok=5),
        _line(now.strftime("%Y-%m-%d") + " 10:00:00", secs=20.0, ptok=200, ctok=10),
        _line(now.strftime("%Y-%m-%d") + " 11:00:00", secs=30.0, ptok=300, ctok=15,
              note="пустой ответ", ok=True),
        _line(yesterday + " 23:00:00", secs=99.0, ptok=999, ctok=99),
    ]
    config.BRAIN_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    config.BRAIN_LOG_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    p = daypulse.collect()
    assert p["turns"] == 3                     # вчерашний не считается
    assert p["empty"] == 1
    assert p["median"] == 20.0                 # 10/20/30 → медиана 20
    assert p["ptok"] == 600 and p["ctok"] == 30
    assert p["answered"] == 3


def test_pulse_render_carries_digits(home):
    now = _today()
    day = now.strftime("%Y-%m-%d")
    config.BRAIN_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    config.BRAIN_LOG_FILE.write_text(
        _line(day + " 09:00:00", secs=20.0, ptok=200, ctok=10) + "\n",
        encoding="utf-8")
    out = daypulse.render()
    assert "Пульс дня" in out
    assert "медиана 20,0" in out
    assert "пустых ответов нет" in out
    assert "дрейф" in out


def test_pulse_reflex_brain_silent(agent, srv):
    r = agent.handle("пульс дня")
    assert r.tool_used == "pulse" and r.source == "python"
    assert srv.calls == []                     # пульс — рефлекс: мозг молчит


def test_pulse_variants(agent):
    for cmd in ("пульс", "пульс дома", "какой у тебя пульс"):
        r = agent.handle(cmd)
        assert r.tool_used == "pulse"


def test_pulse_counts_real_brain_path(agent, srv):
    """Живой путь: ход к мозгу пишет журнал — пульс его видит.
    Замыкает круг «кто пишет → кто читает» без синтетики."""
    srv.usage_extra = {"prompt_tokens": 1500, "completion_tokens": 30}
    agent.handle("привет, кто ты?")
    assert srv.calls                          # мозг правда звался
    p = daypulse.collect()
    assert p["turns"] >= 1
    assert p["ctok"] >= 1


def test_pulse_broken_lines_skipped(home):
    now = _today()
    day = now.strftime("%Y-%m-%d")
    config.BRAIN_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    config.BRAIN_LOG_FILE.write_text(
        "{битый json\n" +
        _line(day + " 09:00:00", secs=12.0) + "\n" +
        "\n", encoding="utf-8")
    p = daypulse.collect()
    assert p["turns"] == 1                     # битая строка не роняет пульс


# ---------- Ф86 душа и тело ----------

def test_how_are_you_answers_with_body(agent, srv):
    r = agent.handle("как ты?")
    assert r.tool_used == "feelings" and r.source == "python"
    assert srv.calls == []                     # рефлекс
    assert "не разговаривали" in r.text        # душа честна (чувства)
    assert "тело:" in r.text                   # Ф86: и тело в ответе


def test_body_line_honest_empty(home):
    line = daypulse.body_line()
    assert "молчало" in line


# ---------- Ф87 дрейф скорости ----------

def _write_week(now: dt.datetime, day_secs: float, days: int = 5) -> None:
    """Неделя до сегодня: по одному честному ходу в день."""
    lines = []
    for i in range(1, days + 1):
        d = (now - dt.timedelta(days=i)).strftime("%Y-%m-%d")
        lines.append(_line(d + " 12:00:00", secs=day_secs))
    config.BRAIN_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    config.BRAIN_LOG_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_drift_heavier_today(home):
    now = _today()
    _write_week(now, day_secs=20.0)
    day = now.strftime("%Y-%m-%d")
    with config.BRAIN_LOG_FILE.open("a", encoding="utf-8") as f:
        for h in ("09:00:00", "10:00:00", "11:00:00"):
            f.write(_line(day + " " + h, secs=40.0) + "\n")
    out = daypulse.drift_line()
    assert "тяжелее" in out
    assert "40,0" in out and "20,0" in out


def test_drift_lighter_today(home):
    now = _today()
    _write_week(now, day_secs=30.0)
    day = now.strftime("%Y-%m-%d")
    with config.BRAIN_LOG_FILE.open("a", encoding="utf-8") as f:
        for h in ("09:00:00", "10:00:00", "11:00:00"):
            f.write(_line(day + " " + h, secs=10.0) + "\n")
    out = daypulse.drift_line()
    assert "легче" in out


def test_drift_few_turns_honest(home):
    """Три секунды — не статистика: двух ходов мало для диагноза."""
    now = _today()
    day = now.strftime("%Y-%m-%d")
    config.BRAIN_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    config.BRAIN_LOG_FILE.write_text(
        _line(day + " 09:00:00", secs=5.0) + "\n" +
        _line(day + " 09:01:00", secs=6.0) + "\n", encoding="utf-8")
    assert "мало ходов" in daypulse.drift_line()


# ---------- Ф88 шрамы в хвосте ----------

def test_scars_ride_in_tail(agent, home):
    """Сутки с серией пустых ответов — каждый ход несёт закон ключа."""
    now = _today()
    config.BRAIN_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    config.BRAIN_LOG_FILE.write_text(
        _line((now - dt.timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S"),
              secs=30.0, note="пустой ответ") + "\n" +
        _line((now - dt.timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S"),
              secs=25.0, note="пустой ответ") + "\n", encoding="utf-8")
    tail = agent._turn_context("привет")
    assert "ШРАМЫ СУТОК" in tail
    assert "answer" in tail                   # закон ключа назван


def test_scars_silent_when_clean(agent, home):
    """Чистые сутки — блок молчит: хвост дорог (урок диеты)."""
    now = _today()
    config.BRAIN_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    config.BRAIN_LOG_FILE.write_text(
        _line(now.strftime("%Y-%m-%d") + " 09:00:00", secs=10.0) + "\n",
        encoding="utf-8")
    tail = agent._turn_context("привет")
    assert "ШРАМЫ" not in tail


def test_scars_single_empty_below_threshold(agent, home):
    """Один пустой ответ — шум, не серия: порог 2 честен."""
    now = _today()
    config.BRAIN_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    config.BRAIN_LOG_FILE.write_text(
        _line(now.strftime("%Y-%m-%d %H:%M:%S"), secs=30.0,
              note="пустой ответ") + "\n", encoding="utf-8")
    assert daypulse.scars_block() is None


def test_scars_old_empties_do_not_count(agent, home):
    """Пустые двухдневной давности — старые раны: сутки есть сутки."""
    now = _today()
    old = (now - dt.timedelta(days=2)).strftime("%Y-%m-%d %H:%M:%S")
    config.BRAIN_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    config.BRAIN_LOG_FILE.write_text(
        _line(old, secs=30.0, note="пустой ответ") + "\n" +
        _line(old, secs=25.0, note="не-json") + "\n", encoding="utf-8")
    assert daypulse.scars_block() is None


# ---------- Ф89 пульс в зеркалах ----------

def test_status_carries_pulse(agent):
    r = agent.handle("статус")
    assert r.tool_used == "status"
    assert "тело:" in r.text                  # статус отвечает и телом


def test_self_study_knows_pulse(agent):
    r = agent.handle("изучи себя")
    assert "пульс дня" in r.text              # зеркало знает орган


def test_manifest_slim_carries_pulse_name():
    slim = manifest_slim()
    assert "пульс дня" in slim                # имя в стройном манифесте


# ---------- починка полей бухгалтерии (жук дня-13) ----------

def test_energy_reads_live_field(home):
    """Живой журнал пишет completion_tokens — энергия обязана видеть."""
    today = time.strftime("%Y-%m-%d")
    config.BRAIN_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    config.BRAIN_LOG_FILE.write_text(
        _line(today + " 10:00:00", secs=40.2, ctok=84) + "\n" +
        _line(today + " 11:00:00", secs=59.8, ctok=100) + "\n",
        encoding="utf-8")
    out = energy.render()
    assert "184 ток" in out                   # 84 + 100: живое поле прочитано
    assert "средняя генерация" in out


def test_promptweight_reads_live_field(home):
    """Истина сервера — из живого поля prompt_tokens, не из «ptok»."""
    config.BRAIN_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    config.BRAIN_LOG_FILE.write_text(
        _line("2026-11-24 12:00:00", secs=10.0, ptok=2100, ctok=84) + "\n",
        encoding="utf-8")
    out = promptweight.render()
    assert "2100" in out and "истина от сервера" in out
