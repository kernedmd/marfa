# -*- coding: utf-8 -*-
"""Тесты Ф81 «аудит логов»: цепочка целая / подмена / удаление / вставка."""
import json

import pytest

from core import config
from safety import guard
from safety.log_audit import audit, print_report


@pytest.fixture()
def log_path(tmp_path):
    return tmp_path / "logs" / "guard_log.jsonl"


def _write_chain(path, levels):
    """Честная цепочка через GuardLog (тот же код, что в работе)."""
    gl = guard.GuardLog(path)
    for lvl in levels:
        gl.append(lvl, "test.rule", f"событие уровня {lvl}")
    return gl


def test_clean_chain_ok(log_path):
    _write_chain(log_path, ["LOW", "MEDIUM", "HIGH"])
    rep = audit(log_path)
    assert rep["verdict"] == "OK"
    assert rep["total"] == 3
    assert rep["by_level"] == {"LOW": 1, "MEDIUM": 1, "HIGH": 1}
    assert rep["broken_at"] is None


def test_empty_log_ok(log_path):
    rep = audit(log_path)  # файла нет
    assert rep["verdict"] == "OK" and rep["total"] == 0


def test_tampered_entry_detected(log_path):
    """Подмена уровня в середине цепочки — разрыв виден."""
    _write_chain(log_path, ["LOW", "LOW", "LOW", "LOW"])
    lines = log_path.read_text(encoding="utf-8").splitlines()
    rec = json.loads(lines[2])
    rec["level"] = "BANNED"              # задним числом «улучшаем» историю
    lines[2] = json.dumps(rec, ensure_ascii=False, sort_keys=True)
    log_path.write_text("\n".join(lines), encoding="utf-8")
    rep = audit(log_path)
    assert rep["verdict"] == "TAMPERED"
    assert rep["broken_at"] == 2


def test_deleted_entry_detected(log_path):
    """Удаление записи ломает цепочку хвоста."""
    _write_chain(log_path, ["LOW", "HIGH", "LOW"])
    lines = log_path.read_text(encoding="utf-8").splitlines()
    del lines[1]                          # прячем HIGH-событие
    log_path.write_text("\n".join(lines), encoding="utf-8")
    rep = audit(log_path)
    assert rep["verdict"] == "TAMPERED"
    assert rep["broken_at"] is not None


def test_inserted_entry_detected(log_path):
    """Вставка чужой записи между настоящими — разрыв со вставленной позиции."""
    _write_chain(log_path, ["LOW", "LOW"])
    lines = log_path.read_text(encoding="utf-8").splitlines()
    fake = {"ts": 1.0, "level": "LOW", "rule": "fake", "reason": "вставлено вручную"}
    lines.insert(1, json.dumps(fake, ensure_ascii=False, sort_keys=True))
    log_path.write_text("\n".join(lines), encoding="utf-8")
    rep = audit(log_path)
    assert rep["verdict"] == "TAMPERED"


def test_report_text_readable(log_path):
    _write_chain(log_path, ["LOW"])
    rep = audit(log_path)
    text = print_report(rep)
    assert "OK" in text and "Записей: 1" in text
    rec_tampered = dict(rep, verdict="TAMPERED", broken_at=0)
    assert "TAMPERED" in print_report(rec_tampered)


def test_audit_reads_work_log(log_path, tmp_path, monkeypatch):
    """Аудит того же лога, куда реальный СТРАЖ пишет вердикты."""
    monkeypatch.setattr(guard, "_LOG", None)
    monkeypatch.setattr(config, "GUARD_LOG_FILE", log_path)
    guard.decide(guard.Verdict("LOW", "allow", "чисто", "t.ok"))
    with pytest.raises(PermissionError):
        guard.enforce(guard.Verdict("HIGH", "deny", "вне дома", "t.bad"))
    rep = audit(log_path)
    assert rep["verdict"] == "OK" and rep["total"] == 2
