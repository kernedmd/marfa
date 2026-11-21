# -*- coding: utf-8 -*-
r"""tests/test_backup.py — №23 «сохрани себя»: бэкап души дома.

Душа — доктрина, память, дневники, разговоры, уроки, резолюция живого
языка. Тело (модели, venv, логи) не ездит. Ротация: 14 свежих живут,
старшие — в _trash/backup_old, ничего не удаляется насовсем.
"""
import datetime as dt
import json
import zipfile

import pytest

from core import config
from core.backup import BACKUP_KEEP, create_backup, render, tick

NOW = dt.datetime(2026, 11, 21, 23, 30)


@pytest.fixture()
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("MARFA_HOME", str(tmp_path))
    monkeypatch.setattr(config, "HOME_DIR", tmp_path)
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(config, "DOCTRINE_FILE",
                        tmp_path / "data" / "creator_doctrine.json")
    monkeypatch.setattr(config, "QUESTIONS_FILE",
                        tmp_path / "data" / "questions.json")
    monkeypatch.setattr(config, "DIARY_DIR", tmp_path / "data" / "diary")
    monkeypatch.setattr(config, "LIVE_VOICE_FILE",
                        tmp_path / "data" / "live_voice.json")
    config.ensure_dirs()
    yield tmp_path


def _mk_soul(home):
    (home / "data" / "creator_doctrine.json").write_text(
        json.dumps({"doctrine": "дом живёт"}, ensure_ascii=False),
        encoding="utf-8")
    d = home / "data" / "diary"
    d.mkdir(parents=True, exist_ok=True)
    (d / "2026-11-21.md").write_text("# Дневник\nТихий день.",
                                      encoding="utf-8")
    (home / "data" / "live_voice.json").write_text(
        json.dumps({"enabled": True}), encoding="utf-8")


def test_backup_zip_holds_the_soul(home):
    _mk_soul(home)
    report = create_backup(now=NOW)
    assert report["path"].exists()
    assert report["size"] > 0
    assert "data\\creator_doctrine.json" in report["files"] or \
           "data/creator_doctrine.json" in report["files"]
    assert any("2026-11-21.md" in f for f in report["files"])
    with zipfile.ZipFile(report["path"]) as z:
        names = z.namelist()
    assert any("live_voice.json" in n for n in names)
    assert "доктрина Создателя" not in report["missing"]


def test_backup_missing_reported_honestly(home):
    report = create_backup(now=NOW)          # пустой дом
    assert report["files"] == []
    assert "доктрина Создателя" in report["missing"]
    text = render(report)
    assert "не было" in text and "доктрина" in text


def test_rotation_keeps_14_moves_rest_to_trash(home):
    _mk_soul(home)
    bdir = home / "data" / "backup"
    bdir.mkdir(parents=True, exist_ok=True)
    for i in range(BACKUP_KEEP + 3):         # 17 старых архивов
        (bdir / ("marfa_backup_202611%02d_1200.zip" % (i + 1))).write_text(
            "старый", encoding="utf-8")
    create_backup(now=NOW)                   # +1 новый = 18
    kept = list(bdir.glob("marfa_backup_*.zip"))
    trash = list((home / "_trash" / "backup_old").glob("*.zip"))
    assert len(kept) == BACKUP_KEEP
    assert len(trash) == 4                    # 18 - 14: не насовсем, в _trash


def test_agent_command_save_yourself(home):
    from core.agent import Agent
    _mk_soul(home)
    r = Agent(brain=None, memory=None, doctrine="").handle("сохрани себя")
    assert r.source == "python" and r.tool_used == "backup"
    assert "Сохранила себя" in r.text
    assert (home / "data" / "backup").exists()


def test_backup_job_in_schedule():
    from core.schedule import default_jobs
    jobs = {j["id"]: j for j in default_jobs()}
    assert jobs["backup"]["kind"] == "daily"
    assert jobs["backup"]["at"] == "23:30"    # после вечернего дневника


def test_tick_reports_numbers(home):
    _mk_soul(home)
    note = tick()
    assert "бэкап:" in note and "КБ" in note
