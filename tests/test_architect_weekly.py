# -*- coding: utf-8 -*-
"""tests/test_architect_weekly.py — №29 роадмапа 30: architect_oncall v2.

Еженедельный аудит дома: тесты, коммиты, здоровье диска, дрейф
канона — отчёт Создателю (команда «доклад архитектора» + расписание
вс 20:00). Контракт:

  - все источники на моках (швы _src_*): реальный pytest/git/диск
    в тестах не нужны — час прогона батареи не цена якоря;
  - отчёт несёт все пять секций; каждый источник в своей броне
    (закон №10 р3): упавший — честная строка «не ответил», отчёт жив;
  - сохраняется в logs/architect/weekly_<год>-W<неделя>.md — одна
    неделя один файл (снимок, не дневник);
  - «нет pytest» — «НЕ ЗАПУСКАЛИСЬ», а не «красные» (N7);
  - работа расписания зарегистрирована (вс 20:00, weekly);
  - команда агента не будит мозг, крах — честный текст.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import architect_oncall  # noqa: E402
from core import agent  # noqa: E402


@pytest.fixture()
def mocked_sources(monkeypatch, tmp_path):
    """Все источники аудита — на моках; архив — во временной папке."""
    monkeypatch.setattr(architect_oncall, "ARCHIVE_DIR", tmp_path / "arch")
    monkeypatch.setattr(architect_oncall, "_src_services",
                        lambda: "мозг (8082): жив; глаза (8083): жив; панель (5001): жив")
    monkeypatch.setattr(architect_oncall, "_src_tests",
                        lambda: "БАТАРЕЯ ЗЕЛЁНАЯ — 800 passed in 60 s")
    monkeypatch.setattr(architect_oncall, "_src_commits",
                        lambda days=7: "12 коммитов за 7 дней; последний: глаза №2 «найди на экране»")
    monkeypatch.setattr(architect_oncall, "_src_disk",
                        lambda: "свободно 240 ГБ из 500 — ОК")
    monkeypatch.setattr(architect_oncall, "_src_canon_drift",
                        lambda: "дерево чистое — канон и код в одной правде")
    yield tmp_path


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


# ---------- отчёт ----------

def test_weekly_report_all_sections(mocked_sources):
    text = architect_oncall.weekly_report()
    for sec in ("СЛУЖБЫ", "ТЕСТЫ", "КОММИТЫ", "ДИСК", "КАНОН"):
        assert "## %s" % sec in text, sec
    assert "800 passed" in text
    assert "12 коммитов" in text
    assert "дерево чистое" in text
    assert "неделя 20" in text or "неделя 19" in text  # W-номер года честен


def test_weekly_report_saves_file(mocked_sources):
    architect_oncall.weekly_report()
    files = list((mocked_sources / "arch").glob("weekly_*-W*.md"))
    assert len(files) == 1
    assert "## ТЕСТЫ" in files[0].read_text(encoding="utf-8")


def test_weekly_report_source_crash_armored(mocked_sources, monkeypatch):
    """№10 р3: источник упал — честная строка, отчёт жив целиком."""
    def boom():
        raise RuntimeError("pytest завис")

    monkeypatch.setattr(architect_oncall, "_src_tests", boom)
    text = architect_oncall.weekly_report()
    assert "не ответил" in text and "pytest завис" in text
    assert "## КОММИТЫ" in text           # остальные секции на месте


def test_weekly_report_file_down_report_alive(monkeypatch, tmp_path):
    """Файл не записался — отчёт в чате всё равно жив."""
    class BrokenDir:
        def mkdir(self, *a, **kw):
            raise OSError("диск read-only")

        def __truediv__(self, other):
            return self

        def write_text(self, *a, **kw):
            raise OSError("диск read-only")

    monkeypatch.setattr(architect_oncall, "ARCHIVE_DIR", BrokenDir())
    monkeypatch.setattr(architect_oncall, "_src_tests",
                        lambda: "БАТАРЕЯ ЗЕЛЁНАЯ — 1 passed")
    text = architect_oncall.weekly_report()
    assert "## ТЕСТЫ" in text


def test_src_tests_no_pytest_is_not_red(monkeypatch):
    """N7: нет pytest — «НЕ ЗАПУСКАЛИСЬ», не «красные»."""

    class FakeRun:
        returncode = 1
        stderr = "python: No module named pytest"
        stdout = ""

    monkeypatch.setattr(architect_oncall.subprocess, "run",
                        lambda *a, **kw: FakeRun())
    assert "НЕ ЗАПУСКАЛИСЬ" in architect_oncall._src_tests()


def test_src_disk_low_space_warns(monkeypatch):
    class DU:
        free = 10 * 2**30
        total = 500 * 2**30
    monkeypatch.setattr(architect_oncall.shutil, "disk_usage", lambda p: DU())
    line = architect_oncall._src_disk()
    assert "МАЛО МЕСТА" in line and "10 ГБ" in line


def test_src_canon_drift_flags_docs(monkeypatch):
    class FakeRun:
        returncode = 0
        stdout = " M docs/ROADMAP_30.md\n M core/eyes.py\n"
    monkeypatch.setattr(architect_oncall.subprocess, "run",
                        lambda *a, **kw: FakeRun())
    line = architect_oncall._src_canon_drift()
    assert "незакоммичено файлов: 2" in line
    assert "КАНОН ДРЕЙФУЕТ" in line        # книги docs/ — отдельно


# ---------- расписание ----------

def test_weekly_audit_job_registered():
    from core.schedule import default_jobs
    jobs = {j["id"]: j for j in default_jobs()}
    assert "architect-weekly" in jobs
    j = jobs["architect-weekly"]
    assert j["kind"] == "weekly" and j["weekday"] == "sun" and j["at"] == "20:00"


def test_weekly_audit_job_runs_report(monkeypatch, mocked_sources):
    """Работа расписания зовёт настоящий отчёт и возвращается строкой
    статуса — служба стремления не падает и не молчит."""
    from core.schedule import default_jobs
    jobs = {j["id"]: j for j in default_jobs()}
    assert jobs["architect-weekly"]["run"]().startswith("доклад архитектора")


# ---------- команда агента ----------

def test_agent_command_weekly_report(monkeypatch, mocked_sources):
    a = _agent()
    for msg in ("доклад архитектора", "аудит недели", "доклад архитектора?"):
        r = a.handle(msg)
        assert r.tool_used == "architect_weekly", msg
        assert "## ТЕСТЫ" in r.text
        assert a.brain.calls == 0, msg


def test_agent_command_crash_honest(monkeypatch):
    def boom(save=True):
        raise RuntimeError("всё упало")

    monkeypatch.setattr(architect_oncall, "weekly_report", boom)
    a = _agent()
    r = a.handle("доклад архитектора")
    assert r.tool_used == "architect_weekly"
    assert "не собрался" in r.text and "архитектору" in r.text
    assert a.brain.calls == 0


# ---------- СТРАЖ «ТЕСТ В ТЕСТЕ» (23.11, урок песочницы) ----------

def test_src_tests_refuses_inside_battery(monkeypatch):
    """Дежурный, проснувшись ВНУТРИ батареи (стремление в тесте гоняет
    настоящий weekly_audit), не запускает вторую батарею: она дошла бы
    до стремления снова — и так до таймаутов, рекурсия из одной минуты.
    PYTEST_CURRENT_TEST ставит сам pytest — честный отказ, как N7."""
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "tests/test_drive.py::x")
    line = architect_oncall._src_tests()
    assert "НЕ ЗАПУСКАЛИСЬ" in line and "тест в тесте" in line


def test_src_tests_runs_outside_battery(monkeypatch):
    """Вне батареи (живой дом, вс 20:00) — батарея запускается как
    раньше: страж не превратил weekly_audit в вечно молчащий."""
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    # подменяем сам запуск: важно, что страж его ПРОПУСТИЛ
    called = []

    def fake_run(cmd, **kw):
        called.append(cmd)
        class R:
            returncode = 0
            stdout = "779 passed"
            stderr = ""
        return R()

    monkeypatch.setattr(architect_oncall.subprocess, "run", fake_run)
    line = architect_oncall._src_tests()
    assert called, "страж не пустил батарею вне теста — слишком рьяно"
    assert "ЗЕЛЁНАЯ" in line
