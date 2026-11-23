# -*- coding: utf-8 -*-
"""tests/test_quiet.py — №27 роадмапа 30: «тихий час».

«Тишина» — лог панели режется до ошибок. Контракт:

  - «тишина» — уровень werkzeug-логгера ERROR (access-строки
    «GET /api/progress 200» молчат, ошибки слышны), резолюция в
    data/quiet.json;
  - «не тишина» возвращает INFO;
  - резолюция переживает рестарт панели: apply_saved читает файл
    на старте (web/app зовёт);
  - битый файл / нет файла — дом ГОВОРИТ: тишина без воли Создателя —
    не тишина, а сбой;
  - команды агента не будят мозг.
"""
import json
import logging
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import agent, config, quiet  # noqa: E402


@pytest.fixture()
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("MARFA_HOME", str(tmp_path))
    monkeypatch.setattr(config, "HOME_DIR", tmp_path)
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(config, "QUIET_FILE", tmp_path / "data" / "quiet.json")
    # логгер — глобальный: восстанавливаем уровень после теста
    lg = logging.getLogger(quiet.PANEL_LOGGER)
    saved = lg.level
    yield tmp_path
    lg.setLevel(saved)


def _agent():
    class FakeBrain:
        calls = 0

        def ask_json(self, *a, **kw):
            self.calls += 1
            return {"answer": "мозг"}

    class FakeMemory:
        def recall(self, *a, **kw):
            return []

    return agent.Agent(brain=FakeBrain(), memory=FakeMemory())


def _level() -> int:
    return logging.getLogger(quiet.PANEL_LOGGER).level


# ---------- орган ----------

def test_set_quiet_cuts_access_log(home):
    r = quiet.set_quiet(True)
    assert _level() == logging.ERROR
    assert "Тихий час" in r and "не тишина" in r
    rec = json.loads((home / "data" / "quiet.json").read_text(encoding="utf-8"))
    assert rec["quiet"] is True


def test_set_loud_returns(home):
    quiet.set_quiet(True)
    r = quiet.set_quiet(False)
    assert _level() == logging.INFO
    assert "Говорю снова" in r
    rec = json.loads((home / "data" / "quiet.json").read_text(encoding="utf-8"))
    assert rec["quiet"] is False


def test_apply_saved_honors_resolution(home):
    """Рестарт панели: apply_saved читает волю из файла, а не из
    логгера (уровень — следствие воли, не наоборот)."""
    (home / "data").mkdir(parents=True, exist_ok=True)
    (home / "data" / "quiet.json").write_text(
        json.dumps({"quiet": True}), encoding="utf-8")
    logging.getLogger(quiet.PANEL_LOGGER).setLevel(logging.INFO)
    assert quiet.apply_saved() is True
    assert _level() == logging.ERROR


def test_apply_saved_no_file_is_loud(home):
    """Файла нет — дом говорит: тишина без воли Создателя — сбой."""
    logging.getLogger(quiet.PANEL_LOGGER).setLevel(logging.ERROR)
    assert quiet.apply_saved() is False
    assert _level() == logging.INFO


def test_apply_saved_broken_file_is_loud(home):
    (home / "data").mkdir(parents=True, exist_ok=True)
    (home / "data" / "quiet.json").write_text("{битый json", encoding="utf-8")
    assert quiet.apply_saved() is False
    assert _level() == logging.INFO


def test_is_quiet_false_without_file(home):
    assert quiet.is_quiet() is False


# ---------- команды агента ----------

def test_agent_command_quiet_and_loud(home):
    a = _agent()
    for msg in ("тишина", "тихий час?", "замолчи лог"):
        r = a.handle(msg)
        assert r.tool_used == "quiet", msg
        assert "Тихий час" in r.text
        assert a.brain.calls == 0, msg
    assert _level() == logging.ERROR
    for msg in ("не тишина", "громко", "можно говорить"):
        r = a.handle(msg)
        assert r.tool_used == "quiet", msg
        assert "Говорю снова" in r.text
        assert a.brain.calls == 0, msg
    assert _level() == logging.INFO


def test_agent_quiet_crash_falls_to_brain(home, monkeypatch):
    """Броня №4 р3: орган упал — чат жив, говорит мозг."""
    def boom(on):
        raise RuntimeError("логгер закапризничал")

    monkeypatch.setattr(quiet, "set_quiet", boom)
    a = _agent()
    r = a.handle("тишина")
    assert r.source == "brain" and a.brain.calls == 1


def test_panel_import_applies_saved(home, monkeypatch):
    """web/app зовёт apply_saved на старте: резолюция доживает до
    рестарта панели (импорт модуля — тот же рестарт в миниатюре).

    Герметичность батареи: web.app к этому моменту мог импортировать
    сосед сверху (test_monitor_web) — обычный import стал бы no-op и
    «рестарт» не случился бы. reload честно переисполняет модуль,
    как настоящий перезапуск панели."""
    (home / "data").mkdir(parents=True, exist_ok=True)
    (home / "data" / "quiet.json").write_text(
        json.dumps({"quiet": True}), encoding="utf-8")
    logging.getLogger(quiet.PANEL_LOGGER).setLevel(logging.INFO)
    import importlib
    import web.app as web_app          # noqa: F401 — был импортирован или нет
    importlib.reload(web_app)          # «рестарт панели» даже при кэше
    assert _level() == logging.ERROR
