# -*- coding: utf-8 -*-
r"""tests/test_self_knowledge.py — самопознание v2 (Г-2.3) + таймаут-закон.

Переписка Создателя с Марфой (22.11.2026) вскрыла три болезни одним
разговором:

    «Изучи себя»          → мозг недоступен: timed out
    «Попробуй изучить»    → неизвестный инструмент: filesystem  (трижды)
    «ЧТО ты умеешь?»      → общие слова, ничего о доме

Якоря лечения: манифест возможностей в промпте (мозг знает ТОЧНЫЕ
имена инструментов и команд), быстрая команда «изучи себя» (честный
динамический отчёт без LLM), уши в ЯДРЕ и состоянии дома, меню при
неизвестном инструменте, таймаут мозга из закона дома + человеческая
подсказка при timed out.
"""
import re
from pathlib import Path

import core.config as config
from core.agent import Agent, IDENTITY, _house_state
from core.brain import BrainClient, BrainError
from core.identity import (TOOLS, capabilities_report, ears_alive,
                           ears_diagnosis, manifest, tool_names)
from core.memory import Memory


# ---------- заглушки ----------

class _NoBrain:
    """Мозг-заглушка: быстрые команды не должны будить 30B."""

    def ask_json(self, *a, **kw):
        raise AssertionError("тест не должен будить мозг")


class _Mem:
    """Память-заглушка: без воспоминаний, но умеет считать себя."""

    def __init__(self, n=None):
        self._n = n

    def recall(self, query, top_k=3):
        return []

    def remember(self, text):
        pass

    def count(self):
        if self._n is None:
            raise AssertionError("считать не просили")
        return self._n


class _ActionBrain:
    """Мозг, который сразу зовёт инструмент (любой)."""

    def __init__(self, tool):
        self.tool = tool

    def ask_json(self, *a, **kw):
        return {"action": {"tool": self.tool, "args": {}}}


class _TimeoutBrain:
    """Мозг, думающий дольше таймаута."""

    def ask_json(self, *a, **kw):
        raise BrainError("timed out")


def _agent(brain=None, memory=None):
    return Agent(brain=brain or _NoBrain(), memory=memory or _Mem(),
                 doctrine="ДОКТРИНА-ТЕСТ")


def _flat(text: str) -> str:
    """Нормализация пробелов: перенос строки в доке не должен рвать якорь."""
    return re.sub(r"\s+", " ", text)


# ---------- отчёт «изучи себя» ----------

def test_report_knows_self():
    """Отчёт называет: имя, Создателя, мозг, глаза, уши, команды, инструменты."""
    r = capabilities_report(memory=_Mem(7), eyes_ok=True, ears_ok=True)
    for fact in ("Марфа", "Илья", "Qwen3-30B", "Qwen2.5-VL", "vosk",
                 "посмотри", "read_file", "вспомни"):
        assert fact in r, "в отчёте нет: " + fact


def test_report_honest_about_dead_senses():
    """Мёртвые чувства называются мёртвыми — без фантазий о зрении и слухе.
    v2: уши называют ПРИЧИНУ (диагноз из статуса службы), а не
    отговорку «молчит или микрофона нет»."""
    r = capabilities_report(memory=None, eyes_ok=False, ears_ok=False)
    assert "НЕ запущены" in r
    assert "не слышу" in r
    r_live = capabilities_report(memory=None, eyes_ok=True, ears_ok=True)
    assert "живы" in r_live and "жив" in r_live


def test_report_counts_memory_or_says_plain():
    """Память с count() — цифра; без памяти — честно без цифры, но не падает."""
    r = capabilities_report(memory=_Mem(7))
    assert "живых записей: 7" in r
    r_plain = capabilities_report(memory=None)
    assert "живых записей" not in r_plain
    assert "Память" in r_plain


def test_report_names_limits_honestly():
    """«Чего не умею» — прямо: без резолюции руки не двигаются,
    голоса нет, кириллицу руками не печатаю. Обещать нельзя."""
    r = capabilities_report(memory=None, eyes_ok=False, ears_ok=False).lower()
    assert "чего не умею" in r
    assert "голосом" in r
    assert "filesystem" in r  # чужое имя помечено чужим
    assert "не двигают мышью" in r   # руки — только по резолюции Создателя


def test_report_tells_hands_truth(tmp_path, monkeypatch):
    """Руки v2 «единое зрение»: своей модели нет — координаты глаз;
    без резолюции — сухой режим, с резолюцией — честное «ВКЛЮЧЕНА»."""
    monkeypatch.setattr(config, "HANDS_ENABLED_FILE",
                        tmp_path / "нет_резолюции.json")
    r = capabilities_report(memory=None, eyes_ok=True, ears_ok=True)
    assert "координатах глаз" in r            # единое зрение
    assert "сухой режим" in r                 # без резолюции — только план
    assert "UI-TARS" not in r                 # своя модель больше не нужна
    monkeypatch.setattr(config, "HANDS_ENABLED_FILE",
                        tmp_path / "есть_резолюция.json")
    (tmp_path / "есть_резолюция.json").write_text("{}", encoding="utf-8")
    r2 = capabilities_report(memory=None, eyes_ok=True, ears_ok=True)
    assert "ВКЛЮЧЕНА" in r2


def test_tools_are_single_source_of_truth():
    """Имена инструментов и их описания едут из одного списка TOOLS."""
    assert tool_names() == ", ".join(name for name, _ in TOOLS)
    assert len(TOOLS) >= 6                # v2: + ui_action (руки)
    for name, what in TOOLS:
        assert name in manifest() and what in capabilities_report(
            memory=None, eyes_ok=False, ears_ok=False)


def test_ui_action_tool_exists():
    """v2: мозг может ДОВЕРИТЬ задание рукам — но не координаты."""
    names = [name for name, _ in TOOLS]
    assert "ui_action" in names


# ---------- манифест в системном промпте ----------

def test_manifest_lists_exact_tool_names():
    """Мозг видит в промпте ТОЧНЫЕ имена инструментов и запрет выдумывать."""
    extra = _agent()._static_system()
    assert "МОИ ВОЗМОЖНОСТИ" in extra
    for name in ("read_file", "write_file", "run_python",
                 "browser_search", "check_brackets"):
        assert name in extra, "в промпте нет инструмента: " + name
    assert "не выдумывай" in extra.lower()


def test_manifest_static_prefix_for_kv_cache():
    """День-11 (Ф77): система — ТОЛЬКО статика: ЯДРО -> СТРОЙНЫЙ манифест
    -> доктрина. Часы и RAG уехали в хвост хода — префикс не меняется
    от сообщения к сообщению, KV-кэш сервера живёт."""
    extra = _agent()._static_system()
    i_core = extra.index("ЯДРО — кто я")
    i_manifest = extra.index("МОИ ВОЗМОЖНОСТИ")
    i_doctrine = extra.index("ДОКТРИНА-ТЕСТ")
    assert i_core < i_manifest < i_doctrine
    assert "Состояние дома" not in extra     # подвижное — не в системе
    tail = _agent()._turn_context("привет")
    assert "Состояние дома" in tail          # оно — в хвосте хода
    assert extra == _agent()._static_system()  # система статична между ходами


def test_manifest_mentions_fast_commands():
    """Мозг знает быстрые команды дома — чтобы подсказывать, а не фантазировать."""
    extra = _agent()._static_system()
    for cmd in ("посмотри", "помни", "подведи день", "сколько ты не спала",
                "посмотри в камеру", "руки <задача>"):
        assert cmd in extra, "в манифесте нет команды: " + cmd


def test_manifest_warns_about_dry_hands():
    """Мозг знает: без резолюции Создателя руки не кликают — и не
    говорит Создателю «уже нажала»."""
    extra = _agent()._static_system().lower()
    assert "сухом режиме" in extra
    assert "уже нажала" in extra


# ---------- поведение агента ----------

def test_fast_self_inspect_no_brain():
    """«Изучи себя» — быстрая: мозг молчит, отчёт от Python."""
    r = _agent().handle("изучи себя")
    assert r.source == "python" and r.tool_used == "self_inspect"
    assert "Марфа" in r.text and "Qwen3-30B" in r.text


def test_variants_of_self_question():
    """Формулировки Создателя разные — команда одна."""
    for phrase in ("что ты умеешь", "кто ты", "расскажи о себе",
                   "твои возможности", "что умеешь"):
        r = _agent().handle(phrase)
        assert r.source == "python" and r.tool_used == "self_inspect", phrase


def test_unknown_tool_gets_menu():
    """«filesystem» → не голый отказ, а меню настоящих имён."""
    r = _agent(brain=_ActionBrain("filesystem")).handle("изучи свои файлы")
    assert "неизвестный инструмент: filesystem" in r.text
    assert "read_file" in r.text and "write_file" in r.text


def test_identity_mentions_ears_truth():
    """ЯДРО — правда о теле: уши ЖИВУТ (не «впереди»), голоса нет, есть «изучи себя»."""
    assert "уши vosk" in IDENTITY
    assert "Уши и голос — впереди" not in IDENTITY   # устаревшая строка умерла
    assert "изучи себя" in IDENTITY


def test_house_state_knows_ears():
    """Состояние дома для мозга включает уши — живые или честно молчащие."""
    assert "уши:" in _house_state()


# ---------- таймаут мозга ----------

def test_brain_timeout_is_law_of_house(monkeypatch):
    """Таймаут едет из закона дома: 300 сек, и _post реально их использует."""
    assert config.BRAIN_TIMEOUT_SEC == 300
    captured = {}

    class _Resp:
        status = 200

        def read(self):
            return b'{"choices": [{"message": {"content": "ok"}}]}'

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(req, timeout=None, **kw):
        captured["timeout"] = timeout
        return _Resp()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    BrainClient().chat([{"role": "user", "content": "привет"}])
    assert captured["timeout"] == config.BRAIN_TIMEOUT_SEC


def test_timeout_note_is_human():
    """timed out → человеческое объяснение, а не голый технический обрыв."""
    r = _agent(brain=_TimeoutBrain()).handle("расскажи длинную историю")
    assert "мозг недоступен" in r.text and r.source == "fallback"
    assert "не поломка" in r.text
    assert "300" in r.text          # сколько честно ждали
    assert "timed out" in r.text    # исходная техническая правда не спрятана


# ---------- память: число живых записей ----------

def test_memory_count_alive_only(tmp_path):
    """count() считает живых: истёкшие записи не притворяются памятью."""
    mem = Memory(data_dir=tmp_path, ttl_hours=1.0)
    mem.remember("первый факт")
    mem.remember("второй факт")
    mem.remember("просроченное", ttl_hours=-0.01)   # expire_at в прошлом
    assert mem.count() == 2


# ---------- уши: живость по сердцебиению ----------

def test_ears_alive_reads_heartbeat(tmp_path, monkeypatch):
    """Свежее сердцебиение «ok» — ухо живо; старое или «no_mic» — молчит."""
    import datetime as dt
    import json
    status = tmp_path / "ears_status.json"

    def write(state, ts, device=""):
        rec = {"ts": ts.isoformat(timespec="seconds"), "state": state}
        if device:
            rec["device"] = device
        status.write_text(json.dumps(rec), encoding="utf-8")

    monkeypatch.setattr(config, "EARS_STATUS_FILE", status)
    write("ok", dt.datetime.now())
    assert ears_alive() is True
    write("ok", dt.datetime.now() - dt.timedelta(minutes=10))
    assert ears_alive() is False            # сердца нет 10 минут
    write("no_mic", dt.datetime.now())
    assert ears_alive() is False            # честно: не слышу
    status.unlink()
    assert ears_alive() is False            # файла нет — тоже не слышу


# ---------- уши v2: диагноз называет ПРИЧИНУ ----------

def test_ears_diagnosis_names_the_reason(tmp_path, monkeypatch):
    """Урок 22.11: «молчит или микрофона нет» — отговорка; служба знает
    точную причину, и Марфа называет её Создателю."""
    import datetime as dt
    import json
    from core.identity import ears_diagnosis
    status = tmp_path / "ears_status.json"

    def write(state, ts, error="", device=""):
        rec = {"ts": ts.isoformat(timespec="seconds"), "state": state}
        if error:
            rec["error"] = error
        if device:
            rec["device"] = device
        status.write_text(json.dumps(rec, ensure_ascii=False),
                          encoding="utf-8")

    monkeypatch.setattr(config, "EARS_STATUS_FILE", status)
    write("ok", dt.datetime.now(), device="HD WebCam Mic")
    d = ears_diagnosis()
    assert "живы" in d and "HD WebCam Mic" in d   # каким устройством слушает
    write("no_mic", dt.datetime.now(), error="PortAudio error -9996")
    assert "микрофон не найден" in ears_diagnosis()
    write("no_model", dt.datetime.now())
    assert "85_fix_ears" in ears_diagnosis()       # что чинить
    write("no_sounddevice", dt.datetime.now())
    assert "sounddevice" in ears_diagnosis()
    write("ok", dt.datetime.now() - dt.timedelta(minutes=10))
    assert "сердце" in ears_diagnosis() and "замерло" in ears_diagnosis()
    status.unlink()
    assert "не запущена" in ears_diagnosis()


# ---------- якоря на книгу дома ----------

def test_manual_teaches_the_symptoms():
    """РУКОВОДСТВО, раздел 9: переписка 22.11 разложена по графам таблицы."""
    text = _flat(Path("docs/РУКОВОДСТВО_СОЗДАТЕЛЯ.md").read_text(encoding="utf-8"))
    for anchor in ("timed out", "filesystem", "изучи себя"):
        assert anchor in text, "в РУКОВОДСТВЕ нет: " + anchor


def test_roadmap_has_self_knowledge_circle():
    """ROADMAP_30 знает о фишке самопознания."""
    text = _flat(Path("docs/ROADMAP_30.md").read_text(encoding="utf-8"))
    assert "Самопознание" in text
    assert "изучи себя" in text


def test_roadmap_has_eyes_v2_and_hands():
    """Круг Р и глаза v2 записаны в карту: попугай промпта, руки-слуга."""
    text = _flat(Path("docs/ROADMAP_30.md").read_text(encoding="utf-8"))
    assert "Глаза v2" in text
    assert "антипопугай" in text.lower() or "попугай" in text
    assert "руки, экзамен" in text            # Р-0 — команда экзамена


def test_manual_teaches_hands_and_camera():
    """РУКОВОДСТВО: кнопка 91 (резолюция на моторику), сухой режим,
    команды камеры и «что ты видишь» — строки 10-11 разбора полётов."""
    text = _flat(Path("docs/РУКОВОДСТВО_СОЗДАТЕЛЯ.md").read_text(encoding="utf-8"))
    for anchor in ("91_hands_gate", "СУХОМ режиме", "руки, экзамен",
                   "что ты видишь", "посмотри в камеру", "opencv-python"):
        assert anchor in text, "в РУКОВОДСТВЕ нет: " + anchor
