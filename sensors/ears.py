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
  C:\Marfa\venv\Scripts\python.exe sensors\ears.py --service  # вечная служба (автозапуск)
Лечится кнопкой scripts\85_fix_ears.bat (модель легла криво —
вложенная распаковка архива с сайта).
"""
from __future__ import annotations

import datetime as dt
import json
import re
import sys
import time
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import config, loghygiene  # noqa: E402

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


def model_files_ok(model_dir) -> bool:
    """Есть ли в папке НАСТОЯЩИЕ файлы vosk-модели.

    Маркер — am/final.mdl (акустическая модель): он есть и в small,
    и в больших моделях alphacephei. Папка без него — не модель,
    а след неудачной распаковки. vosk про такую папку молчит
    по-английски («Failed to create a model») — проверяем сами,
    до него, и говорим по-русски.
    """
    return (Path(model_dir) / "am" / "final.mdl").is_file()


def _write_status(state: str, error: str = "",
                 last_wake: str = "", device: str = "") -> None:
    r"""Сердцебиение службы ушей: data\ears_status.json.

    Панель и старт дома смотрят сюда: живо ли ухо, что оно слышало
    последним и КАКИМ устройством слушает (v2, 22.11: микрофон
    веб-камеры нашёлся — Создатель должен это видеть). Ошибки записи
    (диск/права) — не повод рвать слух.
    """
    rec = {"ts": dt.datetime.now().isoformat(timespec="seconds"),
           "sensor": "ears", "state": state}
    if error:
        rec["error"] = error[:300]
    if last_wake:
        rec["last_wake"] = last_wake
    if device:
        rec["device"] = device[:120]
    try:
        Path(config.EARS_STATUS_FILE).parent.mkdir(parents=True, exist_ok=True)
        Path(config.EARS_STATUS_FILE).write_text(
            json.dumps(rec, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


# ---------------------------------------------------------------
# v2 (22.11, урок Создателя): веб-камера с микрофоном подключена —
# но её микрофон часто НЕ выбран устройством по умолчанию, и старая
# служба честно писала «no_mic», хотя микрофон в доме ЕСТЬ. Теперь
# служба сама перебирает все входные устройства и берёт первое,
# которое открылось. Логика — чистые функции: тестируются без железа.
# ---------------------------------------------------------------

def _input_devices(sd) -> list:
    """Все входные устройства: [(индекс или None для «по умолчанию», имя)].

    None идёт ПЕРВЫМ — сначала пробуем устройство по умолчанию, потом
    каждый вход: микрофон веб-камеры часто не «дефолт», но он есть.
    """
    devs = []
    try:
        d = sd.query_devices(kind="input")
        devs.append((None, str(d.get("name", "по умолчанию"))))
    except Exception:
        pass
    try:
        for i, d in enumerate(sd.query_devices()):
            if int(d.get("max_input_channels", 0) or 0) > 0:
                devs.append((i, str(d.get("name", "?"))))
    except Exception:
        pass
    return devs


def _open_ear_stream(sd, samplerate: int, callback):
    """Открыть микрофон: сначала «по умолчанию», потом каждый вход.

    Возвращает (поток, имя устройства). Ни одно не открылось —
    исключение со списком попыток: служба напишет его в статус,
    и Создатель увидит, ЧТО видит Windows вместо микрофона.
    """
    errors = []
    for idx, name in _input_devices(sd):
        kw = {"samplerate": samplerate, "blocksize": 4000,
              "dtype": "int16", "channels": 1, "callback": callback}
        if idx is not None:
            kw["device"] = idx
        try:
            return sd.RawInputStream(**kw), name
        except Exception as e:
            errors.append("%s: %s" % (name, e))
    raise RuntimeError("ни один микрофон не открылся (пробовал: %s)"
                       % "; ".join(errors[:3] or ["устройств не найдено"]))


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
        self.model_dir = Path(model_dir or config.EARS_MODEL_DIR)
        if not self.model_dir.is_dir():
            raise FileNotFoundError(
                "модель ушей не найдена: %s (скачай vosk-model-small-ru-0.22 "
                "с alphacephei.com/vosk/models в C:\\Marfa\\models\\)" % self.model_dir)
        if not model_files_ok(self.model_dir):
            # Урок первого живого прогона на Z440 (20.11.2026): папка была,
            # а модели в ней не было — vosk ответил голым английским
            # «Folder does not contain model files». Говорим точно.
            nested = self.model_dir / self.model_dir.name
            if model_files_ok(nested):
                raise FileNotFoundError(
                    "модель ушей лежит ВЛОЖЕННО: сторож смотрит в %s, а файлы "
                    "модели нашлись в %s (классика «Извлечь всё» в Проводнике: "
                    "внутри архива ещё одна папка с тем же именем). Подними "
                    "содержимое вложенной папки на уровень выше или нажми "
                    "scripts\\85_fix_ears.bat — она чинит сама"
                    % (self.model_dir, nested))
            raise FileNotFoundError(
                "папка модели ушей есть, а ФАЙЛОВ модели в ней нет: %s (ждал "
                "am\\final.mdl и соседей conf, graph, ivector). Похоже, архив "
                "не распакован или распакован не туда. Нажми "
                "scripts\\85_fix_ears.bat — она чинит сама" % self.model_dir)
        import vosk  # лениво: тесты логики живут без модели

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
            # Ф96 (круг 17): копилка слуха — через дверь ротации, как все
            loghygiene.append_line(self.log_file,
                                    json.dumps(rec, ensure_ascii=False) + "\n")
        except OSError:
            pass  # лог не должен рвать слух


def check(model_dir: Optional[Path] = None) -> str:
    """Проверка ушей без микрофона: модель грузится, тишина распознаётся."""
    s = NameSentinel(model_dir)
    out = s.feed(b"\x00" * s.sample_rate * 2)  # 1 сек тишины
    return ("модель жива: %s, тишина -> event=%s (должно быть silence)"
            % (s.model_dir.name, out["event"]))


def selftest() -> str:
    r"""«проверь уши» — живой осмотр слуха ПО СТУПЕНЯМ, ничего не запуская.

    Урок живого лога 23.11: Марфа повторяла «не могу слышать голос», а
    ЧТО чинить — не называла (и на «проверь микрофон» уходила в общие
    слова). Осмотр называет ступень поломки и ТОЧНОЕ лечение:
      1) СЛУЖБА — сердце data\ears_status.json свежее? Диагноз из статуса
         (no_mic / no_model / no_sounddevice / висит), не выдумка;
      2) МОДЕЛЬ — файлы vosk на месте? (быстрая проверка по маркеру
         am/final.mdl, без загрузки; вложенная распаковка — по имени);
      3) ЗВУК — sounddevice видит входные устройства? (нет обёртки —
         команда установки в venv, не в системный Python).
    Исключений не поднимает: каждая ступень честна отдельно.
    """
    lines = ["ПРОВЕРКА УШЕЙ (вживую, не по памяти):"]

    # --- 1. служба ---
    from core import identity   # config-only, цикла нет
    diag = identity.ears_diagnosis()
    service_alive = diag.startswith("живы")
    lines.append("- служба слуха: " + diag)

    # --- 2. модель ---
    model_dir = Path(config.EARS_MODEL_DIR)
    if model_files_ok(model_dir):
        lines.append("- модель ушей: на месте (%s)" % model_dir.name)
    elif model_files_ok(model_dir / model_dir.name):
        lines.append("- модель ушей: ВЛОЖЕННАЯ распаковка — кнопка 85 "
                     "(scripts\\85_fix_ears.bat) поднимет файлы на уровень")
    else:
        lines.append("- модель ушей: НЕТ — кнопка 85 (scripts\\85_fix_ears.bat) "
                     "скачает и положит сама")

    # --- 3. звук ---
    try:
        import sounddevice as sd  # noqa: F401 — наличие обёртки
        devs = _input_devices(sd)
        if devs:
            names = "; ".join(n for _, n in devs[:4])
            lines.append("- микрофоны видит Windows: " + names)
        else:
            lines.append("- микрофонов НЕТ: воткни или включи микрофон "
                         "(у веб-камеры свой); Параметры → Система → Звук → Вход")
    except ImportError:
        lines.append("- обёртки звука нет: venv\\Scripts\\python.exe -m pip "
                     "install sounddevice (голый pip ставит мимо дома)")
    except Exception as e:
        lines.append("- звук не выяснить: %s" % e)

    # --- итог: лечение по слабейшей ступени ---
    if service_alive:
        lines.append("УШИ СЛЫШАТ — позови «Марфа» вслух, сторож имени "
                     "должен отозваться в консоли службы.")
    else:
        lines.append("ЧТО ДЕЛАТЬ: поднять службу — Старт_Марфа.bat (пятый "
                     "слуга, поднимается сам) или кнопка 89 "
                     "(scripts\\89_live_voice.bat); если строки выше ругаются "
                     "на модель или звук — сначала они.")
    return "\n".join(lines)


# ---------------------------------------------------------------
# v3 (27.11, круг 29 «УШИ НЕ ВРУТ», Ф176–Ф177): слух отвечает
# ПРАВДОЙ и умеет слушать ПО СЛОВУ. Живой лог дня-16: «Да, ты уже
# все же найчилсь слышать микрофон?» — «Да, я слышу микрофон.
# Проверила — всё работает» — ВЫДУМКА (никакой проверки не было);
# «Слушай микрофон 15 секунд» — «неизвестный инструмент: listen»
# (мозг выдумал инструмент, дом не умел слушать по слову).
# ---------------------------------------------------------------

def _status_record() -> Optional[dict]:
    """Живая запись статуса службы ушей (data\\ears_status.json) или None.

    Путь читается ЛЕНИВО (закон песочницы conftest): тесты патчат
    config.EARS_STATUS_FILE поверх автопесочницы — орган следует за
    патчем, а не за значением на импорте.
    """
    try:
        raw = json.loads(Path(config.EARS_STATUS_FILE).read_text(
            encoding="utf-8"))
        return raw if isinstance(raw, dict) else None
    except (OSError, ValueError):
        return None


def _heart_age(rec: dict) -> Optional[float]:
    """Сколько секунд назад билось сердце службы (None — не разобрать)."""
    try:
        ts = dt.datetime.fromisoformat(str(rec.get("ts", "")))
        return (dt.datetime.now() - ts).total_seconds()
    except ValueError:
        return None


def _service_alive(rec: Optional[dict]) -> bool:
    """Живо ли ухо СЕЙЧАС: статус ok И сердце свежее (допуск 90 с,
    -300 с — перевод часов). Больше никакой «веры» — только факты."""
    if rec is None:
        return False
    age = _heart_age(rec)
    return (str(rec.get("state", "")) == "ok"
            and age is not None and -300.0 <= age <= 90.0)


def hearing_answer() -> str:
    r"""Ф176 «УШИ НЕ ВРУТ»: честный ответ о СЛУХЕ — из живого сердца
    службы ушей, не из фантазии мозга.

    Вопрос «ты меня слышишь?» — вопрос о ФАКТЕ, и отвечает орган из
    первых рук: статус службы ушей (data\ears_status.json) — живое
    сердце, причина, устройство. Уши (вход) и горло (выход) названы
    РАЗНЫМИ органами: живой лог отвечал на вопрос о слухе отговоркой
    про голос. Никаких «проверила — всё работает» без проверки (R11).
    """
    rec = _status_record()
    if rec is None:
        return ("Не знаю, слышу ли: служба ушей не пишет сердцебиение "
                "(data\\ears_status.json нет) — она не запущена. Поднять: "
                "Старт_Марфа.bat (пятый слуга) или «проверь уши» — осмотр "
                "по ступеням. Это про УШИ (вход); голос — отдельный орган.")
    age = _heart_age(rec)
    state = str(rec.get("state", ""))
    dev = str(rec.get("device", ""))
    if _service_alive(rec):
        tail = " (микрофон: %s)" % dev if dev else ""
        return ("Да, слышу — проверила по живому сердцу службы ушей, не "
                "по памяти: сторож имени слушает%s и слышит слово «Марфа». "
                "Говори «Марфа, …» вслух. Если я не отвечаю на голос — "
                "возможно, спит вторая ступень (whisper-мост): скажи "
                "«проверь мост»." % tail)
    if state == "ok":
        return ("Не могу сказать «слышу»: сердце службы замерло (%s с "
                "назад) — служба висит или умерла. Скажи «проверь уши» — "
                "осмотр по ступеням с лечением."
                % ("?" if age is None else int(age)))
    # no_mic / no_model / no_sounddevice / прочее — причина по имени
    reason = {
        "no_mic": "микрофон не найден или занят",
        "no_model": "модель ушей не найдена (кнопка 85_fix_ears)",
        "no_sounddevice": "не поставлен sounddevice (pip install sounddevice)",
    }.get(state, state or "неизвестное состояние")
    err = str(rec.get("error", ""))[:120]
    if err:
        reason += ": %s" % err
    return ("Нет, не слышу — %s. Проверила по живому статусу службы ушей, "
            "это не догадка. Лечение: «проверь уши» — осмотр по ступеням. "
            "Уши (вход) и горло (голос, выход) — разные органы: неслышащая "
            "Марфа всё равно может говорить." % reason)


def _heards_since(start: dt.datetime, limit: int = 8) -> list:
    """Расслышанное службой ушей С МОМЕНТА start: полные фразы, без
    обрывков и дублей.

    Сторож пишет в журнал и ПРОМЕЖУТОЧНЫЕ результаты (частичные
    распознавания растут приставкой: «при», «приве», «привет») —
    фрагмент, целиком лежащий в другой фразе окна, поглощается ею:
    Создатель читает фразы, а не их обрывки. Допуск -1 с: запись той
    же секунды, что и старт, — услышанная нашим окном.
    """
    try:
        raw = Path(config.EARS_LOG_FILE).read_text(encoding="utf-8")
    except OSError:
        return []
    texts: list = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if not isinstance(rec, dict) or rec.get("sensor") != "ears":
            continue
        text = str(rec.get("text", "")).strip()
        if not text:
            continue
        try:
            ts = dt.datetime.fromisoformat(str(rec.get("ts", "")))
        except ValueError:
            continue
        if ts >= start - dt.timedelta(seconds=1):
            texts.append(text)
    kept = []
    for t in texts:
        low = t.lower()
        # обрывок, лежащий внутри ДРУГОЙ фразы окна, — мусор сторожа
        if any(low != other.lower() and low in other.lower()
               for other in texts):
            continue
        kept.append(t)
    # УРОК ЖИВОГО ЛОГА (день-18, 28.11): считалка «раз два три четыре
    # пять…» пришла в отчёт ЧЕТЫРЬМЯ вариантами с разными хвостами
    # («стреляет их» → «стреляет паутиной» → «стреляет пиф паф» →
    # «выпей кайф…») — vosk не только наращивает фразу приставкой, он
    # ПЕРЕСМАТРИВАЕТ уже сказанное, и пересмотр подстрокой старой
    # версии не бывает, так что поглощение выше его не берёт. В 15
    # секундах не живут два полных повтора считалки — это пересмотры
    # ОДНОЙ фразы. Узнаём по общему началу (первые 5 слов): в группе
    # остаётся последняя — самая дораспознанная версия.
    heads: dict = {}
    for t in kept:
        sig = " ".join(t.lower().split()[:5])
        heads[sig] = t
    kept = list(heads.values())
    uniq: list = []
    for t in kept:                       # подряд-дубли — одно слово дважды
        if not uniq or uniq[-1].lower() != t.lower():
            uniq.append(t)
    return uniq[-limit:]


def listen(seconds: float = 10.0, sleep=time.sleep) -> str:
    r"""Ф177 «СЛУШАЙ МИКРОФОН <N СЕК>»: живое прослушивание БЕЗ второго
    микрофона.

    Служба ушей (сторож имени) слушает ВСЕГДА и пишет всё расслышанное
    в logs\ears_log.jsonl — второе ухо в тот же микрофон не открываем
    (делить устройство с самой собой — конфликт). Вместо этого ждём N
    секунд, пока слушает служба, потом честно читаем из журнала всё,
    что она расслышала за это окно. Тишина — тишина, выдумки нет.
    Ухо мертво — честный отказ (Ф176), не тишина вместо диагноза.
    Границы: 5–60 секунд (голая просьба — 10).
    """
    try:
        seconds = float(seconds)
    except (TypeError, ValueError):
        seconds = 10.0
    seconds = max(5.0, min(60.0, seconds))
    rec = _status_record()
    if not _service_alive(rec):
        return (hearing_answer()
                + " Пока ухо не живое — слушать нечего: сначала "
                  "лечение, потом «слушай микрофон» снова.")
    start = dt.datetime.now()
    sleep(seconds)
    heard = _heards_since(start)
    if not heard:
        return ("Слушала %d секунд — тишина: сторож имени ничего не "
                "расслышал. Говори громче и в микрофон; зов «Марфа» он "
                "слышит точно. Хочешь длинную фразу — скажи «Марфа, …»: "
                "whisper-мост (вторая ступень) расшифрует её целиком."
                % int(seconds))
    lines = ["Слушала %d секунд, вот что расслышало ухо-сторож (короткие "
             "фразы, слово в слово не гарантирую):" % int(seconds)]
    for t in heard:
        lines.append("  · «%s»" % t)
    return "\n".join(lines)


def demo(seconds: float = 60.0) -> None:
    """Живое демо на Z440: слушает микрофон, печатает всё услышанное.

    Позови Марфу вслух — увидишь строку [ИМЯ!] ... и слово, которое
    сработало. Выход: Ctrl+C или по таймауту.
    """
    try:
        import sounddevice  # ставится отдельно: pip install sounddevice
    except ImportError:
        # Урок первого демо на Z440 (20.11.2026): голый traceback
        # «No module named 'sounddevice'» — не наш стиль. Говорим,
        # ЧТО не хватает и КАК поставить, прямо в консоль.
        print("=" * 60)
        print("НЕ ХВАТАЕТ ОДНОЙ ДЕТАЛИ: sounddevice — обёртка микрофона.")
        print("Ставится одной командой (в venv Марфы):")
        print(r"  C:\Marfa\venv\Scripts\python.exe -m pip install sounddevice")
        print("Если pypi.org не отвечает — через зеркало tuna:")
        print(r"  C:\Marfa\venv\Scripts\python.exe -m pip install sounddevice"
              " -i https://pypi.tuna.tsinghua.edu.cn/simple")
        print("Потом запусти демо ещё раз.")
        raise SystemExit(1)

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

    try:
        stream, mic_name = _open_ear_stream(sounddevice, s.sample_rate,
                                            callback)
        with stream:
            print("Слушаю «%s»..." % mic_name)
            import time
            try:
                time.sleep(seconds)
            except KeyboardInterrupt:
                pass
    except Exception as e:
        # микрофона нет / занят / нет прав — PortAudio говорит технично,
        # а Создателю нужен человеческий ответ
        print("=" * 60)
        print("МИКРОФОН НЕ ПОДКЛЮЧЁН или занят: %s" % e)
        print("Проверь, что микрофон вставлен и выбран устройством ввода")
        print("по умолчанию: Параметры -> Система -> Звук -> Вход.")
        print("Служба ушей (--service) перебирает все входные устройства")
        print("сама — включая микрофон веб-камеры.")
        raise SystemExit(1)
    print("Демо закончено. Лог: %s" % config.EARS_LOG_FILE)


def serve(retry_secs: float = config.EARS_RETRY_SECS,
          heartbeat: float = 30.0) -> None:
    r"""СЛУЖБА УШЕЙ: вечный сторож имени для автозапуска дома.

    Отличие от демо: никогда не сдаётся.
      - микрофона нет / занят — пишет честный статус (нет микрофона),
        ждёт и пробует снова: воткнул микрофон — ухо проснулось само,
        дом перезапускать не надо;
      - v2 (22.11): устройство «по умолчанию» не открывается — служба
        перебирает ВСЕ входные устройства: микрофон веб-камеры часто
        не «дефолт», но он есть; нашла — пишет его имя в статус;
      - модели нет — то же самое (кнопка 85_fix_ears чинит параллельно);
      - sounddevice не поставлен — то же самое;
      - пока слушает — пишет сердцебиение в статус-файл: панель и
        «статус дома» видят живое ухо (data\ears_status.json).
    Выход — только Ctrl+C или смерть процесса. Лог всех событий —
    logs\ears_log.jsonl (правило 6.6).
    """
    print("=" * 60)
    print("МАРФА — служба ушей (сторож имени, вечный режим)")
    print("=" * 60)
    while True:
        # -- деталь за деталью: чего не хватает — честно в статус и ждём --
        try:
            import sounddevice
        except ImportError:
            print("[%s] sounddevice не поставлен — ставь: pip install sounddevice"
                  % dt.datetime.now().strftime("%H:%M:%S"))
            _write_status("no_sounddevice", error="pip install sounddevice")
            time.sleep(retry_secs)
            continue
        try:
            s = NameSentinel()
        except FileNotFoundError as e:
            # модель не найдена/лежит криво — кнопка 85_fix_ears чинит,
            # служба ждёт и подхватит, как только файлы встанут на место
            print("[%s] %s" % (dt.datetime.now().strftime("%H:%M:%S"), e))
            _write_status("no_model", error=str(e))
            time.sleep(retry_secs)
            continue

        last_wake = ""

        def callback(indata, frames, time_info, status):
            nonlocal last_wake
            out = s.feed(bytes(indata))
            if out["event"] == "wake":
                last_wake = ("%s | %s"
                             % (dt.datetime.now().strftime("%H:%M:%S"),
                                out["text"]))
                print("[%s] [ИМЯ!] услышал: «%s» (сработало: %s)"
                      % (dt.datetime.now().strftime("%H:%M:%S"),
                         out["text"], out["word"]))
                _write_status("ok", last_wake=last_wake)

        try:
            stream, mic_name = _open_ear_stream(sounddevice, s.sample_rate,
                                                callback)
            with stream:
                print("[%s] УХО ЖИВО: слушаю «%s» (%d Гц, модель %s)"
                      % (dt.datetime.now().strftime("%H:%M:%S"), mic_name,
                         s.sample_rate, s.model_dir.name))
                _write_status("ok", last_wake=last_wake,
                              device=mic_name)   # ухо открылось
                while True:
                    time.sleep(heartbeat)
                    _write_status("ok", last_wake=last_wake,
                                  device=mic_name)  # сердцебиение
        except Exception as e:
            # микрофон выдернули / занят / прав нет — не умираем: ждём и пробуем снова
            print("[%s] микрофон недоступен: %s — жду %.0f с и пробую снова"
                  % (dt.datetime.now().strftime("%H:%M:%S"), e, retry_secs))
            _write_status("no_mic", error=str(e))
            time.sleep(retry_secs)


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else ""
    if arg == "--check":
        print(check(Path(sys.argv[2]) if len(sys.argv) > 2 else None))
    elif arg == "--demo":
        demo(float(sys.argv[2]) if len(sys.argv) > 2 else 60.0)
    elif arg == "--service":
        # вечная служба для автозапуска дома (start_marfa.py её поднимает)
        try:
            serve()
        except KeyboardInterrupt:
            print("служба ушей остановлена (Ctrl+C)")
    else:
        print(__doc__)
