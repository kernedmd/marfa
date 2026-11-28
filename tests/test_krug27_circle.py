# -*- coding: utf-8 -*-
r"""tests/test_krug27_circle.py — ЗОЛОТОЙ ЯКОРЬ КРУГА 27 «ГОРЛО
ЛЕЧИТСЯ СЛОВОМ» (Ф166–Ф170, день-16 вечер, 27.11.2026).

Круг родился из живого лога дня-16: «проверь горло» честно показал
«слуга: СПИТ», но лечение назвал консолью («поднять слуга на 8084»);
Создатель спросил «А ты сможешь себя починить?» — мозг позвал
code_patch БЕЗ полей, ответил шпаргалкой «кодеру нужны ДВА поля:
path и requirement» («Я ничего не понял, что ты мне написала»), а со
второй попытки повёл кодера патчить МОДЕЛЬ v5_6_ru.pt (140 МБ) —
«инструмент code_patch споткнулся: файл больше 2097152 байт».

Якоря (все — через калитку agent.handle, мозг молчит где не зван):
- Ф166: мозг ЗНАЕТ горло-слова («проверь/разбуди/уложи горло») и
  закон «кодер — врач КОДА; спящий слуга — не сломанный файл»;
- Ф167: код-патч говорит человечески — модель и бинарники кодер не
  лечит (отказ ДО кодера, с лекарством словом), большой файл —
  читаемый диагноз, а не «споткнулся»; ошибка полей — голосом Марфы
  («мой промах»), не шпаргалкой для мозга;
- Ф168: «почини горло/голос/слугу», «разбуди/подними/запусти слугу» —
  рефлекс дома к wake_throat, ДО почини-парсера кодера;
- Ф169: «проверь горло» при спящем слуге называет лекарство СЛОВОМ
  («скажи „разбуди горло“ — подниму сама»); не хватает посылки —
  честно названо, ЧЕГО именно;
- Ф170: «что тебе сегодня снилось?» и «что тебе приснилось?» —
  орган снов, не мозг-выдумщик («образы, связанные с
  предназначением» из живого лога).

Швы: ensure_server/release (repair), voice.wake_throat,
throat.alive, torch в sys.modules — ничего живого не поднимается:
ни кодера, ни горла.
"""
import sys
import types
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import agent, config, identity, progress, repair, voice  # noqa: E402
from core.agent import Agent  # noqa: E402


# ---------------------------------------------------------------
# Песочница круга (паттерн krug26): дом — tmp, слуги — швы
# ---------------------------------------------------------------

@pytest.fixture
def home(tmp_path, monkeypatch):
    """Изолированный дом: патчи и модели не трогают станцию."""
    monkeypatch.setattr(config, "HOME_DIR", tmp_path)
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(config, "LOGS_DIR", tmp_path / "logs")
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
    # горло-слова — шов: рефлекс жив, слуга не поднимается
    monkeypatch.setattr(voice, "wake_throat",
                        lambda: "горло ЖИВО на порту 8084 (шов)")
    progress.reset()
    return tmp_path


class FakeBrain:
    """Мозг-счётчик: считает вызовы, отвечает заготовкой."""

    def __init__(self, answer="живой ответ мозга по существу"):
        self.calls = 0
        self.answer = answer

    def ask_json(self, *a, **kw):
        self.calls += 1
        return {"answer": self.answer}


class FakeMemory:
    def recall(self, *a, **kw):
        return []


def _agent(brain=None):
    return Agent(brain=brain or FakeBrain(), memory=FakeMemory(),
                 doctrine="Тестовая доктрина круга 27")


# ================================================================
# Ф166 «ЛЕКСИКОН ГОРЛА В ГОСТИНОЙ» — мозг знает слова лечения
# ================================================================

def test_f166_brain_knows_throat_words(home):
    """«проверь горло», «разбуди горло», «уложи горло» — в списке
    быстрых команд и в стройном манифесте: на «сможешь себя
    починить?» мозг отвечает СЛОВОМ дома, а не патчем модели."""
    fast = " | ".join(identity.FAST_COMMANDS)
    for word in ("проверь горло", "разбуди горло", "уложи горло"):
        assert word in fast, "команда должна жить в FAST_COMMANDS: " + word
    slim = identity.manifest_slim()
    for word in ("проверь горло", "разбуди горло", "уложи горло"):
        assert word in slim, "стройный манифест несёт: " + word


def test_f166_coder_is_code_doctor(home):
    """Закон в манифесте: кодер — врач КОДА (.py), модели и бинарники
    не лечит; спящий слуга — НЕ сломанный файл (живой лог дня-16:
    мозг патчил v5_6_ru.pt)."""
    slim = identity.manifest_slim()
    assert "врач КОДА" in slim or "врач кода" in slim
    assert "не сломанный файл" in slim
    assert ".pt" in slim, "имена нелечимых форматов — в законе"


# ================================================================
# Ф167 «КОД-ПАТЧ ГОВОРИТ ЧЕЛОВЕЧЕСКИ»
# ================================================================

def test_f167_model_refused_before_coder(home, monkeypatch):
    """«почини models\voice\v5_6_ru.pt: …» — честный отказ ДО кодера:
    это модель, не код; лекарство — «разбуди горло», не патч. Кодер
    не поднимается вовсе (VRAM-танец не стартует)."""
    model_dir = Path(config.HOME_DIR) / "models" / "voice"
    model_dir.mkdir(parents=True, exist_ok=True)
    (model_dir / "v5_6_ru.pt").write_bytes(b"x" * 1024)
    coder_calls = {"n": 0}

    def _seam(wait_secs=None):
        coder_calls["n"] += 1
        return True, "кодер на посту (шов)"
    monkeypatch.setattr(repair, "ensure_server", _seam)
    out = repair.make_patch("models/voice/v5_6_ru.pt",
                            "сделай голос живым")
    assert "модель" in out and "не код" in out
    assert "разбуди горло" in out, "отказ несёт лекарство словом"
    assert coder_calls["n"] == 0, "кодер не поднимается: не его пациент"


def test_f167_binary_zoo(home):
    """Страж знает всех нелечимых: .gguf — модель, .exe — программа,
    .zip — архив, .wav — звук; .py и без суффикса — путь открыт."""
    def reply(name):
        return repair.not_code_reply(Path(name))
    assert "модель" in reply("coder.gguf")
    assert "программа" in reply("tool.exe")
    assert "архив" in reply("backup.zip")
    assert "звук" in reply("probe.wav")
    assert reply("hello.py") is None
    assert reply("README") is None


def test_f167_big_file_readable_refusal(home):
    """Файл больше 2 МБ чтения — читаемый диагноз, не «инструмент
    споткнулся» из живого лога дня-16. Круг 35 (В6): не-.py отказывается
    ЕЩЁ РАНЬШЕ — сит-чеком до чтения («не .py» вместо «не по зубам»),
    обе гарантии Ф167 держатся: диагноз словами, до кодера не доходит."""
    big_dir = Path(config.HOME_DIR) / "logs"
    big_dir.mkdir(parents=True, exist_ok=True)
    (big_dir / "huge.log").write_bytes(b"a" * (2 * 1024 * 1024 + 64))
    out = repair.make_patch("logs/huge.log", "сделай меньше")
    assert ("не по зубам" in out) or ("не .py" in out)
    assert "споткнулся" not in out


def test_f167_two_fields_in_marfas_voice(home):
    """Мозг позвал code_patch без полей — Создатель читает голос
    Марфы («мой промах» + живое лекарство), не шпаргалку «ДВА поля:
    path и requirement» (живой лог: «Я ничего не понял»)."""
    class NoFieldsBrain:
        def __init__(self):
            self.calls = 0

        def ask_json(self, *a, **kw):
            self.calls += 1
            return {"action": {"tool": "code_patch",
                               "args": {"text": "почини горло"}}}
    a = Agent(brain=NoFieldsBrain(), memory=FakeMemory(), doctrine="Тест")
    r = a.handle("а ты сможешь себя починить?")
    assert r.tool_used == "code_patch"
    assert "мой промах" in r.text, "Марфа признаёт свой промах голосом"
    assert "разбуди горло" in r.text, "и сразу называет лекарство словом"
    assert "ДВА поля" not in r.text, "шпаргалка для мозга — не для Создателя"


# ================================================================
# Ф168 «ПОЧИНИ ГОРЛО — РЕФЛЕКС»
# ================================================================

def test_f168_fix_throat_is_a_reflex(home):
    """«почини горло» и «почини голос» — дом будит слугу (тот же
    маршрут, что «разбуди горло»), мозг молчит: естественная речь
    Создателя не улетает в кодер патчить модель."""
    a = _agent()
    r = a.handle("почини горло")
    assert r.source == "python" and r.tool_used == "throat_wake"
    assert a.brain.calls == 0, "горло — рефлекс, не мозг"
    assert "шов" in r.text
    r2 = a.handle("почини голос")
    assert r2.tool_used == "throat_wake" and a.brain.calls == 0


def test_f168_wake_servant_variants(home):
    """«разбуди/подними/запусти/включи слугу» — будят горло; старые
    «разбуди горло» не сломаны (маршрут один, список шире)."""
    a = _agent()
    for phrase in ("разбуди слугу", "подними слугу", "запусти слугу",
                   "включи слугу", "разбуди горло"):
        r = a.handle(phrase)
        assert r.tool_used == "throat_wake", phrase
        assert r.source == "python", phrase
    assert a.brain.calls == 0


# ================================================================
# Ф169 «ЛЕКАРСТВО СЛОВОМ» — диагноз называет лечение дом. словом
# ================================================================

def test_f169_sleeping_servant_medicine_by_word(home, monkeypatch):
    """Слуга спит, модель и torch на месте — лечение в отчёте
    СЛОВОМ: «скажи „разбуди горло“ — подниму сама», не консольная
    инструкция «поднять слуга на 8084» (живой лог дня-16)."""
    model = Path(config.HOME_DIR) / "models" / "voice" / "v5_6_ru.pt"
    model.parent.mkdir(parents=True, exist_ok=True)
    model.write_bytes(b"x" * 1024)
    monkeypatch.setattr(config, "THROAT_MODEL_FILE", model)
    fake_torch = types.ModuleType("torch")
    fake_torch.__version__ = "2.7.1+cu118 (шов)"
    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    from core import throat
    monkeypatch.setattr(throat, "alive", lambda: False)
    report = voice.throat_report()
    assert "слуга: СПИТ" in report
    assert "разбуди горло" in report, "лекарство — слово дома"
    assert "подниму" in report, "Марфа предлагает себя, не консоль"
    assert "поднять слугу на" not in report, "консольная строка умерла"


def test_f169_missing_parcel_honest(home, monkeypatch):
    """Модели и torch нет — лечение честно называет, ЧЕГО не хватает,
    и где посылка; слово «разбуди горло» не предлагается зря."""
    monkeypatch.setattr(config, "THROAT_MODEL_FILE",
                        Path(config.HOME_DIR) / "models" / "voice" /
                        "нет_модели.pt")
    monkeypatch.setitem(sys.modules, "torch", None)   # import torch — мимо
    from core import throat
    monkeypatch.setattr(throat, "alive", lambda: False)
    report = voice.throat_report()
    assert "слуга: СПИТ" in report
    assert "не хватает модели v5_6_ru.pt" in report
    assert "torch" in report
    assert "посылка" in report, "путь лечения — посылка, не патч"
    assert "подниму сама" not in report


def test_f169_report_through_gate(home):
    """«проверь горло» — по-прежнему рефлекс дома (5 секунд из живого
    лога), мозг молчит."""
    a = _agent()
    r = a.handle("проверь горло")
    assert r.source == "python" and r.tool_used == "throat"
    assert a.brain.calls == 0


# ================================================================
# Ф170 «СНЫ ШИРЕ» — орган снов узнаёт живые варианты фразы
# ================================================================

def test_f170_dream_organ_takes_today(home):
    """«ЧТо тебе сегодня снилось?» — орган снов (живой лог дня-16:
    слово «сегодня» роняло фразу в мозг, и тот фантазировал
    «образы, связанные с предназначением»)."""
    a = _agent()
    r = a.handle("ЧТо тебе сегодня снилось?")
    assert r.source == "python" and r.tool_used == "dream"
    assert a.brain.calls == 0, "сон — орган, не фантазия мозга"
    r2 = a.handle("что тебе приснилось?")
    assert r2.tool_used == "dream" and a.brain.calls == 0


def test_f170_dream_variants_and_legacy(home):
    """Все варианты фразы — органу; старое «что тебе снилось» не
    сломано (якорь круга 26 жив)."""
    a = _agent()
    for phrase in ("что тебе снилось", "что тебе снилось сегодня",
                   "что сегодня снилось", "что снилось сегодня",
                   "что тебе сегодня приснилось"):
        r = a.handle(phrase)
        assert r.tool_used == "dream", phrase
    assert a.brain.calls == 0
