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

import sensors.ears as ears_mod
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


# ---------- служба ушей: вечный сторож для автозапуска ----------

class _Stop(BaseException):
    """Разрыв бесконечного цикла службы в тестах (как Ctrl+C — его служба
    пропускает мимо всех except Exception)."""


def _run_serve(monkeypatch, tmp_path, sd_module, sentinel=None,
               stop_after=2):
    """serve() с подменённым миром; сон выбрасывает _Stop после N вызовов."""
    import sensors.ears as ears

    monkeypatch.setattr(ears.config, "EARS_STATUS_FILE",
                        tmp_path / "ears_status.json")
    if sentinel is not None:
        monkeypatch.setattr(ears, "NameSentinel", sentinel)
    # None = «пакета нет»: None в sys.modules роняет import sounddevice
    # ImportError'ом на ЛЮБОЙ машине — даже там, где пакет стоит в venv.
    # Урок станции 21.11: настоящий sounddevice без микрофона провёл
    # службу до честного «no_mic» — и тест «нет пакета» провалился.
    monkeypatch.setitem(sys.modules, "sounddevice", sd_module)

    calls = {"n": 0}

    def fake_sleep(secs):
        calls["n"] += 1
        if calls["n"] >= stop_after:
            raise _Stop()

    monkeypatch.setattr(ears.time, "sleep", fake_sleep)
    try:
        ears.serve(retry_secs=0.01, heartbeat=0.01)
    except _Stop:
        pass
    status = tmp_path / "ears_status.json"
    rec = json.loads(status.read_text(encoding="utf-8")) if status.exists() else {}
    return rec, calls["n"]


class _FakeStream:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


_DEVICES = [
    {"name": "Динамики (RealTek)", "max_input_channels": 0},
    {"name": "HD WebCam Mic", "max_input_channels": 1},
]


class _SdOk:
    """Фальшивый sounddevice: поток открывается и живёт."""

    @staticmethod
    def query_devices(kind=None):
        if kind == "input":
            return {"name": "Микрофон по умолчанию",
                    "max_input_channels": 2}
        return list(_DEVICES)

    @staticmethod
    def RawInputStream(**kw):
        return _FakeStream()


class _SdNoMic:
    """Фальшивый sounddevice: как Z440 без микрофона («Error querying device -1»)."""

    class PortAudioError(Exception):
        pass

    @staticmethod
    def query_devices(kind=None):
        if kind == "input":
            return {"name": "микрофон по умолчанию",
                    "max_input_channels": 0}
        return []

    @staticmethod
    def RawInputStream(**kw):
        raise _SdNoMic.PortAudioError("Error querying device -1")


class _SdWebcamOnly:
    """Дефолтного микрофона нет (PortAudio -1), но веб-камера со своим есть.

    Урок Создателя 22.11: камера подключена, а её микрофон не выбран
    системой «по умолчанию» — старая служба честно писала «no_mic»,
    хотя микрофон в доме ЕСТЬ."""

    opened = []

    @staticmethod
    def query_devices(kind=None):
        if kind == "input":
            raise RuntimeError("Error querying device -1")
        return list(_DEVICES)

    @staticmethod
    def RawInputStream(**kw):
        if "device" not in kw:
            raise RuntimeError("Error querying device -1")
        _SdWebcamOnly.opened.append(kw["device"])
        return _FakeStream()


class _SentinelOk:
    sample_rate = 16000
    model_dir = Path("stub-model")

    def __init__(self, *a, **k):
        pass


def test_service_no_mic_reports_and_retries(monkeypatch, tmp_path):
    """Урок Z440: микрофона нет — служба НЕ умирает, пишет статус и ждёт."""
    rec, sleeps = _run_serve(monkeypatch, tmp_path, _SdNoMic(),
                             sentinel=_SentinelOk, stop_after=3)
    assert rec["state"] == "no_mic"
    assert "device -1" in rec["error"]          # диагноз сохранён
    assert sleeps >= 3                          # цикл ждал и пробовал снова


def test_service_no_model_reports_and_retries(monkeypatch, tmp_path):
    """Модели нет — честный статус, служба жива (кнопка 85 чинит параллельно)."""

    def no_model(*a, **k):
        raise FileNotFoundError("модель ушей не найдена: stub")

    rec, sleeps = _run_serve(monkeypatch, tmp_path, _SdOk(),
                             sentinel=no_model, stop_after=2)
    assert rec["state"] == "no_model"
    assert sleeps >= 2


def test_service_no_sounddevice_reports(monkeypatch, tmp_path):
    """sounddevice не поставлен — статус с командой установки, не traceback."""
    rec, sleeps = _run_serve(monkeypatch, tmp_path, None,
                             sentinel=_SentinelOk, stop_after=2)
    assert rec["state"] == "no_sounddevice"
    assert "pip install sounddevice" in rec["error"]
    assert sleeps >= 2


def test_service_streams_and_heartbeats(monkeypatch, tmp_path):
    """Ухо живо: статус ok, сердце бьётся (каждый heartbeat — свежий ts)."""
    rec, sleeps = _run_serve(monkeypatch, tmp_path, _SdOk(),
                             sentinel=_SentinelOk, stop_after=3)
    assert rec["state"] == "ok"                  # сердцебиение дошло до файла
    assert rec.get("last_wake", "") == ""         # имени ещё не слышали
    assert "Микрофон по умолчанию" in rec.get("device", "")  # каким слушаем


def test_service_finds_webcam_mic(monkeypatch, tmp_path):
    """v2, урок Создателя 22.11: дефолтного микрофона нет, но веб-камера
    со своим есть — служба перебирает устройства сама и находит его."""
    _SdWebcamOnly.opened = []
    rec, sleeps = _run_serve(monkeypatch, tmp_path, _SdWebcamOnly(),
                             sentinel=_SentinelOk, stop_after=3)
    assert rec["state"] == "ok"                  # ухо открылось на веб-камере
    assert _SdWebcamOnly.opened == [1]           # индекс HD WebCam Mic
    assert "HD WebCam Mic" in rec.get("device", "")


# ---------- v2: чистая логика выбора устройства ----------

def test_input_devices_default_first():
    """Сначала «по умолчанию» (None), потом все входящие — порядок закона."""
    devs = ears_mod._input_devices(_SdOk())
    assert devs[0][0] is None                    # дефолт первым
    names = [name for _, name in devs]
    assert "HD WebCam Mic" in names
    assert "Динамики (RealTek)" not in names     # выход — не ухо


def test_open_ear_stream_tries_all_devices():
    """Дефолт не открылся — берём следующий входящий (веб-камеру)."""
    stream, name = ears_mod._open_ear_stream(_SdWebcamOnly(), 16000,
                                             lambda *a: None)
    assert name == "HD WebCam Mic"
    assert _SdWebcamOnly.opened[-1] == 1


def test_open_ear_stream_nothing_honest():
    """Ни одно устройство не открылось — исключение перечисляет попытки."""
    with pytest.raises(RuntimeError) as ei:
        ears_mod._open_ear_stream(_SdNoMic(), 16000, lambda *a: None)
    assert "ни один микрофон" in str(ei.value)


def test_service_wake_updates_last_wake(monkeypatch, tmp_path):
    """Слышала имя — статус запоминает, что и когда (для панели и статуса дома)."""
    import sensors.ears as ears

    monkeypatch.setattr(ears.config, "EARS_STATUS_FILE",
                        tmp_path / "ears_status.json")
    monkeypatch.setitem(sys.modules, "sounddevice", _SdOk())

    class SentinelWithSpeech:
        sample_rate = 16000
        model_dir = Path("stub-model")

        def feed(self, chunk):
            return {"event": "wake", "text": "марфа включи свет", "word": "марфа"}

    monkeypatch.setattr(ears, "NameSentinel", SentinelWithSpeech)

    captured = {}

    class SdCallback(_SdOk):
        @staticmethod
        def RawInputStream(**kw):
            captured.update(kw)      # ловим callback потока
            return _FakeStream()

    monkeypatch.setitem(sys.modules, "sounddevice", SdCallback())

    def fake_sleep(secs):
        captured["callback"](b"\x00" * 3200, 0, None, None)  # кадр с именем
        raise _Stop()

    monkeypatch.setattr(ears.time, "sleep", fake_sleep)
    try:
        ears.serve(retry_secs=0.01, heartbeat=0.01)
    except _Stop:
        pass
    rec = json.loads((tmp_path / "ears_status.json").read_text(encoding="utf-8"))
    assert rec["state"] == "ok"
    assert "марфа включи свет" in rec["last_wake"]


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


# ---------- «проверь уши» (23.11): осмотр по ступеням с рецептом ----------

def _home(monkeypatch, tmp_path, state=None):
    """tmp-дом со статусом ушей по желанию теста."""
    from core import config
    monkeypatch.setenv("MARFA_HOME", str(tmp_path))
    monkeypatch.setattr(config, "HOME_DIR", tmp_path)
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(config, "EARS_STATUS_FILE",
                        tmp_path / "data" / "ears_status.json")
    monkeypatch.setattr(config, "EARS_MODEL_DIR",
                        tmp_path / "models" / "vosk-model-small-ru-0.22")
    return config


def test_selftest_service_alive_reports_and_rejoices(monkeypatch, tmp_path):
    """Служба жива — осмотр радуется и зовёт проверить голосом, а не
    молчит «не могу слышать»."""
    import datetime as dt
    cfg = _home(monkeypatch, tmp_path)
    cfg.DATA_DIR.mkdir(parents=True, exist_ok=True)
    cfg.EARS_STATUS_FILE.write_text(json.dumps({
        "ts": dt.datetime.now().isoformat(timespec="seconds"),
        "state": "ok", "device": "Микрофон веб-камеры"}), encoding="utf-8")
    text = ears_mod.selftest()
    assert "живы" in text and "Микрофон веб-камеры" in text
    assert "позови" in text and "Марфа" in text


def test_selftest_dead_service_names_the_fix(monkeypatch, tmp_path):
    """Служба молчит — осмотр называет РЕЦЕПТ (Старт дома / кнопка 89),
    урок живого лога: «не могу слышать голос» без пути лечения."""
    _home(monkeypatch, tmp_path)      # нет статуса — служба не пишет сердце
    text = ears_mod.selftest()
    assert "не слышу: служба ушей не пишет сердцебиение" in text
    assert "89" in text and "Старт_Марфа" in text


def test_selftest_nested_model_detected(monkeypatch, tmp_path):
    """Вложенная распаковка модели — классика «Извлечь всё»: осмотр
    видит её и зовёт кнопку 85 по имени."""
    cfg = _home(monkeypatch, tmp_path)
    nested = cfg.EARS_MODEL_DIR / cfg.EARS_MODEL_DIR.name / "am"
    nested.mkdir(parents=True, exist_ok=True)
    (nested / "final.mdl").write_bytes(b"x")
    text = ears_mod.selftest()
    assert "ВЛОЖЕННАЯ" in text and "85" in text


def test_selftest_no_model_no_sounddevice_honest(monkeypatch, tmp_path):
    """Нет модели и нет обёртки звука — обе ступени честны, каждая со
    своей командой; никаких «попробуй позже»."""
    import sys as _sys
    _home(monkeypatch, tmp_path)
    real_import = __import__

    def _no_sd(name, *a, **kw):
        if name == "sounddevice":
            raise ImportError("нет пакета")
        return real_import(name, *a, **kw)

    monkeypatch.setattr("builtins.__import__", _no_sd)
    text = ears_mod.selftest()
    monkeypatch.undo()
    assert "модель ушей: НЕТ" in text
    assert "sounddevice" in text and "venv" in text


def test_selftest_mics_listed(monkeypatch, tmp_path):
    """Windows видит микрофоны — осмотр называет их по именам (Создатель
    должен видеть, каким устройством дом слушает)."""
    _home(monkeypatch, tmp_path)

    class FakeSD:
        @staticmethod
        def query_devices(kind=None):
            if kind == "input":
                return {"name": "Микрофон (Webcam HD)", "max_input_channels": 1}
            return [{"name": "Микрофон (Webcam HD)", "max_input_channels": 1},
                    {"name": "Динамики", "max_input_channels": 0}]

    import sys as _sys
    _sys.modules["sounddevice"] = FakeSD()
    try:
        text = ears_mod.selftest()
    finally:
        del _sys.modules["sounddevice"]
    assert "Webcam HD" in text
