# -*- coding: utf-8 -*-
"""tests/test_start_marfa.py — №22: автозапуск дома одной командой.

Швы _alive / _spawn / _wait / _log / subprocess.run подменяются —
реальные порты, консоли и планировщик не трогаются.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import start_marfa as sm  # noqa: E402


def _cfg(tmp_path, brain="", eyes="run eyes", panel="run panel"):
    p = tmp_path / "start_marfa.json"
    p.write_text(json.dumps({"brain_cmd": brain, "eyes_cmd": eyes,
                             "panel_cmd": panel}, ensure_ascii=False),
                 encoding="utf-8")
    return p


# ---------- конфиг ----------

def test_ensure_config_creates_template(tmp_path):
    p = tmp_path / "start_marfa.json"
    cfg = sm.ensure_config(p)
    assert p.exists()
    # шаблон = живые команды Создателя (Старт_Марфа.bat от 17.11.2026)
    assert "llama-server" in cfg["brain_cmd"] and "--port 8082" in cfg["brain_cmd"]
    assert "--port 8083" in cfg["eyes_cmd"] and "models\\vlm\\" in cfg["eyes_cmd"]
    assert "web" in cfg["panel_cmd"] and "5001" in cfg["panel_cmd"]


def test_ensure_config_keeps_existing(tmp_path):
    p = _cfg(tmp_path, brain="моя команда мозга")
    cfg = sm.ensure_config(p)
    assert cfg["brain_cmd"] == "моя команда мозга"


# ---------- _wait ----------

def test_wait_alive_after_poll(monkeypatch):
    states = iter([False, True])

    def flaky(port, path):
        return next(states)

    monkeypatch.setattr(sm, "_alive", flaky)
    monkeypatch.setattr(sm.time, "sleep", lambda s: None)
    assert sm._wait(8083, "/health", 90) is True


def test_wait_timeout(monkeypatch):
    monkeypatch.setattr(sm, "_alive", lambda port, path: False)
    monkeypatch.setattr(sm.time, "sleep", lambda s: None)
    assert sm._wait(8083, "/health", 0.05) is False


# ---------- main ----------

def _run_main(monkeypatch, tmp_path, alive_ports, cfg_brain=""):
    """main() с подменёнными швами; возвращает (код, вывод, список spawn)."""
    spawned, logged = [], []
    monkeypatch.setattr(sm, "_alive",
                        lambda port, path: port in alive_ports)
    monkeypatch.setattr(sm, "_spawn", lambda cmd: spawned.append(cmd))
    monkeypatch.setattr(sm, "_wait", lambda p, path, t, poll=2.0: True)
    monkeypatch.setattr(sm, "_log", lambda line: logged.append(line))
    cfg = _cfg(tmp_path, brain=cfg_brain)
    import io
    import contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = sm.main(["--config", str(cfg)])
    return rc, buf.getvalue(), spawned, logged


def test_main_all_alive(monkeypatch, tmp_path):
    rc, out, spawned, logged = _run_main(monkeypatch, tmp_path,
                                         {8082, 8083, 5001})
    assert rc == 0
    assert not spawned
    assert out.count("уже жив") == 3
    assert logged and "уже жили" in logged[0]


def test_main_starts_eyes_only(monkeypatch, tmp_path):
    """Мозг и панель живы, глаза нет — поднимаются только глаза."""
    rc, out, spawned, _ = _run_main(monkeypatch, tmp_path, {8082, 5001})
    assert rc == 0
    assert spawned == ["run eyes"]
    assert "ожил" in out


def test_main_brain_without_cmd(monkeypatch, tmp_path):
    """Мозг не жив и команды нет — честная подсказка, дом не блокируется."""
    rc, out, spawned, _ = _run_main(monkeypatch, tmp_path, {8083, 5001},
                                    cfg_brain="")
    assert rc == 0
    assert not spawned                      # глаза и панель уже живы
    assert "впиши" in out and "brain_cmd" in out
    assert "МОЗГ" in out


def test_main_brain_cmd_used(monkeypatch, tmp_path):
    """Мозг не жив, команда вписана — поднимается и не ждётся (CPU)."""
    rc, out, spawned, _ = _run_main(monkeypatch, tmp_path, {8083, 5001},
                                    cfg_brain="run brain")
    assert rc == 0
    assert "run brain" in spawned
    assert "разогревается" in out


# ---------- планировщик ----------

def test_register_scheduler_ok(monkeypatch):
    seen = []

    class R:
        returncode = 0

    def fake_run(cmd, **k):
        seen.append(cmd)
        return R()

    monkeypatch.setattr(sm.subprocess, "run", fake_run)
    assert sm.register_scheduler() is True
    assert seen[0][0].lower().endswith("schtasks") or "schtasks" in seen[0][0].lower()
    assert "/SC" in seen[0] and "ONLOGON" in seen[0]
    assert "Марфа" in seen[0]


def test_register_scheduler_fail(monkeypatch):
    class R:
        returncode = 1

    monkeypatch.setattr(sm.subprocess, "run",
                        lambda cmd, **k: R())
    assert sm.register_scheduler() is False


def test_scheduler_flag_calls_register(monkeypatch):
    called = []
    monkeypatch.setattr(sm, "register_scheduler",
                        lambda: (called.append(1) or True))
    monkeypatch.setattr(sm, "_log", lambda line: None)
    import contextlib
    import io
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = sm.main(["--в-планировщик"])
    assert rc == 0 and called and "автозагрузку" in buf.getvalue()
