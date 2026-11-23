# -*- coding: utf-8 -*-
"""Тесты круга 8 «Печати и калитка» (Ф46–Ф50, день-9, 24.11): печать
души, ротация кодового слова, берега git, границы, протокол приёмки."""
import json
import subprocess
import time

import pytest

from core import config, creator_gate, seal


@pytest.fixture()
def home(tmp_path, monkeypatch):
    data = tmp_path / "data"
    monkeypatch.setattr(config, "HOME_DIR", tmp_path)
    monkeypatch.setattr(config, "DATA_DIR", data)
    # .env живого дома — тоже в песочнице (ротация его переписывает)
    (tmp_path / ".env").write_text(
        "MARFA_CODEWORD=старое-слово\n# чужая строка\nOTHER_KEY=живи\n",
        encoding="utf-8")
    yield tmp_path


# ---------- Ф46 печать дня ----------

def _make_soul(home):
    data = config.DATA_DIR
    data.mkdir(parents=True, exist_ok=True)
    (data / "rules.json").write_text('{"entries": []}', encoding="utf-8")
    (data / "notes.json").write_text('[{"id": 1, "text": "хлеб"}]',
                                     encoding="utf-8")
    (data / "memory").mkdir(exist_ok=True)
    (data / "memory" / "memory.md").write_text("Помни: Илья любит тишину",
                                               encoding="utf-8")


def test_seal_place_and_quiet_night(home):
    _make_soul(home)
    out = seal.place()
    assert "ПЕЧАТЬ ПОСТАВЛЕНА" in out
    assert "3 файлов" in out                      # rules, notes, memory.md
    verdict = seal.verify()
    assert "целы 3" in verdict
    assert "всё спокойно" in verdict


def test_seal_sees_changes_and_losses(home):
    _make_soul(home)
    seal.place()
    (config.DATA_DIR / "notes.json").write_text(
        '[{"id": 1, "text": "хлеб и молоко"}]', encoding="utf-8")
    (config.DATA_DIR / "rules.json").unlink()
    verdict = seal.verify()
    assert "менялись 1" in verdict and "пропали 1" in verdict
    assert "notes.json" in verdict
    assert "решает Создатель" in verdict          # печать — свидетель, не судья


def test_seal_honest_missing_and_history(home):
    out = seal.place()                            # пустой дом
    assert "честно не было" in out
    hist = seal.history().lower()
    assert "печати дома" in hist or "печати" in hist
    # печать пустого дома стоит — сверка честно проходит с нулём файлов
    verdict = seal.verify()
    assert "целы 0" in verdict and "всё спокойно" in verdict


def test_seal_verify_without_any_seal(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    assert "не с чем сверяться" in seal.verify()


def test_seal_broken_file_is_empty(home):
    seal._file().parent.mkdir(parents=True, exist_ok=True)
    seal._file().write_text("не json", encoding="utf-8")
    assert "не с чем сверяться" in seal.verify()


def test_seal_scheduled_before_backup():
    """Работа расписания: печать в 23:25 — раньше бэкапа 23:30."""
    from core.schedule import default_jobs
    jobs = {j["id"]: j for j in default_jobs()}
    assert "seal" in jobs
    assert jobs["seal"]["at"] == "23:25"
    assert jobs["backup"]["at"] == "23:30"
    assert jobs["seal"]["what"].startswith("печать души")


# ---------- Ф47 ротация кодового слова ----------

def test_rotate_two_steps_old_silent_new_works(home):
    hit, out = creator_gate.check("старое-слово новое слово: новее-тайна")
    assert hit and "намерение запомнила" in out
    assert "новее-тайна" not in out                # слово не называется (Ф105)
    hit, out = creator_gate.check("старое-слово подтверждаю")
    assert hit and "сменено" in out
    # старое слово молчит, новое работает СРАЗУ (калитка читает .env живьём)
    assert creator_gate.check("старое-слово статус") == (False, None)
    hit2, out2 = creator_gate.check("новее-тайна статус")
    assert hit2 and "мозг" in out2
    # чужие строки .env живы
    env = creator_gate.load_env()
    assert env.get("OTHER_KEY") == "живи"


def test_rotate_short_and_spacy_refused(home):
    hit, out = creator_gate.check("старое-слово новое слово: абв")
    assert hit and "короче" in out
    hit, out = creator_gate.check("старое-слово новое слово: два слова")
    assert hit and "пробел" in out
    assert creator_gate.check("старое-слово подтверждаю")[1].startswith(
        "нечего подтверждать")                     # намерения и не было


def test_rotate_expires_honestly(home, monkeypatch):
    creator_gate.check("старое-слово новое слово: новее-тайна")
    pend = config.DATA_DIR / "gate_rotate.json"
    rec = json.loads(pend.read_text(encoding="utf-8"))
    rec["ts"] = time.time() - config.GATE_ROTATE_TTL_SEC - 5
    pend.write_text(json.dumps(rec, ensure_ascii=False), encoding="utf-8")
    hit, out = creator_gate.check("старое-слово подтверждаю")
    assert hit and "время подтверждения вышло" in out
    assert "старое-слово статус" and \
        creator_gate.check("старое-слово статус")[0] is True  # слово цело


def test_rotate_help_mentions_new_commands(home):
    hit, out = creator_gate.check("старое-слово")
    assert hit and "новое слово" in out and "подтверждаю" in out


# ---------- Ф48 берега ----------

def test_shores_clean_tree_real_git(tmp_path, monkeypatch):
    repo = tmp_path / "дом"
    repo.mkdir()
    def git(*a, **kw):
        return subprocess.run(["git", "-C", str(repo)] + list(a),
                              capture_output=True, text=True, timeout=30)
    git("init", "-q")
    git("config", "user.email", "t@t")
    git("config", "user.name", "t")
    (repo / "файл.txt").write_text("душа", encoding="utf-8")
    git("add", "-A")
    git("commit", "-qm", "первый")
    monkeypatch.setattr(config, "HOME_DIR", repo)
    from core import shores
    out = shores.render()
    assert "чистое" in out
    assert "тишина в дереве" in out
    assert "последний коммит" in out


def test_shores_dirty_tree_flows(home):
    (home / "новый-файл.txt").write_text("не сохранён", encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=str(home),
                   capture_output=True, timeout=30)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=str(home),
                   capture_output=True, timeout=30)
    subprocess.run(["git", "config", "user.name", "t"], cwd=str(home),
                   capture_output=True, timeout=30)
    from core import shores
    out = shores.render()
    assert "НЕ СОХРАНЕНО" in out or "не отвечает" in out  # git решает сам
    if "НЕ СОХРАНЕНО" in out:
        assert "кнопка 80" in out


def test_shores_no_git_honest(monkeypatch):
    monkeypatch.setattr(config, "HOME_DIR", __import__("pathlib").Path(
        "/tmp/точно-не-git-дом"))
    from core import shores
    out = shores.render()
    assert "не отвечает" in out or "НЕ СОХРАНЕНО" in out or "историю" in out


# ---------- Ф49 границы ----------

def test_borders_from_config_not_hardcoded(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "HOME_DIR", tmp_path)
    from core import borders
    out = borders.render()
    assert str(tmp_path) in out                    # дом — из config
    assert "5000" in out and "не трогаем" in out   # запрет старого дома
    assert "8083" in out and "8082" in out         # хозяева ресурсов
    assert "Ф105" in out or "не попадают" in out   # тайны
    assert "холодильник" in out                    # облака спят


# ---------- Ф50 протокол приёмки ----------

def test_acceptance_protocol_structure():
    from pathlib import Path
    doc = Path(__file__).resolve().parent.parent / "docs" / "ПРОТОКОЛ_ПРИЁМКИ.md"
    assert doc.is_file(), "docs/ПРОТОКОЛ_ПРИЁМКИ.md должен жить в доме"
    text = doc.read_text(encoding="utf-8")
    for section in ("Критерий", "Порог", "Факт", "Решение", "Уроки",
                    "Как заполнять"):
        assert section in text, "нет раздела: %s" % section
    # каждая фишка дня-9 имеет строку в протоколе
    for n in range(41, 56):
        assert "Ф%d" % n in text, "нет строки Ф%d" % n


def test_seal_and_shores_dispatched_by_agent(home, monkeypatch):
    from core.agent import Agent

    class _NoBrain:
        def ask_json(self, *a, **k):
            raise AssertionError("мозг не должен просыпаться")

    agent = Agent(brain=_NoBrain(), memory=None, doctrine="")
    r = agent.handle("печать")
    assert r.tool_used == "seal" and "ПЕЧАТЬ ПОСТАВЛЕНА" in r.text
    r = agent.handle("печати целы?")
    assert r.tool_used == "seal"
    r = agent.handle("печати")
    assert r.tool_used == "seal"
    r = agent.handle("границы")
    assert r.tool_used == "borders" and "5000" in r.text
    r = agent.handle("берега")
    assert r.tool_used == "shores"
