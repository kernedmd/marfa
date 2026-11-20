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

from sensors.ears import (NameSentinel, heard_wake, levenshtein,
                         model_files_ok, normalize)


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


# ---------- маркер здоровой папки модели ----------

def test_model_files_ok_marker(tmp_path):
    # маркер — am/final.mdl (есть в любой модели alphacephei)
    assert model_files_ok(tmp_path) is False
    (tmp_path / "am").mkdir()
    assert model_files_ok(tmp_path) is False
    (tmp_path / "am" / "final.mdl").write_text("stub")
    assert model_files_ok(tmp_path) is True


# ---------- диагноз поломанной папки: по-русски и ДО vosk ----------

def test_sentinel_broken_folder_speaks_russian(tmp_path, monkeypatch):
    """Папка есть, файлов нет — ошибка объясняет, что делать.

    Урок первого живого прогона на Z440: vosk на такую папку отвечал
    голым «Failed to create a model». Диагноз ставим ДО импорта vosk —
    поэтому подменяем vosk на сломанный: если порядок нарушится, тест упадёт.
    """
    empty = tmp_path / "vosk-model-small-ru-0.22"
    empty.mkdir()
    monkeypatch.setitem(sys.modules, "vosk", None)  # import vosk -> ImportError
    with pytest.raises(FileNotFoundError) as ei:
        NameSentinel(empty)
    msg = str(ei.value)
    assert "ФАЙЛОВ модели" in msg
    assert "85_fix_ears" in msg            # ошибка называет кнопку-лекаря


def test_sentinel_nested_folder_points_exactly(tmp_path, monkeypatch):
    """Вложенная распаковка — ошибка называет точный путь вложенной папки."""
    nested = tmp_path / "vosk-model-small-ru-0.22" / "vosk-model-small-ru-0.22"
    (nested / "am").mkdir(parents=True)
    (nested / "am" / "final.mdl").write_text("stub")
    monkeypatch.setitem(sys.modules, "vosk", None)
    with pytest.raises(FileNotFoundError) as ei:
        NameSentinel(nested.parent)
    assert "ВЛОЖЕННО" in str(ei.value)
    assert str(nested) in str(ei.value)    # не «где-то там», а точный путь


# ---------- демо без sounddevice: инструкция, а не traceback ----------

def test_demo_missing_sounddevice_speaks_russian(monkeypatch, capsys):
    """Урок первого демо на Z440: голый «No module named 'sounddevice'».

    Теперь демо само печатает команду установки (и зеркало tuna)
    и выходит кодом 1 — без ледяного traceback.
    """
    import sensors.ears as ears
    monkeypatch.setitem(sys.modules, "sounddevice", None)  # import -> ImportError
    with pytest.raises(SystemExit) as ei:
        ears.demo(1.0)
    out = capsys.readouterr().out
    assert ei.value.code == 1
    assert "pip install sounddevice" in out      # точная команда
    assert "tuna" in out                        # запасное зеркало
    assert "venv" in out                        # правильный питон


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
