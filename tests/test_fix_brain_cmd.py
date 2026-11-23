# -*- coding: utf-8 -*-
"""tests/test_fix_brain_cmd.py — кнопка 92 «ремонт мозга» (день-8, 23.11).

Швы start_marfa (_alive/_spawn/_wait/_log) подменяются — реальные
порты, консоли и процессы не трогаются. Конфиг — только tmp_path.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import fix_brain_cmd as fb  # noqa: E402
import start_marfa as sm  # noqa: E402


POISONED = ('llama.cpp\\llama-server.exe -m models\\Qwen3-30B-A3B-Q4_K_M.gguf '
            '--host 127.0.0.1 --port 8082 -ngl 0 -c 8192 --temp 0.7 '
            '--top-p 0.8 --top-k 20 --repeat-penalty 1.0 --jinja '
            '--chat-template-kwargs "{\\"enable_thinking\\": false}"')


def _cfg(tmp_path, brain_cmd=POISONED):
    p = tmp_path / "start_marfa.json"
    p.write_text(json.dumps({"brain_cmd": brain_cmd,
                             "eyes_cmd": "run eyes"}, ensure_ascii=False),
                 encoding="utf-8")
    return p


# ---------- лечение конфига ----------

def test_button_heals_poisoned_config(tmp_path, monkeypatch, capsys):
    """Ядовитая команда (кавычки §15) лечится, честное «было/стало»
    — на экране: Создатель видит, что именно поменялось."""
    monkeypatch.setattr(sm, "_log", lambda line: None)
    p = _cfg(tmp_path)
    rc = fb.main(["--config", str(p)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "было:" in out and "стало:" in out
    healed = json.loads(p.read_text(encoding="utf-8"))["brain_cmd"]
    assert '"' not in healed and "--jinja" not in healed


def test_button_healthy_config_idempotent(tmp_path, capsys):
    """Здоровая команда — не трогается: сколько угодно нажатий, вреда
    нет (закон кнопок дома, 85_fix_ears)."""
    p = _cfg(tmp_path, brain_cmd=sm.TEMPLATE["brain_cmd"])
    rc = fb.main(["--config", str(p)])
    assert rc == 0
    assert "здорова" in capsys.readouterr().out
    assert json.loads(p.read_text(encoding="utf-8"))["brain_cmd"] \
        == sm.TEMPLATE["brain_cmd"]


def test_button_creates_missing_config(tmp_path, monkeypatch, capsys):
    """Конфига нет — создаётся шаблон со здоровой командой (первый
    запуск на новой машине не должен рождать бомбу)."""
    monkeypatch.setattr(sm, "_log", lambda line: None)
    p = tmp_path / "start_marfa.json"
    rc = fb.main(["--config", str(p)])
    assert rc == 0
    cfg = json.loads(p.read_text(encoding="utf-8"))
    assert '"' not in cfg["brain_cmd"]


# ---------- подъём мозга ----------

def test_button_starts_dead_brain(tmp_path, monkeypatch, capsys):
    """Мозг не жив — поднимается в отдельной консоли и «оживает»
    (шов _wait подменён: реального llama-server в песочнице нет)."""
    monkeypatch.setattr(sm, "_log", lambda line: None)
    spawned = []
    monkeypatch.setattr(sm, "_alive", lambda port, path: False)
    monkeypatch.setattr(sm, "_spawn", lambda cmd: spawned.append(cmd))
    monkeypatch.setattr(sm, "_wait", lambda p, path, t, poll=2.0: True)
    p = _cfg(tmp_path)
    rc = fb.main(["--config", str(p), "--start"])
    assert rc == 0
    assert spawned and '""' not in spawned[0]      # команда без кавычек
    assert "ОЖИЛ" in capsys.readouterr().out


def test_button_alive_brain_not_touched(tmp_path, monkeypatch, capsys):
    """Живой мозг не перезапускается (закон старта дома) — кнопка
    честно говорит «не трогаю»."""
    monkeypatch.setattr(sm, "_log", lambda line: None)
    spawned = []
    monkeypatch.setattr(sm, "_alive", lambda port, path: True)
    monkeypatch.setattr(sm, "_spawn", lambda cmd: spawned.append(cmd))
    p = _cfg(tmp_path)
    rc = fb.main(["--config", str(p), "--start"])
    assert rc == 0
    assert not spawned
    assert "не трогаю" in capsys.readouterr().out


def test_button_dead_brain_honest_failure(tmp_path, monkeypatch, capsys):
    """Не ожил за 120 с — честный отказ с путём лечения (консоль
    мозга, карточка «Мозг»), код 1: кнопка не врёт успехом."""
    monkeypatch.setattr(sm, "_log", lambda line: None)
    monkeypatch.setattr(sm, "_alive", lambda port, path: False)
    monkeypatch.setattr(sm, "_spawn", lambda cmd: None)
    monkeypatch.setattr(sm, "_wait", lambda p, path, t, poll=2.0: False)
    p = _cfg(tmp_path)
    rc = fb.main(["--config", str(p), "--start"])
    assert rc == 1
    out = capsys.readouterr().out
    assert "НЕ ожил" in out and "консоль" in out


def test_button_no_start_flag_only_heals(tmp_path, monkeypatch):
    """Без --start кнопка только лечит конфиг (старт — отдельная
    воля: лечение и подъём не срослись в принуждение)."""
    monkeypatch.setattr(sm, "_log", lambda line: None)
    spawned = []
    monkeypatch.setattr(sm, "_spawn", lambda cmd: spawned.append(cmd))
    p = _cfg(tmp_path)
    rc = fb.main(["--config", str(p)])
    assert rc == 0
    assert not spawned
