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


def _cfg(tmp_path, brain="", eyes="run eyes", panel="run panel",
         ears="run ears"):
    p = tmp_path / "start_marfa.json"
    p.write_text(json.dumps({"brain_cmd": brain, "eyes_cmd": eyes,
                             "panel_cmd": panel, "ears_cmd": ears},
                            ensure_ascii=False),
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

def _run_main(monkeypatch, tmp_path, alive_ports, cfg_brain="",
              ears_alive=False, drive_alive=False):
    """main() с подменёнными швами; возвращает (код, вывод, список spawn)."""
    spawned, logged = [], []
    monkeypatch.setattr(sm, "_alive",
                        lambda port, path: port in alive_ports)
    monkeypatch.setattr(sm, "_spawn", lambda cmd: spawned.append(cmd))
    monkeypatch.setattr(sm, "_wait", lambda p, path, t, poll=2.0: True)
    monkeypatch.setattr(sm, "_log", lambda line: logged.append(line))
    monkeypatch.setattr(sm, "_ears_alive", lambda: ears_alive)
    monkeypatch.setattr(sm, "_drive_alive", lambda: drive_alive)
    cfg = _cfg(tmp_path, brain=cfg_brain)
    import io
    import contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = sm.main(["--config", str(cfg)])
    return rc, buf.getvalue(), spawned, logged


def test_main_all_alive(monkeypatch, tmp_path):
    rc, out, spawned, logged = _run_main(monkeypatch, tmp_path,
                                         {8082, 8083, 5001}, ears_alive=True,
                                         drive_alive=True)
    assert rc == 0
    assert not spawned
    assert out.count("уже жив") == 5          # мозг, глаза, панель, уши, стремление
    assert "уши: уже жив" in out
    assert "стремление: уже жив" in out
    assert logged and "уже жили" in logged[0]


def test_main_starts_eyes_only(monkeypatch, tmp_path):
    """Мозг и панель живы, глаза и уши нет — поднимаются глаза и уши."""
    rc, out, spawned, _ = _run_main(monkeypatch, tmp_path, {8082, 5001},
                                    drive_alive=True)
    assert rc == 0
    assert spawned == ["run eyes", "run ears"]
    assert "ожил" in out


def test_main_starts_drive_too(monkeypatch, tmp_path):
    """Ничего нет — поднимаются и глаза, и уши, и стремление."""
    rc, out, spawned, _ = _run_main(monkeypatch, tmp_path, set())
    assert rc == 0
    assert "run drive" not in spawned
    assert spawned[-1].endswith("core.drive --service")   # стремление пятым


def test_main_brain_without_cmd(monkeypatch, tmp_path):
    """Мозг не жив и команды нет — честная подсказка, дом не блокируется."""
    rc, out, spawned, _ = _run_main(monkeypatch, tmp_path, {8083, 5001},
                                    cfg_brain="", ears_alive=True, drive_alive=True)
    assert rc == 0
    assert not spawned                      # глаза, панель и уши уже живы
    assert "впиши" in out and "brain_cmd" in out
    assert "МОЗГ" in out


def test_main_brain_cmd_used(monkeypatch, tmp_path):
    """Мозг не жив, команда вписана — поднимается и ЖДЁТСЯ (день-8:
    старт без ожидания прятал смерть команды за «проверь позже»)."""
    rc, out, spawned, _ = _run_main(monkeypatch, tmp_path, {8083, 5001},
                                    cfg_brain="run brain", ears_alive=True, drive_alive=True)
    assert rc == 0
    assert spawned == ["run brain"]
    assert "ожил" in out


def test_main_brain_dead_says_console_and_button(monkeypatch, tmp_path):
    """День-8: мозг не ожил за ожидание — честный намёк на консоль и
    кнопку 92, а не молчаливое «проверь позже» (кавычки терапии §15
    убили сервер, а старт делал вид, что всё нормально)."""
    spawned, logged = [], []
    monkeypatch.setattr(sm, "_alive",
                        lambda port, path: port in {8083, 5001})
    monkeypatch.setattr(sm, "_spawn", lambda cmd: spawned.append(cmd))
    monkeypatch.setattr(sm, "_wait", lambda p, path, t, poll=2.0: False)
    monkeypatch.setattr(sm, "_log", lambda line: logged.append(line))
    monkeypatch.setattr(sm, "_ears_alive", lambda: True)
    monkeypatch.setattr(sm, "_drive_alive", lambda: True)
    cfg = _cfg(tmp_path, brain="run brain")
    import io
    import contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = sm.main(["--config", str(cfg)])
    out = buf.getvalue()
    assert rc == 0                       # дом поднимается и без мозга
    assert "НЕ ожил" in out
    assert "консоль мозга" in out
    assert "92_brain_fix" in out


# ---------- уши: четвёртый слуга ----------

def test_main_ears_default_for_old_config(monkeypatch, tmp_path):
    """Старый конфиг без ears_cmd — уши всё равно поднимаются (апгрейд на лету)."""
    p = tmp_path / "start_marfa.json"
    p.write_text(json.dumps({"brain_cmd": "", "eyes_cmd": "run eyes",
                             "panel_cmd": "run panel"}, ensure_ascii=False),
                 encoding="utf-8")
    spawned, logged = [], []
    monkeypatch.setattr(sm, "_alive", lambda port, path: True)
    monkeypatch.setattr(sm, "_spawn", lambda cmd: spawned.append(cmd))
    monkeypatch.setattr(sm, "_log", lambda line: logged.append(line))
    monkeypatch.setattr(sm, "_ears_alive", lambda: False)
    import io
    import contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = sm.main(["--config", str(p)])
    assert rc == 0
    assert sm.TEMPLATE["ears_cmd"] in spawned     # команда по умолчанию
    assert "службу слуха" in buf.getvalue()


def test_ears_alive_by_heartbeat(monkeypatch, tmp_path):
    """Живость ушей — по свежести сердцебиения в статус-файле."""
    import datetime as dt
    f = tmp_path / "ears_status.json"
    monkeypatch.setattr(sm, "EARS_STATUS_FILE", f)
    assert sm._ears_alive() is False               # файла нет
    fresh = {"ts": dt.datetime.now().isoformat(timespec="seconds"),
             "state": "ok"}
    f.write_text(json.dumps(fresh), encoding="utf-8")
    assert sm._ears_alive() is True                # сердце только что
    stale = {"ts": (dt.datetime.now()
                    - dt.timedelta(seconds=sm.EARS_FRESH_SECS + 10)).isoformat(),
             "state": "ok"}
    f.write_text(json.dumps(stale), encoding="utf-8")
    assert sm._ears_alive() is False               # сердце замерло
    f.write_text("не json вовсе", encoding="utf-8")
    assert sm._ears_alive() is False               # мусор в файле — не живо


# ---------- планировщик ----------

def test_register_scheduler_ok(monkeypatch):
    """Две задачи: дом при входе + синхронизация каждые 2 часа (/auto)."""
    seen = []

    class R:
        returncode = 0

    def fake_run(cmd, **k):
        seen.append(cmd)
        return R()

    monkeypatch.setattr(sm.subprocess, "run", fake_run)
    assert sm.register_scheduler() is True
    assert len(seen) == 2
    house, sync = seen
    # дом при входе в Windows
    assert "schtasks" in house[0].lower()
    assert "/SC" in house and "ONLOGON" in house and "Марфа" in house
    # петля синхронизации — сама, каждые 2 часа, без pause
    assert "/SC" in sync and "HOURLY" in sync and "/MO" in sync
    assert "Марфа-синхронизация" in sync
    assert "80_sync_github.bat" in sync[6] and "/auto" in sync[6]


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
