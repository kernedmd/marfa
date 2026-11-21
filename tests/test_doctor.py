# -*- coding: utf-8 -*-
r"""tests/test_doctor.py — №21 «доктор дома»: осмотр, лечение, автолечение.

Честность конструкции:
- осмотр ничего не трогает и не выдумывает: мёртвый порт — факт;
- .env проверяется на существование, значения НЕ читаются;
- лечение — только командами из start_marfa.json; нет конфига — лечить
  нечем, и доктор так и говорит;
- автолечение лечит слугу, мёртвого ДВА осмотра подряд, и не чаще
  раза в 30 минут: разгружающийся мозг спавнами не дёргаем.
"""
import datetime as dt
import json

import pytest

from core import config, doctor

NOW = dt.datetime(2026, 11, 21, 15, 0)


@pytest.fixture()
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("MARFA_HOME", str(tmp_path))
    monkeypatch.setattr(config, "HOME_DIR", tmp_path)
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(config, "LOGS_DIR", tmp_path / "logs")
    monkeypatch.setattr(config, "MODELS_DIR", tmp_path / "models")
    monkeypatch.setattr(config, "EARS_STATUS_FILE",
                        tmp_path / "data" / "ears_status.json")
    monkeypatch.setattr(config, "DRIVE_STATUS_FILE",
                        tmp_path / "data" / "drive_status.json")
    monkeypatch.setattr(config, "DOCTOR_STATE_FILE",
                        tmp_path / "data" / "doctor_state.json")
    monkeypatch.setattr(config, "EVOLUTION_DIR",
                        tmp_path / "data" / "evolution")
    monkeypatch.setattr(config, "BRAIN_URL", "http://127.0.0.1:1")
    monkeypatch.setattr(doctor, "START_CONFIG_FILE", tmp_path / "start_marfa.json")
    config.ensure_dirs()
    yield tmp_path


def _beat(path, age_secs=0):
    path.parent.mkdir(parents=True, exist_ok=True)
    ts = (dt.datetime.now() - dt.timedelta(seconds=age_secs)).isoformat(
        timespec="seconds")
    path.write_text(json.dumps({"ts": ts}), encoding="utf-8")


# ---------- осмотр ----------

def test_check_all_dead_ports_seen_honestly(home, monkeypatch):
    # Урок станции 21.11: порты — достояние МАШИНЫ, не теста. На живом
    # доме панель реально отвечает (и это хорошо) — тест «все мертвы»
    # не имеет права надеяться на глухую машину архитектора.
    monkeypatch.setattr(doctor, "_http_ok", lambda url: False)
    report = doctor.check_all(now=NOW)
    assert report["ok"] is False
    assert report["checks"]["brain"]["ok"] is False
    assert report["checks"]["panel"]["ok"] is False
    assert report["checks"]["drive"]["ok"] is False     # сердца ещё нет
    assert report["checks"]["eyes"]["ok"] is False


def test_check_all_healthy(home, monkeypatch):
    monkeypatch.setattr(doctor, "_http_ok", lambda url: True)
    _beat(config.EARS_STATUS_FILE)
    _beat(config.DRIVE_STATUS_FILE)
    (tmp := home / "venv" / "Scripts").mkdir(parents=True)
    (tmp / "python.exe").write_text("", encoding="utf-8")
    (home / ".env").write_text("MARFA_SECRET=тихо\n", encoding="utf-8")

    class _Disk:  # диск — про Z440, не про машину тестов
        def __init__(self, free_gb):
            self.free = int(free_gb * 2**30)
        total = property(lambda self: 500 * 2**30)
        used = property(lambda self: 100 * 2**30)

    monkeypatch.setattr(doctor.shutil, "disk_usage",
                        lambda path: _Disk(120.0))
    report = doctor.check_all(now=NOW)
    assert report["ok"] is True
    assert report["checks"]["ears"]["ok"] is True
    assert report["checks"]["venv"]["ok"] is True
    assert report["checks"]["env"]["ok"] is True
    assert "свободно 120.0 ГБ" in report["checks"]["disk"]["note"]


def test_env_values_never_leak(home, monkeypatch):
    """Секрет из .env не попадает в отчёт: доктор смотрит, не читает."""
    monkeypatch.setattr(doctor, "_http_ok", lambda url: True)
    _beat(config.EARS_STATUS_FILE)
    _beat(config.DRIVE_STATUS_FILE)
    (home / ".env").write_text("MARFA_SECRET=секретно-слово\n", encoding="utf-8")
    blob = json.dumps(doctor.check_all(now=NOW), ensure_ascii=False)
    assert "секретно-слово" not in blob
    assert "не читаю" in blob


def test_render_is_plain_language(home):
    text = doctor.render(doctor.check_all(now=NOW))
    assert "ДОКТОР ДОМА" in text
    assert "мозг 8082" in text
    assert "Вердикт:" in text


# ---------- лечение ----------

def _mk_start_config(home):
    home.joinpath("start_marfa.json").write_text(json.dumps({
        "brain_cmd": "run brain", "eyes_cmd": "run eyes",
        "panel_cmd": "run panel", "ears_cmd": "run ears",
        "drive_cmd": "run drive"}, ensure_ascii=False), encoding="utf-8")


def test_heal_spawns_start_commands(home, monkeypatch):
    _mk_start_config(home)
    spawned = []
    monkeypatch.setattr(doctor, "_spawn", lambda cmd: spawned.append(cmd))
    actions = doctor.heal(["panel"])
    assert spawned == ["run panel"]
    assert any("панель" in a for a in actions)


def test_heal_without_config_is_honest(home, monkeypatch):
    spawned = []
    monkeypatch.setattr(doctor, "_spawn", lambda cmd: spawned.append(cmd))
    actions = doctor.heal(["brain"])
    assert spawned == []
    assert any("нечем" in a for a in actions)


# ---------- автолечение ----------

def test_tick_auto_first_sight_marks_but_not_heals(home, monkeypatch):
    _mk_start_config(home)
    # порты — машины, не теста (урок станции: панель была жива в 19:36)
    monkeypatch.setattr(doctor, "_http_ok", lambda url: False)
    spawned = []
    monkeypatch.setattr(doctor, "_spawn", lambda cmd: spawned.append(cmd))
    note = doctor.tick_auto(now=NOW)
    assert spawned == []                        # первый осмотр: сначала убедимся
    state = json.loads(config.DOCTOR_STATE_FILE.read_text(encoding="utf-8"))
    assert "panel" in state["seen_dead"]
    assert "мёртвые" in note


def test_tick_auto_second_sight_heals(home, monkeypatch):
    _mk_start_config(home)
    spawned = []
    monkeypatch.setattr(doctor, "_spawn", lambda cmd: spawned.append(cmd))
    doctor.tick_auto(now=NOW)
    note = doctor.tick_auto(now=NOW + dt.timedelta(minutes=6))
    assert spawned, "мёртвый два осмотра подряд — поднимаю"
    assert "поднято" in note


def test_tick_auto_alive_resets_seen_dead(home, monkeypatch):
    _mk_start_config(home)
    spawned = []
    monkeypatch.setattr(doctor, "_spawn", lambda cmd: spawned.append(cmd))
    doctor.tick_auto(now=NOW)
    monkeypatch.setattr(doctor, "_http_ok", lambda url: True)
    _beat(config.EARS_STATUS_FILE)
    _beat(config.DRIVE_STATUS_FILE)
    doctor.tick_auto(now=NOW + dt.timedelta(minutes=6))
    state = json.loads(config.DOCTOR_STATE_FILE.read_text(encoding="utf-8"))
    assert "panel" not in state["seen_dead"]
    assert spawned == []


def test_tick_auto_respects_heal_interval(home, monkeypatch):
    _mk_start_config(home)
    spawned = []
    monkeypatch.setattr(doctor, "_spawn", lambda cmd: spawned.append(cmd))
    doctor.tick_auto(now=NOW)
    doctor.tick_auto(now=NOW + dt.timedelta(minutes=6))     # лечит
    n = len(spawned)
    state = json.loads(config.DOCTOR_STATE_FILE.read_text(encoding="utf-8"))
    assert state["healed"]
    doctor.tick_auto(now=NOW + dt.timedelta(minutes=12))    # снова мёртв
    doctor.tick_auto(now=NOW + dt.timedelta(minutes=18))    # но недавно лечили
    assert len(spawned) == n, "не чаще раза в 30 минут на слугу"


def test_tick_auto_drive_self_check_waits_heartbeat(home):
    """Сердце стремления пишет сам тик — автодоктор внутри тика видит
    прошлый такт (<= 180 c назад) и не считает службу мёртвой."""
    _beat(config.DRIVE_STATUS_FILE, age_secs=60)
    report = doctor.check_all()
    assert report["checks"]["drive"]["ok"] is True


# ---------- агент и кнопка ----------

def test_agent_command_doctor(home, monkeypatch):
    from core.agent import Agent

    class NoBrain:
        def ask_json(self, *a, **k):  # noqa: ANN002, ANN003
            raise AssertionError("осмотр — без мозга")

    r = Agent(brain=NoBrain(), memory=None, doctrine="").handle("доктор")
    assert r.source == "python" and r.tool_used == "doctor"
    assert "мозг 8082" in r.text
    r2 = Agent(brain=NoBrain(), memory=None, doctrine="").handle("осмотри дом")
    assert r2.tool_used == "doctor"


def test_doctor_job_registered_in_schedule():
    from core.schedule import default_jobs
    jobs = {j["id"]: j for j in default_jobs()}
    assert "doctor" in jobs
    assert jobs["doctor"]["kind"] == "interval"
    assert jobs["doctor"]["every"] == doctor.AUTO_INTERVAL_SECS


def test_button_84_exists_and_honest():
    from pathlib import Path
    bat = Path(__file__).resolve().parents[1] / "scripts" / "84_doctor.bat"
    assert bat.is_file()
    t = bat.read_text(encoding="utf-8")
    assert "marfa_doctor.py" in t
    assert "--heal" in t
    assert "if not exist scripts\\marfa_doctor.py" in t   # файл может ехать в bundle
    assert "BTN_VER 84.1" in t
    assert "pause" in t


def test_cli_main_renders_report(home, capsys):
    import importlib.util
    from pathlib import Path
    script = (Path(__file__).resolve().parents[1] / "scripts"
              / "marfa_doctor.py")
    spec = importlib.util.spec_from_file_location("marfa_doctor_cli", script)
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    assert cli.main([]) == 0                    # осмотр без лечения — без input
    out = capsys.readouterr().out
    assert "ДОКТОР ДОМА" in out
    assert "Вердикт:" in out
