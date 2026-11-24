# -*- coding: utf-8 -*-
r"""sensors/throat.py — Ф121 «СЛУГА-ГЛОТО»: Silero v5_6_ru синтезирует
речь дома на порту 8084 (круг 23, день-14; ТЗ docs\ТЗ_Голос_v2.md).

ДОКТРИНА СЛУГИ. Горло — СЛУГА ПО ВЫЗОВУ по образцу эмбеддера (8087) и
whisper-моста (8086): поднимает кнопка 95 (или «проверь голос» — орган
скажет, что слуга спит и как разбудить). Живёт на CPU (torch.package,
4 потока): VRAM принадлежит глазам, принцип хозяина ресурса. RAM
~0,5-1 ГБ — план 44/64 ГБ даже не заметит.

ГЛОТКА ОТДЕЛЕНА ОТ РТА: слуга СИНТЕЗИРУЕТ и отдаёт WAV-байты (HTTP),
рот (winsound в теле дома) играет их у Создателя. Поэтому орган
кроссплатформенен: в песочнице архитектора (Linux) он отдаёт те же
байты, что на станции (Windows) — первый ЖИВОЙ ЯКОРЬ органа (Ф123):
torch.package не знает, где живёт.

ИНТОНАЦИЯ ЧЕСТНА: модель v5_6 читает «?» и «!» сама (проверено на слух
Создателем: «восклицание — норм»); дискретных эмоций орган не имеет
(type_str/intensity молча игнорируются — живая проверка круга 23) —
краски речи: пунктуация + SSML prosody (темп «говори быстрее/медленнее»).

ЗАКОН ЛЕНИВОГО TORCH: import torch живёт ВНУТРИ загрузки модели —
модуль импортируется без torch (панель и якоря не падают, пока посылка
не приехала; «сухой режим» честен с пути лечения).

API (localhost only):
  GET /health → {"ok":true,"sensor":"throat","model":…,"speakers":[…],
                 "threads":…,"sample_rate":…,"synths":N}
  POST /say {"text":…,"speaker":"baya","rate":-5..5,"volume":0..100}
       → 200 audio/wav (заголовки X-Marfa-Duration, X-Marfa-RTF)
       → 4xx/5xx {"error":"честная причина по-русски"}

Запуск на Z440 (и в песочнице архитектора — орган кроссплатформенный):
  venv\Scripts\python.exe sensors\throat.py --check         # осмотр
  venv\Scripts\python.exe sensors\throat.py --demo          # проба в WAV
  venv\Scripts\python.exe sensors\throat.py --service       # служба на 8084
"""
from __future__ import annotations

import io
import json
import sys
import time
import wave
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import config  # noqa: E402
from core import throat as _logic  # noqa: E402  один источник логики

# ---------------------------------------------------------------
# Состояние слуги
# ---------------------------------------------------------------
_model = None          # загружается один раз — модель в RAM, не в цикле
_synths = 0            # сколько фраз сказано с подъёма


def _write_status(state: str, error: str = "", **extra) -> None:
    """Сердцебиение: data\throat_status.json — панель и «статус» видят
    горло, как видят уши (ears_status.json). Ошибка записи не рвёт
    голос (закон эфира)."""
    rec = {"ts": time.strftime("%Y-%m-%d %H:%M:%S"),
           "sensor": "throat", "state": state,
           "port": config.PORT_THROAT}
    if error:
        rec["error"] = error[:300]
    rec.update(extra)
    try:
        Path(config.THROAT_STATUS_FILE).parent.mkdir(parents=True,
                                                     exist_ok=True)
        Path(config.THROAT_STATUS_FILE).write_text(
            json.dumps(rec, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


def find_model() -> Path:
    """Модель слуги: законный путь + glob-запас. Нет — честный отказ
    с путём лечения (посылка), не молчаливый падеж по-английски."""
    p = _logic.find_model()
    if p:
        return p
    raise SystemExit("Не нашла модель горла: %s\n"
                     "Положи посылку — docs\\ТЗ_Голос_v2.md, раздел 7:\n"
                     "  models\\voice\\v5_6_ru.pt (147 664 410 байт,\n"
                     "  sha256 04cc9b1d…cbf50b2e)"
                     % config.THROAT_MODEL_FILE)


def load_model():
    """Загрузить torch.package (2-3 с, ~0,5 ГБ RAM). torch отсутствует —
    честный текст посылки, не трейсбек."""
    global _model
    if _model is not None:
        return _model
    try:
        import torch
    except ImportError:
        raise SystemExit(
            "torch не установлен — посылка docs\\ТЗ_Голос_v2.md раздел 7:\n"
            "  кнопка scripts\\95_Горло.bat, выбор [4] (wheels из "
            "incoming\\wheels)\n"
            "  до посылки голос дома — SAPI (запасной рот), цепь честна")
    torch.set_num_threads(config.THROAT_THREADS)
    path = find_model()
    model = torch.package.PackageImporter(str(path)).load_pickle(
        "tts_models", "model")
    model.to(torch.device("cpu"))
    _model = model
    return model


# ---------------------------------------------------------------
# Синтез: нормализация (Ф23) → SSML-темп → WAV-байты
# ---------------------------------------------------------------

def pcm_to_wav(samples, sample_rate: int) -> bytes:
    """float-сэмплы (−1..1) → WAV-байты (mono, 16-bit). Чистая функция:
    якоря Ф123 собирают WAV ей же — не дублируем закон."""
    import numpy as np
    buf = io.BytesIO()
    clipped = np.clip(samples, -1.0, 1.0)
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes((clipped * 32767).astype("<i2").tobytes())
    return buf.getvalue()


def synth(text: str, speaker: str, rate: int = 0, volume: int = 100) -> tuple:
    """Одна фраза → (True, wav-байты, длительность, rtf) или
    (False, честная причина, 0, 0). Любой крах ловится — слуга не
    умирает от одной фразы (закон эфира и для глотки)."""
    model = load_model()
    clean = _logic.normalize_text(text)
    if not clean:
        return False, "текст пуст — нечего говорить", 0.0, 0.0
    if speaker not in _logic.SPEAKERS:
        return False, ("не знаю голоса «%s» — есть: %s"
                       % (speaker, ", ".join(_logic.SPEAKERS))), 0.0, 0.0
    ssml = _logic.build_ssml(clean, rate)
    t0 = time.perf_counter()
    try:
        if ssml:
            audio = model.apply_tts(ssml_text=ssml, speaker=speaker,
                                    sample_rate=config.THROAT_SAMPLE_RATE)
        else:
            audio = model.apply_tts(text=clean, speaker=speaker,
                                    sample_rate=config.THROAT_SAMPLE_RATE,
                                    put_accent=True, put_yo=True)
    except Exception as e:
        return False, "горло подавилось: %s: %s" % (type(e).__name__, e), \
            0.0, 0.0
    wall = time.perf_counter() - t0
    dur = float(len(audio)) / config.THROAT_SAMPLE_RATE
    if dur <= 0:
        return False, "модель вернула тишину — скажи архитектору", 0.0, 0.0
    gain = max(0, min(100, int(volume))) / 100.0
    samples = audio.numpy() * gain
    return True, pcm_to_wav(samples, config.THROAT_SAMPLE_RATE), dur, \
        (wall / dur if dur else 0.0)


# ---------------------------------------------------------------
# HTTP-слуга: однопоточный — синтез CPU-тяжёлый, вторая фраза
# подождёт первой (закон одного голоса и на сервере)
# ---------------------------------------------------------------

class _Handler(BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):      # консоль слуги — по-русски
        sys.stdout.write("[горло] %s\n" % (fmt % args))
        sys.stdout.flush()

    def _json(self, code: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):                        # /health — живость
        if self.path != "/health":
            self._json(404, {"error": "горло знает только /health и /say"})
            return
        model = find_model()
        self._json(200, {
            "ok": True, "sensor": "throat", "model": model.name,
            "speakers": list(_logic.SPEAKERS), "threads":
                config.THROAT_THREADS,
            "sample_rate": config.THROAT_SAMPLE_RATE, "synths": _synths,
        })

    def do_POST(self):                       # /say — синтез
        global _synths
        if self.path != "/say":
            self._json(404, {"error": "горло знает только /health и /say"})
            return
        try:
            size = int(self.headers.get("Content-Length") or 0)
            req = json.loads(self.rfile.read(size).decode("utf-8"))
        except Exception as e:
            self._json(400, {"error": "не поняла запрос: %s" % e})
            return
        text = str(req.get("text") or "")
        speaker = str(req.get("speaker") or _logic.DEFAULT_SPEAKER)
        rate = int(req.get("rate") or 0)
        volume = int(req.get("volume") if req.get("volume") is not None
                     else 100)
        if len(text) > 4000:
            self._json(400, {"error": "вслух — не больше 4000 символов "
                                      "за раз, а тут %d" % len(text)})
            return
        ok, data, dur, rtf = synth(text, speaker, rate, volume)
        if not ok:
            self._json(400, {"error": data})
            return
        _synths += 1
        _write_status("жив", speaker=speaker,
                      last_duration=round(dur, 2),
                      last_rtf=round(rtf, 3), synths=_synths)
        self.send_response(200)
        self.send_header("Content-Type", "audio/wav")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("X-Marfa-Duration", "%.2f" % dur)
        self.send_header("X-Marfa-RTF", "%.3f" % rtf)
        self.end_headers()
        self.wfile.write(data)


def serve() -> None:
    """Вечная служба на 8084. Модель грузится ДО первого запроса —
    «скажи вслух» не ждёт горло, горло уже готово."""
    load_model()                      # упадёт честно (SystemExit с путём)
    _write_status("жив", model=find_model().name,
                  threads=config.THROAT_THREADS)
    srv = HTTPServer(("127.0.0.1", config.PORT_THROAT), _Handler)
    print("[горло] слуга-горло на порту %d (CPU, %d потоков, %d Гц); "
          "уйти — закрыть окно"
          % (config.PORT_THROAT, config.THROAT_THREADS,
             config.THROAT_SAMPLE_RATE))
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        _write_status("уложен")
        srv.server_close()


# ---------------------------------------------------------------
# Режимы кнопки и консоли
# ---------------------------------------------------------------

def check() -> None:
    """--check: осмотр горла без подъёма службы (честно, по-русски)."""
    print("ОСМОТР ГОРЛА (Ф121, слуга на %d):" % config.PORT_THROAT)
    print("  · python: %s" % sys.version.split()[0])
    ok = _logic.torch_present()
    import importlib
    ver = ""
    if ok:
        ver = " " + importlib.import_module("torch").__version__
    print("  · torch: %s%s" % ("есть" if ok else "НЕТ — посылка "
                               "(ТЗ_Голос_v2, раздел 7)", ver))
    model = _logic.find_model()
    if model:
        size = model.stat().st_size
        print("  · модель: %s (%d байт)" % (model, size))
        if size != 147_664_410:
            print("    внимание: ожидается 147 664 410 байт (v5_6_ru) — "
                  "файл другого размера, проверь посылку")
    else:
        print("  · модель: НЕ НАЙДЕНА — %s" % config.THROAT_MODEL_FILE)
    if _logic.alive():
        h = _logic.health() or {}
        print("  · слуга: ЖИВ (модель %s, фраз сказано: %s)"
              % (h.get("model"), h.get("synths")))
    else:
        print("  · слуга: спит — поднимет кнопка 95 (выбор 2) или "
              "«проверь голос»")
    print("  · голоса: %s" % _logic.speakers_line())
    print("  · цепь: silero → SAPI → честный отказ (день-14)")


def demo(phrase: str, out: str = "") -> None:
    """--demo: одна фраза в WAV-файл — орган доказывает работу байтами
    (в песочнице архитектора — живой якорь, на станции — проба уха)."""
    t0 = time.perf_counter()
    ok, data, dur, rtf = synth(phrase, _logic.DEFAULT_SPEAKER)
    if not ok:
        print("ОТКАЗ: %s" % data)
        return
    load_s = time.perf_counter() - t0 - (dur * rtf)
    out = out or str(Path(config.DATA_DIR) / "throat_demo.wav")
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_bytes(data)
    print("СКАЗАЛА: %d символов → %s" % (len(phrase), out))
    print("звук %.2f с | синтез %.3f с | RTF %.3f | загрузка ~%.1f с"
          % (dur, dur * rtf, rtf, max(0.0, load_s)))


def main() -> None:
    args = sys.argv[1:]
    if not args or args[0] == "--check":
        check()
    elif args[0] == "--service":
        serve()
    elif args[0] == "--demo":
        phrase = args[1] if len(args) > 1 else \
            "Привет, Илья. Это Марфа. Я нашла себе новый голос, тёплый и живой."
        demo(phrase, args[2] if len(args) > 2 else "")
    else:
        print("режимы: --check | --demo [фраза] [файл.wav] | --service")


if __name__ == "__main__":
    main()
