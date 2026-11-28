# -*- coding: utf-8 -*-
"""МОСТ УШЕЙ (23.11, фронт 4 «голос»): вторая ступень слуха — whisper
по зову, ловец фраз, голосовой ход в дом.

Доктрина ушей всегда была двухступенчатой (шапка sensors/ears.py);
Арсенал с рождения держал ggml-large-v3-turbo.bin «готовым к найму».
Здесь проверяется математика захвата (WAV, тишина, кольцо-предыстория),
церемония слуги (найм по образцу кодера), честность полного хода
(фраза без имени — не зов; провал whisper — не «Марфа», а ошибка)
и проводка в дом: агент, состояние, зеркало, манифест.
"""
import datetime as dt
import json
import struct
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import sensors.ear_bridge as bridge
from core import config, identity
from core.agent import Agent, _house_state
from core.brain import BrainClient
from core.memory import Memory
from tests.fake_llama_server import start_fake_brain


@pytest.fixture()
def home(tmp_path, monkeypatch):
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


@pytest.fixture()
def srv(monkeypatch, home):
    server = start_fake_brain()
    monkeypatch.setattr(config, "BRAIN_URL", server.base_url)
    yield server
    server.shutdown()


@pytest.fixture()
def agent(srv):
    mem = Memory(data_dir=Path(config.DATA_DIR))
    return Agent(brain=BrainClient(brain_url=srv.base_url), memory=mem,
                 doctrine="Тестовая доктрина")


def _loud_pcm(secs: float, rate: int = 16000, amp: int = 12000) -> bytes:
    """Громкий «звук»: чередование амплитуд — RMS заведомо выше порога."""
    n = int(secs * rate)
    return struct.pack("<%dh" % n, *(amp if i % 2 == 0 else -amp
                                     for i in range(n)))


def _quiet_pcm(secs: float, rate: int = 16000) -> bytes:
    return b"\x00" * (int(secs * rate) * 2)


# ---------- математика захвата: WAV и громкость ----------

def test_pcm_to_wav_header(home):
    pcm = _quiet_pcm(0.1)
    wav = bridge.pcm_to_wav(pcm, 16000)
    assert wav[:4] == b"RIFF" and wav[8:12] == b"WAVE"
    assert wav[12:16] == b"fmt " and wav[36:40] == b"data"
    assert struct.unpack("<I", wav[4:8])[0] == 36 + len(pcm)
    assert struct.unpack("<I", wav[40:44])[0] == len(pcm)
    assert struct.unpack("<H", wav[22:24])[0] == 1      # моно
    assert struct.unpack("<I", wav[24:28])[0] == 16000  # частота
    assert wav[44:] == pcm


def test_rms_silence_loud_empty(home):
    assert bridge.rms(b"") == 0.0
    assert bridge.rms(_quiet_pcm(0.1)) == 0.0
    assert bridge.rms(_loud_pcm(0.1)) == pytest.approx(12000.0, rel=0.01)


# ---------- ловец фраз: кольцо, тишина, потолок ----------

def test_catcher_preroll_kept_before_wake(home):
    """Фраза начинается ДО срабатывания сторожа: кольцо при деле.

    Урок двухступенчатого слуха: имя звучит в начале фразы, а сторож
    срабатывает по ЧАСТИЧНОМУ результату — без предыстории whisper
    получил бы «...ый час» вместо «Марфа, который час».
    """
    c = bridge.PhraseCatcher(sample_rate=16000, preroll_sec=1.0)
    c.feed(_loud_pcm(0.6))            # имя — ещё до зова, уходит в кольцо
    assert c.feed(_quiet_pcm(0.1))["event"] == "idle"
    c.arm()
    ev = c.feed(_quiet_pcm(2.0))      # тишина — фраза кончилась
    assert ev["event"] == "done"
    assert len(ev["pcm"]) >= 0.6 * 16000 * 2   # имя НЕ потерялось


def test_catcher_end_by_silence_after_voice(home):
    c = bridge.PhraseCatcher(sample_rate=16000, silence_sec=1.0)
    c.arm()
    assert c.feed(_loud_pcm(0.4))["event"] == "capturing"
    assert c.feed(_quiet_pcm(0.5))["event"] == "capturing"   # тишины мало
    ev = c.feed(_quiet_pcm(0.7))     # 1.2 с тишины — хватит
    assert ev["event"] == "done" and ev["voice"] is True


def test_catcher_ceiling_never_exceeded(home):
    """Потолок фразы — закон: болтун без пауз не занял микрофон навечно."""
    c = bridge.PhraseCatcher(sample_rate=16000, max_sec=2.0,
                             silence_sec=5.0)
    c.arm()
    ev = {"event": "capturing"}
    for _ in range(40):
        ev = c.feed(_loud_pcm(0.25))
        if ev["event"] == "done":
            break
    assert ev["event"] == "done"
    assert len(ev["pcm"]) <= 2.3 * 16000 * 2


def test_catcher_ring_bounded(home):
    c = bridge.PhraseCatcher(sample_rate=16000, preroll_sec=1.0)
    for _ in range(20):
        c.feed(_loud_pcm(0.5))        # 10 с болтовни ДО зова
    assert len(c._ring) <= 1.0 * 16000 * 2 + 8000   # кольцо не толстеет


def test_catcher_voice_flag_from_ring(home):
    """Имя в кольце — голос «был», даже если после зова наступила пауза."""
    c = bridge.PhraseCatcher(sample_rate=16000, silence_sec=0.5)
    c.feed(_loud_pcm(0.5))
    c.arm()
    assert c._heard_voice is True
    ev = c.feed(_quiet_pcm(0.8))
    assert ev["event"] == "done" and ev["voice"] is True


def test_catcher_silent_wake_marks_no_voice(home):
    c = bridge.PhraseCatcher(sample_rate=16000, silence_sec=0.5)
    c.feed(_quiet_pcm(0.5))           # ложная тревога в тишине
    c.arm()
    ev = c.feed(_quiet_pcm(0.8))
    assert ev["event"] == "done" and ev["voice"] is False


# ---------- слуга: найти, нанять, уложить ----------

def test_find_model_and_server(home):
    (Path(config.MODELS_DIR) / "ggml-large-v3-turbo.bin").write_bytes(b"x")
    lcpp = Path(config.HOME_DIR) / "llama.cpp"
    lcpp.mkdir()
    (lcpp / "whisper-server.exe").write_bytes(b"x")
    assert bridge.find_whisper_model().name == "ggml-large-v3-turbo.bin"
    assert bridge.find_whisper_server() == lcpp / "whisper-server.exe"


def test_find_server_llama_prefix_name(home):
    lcpp = Path(config.HOME_DIR) / "llama.cpp"
    lcpp.mkdir()
    (lcpp / "llama-whisper-server.exe").write_bytes(b"x")
    assert bridge.find_whisper_server() is not None


def test_ensure_server_honest_when_missing(home):
    ok, note = bridge.ensure_server()
    assert ok is False
    assert "whisper-сервера нет" in note


def test_ensure_server_spawn_and_wait(home, monkeypatch):
    (Path(config.MODELS_DIR) / "ggml-large-v3-turbo.bin").write_bytes(b"x")
    lcpp = Path(config.HOME_DIR) / "llama.cpp"
    lcpp.mkdir()
    (lcpp / "whisper-server.exe").write_bytes(b"x")
    spawns = []
    monkeypatch.setattr(bridge, "_spawn_server",
                        lambda s, m: spawns.append((s, m)) or "cmd")
    alive = iter([False, False, True])
    monkeypatch.setattr(bridge, "server_alive", lambda: next(alive))
    ok, note = bridge.ensure_server(wait_secs=5)
    assert ok is True and "на посту" in note and len(spawns) == 1


def test_maybe_release_respects_keepalive(home, monkeypatch):
    """Закон арсенала: модель без работы не гоняется — но и не мечется."""
    from core import vram
    monkeypatch.setattr(bridge, "server_alive", lambda: True)
    stopped = []
    # КРУГ 36 (ритуал продления): церемония — lay_down со статусами
    monkeypatch.setattr(vram, "lay_down",
                        lambda port, server_name="llama-server":
                        stopped.append((port, server_name))
                        or vram.StopResult("laid", "шов"))
    bridge._last_used = time.time()          # только что работал
    assert bridge.maybe_release() == "" and not stopped
    bridge._last_used = time.time() - config.WHISPER_KEEPALIVE_SEC - 10
    assert "лёг" in bridge.maybe_release()
    assert stopped and stopped[0][0] == config.PORT_WHISPER
    assert "whisper-server" in stopped[0][1]


# ---------- расшифровка: клиент слуги ----------

def test_post_transcription_ok(home, monkeypatch):
    import requests

    calls = []

    class FakeResp:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {"text": "Марфа, который час"}

    def fake_post(url, files=None, data=None, timeout=None):
        calls.append({"url": url, "files": files, "data": data})
        return FakeResp()

    monkeypatch.setattr(requests, "post", fake_post)
    text = bridge._post_transcription(b"RIFF....")
    assert text == "Марфа, который час"
    assert calls[0]["url"].endswith(config.WHISPER_TRANSCRIBE_PATH)
    assert "file" in calls[0]["files"]           # multipart — как OpenAI


def test_post_transcription_404_honest(home, monkeypatch):
    import requests

    class FakeResp:
        status_code = 404

        def raise_for_status(self):
            pass

    monkeypatch.setattr(requests, "post",
                        lambda *a, **kw: FakeResp())
    with pytest.raises(RuntimeError) as ei:
        bridge._post_transcription(b"RIFF....")
    assert "--inference-path" in str(ei.value)   # лечение — в тексте ошибки


def test_transcribe_wraps_failure(home, monkeypatch):
    monkeypatch.setattr(bridge, "ensure_server",
                        lambda wait_secs=None: (False, "слуги нет"))
    text, note = bridge.transcribe(_loud_pcm(0.5))
    assert text is None and "слуги нет" in note

    def boom(wav):
        raise RuntimeError("порт закрыт")

    monkeypatch.setattr(bridge, "ensure_server",
                        lambda wait_secs=None: (True, "на посту"))
    monkeypatch.setattr(bridge, "_post_transcription", boom)
    text, note = bridge.transcribe(_loud_pcm(0.5))
    assert text is None and "расшифровка не удалась" in note


# ---------- полный ход: честность каждой ступени ----------

class FakeReply:
    def __init__(self, text, source="brain"):
        self.text, self.source, self.meta = text, source, {"tok": 42}


def _patch_pipeline(monkeypatch, text=None, fail=False,
                    reply="Сейчас 15:34, воскресенье."):
    """Швы хода: расшифровка и агент — подменяются, счётчик_calls честен."""
    asked = {"transcribe": 0, "agent": 0}

    def fake_transcribe(pcm, sample_rate=16000):
        asked["transcribe"] += 1
        if fail:
            return None, "слуга не поднялся"
        return text, "расшифровал"

    def fake_agent(t, history=None, voice=False):
        asked["agent"] += 1
        asked["agent_text"] = t
        asked["voice"] = voice
        return FakeReply(reply)

    monkeypatch.setattr(bridge, "transcribe", fake_transcribe)
    monkeypatch.setattr(bridge, "_agent_answer", fake_agent)
    return asked


def test_handle_phrase_full_exchange(home, monkeypatch):
    asked = _patch_pipeline(monkeypatch, text="Марфа, который час")
    rec = bridge.handle_phrase(_loud_pcm(1.5), 16000, had_voice=True)
    assert rec["event"] == "exchange"
    assert rec["phrase"] == "Марфа, который час"
    assert rec["answer"] == "Сейчас 15:34, воскресенье."
    assert rec["seq"] == 1 and rec["tok"] == 42
    assert asked["agent"] == 1
    # Ф160 (круг 26): голосовой ход несёт дому свой ИСТОЧНИК — агент
    # знает, что его позвали голосом (не печатью)
    assert asked["voice"] is True
    # разговор голосом — своя сессия, переживает всё (№11)
    from core.dialog import DialogStore
    turns = DialogStore().turns(config.VOICE_SESSION)
    assert [t["role"] for t in turns] == ["user", "assistant"]
    assert turns[0]["text"] == "Марфа, который час"
    # журнал голосовых ходов: одна строка на обмен (правило 6.6)
    data = bridge.voice_recent(after=-1)
    assert data["seq"] == 1 and len(data["turns"]) == 1
    # статус: не «в работе», последняя фраза помнится
    st = json.loads(Path(config.VOICE_STATUS_FILE).read_text(
        encoding="utf-8"))
    assert st["busy"] is False and "который час" in st["last_phrase"]


def test_handle_phrase_skip_when_no_name(home, monkeypatch):
    """«Марка красивая» — ложная тревога сторожа: мозг не будим.

    Урок: «лишний запуск whisper на 3 секунды дешевле, чем проспать
    зов» — верно для СЛУГИ, но не для МОЗГА: фраза без имени в дом
    не идёт, exchange не рождается.
    """
    asked = _patch_pipeline(monkeypatch, text="марка красивая")
    rec = bridge.handle_phrase(_loud_pcm(1.5), 16000, had_voice=True)
    assert rec["event"] == "skip" and asked["agent"] == 0
    assert "имени в фразе нет" in rec["why"]


def test_handle_phrase_bare_call_is_a_turn(home, monkeypatch):
    """Одинокий зов «Марфа!» — законный ход (№39: зов слышит мозг)."""
    asked = _patch_pipeline(monkeypatch, text=None)
    rec = bridge.handle_phrase(_quiet_pcm(0.3), 16000, had_voice=True)
    assert rec["event"] == "exchange"
    assert asked["agent_text"] == "Марфа"
    assert rec["phrase"] == "Марфа"


def test_handle_phrase_silence_without_words_skipped(home, monkeypatch):
    asked = _patch_pipeline(monkeypatch, text="   ")
    rec = bridge.handle_phrase(_quiet_pcm(2.0), 16000, had_voice=False)
    assert rec["event"] == "skip" and asked["agent"] == 0
    assert "тишина без слов" in rec["why"]


def test_handle_phrase_whisper_failure_is_error_not_call(home, monkeypatch):
    """Провал слуги — НЕ «Марфа»: подмена провала зовом будила бы мозг
    вхолостую (урок мозга v4: не молча выбрасывать и не подменять)."""
    asked = _patch_pipeline(monkeypatch, fail=True)
    rec = bridge.handle_phrase(_loud_pcm(1.5), 16000, had_voice=True)
    assert rec["event"] == "error" and rec["stage"] == "whisper"
    assert asked["agent"] == 0


def test_handle_phrase_agent_crash_keeps_hearing(home, monkeypatch):
    """Крах агента — слух жив: ошибка в журнал, служба слушает дальше.
    Шов продлён честно (Ф160, круг 26): голосовой ход несёт voice=True —
    сигнатура шва знает источник реплики."""
    def boom(t, history=None, voice=False):
        raise RuntimeError("мозг уснул на ходу")

    monkeypatch.setattr(bridge, "transcribe",
                        lambda p, r=16000: ("Марфа, время", "ок"))
    monkeypatch.setattr(bridge, "_agent_answer", boom)
    rec = bridge.handle_phrase(_loud_pcm(1.0), 16000, had_voice=True)
    assert rec["event"] == "error" and "мозг уснул" in rec["error"]
    st = json.loads(Path(config.VOICE_STATUS_FILE).read_text(
        encoding="utf-8"))
    assert st["busy"] is False      # флаг «в работе» снят — панель не врёт


def test_handle_phrase_wake_forms_accepted(home, monkeypatch):
    """Падежи имени в расшифровке — тоже зов («спасибо, Марфе» — живая
    речь, whisper падежи пишет как слышит)."""
    for form in ("Марфа", "Марфу", "Марфе"):
        asked = _patch_pipeline(monkeypatch, text="передай %s привет" % form)
        rec = bridge.handle_phrase(_loud_pcm(1.0), 16000, had_voice=True)
        assert rec["event"] == "exchange", form


# ---------- журнал и статус ----------

def test_voice_append_seq_monotonic_and_recent(home):
    a = bridge.voice_append({"event": "exchange", "phrase": "раз"})
    b = bridge.voice_append({"event": "exchange", "phrase": "два"})
    assert a["seq"] == 1 and b["seq"] == 2
    data = bridge.voice_recent(after=1)
    assert data["seq"] == 2
    assert [t["phrase"] for t in data["turns"]] == ["два"]
    assert bridge.voice_recent(after=2)["turns"] == []


def test_voice_recent_broken_lines_skipped(home):
    p = Path(config.VOICE_LOG_FILE)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("не json\n\n{\"seq\": 5, \"event\": \"exchange\", "
                 "\"phrase\": \"живая\"}\n", encoding="utf-8")
    data = bridge.voice_recent(after=-1)
    assert data["seq"] == 5
    assert [t["phrase"] for t in data["turns"]] == ["живая"]


def test_voice_recent_no_file(home):
    assert bridge.voice_recent() == {"seq": 0, "turns": []}


def test_voice_busy_flag_fresh_and_stale(home):
    bridge._voice_status("ok", busy=True)
    assert bridge.voice_busy() is True
    bridge._voice_status("ok", busy=False)
    assert bridge.voice_busy() is False
    # протухший флаг (3+ минуты) — не «в работе»
    Path(config.VOICE_STATUS_FILE).write_text(json.dumps(
        {"ts": (dt.datetime.now() - dt.timedelta(minutes=10)).isoformat(
            timespec="seconds"), "busy": True}), encoding="utf-8")
    assert bridge.voice_busy() is False


def test_state_line_alive_missing_stale(home):
    assert bridge.state_line() == ""            # службы нет — строки нет
    bridge._voice_status("ok")
    line = bridge.state_line()
    assert "вслух" in line and "мост ушей" in line
    Path(config.VOICE_STATUS_FILE).write_text(json.dumps(
        {"ts": (dt.datetime.now() - dt.timedelta(hours=1)).isoformat(
            timespec="seconds"), "state": "ok"}), encoding="utf-8")
    assert bridge.state_line() == ""            # протухло — не врём


# ---------- осмотр по ступеням ----------

def test_selftest_missing_parts_honest(home):
    text = bridge.selftest()
    assert "модель whisper: НЕТ" in text
    assert "whisper-сервер: НЕТ" in text
    assert "ЧТО ДЕЛАТЬ" in text


def test_selftest_ready_when_parts_present(home):
    (Path(config.MODELS_DIR) / "ggml-large-v3-turbo.bin").write_bytes(b"x")
    lcpp = Path(config.HOME_DIR) / "llama.cpp"
    lcpp.mkdir()
    (lcpp / "whisper-server.exe").write_bytes(b"x")
    bridge._voice_status("ok")
    text = bridge.selftest()
    assert "МОСТ В СТРОЮ" in text and "на месте" in text


def test_check_reports_spawn_failure(home, monkeypatch, capsys):
    monkeypatch.setattr(bridge, "ensure_server",
                        lambda wait_secs=None: (False, "не ожил"))
    verdict = bridge.check()
    assert "не поднялся" in verdict


def test_check_verdict_on_silence(home, monkeypatch, capsys):
    monkeypatch.setattr(bridge, "ensure_server",
                        lambda wait_secs=None: (True, "на посту"))
    monkeypatch.setattr(bridge, "_post_transcription",
                        lambda wav: "")
    assert "МОСТ ГОТОВ" in bridge.check()
    monkeypatch.setattr(bridge, "_post_transcription",
                        lambda wav: "спасибо за просмотр")
    assert "бормочет" in bridge.check()         # привычка whisper — честно


# ---------- проводка в дом: агент, состояние, зеркало ----------

def test_agent_command_proveri_most(agent, srv):
    r = agent.handle("проверь мост")
    assert r.source == "python" and r.tool_used == "ear_bridge_selftest"
    assert "ПРОВЕРКА МОСТА УШЕЙ" in r.text


def test_agent_command_most_after_ears(agent, srv):
    """Порядок веток: «проверь уши» осталось ушей, «мост» — мостом."""
    r = agent.handle("проверь уши")
    assert r.tool_used == "ears_selftest"


def test_agent_house_state_knows_bridge(agent, srv, home):
    text = _house_state()
    assert "мост ушей" not in text          # службы нет — строки нет
    bridge._voice_status("ok")
    text = _house_state()
    assert "говорить вслух" in text         # мозг ЗНАЕТ о новом канале


def test_identity_bridge_note_honest(home):
    note = identity.bridge_note()
    assert "модели whisper нет" in note
    (Path(config.MODELS_DIR) / "ggml-large-v3-turbo.bin").write_bytes(b"x")
    lcpp = Path(config.HOME_DIR) / "llama.cpp"
    lcpp.mkdir()
    (lcpp / "whisper-server.exe").write_bytes(b"x")
    assert "построен" in identity.bridge_note()


def test_identity_report_and_manifest_voice(agent, srv):
    report = identity.capabilities_report(memory=agent.memory)
    assert "Мост ушей (вторая ступень)" in report
    # день-10 (Ф56–Ф60): организм заговорил — прежняя честность «рта
    # нет» СТАЛА ложью; якорь следует за правдой, как и зеркало
    assert "Голос:" in report and "рта нет" not in report
    manifest = identity.manifest()
    assert "СЛЫШУ голосом" in manifest             # мозг знает о канале
    assert "проверь мост" in manifest              # и о команде осмотра
    assert "скажи вслух" in manifest               # и о своём голосе (Ф56)
