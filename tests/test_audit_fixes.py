# -*- coding: utf-8 -*-
"""tests/test_audit_fixes.py — регрессии большого аудита 22.11.

Создатель принёс внешний аудит дома (K1–K7, H1–H10, M-серия).
Каждый вылеченный пункт закреплён здесь тестом — чтобы не вернуть
баг вторым коммитом. Нумерация — по письму аудита.
"""
import datetime as dt
import json

import pytest

from core import config
from core.history import HistoryCompressor, _first_sentence
from core.librarian import Librarian, chunk_text, MAX_CHUNKS_PER_FILE
from core.memory import Memory, JsonBackend, ChromaBackend, _clean_metadata, _ts
from core.questions import QuestionBank
from core.schedule import Scheduler, job, _parse_hhmm, RETRY_DELAY_SEC


@pytest.fixture()
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("MARFA_HOME", str(tmp_path))
    monkeypatch.setattr(config, "HOME_DIR", tmp_path)
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(config, "GUARD_LOG_FILE", tmp_path / "logs" / "guard_log.jsonl")
    monkeypatch.setattr(config, "EARS_STATUS_FILE", tmp_path / "data" / "ears_status.json")
    monkeypatch.setattr(config, "DRIVE_STATUS_FILE", tmp_path / "data" / "drive_status.json")
    monkeypatch.setattr(config, "SCHEDULE_STATE_FILE", tmp_path / "data" / "schedule_state.json")
    monkeypatch.setattr(config, "QUEUE_FILE", tmp_path / "data" / "queue.json")
    monkeypatch.setattr(config, "QUESTIONS_FILE", tmp_path / "data" / "questions.json")
    config.ensure_dirs()
    yield tmp_path


# ---------------------------------------------------------------
# K4: ChromaBackend.add больше не выкидывает links из метаданных
# ---------------------------------------------------------------

class _FakeCol:
    def __init__(self):
        self.adds = []

    def add(self, ids, documents, metadatas):
        self.adds.append({"ids": ids, "documents": documents,
                          "metadatas": metadatas})


def test_k4_chroma_add_keeps_links():
    col = _FakeCol()
    backend = ChromaBackend.__new__(ChromaBackend)
    backend.col = col
    backend.add({"id": "a1", "text": "привет", "norm": "привет",
                 "tags": ["тест"], "links": ["b2"], "hits": 0})
    meta = col.adds[0]["metadatas"][0]
    assert meta.get("links") == ["b2"]        # связь доехала (K4)
    assert "text" not in meta and "id" not in meta   # а текст/id — не в метаданных


def test_h10_clean_metadata_empty_is_dict_not_none():
    assert _clean_metadata({}) == {}
    assert _clean_metadata(None) == {}
    assert _clean_metadata({"x": None}) == {}


# ---------------------------------------------------------------
# K5: created_at/expire_at строкой не роняют recall/compress/_alive
# ---------------------------------------------------------------

def test_k5_iso_strings_do_not_crash(home):
    mem = Memory(data_dir=home / "data")
    # запись с ISO-строками — как после импорта/ручной правки
    mem.fallback.add({"id": "iso1", "text": "строка с ISO датой про порты",
                      "norm": "строка с iso датой про порты", "tags": [],
                      "importance": 1.0,
                      "created_at": "2026-11-01T10:00:00",
                      "updated_at": "2026-11-01T10:00:00",
                      "expire_at": "2026-12-01T10:00:00",
                      "hits": 0, "links": []})
    assert mem._alive(mem._records()[0]) is True
    got = mem.recall("ISO дата")              # не TypeError
    assert isinstance(got, list)
    stats = mem.compress_old(days=7, now=dt.datetime(2026, 11, 20).timestamp())
    assert isinstance(stats["compressed"], int)   # не ValueError


def test_k5_garbage_timestamp_skipped_not_fatal(home):
    mem = Memory(data_dir=home / "data")
    mem.fallback.add({"id": "bad1", "text": "мусорная дата про порты",
                      "tags": [], "importance": 1.0,
                      "created_at": "не-дата-вовсе",
                      "expire_at": "тоже-мусор", "hits": 0, "links": []})
    assert isinstance(mem.recall("мусор"), list)
    assert isinstance(mem.compress_old(days=7), dict)


def test_k5_ts_helper():
    assert _ts(1732260000) == 1732260000.0
    assert _ts("2026-11-22T10:00:00") is not None
    assert _ts("мусор") is None
    assert _ts("мусор", default=42) == 42
    assert _ts(None, default=7) == 7


# ---------------------------------------------------------------
# H1/M3: точечные запросы вместо полных сканов; link одним проходом
# ---------------------------------------------------------------

def test_h1_json_find_by_norm_and_legacy(home):
    mem = Memory(data_dir=home / "data")
    mem.remember("точный дедуп по норме")
    # старая запись БЕЗ norm (M8) — дедуп всё равно находит её
    mem.fallback.add({"id": "legacy1", "text": "легаси запись без norm",
                      "tags": [], "importance": 1.0,
                      "created_at": 1730000000.0, "updated_at": 1730000000.0,
                      "expire_at": None, "hits": 0, "links": []})
    assert mem.fallback.find_by_norm("легаси запись без norm")["id"] == "legacy1"
    before = len(mem._records())
    mem.remember("Легаси запись без norm!")   # другой регистр/пунктуация
    assert len(mem._records()) == before      # обновилось, а не плодилось (M8)


def test_m3_link_one_pass(home):
    mem = Memory(data_dir=home / "data")
    a = mem.remember("первая мысль")
    b = mem.remember("вторая мысль")
    calls = []
    orig = mem._records

    def counting():
        calls.append(1)
        return orig()

    mem._records = counting
    assert mem.link(a["id"], b["id"]) is True
    assert len(calls) == 1                    # один проход, не три (M3)


# ---------------------------------------------------------------
# H2: битый JSON памяти — карантин, не смерть
# ---------------------------------------------------------------

def test_h2_broken_json_quarantined(home):
    p = home / "data" / "memory" / "memory.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("{битый json", encoding="utf-8")
    backend = JsonBackend(p)
    assert backend._load() == []              # не JSONDecodeError
    aside = list(p.parent.glob("memory.json.broken-*"))
    assert aside, "битый файл отложен для спасения, не затёрт"
    # и дом продолжает работать
    mem = Memory(data_dir=home / "data")
    mem.remember("после битого файла помню новое")
    assert any("после битого" in r["text"] for r in mem._records())


# ---------------------------------------------------------------
# M2: tags=[] — честная очистка
# ---------------------------------------------------------------

def test_m2_empty_tags_clears(home):
    mem = Memory(data_dir=home / "data")
    mem.remember("теги чистятся", tags=["старый"])
    rec = mem.remember("теги чистятся", tags=[])
    assert rec["tags"] == []


# ---------------------------------------------------------------
# M4: compress считает только реально забытые
# ---------------------------------------------------------------

def test_m4_compress_counts_only_real_forgets(home):
    mem = Memory(data_dir=home / "data")
    old = dt.datetime(2026, 10, 1).timestamp()
    for i in range(5):
        mem.remember("старая мысль номер %d" % i)
        # уводим created_at за горизонт
        recs = mem.fallback._load()
        recs[-1]["created_at"] = old
        mem.fallback._save(recs)
    mem.forget = lambda _id: False            # forget не смог
    stats = mem.compress_old(days=7, now=dt.datetime(2026, 11, 20).timestamp())
    assert stats["compressed"] == 0           # не врём в отчёте (M4)


# ---------------------------------------------------------------
# M13: фоллбэк памяти — видимый урок (один раз за процесс)
# ---------------------------------------------------------------

def test_m13_fallback_writes_lesson_once(home, monkeypatch):
    import core.memory as mem_mod
    monkeypatch.setattr(mem_mod, "_fallback_lesson_done", False)
    lessons = []
    monkeypatch.setitem(__import__("sys").modules, "evolution.journal",
                        __import__("types").SimpleNamespace(
                            log_lesson=lambda k, t: lessons.append((k, t))))
    Memory(data_dir=home / "data")
    Memory(data_dir=home / "data")            # второй раз — тишина
    assert len([x for x in lessons if x[0] == "память-фоллбэк"]) == 1


# ---------------------------------------------------------------
# K6: новейший ход длиннее бюджета — его выжимка, не пустота
# ---------------------------------------------------------------

def test_k6_huge_newest_turn_survives_as_extract():
    h = HistoryCompressor()
    h.add_turn("user", "короткий старый ход")
    huge = ("Огромный ход. " + "подробности событий и обстоятельств. ") * 400
    h.add_turn("assistant", huge)
    text = h.render(prefer_brain=False)
    assert "Последние ходы:" in text
    assert "Огромный ход." in text           # выжимка новейшего жива (K6)
    assert config.token_estimate(text) <= h.budget
    assert h.last_stats["kept_verbatim"] >= 1


def test_m6_first_sentence_end_of_string():
    assert _first_sentence("Привет.") == "Привет."
    assert _first_sentence("Раз. Два") == "Раз."
    from core.dialog import _first_sentence as dialog_sent
    assert dialog_sent("Привет.") == "Привет."   # тот же фикс в dialog


# ---------------------------------------------------------------
# H3: сводка мозгом кэшируется — два render, один поход к 30B
# ---------------------------------------------------------------

def test_h3_brain_summary_cached():
    calls = []

    class Brain:
        def chat(self, messages, gen_tokens=None, temperature=0.2):
            calls.append(1)
            return "сводка от 30B"

    h = HistoryCompressor(brain=Brain())
    for i in range(20):
        # ходы достаточно длинные, чтобы хвост не съел всё — старые
        # ходы обязаны попасть в сводку, иначе мозг не зовётся вовсе
        h.add_turn("user", ("ход номер %d. " % i) + "детали событий. " * 60)
    t1 = h.render(prefer_brain=True)
    assert "сводка от 30B" in t1 and len(calls) == 1
    t2 = h.render(prefer_brain=True)
    assert "сводка от 30B" in t2
    assert len(calls) == 1                    # мозг дёрган один раз (H3)
    # а когда старые ходы меняются — сводка пересобирается
    # (круг 35: оценка стала консервативной (2 симв/ток) — короткий новый
    # ход влезает в дословный хвост целиком и старые НЕ меняются: кэш
    # честен, мозг спит. Меняем старые ходы ДОЛГИМ ходом, вытесняющим
    # дословный хвост старых)
    h.add_turn("user", "новый ход, меняющий историю. " + "подробности. " * 130)
    h.render(prefer_brain=True)
    assert len(calls) == 2


def test_m7_dropped_honest_after_fit():
    h = HistoryCompressor()
    for i in range(30):
        h.add_turn("user", ("ход %d. " % i) + "детали. " * 300)
    h.render(prefer_brain=False)
    # dropped считается по факту представленных ходов, не по промежуточным спискам
    assert h.last_stats["dropped"] >= 0
    assert h.last_stats["kept_verbatim"] + h.last_stats["summarized"] \
        + h.last_stats["dropped"] == len(h.turns)


# ---------------------------------------------------------------
# K7: упавшая работа не помечается выполненной
# ---------------------------------------------------------------

def test_k7_failed_daily_not_marked_done(home):
    sched = Scheduler()
    boom_calls = []

    def boom():
        boom_calls.append(1)
        raise RuntimeError("дневник не собрался")

    j = job("diary", "daily", at="08:00", what="падает", run=boom)
    res = sched.tick(dt.datetime(2026, 11, 21, 8, 0), [j])
    assert res[0]["ok"] is False
    state = json.loads(config.SCHEDULE_STATE_FILE.read_text(encoding="utf-8"))
    assert "diary" not in state               # успехом НЕ помечена (K7)
    assert "diary!fail" in state              # провал виден отдельным ключом
    # минуту спустя — НЕ пора (пауза 30 минут между попытками)
    assert sched.due(dt.datetime(2026, 11, 21, 8, 1), [j]) == []
    # через 31 минуту — повтор
    assert sched.due(dt.datetime(2026, 11, 21, 8, 31), [j]) == [j]
    assert len(boom_calls) == 1               # пока не повторялась


def test_k7_success_wipes_fail_memory(home):
    sched = Scheduler()
    flaky = {"n": 0}

    def flaky_run():
        flaky["n"] += 1
        if flaky["n"] == 1:
            raise RuntimeError("первый раз падаю")
        return "готово"

    j = job("plan", "daily", at="08:00", what="флейк", run=flaky_run)
    sched.tick(dt.datetime(2026, 11, 21, 8, 0), [j])
    sched.tick(dt.datetime(2026, 11, 21, 8, 31), [j])   # повтор — успех
    state = json.loads(config.SCHEDULE_STATE_FILE.read_text(encoding="utf-8"))
    assert state.get("plan")                  # успех записан
    assert "plan!fail" not in state           # провал стёрт
    # и до завтра не повторится
    assert sched.due(dt.datetime(2026, 11, 21, 23, 0), [j]) == []


def test_m9_bad_time_honest_error():
    for bad in ("8", "08:00:00", "25:00", "ab:cd"):
        with pytest.raises(ValueError):
            _parse_hhmm(bad)
    assert _parse_hhmm("08:30") == (8, 30)


def test_m9_m10_bad_job_spec_not_due_no_crash(home):
    sched = Scheduler()
    bad_time = job("bt", "daily", at="25:00", what="кривое время", run=lambda: 1)
    bad_day = job("bd", "weekly", weekday="sunday", at="10:00",
                  what="кривой день", run=lambda: 1)
    assert sched.due(dt.datetime(2026, 11, 21, 10, 0), [bad_time, bad_day]) == []
    res = sched.tick(dt.datetime(2026, 11, 21, 10, 0), [bad_time])
    assert res == []                          # расписание живо, ничего не упало


def test_m11_future_state_treated_as_absent(home):
    sched = Scheduler()
    j = job("q", "interval", every=60, what="тест", run=lambda: "ок")
    # часы прыгнули назад: state из «завтра»
    config.SCHEDULE_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    config.SCHEDULE_STATE_FILE.write_text(
        json.dumps({"q": dt.datetime(2026, 11, 22, 10, 0).isoformat()}),
        encoding="utf-8")
    assert sched.due(dt.datetime(2026, 11, 21, 10, 0), [j]) == [j]


# ---------------------------------------------------------------
# H4: кривые статус-файлы не роняют инициативу
# ---------------------------------------------------------------

def test_h4_weird_status_files_survive(home):
    config.EARS_STATUS_FILE.write_text('["массив", "вместо", "словаря"]',
                                       encoding="utf-8")
    config.DRIVE_STATUS_FILE.write_text('{"brain_down_since": null}',
                                        encoding="utf-8")
    asked = QuestionBank().tick(now=dt.datetime(2026, 11, 21, 12, 0))
    assert isinstance(asked, list)            # служба стремления жива


def test_h6_non_dict_items_filtered(home):
    p = home / "data" / "questions.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"next": 5, "items": ["a", 42, None]}),
                 encoding="utf-8")
    bank = QuestionBank()
    assert bank.open_items() == []            # не AttributeError
    q = bank.add("живой вопрос", source="тест")
    assert q and q["id"] == "q5"


def test_h5_duplicate_cancel_writes_lesson(home):
    from core.autonomy import load_queue, save_queue
    tasks = load_queue()
    save_queue([{"id": "t1", "title": "дубль", "status": "pending",
                 "created_at": "2026-11-01T10:00:00"},
                {"id": "t2", "title": "дубль", "status": "pending",
                 "created_at": "2026-11-01T10:00:00"}])
    QuestionBank().tick(now=dt.datetime(2026, 11, 21, 12, 0))
    cancelled = [t for t in load_queue() if t["status"] == "cancelled"]
    assert len(cancelled) == 1


# ---------------------------------------------------------------
# H8/H9/M5: библиотекарь
# ---------------------------------------------------------------

def test_h8_chunk_cap_strict():
    giant = "\n\n".join(("абзац %d " % i) * 400 for i in range(60))
    assert len(chunk_text(giant)) <= MAX_CHUNKS_PER_FILE   # без 41-го куска


def test_h9_failed_memory_does_not_mark_read(home, monkeypatch):
    (home / "docs").mkdir(exist_ok=True)
    (home / "docs" / "book.md").write_text("Глава первая. Много текста. " * 50,
                                           encoding="utf-8")
    lib = Librarian(home=home)
    from core.memory import Memory as _M

    def broken_remember(self, *a, **k):
        raise RuntimeError("память лежит")

    monkeypatch.setattr(_M, "remember", broken_remember)
    report = lib.read_one()
    assert report is not None and report["ok"] is False     # честный отказ
    # состояние НЕ помечено — файл вернётся в работу
    state = json.loads((home / "data" / "librarian_state.json").read_text()
                       ) if (home / "data" / "librarian_state.json").exists() else {}
    assert "docs/book.md" not in state.get("files", {})


def test_m5_empty_file_advances_and_reports_zero(home):
    (home / "docs").mkdir(exist_ok=True)
    (home / "docs" / "empty.md").write_text("   ", encoding="utf-8")
    lib = Librarian(home=home)
    report = lib.read_one()
    assert report["chunks"] == 0 and report["ok"] is True
    assert lib.read_one() is None              # полка пошла дальше


# ---------------------------------------------------------------
# K1/M12: мигратор fix_chroma_v4 безопасен
# ---------------------------------------------------------------

def test_k1_migrator_idempotent_on_fixed_file(tmp_path):
    import core.fix_chroma_v4 as migrator
    from pathlib import Path
    src = Path("core/memory.py")
    dst = tmp_path / "memory.py"
    dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    changed = migrator.apply(dst)
    assert changed is False                    # уже исправлен — не тронут (K1)
    assert "def _norm" in dst.read_text(encoding="utf-8")


def test_k1_migrator_refuses_suspicious_state(tmp_path):
    import core.fix_chroma_v4 as migrator
    from pathlib import Path
    dst = tmp_path / "memory.py"
    # состояние «после повторного запуска старого скрипта»: вырезано всё,
    # кроме _clean_metadata и класса
    suspicious = ("import json\n\n\ndef _clean_metadata(md):\n    return {}\n\n\n"
                  "class Memory:\n    pass\n")
    dst.write_text(suspicious, encoding="utf-8")
    assert migrator.apply(dst) is False        # отказ, честный совет git checkout
    assert dst.read_text(encoding="utf-8") == suspicious   # файл не тронут
