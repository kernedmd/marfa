# -*- coding: utf-8 -*-
"""tests/test_changelog.py — №24 роадмапа 30: «логбук фишек».

CHANGELOG.md из git log: каждая строка — коммит, ПЕРВАЯ строка
коммита в этом доме и есть выжимка фичи (канон канона: маска «Г-N:»
не прижилась, орган+№+суть — живой стандарт). Контракт:

  - фиксированный лог → фиксированный список (роадмап);
  - мусорные строки лога пропускаются молча, логбук не падает;
  - дни — секциями, новые сверху; тег «№N» — жирным;
  - длинные первые строки режутся с честным «…»;
  - пустой лог — честный отказ, а не пустой CHANGELOG;
  - команда «логбук» собирает файл и говорит правду, мозг молчит.

Швы: changelog._git_log (реальный git не нужен).
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import agent, config  # noqa: E402
from evolution import changelog  # noqa: E402

FIXED_LOG = [
    "d765e37|2026-11-23|статус дома v1.2: внутренняя жизнь на одной странице",
    "baa4279|2026-11-23|чувства-сон-мысли: ВЖИВЛЕНИЕ — три органа подсоединены к организму",
    "eb2f419|2026-11-23|глаза №2 «найди на экране»: ЛЕСТНИЦА ЗОН — мелкая надпись читается в увеличенной четверти",
    "0cb1e10|2026-11-22|руки №18 «запиши в буфер» + Р-4 ЗАКРЫТ: КИРИЛЛИЦА ПЕЧАТАЕТСЯ",
    "мусорная строка без палочек",
    "|2026-11-22|пустой хеш",
    "abc1234|2026-11-21|",
    "399b740|2026-11-16|канон v10.0-pre восстановлен и зафиксирован",
]


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


# ---------- парсер ----------

def test_parse_fixed_log():
    entries = changelog.parse_log(FIXED_LOG)
    # мусор (без тройки, пустые поля) пропущен молча
    assert len(entries) == 5
    assert entries[0]["hash"] == "d765e37"
    assert entries[0]["date"] == "2026-11-23"
    assert entries[0]["subject"].startswith("статус дома")
    assert entries[-1]["hash"] == "399b740"


def test_parse_empty():
    assert changelog.parse_log([]) == []


# ---------- рендер ----------

def test_render_groups_by_date_newest_first():
    md = changelog.render_changelog(changelog.parse_log(FIXED_LOG))
    assert md.startswith("# Марфа — логбук фишек")
    assert "## 2026-11-23 — 3 коммита" in md
    assert "## 2026-11-22 — 1 коммит" in md
    assert "## 2026-11-16 — 1 коммит" in md
    # новые сверху: секции идут раньше старых (шапка не считается)
    assert md.index("## 2026-11-23") < md.index("## 2026-11-22") \
        < md.index("## 2026-11-16")


def test_render_bolds_feature_tags():
    md = changelog.render_changelog(changelog.parse_log(FIXED_LOG))
    assert "**глаза №2 «найди на экране»**" in md
    assert "**руки №18 «запиши в буфер» + Р-4 ЗАКРЫТ**" in md
    # запись без тега — просто строка
    assert "- статус дома v1.2" in md


def test_render_truncates_long_subjects():
    long_subject = "глаза №2 «найди на экране»: " + "очень длинная история " * 30
    md = changelog.render_changelog(
        [{"hash": "aaaa111", "date": "2026-11-23", "subject": long_subject}])
    assert "…" in md
    line = [l for l in md.splitlines() if l.startswith("- **")][0]
    assert len(line) < changelog.SUBJECT_CAP + 80


def test_render_plurals_russian():
    one = changelog.render_changelog(
        [{"hash": "a1", "date": "2026-11-23", "subject": "x №1: y"}])
    assert "1 коммит" in one
    two = changelog.render_changelog([
        {"hash": "a1", "date": "2026-11-23", "subject": "x №1: y"},
        {"hash": "a2", "date": "2026-11-23", "subject": "z №2: w"}])
    assert "2 коммита" in two


# ---------- запись файла ----------

def test_write_changelog_creates_file(tmp_path, monkeypatch):
    monkeypatch.setattr(changelog, "_git_log", lambda root: FIXED_LOG)
    rep = changelog.write_changelog(root=tmp_path)
    assert rep["commits"] == 5 and rep["days"] == 3
    out = tmp_path / "CHANGELOG.md"
    assert out.is_file()
    md = out.read_text(encoding="utf-8")
    assert "глаза №2" in md and "399b740" not in md      # хеши не шумят


def test_write_changelog_empty_log_refuses(tmp_path, monkeypatch):
    monkeypatch.setattr(changelog, "_git_log", lambda root: [])
    with pytest.raises(RuntimeError):
        changelog.write_changelog(root=tmp_path)
    assert not (tmp_path / "CHANGELOG.md").exists()


def test_write_changelog_git_down_refuses(tmp_path, monkeypatch):
    def boom(root):
        raise RuntimeError("git log не вышел: не репозиторий")

    monkeypatch.setattr(changelog, "_git_log", boom)
    with pytest.raises(RuntimeError):
        changelog.write_changelog(root=tmp_path)


# ---------- корень книги: чей код — того и книга ----------

def test_repo_root_is_codes_own_repo(tmp_path, monkeypatch):
    # УРОК ДЕГРАДАЦИИ: HOME_DIR в песочнице/симуляции — посторонний
    # контекст; корень книги резолвится от ПАПКИ КОДА и на чужой дом
    # не переезжает, каким бы ни был HOME_DIR
    monkeypatch.setattr(config, "HOME_DIR", tmp_path)   # не репозиторий
    root = changelog._repo_root()
    code_repo = Path(changelog.__file__).resolve().parent.parent
    assert root.resolve() == code_repo.resolve()         # книга — у кода
    assert root.is_absolute()


def test_write_changelog_reports_absolute_file(tmp_path, monkeypatch):
    # отчёт показывает ТОЧНЫЙ абсолютный путь книги — относительный
    # корень больше не может молча дотянуться до cwd
    monkeypatch.setattr(changelog, "_git_log", lambda root: FIXED_LOG)
    monkeypatch.setattr(changelog, "_repo_root", lambda: tmp_path)
    rep = changelog.write_changelog()
    assert rep["file"] == str(tmp_path.resolve() / "CHANGELOG.md")


# ---------- команда агента ----------

def test_agent_command_logbook(tmp_path, monkeypatch):
    # УРОК ДЕГРАДАЦИИ КНИГИ (23.11, утро): корень резолвился в Path("."),
    # и батарея, запущенная от корня репозитория, ПЕРЕЗАПИСЫВАЛА
    # настоящий CHANGELOG.md фикстурой из пяти коммитов — тест протекал
    # в дом и портил его книгу. Якорь теперь один и жёсткий: логбук
    # пишет ТОЛЬКО в tmp_path (абсолютный), до настоящего файла не
    # дотягивается в принципе
    a = _agent()
    monkeypatch.setattr(
        changelog, "_git_log", lambda root: FIXED_LOG)
    monkeypatch.setattr(changelog, "_repo_root", lambda: tmp_path)
    for msg in ("логбук", "обнови логбук", "логбук?"):
        r = a.handle(msg)
        assert r.tool_used == "changelog", msg
        assert "Логбук собран" in r.text and "5 коммитов" in r.text
        assert a.brain.calls == 0, msg
    # книга собрана В ПЕСОЧНИЦЕ теста, а не в репозитории дома
    assert (tmp_path / "CHANGELOG.md").is_file()
    assert str(tmp_path) in str((tmp_path / "CHANGELOG.md").resolve())


def test_agent_command_logbook_crash_honest(monkeypatch):
    def boom(root=None):
        raise RuntimeError("git не найден")

    monkeypatch.setattr(changelog, "write_changelog", boom)
    a = _agent()
    r = a.handle("логбук")
    assert r.tool_used == "changelog"
    assert "не собрался" in r.text and "архитектору" in r.text
    assert a.brain.calls == 0
