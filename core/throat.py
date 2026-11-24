# -*- coding: utf-8 -*-
"""core/throat.py — Ф121 «СЛУГА-ГЛОТО» (день-14, круг 23): Silero v5_6
превращает текст Марфы в ЗВУК С ИНТОНАЦИЕЙ — горло дома на порту 8084.

ПРОРОЧЕСТВО Ф56 ИСПОЛНИЛОСЬ. День-10 писал: «TTS-модель из чулана
остаётся спать, пока стандартный голос не покажется Создателю слабым —
тогда вернёмся». Создатель прослушал 12 живых проб и вынес вердикт:
«v5_6_ru, восклицание — норм». Дом вернулся к TTS — но не в чулан
(model_212000.safetensors спит дальше: не опознана — не нанята), а по
живой проверке. SAPI (Ирина) остаётся ЗАПАСНЫМ РТОМ: цепь честна —
горло спит, говорит SAPI; оба молчат — честный отказ с путём лечения.

ГЛОТКА ОТДЕЛЕНА ОТ РТА (урок ресурса): слуга-горло — чистый синтезатор
(CPU, torch.package, RTF ~0.03: 20 секунд речи за 0.6 с), отдаёт WAV
байтами по HTTP; РОТ (воспроизведение) остаётся в теле дома —
winsound (stdlib Windows) играет байты в потоке-демоне. Слуга не
трогает колонки, как эмбеддер не занимается поиском.

КРОССПЛАТФОРМЕННЫЙ ОРГАН — ЖИВОЙ ЯКОРЬ В ПЕСОЧНИЦЕ (Ф123): torch.package
не знает, где живёт (Win/Linux), — впервые в истории дома орган
проверяется ЖИВЬЁМ у архитектора: песочница слышит те же байты, что
услышит станция. Прежние якоря читали код — этот слушает голос.

Числа — прописью через орган Ф23 (numeral.words): «2026» горло
прочтёт «две тысячи двадцать шесть» ДО синтеза. Дроби, даты и телефоны
честно остаются как есть (v1: прописывать их — работа смысла, не
глотки; закон numeral.py: «дроби — мозгу»).

Здесь живёт КЛИЕНТ и ЧИСТАЯ ЛОГИКА (спикеры, нормализация, prosody);
сам слуга — sensors/throat.py. Чистые функции тестируются без torch
и без сервера (закон ушей: логика — швы, модели — по вызову).
"""
from __future__ import annotations

import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

from core import config

# ---------------------------------------------------------------
# Спикеры Silero v5_6_ru — проверены живьём (12 проб, песочница
# архитектора): available_speakers орган не отдаёт (None) — список
# вымерен на слух и байтами, хранит дом, не модель
# ---------------------------------------------------------------
SPEAKERS = {
    "baya": "бая",
    "kseniya": "ксения",
    "xenia": "ксения-латинская",
    "aidar": "айдар",
    "eugene": "евгений",
}
FEMALE = ("baya", "kseniya", "xenia")        # три женских, выбор Создателя
DEFAULT_SPEAKER = "baya"                     # вердикт день-14: восклицание — норм

# как Создатель зовёт голоса живой речью (ё уже приведена к е)
_ALIASES = {
    "бая": "baya", "байя": "baya", "баяю": "baya",
    "ксения": "kseniya", "ксенью": "kseniya", "ксения-кириллическая": "kseniya",
    "ксения латинская": "xenia", "ксения-латинская": "xenia",
    "xenia": "xenia", "ксения-2": "xenia",
    "айдар": "aidar", "айдару": "aidar",
    "евгений": "eugene", "евгения": "eugene",
}

# markdown-шум ответов Марфы: глазам — заголовок, глотке — помеха
_MD_NOISE = re.compile(r"[*#`_>~|]+")
_MD_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")   # [текст](ссылка) → текст
_MULTI_WS = re.compile(r"\s+")


# ---------------------------------------------------------------
# Чистая логика: спикеры, текст, prosody — без torch и без HTTP
# ---------------------------------------------------------------

def normalize_speaker(word: str) -> Optional[str]:
    """Живое имя голоса → id спикера. Латиница принимается напрямую
    (baya), кириллица — по словарю живой речи («бая», «смену на ксению»).
    Не голос — None: вызывающий скажет честно, какие голоса есть."""
    w = str(word or "").strip().lower().replace("ё", "е").rstrip("?.! ")
    if not w:
        return None
    w = w.replace("смени голос на ", "").replace("поменяй голос на ", "")
    w = w.replace("голос ", "").strip()
    if w in SPEAKERS:
        return w
    return _ALIASES.get(w)


def normalize_text(text: str) -> str:
    """Текст → то, что слышит глотка: без markdown-шума, целые числа —
    прописью (Ф23), пробелы — в один слой.

    Честные границы v1: дроби («3,5»), даты («25.11.2026»), телефоны
    («+7…») и числа с ведущим нулём («007») остаются цифрами —
    прописывать их — работа смысла, не глотки (закон numeral.py).
    """
    text = _MD_LINK.sub(r"\1", str(text or ""))
    text = _MD_NOISE.sub(" ", text)
    out = []
    for tok in text.split():
        core_tok = tok.strip(".,!?;:()«»\"'")
        if (core_tok.isdigit() and len(core_tok) <= 12
                and not (len(core_tok) > 1 and core_tok.startswith("0"))):
            from core import numeral
            try:
                tok = tok.replace(core_tok, numeral.words(int(core_tok)))
            except ValueError:
                pass          # больше триллиона — останется цифрами, честно
        out.append(tok)
    return _MULTI_WS.sub(" ", " ".join(out)).strip()


def rate_to_prosody(rate: int) -> Optional[str]:
    """Темп SAPI-шкалы (−5..5, Ф58) → prosody Silero. 0 — родной темп
    модели (SSML не нужен: меньше обёрток — меньше сюрпризов)."""
    rate = max(-5, min(5, int(rate)))
    if rate == 0:
        return None
    if rate <= -3:
        return "x-slow"
    if rate < 0:
        return "slow"
    if rate < 3:
        return "fast"
    return "x-fast"


def xml_escape(text: str) -> str:
    """Текст → тело SSML: три побега, которых требует XML."""
    return (text.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;"))


def build_ssml(text: str, rate: int) -> Optional[str]:
    """SSML-обёртка, если темп сдвинут. Родной темп — None: модель
    говорит чисто и без обёрток, интонацию «?» и «!» она читает сама
    (живая проверка круга 23: вопрос и восклицание различаются
    байтами — две волны, один текст, разные знаки)."""
    prosody = rate_to_prosody(rate)
    if not prosody:
        return None
    return ('<speak><prosody rate="%s">%s</prosody></speak>'
            % (prosody, xml_escape(text)))


def speakers_line() -> str:
    """Голоса горла человеческим языком — для «какие голоса»."""
    parts = []
    for sid, ru in SPEAKERS.items():
        mark = " (женский)" if sid in FEMALE else " (мужской)"
        parts.append("%s — «голос %s»" % (ru, sid))
    return "; ".join(parts)


def wake_note() -> str:
    """Честный путь лечения: как разбудить горло (доктрина слуги)."""
    return ("горло (silero) спит — разбудит кнопка scripts\\95_Горло.bat "
            "или «проверь голос»; посылка — docs\\ТЗ_Голос_v2.md, раздел 7")


# ---------------------------------------------------------------
# Чистая логика: WAV-заголовок (общий для слуги и якорей)
# ---------------------------------------------------------------

def wav_duration_sec(wav_bytes: bytes) -> float:
    """Длительность WAV-байтов по заголовку (RIFF/PCM, mono 16-bit).
    Якори Ф123 слушают байты, не доверяя словам сервера."""
    if len(wav_bytes) < 44 or wav_bytes[:4] != b"RIFF" \
            or wav_bytes[8:12] != b"WAVE":
        return 0.0
    import struct
    rate = struct.unpack("<I", wav_bytes[24:28])[0]
    data_size = struct.unpack("<I", wav_bytes[40:44])[0]
    if rate <= 0:
        return 0.0
    return (data_size / 2) / rate      # 16-bit mono: 2 байта на сэмпл


# ---------------------------------------------------------------
# Клиент слуги: живость, здоровье, подъём, синтез
# ---------------------------------------------------------------

def alive() -> bool:
    """Жив ли слуга: любой HTTP-ответ с порта — жив (закон эмбеддера:
    нам достаточно, что порт служит)."""
    import requests
    try:
        requests.get(config.THROAT_URL + "/health", timeout=2)
        return True
    except Exception:
        return False


def health() -> Optional[dict]:
    """Ответ /health — модель, спикеры, число фраз. Спит — None."""
    import requests
    try:
        r = requests.get(config.THROAT_URL + "/health", timeout=3)
        if r.status_code == 200:
            data = r.json()
            return data if isinstance(data, dict) else None
    except Exception:
        pass
    return None


def find_model() -> Optional[Path]:
    """Модель горла в чулане: сначала законный путь (models/voice/),
    потом glob — имя могли поменять при переносе посылки."""
    main = Path(config.THROAT_MODEL_FILE)
    if main.is_file():
        return main
    voice_dir = main.parent
    if voice_dir.is_dir():
        for pat in ("*v5*ru*.pt", "*.pt"):
            cands = sorted(voice_dir.glob(pat))
            if cands:
                return cands[0]
    return None


def torch_present() -> bool:
    """Есть ли torch в теле (не в слуге). ImportError — не крах органа:
    цепь честно уйдёт в SAPI, а проверка подскажет посылку."""
    try:
        import torch  # noqa: F401
        return True
    except ImportError:
        return False


def ensure_server(wait_secs: Optional[float] = None) -> tuple:
    """Поднять слугу-горло: (жив, честная сводка). Образец — эмбеддер:
    слуга ПО ВЫЗОВУ, орган зовёт его кнопкой (95) или «проверь голос»,
    но не из каждого «скажи вслух» (спавн из рефлекса — сюрприз, а
    не сервис). Проверки ДО спавна: torch и модель — иначе честный
    отказ с путём лечения, а не консоль с трейсбеком."""
    if alive():
        return True, "слуга-горло уже на порту %d" % config.PORT_THROAT
    if not torch_present():
        return False, ("torch не установлен — посылка docs\\ТЗ_Голос_v2.md "
                       "раздел 7 (wheels + модель, кнопка 95, выбор 4)")
    model = find_model()
    if not model:
        return False, ("не нашла модель горла (%s) — положи посылку: "
                       "docs\\ТЗ_Голос_v2.md, раздел 7"
                       % config.THROAT_MODEL_FILE)
    script = Path(config.HOME_DIR) / "sensors" / "throat.py"
    if not script.is_file():
        return False, "не нашла sensors/throat.py — скажи архитектору"
    cmd = '"%s" "%s" --service' % (sys.executable, script)
    subprocess.Popen(cmd, shell=True, cwd=str(config.HOME_DIR),
                     creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0))
    deadline = time.time() + (wait_secs if wait_secs is not None
                              else config.THROAT_START_WAIT_SECS)
    while time.time() < deadline:
        if alive():
            return True, ("слуга-горло поднялся на порту %d (CPU, %d "
                          "потоков — VRAM не трогаем)"
                          % (config.PORT_THROAT, config.THROAT_THREADS))
        time.sleep(2.0)
    return False, ("слуга не ожил за %d с — посмотри его консоль "
                   "(модель не легла? torch не тот?)"
                   % config.THROAT_START_WAIT_SECS)


def lay_to_rest() -> str:
    """Уложить слугу (кнопка 95, выбор 3): голос — по вызову, семантика
    слуги. VRAM он не держит, но полгигабайта RAM и 4 потока — тоже
    ресурс дома."""
    try:
        import psutil
    except ImportError:
        return ("psutil не установлен — уложи консоль слуги вручную "
                "(закрой окно горла)")
    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            cmd = " ".join(proc.info.get("cmdline") or [])
            if "throat.py" in cmd and "--service" in cmd:
                proc.terminate()
                return ("слуга-горло уложен — порт %d свободен"
                        % config.PORT_THROAT)
        except Exception:
            continue
    if not alive():
        return "слуга и так спал — порт %d тих" % config.PORT_THROAT
    return "не смогла уложить слугу — закрой его консоль вручную"


def synthesize(text: str, speaker: str = DEFAULT_SPEAKER,
               rate: int = 0, volume: int = 100,
               timeout: Optional[float] = None) -> tuple:
    """Текст → (True, WAV-байты) или (False, честная причина).

    Слуга делает всё тяжёлое: нормализацию (Ф23), SSML-темп, громкость
    (масштаб сэмплов). Клиент верит байтам, но проверяет заголовок —
    пустышке от WAV-органа дом не рад (закон фактов)."""
    import requests
    text = str(text or "").strip()
    if not text:
        return False, "нечего говорить — текст пустой"
    payload = {"text": text, "speaker": str(speaker or DEFAULT_SPEAKER),
               "rate": int(rate), "volume": int(volume)}
    try:
        r = requests.post(config.THROAT_URL + "/say", json=payload,
                          timeout=timeout or config.THROAT_TIMEOUT_SEC)
    except Exception as e:
        return False, "горло не ответило: %s" % e
    if r.status_code != 200:
        why = ""
        try:
            why = str((r.json() or {}).get("error") or "")[:200]
        except Exception:
            why = r.text[:200]
        return False, "горло отказало: %s" % why
    data = r.content or b""
    if wav_duration_sec(data) <= 0:
        return False, "горло вернуло пустой звук — скажи архитектору"
    return True, data
