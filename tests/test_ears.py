# -*- coding: utf-8 -*-
r"""tests/test_ears.py — уши Марфы (Г-уши, Этап 1): сторож имени.

Логика пробуждения — чистые функции: проверяются без модели и микрофона.
NameSentinel — на фальшивом распознавателе (duck-тип, как fake_llama_server
для мозга). Живая модель — интеграционный тест, пропускается, если её нет.
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sensors.ears import NameSentinel, heard_wake, levenshtein, normalize


# ---------- normalize: канон услышанного ----------

def test_normalize_lowercase_yo_punct():
    assert normalize("Марфа!") == "марфа"
    assert normalize("МАРФУ, привет") == "марфу привет"
    assert normalize("ма-рфа") == "ма рфа"          # дефис — граница слова
    assert normalize("Ёлка ёж") == "елка еж"        # ё -> е
    assert normalize("") == ""


# ---------- levenshtein ----------

def test_levenshtein_basic():
    assert levenshtein("марфа", "марфа") == 0
    assert levenshtein("марфа", "марва") == 1   # оглушение ф->в
    assert levenshtein("марфа", "март") == 2
    assert levenshtein("", "аб") == 2
    assert levenshtein("аб", "") == 2


# ---------- heard_wake: главное — не проспать Создателя ----------

@pytest.mark.parametrize("phrase", [
    "Марфа", "марфа!", "МАРФУ", "Марфа, привет", "эй марва",
    "ну-ка марфу сюда", "скажи мне марфа пожалуйста",
])
def test_wake_heard(phrase):
    assert heard_wake(phrase) is not None


@pytest.mark.parametrize("phrase", [
    "март", "форма", "маркет", "рама", "погода хорошая", "",
])
def test_wake_not_heard(phrase):
    # «марка» дистанция 1 — осознанно срабатывает (лучше лишний whisper)
    assert heard_wake(phrase) is None


def test_wake_returns_token():
    assert heard_wake("Привет, МАРВА!") == "марва"


# ---------- NameSentinel на фальшивом распознавателе ----------

class FakeRec:
    """Кормим заранее прошитые ответы AcceptWaveform -> (final, json)."""

    def __init__(self, script):
        self.script = list(script)
        self.results = []

    def AcceptWaveform(self, chunk):
        final, payload = self.script.pop(0) if self.script else (True, {})
        res = json.dumps(payload)
        self.results.append(res)
        return final

    def Result(self):
        return self.results[-1]

    def PartialResult(self):
        return self.results[-1]

    def FinalResult(self):
        return self.results[-1]

    def SetWords(self, v):
        pass


def make_sentinel(monkeypatch, tmp_path, script):
    import sensors.ears as ears

    fake = FakeRec(script)

    class FakeVosk:
        Model = staticmethod(lambda path: object())
        KaldiRecognizer = staticmethod(lambda m, sr: fake)

    monkeypatch.setattr(ears, "vosk", FakeVosk, raising=False)
    # _classify пишет лог через config.EARS_LOG_FILE — уводим в tmp
    monkeypatch.setattr(ears.config, "EARS_LOG_FILE", tmp_path / "ears.jsonl")
    s = NameSentinel.__new__(NameSentinel)
    s.model_dir = tmp_path
    s.sample_rate = 16000
    s.wake_words = ears.config.EARS_WAKE_WORDS
    s.max_dist = 1
    s._vosk = FakeVosk
    s.model = object()
    s.rec = fake
    s.log_file = tmp_path / "ears.jsonl"
    s.last_event = "silence"
    return s, fake


def test_sentinel_wake_event(monkeypatch, tmp_path):
    s, _ = make_sentinel(monkeypatch, tmp_path, [
        (False, {"partial": "мар"}),
        (True, {"text": "марфа включи музыку"}),
    ])
    assert s.feed(b"\x00" * 3200)["event"] == "speech"
    out = s.feed(b"\x00" * 3200)
    assert out["event"] == "wake"
    assert out["word"] == "марфа"
    assert s.last_event == "wake"


def test_sentinel_wake_in_partial(monkeypatch, tmp_path):
    """Имя в ПРОМЕЖУТОЧНОМ результате — реакция не ждёт конца фразы."""
    s, _ = make_sentinel(monkeypatch, tmp_path, [
        (False, {"partial": "марфа где"}),
    ])
    out = s.feed(b"\x00" * 3200)
    assert out["event"] == "wake"


def test_sentinel_logs_to_jsonl(monkeypatch, tmp_path):
    s, _ = make_sentinel(monkeypatch, tmp_path, [(True, {"text": "марфа"})])
    s.feed(b"\x00" * 3200)
    log = (tmp_path / "ears.jsonl").read_text(encoding="utf-8").strip()
    rec = json.loads(log.splitlines()[-1])
    assert rec["event"] == "wake" and rec["sensor"] == "ears"


# ---------- интеграция: живая модель (станция/дом, если есть) ----------

@pytest.mark.parametrize("model_dir", [
    Path("/tmp/vosk-model-small-ru-0.22"),                    # станция
    Path(r"C:\Marfa\models\vosk-model-small-ru-0.22"),       # Z440
])
def test_real_model_silence(model_dir):
    pytest.importorskip("vosk")
    if not model_dir.is_dir():
        pytest.skip("модель ушей не найдена: %s" % model_dir)
    s = NameSentinel(model_dir)
    out = s.feed(b"\x00" * s.sample_rate * 2)   # 1 секунда тишины
    assert out["event"] == "silence"
    assert out["text"] == ""
