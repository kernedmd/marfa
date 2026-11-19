# -*- coding: utf-8 -*-
"""Тесты памяти (ТЗ 3.4, ADR-006): remember/recall/forget, дедуп, TTL, связи.

В песочнице chromadb не установлен — все тесты идут через JSON-фоллбэк,
что само по себе проверяет ADR-006. На Z440 с chromadb интерфейс тот же.
"""
import pytest

from core import config
from core.memory import Memory


@pytest.fixture()
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("MARFA_HOME", str(tmp_path))
    monkeypatch.setattr(config, "HOME_DIR", tmp_path)
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(config, "GUARD_LOG_FILE", tmp_path / "logs" / "guard_log.jsonl")
    config.ensure_dirs()
    yield tmp_path


@pytest.fixture()
def mem(home):
    return Memory(data_dir=home / "data")


def test_remember_and_recall(mem):
    mem.remember("Квант мозга Q4_K_M даёт 8-16 ток/с на DDR4", tags=["мозг"])
    got = mem.recall("какой квант мозга по умолчанию")
    assert got and "Q4_K_M" in got[0]["text"]


def test_recall_empty_memory(mem):
    assert mem.recall("что угодно") == []


def test_dedup_same_text_updates(mem):
    """Дедуп: тот же текст не плодит копии, а обновляет запись."""
    a = mem.remember("Гит-страж блокирует коммиты с секретами", importance=2)
    b = mem.remember("Гит-страж блокирует коммиты с секретами!", importance=4)
    assert a["id"] == b["id"]
    assert b["importance"] == 4
    assert len(mem._records()) == 1


def test_ttl_expired_for_gotten(mem):
    mem.remember("временное", ttl_hours=0)
    # память не двигает часы, но сборка мусора обязана почистить
    assert mem.forget_expired() == 1
    assert mem.recall("временное") == []


def test_ttl_alive(mem):
    mem.remember("живое", ttl_hours=48)
    assert mem.forget_expired() == 0


def test_forget_by_id(mem):
    rec = mem.remember("забудь меня")
    assert mem.forget(rec["id"]) is True
    assert mem.recall("забудь") == []
    assert mem.forget("несуществующий_id") is False


def test_links_bidirectional(mem):
    a = mem.remember("Ф51 иерархический контекст")
    b = mem.remember("Ф53 сжатие истории")
    assert mem.link(a["id"], b["id"]) is True
    rec_a = next(r for r in mem._records() if r["id"] == a["id"])
    rec_b = next(r for r in mem._records() if r["id"] == b["id"])
    assert b["id"] in rec_a["links"]
    assert a["id"] in rec_b["links"]
    assert mem.link(a["id"], "нет_такого") is False


def test_importance_boosts_recall(mem):
    mem.remember("редкая деталь: порт веб-панели 5001", importance=5)
    mem.remember("частая болтовня про погоду и настроение", importance=0.5)
    got = mem.recall("веб панель порт")
    assert got and "5001" in got[0]["text"]


def test_remember_empty_rejected(mem):
    with pytest.raises(ValueError):
        mem.remember("   ")
