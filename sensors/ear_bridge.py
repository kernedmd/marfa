# -*- coding: utf-8 -*-
r"""sensors/ear_bridge.py — МОСТ УШЕЙ: вторая ступень слуха (фронт 4 «голос»).

Доктрина ушей — ДВЕ ступени (шапка sensors/ears.py, мастер-ТЗ):
  ступень 1 — сторож имени (vosk small): слушает вечно, ~1% CPU;
  ступень 2 — ЭТОТ МОДУЛЬ: whisper large-v3-turbo из чулана просыпается
    НА СЕКУНДЫ после зова и расшифровывает ФРАЗУ ЦЕЛИКОМ.

Так говорят с домом голосом: «Марфа, который час?» →
  1. сторож ловит имя (частичный результат — реакция не ждёт конца фразы);
  2. ловец фраз копит звук (кольцо-предыстория + до 10 с, конец — по
     тишине) — энергодетектор, чистая математика;
  3. whisper-слуга (порт 8086, CPU — VRAM принадлежит глазам) слушает
     OpenAI-совместимый путь /v1/audio/transcriptions и возвращает текст;
  4. текст идёт В ДОМ тем же путём, что строка из чата: Agent.handle —
     обращение «Марфа, …» снимает дом №39, быстрые команды срабатывают,
     мозг отвечает в сессию «голос»;
  5. обмен ложится в журнал data\voice\voice_log.jsonl — панель читает
     его (/api/voice) и показывает ход в чате живьём, с пометкой «услышала
     голосом».

Честность конструкции (гейт §5 и закон фактов):
- фраза БЕЗ имени (ложная тревога сторожа: «марка», оглушения) — не зов:
  обмен пишется в журнал со сноской, дом не беспокоим;
- whisper не поднимается / расшифровка не удалась — уши живут дальше,
  ошибка честно в журнал и статус, слух не рвётся (никакой орган не
  роняет слух);
- одинокий зов «Марфа!» без команды — тоже ход: дом №39, «зов слышит
  мозг»; но тишина БЕЗ слов — не зов, пропускаем молча;
- слуга whisper — ПО ВЫЗОВУ (как кодер): поднялся по зову, через 5 минут
  тишины лёг. RAM ~2 ГБ на минутах разговора — не навсегда.

Логика — чистые функции и швы (тесты без микрофона и без моделей):
  pcm_to_wav / rms / PhraseCatcher — математика захвата;
  _post_transcription / _spawn_server / _agent_answer — швы HTTP и агента.

Запуск на Z440:
  venv\Scripts\python.exe sensors\ear_bridge.py --check    # глубокий осмотр
  venv\Scripts\python.exe sensors\ear_bridge.py --demo 60  # позови Марфу вслух
  venv\Scripts\python.exe sensors\ear_bridge.py --service  # вечная служба
"""
from __future__ import annotations

import datetime as dt
import json
import queue
import struct
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import config  # noqa: E402

# служебный импорт из ступени 1: сторож, открытие потока, статус ушей —
# мост НЕ дублирует механизмы, а надстраивается над живым ухом
from sensors.ears import (  # noqa: E402
    NameSentinel, _open_ear_stream, _write_status, normalize,
)

# что считаем «именем в расшифровке»: точное слово (whisper слышит лучше
# сторожа, оглушения ему не прощаем — иначе «марка красивая» будила бы мозг)
_WAKE_EXACT = ("марфа", "марфой", "марфу", "марфе", "марфы")


# ---------------------------------------------------------------
# Математика захвата фразы — чистые функции
# ---------------------------------------------------------------

def rms(pcm: bytes) -> float:
    """Среднеквадратичная громкость int16-модуля (пустой PCM — 0.0).

    Порог тишины — config.PHRASE_SILENCE_RMS; калибруется «проверь мост».
    """
    n = len(pcm) // 2
    if n == 0:
        return 0.0
    total = 0
    for i in range(0, len(pcm) - 1, 2):
        v = pcm[i] | (pcm[i + 1] << 8)
        if v >= 32768:          # int16 little-endian со знаком
            v -= 65536
        total += v * v
    return (total / n) ** 0.5


def pcm_to_wav(pcm: bytes, sample_rate: int = 16000) -> bytes:
    """PCM int16 моно → WAV-байты (контейнер, который ждёт whisper).

    RIFF-заголовок руками: аудио-библиотеки дому не нужны ради 44 байт.
    """
    byte_rate = sample_rate * 2
    hdr = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF", 36 + len(pcm), b"WAVE",
        b"fmt ", 16, 1, 1, sample_rate, byte_rate, 2, 16,
        b"data", len(pcm))
    return hdr + pcm


class PhraseCatcher:
    """Ловец фразы после зова. Кормим теми же чанками, что сторожа.

    arm()  — зов услышан: ловим (кольцо-предыстория уже при деле).
    feed() -> {"event": idle|capturing|done, "pcm": bytes, "voice": bool}

    Конец фразы: тишина config.PHRASE_SILENCE_SEC после зова ИЛИ потолок
    config.PHRASE_MAX_SEC (болтун без пауз не занимает микрофон навечно;
    долгая пауза после имени — тоже конец: «Марфа… [думаешь] …который
    час» ловится первой половиной, не тянем слугу в пустоту).
    «Голос был?» — честный флаг: имя часто звучит ДО срабатывания
    сторожа и живёт в кольце, а после arm() — уже тишина; кольцо тоже
    прослушиваем.
    """

    def __init__(self, sample_rate: int = 16000,
                 preroll_sec: float = config.PHRASE_PREROLL_SEC,
                 max_sec: float = config.PHRASE_MAX_SEC,
                 silence_sec: float = config.PHRASE_SILENCE_SEC,
                 silence_rms: float = config.PHRASE_SILENCE_RMS) -> None:
        self.sample_rate = sample_rate
        self.preroll_sec = preroll_sec
        self.max_sec = max_sec
        self.silence_sec = silence_sec
        self.silence_rms = silence_rms
        self._ring = bytearray()          # предыстория: последние preroll секунд
        self._ring_max = max(1, int(preroll_sec * sample_rate) * 2)
        self._phrase = bytearray()        # копится после arm()
        self._armed = False
        self._silence = 0.0               # тишина после последнего громкого чанка
        self._heard_voice = False         # был ли звук (кольцо + после зова)

    # -- управление ---------------------------------------------------------

    def arm(self) -> None:
        """Зов услышан — фраза начинается с кольца-предыстории."""
        self._phrase = bytearray(self._ring)
        self._armed = True
        self._silence = 0.0
        self._heard_voice = rms(bytes(self._ring)) >= self.silence_rms

    def is_armed(self) -> bool:
        return self._armed

    # -- основной поток -----------------------------------------------------

    def feed(self, chunk: bytes) -> dict:
        if not self._armed:
            self._ring.extend(chunk)
            if len(self._ring) > self._ring_max:
                del self._ring[:len(self._ring) - self._ring_max]
            return {"event": "idle", "pcm": b"", "voice": False}

        self._phrase.extend(chunk)
        secs = len(self._phrase) / 2.0 / self.sample_rate
        if rms(chunk) >= self.silence_rms:
            self._silence = 0.0
            self._heard_voice = True
        else:
            self._silence += len(chunk) / 2.0 / self.sample_rate

        if secs >= self.max_sec or self._silence >= self.silence_sec:
            self._armed = False
            return {"event": "done", "pcm": bytes(self._phrase),
                    "voice": self._heard_voice}
        return {"event": "capturing", "pcm": b"", "voice": False}


# ---------------------------------------------------------------
# Слуга whisper: найти, поднять, спросить, уложить (образец — кодер)
# ---------------------------------------------------------------

_SERVER_NAMES = ("whisper-server", "llama-whisper-server")


def find_whisper_model() -> Optional[Path]:
    """Тело whisper-turbo в чулане (АРСЕНАЛ: ggml-large-v3-turbo.bin).

    Точное имя/квант могли изменить — ищем по шаблону; нет — None, честно.
    """
    for pat in ("*large-v3-turbo*.bin", "*turbo*.bin", "*whisper*.bin"):
        cands = sorted(config.MODELS_DIR.glob(pat))
        if cands:
            return cands[0]
    return None


def find_whisper_server() -> Optional[Path]:
    """Бинарник whisper-сервера в сборке llama.cpp (или рядом).

    Имя в сборках гуляет (whisper-server / llama-whisper-server) — ищем
    оба; и в llama.cpp, и в whisper.cpp, если Создатель положил отдельно.
    """
    homes = [config.HOME_DIR / "llama.cpp", config.HOME_DIR / "whisper.cpp",
             config.HOME_DIR]
    for name in _SERVER_NAMES:
        for base in homes:
            p = base / (name + ".exe")
            if p.is_file():
                return p
    return None


def server_alive() -> bool:
    """Жив ли whisper-слуга: любой HTTP-ответ с порта — жив (даже 404:
    у whisper-server свои пути здоровья, нам достаточно, что порт служит).
    """
    import requests
    try:
        requests.get(config.WHISPER_URL, timeout=2)
        return True
    except Exception:
        return False


def _spawn_server(server: Path, model: Path) -> str:
    """Поднять whisper-слугу в своей консоли — как старт дома.

    Минимальный набор флагов (не выдумываем): модель, адрес, порт и
    OpenAI-путь --inference-path — его понимают свежие сборки whisper.cpp.
    """
    cmd = ('"%s" -m "%s" --host 127.0.0.1 --port %d --inference-path %s'
           % (server, model, config.PORT_WHISPER,
              config.WHISPER_TRANSCRIBE_PATH))
    subprocess.Popen(cmd, shell=True, cwd=str(config.HOME_DIR),
                     creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0))
    return cmd


_last_used = 0.0     # когда слуга работал последний раз (keepalive)


def ensure_server(wait_secs: Optional[float] = None) -> tuple:
    """Поднять whisper-слугу: (жив ли, честная сводка). Образец — кодер.

    CPU-слуга: VRAM не трогает, глаза не присаживаются (принцип хозяина
    ресурса) — танца нет, только подъём и ожидание здоровья.
    """
    global _last_used
    wait_secs = config.WHISPER_START_WAIT_SECS if wait_secs is None else wait_secs
    _last_used = time.time()
    if server_alive():
        return True, "whisper-слуга уже на посту"
    server = find_whisper_server()
    if server is None:
        return False, ("whisper-сервера нет в сборке: жду whisper-server.exe "
                       "в %s (свежая сборка llama.cpp/whisper.cpp для Windows; "
                       "если слуга в консоли упал на флаге --inference-path — "
                       "сборка старая, нужен свежий выпуск)"
                       % (config.HOME_DIR / "llama.cpp"))
    model = find_whisper_model()
    if model is None:
        return False, ("модели whisper нет в чулане: жду ggml-large-v3-turbo"
                       "*.bin в %s — проверь АРСЕНАЛ, раздел «готовы к найму»"
                       % config.MODELS_DIR)
    try:
        _spawn_server(server, model)
    except Exception as e:
        return False, "не поднялся: %s" % e
    deadline = time.time() + wait_secs
    while time.time() < deadline:
        if server_alive():
            return True, ("whisper-слуга на посту (%s, %s)"
                          % (server.name, model.name))
        time.sleep(2.0)
    return False, ("не ожил за %.0f с — посмотри его консоль (флаг "
                   "--inference-path старой сборкой не понят?)" % wait_secs)


def maybe_release() -> str:
    """Уложить слугу, если он простаивает дольше keepalive (закон арсенала:
    модель без работы не гоняется). Вызывается сердцебиением службы.
    """
    if not server_alive() or _last_used <= 0:
        return ""
    if time.time() - _last_used < config.WHISPER_KEEPALIVE_SEC:
        return ""
    from core.vram import stop_llama
    for name in _SERVER_NAMES:
        if stop_llama(config.PORT_WHISPER, server_name=name):
            return ("whisper-слуга лёг (тишина %d с)"
                    % config.WHISPER_KEEPALIVE_SEC)
    return ""


def _post_transcription(wav_bytes: bytes) -> str:
    """ШОВ ДЛЯ ТЕСТОВ: HTTP-вызов whisper-слуги (OpenAI-совместимый).

    multipart: file=phrase.wav + model + response_format=json; ответ
    {"text": "..."} — как у OpenAI, только локально.
    """
    import requests
    r = requests.post(
        config.WHISPER_URL + config.WHISPER_TRANSCRIBE_PATH,
        files={"file": ("phrase.wav", wav_bytes, "audio/wav")},
        data={"model": "whisper-1", "response_format": "json"},
        timeout=config.WHISPER_TIMEOUT_SEC)
    if r.status_code == 404:
        raise RuntimeError("слуга не знает путь %s — нужен --inference-path "
                           "при старте whisper-server (свежая сборка)"
                           % config.WHISPER_TRANSCRIBE_PATH)
    r.raise_for_status()
    data = r.json()
    text = data.get("text") if isinstance(data, dict) else None
    if not isinstance(text, str):
        raise RuntimeError("слуга ответил не текстом: %.120s" % data)
    return text


def transcribe(pcm: bytes, sample_rate: int = 16000) -> tuple:
    """Фраза-PCM → (текст | None, сводка действий).

    None — слуга не смог (не поднялся / путь не отвечает): честная сводка
    возвращает вместо текста, подменять «Марфой» провал нельзя.
    """
    ok, note = ensure_server()
    if not ok:
        return None, note
    try:
        return _post_transcription(pcm_to_wav(pcm, sample_rate)), \
            note + "; расшифровал"
    except Exception as e:
        return None, "%s; расшифровка не удалась: %s" % (note, e)


# ---------------------------------------------------------------
# Журнал голосовых ходов: один обмен — одна строка (правило 6.6)
# ---------------------------------------------------------------

_LOG_MAX_LINES = 5000     # потолок журнала; старое честно подрезается
_LOG_KEEP_LINES = 4000


def _now() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


def voice_append(rec: dict) -> dict:
    """Дописать ход в data\\voice\\voice_log.jsonl; seq сквозной.

    Файл — не орган дыхания: ошибка записи не рвёт слух, ход просто
    не попадёт в журнал (разговор живёт в сессии «голос» и так).
    """
    try:
        p = Path(config.VOICE_LOG_FILE)
        p.parent.mkdir(parents=True, exist_ok=True)
        lines = []
        if p.is_file():
            lines = [ln for ln in p.read_text(encoding="utf-8").splitlines()
                     if ln.strip()]
        last_seq = 0
        if lines:
            try:
                last_seq = int(json.loads(lines[-1]).get("seq") or 0)
            except (ValueError, IndexError):
                last_seq = 0
        rec = dict(rec)
        rec["seq"] = last_seq + 1
        rec.setdefault("ts", _now())
        lines.append(json.dumps(rec, ensure_ascii=False))
        if len(lines) > _LOG_MAX_LINES:      # подрезка: seq живёт в строках
            lines = lines[-_LOG_KEEP_LINES:]
        tmp = p.with_suffix(".tmp")
        tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
        tmp.replace(p)
        return rec
    except OSError:
        return dict(rec, seq=0)


def voice_recent(after: int = -1, limit: int = 50) -> dict:
    """Ходы новее seq=after: {"seq": последний, "turns": [...]}.

    Для панели (/api/voice): страница помнит последний показанный seq и
    спрашивает только прирост. Битые строки пропускаем молча — журнал
    не должен ронять страницу.
    """
    p = Path(config.VOICE_LOG_FILE)
    out = []
    last = 0
    try:
        if p.is_file():
            for ln in p.read_text(encoding="utf-8").splitlines():
                ln = ln.strip()
                if not ln:
                    continue
                try:
                    rec = json.loads(ln)
                except ValueError:
                    continue
                if not isinstance(rec, dict):
                    continue
                try:
                    seq = int(rec.get("seq") or 0)
                except (TypeError, ValueError):
                    seq = 0
                last = max(last, seq)
                if seq > after:
                    out.append(rec)
    except OSError:
        pass
    return {"seq": last, "turns": out[-limit:] if limit else out}


def _voice_status(state: str, error: str = "", phrase: str = "",
                  busy: bool = False, device: str = "") -> None:
    """Сердцебиение моста: data\\voice\\status.json (как ears_status).

    busy=True — фраза в работе (расшифровка/ответ): панель показывает
    «услышала голосом, думаю…», а не молчит минуту.
    """
    rec = {"ts": _now(), "sensor": "ear_bridge", "state": state,
           "busy": bool(busy)}
    if error:
        rec["error"] = error[:300]
    if phrase:
        rec["last_phrase"] = phrase[:300]
    if device:
        rec["device"] = device[:120]
    try:
        Path(config.VOICE_STATUS_FILE).parent.mkdir(parents=True, exist_ok=True)
        Path(config.VOICE_STATUS_FILE).write_text(
            json.dumps(rec, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


def voice_busy() -> bool:
    """Фраза в работе? Панель спрашивает вместе с ходами."""
    try:
        rec = json.loads(Path(config.VOICE_STATUS_FILE).read_text(
            encoding="utf-8"))
        if not isinstance(rec, dict) or not rec.get("busy"):
            return False
        ts = dt.datetime.fromisoformat(rec.get("ts") or "")
        return (dt.datetime.now() - ts).total_seconds() <= 180
    except (OSError, ValueError):
        return False


def state_line() -> str:
    """Строка для состояния дома: жива ли служба моста.

    Пустая строка — службы нет/молчит: состояние дома не толстеет
    (образец — правила №40: «законов нет — строки нет»). Живая служба
    говорит мозгу главное: СО МНОЙ МОЖНО ГОВОРИТЬ ВСЛУХ.
    """
    try:
        rec = json.loads(Path(config.VOICE_STATUS_FILE).read_text(
            encoding="utf-8"))
        if not isinstance(rec, dict):
            return ""
        ts = dt.datetime.fromisoformat(rec.get("ts") or "")
        if not -300.0 <= (dt.datetime.now() - ts).total_seconds() <= 120:
            return ""
        if rec.get("state") == "ok":
            return ("мост ушей: служба жива — со мной можно говорить вслух "
                    "(«Марфа, <просьба>»), фразу услышу целиком")
        return "мост ушей: %s" % rec.get("state")
    except (OSError, ValueError, TypeError):
        return ""


# ---------------------------------------------------------------
# Ответ дома: фраза → Agent.handle (тем же путём, что строка из чата)
# ---------------------------------------------------------------

def _agent_answer(text: str, history: Optional[list] = None):
    """ШОВ ДЛЯ ТЕСТОВ: вызов агента дома. Ленивый импорт — служба ушей
    не должна падать на старте из-за проблем импорта агента."""
    from core.agent import Agent
    return Agent().handle(text, history=history)


def _has_wake_exact(text: str) -> bool:
    """Есть ли в расшифровке ТОЧНОЕ имя. Оглушения не прощаем: whisper
    слышит лучше сторожа; «марка красивая» — ложная тревога, не зов."""
    return any(w in _WAKE_EXACT for w in normalize(text).split())


def handle_phrase(pcm: bytes, sample_rate: int = 16000,
                  had_voice: bool = True) -> dict:
    """ПОЛНЫЙ ГОЛОСОВОЙ ХОД: фраза → текст → ответ дома → журнал.

    Возвращает запись журнала (exchange / skip / error). Ни один шаг не
    роняет слух: провал пишется честно, служба слушает дальше.
    """
    t0 = time.time()
    _voice_status("ok", busy=True)
    kept_phrase = ""
    try:
        # 1) расшифровка (одинокий короткий зов без слов — голое имя,
        #    дом №39: «Марфа» без продолжения — зов, его слышит мозг)
        secs = len(pcm) / 2.0 / sample_rate
        if secs < config.PHRASE_MIN_PCM_SEC and rms(pcm) < config.PHRASE_SILENCE_RMS:
            text, note = "Марфа", "короткий зов без слов"
        else:
            text, note = transcribe(pcm, sample_rate)
            if text is None:
                return voice_append({"event": "error", "stage": "whisper",
                                     "error": note})
            text = text.strip()
            if not text:
                if had_voice:
                    text = "Марфа"       # слова были, но whisper промолчал — зов
                else:
                    return voice_append(
                        {"event": "skip", "phrase": "",
                         "why": "тишина без слов — не зов"})
        kept_phrase = text
        # 2) имя в фразе? Ложная тревога сторожа («марка») — не будим мозг
        if not _has_wake_exact(text):
            return voice_append({"event": "skip", "phrase": text,
                                 "why": "имени в фразе нет — не зов"})
        # 3) ответ дома тем же путём, что строка из чата
        from core.dialog import DialogStore
        store = DialogStore()
        history = DialogStore.render_messages(
            store.turns(config.VOICE_SESSION))
        reply = _agent_answer(text, history=history)
        secs_total = round(time.time() - t0, 1)
        meta = {"voice": True, "secs": secs_total, "src": reply.source}
        if isinstance(getattr(reply, "meta", None), dict):
            for k in ("tok", "ptok"):
                v = reply.meta.get(k)
                if isinstance(v, (int, float)) and v:
                    meta[k] = v
        try:
            store.append(config.VOICE_SESSION, "user", text,
                         meta={"voice": True})
            store.append(config.VOICE_SESSION, "assistant", reply.text,
                         meta=meta)
        except (OSError, ValueError):
            pass  # сессия — не орган дыхания; журнал ниже всё запишет
        return voice_append({"event": "exchange", "phrase": text,
                             "answer": reply.text, "secs": secs_total,
                             "src": reply.source, "tok": meta.get("tok"),
                             "ptok": meta.get("ptok")})
    except Exception as e:
        return voice_append({"event": "error", "stage": "voice",
                             "error": "%s: %s" % (type(e).__name__, e)})
    finally:
        _voice_status("ok", phrase=kept_phrase, busy=False)


# ---------------------------------------------------------------
# Осмотр: «проверь мост» — по ступеням, с точным лечением
# ---------------------------------------------------------------

def selftest() -> str:
    r"""Живой осмотр моста ПО СТУПЕНЯМ (урок «проверь уши»): называем
    ступень поломки и ТОЧНОЕ лечение, ничего тяжёлого не запуская.

      1) МОДЕЛЬ — ggml-large-v3-turbo.bin в чулане?
      2) СЛУГА-БИНАРНИК — whisper-server.exe в сборке?
      3) СЕРДЦЕ — служба моста пишет status.json свежо?
      4) СЛУГА ЖИВ — порт 8086 отвечает? (нет — «поднимется по зову»,
         это не поломка)
    Исключений не поднимает.
    """
    lines = ["ПРОВЕРКА МОСТА УШЕЙ (вживую, не по памяти):"]

    model = find_whisper_model()
    if model:
        lines.append("- модель whisper: на месте (%s)" % model.name)
    else:
        lines.append("- модель whisper: НЕТ — жду ggml-large-v3-turbo*.bin "
                     "в %s (АРСЕНАЛ, «готовы к найму»)" % config.MODELS_DIR)

    server = find_whisper_server()
    if server:
        lines.append("- whisper-сервер: %s" % server)
    else:
        lines.append("- whisper-сервер: НЕТ в %s — свежая сборка llama.cpp/"
                     "whisper.cpp для Windows кладёт whisper-server.exe; "
                     "старую сборку обнови (нужен флаг --inference-path)"
                     % (config.HOME_DIR / "llama.cpp"))

    try:
        rec = json.loads(Path(config.VOICE_STATUS_FILE).read_text(
            encoding="utf-8"))
        ts = dt.datetime.fromisoformat(rec.get("ts") or "")
        fresh = (dt.datetime.now() - ts).total_seconds() <= 120
        state = rec.get("state") or "?"
    except (OSError, ValueError, TypeError):
        fresh, state = False, "нет статуса"
    if fresh:
        lines.append("- служба моста: жива (%s)" % state)
    else:
        lines.append("- служба моста: сердцебиения нет — подними дом "
                     "(Старт_Марфа.bat) или запусти venv\\Scripts\\python.exe "
                     "sensors\\ear_bridge.py --service")

    if server_alive():
        lines.append("- whisper-слуга: на посту (порт %d)" % config.PORT_WHISPER)
    else:
        lines.append("- whisper-слуга: спит — НЕ ПОЛОМКА: поднимется сам "
                     "по первому зову (слуга по вызову, как кодер)")

    ok_model, ok_server = bool(model), bool(server)
    if ok_model and ok_server and fresh:
        lines.append("МОСТ В СТРОЮ: позови «Марфа, …» вслух — фраза придёт "
                     "в чат с пометкой «услышала голосом».")
    elif ok_model and ok_server:
        lines.append("ЧТО ДЕЛАТЬ: поднять службу моста — она поднимется "
                     "вместе с домом (Старт_Марфа.bat).")
    else:
        lines.append("ЧТО ДЕЛАТЬ: сначала недостающие ступени выше — без "
                     "модели или бинарника мост не слышит фраз.")
    return "\n".join(lines)


def check() -> str:
    r"""Глубокий осмотр (--check): всё выше + ПРОБА ТИШИНЫ через слугу.

    Поднимает whisper-слугу и расшифровывает секунду синтетической
    тишины: честный ответ на тишину — пустой текст (или короткий
    артефакт — известная привычка whisper, виден сразу). Живой слуга
    после пробы не укладывается насильно: его уложит keepalive службы.
    """
    print(selftest())
    print()
    print("ПРОБА ТИШИНЫ: поднимаю слугу и расшифровываю 1 с тишины...")
    ok, note = ensure_server()
    print("- слуга: %s" % note)
    if not ok:
        return ("ИТОГ: слуга не поднялся — смотри его консоль. Если упал на "
                "флаге --inference-path, нужна свежая сборка whisper.cpp.")
    try:
        silence = b"\x00" * 16000 * 2       # 1 с тишины int16
        text = _post_transcription(pcm_to_wav(silence))
        print("- расшифровка тишины: «%s»" % (text or "(пусто)"))
        if text.strip():
            verdict = ("МОСТ РАБОТАЕТ, но whisper на тишине бормочет «%s» — "
                       "известная привычка модели; живые фразы громче тишины, "
                       "на деле почти не мешает." % text.strip()[:60])
        else:
            verdict = ("МОСТ ГОТОВ: путь уши → whisper → текст работает. "
                       "Позови «Марфа, время» и смотри чат.")
        print("- " + verdict)
        return verdict
    except Exception as e:
        print("- расшифровка не удалась: %s" % e)
        return ("ИТОГ: слуга жив, но путь %s не отвечает — проверь флаг "
                "--inference-path в консоли слуги."
                % config.WHISPER_TRANSCRIBE_PATH)


# ---------------------------------------------------------------
# Демо и служба
# ---------------------------------------------------------------

def _say(rec: dict) -> None:
    """Печать хода в консоль (демо и служба говорят одинаково)."""
    event = rec.get("event")
    ts = dt.datetime.now().strftime("%H:%M:%S")
    if event == "exchange":
        print("[%s] [ГОЛОС] «%s» → «%s»"
              % (ts, (rec.get("phrase") or "")[:80],
                 (rec.get("answer") or "")[:120]))
    elif event == "skip":
        print("[%s] [ГОЛОС] не зов: «%s» (%s)"
              % (ts, (rec.get("phrase") or "")[:80], rec.get("why")))
    else:
        print("[%s] [ГОЛОС] сбой: %s" % (ts, rec.get("error")))


def demo(seconds: float = 60.0) -> None:
    """Живое демо: слушай, лови, расшифруй, ответь — всё в консоль.

    Позови «Марфа, который час» — увидишь весь ход по шагам. Тяжёлая
    работа уходит в свой поток: микрофон не глухнет, пока думают.
    """
    try:
        import sounddevice
    except ImportError:
        print("=" * 60)
        print("НЕ ХВАТАЕТ ОДНОЙ ДЕТАЛИ: sounddevice — обёртка микрофона.")
        print(r"  C:\Marfa\venv\Scripts\python.exe -m pip install sounddevice")
        raise SystemExit(1)

    s = NameSentinel()
    catcher = PhraseCatcher(sample_rate=s.sample_rate)
    print("=" * 60)
    print("МАРФА — мост ушей, демо (%.0f с): позови «Марфа, ...»" % seconds)
    print("=" * 60)

    def callback(indata, frames, time_info, status):
        out = s.feed(bytes(indata))
        ev = catcher.feed(bytes(indata))
        if out["event"] == "wake" and not catcher.is_armed():
            catcher.arm()
            print("[%s] [ИМЯ!] ловлю фразу..."
                  % dt.datetime.now().strftime("%H:%M:%S"))
        if ev["event"] == "done" and ev["pcm"]:
            print("[%s] фраза %.1f с — расшифровываю..."
                  % (dt.datetime.now().strftime("%H:%M:%S"),
                     len(ev["pcm"]) / 2.0 / s.sample_rate))
            threading.Thread(
                target=_say, args=(handle_phrase(ev["pcm"], s.sample_rate,
                                                 ev.get("voice", True)),),
                daemon=True).start()

    try:
        stream, mic_name = _open_ear_stream(sounddevice, s.sample_rate, callback)
        with stream:
            print("Слушаю «%s»..." % mic_name)
            time.sleep(seconds)
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print("МИКРОФОН НЕ ПОДКЛЮЧЁН или занят: %s" % e)
        raise SystemExit(1)


def _voice_worker(q: "queue.Queue") -> None:
    """Рабочий поток: тяжёлая работа (whisper, мозг) — НЕ в аудио-потоке.

    Очередь сериализует фразы: пока думает первая, вторая ждёт своей.
    """
    while True:
        item = q.get()
        if item is None:
            return
        pcm, had_voice = item
        try:
            _say(handle_phrase(pcm, config.EARS_SAMPLE_RATE, had_voice))
        except Exception as e:
            print("[%s] рабочий моста споткнулся (слушаю дальше): %s"
                  % (dt.datetime.now().strftime("%H:%M:%S"), e))
        note = maybe_release()
        if note:
            print("[%s] %s" % (dt.datetime.now().strftime("%H:%M:%S"), note))


def serve(retry_secs: float = config.EARS_RETRY_SECS,
          heartbeat: float = 30.0) -> None:
    r"""СЛУЖБА МОСТА: вечный сторож имени + ловец фраз + whisper по зову.

    Отличия от ears.serve (ступень 1): тот же микрофон, тот же статус
    ушей (data\ears_status.json — старт дома по-прежнему видит слух),
    но каждый зов уезжает В ДОМ полным ходом. Никогда не сдаётся:
    нет микрофона/модели/звука — честный статус и ожидание, как у ушей.
    """
    print("=" * 60)
    print("МАРФА — служба моста ушей (сторож + фразы + whisper по зову)")
    print("=" * 60)
    while True:
        try:
            import sounddevice
        except ImportError:
            print("[%s] sounddevice не поставлен — жду (pip install sounddevice)"
                  % dt.datetime.now().strftime("%H:%M:%S"))
            _write_status("no_sounddevice", error="pip install sounddevice")
            _voice_status("no_sounddevice", error="pip install sounddevice")
            time.sleep(retry_secs)
            continue
        try:
            s = NameSentinel()
        except FileNotFoundError as e:
            print("[%s] %s" % (dt.datetime.now().strftime("%H:%M:%S"), e))
            _write_status("no_model", error=str(e))
            _voice_status("no_model", error=str(e))
            time.sleep(retry_secs)
            continue

        catcher = PhraseCatcher(sample_rate=s.sample_rate)
        q: "queue.Queue" = queue.Queue()
        threading.Thread(target=_voice_worker, args=(q,), daemon=True).start()
        last_wake = ""

        def callback(indata, frames, time_info, status):
            nonlocal last_wake
            chunk = bytes(indata)
            out = s.feed(chunk)
            ev = catcher.feed(chunk)
            if out["event"] == "wake" and not catcher.is_armed():
                catcher.arm()
                last_wake = ("%s | %s" % (dt.datetime.now()
                                          .strftime("%H:%M:%S"), out["text"]))
                print("[%s] [ИМЯ!] услышала: «%s» — ловлю фразу..."
                      % (dt.datetime.now().strftime("%H:%M:%S"), out["text"]))
                _write_status("ok", last_wake=last_wake)
            if ev["event"] == "done" and ev["pcm"]:
                q.put((ev["pcm"], ev.get("voice", True)))

        try:
            stream, mic_name = _open_ear_stream(sounddevice, s.sample_rate,
                                                callback)
            with stream:
                print("[%s] МОСТ ЖИВ: слушаю «%s» (%d Гц, модель %s)"
                      % (dt.datetime.now().strftime("%H:%M:%S"), mic_name,
                         s.sample_rate, s.model_dir.name))
                _write_status("ok", last_wake=last_wake, device=mic_name)
                _voice_status("ok", device=mic_name)
                while True:
                    time.sleep(heartbeat)
                    _write_status("ok", last_wake=last_wake, device=mic_name)
                    _voice_status("ok", device=mic_name)
                    note = maybe_release()
                    if note:
                        print("[%s] %s" % (dt.datetime.now()
                                           .strftime("%H:%M:%S"), note))
        except Exception as e:
            print("[%s] микрофон недоступен: %s — жду %.0f с и пробую снова"
                  % (dt.datetime.now().strftime("%H:%M:%S"), e, retry_secs))
            _write_status("no_mic", error=str(e))
            _voice_status("no_mic", error=str(e))
            time.sleep(retry_secs)


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else ""
    if arg == "--check":
        print(check())
    elif arg == "--demo":
        demo(float(sys.argv[2]) if len(sys.argv) > 2 else 60.0)
    elif arg == "--service":
        try:
            serve()
        except KeyboardInterrupt:
            print("служба моста остановлена (Ctrl+C)")
    else:
        print(__doc__)
