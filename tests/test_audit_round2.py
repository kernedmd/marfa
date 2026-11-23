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
def agent_srv(tmp_path, monkeypatch):
    """Агент + фейк-мозг в tmp-доме (контракт test_agent, для якорей H8)."""
    from core.agent import Agent
    from core.brain import BrainClient
    from core.memory import Memory
    monkeypatch.setenv("MARFA_HOME", str(tmp_path))
    monkeypatch.setattr(config, "HOME_DIR", tmp_path)
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(config, "LOGS_DIR", tmp_path / "logs")
    monkeypatch.setattr(config, "DOCTRINE_FILE",
                        tmp_path / "data" / "creator_doctrine.json")
    monkeypatch.setattr(config, "EARS_LOG_FILE", tmp_path / "logs" / "ears_log.jsonl")
    monkeypatch.setattr(config, "EARS_STATUS_FILE", tmp_path / "data" / "ears_status.json")
    config.ensure_dirs()
    from tests.fake_llama_server import start_fake_brain
    srv = start_fake_brain()
    monkeypatch.setattr(config, "BRAIN_URL", srv.base_url)
    agent = Agent(brain=BrainClient(brain_url=srv.base_url),
                  memory=Memory(data_dir=tmp_path / "data"),
                  doctrine="Тестовая доктрина")
    yield agent, srv
    srv.shutdown()


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


# ================================================================
# ФАЗА 2 — НЕ ПАДАТЬ
# ================================================================

def test_k7_serve_survives_crashing_tick(home, monkeypatch, capsys):
    """Доктрина модуля — «служба не умирает»: упавший тик не убивает
    процесс, урок записан, следующий тик живёт."""
    from core import drive
    calls = {"n": 0}

    def boom():
        calls["n"] += 1
        raise RuntimeError("расписание упало")

    monkeypatch.setattr(drive, "one_tick", boom)
    drive.serve(interval=0.001, max_ticks=3)
    out = capsys.readouterr().out
    assert calls["n"] == 3                       # все тики прожиты
    assert "служба живёт" in out                 # честно про падение


def test_h7_write_status_survives_broken_prev(home):
    """Битое сердце (число вместо ISO, список вместо jobs) — не смерть
    службы на втором тике."""
    from core import drive
    config.DRIVE_STATUS_FILE.write_text(json.dumps(
        {"brain_down_since": 42, "jobs": ["мусор", "вместо", "словаря"]}),
        encoding="utf-8")
    now = dt.datetime(2026, 11, 22, 12, 0)
    status = drive._write_status(False, [], now=now)   # не упало
    assert status["brain_down_since"] == now.isoformat(timespec="seconds")
    assert status["jobs"] == {}


def test_h2_diary_survives_null_ts(home):
    """Журнал уроков с "ts": null — дневник собирается, живые записи считаются."""
    from core.diary import _count_day_lines
    p = home / "data" / "evolution" / "journal.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join([
        json.dumps({"kind": "a", "ts": None}),
        json.dumps({"kind": "b", "ts": "2026-11-22T10:00:00"}),
        "вообще не json",
        json.dumps(["не", "словарь"]),
        json.dumps({"kind": "c", "ts": "2026-11-22T11:00:00"}),
    ]), encoding="utf-8")
    assert _count_day_lines(p, dt.date(2026, 11, 22)) == 2


def test_h3_load_env_disappearing_file(home, monkeypatch):
    """.env исчез между exists() и read_text() — калитка закрыта, не исключение."""
    from core import creator_gate
    (home / ".env").write_text("MARFA_CODEWORD=тайна\n", encoding="utf-8")

    def gone(self, *a, **k):
        raise FileNotFoundError("антивирус успел раньше")

    monkeypatch.setattr(Path, "read_text", gone)
    assert creator_gate.load_env() == {}
    assert creator_gate.check("тайна статус") == (False, None)  # путь обычный


def test_h6_brain_without_choices_is_honest_error():
    """200 с телом без choices — BrainError с диагнозом, а не KeyError
    под маской «мозг недоступен»."""
    from core.brain import BrainClient, BrainError
    client = BrainClient(brain_url="http://127.0.0.1:1")

    def weird(path, payload):
        return {"error": "server lost its mind"}

    client._post = weird
    with pytest.raises(BrainError) as ei:
        client.chat([{"role": "user", "content": "привет"}])
    assert "choices" in str(ei.value)


def test_m1_chat_zero_tokens_floored_at_one():
    """gen_tokens=0 — не пустой ответ сервера: нижняя граница 1 токен."""
    from tests.fake_llama_server import start_fake_brain
    from core.brain import BrainClient
    srv = start_fake_brain()
    try:
        client = BrainClient(brain_url=srv.base_url)
        client.chat([{"role": "user", "content": "привет"}], gen_tokens=0)
        assert srv.calls[-1]["max_tokens"] == 1
        client.chat([{"role": "user", "content": "привет"}], gen_tokens=-5)
        assert srv.calls[-1]["max_tokens"] == 1
    finally:
        srv.shutdown()


def test_n7_gate_tests_honest_without_pytest(home, monkeypatch):
    """pytest не установлен — «НЕ ЗАПУСКАЛИСЬ», а не «ЕСТЬ КРАСНЫЕ ТЕСТЫ»."""
    from core import creator_gate

    class R:
        returncode = 1
        stdout = ""
        stderr = "/usr/bin/python: No module named pytest"

    monkeypatch.setattr(creator_gate.subprocess, "run", lambda *a, **k: R())
    out = creator_gate._cmd_tests()
    assert "НЕ ЗАПУСКАЛИСЬ" in out
    assert "КРАСНЫЕ ТЕСТЫ" not in out.split("не красные")[0]   # не «красные»


def test_n8_drive_reuses_one_brain_client(home, monkeypatch):
    """Клиент мозга — один на жизнь службы; смена BRAIN_URL подхватывается."""
    from core import drive
    from core import brain as brain_mod
    made = []

    class FakeClient:
        def __init__(self, brain_url=""):
            made.append(brain_url or "default")
        def health(self):
            return True

    monkeypatch.setattr(brain_mod, "BrainClient", FakeClient)
    monkeypatch.setattr(drive, "_BRAIN_CACHE", (None, ""))
    assert drive._brain_ok() and drive._brain_ok()
    assert len(made) == 1                        # один на много тиков
    monkeypatch.setattr(config, "BRAIN_URL", "http://127.0.0.1:9")
    assert drive._brain_ok()
    assert len(made) == 2                        # переезд — новый клиент


# ================================================================
# ФАЗА 3 — НЕ ВРАТЬ
# ================================================================

def test_h1_diary_sees_iso_memories(home):
    """created_at ISO-строкой (ручная правка/импорт) — дневник ВИДИТ
    новые воспоминания, а не пишет «0» навсегда."""
    from core.diary import Diary
    day = dt.date(2026, 11, 22)
    mem = home / "data" / "memory"
    mem.mkdir(parents=True, exist_ok=True)
    (mem / "memory.json").write_text(json.dumps([
        {"text": "число", "created_at": dt.datetime(2026, 11, 22, 10, 0).timestamp()},
        {"text": "ISO-строка", "created_at": "2026-11-22T11:30:00"},
        {"text": "вчерашнее", "created_at": "2026-11-21T09:00:00"},
        {"text": "мусор", "created_at": "не дата вовсе"},
    ], ensure_ascii=False), encoding="utf-8")
    facts = Diary(data_dir=home / "data").collect_facts(day)
    assert facts.get("memory_new") == 2          # оба формата честно видны


def test_n1_voice_keeps_paragraphs():
    """Абзацы живого рассказа не слипаются в простыню."""
    from core.diary import _sanitize_voice
    raw = "Утро началось тихо. Я слушала дом.\n\nПотом Илья написал мне.\n\nМы поговорили."
    out = _sanitize_voice(raw)
    assert out.count("\n\n") == 2                # оба абзаца живы
    assert "Утро" in out and "поговорили" in out


def test_h4_parse_json_brace_inside_string():
    """Скобка } внутри строкового литерала — валидный ответ сенсора,
    а не «глаза ошибились»."""
    from core.eyes import parse_json
    d = parse_json('{"text": "закрываю } окно", "n": 1}')
    assert d == {"text": "закрываю } окно", "n": 1}
    d2 = parse_json('Вот ответ: {"a": "строка со } и { внутри", "b": {"c": 2}} и хвост')
    assert d2["b"]["c"] == 2
    d3 = parse_json('{"esc": "кавычка \\" и } после"}')
    assert d3["esc"] == 'кавычка " и } после'


def test_n5_disk_uninspectable_is_not_ok(home, monkeypatch):
    """«Не смогли посмотреть диск» — честное НЕ-ок, а не зелёная галочка."""
    from core import doctor

    def boom(path):
        raise OSError("диск спрятался")

    monkeypatch.setattr(doctor.shutil, "disk_usage", boom)
    report = doctor.check_all()
    c = report["checks"]["disk"]
    assert c["ok"] is False and "не посмотреть" in c["note"]


# ================================================================
# ФАЗА 4 — НЕ ВИСЕТЬ (+ M6 поднят из фазы 5: тот же файл доктора)
# ================================================================

def test_h5_ask_one_deadline_for_whole_chain(monkeypatch):
    """Висяк сенсора: цепочка грамматик ест ОДИН бюджет времени —
    3×240 с тишины (до 12 минут блокировки панели) больше невозможно."""
    import time as _time
    from core import eyes
    calls = []

    def slow_fail(body, timeout=None):
        calls.append(body.get("response_format", {}).get("type"))
        _time.sleep(0.05)
        raise RuntimeError("сенсор молчит")

    monkeypatch.setattr(eyes, "_post_chat", slow_fail)
    monkeypatch.setattr(eyes, "EYES_TIMEOUT", 0.06)
    t0 = _time.monotonic()
    with pytest.raises(RuntimeError) as ei:
        eyes._ask("b64", "промпт", {"type": "object"}, 10)
    assert _time.monotonic() - t0 < 0.5          # не 12 минут
    assert len(calls) <= 2                        # не вся цепочка
    assert "время вопроса вышло" in str(ei.value)  # честная причина


def test_n9_ask_reports_all_attempts(monkeypatch):
    """Обе попытки упали — в ошибке ОБЕ, а не только последняя."""
    from core import eyes

    def two_flavors(body, timeout=None):
        fmt = body.get("response_format", {}).get("type")
        if fmt == "json_schema":
            raise RuntimeError("схема отвергнута")
        raise RuntimeError("таймаут")

    monkeypatch.setattr(eyes, "_post_chat", two_flavors)
    with pytest.raises(RuntimeError) as ei:
        eyes._ask("b64", "промпт", {"type": "object"}, 10)
    msg = str(ei.value)
    assert "схема отвергнута" in msg and "таймаут" in msg


def test_m12_no_upscale():
    """Маленький экран/камера не растягиваются до 1280 — апскейл кормил
    сенсор лишними пикселями и секундами инференса."""
    Image = pytest.importorskip("PIL.Image")
    from core.eyes import _shrink
    small = Image.new("RGB", (800, 600))
    assert _shrink(small, 1280).size == (800, 600)     # не апскейлим
    big = Image.new("RGB", (1920, 1080))
    assert _shrink(big, 1280).size == (1280, 720)      # даунскейл жив


def test_m7_crit_servants_get_longer_timeout(monkeypatch):
    """Разогревающийся 30B (--mlock, 19 ГБ с диска) отвечает первые
    секунды медленно: crit-слуги — 10 с, warn — 2 с; поспешный «мозг
    мёртв» поднимал второго llama-server на том же порту."""
    from core import doctor
    seen = {}

    class _Resp:
        status = 200
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False

    def fake(url, timeout=None):
        seen[url] = timeout
        return _Resp()

    monkeypatch.setattr(doctor.urllib.request, "urlopen", fake)
    assert doctor._http_ok("http://127.0.0.1:8082/health")   # мозг — crit
    assert seen["http://127.0.0.1:8082/health"] == doctor.CRIT_CHECK_TIMEOUT_SECS
    assert doctor._http_ok("http://127.0.0.1:5001/api/status")  # панель — crit
    assert doctor._http_ok("http://127.0.0.1:8083/health")      # глаза — warn
    assert seen["http://127.0.0.1:8083/health"] == doctor.CHECK_TIMEOUT_SECS


def test_n6_urls_come_from_services_table(monkeypatch):
    """Порты осмотра — из таблицы SERVICES, мозг — из закона дома;
    переопределение BRAIN_URL (тест/переезд) уважается."""
    from core import doctor
    urls = doctor._service_urls()
    assert urls["eyes"] == "http://127.0.0.1:8083/health"
    assert urls["panel"] == "http://127.0.0.1:5001/api/status"
    monkeypatch.setattr(config, "BRAIN_URL", "http://127.0.0.1:9")
    assert doctor._service_urls()["brain"] == "http://127.0.0.1:9/health"


def test_m6_spawn_without_shell(monkeypatch):
    """Команда из start_marfa.json исполняется СПИСКОМ без shell —
    конфиг, подменённый через write_file, не становится RCE."""
    import subprocess as _sp
    from core import doctor
    spawned = []
    monkeypatch.setattr(doctor.subprocess, "Popen",
                        lambda argv, **kw: spawned.append((argv, kw)))
    doctor._spawn('venv\\Scripts\\python.exe -m flask --port 5001')
    argv, kw = spawned[0]
    assert argv == ["venv\\Scripts\\python.exe", "-m", "flask",
                    "--port", "5001"]
    assert kw.get("shell") is False
    with pytest.raises(ValueError):
        doctor._spawn("del C:\\Marfa & calc")     # метасимволы — отказ


def test_m6_split_cmd_keeps_windows_paths():
    """Слэши путей Windows живы, кавычки путей с пробелами сняты."""
    from core.doctor import _split_cmd
    assert _split_cmd("llama.cpp\\llama-server.exe -m models\\brain.gguf") == \
        ["llama.cpp\\llama-server.exe", "-m", "models\\brain.gguf"]
    assert _split_cmd('"C:\\Program Files\\app.exe" --flag') == \
        ["C:\\Program Files\\app.exe", "--flag"]


# ================================================================
# ФАЗА 5 — ГИГИЕНА И КОНТРАКТЫ
# ================================================================

def test_m10_append_thread_safe(home):
    """Два потока пишут одну сессию — оба хода живы (раньше: последний
    replace тихо затирал первого, Марфа «забывала» сообщение)."""
    import threading
    from core.dialog import DialogStore
    store = DialogStore(home / "data" / "dialog")
    n, workers = 20, 4

    def worker(k):
        for i in range(n):
            store.append("race", "user", "ход %d-%d" % (k, i))

    ts = [threading.Thread(target=worker, args=(k,)) for k in range(workers)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert len(store.turns("race")) == n * workers


def test_h9_render_accepts_content_key():
    """История в формате мозга ({role, content}) — валидна для рендера:
    опечатка в ключе не опустошает разговор молча."""
    from core.dialog import DialogStore
    turns = [{"role": "user", "content": "вопрос мозгового формата"},
             {"role": "assistant", "content": "ответ мозгового формата"}]
    msgs = DialogStore.render_messages(turns)
    assert msgs[-1]["content"] == "ответ мозгового формата"


def test_h9_ask_json_accepts_text_key():
    """DialogStore.turns (text) напрямую в ask_json — мозг видит историю."""
    from tests.fake_llama_server import start_fake_brain
    from core.brain import BrainClient
    srv = start_fake_brain()
    try:
        client = BrainClient(brain_url=srv.base_url)
        srv.reply_content = '{"answer": "ок"}'
        client.ask_json("вопрос", history=[
            {"role": "user", "text": "привет был"},
            {"role": "assistant", "text": "привет, Илья"},
        ])
        roles = [m["role"] for m in srv.calls[-1]["messages"]]
        assert "assistant" in roles            # история не отфильтровалась
        assert any("привет был" in m["content"]
                   for m in srv.calls[-1]["messages"])
    finally:
        srv.shutdown()


def test_h8_agent_prompt_under_law(agent_srv):
    """Промпт агентского трека — через Ф51: бюджет соблюдается, RAG
    (день-11: в хвосте хода, с потолком Ф78) не уезжает за контекст
    молча."""
    agent, srv = agent_srv
    for i in range(60):                        # жирные воспоминания
        agent.memory.remember("воспоминание %d: %s" % (i, "деталь " * 60))
    extra = agent._static_system()
    assert config.token_estimate(extra) <= config.PROMPT_BUDGET_TOKENS
    assert "ЗАКОН СКОРОСТИ" in extra           # ядро живо
    tail = agent._turn_context("о доме")
    # Ф78: хвост хода — состояние + НЕ БОЛЕЕ трёх воспоминаний в потолке,
    # жирная запись режется по границе слов с многоточием
    assert "ПАМЯТЬ" in tail
    assert tail.count("\n- ") + tail.count("\n– ") <= 3
    assert config.token_estimate(tail) <= 1000  # хвост не дороже истории
    srv.reply_content = '{"answer": "ок"}'
    agent.handle("расскажи о доме")
    sys_msg = next(m for m in srv.calls[-1]["messages"] if m["role"] == "system")
    assert config.token_estimate(sys_msg["content"]) <= config.PROMPT_BUDGET_TOKENS


def test_h8_oversized_doctrine_honest_reply(tmp_path, monkeypatch):
    """Доктрина-гигант — ЧП дома, но чат отвечает честно, а не 500-й."""
    monkeypatch.setenv("MARFA_HOME", str(tmp_path))
    monkeypatch.setattr(config, "HOME_DIR", tmp_path)
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(config, "LOGS_DIR", tmp_path / "logs")
    monkeypatch.setattr(config, "EARS_LOG_FILE", tmp_path / "logs" / "ears_log.jsonl")
    monkeypatch.setattr(config, "EARS_STATUS_FILE", tmp_path / "data" / "ears_status.json")
    config.ensure_dirs()
    from core.agent import Agent
    giant = "закон " * 2000                    # ~6600 ток — не влезает
    r = Agent(brain=None, memory=None, doctrine=giant).handle("расскажи о законах дома")
    assert r.source == "fallback"
    assert "архитектору" in r.text


def test_feature_task_command(home):
    """Фишка: «задача: ...» — в очередь и в СЕГОДНЯШНИЙ план (force),
    без будоража мозга; «задача была...» — не команда."""
    import datetime as dt
    from core.agent import Agent
    from core.autonomy import DayPlanner, load_queue
    from core import autonomy

    class NoBrain:
        def ask_json(self, *a, **k):
            raise AssertionError("задача — без мозга")

    # план дня уже построен (после 08:00) — новая задача должна войти в него
    planner = DayPlanner(data_dir=home / "data")
    planner.build_plan(day=dt.date.today(),
                       now=dt.datetime.now().replace(hour=12))
    agent = Agent(brain=NoBrain(), memory=None, doctrine="")
    r = agent.handle("задача: проверить микрофон до вечера")
    assert r.tool_used == "add_task"
    assert "проверить микрофон" in r.text
    assert any("проверить микрофон" in t["title"] for t in load_queue())
    plan = json.loads((home / "data"
                       / ("plan_%s.json" % dt.date.today().isoformat())).read_text(
                           encoding="utf-8"))
    assert any("проверить микрофон" in t["title"] for t in plan["tasks"])
    # обычная речь — не команда, уходит дальше по диспетчеру
    fast = agent._fast("задача была в том, чтобы проверить")
    assert fast is None


def test_feature_prompt_tokens_in_stamp(agent_srv):
    """Штамп несёт и промпт-токены: «165,8 с · 273 ток · промпт 2100» —
    долгий префикс отличим от долгого декода без консоли."""
    agent, srv = agent_srv
    srv.reply_content = '{"answer": "кратко"}'
    srv.usage_extra = {"prompt_tokens": 2100, "completion_tokens": 273}
    r = agent.handle("долгий вопрос")
    assert r.meta and r.meta.get("ptok") == 2100 and r.meta.get("tok") == 273


def test_n4_relative_marfa_home_anchored():
    """Относительный MARFA_HOME живёт от домашнего каталога пользователя —
    запуск из другой папки не переезжает дом."""
    from core.config import _resolve_home
    p = _resolve_home("data/marfa")
    assert p.is_absolute()
    assert str(p).startswith(str(Path.home()))
    assert _resolve_home(str(Path("/tmp") / "x")).is_absolute()
