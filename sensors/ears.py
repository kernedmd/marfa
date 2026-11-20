# -*- coding: utf-8 -*-
r"""sensors/ears.py — Г-уши, Этап 1: СТОРОЖ ИМЕНИ (vosk small, всегда на CPU).

Двухступенчатая схема ушей (доктрина «хозяина ресурса», MASTER_TZ 4):
  ступень 1 — ЭТОТ файл: vosk-model-small-ru (45 МБ, ~1% CPU, ~300 МБ RAM)
    слушает микрофон ВЕЧНО и ловит только слово «Марфа» (и его фонетические
    вариации: «марва», «марфу» — оглушения живой речи);
  ступень 2 — whisper-turbo (тяжёлый): включается на секунды ПОСЛЕ того,
    как сторож услышал имя, и расшифровывает уже саму фразу.

Так устроены коммерческие ассистенты: дешёвый детектор 24/7 + точный
мозг по требованию. Держать большой vosk (1.8 ГБ, гигабайты RAM) ради
одного слова — греть комнату рядом с 30B-мозгом (план RAM 44 ГБ, Ф97).

Логика пробуждения — чистые функции (normalize, levenshtein,
heard_wake): тестируются без модели и без микрофона. NameSentinel —
обёртка над vosk; демо-режим --demo требует sounddevice (микрофон).

Запуск на Z440:
  C:\Marfa\venv\Scripts\python.exe -m pip install sounddevice
  C:\Marfa\venv\Scripts\python.exe sensors\ears.py --check    # без микрофона
  C:\Marfa\venv\Scripts\python.exe sensors\ears.py --demo 60  # позови Марфу
"""
from __future__ import annotations

import datetime as dt
import json
import re
import sys
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import config  # noqa: E402

_PUNCT = re.compile(r"[^\wа-яёА-ЯЁ]+", re.UNICODE)


def normalize(text: str) -> str:
    """Приводим услышанное к канону: нижний регистр, ё→е, без пунктуации."""
    return _PUNCT.sub(" ", (text or "").lower().replace("ё", "е")).strip()


def levenshtein(a: str, b: str) -> int:
    """Расстояние Левенштейна — одна опечатка/оглушение = 1."""
    if a == b:
        return 0
    if not a or not b:
        return max(len(a), len(b))
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1,        # удаление
                           cur[j - 1] + 1,     # вставка
                           prev[j - 1] + (ca != cb)))  # замена
        prev = cur
    return prev[-1]


def heard_wake(text: str,
               words: tuple[str, ...] = config.EARS_WAKE_WORDS,
               max_dist: int = config.EARS_WAKE_MAX_DIST) -> Optional[str]:
    """Есть ли в фразе слово-триггер? Возвращает ТОКЕН, который сработал.

    Допуск max_dist=1: «марва», «марфу» (оглушения живой речи) — это Марфу
    зовут. «март», «форма» (дистанция 2+) — мимо. «марка» (дистанция 1)
    сработает ложноположительно — осознанный компромисс сторожа: лишний
    запуск whisper на 3 секунды дешевле, чем проспать зов Создателя.
    """
    for token in normalize(text).split():
        for wake in words:
            if levenshtein(token, wake) <= max_dist:
                return token
    return None


class NameSentinel:
    """Сторож имени: кормим звуком чанками, получаем события.

    feed(chunk) -> {"event": wake|speech|silence, "text": ..., "word": ...}
      chunk — bytes PCM int16 моно 16 кГц (родной формат vosk).
      wake — услышано имя (в финале ИЛИ в промежуточном результате:
      реакция не ждёт конца фразы).
    """

    def __init__(self, model_dir: Optional[Path] = None,
                 sample_rate: int = config.EARS_SAMPLE_RATE,
                 wake_words: tuple[str, ...] = config.EARS_WAKE_WORDS,
                 max_dist: int = config.EARS_WAKE_MAX_DIST) -> None:
        import vosk  # лениво: тесты логики живут без модели

        self.model_dir = Path(model_dir or config.EARS_MODEL_DIR)
        if not self.model_dir.is_dir():
            raise FileNotFoundError(
                "модель ушей не найдена: %s (скачай vosk-model-small-ru-0.22 "
                "с alphacephei.com/vosk/models в C:\\Marfa\\models\\)" % self.model_dir)
        self.sample_rate = sample_rate
        self.wake_words = wake_words
        self.max_dist = max_dist
        self._vosk = vosk
        self.model = vosk.Model(str(self.model_dir))
        self.rec = vosk.KaldiRecognizer(self.model, sample_rate)
        self.rec.SetWords(True)
        self.log_file = Path(config.EARS_LOG_FILE)
        self.last_event = "silence"

    # -- основной поток: PCM-чанки с микрофона -----------------------------
    def feed(self, chunk: bytes) -> dict:
        final = self.rec.AcceptWaveform(chunk)
        text = ""
        if final:
            text = json.loads(self.rec.Result()).get("text", "")
        else:
            text = json.loads(self.rec.PartialResult()).get("partial", "")
        return self._classify(text)

    def finish(self) -> dict:
        """Дослушать хвост потока при остановке."""
        return self._classify(json.loads(self.rec.FinalResult()).get("text", ""))

    # -- внутреннее ---------------------------------------------------------
    def _classify(self, text: str) -> dict:
        word = heard_wake(text, self.wake_words, self.max_dist)
        if word:
            event = "wake"
        elif text.strip():
            event = "speech"
        else:
            event = "silence"
        self.last_event = event
        if event != "silence":
            self._log(event, text, word)
        return {"event": event, "text": text, "word": word}

    def _log(self, event: str, text: str, word: Optional[str]) -> None:
        rec = {"ts": dt.datetime.now().isoformat(timespec="seconds"),
               "sensor": "ears", "event": event, "text": text}
        if word:
            rec["word"] = word
        try:
            self.log_file.parent.mkdir(parents=True, exist_ok=True)
            with self.log_file.open("a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        except OSError:
            pass  # лог не должен рвать слух


def check(model_dir: Optional[Path] = None) -> str:
    """Проверка ушей без микрофона: модель грузится, тишина распознаётся."""
    s = NameSentinel(model_dir)
    out = s.feed(b"\x00" * s.sample_rate * 2)  # 1 сек тишины
    return ("модель жива: %s, тишина -> event=%s (должно быть silence)"
            % (s.model_dir.name, out["event"]))


def demo(seconds: float = 60.0) -> None:
    """Живое демо на Z440: слушает микрофон, печатает всё услышанное.

    Позови Марфу вслух — увидишь строку [ИМЯ!] ... и слово, которое
    сработало. Выход: Ctrl+C или по таймауту.
    """
    import sounddevice  # ставится отдельно: pip install sounddevice

    s = NameSentinel()
    print("=" * 60)
    print("МАРФА — уши, демо сторожа имени (%.0f сек)" % seconds)
    print("Модель: %s · %d Гц · слушаю..." % (s.model_dir.name, s.sample_rate))
    print("Позови: «Марфа, ...» — выход Ctrl+C")
    print("=" * 60)

    def callback(indata, frames, time_info, status):
        out = s.feed(bytes(indata))
        if out["event"] == "wake":
            print("[%s] [ИМЯ!] услышал: «%s» (сработало: %s)"
                  % (dt.datetime.now().strftime("%H:%M:%S"), out["text"], out["word"]))
        elif out["event"] == "speech":
            print("[%s]         речь:   «%s»"
                  % (dt.datetime.now().strftime("%H:%M:%S"), out["text"]))

    with sounddevice.RawInputStream(samplerate=s.sample_rate, blocksize=4000,
                                    dtype="int16", channels=1, callback=callback):
        import time
        try:
            time.sleep(seconds)
        except KeyboardInterrupt:
            pass
    print("Демо закончено. Лог: %s" % config.EARS_LOG_FILE)


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else ""
    if arg == "--check":
        print(check(Path(sys.argv[2]) if len(sys.argv) > 2 else None))
    elif arg == "--demo":
        demo(float(sys.argv[2]) if len(sys.argv) > 2 else 60.0)
    else:
        print(__doc__)
