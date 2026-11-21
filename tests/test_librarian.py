# -*- coding: utf-8 -*-
"""Тесты библиотекаря v0 (Круг Д): Марфа читает дом.

Полка — docs/*.md и README. Один тик — один файл (дёшево). Куски —
в память с тегом «библиотека» (сжатие №7 их не трогает). Изменился
файл — перечитывается. LLM нет: слова Создателя едут дословно.
"""
import os

import pytest

from core import config
from core.agent import Agent
from core.librarian import Librarian, chunk_text, library_files
from core.memory import Memory


@pytest.fixture()
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("MARFA_HOME", str(tmp_path))
    monkeypatch.setattr(config, "HOME_DIR", tmp_path)
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(config, "LIBRARIAN_STATE_FILE", tmp_path / "data" / "librarian_state.json")
    config.ensure_dirs()
    (tmp_path / "docs").mkdir(exist_ok=True)
    yield tmp_path


# ---------- механика кусков ----------

def test_chunk_merges_paragraphs():
    chunks = chunk_text("абзац один.\n\nабзац два.\n\nабзац три.")
    assert len(chunks) == 1 and "абзац один" in chunks[0]


def test_chunk_splits_long_text():
    text = "\n\n".join("параграф номер %d со словами. " % i * 10 for i in range(30))
    chunks = chunk_text(text, chunk_chars=200)
    assert len(chunks) > 1
    assert all(len(c) <= 400 for c in chunks)


def test_chunk_cap():
    text = "\n\n".join("кусок %d " % i * 100 for i in range(500))
    assert len(chunk_text(text)) <= 40


# ---------- полка ----------

def test_library_shelf(home):
    (home / "docs" / "a.md").write_text("# A", encoding="utf-8")
    (home / "docs" / "b.txt").write_text("не md", encoding="utf-8")
    (home / "README.md").write_text("# Дом", encoding="utf-8")
    files = library_files(home)
    names = [p.name for p in files]
    assert names == ["a.md", "README.md"]      # txt и прочее — не берём


# ---------- чтение ----------

def test_read_one_file_per_tick(home):
    (home / "docs" / "first.md").write_text(
        "Правило дома: порт 5000 не трогаем никогда.", encoding="utf-8")
    (home / "docs" / "second.md").write_text(
        "Вторая глава: глаза смотрят раз в минуту.", encoding="utf-8")

    lib = Librarian(home=home)
    r1 = lib.read_one()
    assert r1["file"] == "docs/first.md"
    r2 = lib.read_one()
    assert r2["file"] == "docs/second.md"
    assert lib.read_one() is None              # всё прочитано


def test_read_puts_chunks_into_memory(home):
    (home / "docs" / "rule.md").write_text(
        "Правило дома: порт 5000 не трогаем никогда. Это закон.", encoding="utf-8")
    Librarian(home=home).read_one()
    mem = Memory(data_dir=home / "data")
    got = mem.recall("порт 5000")
    assert got and "порт 5000 не трогаем" in got[0]["text"]
    assert "библиотека" in got[0].get("tags", [])


def test_changed_file_reread(home):
    p = home / "docs" / "live.md"
    p.write_text("версия один", encoding="utf-8")
    lib = Librarian(home=home)
    lib.read_one()
    assert lib.read_one() is None
    p.write_text("версия два: блокады больше нет", encoding="utf-8")
    os.utime(p, (p.stat().st_mtime + 10,) * 2)   # mtime строго новее
    r = lib.read_one()
    assert r is not None and r["file"] == "docs/live.md"
    mem = Memory(data_dir=home / "data")
    assert any("блокады больше нет" in x["text"] for x in mem._records())


def test_state_survives_restart(home):
    (home / "docs" / "x.md").write_text("прочитано до рестарта", encoding="utf-8")
    Librarian(home=home).read_one()
    assert Librarian(home=home).read_one() is None


# ---------- команда в чате ----------

class NoBrain:
    def ask_json(self, *a, **k):          # noqa: ANN002, ANN003
        raise AssertionError("мозг не должен просыпаться")


def test_agent_read_command(home):
    (home / "docs" / "rule.md").write_text(
        "Правило дома: порт 5000 не трогаем никогда.", encoding="utf-8")
    agent = Agent(brain=NoBrain(), memory=None, doctrine="")
    r = agent.handle("почитай")
    assert r.source == "python" and r.tool_used == "librarian"
    assert "docs/rule.md" in r.text

    r2 = agent.handle("почитай")
    assert "полка прочитана" in r2.text
