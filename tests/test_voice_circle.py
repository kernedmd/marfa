# -*- coding: utf-8 -*-
"""Тесты круга 10 «ГОЛОС» (Ф56–Ф60, день-10): слуга-голос Windows SAPI
через EncodedCommand, озвучка ответов, интонация, живой тест, зеркало.

Законы, которые куются здесь:
- EncodedCommand = base64(UTF-16LE): кавычкам и инъекциям нет шанса
  (закон дня-8 в новом обличье) — проверяем байтами, не на слово;
- голос не рвёт дом (закон эфира): поток-демон глотает любой крах;
- один голос в один момент: второй «скажи вслух» ждёт, а не ревёт;
- сухой режим честен: нет PowerShell — орган отказывает с причиной.
"""
import base64
import json
import threading
import time
from pathlib import Path

import pytest

from core import config, voice


@pytest.fixture()
def home(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "HOME_DIR", tmp_path)
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    config.ensure_dirs()
    # кэш голосов каждого теста — свой (законы кэша проверяем явно)
    monkeypatch.setattr(voice, "_VOICES_CACHE",
                        {"ts": 0.0, "voices": [], "error": ""})
    yield tmp_path / "data"


# ---------- Ф56: транспорт PowerShell — кавычкам нет шанса ----------

def test_encoded_command_roundtrip():
    """base64(UTF-16LE) — единственный формат -EncodedCommand;
    скрипт возвращается байт-в-байт."""
    script = "$s.Speak('привет')"
    b64 = voice._b64_script(script)
    assert base64.b64decode(b64).decode("utf-16-le") == script


def test_ps_escape_only_apostrophes():
    """Побег ровно один: ' → '' (закон самого PowerShell). Кавычки
    двойные и точки с запятой текста НЕ трогаются — они уже безопасны
    внутри одинарных кавычек скрипта."""
    assert voice._ps_escape("не 'трогай' меня") == "не ''трогай'' меня"
    assert voice._ps_escape('обычный "текст"; 1+1') == 'обычный "текст"; 1+1'


def test_speak_script_carries_text_lawfully():
    """Скрипт произнесения: текст внутри одинарных кавычек с побегом,
    темп и громкость из настроек, выбор голоса в броне try/catch."""
    script = voice._speak_script("привет, Илья'",
                                 {"rate": -2, "volume": 60}, "Ирина")
    assert "$s.Rate = -2" in script and "$s.Volume = 60" in script
    assert "SelectVoice('Ирина')" in script
    # апостроф текста удвоен + закрывающая кавычка скрипта: три штриха
    assert "$s.Speak('привет, Илья''')" in script


def _with_voices(monkeypatch, voices=(("Microsoft Irina", "ru-RU"),)):
    """Станция с голосами: PowerShell «есть», список голосов — кэш."""
    monkeypatch.setattr(voice, "available", lambda: True)
    monkeypatch.setattr(voice, "_VOICES_CACHE",
                        {"ts": time.monotonic(), "voices": list(voices),
                         "error": ""})


class _FakePS:
    """Шов PowerShell: помнит вызовы; скрипт про голоса отвечает
    списком (как живой SAPI), прочие — кодом 0."""

    def __init__(self, voices=("Microsoft Irina", "ru-RU")):
        self.calls = []
        self._voices = voices

    def __call__(self, script, timeout):
        self.calls.append((script, timeout))
        if "GetInstalledVoices" in script:
            return 0, "%s|%s\n" % self._voices
        return 0, ""


def test_speak_happy_path(home, monkeypatch):
    """Живой голос: список аргументов без shell, скрипт в base64,
    таймаут растёт от длины текста (SAPI не убит на середине слова)."""
    _with_voices(monkeypatch)
    fake = _FakePS()
    monkeypatch.setattr(voice, "_ps", fake)
    report = voice.speak("Марфа на связи")
    assert "Сказала вслух" in report and "Microsoft Irina" in report
    script, timeout = fake.calls[0]
    assert "Марфа на связи" in script
    assert timeout >= 20 + len("Марфа на связи") / 5.0 - 0.01


def test_speak_no_powershell_honest(home, monkeypatch):
    """Сухой режим: орган отказывает с причиной, PowerShell не зовётся."""
    monkeypatch.setattr(voice, "available", lambda: False)
    def _boom(*a, **kw):
        raise AssertionError("PowerShell не должен зваться в сухом режиме")
    monkeypatch.setattr(voice, "_ps", _boom)
    assert "PowerShell" in voice.speak("привет")


def test_speak_no_voices_honest(home, monkeypatch):
    """Windows без голосов: честный путь лечения, не молчаливый крах."""
    _with_voices(monkeypatch, voices=())
    monkeypatch.setattr(voice, "_ps", _FakePS())
    assert "ни один голос" in voice.speak("привет")


def test_speak_empty_and_over_limit(home, monkeypatch):
    _with_voices(monkeypatch)
    assert "пустой" in voice.speak("   ")
    assert "не больше 500" in voice.speak("а" * 501)


def test_one_mouth_at_a_time(home, monkeypatch):
    """Пока говорю — второй «скажи вслух» просит подождать: один рот,
    а не два рупора (человек не говорит поверх себя)."""
    _with_voices(monkeypatch)
    assert voice._MOUTH_LOCK.acquire(blocking=False)
    try:
        assert "ещё говорю" in voice.speak("первая фраза")
    finally:
        voice._MOUTH_LOCK.release()


def test_speak_async_never_breaks_house(home, monkeypatch):
    """Закон эфира: даже крах речи глотается потоком-демоном."""
    done = threading.Event()

    def _boom(text, limit=voice.REPLY_LIMIT):
        done.set()
        raise RuntimeError("динамик отключили провод")

    monkeypatch.setattr(voice, "speak", _boom)
    voice.speak_async("не урони меня")
    assert done.wait(2.0)          # поток жил и умер молча — дом цел


def test_speak_async_passes_text(home, monkeypatch):
    seen = {}
    done = threading.Event()

    def _fake(text, limit=voice.REPLY_LIMIT):
        seen["text"], seen["limit"] = text, limit
        done.set()

    monkeypatch.setattr(voice, "speak", _fake)
    voice.speak_async("ответ дома")
    assert done.wait(2.0)
    assert seen["text"] == "ответ дома" and seen["limit"] == voice.REPLY_LIMIT


def test_say_dispatches_async_with_preview(home, monkeypatch):
    """«скажи вслух» — предыпросмотр честен, само произнесение — в
    потоке: чат не ждёт, пока SAPI договорит."""
    _with_voices(monkeypatch)
    seen = {}
    def _fake_async(text, limit=voice.SAY_LIMIT):
        seen["text"] = text
    monkeypatch.setattr(voice, "speak_async", _fake_async)
    assert "произношу вслух" in voice.say("привет, Создатель")
    assert seen["text"] == "привет, Создатель"
    long = "слово " * 120
    assert "не больше 500" in voice.say(long)
    assert "что сказать" in voice.say("")


def test_say_dry_honest(home, monkeypatch):
    monkeypatch.setattr(voice, "available", lambda: False)
    assert "Windows" in voice.say("привет")


# ---------- Ф58: интонация — границы честны ----------

def test_tune_steps_and_persistence(home):
    assert "темп -1" in voice.tune("медленнее")
    data = json.loads((home / "voice_settings.json").read_text(encoding="utf-8"))
    assert data["rate"] == -1 and data["volume"] == 100
    assert "громкость 80" in voice.tune("тише")
    assert "обычный темп" in voice.tune("нормально")


def test_tune_bounds_refuse_honestly(home):
    for _ in range(6):
        voice.tune("медленнее")
    assert "медленнее всех" in voice.tune("медленнее")   # темп -5 — край
    for _ in range(6):
        voice.tune("громче")
    assert "громче некуда" in voice.tune("громче")       # 100 из 100
    assert "не знаю такой интонации" in voice.tune("шёпотом")


def test_tune_settings_survive_garbage(home):
    """Битый файл настроек — честные значения по умолчанию (закон H4/H5:
    кривой статус-файл не роняет орган)."""
    home.mkdir(parents=True, exist_ok=True)
    (home / "voice_settings.json").write_text("{мусор", encoding="utf-8")
    assert "обычный темп" in voice.tune("нормально")


# ---------- Ф57: резолюция «говори вслух» ----------

def test_out_flag_roundtrip(home, monkeypatch):
    _with_voices(monkeypatch)
    assert "отвечаю вслух" in voice.set_out(True)
    assert voice.out_enabled() is True
    assert json.loads((home / "voice_out.json").read_text(
        encoding="utf-8"))["on"] is True
    assert "молчу" in voice.set_out(False)
    assert voice.out_enabled() is False


def test_out_flag_default_silent(home):
    """Файла нет — молчу: голос — воля Создателя (как моторика)."""
    assert voice.out_enabled() is False


def test_out_flag_garbage_is_silence(home):
    (home / "voice_out.json").write_text("не json", encoding="utf-8")
    assert voice.out_enabled() is False


def test_set_out_honest_without_voices(home, monkeypatch):
    monkeypatch.setattr(voice, "available", lambda: True)
    monkeypatch.setattr(voice, "_VOICES_CACHE",
                        {"ts": time.monotonic(), "voices": [], "error": ""})
    assert "ни одного голоса" in voice.set_out(True)


# ---------- Ф59/Ф60: диагноз и живой тест ----------

def test_diagnosis_dry(home, monkeypatch):
    monkeypatch.setattr(voice, "available", lambda: False)
    assert "PowerShell" in voice.diagnosis()


def test_diagnosis_russian_voice(home, monkeypatch):
    _with_voices(monkeypatch, (("Microsoft Irina", "ru-RU"),
                               ("Microsoft David", "en-US")))
    assert "Microsoft Irina (русский)" in voice.diagnosis()
    voice.set_out(True)
    assert "отвечаю вслух" in voice.diagnosis()


def test_diagnosis_no_russian(home, monkeypatch):
    _with_voices(monkeypatch, (("Microsoft David", "en-US"),))
    assert "с акцентом" in voice.diagnosis()


def test_selftest_dry_honest(home, monkeypatch):
    monkeypatch.setattr(voice, "available", lambda: False)
    assert "сухом режиме" in voice.selftest()


def test_selftest_with_voices(home, monkeypatch):
    """Живой тест: голоса системы, интонация, пробная фраза, подсказка."""
    _with_voices(monkeypatch, (("Microsoft Irina", "ru-RU"),))
    fake = _FakePS()
    monkeypatch.setattr(voice, "_ps", fake)
    report = voice.selftest()
    assert "ПРОВЕРКА ГОЛОСА" in report
    assert "Microsoft Irina" in report and "русский" in report
    assert "интонация" in report and "проба" in report
    assert "говори вслух" in report
    assert fake.calls                    # пробная фраза реально ушла в SAPI


# ---------- проводка агента: мозг молчит ----------

@pytest.fixture()
def agent(home, monkeypatch):
    from core.agent import Agent
    from core.memory import Memory
    return Agent(memory=Memory(data_dir=Path(config.DATA_DIR)),
                 doctrine="Тестовая доктрина")


def test_agent_say_command(agent, monkeypatch):
    seen = {}
    monkeypatch.setattr(voice, "say", lambda t: "произношу: " + t)
    r = agent.handle("скажи вслух доброе утро, дом!")
    assert r.source == "python" and r.tool_used == "voice"
    assert "доброе утро, дом" in r.text
    r = agent.handle("Марфа, произнеси вслух: я живая")
    assert r.source == "python" and "я живая" in r.text


def test_agent_voice_resolution(agent, monkeypatch):
    calls = []
    monkeypatch.setattr(voice, "set_out",
                        lambda on: calls.append(on) or "резолюция")
    assert agent.handle("говори вслух").source == "python"
    assert agent.handle("молчи").source == "python"
    assert agent.handle("перестань говорить вслух").source == "python"
    assert calls == [True, False, False]


def test_agent_tune_command(agent, monkeypatch):
    monkeypatch.setattr(voice, "tune", lambda w: "интонация: " + w)
    r = agent.handle("говори медленнее")
    assert r.source == "python" and "медленнее" in r.text
    r = agent.handle("говори громче")
    assert r.source == "python" and "громче" in r.text


def test_agent_check_voice(agent, monkeypatch):
    monkeypatch.setattr(voice, "selftest", lambda: "ПРОВЕРКА ГОЛОСА: жив")
    r = agent.handle("проверь голос")
    assert r.source == "python" and "ПРОВЕРКА ГОЛОСА" in r.text


def test_agent_say_without_text_is_hint(agent, monkeypatch):
    monkeypatch.setattr(voice, "say", lambda t: "что сказать?")
    r = agent.handle("скажи вслух")
    # хвостовой знак не роняет команду в мозг (урок р3 №8)
    assert r.tool_used == "voice"


# ---------- проводка зеркала (Ф60): три лжи «рта нет» вылечены ----------

def test_identity_knows_voice():
    from core import identity
    joined = "; ".join(identity.FAST_COMMANDS)
    assert "скажи вслух" in joined and "проверь голос" in joined
    report = identity.capabilities_report(eyes_ok=True, ears_ok=True)
    assert "Голос:" in report
    assert "рта нет" not in report           # старая ложь вычищена
    src = Path(core_file("identity.py")).read_text(encoding="utf-8")
    assert "голосом я ещё не отвечаю" not in src


def core_file(name):
    return Path(__file__).resolve().parents[1] / "core" / name


def test_house_state_voice_note(agent, monkeypatch):
    """«статус» знает правду о голосе — сенсор в броне (закон №10 р3)."""
    monkeypatch.setattr(voice, "diagnosis", lambda: "говорю голосом Тест")
    from core.agent import _house_state
    assert "голос: говорю голосом Тест" in _house_state()


# ---------- проводка панели и моста: озвучка ответов ----------

def test_web_chat_speaks_when_enabled(home, monkeypatch):
    """«говори вслух» — ответы чата уходят в голос; «молчи» — нет."""
    from web.app import app

    class _FakeReply:
        text, source, meta = "ответ вслух", "python", None

    class _FakeAgent:
        def __init__(self, *a, **kw):
            pass
        def handle(self, text, history=None, **kw):
            return _FakeReply()

    import web.app as webapp
    monkeypatch.setattr(webapp, "Agent", _FakeAgent)
    spoken = []
    monkeypatch.setattr(voice, "out_enabled", lambda: True)
    monkeypatch.setattr(voice, "speak_async", lambda t, limit=None: spoken.append(t))
    app.config["TESTING"] = True
    client = app.test_client()
    r = client.post("/api/chat", json={"text": "привет",
                                       "session": "s1"})
    assert r.status_code == 200
    assert spoken == ["ответ вслух"]
    monkeypatch.setattr(voice, "out_enabled", lambda: False)
    client.post("/api/chat", json={"text": "ещё раз", "session": "s1"})
    assert len(spoken) == 1                    # молчим — не копим


def test_ear_bridge_speaks_voice_answers(home, monkeypatch):
    """Голосовой ход — голосовой ответ: мост озвучивает обмен, если
    Создатель сказал «говори вслух»; нет — тишина (закон воли)."""
    from sensors import ear_bridge as bridge

    spoken = []
    monkeypatch.setattr(voice, "speak_async",
                        lambda t, limit=None: spoken.append(t))

    def fake_transcribe(pcm, sample_rate=16000):
        return "Марфа, который час", "расшифровал"

    class _R:
        text, source, meta = "Сейчас 15:34", "python", {"tok": 8}

    monkeypatch.setattr(bridge, "transcribe", fake_transcribe)
    monkeypatch.setattr(bridge, "_agent_answer",
                        lambda t, history=None: _R())
    monkeypatch.setattr(voice, "out_enabled", lambda: True)
    rec = bridge.handle_phrase(b"\x01" * 32000, 16000, had_voice=True)
    assert rec["event"] == "exchange"
    assert spoken == ["Сейчас 15:34"]
    monkeypatch.setattr(voice, "out_enabled", lambda: False)
    bridge.handle_phrase(b"\x01" * 32000, 16000, had_voice=True)
    assert len(spoken) == 1


# ---------- кнопка 94: голос — орган Создателя ----------

def test_button94_exists():
    btn = Path(__file__).resolve().parents[1] / "scripts" / "94_voice.bat"
    assert btn.exists(), "кнопка 94_voice.bat должна лежать в scripts/"
    text = btn.read_text(encoding="utf-8")
    assert "BTN_VER 94" in text
    assert "voice.selftest()" in text and "voice.say(" in text
