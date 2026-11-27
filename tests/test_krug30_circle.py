# -*- coding: utf-8 -*-
r"""tests/test_krug30_circle.py — ЗОЛОТОЙ ЯКОРЬ КРУГА 30 «ЧУЖИЕ БУКВЫ»
(Ф181–Ф183, день-17, 27.11.2026, вечер).

Круг родился из живого лога дня-17, вечер — ПЕРВЫЙ живой голосовой ход
в истории дома: «Марфа, который час?» вслух. Весь тракт проработал
(сторож vosk поймал имя → ловец фраз собрал звук → whisper-слуга
расшифровал за 2 с → «услышала голосом» в чате) — и фраза умерла
на последней калитке:

- голосом: «Marfa, which hour?» — имени в фразе нет — не зов (×3):
  whisper на короткой русской фразе решил, что язык английский, и
  написал имя ЛАТИНИЦЕЙ; словарь _WAKE_EXACT ждал кириллицу (Ф181);
- «проверь мост» (дважды за день): «служба моста: сердцебиения нет» —
  мост поднимался руками из консоли, окно закрылось, слух фраз умер
  молча при живых ушах-сторож; автозапуск дома мост не знал (Ф182);
- find_whisper.py: «архивов не найдено» — GitHub с релиза v1.9.4
  перестал прикладывать бинарники whisper.cpp, скрипт не знал про
  SourceForge-зеркало b4938; и дом слуги — whisper.cpp, НЕ llama.cpp
  (там живой мозг со своими свежими dll — 38 файлов зеркала поверх
  = подмена dll мозга постарше) (Ф183).

Якоря: латиница имени — зов (живая фраза лога), гейт строг («марка»
не зов и латиницей тоже); язык фразы — в каждом запросе слуге и во
флаге его подъёма; мост — шестой слуга старта дома (статус-файл,
апгрейд конфига на лету); find_whisper знает зеркало и дом слуги.
"""
import datetime as dt
import json
import struct
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import sensors.ear_bridge as bridge
from core import config


@pytest.fixture()
def home(tmp_path, monkeypatch):
    """Свой дом для голосового хода — как у якорей моста (круг 23):
    константы, вычисленные на импорте, патчу явно поверх автопесочницы."""
    monkeypatch.setenv("MARFA_HOME", str(tmp_path))
    monkeypatch.setattr(config, "HOME_DIR", tmp_path)
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(config, "MODELS_DIR", tmp_path / "models")
    monkeypatch.setattr(config, "VOICE_DIR", tmp_path / "data" / "voice")
    monkeypatch.setattr(config, "VOICE_LOG_FILE",
                        tmp_path / "data" / "voice" / "voice_log.jsonl")
    monkeypatch.setattr(config, "VOICE_STATUS_FILE",
                        tmp_path / "data" / "voice" / "status.json")
    config.ensure_dirs()
    (tmp_path / "models").mkdir(exist_ok=True)
    yield tmp_path


# ---------- Ф181: чужие буквы имени ----------

def test_wake_latin_script_is_a_call():
    """Живая фраза лога дня-17: «Marfa, which hour?» — ЗОВ, не пропуск.

    whisper расшифровал русскую фразу латиницей; до Ф181 калитка
    _has_wake_exact её отвергала трижды подряд при живом слухе.
    """
    assert bridge._has_wake_exact("Marfa, which hour?") is True
    assert bridge._has_wake_exact("Marfa, which one?") is True


def test_wake_latin_cases_accepted():
    """Латинская транслитерация падежей — как кириллические падежи
    (прецедент: test_handle_phrase_wake_forms_accepted, круг 23)."""
    for form in ("Marfa", "Marfu", "Marfy", "Marfe", "Marfoy"):
        assert bridge._has_wake_exact("передай %s привет" % form) is True


def test_wake_gate_stays_strict_both_scripts():
    """Гейт остаётся строгим: «марка» — не зов на любых буквах;
    «март» — не имя. Имя узнали шире, слух не распахнули настежь."""
    assert bridge._has_wake_exact("марка красивая") is False
    assert bridge._has_wake_exact("marke is fine") is False
    assert bridge._has_wake_exact("март холодный") is False
    assert bridge._has_wake_exact("который час") is False


def test_wake_cyrillic_forms_unchanged():
    """Старый словарь цел: кириллица — все падежи, как до круга 30."""
    for form in ("Марфа", "Марфу", "Марфе", "Марфой", "Марфы"):
        assert bridge._has_wake_exact("передай %s привет" % form) is True


def test_handle_phrase_latin_name_full_exchange(home, monkeypatch):
    """ПОЛНЫЙ ХОД с латиницей: расшифровка «Marfa, which hour?» —
    фраза доходит до дома, ответ пишется в журнал. Живой провал
    дня-17 («не зов» ×3) не повторяется."""
    asked = {}

    def fake_transcribe(pcm, sample_rate=16000):
        return "Marfa, which hour?", "расшифровал"

    class FakeReply:
        text, source, meta = "Сейчас 21:07.", "brain", {"tok": 30}

    def fake_agent(t, history=None, voice=False):
        asked["text"] = t
        asked["voice"] = voice
        return FakeReply()

    monkeypatch.setattr(bridge, "transcribe", fake_transcribe)
    monkeypatch.setattr(bridge, "_agent_answer", fake_agent)
    monkeypatch.setattr(bridge, "_speak_reply", lambda text: None)
    rec = bridge.handle_phrase(struct.pack("<8000h", *([9000] * 8000)),
                               16000, had_voice=True)
    assert rec["event"] == "exchange"
    assert asked["text"] == "Marfa, which hour?"
    assert asked["voice"] is True
    assert rec["phrase"] == "Marfa, which hour?"


# ---------- Ф181: язык фразы — дому, не гаданию автоматики ----------

def test_post_transcription_sends_russian_language(home, monkeypatch):
    """Каждый запрос слуге несёт language=ru — подсказка живёт в поле
    формы (как у OpenAI), работает и с уже поднятым слугой, без
    перезапуска. Шов requests.post — как у якорей моста."""
    import requests

    calls = []

    class FakeResp:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {"text": "Марфа, который час"}

    def fake_post(url, files=None, data=None, timeout=None):
        calls.append(data)
        return FakeResp()

    monkeypatch.setattr(requests, "post", fake_post)
    assert bridge._post_transcription(b"RIFF....") == "Марфа, который час"
    assert calls and calls[0].get("language") == "ru"


def test_spawn_server_carries_language_flag(home, monkeypatch):
    """Подъём слуги — с флагом -l ru (сборка b4938 флаг знает —
    проверено по строкам бинарника). Живёт в самой команде: слуга,
    поднятый до круга 30, после 5 минут тишины ляжет — и встанет
    уже с языком."""
    got = {}

    def fake_popen(cmd, **kw):
        got["cmd"] = cmd
        return object()

    monkeypatch.setattr(bridge.subprocess, "Popen", fake_popen)
    server = Path(config.HOME_DIR) / "whisper.cpp" / "whisper-server.exe"
    model = Path(config.HOME_DIR) / "models" / "ggml-large-v3-turbo.bin"
    cmd = bridge._spawn_server(server, model)
    assert " -l ru " in cmd
    assert got["cmd"] == cmd


# ---------- Ф182: мост — шестой слуга старта дома ----------

def test_start_template_has_bridge_cmd():
    """Шаблон старта знает команду моста: живой конфиг без поля
    получает её на лету (прецедент ears_cmd, апгрейд на лету)."""
    import start_marfa
    assert "ear_bridge.py --service" in start_marfa.TEMPLATE["bridge_cmd"]


def test_start_bridge_alive_by_heartbeat(home, monkeypatch):
    """Живость моста — по статус-файлу (как уши): свежее сердце —
    жив, устаревшее/файла нет — не поднимай второй экземпляр."""
    import start_marfa
    sf = home / "data" / "voice" / "status.json"
    sf.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(start_marfa, "BRIDGE_STATUS_FILE", sf)
    # нет файла — не жив
    assert start_marfa._bridge_alive() is False
    # свежее сердце — жив
    sf.write_text(json.dumps(
        {"ts": dt.datetime.now().isoformat(timespec="seconds"),
         "sensor": "ear_bridge", "state": "ok"}), encoding="utf-8")
    assert start_marfa._bridge_alive() is True
    # устаревшее — не жив (окно консоли закрылось — круг 30 поднимет сам)
    sf.write_text(json.dumps(
        {"ts": (dt.datetime.now() -
                dt.timedelta(seconds=start_marfa.BRIDGE_FRESH_SECS + 60)
                ).isoformat(timespec="seconds"),
         "sensor": "ear_bridge", "state": "ok"}), encoding="utf-8")
    assert start_marfa._bridge_alive() is False


def test_start_bridge_status_path_matches_service(home, monkeypatch):
    """Путь старта дома = путь службы моста (config.VOICE_STATUS_FILE):
    старт читает ТО сердце, которое пишет ear_bridge.serve()."""
    import start_marfa
    import sensors.ear_bridge as br
    assert Path(start_marfa.BRIDGE_STATUS_FILE).name == \
        Path(config.VOICE_STATUS_FILE).name
    assert Path(start_marfa.BRIDGE_STATUS_FILE).parts[-3:] == \
        Path(config.VOICE_STATUS_FILE).parts[-3:]


# ---------- Ф183: find_whisper знает зеркало и дом слуги ----------

def test_find_whisper_mirror_and_home():
    """GitHub перестал давать бинарники (v1.9.4+) — скрипт знает
    зеркало b4938; дом слуги — whisper.cpp, НЕ llama.cpp (в спальне
    мозга свои свежие dll; урок дня-17 про подмену)."""
    import scripts.find_whisper as fw
    assert "sourceforge.net" in fw.MIRROR_URL
    assert "whisper-bin-x64" in fw.MIRROR_URL
    assert fw.TARGET_DIR.name == "whisper.cpp"
    assert fw.TARGET_DIR != fw.MARFA_ROOT / "llama.cpp"
