# -*- coding: utf-8 -*-
"""Тесты круга 6 «Дом и его тело» (Ф36–Ф40, 23.11): расписание, поиск
файлов, вес дома, полка, летопись."""
import datetime as dt
import json
import os
import time
from pathlib import Path

import pytest

from core import agenda, config, filefind, legacy, shelf, weight
from tests.fake_llama_server import start_fake_brain


@pytest.fixture()
def home(tmp_path, monkeypatch):
    """Песочница круга 6: дом — только tmp_path (урок изоляции круга 1)."""
    monkeypatch.setattr(config, "HOME_DIR", tmp_path)
    monkeypatch.setattr(config, "SCHEDULE_STATE_FILE",
                        tmp_path / "data" / "schedule_state.json")
    monkeypatch.setattr(config, "LIBRARIAN_STATE_FILE",
                        tmp_path / "data" / "librarian_state.json")
    yield tmp_path


@pytest.fixture()
def srv(monkeypatch, home):
    server = start_fake_brain()
    monkeypatch.setattr(config, "BRAIN_URL", server.base_url)
    yield server
    server.shutdown()


@pytest.fixture()
def agent(srv):
    from core.agent import Agent
    from core.brain import BrainClient
    from core.memory import Memory
    mem = Memory(data_dir=Path(config.DATA_DIR))
    return Agent(brain=BrainClient(brain_url=srv.base_url), memory=mem,
                 doctrine="Тестовая доктрина")


# ---------- Ф36 расписание ----------

def test_agenda_lists_jobs_with_honest_units():
    """«every» расписания — СЕКУНДЫ: доктор every=300 — «раз в 5 мин»,
    библиотекарь 3600 — «раз в час». Первая ревизия обещала
    «раз в 300 мин» — единицы не выдумываются."""
    out = agenda.render()
    assert "РАСПИСАНИЕ ДОМА" in out
    assert "раз в 5 мин" in out            # доктор (300 с)
    assert "раз в час" in out              # библиотекарь (3600 с)
    assert "раз в минуту" in out           # очередь (60 с)
    assert "300 мин" not in out            # урок круга: секунды ≠ минуты


def test_agenda_weekly_wording():
    """«по воскресеньям» — готовой формой слова: «по средуам» и
    «понедельникник» первой ревизии — якорь навсегда."""
    out = agenda.render()
    assert "по воскресеньям в 20:00" in out
    assert "понедельникник" not in out
    assert "средуам" not in out and "воскресенам" not in out


def test_agenda_today_mark(home):
    """Прогон сегодня — «сегодня было в ЧЧ:ММ»; давний — просто «было»."""
    config.SCHEDULE_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    config.SCHEDULE_STATE_FILE.write_text(json.dumps(
        {"plan": {"last": time.time()}}), encoding="utf-8")
    assert "сегодня было в" in agenda.render()
    old = time.mktime(dt.datetime(2026, 11, 1, 8, 0).timetuple())
    config.SCHEDULE_STATE_FILE.write_text(json.dumps(
        {"plan": {"last": old}}), encoding="utf-8")
    out = agenda.render()
    assert "было 01.11 08:00" in out
    assert "сегодня было" not in out


def test_agenda_broken_state_honest(home):
    """Битое состояние — работы всё равно известны (расписание — код)."""
    config.SCHEDULE_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    config.SCHEDULE_STATE_FILE.write_text("не json", encoding="utf-8")
    out = agenda.render()
    assert "план дня" in out and "доктор" in out


def test_agenda_garbage_last_is_skipped(home):
    """Мусор в «last» — строка без крэша (броня органа)."""
    config.SCHEDULE_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    config.SCHEDULE_STATE_FILE.write_text(json.dumps(
        {"plan": {"last": "вчера"}}), encoding="utf-8")
    out = agenda.render()
    assert "план дня" in out and "сегодня было" not in out


# ---------- Ф37 найди файл ----------

def test_filefind_finds_and_skips_cluttered_rooms(home):
    """Находит по подстроке; чуланы (venv, models) честно не смотрит."""
    (home / "data").mkdir(exist_ok=True)
    (home / "data" / "otchet_goda.txt").write_text("x", encoding="utf-8")
    (home / "venv").mkdir(exist_ok=True)
    (home / "venv" / "otchet_venv.txt").write_text("x", encoding="utf-8")
    out = filefind.find("otchet")
    assert "otchet_goda.txt" in out
    assert "venv" not in out                # чулан не смотрела — и не нашла


def test_filefind_no_hits_honest(home):
    (home / "data").mkdir(exist_ok=True)
    assert "не нашла" in filefind.find("зонтик")


def test_filefind_empty_query_hint():
    assert "что искать" in filefind.find("")


def test_filefind_cap_and_freshness(home):
    """Потолок 20 с «… и ещё N»; свежие сверху."""
    d = home / "data"
    d.mkdir(exist_ok=True)
    for i in range(25):
        f = d / ("doklad_%02d.txt" % i)
        f.write_text("x", encoding="utf-8")
        stamp = time.mktime(dt.datetime(2026, 11, i + 1, 10, 0).timetuple())
        os.utime(f, (stamp, stamp))
    out = filefind.find("doklad")
    assert "НАЙДЕНО (20" in out
    assert "… и ещё 5" in out
    assert "doklad_24" in out              # ноябрь свежее — сверху


def test_filefind_deep_paths_limited(home):
    """Глубже 5 этажей не спускается — честная граница скорости."""
    p = home
    for i in range(7):
        p = p / ("etazh%d" % i)
    p.mkdir(parents=True, exist_ok=True)
    (p / "glubokiy_klad.txt").write_text("x", encoding="utf-8")
    assert "не нашла" in filefind.find("glubokiy")


# ---------- Ф38 вес дома ----------

def test_weight_house_top_and_total(home):
    (home / "data").mkdir(exist_ok=True)
    (home / "logs").mkdir(exist_ok=True)
    (home / "data" / "a.bin").write_bytes(b"1" * 5000)
    (home / "logs" / "b.log").write_bytes(b"1" * 300)
    out = weight.render()
    assert "ВЕС ДОМА" in out
    assert "data" in out and "logs" in out
    assert "4,9 КБ" in out                 # 5000 Б по-человечески, запятая


def test_weight_single_folder(home):
    (home / "data").mkdir(exist_ok=True)
    (home / "data" / "a.bin").write_bytes(b"1" * 2048)
    out = weight.render("data")
    assert "«data» весит" in out and "2,0 КБ" in out


def test_weight_missing_folder_honest(home):
    assert "нет" in weight.render("chulan")


def test_weight_refuses_escape(home):
    """«..» и слэши — не части имени: дом наружу не выходит."""
    assert "какую папку" in weight.render("..")
    assert "какую папку" in weight.render("data/../../..")


def test_weight_empty_home_honest(home):
    assert "нечего взвешивать" in weight.render()


# ---------- Ф39 полка ----------

def test_shelf_sorted_by_chunks(home):
    config.LIBRARIAN_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    config.LIBRARIAN_STATE_FILE.write_text(json.dumps(
        {"files": {"malo.txt": {"chunks": 3}, "mnogo.md": {"chunks": 40}}}),
        encoding="utf-8")
    out = shelf.render()
    assert "ПОЛКА" in out and "43 кусков" in out
    assert out.index("mnogo.md") < out.index("malo.txt")


def test_shelf_armored_against_garbage(home):
    """Мусорные chunks не роняют полку (броня органа)."""
    config.LIBRARIAN_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    config.LIBRARIAN_STATE_FILE.write_text(json.dumps(
        {"files": {"bityi.txt": {"chunks": "mnogo"},
                   "zhivoy.md": {"chunks": 7}}}), encoding="utf-8")
    out = shelf.render()
    assert "zhivoy.md" in out and "bityi.txt" in out and "0 кусков" in out


def test_shelf_empty_and_broken_honest(home):
    assert "полка пуста" in shelf.render()
    config.LIBRARIAN_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    config.LIBRARIAN_STATE_FILE.write_text("не json", encoding="utf-8")
    assert "полка пуста" in shelf.render()


def test_shelf_cap_twelve(home):
    config.LIBRARIAN_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    files = {"f%02d.txt" % i: {"chunks": i} for i in range(15)}
    config.LIBRARIAN_STATE_FILE.write_text(json.dumps({"files": files}),
                                           encoding="utf-8")
    assert "… и ещё 3" in shelf.render()


# ---------- Ф40 летопись ----------

BOOK = """# Марфа — логбук фишек (CHANGELOG)

История дома из git log: собрано командой «логбук»:
5 коммитов, 2026-11-19 — 2026-11-23.

## 2026-11-23 — 2 коммита

- **круг 6 «Дом и его тело» — Ф36-Ф40** — расписание, найди файл, вес, полка, летопись
- логбук: CHANGELOG.md пересобран — 5 коммитов истории дома

## 2026-11-22 — 3 коммита

- дом №37 «будильник» (Ф10)
- **память v2 «запиши в память»** — рефлекс, мозг молчит
- терапия §15
"""


def test_legacy_reads_book(tmp_path):
    book = tmp_path / "CHANGELOG.md"
    book.write_text(BOOK, encoding="utf-8")
    out = legacy.render(book)
    assert "ЛЕТОПИСЬ ДОМА" in out
    assert "5 коммитов за период 2026-11-19 — 2026-11-23" in out
    assert "Ф36-Ф40" in out                    # новейший день
    assert "будильник" not in out              # прошлые дни — мимо
    assert "**" not in out                     # жир книги не течёт в чат


def test_legacy_caps_long_bullets(tmp_path):
    book = tmp_path / "CHANGELOG.md"
    book.write_text(BOOK.replace(
        "- логбук: CHANGELOG.md пересобран — 5 коммитов истории дома",
        "- " + "очень длинная строка истории дома из книги, длиннее "
        "ста десяти символов, чтобы якорь на подрезку сработал честно"),
        encoding="utf-8")
    assert "…" in legacy.render(book)


def test_legacy_missing_book_honest(tmp_path):
    assert "логбук" in legacy.render(tmp_path / "net.md")


def test_legacy_unparsed_book_honest(tmp_path):
    book = tmp_path / "CHANGELOG.md"
    book.write_text("тут нет шапки с цифрами", encoding="utf-8")
    assert "не разобрана" in legacy.render(book)


def test_legacy_reads_real_repo_book():
    """Настоящая книга репозитория разбирается (регрессия формата)."""
    out = legacy.render()
    assert "ЛЕТОПИСЬ ДОМА" in out
    assert "коммитов за период" in out


def test_legacy_survives_russian_plurals(tmp_path):
    """День-9, регрессия: «161 коммит» (единственное число) сломало
    летопись — регулярка ждала только «коммитов». Все падежи читаются."""
    for form in ("161 коммит,", "163 коммита,", "156 коммитов,"):
        book = tmp_path / ("book_%s.md" % form.split()[1])
        book.write_text(
            "Собрано командой «логбук»:\n%s 2026-11-16 — 2026-11-24.\n\n"
            "## 2026-11-24 — 1 коммит\n\n- фишка дня\n" % form,
            encoding="utf-8")
        out = legacy.render(book)
        assert "ЛЕТОПИСЬ ДОМА" in out, form
        assert "за период 2026-11-16 — 2026-11-24" in out, form


# ---------- проводка агента ----------

def test_agent_schedule_command(agent):
    r = agent.handle("расписание")
    assert r.source == "python" and "РАСПИСАНИЕ ДОМА" in r.text


def test_agent_find_file_command(agent, home):
    (home / "data").mkdir(exist_ok=True)
    (home / "data" / "счёт_фактура.txt").write_text("x", encoding="utf-8")
    r = agent.handle("найди файл фактура")
    assert r.source == "python" and "счёт_фактура.txt" in r.text


def test_agent_find_file_is_not_eyes(agent):
    """«найди файл X» ≠ «найди на экране X»: файлы — по дому, глаза спят."""
    r = agent.handle("найди файл чего-то-нет")
    assert r.source == "python" and "не нашла" in r.text


def test_agent_shelf_weight_legacy(agent, home):
    r = agent.handle("полка")
    assert r.source == "python" and "полка пуста" in r.text
    (home / "data").mkdir(exist_ok=True)
    (home / "data" / "x.bin").write_bytes(b"1" * 100)
    r = agent.handle("вес data")
    assert r.source == "python" and "«data» весит" in r.text
    r = agent.handle("вес дома")
    assert r.source == "python" and "ВЕС ДОМА" in r.text
    r = agent.handle("что построили")
    assert r.source == "python" and "ЛЕТОПИСЬ" in r.text
    r = agent.handle("летопись")
    assert r.source == "python" and "ЛЕТОПИСЬ" in r.text


def test_fast_commands_know_circle6():
    """Манифест и «изучи себя» знают круг 6 — мозг не обещает лишнего."""
    from core import identity
    text = " ".join(identity.FAST_COMMANDS)
    for word in ("расписание", "найди файл", "вес дома", "полка",
                 "что построили"):
        assert word in text
    assert "Ф40" in text
