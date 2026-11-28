# -*- coding: utf-8 -*-
r"""tests/test_masterskaya_circle.py — ЗОЛОТОЙ ЯКОРЬ КРУГА 25 «МАСТЕРСКАЯ».

Ф154–Ф158 (день-15, 26.11.2026). Круг закрыл роадмап 30 целиком
(№15 — последняя фишка) и дал Марфе взрослую мастерскую: диффы патчей,
броня применения (тесты после патча + автоОткат для КОГО УГОДНО),
стрим-канал панели и полный черновик эфира.

Якоря:
- Ф154: патч рождается вместе с patch.diff и счётчиками; «что меняет
  патч N» — сводка из фактов (строки, имена по AST), не пересказ LLM;
  «покажи патч N» — сам дифф; v1-патч без диффа — честная эпоха;
  обе команды живут ЧЕРЕЗ КАЛИТКУ agent.handle — мозг молчит;
- Ф155: «примени патч N» в той же броне, что «внедри»: красные тесты
  после записи = автоОткат; дым-тест гоняет тест модуля И привязанные
  (чей тест импортирует модуль — тот и задаёт поведение);
- Ф156: /api/chat/stream — кадры SSE (стадия → черновик → финал),
  финал несёт штамп и пишет диалог тем же законом, что /api/chat;
  ошибка хода — событие error, не тишина и не 500;
- Ф157: эфир хранит preview (хвост-400, совместимость) И draft
  (полный черновик, потолок 4000); подписчики эфира живут по закону
  «поломка подписчика не рвёт ход»;
- Ф158: роадмап 30 — 30 из 30 с ✅, ни одной выдуманной галочки.

Швы: _ask_coder / ensure_server / release / _smoke_test / _run_pytest
(repair), Agent / DIALOGS (web), ничего живого не поднимается.
"""
import json
import sys
import threading
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import agent, config, progress, repair  # noqa: E402
from core.agent import Agent  # noqa: E402
from core.dialog import DialogStore  # noqa: E402
from safety import guard  # noqa: E402

GOOD_CODE = "def greet():\n    return 'привет'\n"


@pytest.fixture
def home(tmp_path, monkeypatch):
    """Изолированный дом (паттерн test_repair): мастерская не трогает
    файлы станции."""
    monkeypatch.setattr(config, "HOME_DIR", tmp_path)
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(config, "LOGS_DIR", tmp_path / "logs")
    monkeypatch.setattr(config, "MODELS_DIR", tmp_path / "models")
    monkeypatch.setattr(config, "PATCHES_DIR", tmp_path / "data" / "patches")
    monkeypatch.setattr(config, "REPAIR_LOG_FILE",
                        tmp_path / "logs" / "repair_log.jsonl")
    monkeypatch.setattr(config, "GUARD_LOG_FILE",
                        tmp_path / "logs" / "guard_log.jsonl")
    monkeypatch.setattr(config, "CANARIES_FILE",
                        tmp_path / "data" / "canaries.json")
    monkeypatch.setattr(repair, "ensure_server",
                        lambda wait_secs=None: (True, "кодер на посту (шов)"))
    monkeypatch.setattr(repair, "release", lambda: "кодер лёг (шов)")
    progress.reset()
    return tmp_path


def _make_patch(n: int, target: Path, code: str, req="тест круга 25",
                with_diff: bool = True) -> Path:
    """Патч №N в песочнице руками (не через кодер) — как audit_round3.
    Дифф — честный: против СЕГОДНЯШНЕГО содержимого цели."""
    d = config.PATCHES_DIR / ("%04d" % n)
    d.mkdir(parents=True, exist_ok=True)
    (d / target.name).write_text(code, encoding="utf-8")
    meta = {"target": str(target), "file_name": target.name,
            "requirement": req, "applied": False}
    (d / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    if with_diff:
        old = (target.read_text(encoding="utf-8")
               if target.is_file() else "")
        (d / "patch.diff").write_text(
            repair._build_diff(old, code, target.name), encoding="utf-8")
    return d


# ================================================================
# Ф154 «ДИФФ ПАТЧА»
# ================================================================

def test_f154_make_patch_born_with_diff(home, monkeypatch):
    """Патч рождается вместе с patch.diff и счётчиками строк в meta."""
    target = home / "core" / "calc.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("OLD = 1\n", encoding="utf-8")
    monkeypatch.setattr(repair, "_ask_coder", lambda prompt, max_tokens=None:
                        "```python\nNEW = 2\nNEW2 = 3\n```")
    out = repair.make_patch("core/calc.py", "переписать константу")
    assert "ГОТОВ" in out
    d = config.PATCHES_DIR / "0001"
    diff = (d / "patch.diff").read_text(encoding="utf-8")
    assert "было/calc.py" in diff and "стало/calc.py" in diff
    assert "-OLD = 1" in diff and "+NEW = 2" in diff
    meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
    assert meta["added"] == 2 and meta["removed"] == 1
    # дифф и сводка согласны друг с другом
    assert (meta["added"], meta["removed"]) == repair._diff_stats(diff)


def test_f154_make_patch_new_file_all_plus(home, monkeypatch):
    """Новый файл — дифф весь в плюсах, минусов нет."""
    monkeypatch.setattr(repair, "_ask_coder", lambda prompt, max_tokens=None:
                        "```python\n" + GOOD_CODE + "```")
    repair.make_patch("scripts/fresh.py", "новый файл")
    d = config.PATCHES_DIR / "0001"
    diff = (d / "patch.diff").read_text(encoding="utf-8")
    add, rem = repair._diff_stats(diff)
    assert add >= 1 and rem == 0
    meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
    assert meta["new_file"] is True and meta["removed"] == 0


def test_f154_summary_is_facts_not_opinion(home):
    """«что меняет патч N»: строки, имена (новые/задеты), требование,
    статус — из диффа и AST, без единого слова LLM."""
    target = home / "core" / "voice.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("def speak():\n    return 1\n\ndef old():\n    pass\n",
                      encoding="utf-8")
    _make_patch(1, target,
                "def speak():\n    return 2\n\ndef throat():\n    pass\n")
    s = repair.patch_summary(1)
    assert "+2 −2 строк" in s
    assert "throat (новые)" in s or "throat" in s and "(нов" in s
    assert "speak" in s and "(задеты)" in s
    assert "old" in s and "(ушли)" in s
    assert "тест круга 25" in s
    assert "ждёт внедрения" in s
    assert "покажи патч 0001" in s


def test_f154_summary_missing_honest(home):
    """Нет патча — честный отказ со путём лечения."""
    assert "патча №9 нет" in repair.patch_summary(9)
    assert "патча №9 нет" in repair.patch_diff(9)


def test_f154_show_diff_returns_diff(home):
    """«покажи патч N» — сам дифф, с шапками было/стало."""
    target = home / "core" / "calc.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("OLD = 1\n", encoding="utf-8")
    _make_patch(1, target, "NEW = 2\n")
    text = repair.patch_diff(1)
    assert "было/calc.py" in text
    assert "+NEW = 2" in text and "-OLD = 1" in text


def test_f154_v1_patch_epoch_is_honest(home):
    """Патч круга до диффов (v1, без patch.diff) — эпоха названа,
    свежий дифф собирается из бэкапа, правда не выдумана."""
    target = home / "core" / "calc.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("OLD = 1\n", encoding="utf-8")
    d = _make_patch(1, target, "NEW = 2\n", with_diff=False)
    (d / "backup_calc.py").write_text("OLD = 1\n", encoding="utf-8")
    s = repair.patch_summary(1)
    assert "не сохранялся" in s          # эпоха названа честно
    assert "+1 −1 строк" in s            # факты те же
    text = repair.patch_diff(1)
    assert "дифф не сохранился" in text
    assert "+NEW = 2" in text


def test_f154_routes_through_gate(home, monkeypatch):
    """Обе команды — ЧЕРЕЗ КАЛИТКУ agent.handle: мозг молчит (пробник
    круга 24: мёртвая ветка не отвечает чужим голосом)."""
    target = home / "core" / "calc.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("OLD = 1\n", encoding="utf-8")
    _make_patch(1, target, "NEW = 2\n")

    class FakeBrain:
        calls = 0

        def ask_json(self, *a, **kw):
            self.calls += 1
            return {"answer": "мозг"}

    class FakeMemory:
        def recall(self, *a, **kw):
            return []

    a = Agent(brain=FakeBrain(), memory=FakeMemory(),
              doctrine="Тестовая доктрина")
    r1 = a.handle("что меняет патч 1")
    assert r1 is not None and "+1 −1 строк" in r1.text
    r2 = a.handle("покажи патч 1")
    assert r2 is not None and "было/calc.py" in r2.text
    assert a.brain.calls == 0, "рефлекс диффа обязан жить без мозга"


# ================================================================
# Ф155 «БРОНЯ ПРИМЕНЕНИЯ»
# ================================================================

def test_f155_related_tests_by_import(home):
    """Привязанные тесты — по строкам импортов: from core import X,
    from core.X import — да; «voices» рядом с «voice» — нет; свой
    тест не дублируется; потолок 3 файла."""
    tdir = home / "tests"
    tdir.mkdir(parents=True)
    (tdir / "test_voice.py").write_text("", encoding="utf-8")
    (tdir / "test_a.py").write_text(
        "from core import voice\n", encoding="utf-8")
    (tdir / "test_b.py").write_text(
        "from core.voice import speak\n", encoding="utf-8")
    (tdir / "test_c.py").write_text(
        "from core import voice as v, agent\n", encoding="utf-8")
    (tdir / "test_d.py").write_text(
        "from core import voices\n", encoding="utf-8")   # не то слово
    (tdir / "test_e.py").write_text("import json\n", encoding="utf-8")
    got = repair._related_tests("voice")
    assert "test_a.py" in got and "test_b.py" in got and "test_c.py" in got
    assert "test_voice.py" not in got     # свой уже в прогоне
    assert "test_d.py" not in got         # жадный префикс не прошёл
    assert len(got) == 3                  # потолок limit


def test_f155_apply_green_reports_tests(home, monkeypatch):
    """Зелёный прогон — патч применён, отчёт называет тесты."""
    target = home / "core" / "calc.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("OLD = 1\n", encoding="utf-8")
    _make_patch(1, target, "NEW = 2\n")
    monkeypatch.setattr(repair, "_smoke_test",
                        lambda t: (True, "pytest test_calc.py (код 0)\n2 passed"))
    out = repair.apply_patch(1)
    assert "ПРИМЕНЁН" in out
    assert "тесты после патча зелёные" in out
    assert target.read_text(encoding="utf-8") == "NEW = 2\n"
    meta = json.loads((config.PATCHES_DIR / "0001" / "meta.json")
                      .read_text(encoding="utf-8"))
    assert meta["applied"] is True


def test_f155_apply_red_rolls_back(home, monkeypatch):
    """ГЛАВНЫЙ: красные тесты после применения — автоОткат, файл на
    месте, meta честна. Броня — не для одного пути: Создателю как
    Марфе (Ф75)."""
    target = home / "core" / "calc.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("OLD = 1\n", encoding="utf-8")
    _make_patch(1, target, "NEW = 2\n")
    monkeypatch.setattr(repair, "_smoke_test",
                        lambda t: (False, "pytest test_calc.py (код 1)\n1 failed"))
    out = repair.apply_patch(1)
    assert "НЕ ПРИМЕНЁН" in out
    assert "я вернула на место" in out
    assert "1 failed" in out               # отчёт теста — в ответе
    assert target.read_text(encoding="utf-8") == "OLD = 1\n"
    meta = json.loads((config.PATCHES_DIR / "0001" / "meta.json")
                      .read_text(encoding="utf-8"))
    assert meta["applied"] is False


def test_f155_smoke_runs_own_and_related(home, monkeypatch):
    r"""Дым-тест v2: свой тест + привязанные в ОДНОМ прогоне.

    День-18 (продление якоря): путь тестов — tests\<имя>, не голое
    имя: станция словила «код 4, no tests ran» — pytest бежит из
    корня дома, где тестов нет."""
    tdir = home / "tests"
    tdir.mkdir(parents=True)
    (tdir / "test_calc.py").write_text("def test_x():\n    pass\n",
                                       encoding="utf-8")
    (tdir / "test_user.py").write_text(
        "from core import calc\n", encoding="utf-8")
    seen = {}

    def fake_run(files, timeout):
        seen["files"] = list(files)
        return 0, "3 passed"

    monkeypatch.setattr(repair, "_run_pytest", fake_run)
    ok, report = repair._smoke_test(home / "core" / "calc.py")
    assert ok is True
    assert seen["files"] == ["tests/test_calc.py", "tests/test_user.py"]
    assert "tests/test_calc.py tests/test_user.py" in report


def test_f155_smoke_no_tests_compiles(home):
    """Тестов нет — хотя бы компиляция (закон v1 жив)."""
    target = home / "core" / "lone.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("x = 1\n", encoding="utf-8")
    ok, report = repair._smoke_test(target)
    assert ok is True and "компиляция ОК" in report


def test_f155_self_apply_gets_related_too(home, monkeypatch):
    """self_apply (Ф75) на том же конвейере — привязанные тесты
    летят и ему (броня общая, пути разные)."""
    tdir = home / "tests"
    tdir.mkdir(parents=True)
    (tdir / "test_user.py").write_text(
        "from core import calc\n", encoding="utf-8")
    target = home / "core" / "calc.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("OLD = 1\n", encoding="utf-8")
    _make_patch(1, target, "NEW = 2\n")
    repair.allow_self_write()
    seen = {}

    def fake_run(files, timeout):
        seen["files"] = list(files)
        return 1, "1 failed"

    monkeypatch.setattr(repair, "_run_pytest", fake_run)
    out = repair.self_apply(1)
    assert "НЕ ВНЕДРЁН" in out
    assert seen["files"] == ["tests/test_user.py"]   # своего теста нет —
    # привязанный один (tests\<имя> — день-18); красный — откат
    assert target.read_text(encoding="utf-8") == "OLD = 1\n"


# ================================================================
# Ф157 «ПОЛНЫЙ ЧЕРНОВИК»
# ================================================================

def test_f157_draft_full_and_preview_tail():
    """Два взгляда: preview — хвост-400 (совместимость v1), draft —
    полный растущий черновик. Начало длинного ответа не теряется
    молча — честное «…»."""
    progress.reset()
    progress.begin("s")
    long_text = "А" * 300 + "Б" * 300           # 600 символов
    progress.preview(long_text)
    snap = progress.snapshot("s")
    assert snap["preview"].startswith("…")
    assert len(snap["preview"]) <= 401
    assert snap["draft"] == long_text            # целиком
    assert progress.draft() == long_text
    progress.finish(1.0, "brain")
    assert progress.draft() == ""                # ход кончился — чисто


def test_f157_draft_cap_4000():
    """Потолок 4000: сверхдлинный черновик не растёт без границ."""
    progress.reset()
    progress.begin("s")
    progress.preview("Я" * 5000)
    snap = progress.snapshot("s")
    assert len(snap["draft"]) <= 4001
    assert snap["draft"].startswith("…")
    progress.finish()


def test_f157_subscriber_lifecycle():
    """Подписчик слышит стадию и ПОЛНЫЙ черновик; отписка глушит."""
    progress.reset()
    events = []
    cb = lambda kind, payload: events.append((kind, payload))  # noqa: E731
    progress.subscribe(cb)
    progress.subscribe(cb)                     # дубль — один раз
    progress.begin("s")
    progress.stage("мозг думает…")
    progress.preview("первые буквы")
    progress.unsubscribe(cb)
    progress.preview("вторые буквы")           # уже не слышно
    kinds = [k for k, _ in events]
    assert kinds == ["stage", "stage", "preview"]
    assert events[-1][1] == "первые буквы"
    progress.finish()


def test_f157_bad_listener_cannot_break_walk():
    """Закон эфира: подписчик-вредитель глотается — ход живёт."""
    progress.reset()
    progress.subscribe(lambda k, p: 1 / 0)
    progress.begin("s")
    progress.stage("стадия жива")              # не упало
    progress.preview("черновик жив")
    snap = progress.snapshot("s")
    assert snap["stage"] == "стадия жива"
    assert snap["draft"] == "черновик жив"
    progress.finish()


def test_f157_snapshot_compat():
    """Совместимость: старые поля на месте — клиенты v1 не заметили."""
    progress.reset()
    progress.begin("sid1")
    snap = progress.snapshot("sid1")
    for key in ("busy", "sid", "stage", "preview", "elapsed",
                "stage_secs", "mine", "last"):
        assert key in snap, "пропало поле %s — старый клиент сломается" % key
    assert snap["busy"] is True and snap["mine"] is True
    progress.finish()
    assert progress.snapshot("sid1")["busy"] is False


# ================================================================
# Ф156 «СТРИМ-КАНАЛ» (№15 роадмапа 30)
# ================================================================

class _FakeReply:
    def __init__(self, text, source="brain", meta=None):
        self.text = text
        self.source = source
        self.meta = meta or {}


class _StreamAgent:
    """Живой агент шва: стадия → растущий черновик → финал."""

    def handle(self, text, history=None):
        progress.stage("мозг думает…")
        progress.preview("Первая")
        progress.preview("Первая фраза ответа")
        return _FakeReply("Первая фраза ответа", "brain",
                          {"tok": 42, "ptok": 2100})


class _DeadAgent:
    def handle(self, text, history=None):
        raise RuntimeError("мозг недоступен (шов)")


def _sse_frames(resp):
    """Кадры SSE из ответа: список dict'ов из data:-строк."""
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers.get("Content-Type", "")
    frames = []
    for line in resp.get_data(as_text=True).splitlines():
        if line.startswith("data: "):
            frames.append(json.loads(line[6:]))
    return frames


@pytest.fixture
def webhome(home, monkeypatch, tmp_path):
    """Панель в изоляции: агент и диалог — швы, дом — tmp."""
    from web import app as webapp
    monkeypatch.setattr(webapp, "Agent", lambda: _StreamAgent())
    monkeypatch.setattr(webapp, "DIALOGS",
                        DialogStore(home / "data" / "dialog"))
    progress.reset()
    webapp._TEST_WEBHOME = True
    yield webapp
    progress.reset()


def test_f156_stream_stage_preview_final(webhome):
    """Кадры по порядку: стадия → черновик (растёт) → финал со штампом.
    Буквы печатаются живьём — без единого опроса."""
    client = webhome.app.test_client()
    frames = _sse_frames(
        client.post("/api/chat/stream",
                    json={"text": "привет", "session": "krug25"}))
    kinds = [f.get("type") for f in frames]
    assert kinds[0] == "stage"                     # begin — первый кадр
    assert "stage" in kinds and "preview" in kinds
    previews = [f["text"] for f in frames if f.get("type") == "preview"]
    assert previews == ["Первая", "Первая фраза ответа"]   # рост
    finals = [f for f in frames if f.get("type") == "final"]
    assert len(finals) == 1
    fin = finals[0]
    assert fin["reply"] == "Первая фраза ответа"
    assert "<p>" in fin["html"]                    # безопасный HTML (№12)
    assert fin["source_label"] == "мозг"
    assert fin["tok"] == 42 and fin["ptok"] == 2100   # штамп цел


def test_f156_stream_writes_dialog_same_law(webhome):
    """Диалог — тем же законом, что /api/chat: оба хода, штамп в
    памяти (F5 ответа не рвёт)."""
    client = webhome.app.test_client()
    _sse_frames(client.post("/api/chat/stream",
                            json={"text": "вопрос", "session": "krug25"}))
    turns = webhome.DIALOGS.turns("krug25")
    assert [t["role"] for t in turns] == ["user", "assistant"]
    meta = turns[1].get("meta") or {}
    assert meta.get("src") == "brain"
    assert meta.get("tok") == 42


def test_f156_stream_error_is_event_not_silence(webhome, monkeypatch):
    """Крах хода — событие error (не 500 и не тишина), диалог не
    отравлен неудачей (закон /api/chat)."""
    monkeypatch.setattr(webhome, "Agent", lambda: _DeadAgent())
    client = webhome.app.test_client()
    frames = _sse_frames(
        client.post("/api/chat/stream",
                    json={"text": "упади", "session": "krug25"}))
    assert frames[-1]["type"] == "error"
    assert "мозг недоступен" in frames[-1]["error"]
    assert webhome.DIALOGS.turns("krug25") == []   # память чиста


def test_f156_stream_empty_text_is_400(webhome):
    """Пустой текст — честный 400 JSON (стрим не начинается)."""
    client = webhome.app.test_client()
    r = client.post("/api/chat/stream", json={"text": "  ", "session": "x"})
    assert r.status_code == 400


def test_f156_classic_channel_untouched(webhome):
    """Старый /api/chat жив и тем же законом (фоллбэк-честность):
    поля финала стрима и ответа классики — один в один."""
    client = webhome.app.test_client()
    r_classic = client.post("/api/chat",
                            json={"text": "привет", "session": "classic"})
    assert r_classic.status_code == 200
    classic = r_classic.get_json()
    frames = _sse_frames(
        client.post("/api/chat/stream",
                    json={"text": "привет", "session": "krug25"}))
    fin = [f for f in frames if f.get("type") == "final"][0]
    assert set(classic.keys()) == set(fin.keys()) - {"type"}


def test_f156_turn_runs_in_worker_thread(webhome):
    """Ход крутится в потоке — канал не держит панель: события эфира
    из другого потока долетают в стрим (подписка — общий эфир)."""
    seen_threads = []

    class ThreadSpy(_StreamAgent):
        def handle(self, text, history=None):
            seen_threads.append(threading.current_thread().name)
            return _StreamAgent.handle(self, text, history)

    webhome.Agent = lambda: ThreadSpy()
    client = webhome.app.test_client()
    _sse_frames(client.post("/api/chat/stream",
                            json={"text": "кто я", "session": "krug25"}))
    assert seen_threads and seen_threads[0] != "MainThread"


# ================================================================
# Ф158 «РОАДМАП 30/30»
# ================================================================

ROADMAP = Path(__file__).resolve().parents[1] / "docs" / "ROADMAP_30.md"


def test_f158_roadmap_all_30_delivered():
    """Все 30 фишек — с ✅; ни одной выдуманной галочки: якорь парсит
    документ и требует 30 пронумерованных пунктов, каждый закрыт."""
    text = ROADMAP.read_text(encoding="utf-8")
    # раздел фишек — до круговых сессий
    head = text.split("## Круги М и Д")[0]
    items = {}
    for m in __import__("re").finditer(
            r"^(\d+)\. \*\*(.+?)\*\*(.*?)(?=^\d+\. |^## |\Z)",
            head, __import__("re").M | __import__("re").S):
        items[int(m.group(1))] = m.group(3)
    assert sorted(items) == list(range(1, 31)), \
        "в роадмапе должны быть все 30 фишек, найдено: %s" % sorted(items)
    open_items = [n for n, body in items.items() if "✅" not in body]
    assert open_items == [], "фишки без галочки: %s" % open_items


def test_f158_roadmap_says_30_of_30():
    """Книга называет закрытие прямо: «30 из 30 доставлено»."""
    text = ROADMAP.read_text(encoding="utf-8")
    assert "30 из 30 доставлено" in text
    assert "круг 25" in text.lower()


def test_f158_circle_section_present():
    """Раздел круга 25 — в книге роадмапа, все пять фишек названы."""
    text = ROADMAP.read_text(encoding="utf-8")
    assert "Круг 25 «МАСТЕРСКАЯ»" in text
    for tag in ("Ф154", "Ф155", "Ф156", "Ф157", "Ф158"):
        assert tag in text, "в роадмапе нет %s" % tag
