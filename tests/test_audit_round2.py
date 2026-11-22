# -*- coding: utf-8 -*-
"""tests/test_audit_round2.py — якоря аудита Создателя, РАУНД 2 (22.11, вечер).

Порядок фаз Создателя: (1) не терять данные, (2) не падать, (3) не врать,
(4) не висеть, (5) гигиена и контракты. Каждый фикс закреплён тестом —
правило дома: баг без якоря возвращается.

Нумерация — из аудита Создателя (K1..K7, H1..H9, M1..M12, N1..N10),
«раунд 2» — чтобы не путать с раундом 1 (test_audit_fixes.py).
"""
import datetime as dt
import json
import os
import zipfile
from pathlib import Path

import pytest

from core import config

NOW = dt.datetime(2026, 11, 22, 23, 30, 15)


@pytest.fixture()
def home(tmp_path, monkeypatch):
    """tmp-дом: пути из закона, ничего не трогаем вне его."""
    monkeypatch.setenv("MARFA_HOME", str(tmp_path))
    monkeypatch.setattr(config, "HOME_DIR", tmp_path)
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(config, "LOGS_DIR", tmp_path / "logs")
    monkeypatch.setattr(config, "QUEUE_FILE", tmp_path / "data" / "queue.json")
    monkeypatch.setattr(config, "DOCTRINE_FILE",
                        tmp_path / "data" / "creator_doctrine.json")
    monkeypatch.setattr(config, "QUESTIONS_FILE", tmp_path / "data" / "questions.json")
    monkeypatch.setattr(config, "DIARY_DIR", tmp_path / "data" / "diary")
    monkeypatch.setattr(config, "LIVE_VOICE_FILE", tmp_path / "data" / "live_voice.json")
    monkeypatch.setattr(config, "DRIVE_STATUS_FILE", tmp_path / "data" / "drive_status.json")
    monkeypatch.setattr(config, "EARS_STATUS_FILE", tmp_path / "data" / "ears_status.json")
    monkeypatch.setattr(config, "EARS_LOG_FILE", tmp_path / "logs" / "ears_log.jsonl")
    monkeypatch.setattr(config, "EVOLUTION_DIR", tmp_path / "data" / "evolution")
    config.ensure_dirs()
    yield tmp_path


# ================================================================
# ФАЗА 1 — НЕ ТЕРЯТЬ ДАННЫЕ
# ================================================================

# ---------- K1/K2: контекст ----------

def test_k2_token_estimate_empty_is_zero():
    """Пустой текст — 0 токенов: выброшенный блок не ест фантомный токен."""
    assert config.token_estimate("") == 0
    assert config.token_estimate(None if "" else "") == 0
    assert config.token_estimate("abc") >= 1


def test_k1_history_actually_in_prompt():
    """История Ф53 ВЫЧИСЛЯЛАСЬ и считалась в отчёте — но не ложилась в
    parts. Теперь она в промпте, и в отчёте честно."""
    from core.context import build_system
    history = "\n".join("Илья: сообщение %d. Марфа: ответ %d." % (i, i)
                        for i in range(40))
    prompt, rep = build_system(
        doctrine="Я — Марфа. Служу Илье.",
        state_text="RAM 30%", genome_rules=[],
        rag_memories=["что-то важное"], history_text=history)
    assert "[ИСТОРИЯ]" in prompt
    assert "сообщение 0" in prompt            # сама история — в промпте
    assert rep.level_tokens.get("L4_history", 0) > 0
    assert "L4_history" not in [d.split(":")[0] for d in rep.dropped]


def test_context_core_block_goes_first_and_respects_law():
    """H8 (подготовка): статичное ядро (личность+манифест+закон) едет
    перед доктриной, не режется, бюджет 3072 соблюдается."""
    from core.context import build_system
    core = "ЯДРО — кто я: Марфа, дом Ильи." + " статика " * 50
    prompt, rep = build_system(
        doctrine="Доктрина короткая.",
        state_text="Состояние: ок", genome_rules=[],
        rag_memories=["память"], core=core)
    assert prompt.startswith("ЯДРО")          # ядро — первым
    assert "Доктрина короткая." in prompt
    assert rep.level_tokens["L0_core"] > 0
    assert rep.prompt_tokens <= config.PROMPT_BUDGET_TOKENS


def test_context_core_too_big_is_incident():
    """Ядро+доктрина не влезают в 3072 — ЧП дома (ValueError), не молчаливое
    переполнение контекста 4096."""
    from core.context import build_system
    with pytest.raises(ValueError):
        build_system(doctrine="доктрина " * 10,
                     state_text="s", genome_rules=[],
                     core="ядро " * 4000)     # ~5300 ток — не влезает


# ---------- K3/K4/M8/M9: бэкап ----------

def _mk_soul(home):
    (home / "data" / "creator_doctrine.json").write_text(
        json.dumps({"doctrine": "дом живёт"}), encoding="utf-8")
    d = home / "data" / "diary"
    d.mkdir(parents=True, exist_ok=True)
    (d / "2026-11-22.md").write_text("# Дневник", encoding="utf-8")


def test_k3_two_backups_same_second_both_alive(home):
    """Расписание 23:30 + «сохрани себя» в ту же секунду: два архива,
    первый не обрезан вторым."""
    from core.backup import create_backup
    _mk_soul(home)
    r1 = create_backup(now=NOW)
    r2 = create_backup(now=NOW)               # та же секунда
    assert r1["path"] != r2["path"]
    assert r1["path"].exists() and r2["path"].exists()
    assert len(r1["files"]) == len(r2["files"]) and r1["files"]
    assert zipfile.is_zipfile(r1["path"]) and zipfile.is_zipfile(r2["path"])


def test_m8_symlink_not_archived(home):
    """Симлинк в data/ — дверь к 18 ГБ весов: не разворачивается, честно
    отмечается в отчёте («модели не ездят» — обещание)."""
    from core.backup import create_backup
    _mk_soul(home)
    big = home / "models_huge.gguf"
    big.write_text("18 ГБ весов тут", encoding="utf-8")
    link = home / "data" / "memory"
    link.mkdir(exist_ok=True)
    try:
        (link / "weights.gguf").symlink_to(big)
    except OSError:
        pytest.skip("нет прав на симлинк в этой системе")
    report = create_backup(now=NOW)
    assert not any("weights.gguf" in f for f in report["files"])
    with zipfile.ZipFile(report["path"]) as z:
        assert not any("weights.gguf" in n for n in z.namelist())
    assert any("симлинк" in s for s in report["skipped"])


def test_k4_unreadable_file_skipped_zip_still_valid(home, monkeypatch):
    """Один файл не читается — архив собирается ЦЕЛИКОМ, пропуск честно
    в отчёте; частичного zip на полке не остаётся."""
    from core import backup
    _mk_soul(home)
    real_write = zipfile.ZipFile.write

    def flaky_write(self, member, *a, **k):
        if "diary" in str(member):
            raise OSError("диск моргнул")
        return real_write(self, member, *a, **k)

    monkeypatch.setattr(zipfile.ZipFile, "write", flaky_write)
    report = backup.create_backup(now=NOW)
    assert report["files"]                      # доктрина вошла
    assert report["skipped"]                    # дневник — честный пропуск
    assert zipfile.is_zipfile(report["path"])   # архив валиден целиком


def test_m9_rotate_never_overwrites_trash(home):
    """В _trash/backup_old уже лежит архив с тем же именем — не перезаписываем
    (закон: ничего не удаляется насовсем), приезжает с уникальным суффиксом."""
    from core.backup import BACKUP_KEEP, _rotate
    bdir = home / "data" / "backup"
    bdir.mkdir(parents=True)
    for i in range(BACKUP_KEEP + 2):
        (bdir / ("marfa_backup_202611%02d_1200.zip" % (i + 1))).write_text(
            "старый %d" % i, encoding="utf-8")
    trash = home / "_trash" / "backup_old"
    trash.mkdir(parents=True)
    (trash / "marfa_backup_20261101_1200.zip").write_text("прежний жилец",
                                                          encoding="utf-8")
    _rotate()
    assert (trash / "marfa_backup_20261101_1200.zip").read_text(
        encoding="utf-8") == "прежний жилец"      # не затёрт
    assert len(list(trash.glob("*.zip"))) == 3    # 1 прежний + 2 переехали


# ---------- K5/K6/M3/M11: очередь и план ----------

def test_k5_add_task_ids_unique(home):
    """Две задачи в одну секунду — разные id (раньше: одна отметка
    находила только первую)."""
    from core.autonomy import add_task, load_queue
    t1 = add_task("первая")
    t2 = add_task("вторая")                    # та же секунда
    assert t1["id"] != t2["id"]
    ids = [t["id"] for t in load_queue()]
    assert len(ids) == len(set(ids))


def test_m3_save_queue_atomic(home):
    """Краш посреди записи очереди не оставляет обрезанный queue.json."""
    from core import autonomy
    autonomy.save_queue([{"id": "t1", "title": "живая", "status": "pending"}])
    good = config.QUEUE_FILE.read_text(encoding="utf-8")

    def boom(*a, **k):
        raise RuntimeError("краш на середине записи")

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(autonomy.json, "dumps", boom)
    try:
        with pytest.raises(RuntimeError):
            autonomy.save_queue([{"id": "t2", "title": "мусор"}])
    finally:
        monkeypatch.undo()
    assert config.QUEUE_FILE.read_text(encoding="utf-8") == good
    assert not (config.QUEUE_FILE.parent / "queue.tmp").exists()


def test_m11_load_queue_survives_busy_file(home, monkeypatch):
    """Файл занят антивирусом/ACL (PermissionError) — очередь пуста, дом жив."""
    from core.autonomy import load_queue
    config.QUEUE_FILE.write_text('{"tasks": []}', encoding="utf-8")

    def busy(self, *a, **k):
        raise PermissionError("файл занят другим процессом")

    monkeypatch.setattr(Path, "read_text", busy)
    assert load_queue() == []
