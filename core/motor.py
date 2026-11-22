# -*- coding: utf-8 -*-
r"""core/motor.py — РУКИ ДОМА v2 «ЕДИНОЕ ЗРЕНИЕ» (ТЗ_Руки_v2, 22.11).

Возвращение к дому. v1 наняла UI-TARS-7B-DPO четвёртым слугой (порт
8084) с VRAM-танцем: глаза присели → руки поднялись (десятки секунд) →
сделали → руки легли → глаза вернулись (ещё десятки секунд). Живой
прогон показал цену: камера слепнет, «посмотри» стоит в очереди,
Создатель смотрит на часы. Мастер-ТЗ (канон) говорит другое:

- §4, принцип хозяина ресурса: VRAM 6 ГБ — хозяин ГОЛА (Qwen2.5-VL,
  порт 8083); смена хозяина — только по расписанию;
- §8 + Р-4: Qwen2.5-VL-3B выбрана ПОТОМУ, что возвращает и текст,
  и координаты — ровно случай «кнопка "Отправить": X 450, Y 600»;
- §10.2: клик — только по валидированному центру bbox;
- §10.4-3: после действия — новый снимок и подтверждение изменения.

Значит, рукам НЕ НУЖНА своя модель. У дома одно зрение — глаза 8083,
руки — ИСПОЛНИТЕЛЬ координат глаз:

    задание словами → глаза.describe_with_sizes() → элемент по тексту →
    центр bbox → масштаб кадра → пиксели экрана → СТРАЖ →
    сухой план | клик → пиксельная сверка

Глаза больше никогда не приседают ради рук; камера не слепнет; ответ
рук — один взгляд глаз (~9 с), а не перезапуск сервера (десятки
секунд дважды).

UI-TARS (порт 8084) — в ЧУЛАН: файлы лежат в models\, дом их не
нанимает; вернуть может только резолюция Создателя. Порт 8084 свободен.
VRAM-танец остался у единственного тяжёлого заёмщика — кодера
(core/vram.py + core/repair.py).

Моторика (реальные клики и печать) — ТОЛЬКО по резолюции Создателя:
data\hands_enabled.json, кнопка 91_hands_gate.bat. Без неё — СУХОЙ
РЕЖИМ: руки называют действие и точку, мышь не трогают. Экзамен Р-0
v2 («руки, экзамен») проверяет ЦЕПОЧКУ глаза→руки на кнопке Пуск:
сухой режим — рассчитывает точку и масштаб; моторный — кликает,
сверяет пиксели и закрывает меню (Esc из whitelist).

Швы для тестов (tests/test_motor.py подменяет): _screenshot / _execute /
_dpi_aware / enabled — реальный экран и мышь не нужны.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import sys
import time
from pathlib import Path
from typing import Optional

from core import config, progress
from safety import guard

# Задание на РАЗГЛЯДЫВАНИЕ — не для рук (урок живого прогона 22.11:
# мозг поручил рукам «посмотри на меня» — VRAM-танец впустую и клик в
# никуда; смотреть — работа глаз и камеры, быстрые команды).
_LOOKING_MARKS = ("посмотр", "что видишь", "опиши", "прочитай",
                  "камер", "скриншот")

# Глаголы протокола (ТЗ_Руки_v2, раздел 4). Задание Создателя и мозга —
# словами; руки разбирают глагол, остальное — цель или текст.
_VERBS_CLICK = ("нажми", "кликни", "щёлкни", "щелкни", "открой",
                "запусти", "тыкни", "кликнуть")
_VERBS_TYPE = ("напечатай", "набери", "введи", "напиши")
_VERBS_SCROLL = ("прокрути", "прокрутить", "скролль", "скролли",
                 "скроль", "листай", "прокрутишь")
# Латинское сочетание клавиш: «enter», «ctrl c», «ctrl+c», «alt tab»
_COMBO_RX = re.compile(r"^[a-z0-9]+(?:\s*[+\s]\s*[a-z0-9]+)*$")


# ---------------------------------------------------------------
# Резолюция Создателя
# ---------------------------------------------------------------

def enabled() -> bool:
    """Включена ли моторика: data\\hands_enabled.json (кнопка 91).

    Воля Создателя живёт в data/ (в git не попадает) — как резолюция
    живого языка. Файл есть — руки двигают мышью; файла нет — сухой
    режим: план без движения. Код НИКОГДА не пишет этот файл сам.
    """
    return Path(config.HANDS_ENABLED_FILE).is_file()


# ---------------------------------------------------------------
# Разбор задания словами (ТЗ 4)
# ---------------------------------------------------------------

def _norm_combo(s: str) -> str:
    """«ctrl c» / «ctrl + c» / «CTRL C» → «ctrl+c» (формат whitelist)."""
    parts = [p for p in re.split(r"[+ ]", (s or "").strip().lower()) if p]
    return "+".join(parts)


def _after_verb(text: str, verb: str) -> str:
    """Хвост задания после глагола — в ИСХОДНОМ регистре (печать
    бережёт регистр, сверка текстов приводит сама)."""
    return text[len(verb):].strip(" ,:;!.")


def parse_task(task: str) -> dict:
    """Задание словами → план {"verb": ..., ...}.

    verb: click (клик по элементу с прочитанной надписью) | type |
    hotkey | scroll | unknown | empty. Клавиши узнаются по виду:
    «нажми enter» и «клавиши ctrl s» — клавиши, «нажми Пуск» — клик
    по элементу. Примеры значений координат здесь не нужны в принципе:
    руки больше не спрашивают модель о цифрах — цифры дают глаза.
    """
    t = (task or "").strip()
    # «руки, нажми Пуск» — слово «руки» съедает агент, но на всякий
    # случай снимаем и его сами
    t = re.sub(r"^руки\b[\s,;:—-]*", "", t, flags=re.IGNORECASE).strip()
    if not t:
        return {"verb": "empty"}
    low = t.lower().replace("ё", "е")

    # горячие клавиши: «клавиши ctrl+c», «сочетание ctrl c», «нажми
    # клавиши alt tab», «горячая ctrl s»
    m = re.match(r"^(?:нажми\s+|нажать\s+)?(?:клавиши|клавишу|сочетание|"
                 r"сочетании|горячую|горячие|горячая)\s+(.+)$", low)
    if m:
        return {"verb": "hotkey", "combo": _norm_combo(m.group(1))}

    for v in _VERBS_CLICK:
        if low.startswith(v + " ") or low == v:
            target = _after_verb(t, v)
            if not target:
                return {"verb": "empty"}       # «нажми» без цели — подсказка
            if _COMBO_RX.match(target.lower().strip()):
                return {"verb": "hotkey", "combo": _norm_combo(target)}
            return {"verb": "click", "target": target}
    for v in _VERBS_TYPE:
        if low.startswith(v + " ") or low == v:
            text = _after_verb(t, v)
            if not text:
                return {"verb": "empty"}       # «напечатай» без текста
            return {"verb": "type", "text": text}
    for v in _VERBS_SCROLL:
        if low.startswith(v + " ") or low == v:
            rest = _after_verb(t, v).lower().replace("ё", "е")
            if "вверх" in rest or "up" in rest:
                return {"verb": "scroll", "direction": "up"}
            if "вниз" in rest or "down" in rest:
                return {"verb": "scroll", "direction": "down"}
            return {"verb": "scroll", "direction": "down"}  # по умолчанию вниз
    return {"verb": "unknown", "raw": t[:120]}


_HINT = ("Формат задания: «нажми <надпись>» (клик по элементу с этой "
         "надписью), «напечатай <текст>» (латиница — напрямую, кириллица — "
         "через буфер и ctrl+v), «клавиши <ctrl+c>», «прокрути вверх/вниз». "
         "Пример: «руки нажми Пуск». Экзамен цепочки глаза→руки — «руки, "
         "экзамен»")


# ---------------------------------------------------------------
# Сверка текстов: задание ↔ надпись элемента (ТЗ 4)
# ---------------------------------------------------------------

def _norm_text(s) -> str:
    """Нормализация для сверки: нижний регистр, ё→е, без пунктуации."""
    s = str(s or "").lower().replace("ё", "е")
    s = re.sub(r"[«»\"'()\[\]{}.,;:!?…\-–—_/\\]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _conf(el: dict) -> float:
    """Уверенность глаза в элементе; нет числа — честный 0.0."""
    try:
        return float(el.get("confidence") or 0.0)
    except (TypeError, ValueError):
        return 0.0


# Слова-указатели рода элемента: «кнопку Сохранить» → «Сохранить»
_KIND_WORDS = (r"(?:кнопк\w+|ссылк\w+|поле|поля|меню|вкладк\w+|"
               r"иконк\w+|окн\w+)")


def find_element(d: dict, target: str,
                 min_conf: Optional[float] = None) -> Optional[dict]:
    """Найти элемент дескриптора по тексту задания.

    Мастер-ТЗ §10: VLM возвращает текст И координаты — руки сверяют
    надпись. §10.3: элементы с confidence < 0.6 — НЕИЗВЕСТНЫЕ, кликать
    нельзя. Порядок сверки: точное совпадение → надпись внутри цели →
    цель внутри надписи («Пуск» в «нажми кнопку Пуска»). Ничего — None:
    руки не угадывают, честно говорят «не вижу».
    """
    want = _norm_text(target)
    if not want:
        return None
    want = re.sub(r"^%s\s+" % _KIND_WORDS, "", want).strip()
    if not want:
        return None
    thr = config.HANDS_MIN_CONFIDENCE if min_conf is None else min_conf
    els = [e for e in (d.get("elements") or [])
           if isinstance(e, dict) and e.get("bbox")]
    sure = [e for e in els if _conf(e) >= thr]
    # 1) точное совпадение среди уверенных
    for e in sure:
        if _norm_text(e.get("text")) == want:
            return e
    # 2) надпись внутри цели («нажми кнопку Пуска» ⊃ «пуск»)
    for e in sure:
        txt = _norm_text(e.get("text"))
        if txt and txt in want:
            return e
    # 3) цель внутри надписи («блокнот» ⊂ «Блокнот — Безымянный»)
    for e in sure:
        txt = _norm_text(e.get("text"))
        if txt and want in txt:
            return e
    return None


# ---------------------------------------------------------------
# Координаты: центр bbox → пиксели реального экрана (§10.2)
# ---------------------------------------------------------------

def scale_point(x: int, y: int, real_size, sent_size) -> tuple:
    """Координаты КАДРА (что видят глаза) -> пиксели реального экрана.

    Глаза сжимают снимок до WORK_WIDTH; мышь живёт в реальном
    разрешении. Без масштабирования клик ушёл бы в левый верхний угол.
    Клип в границы экрана — страховка от округления на краю: валидный
    bbox по построению даёт точку ВНУТРИ экрана (инвариант единого
    зрения, тест гоняет его 200 случайными кадрами).
    """
    if not sent_size or not sent_size[0] or not real_size:
        return int(x), int(y)
    kx = float(real_size[0]) / float(sent_size[0])
    ky = float(real_size[1]) / float(sent_size[1])
    px = min(int(round(x * kx)), int(real_size[0]) - 1)
    py = min(int(round(y * ky)), int(real_size[1]) - 1)
    return max(0, px), max(0, py)


def frame_center(el: dict) -> tuple:
    """Центр bbox в координатах КАДРА (bbox уже проверен глазами:
    живёт внутри кадра — валидатор глаз v3 выбрасывает выдуманную
    геометрию ДО того, как её увидят руки)."""
    x1, y1, x2, y2 = el["bbox"]
    return (x1 + x2) // 2, (y1 + y2) // 2


def click_point(el: dict, real_size, sent_size) -> tuple:
    """Центр bbox элемента -> пиксели реального экрана (§10.2: клик —
    только по валидированному центру бокса, ничего от себя)."""
    cx, cy = frame_center(el)
    return scale_point(cx, cy, real_size, sent_size)


# ---------------------------------------------------------------
# СТРАЖ моторики (ТЗ 6): whitelist — код, не мнение модели
# ---------------------------------------------------------------

def guard_action(name: str, args, real_size) -> guard.Verdict:
    """Вердикт стража на ОДНО действие рук (точка уже в экранных
    пикселях — координаты дала валидированная геометрия глаз)."""
    if name == "click":
        x, y = int(args[0]), int(args[1])
        if not (0 <= x < real_size[0] and 0 <= y < real_size[1]):
            return guard.Verdict("HIGH", "deny",
                                 "клик за краем экрана (%d, %d)" % (x, y),
                                 "hands.bounds")
        return guard.Verdict("MEDIUM", "allow",
                             "клик (%d, %d)" % (x, y), "hands.click")
    if name == "type":
        text = args[0] or ""
        if len(text) > config.HANDS_TYPE_LIMIT:
            return guard.Verdict("HIGH", "deny",
                                 "печать длиннее %d символов"
                                 % config.HANDS_TYPE_LIMIT, "hands.type.len")
        v = guard.check_secrets(text)
        if not v.allowed():
            return v
        if any(ord(c) > 127 for c in text):
            # Р-4 закрыт буфером (№18): не-латиница печатается ВСТАВКОЙ
            # ctrl+v из буфера — прямой ввод pyautogui.write кириллицу
            # не умеет. Исполнитель сам уводит такой текст в paste —
            # сюда он попадёт, только если его позвали напрямую
            return guard.Verdict("HIGH", "deny",
                                 "прямой ввод — только латиница; кириллица "
                                 "печатается через буфер (ctrl+v)",
                                 "hands.type.charset")
        return guard.Verdict("MEDIUM", "allow",
                             "печать %d символов" % len(text), "hands.type")
    if name == "paste":
        # №18+Р-4: текст кладётся в буфер и вставляется ctrl+v —
        # так печатаются кириллица и любой юникод. Лимит — общий закон
        # печати, секреты — мимо (буфер живёт дольше чата)
        text = args[0] or ""
        if len(text) > config.HANDS_TYPE_LIMIT:
            return guard.Verdict("HIGH", "deny",
                                 "вставка длиннее %d символов"
                                 % config.HANDS_TYPE_LIMIT, "hands.paste.len")
        v = guard.check_secrets(text)
        if not v.allowed():
            return v
        return guard.Verdict("MEDIUM", "allow",
                             "вставка из буфера %d символов" % len(text),
                             "hands.paste")
    if name == "hotkey":
        key = (args[0] or "").strip().lower()
        if key not in config.HANDS_HOTKEY_WHITELIST:
            return guard.Verdict("HIGH", "deny",
                                 "сочетание «%s» не в whitelist (№19)" % key,
                                 "hands.hotkey.whitelist")
        return guard.Verdict("MEDIUM", "allow", "hotkey %s" % key,
                             "hands.hotkey")
    # scroll — простое, без координат и текста
    return guard.Verdict("LOW", "allow", name, "hands.simple")


# ---------------------------------------------------------------
# Исполнение (pyautogui — лениво, честная ошибка без него)
# ---------------------------------------------------------------

def _dpi_aware() -> None:
    """Физические пиксели для мыши (мастер-ТЗ §10.2): DPI-aware процесс.

    Windows-виртуализация (125%/150%) отдаёт не-aware процессу
    логические координаты — pyautogui жмёт мимо даже при верном
    масштабе. Вызываем до первого движения мыши; повторный вызов
    безвреден (отказ уже выставленной политики молча проглатываем)."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)   # per-monitor
        except Exception:
            ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


def _execute(name: str, args) -> str:
    """Исполнить одобренное действие. Возвращает честную сводку."""
    try:
        import pyautogui
    except ImportError as e:
        return ("не исполнила: нет pyautogui (%s) — "
                "venv\\Scripts\\pip install pyautogui" % e)
    _dpi_aware()
    if name == "click":
        x, y = int(args[0]), int(args[1])
        pyautogui.click(x, y)
        return "кликнула (%d, %d)" % (x, y)
    if name == "type":
        pyautogui.write(args[0] or "", interval=0.02)
        return "напечатала %d символов" % len(args[0] or "")
    if name == "scroll":
        up = str(args[0]).lower() == "up"
        pyautogui.scroll(300 if up else -300)
        return "прокрутила %s" % ("вверх" if up else "вниз")
    if name == "hotkey":
        parts = [p.strip() for p in str(args[0]).lower().split("+")
                 if p.strip()]
        pyautogui.hotkey(*parts)
        return "нажала %s" % "+".join(parts)
    return ""


# ---------------------------------------------------------------
# Пиксельная сверка (урок v1.5: истину говорят пиксели, §10.4)
# ---------------------------------------------------------------

def _pixel_diff(before_b64: str, after_b64: str, box=None) -> Optional[float]:
    """Доля изменившихся пикселей (0..1) в области клика.

    None — сравнить не смогли (нет PIL / разные размеры): честно не
    выдумываем «изменилось». diff > 30 по яркости считаем изменением.
    """
    try:
        import io as _io
        import base64 as _b64
        from PIL import Image
        a = Image.open(_io.BytesIO(_b64.b64decode(before_b64))).convert("RGB")
        b = Image.open(_io.BytesIO(_b64.b64decode(after_b64))).convert("RGB")
        if box:
            pad = 24
            box = (max(0, box[0] - pad), max(0, box[1] - pad),
                   min(a.width, box[2] + pad), min(a.height, box[3] + pad))
            a, b = a.crop(box), b.crop(box)
        if a.size != b.size:
            return None
        from PIL import ImageChops
        diff = ImageChops.difference(a, b).convert("L")
        hist = diff.histogram()
        changed = sum(hist[30:])
        return changed / float(a.width * a.height)
    except Exception:
        return None


# ---------------------------------------------------------------
# Лог действий (правило 6.6: логи — истина)
# ---------------------------------------------------------------

def _log_act(rec: dict) -> None:
    try:
        p = Path(config.HANDS_LOG_FILE)
        p.parent.mkdir(parents=True, exist_ok=True)
        rec = dict(rec)
        rec.setdefault("ts", dt.datetime.now().isoformat(timespec="seconds"))
        with p.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except OSError:
        pass


def _lesson(kind: str, text: str) -> None:
    try:
        from evolution.journal import log_lesson
        log_lesson(kind, text)
    except Exception:
        pass


# ---------------------------------------------------------------
# Шов экрана (тесты подменяют)
# ---------------------------------------------------------------

def _screenshot():
    """Снимок для пиксельной сверки — тем же инструментом, что и глаза."""
    from core import eyes
    if eyes._VISION_ERROR:
        raise RuntimeError("глаза не готовы: " + eyes._VISION_ERROR)
    return eyes._screenshot_b64(eyes.WORK_WIDTH)


# ---------------------------------------------------------------
# Цикл задачи (ТЗ 5): один взгляд глаз — одно действие рук
# ---------------------------------------------------------------

def run(task: str) -> str:
    """Выполнить задание руками на координатах глаз (единое зрение).

    Цепочка: задание словами → дескриптор глаз → элемент по тексту →
    центр bbox → масштаб → СТРАЖ → (исполнить | сухой режим) →
    пиксельная сверка. Сервер зрения не гаснет: VRAM не танцует.
    """
    task = (task or "").strip()
    low = task.lower()
    if any(mark in low for mark in _LOOKING_MARKS):
        # Урок живого прогона 22.11: «посмотри на меня» ушло РУКАМ —
        # VRAM-танец впустую и клик в никуда. Руки не смотрят.
        _log_act({"task": task, "redirect": "eyes"})
        _lesson("руки-не-смотрят", task)
        return ("РУКИ не смотрят — это работа глаз и камеры, быстрые "
                "команды: «посмотри» (экран), «посмотри в камеру» "
                "(веб-камера), «проверь камеру» (живой тест). Руки жмут "
                "и печатают: «руки нажми Пуск». Экзамен цепочки — "
                "«руки, экзамен»")
    plan = parse_task(task)
    if plan["verb"] == "empty":
        return "руки ждут задание. " + _HINT
    if plan["verb"] == "unknown":
        _log_act({"task": task, "ok": False, "why": "не поняла задание"})
        return ("РУКИ не поняли задание «%s». %s"
                % (task.strip(",;:.! "), _HINT))
    mode = ("моторика ВКЛЮЧЕНА (резолюция Создателя)" if enabled()
            else "сухой режим: план без кликов (включить — кнопка 91)")
    lines = ["РУКИ — задание: %s [%s]" % (task, mode)]
    # эфир: самый долгий шаг рук — взгляд глаз; дальше план мгновенен
    progress.stage("руки: смотрю на экран глазами и ищу цель…")
    started = time.time()
    try:
        if plan["verb"] == "click":
            lines += _do_click(task, plan["target"], enabled())
        elif plan["verb"] == "type":
            text = plan["text"]
            if any(ord(ch) > 127 for ch in text):
                # Р-4 закрыт (№18): кириллица/юникод — через буфер и
                # ctrl+v, прямой ввод pyautogui.write их не умеет
                lines += _do_paste(task, text, enabled())
            else:
                lines += _do_simple(task, "type", (text,),
                                    'напечатать «%s»' % text, enabled())
        elif plan["verb"] == "hotkey":
            lines += _do_simple(task, "hotkey", (plan["combo"],),
                                'нажать %s' % plan["combo"], enabled())
        elif plan["verb"] == "scroll":
            lines += _do_simple(task, "scroll", (plan["direction"],),
                                'прокрутить %s' % plan["direction"], enabled())
    except Exception as e:
        lines.append("ошибка рук: %s" % e)
        _lesson("руки-ошибка", "%s: %s" % (task, e))
    _log_act({"task": task, "verb": plan["verb"],
              "secs": round(time.time() - started, 1), "mode":
              "motor" if enabled() else "dry"})
    return "\n".join(lines)


def _eyes_or_honest():
    """Глаза живы? Рукам нужны их координаты — без зрения честный отказ,
    никакого самовольного перезапуска серверов (хозяин VRAM — глаза)."""
    from core import eyes
    if eyes._VISION_ERROR:
        raise RuntimeError("глаза не готовы: " + eyes._VISION_ERROR)
    if not eyes.health():
        raise RuntimeError(
            "глаза %d не отвечают — рукам нужны координаты глаз (единое "
            "зрение). Скажи «доктор» или перезапусти дом" % config.PORT_EYES)
    return eyes


def _seen_texts(d: dict, limit: int = 6) -> str:
    """Что глаза ЧИТАЮТ на экране — для честного «не вижу, вот что вижу».

    v2.1 (живой прогон 22.11: «руки нажми Пуск» → «глаза не прочитали
    ни одной надписи» — а ПОЧЕМУ пусто, дом промолчал): пустота теперь
    приходит с ПРИЧИНОЙ из _stats дескриптора — модель ничего не
    вернула / геометрия не прошла проверку / увидели объекты, но
    надписей не прочитали. Молчаливый симптом — не диагноз; в следующем
    прогоне Создателя архитектор должен увидеть корень, а не угадывать.
    """
    texts = [str(e.get("text", "")).strip() for e in (d.get("elements") or [])
             if isinstance(e, dict) and str(e.get("text", "")).strip()]
    if texts:
        return ", ".join("«%s»" % t for t in texts[:limit])
    st = d.get("_stats") if isinstance(d, dict) else None
    if isinstance(st, dict):
        raw = int(st.get("raw") or 0)
        kept = int(st.get("kept") or 0)
        dropped = int(st.get("dropped") or 0)
        if raw and dropped >= raw:
            return ("глаза увидели %d элемент(ов), но НИ ОДИН не прошёл "
                    "проверку координат (геометрия вне кадра) — сообщи "
                    "архитектору, это лечится" % raw)
        if kept:
            return ("глаза видят %d объект(ов), но надписей на них не "
                    "прочитали — света/масштаба не хватило; скажи "
                    "«посмотри» — опишу словами" % kept)
    return "глаза не прочитали на экране ни одной надписи"


def _do_click(task: str, target: str, motor: bool) -> list:
    """Клик по элементу с надписью из задания (ТЗ 5.1)."""
    eyes = _eyes_or_honest()
    d, real, sent = eyes.describe_with_sizes()
    el = find_element(d, target)
    if el is None:
        weak = find_element(d, target, min_conf=0.0)
        if weak is not None:
            _lesson("руки-неуверенно", "%s: %s (%.2f)"
                    % (task, weak.get("text"), _conf(weak)))
            return [("РУКИ не рискнули: вижу похожее — «%s», но "
                     "уверенность глаз %.2f < %.1f (мастер-ТЗ §10.3: "
                     "неуверенное — НЕИЗВЕСТНОЕ). Скажи «посмотри» — "
                     "глаза опишут экран точнее"
                     % (weak.get("text"), _conf(weak),
                        config.HANDS_MIN_CONFIDENCE))]
        _lesson("руки-не-видят", "%s: не нашли %r" % (task, target))
        return [("РУКИ не видят на экране «%s». Глаза читают: %s. "
                 "Скажи «посмотри» — опишу экран; может, надпись "
                 "звучит иначе" % (target, _seen_texts(d)))]
    x, y = click_point(el, real, sent)
    v = guard_action("click", (x, y), real)
    guard.decide(v, {"tool": "ui_action", "task": task, "verb": "click"})
    label = str(el.get("text") or el.get("type") or "?").strip()
    _log_act({"task": task, "verb": "click", "element": label,
              "bbox": el.get("bbox"), "point": [x, y],
              "confidence": _conf(el),
              "verdict": v.to_dict(), "mode": "motor" if motor else "dry"})
    if not v.allowed():
        _lesson("руки-страж", "%s: %s" % (task, v.reason))
        return ["СТРАЖ ОТКАЗАЛ: %s" % v.reason]
    if not motor:
        return [("СУХОЙ РЕЖИМ: кликнула бы в (%d, %d) — центр бокса "
                 "«%s» %s (уверенность глаз %.2f). Включить моторику — "
                 "кнопка 91"
                 % (x, y, label, el.get("bbox"), _conf(el)))]
    # моторика: замкнутый цикл — до/после, пиксельная сверка (§10.4)
    before, _, _ = _screenshot()
    res = _execute("click", (x, y))
    lines = [res + " — по центру бокса «%s» (уверенность %.2f)"
             % (label, _conf(el))]
    time.sleep(0.6)                      # экрану нужно мгновение открыться
    after, _, _ = _screenshot()
    frac = _pixel_diff(before, after, el.get("bbox"))
    if frac is None:
        lines.append("сверка пикселей: не смогла сравнить — честно, "
                     "не выдумываю")
    elif frac > 0.005:
        lines.append("сверка пикселей: у клика экран изменился на %.0f%% "
                     "кадра — замкнутый цикл работает" % (frac * 100))
    else:
        lines.append("сверка пикселей: экран почти не изменился (%.1f%%) — "
                     "возможно, клик не сработал; скажи «посмотри», "
                     "проверю глазами" % (frac * 100))
    return lines


def _do_paste(task: str, text: str, motor: bool) -> list:
    """Печать кириллицы/юникода — через буфер и ctrl+v (№18+Р-4):

    текст ложится в clipboard (страж: лимит печати, секреты мимо) и
    вставляется hotkey ctrl+v из whitelist. Сухой режим — честный
    план без движения мыши. Буфер споткнулся — честный отказ,
    вставки не будет (ctrl+v без буфера вставил бы ПРОШЛЫЙ текст —
    это хуже, чем ничего).
    """
    from core import hands as _hands
    v = guard_action("paste", (text,), (1920, 1080))
    guard.decide(v, {"tool": "ui_action", "task": task, "verb": "paste"})
    _log_act({"task": task, "verb": "paste", "args": [len(text)],
              "verdict": v.to_dict(), "mode": "motor" if motor else "dry"})
    if not v.allowed():
        _lesson("руки-страж", "%s: %s" % (task, v.reason))
        return ["СТРАЖ ОТКАЗАЛ: %s" % v.reason]
    if not motor:
        return [("СУХОЙ РЕЖИМ: положила бы «%s» (%d симв.) в буфер и "
                 "вставила ctrl+v. Включить моторику — кнопка 91"
                 % (text[:40], len(text)))]
    try:
        clip_note = _hands.clipboard_write(text)
    except Exception as e:
        _lesson("руки-буфер", "%s: %s" % (task, e))
        return [("БУФЕР не принял текст: %s — вставки не будет: ctrl+v "
                 "без нового буфера вставил бы ПРОШЛОЕ, это хуже, чем "
                 "ничего. Скажи «в буфер %s» — проверим буфер отдельно"
                 % (e, text[:20]))]
    res = _execute("hotkey", ("ctrl+v",))
    return ["%s; вставила ctrl+v — «%s» (%d симв.)"
            % (clip_note.split(".")[0], text[:40], len(text)), res]


def _do_simple(task: str, name: str, args, human: str,
               motor: bool) -> list:
    """Печать / клавиши / прокрутка — без координат (ТЗ 5.2-5.4)."""
    real = (1920, 1080)                  # для стража границы не нужны,
    v = guard_action(name, args, real)   # но интерфейс один
    guard.decide(v, {"tool": "ui_action", "task": task, "verb": name})
    _log_act({"task": task, "verb": name, "args": list(args)[:1],
              "verdict": v.to_dict(), "mode": "motor" if motor else "dry"})
    if not v.allowed():
        _lesson("руки-страж", "%s: %s" % (task, v.reason))
        return ["СТРАЖ ОТКАЗАЛ: %s" % v.reason]
    if not motor:
        return ["СУХОЙ РЕЖИМ: %s. Включить моторику — кнопка 91" % human]
    return [_execute(name, args)]


# ---------------------------------------------------------------
# Экзамен Р-0 v2 (ТЗ 8): цепочка глаза→руки на кнопке Пуск
# ---------------------------------------------------------------

def exam() -> str:
    """Р-0 v2: живой экзамен ЦЕПОЧКИ глаза→руки (единое зрение).

    Глаза дают бокс Пуска из дескриптора, руки считают центр и
    масштаб. Сухой режим — только рассчитанная точка; моторный —
    настоящий клик, пиксельная сверка и Esc (меню закроется). VRAM
    не танцует: сервер зрения один и не гаснет — в этом и экзамен.
    """
    lines = ["ЭКЗАМЕН Р-0 v2 (цепочка глаза→руки, единое зрение)"]
    progress.stage("экзамен Р-0: глаза ищут «Пуск», руки меряют клик…")
    try:
        eyes = _eyes_or_honest()
        d, real, sent = eyes.describe_with_sizes()
    except Exception as e:
        return "\n".join(lines + ["не смогла спросить глаза: %s" % e])
    el = None
    for cand in d.get("elements", []):
        t = str(cand.get("text", "")).lower()
        if "пуск" in t or "start" in t:
            el = cand
            break
    if el is None:
        return "\n".join(
            lines + ["глаза не нашли Пуск в дескрипторе — экзамен не "
                     "состоялся. Глаза читают: %s. Открой меню Пуска "
                     "(клавиша Win) и скажи «руки, экзамен» ещё раз"
                     % _seen_texts(d)])
    bbox = el.get("bbox") or [0, 0, 0, 0]
    cx, cy = frame_center(el)
    x, y = scale_point(cx, cy, real, sent)
    lines.append("глаза: «%s» bbox %s (уверенность %s); центр кадра "
                 "(%d, %d) → экран (%d, %d) при масштабе %.2f×%.2f"
                 % (el.get("text"), bbox, el.get("confidence", "?"),
                    cx, cy, x, y,
                    real[0] / float(sent[0] or 1),
                    real[1] / float(sent[1] or 1)))
    motor = enabled()
    if not motor:
        _log_act({"exam": True, "eyes_bbox": bbox, "point": [x, y],
                  "mode": "dry"})
        return "\n".join(lines + [
            "СУХОЙ РЕЖИМ: кликнула бы в (%d, %d). Включи моторику "
            "(кнопка 91) и повтори «руки, экзамен» — тогда кликну "
            "по-настоящему и сверю пиксели" % (x, y)])
    try:
        v = guard_action("click", (x, y), real)
        guard.decide(v, {"tool": "ui_action", "task": "экзамен Р-0",
                         "verb": "exam"})
        if not v.allowed():
            return "\n".join(lines + ["СТРАЖ ОТКАЗАЛ: %s" % v.reason])
        before, _, _ = _screenshot()
        lines.append(_execute("click", (x, y)))
        time.sleep(0.8)                  # меню Пуска успевает открыться
        after, _, _ = _screenshot()
        frac = _pixel_diff(before, after)
        # уборка за экзаменом: Esc из whitelist закроет меню
        _execute("hotkey", ("esc",))
        if frac is not None and frac > 0.01:
            verdict = ("ЦЕПОЧКА РАБОТАЕТ: открытие меню изменило %.0f%% "
                       "кадра — глаза навели точно, руки нажали верно"
                       % (frac * 100))
        elif frac is not None:
            verdict = ("клик не изменил экран (%.1f%%) — координаты глаз "
                       "могут врать; НЕ доверяй моторике вслепую, сообщи "
                       "архитектору цифры выше" % (frac * 100))
        else:
            verdict = "пиксели не сравнились — честно: экзамен без вердикта"
        lines.append("сверка пикселей: " + verdict)
        _log_act({"exam": True, "eyes_bbox": bbox, "point": [x, y],
                  "changed_frac": None if frac is None else round(frac, 4),
                  "mode": "motor"})
        _lesson("руки-экзамен", "(%d,%d): %s" % (x, y, verdict[:80]))
        return "\n".join(lines)
    except Exception as e:
        return "\n".join(lines + ["ошибка экзамена: %s" % e])
