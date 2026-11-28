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

from core import config, loghygiene, progress
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
# КРУГ 36 (аудит 333): хоткей — это модификатор («ctrl c») или
# ИЗВЕСТНАЯ одиночная клавиша («enter», «esc»). Одиночное латинское
# слово («Send», «OK», «Save») — НАДПИСЬ кнопки английского интерфейса:
# её КЛИКАЮТ, а не «нажимают клавишей» — прежде английский интерфейс
# был некликабелен в принципе (verb=hotkey → «не в whitelist» → отказ).
# Источник имён — whitelist стража: чего страж не нажмёт, то и не клавиша.
_KEY_NAMES = frozenset(k for k in config.HANDS_HOTKEY_WHITELIST
                       if "+" not in k)
_MODIFIERS = frozenset(("ctrl", "alt", "shift", "win", "cmd", "meta"))


def _is_hotkey(combo: str) -> bool:
    """Сочетание с модификатором или одиночная известная клавиша —
    хоткей; «send»/«ok»/«save» — цели для клика."""
    parts = [p for p in re.split(r"[+ ]", (combo or "").strip().lower()) if p]
    if not parts:
        return False
    if len(parts) == 1:
        return parts[0] in _KEY_NAMES
    return any(p in _MODIFIERS for p in parts[:-1])


# ---------------------------------------------------------------
# Резолюция Создателя
# ---------------------------------------------------------------

def enabled() -> bool:
    """Включена ли моторика: data\\hands_enabled.json (кнопка 91 или
    калитка Создателя).

    КРУГ 36 (аудит 332): файл обязан быть ЧЕСТНОЙ резолюцией —
    валидный JSON-словарь, как пишет кнопка 91. Пустой файл или мусор
    раньше включали моторику по самому факту существования — мозгу
    хватало пустого write_file, чтобы разрешить себе реальные клики.
    (Страж круга 36 заодно запретил мозгу писать этот файл вовсе.)
    """
    try:
        rec = json.loads(Path(config.HANDS_ENABLED_FILE)
                         .read_text(encoding="utf-8"))
        return isinstance(rec, dict)
    except (OSError, ValueError):
        return False


def set_enabled(on: bool) -> str:
    """Резолюция Создателя на моторику — ЧЕСТНОЙ записью: атомарно
    (tmp + replace, как кнопка 91) и с обоснованием внутри. Зовет
    калитка (за кодовым словом) и диспетчер (для выключения); мозг
    этот файл писать не может — страж, круг 36."""
    p = Path(config.HANDS_ENABLED_FILE)
    if on:
        rec = {"ts": dt.datetime.now().isoformat(timespec="seconds"),
               "resolution": "моторика рук включена Создателем",
               "basis": "кнопка 91 / калитка кодового слова (круг 36)"}
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(rec, ensure_ascii=False, indent=1),
                       encoding="utf-8")
        tmp.replace(p)
        return ("моторика ВКЛЮЧЕНА: руки исполняют действия под стражем "
                "(whitelist клавиш, лимит печати, клики в границах "
                "экрана)")
    try:
        p.unlink()
    except FileNotFoundError:
        pass
    return "моторика выключена — руки снова в сухом режиме"


# ---------------------------------------------------------------
# Разбор задания словами (ТЗ 4)
# ---------------------------------------------------------------

def _norm_combo(s: str) -> str:
    """«ctrl c» / «ctrl + c» / «CTRL C» → «ctrl+c» (формат whitelist)."""
    parts = [p for p in re.split(r"[+ ]", (s or "").strip().lower()) if p]
    return "+".join(parts)


def _after_verb(text: str, verb: str, keep_punct: bool = False) -> str:
    """Хвост задания после глагола — в ИСХОДНОМ регистре (печать
    бережёт регистр, сверка текстов приводит сама).

    КРУГ 36 (аудит, р4 №20): «напечатай Привет!» печатает «Привет!» —
    «!» и «.» в печати — ДАННЫЕ, не интонация. Для клика/прокрутки
    пунктуация цели всё равно нормализуется сверкой — там режем."""
    cut = " ,:;" if keep_punct else " ,:;!."
    return text[len(verb):].strip(cut)


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
            if _COMBO_RX.match(target.lower().strip()) and _is_hotkey(target):
                return {"verb": "hotkey", "combo": _norm_combo(target)}
            return {"verb": "click", "target": target}
    for v in _VERBS_TYPE:
        if low.startswith(v + " ") or low == v:
            text = _after_verb(t, v, keep_punct=True)
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
            # КРУГ 36 (аудит): «прокрути влево» — НЕ догадка «вниз»:
            # неизвестное направление — честный отказ, не тихий клик
            return {"verb": "unknown", "raw": t[:120]}
    return {"verb": "unknown", "raw": t[:120]}


_HINT = ("Формат задания: «нажми <надпись>» (клик по элементу с этой "
         "надписью), «напечатай <текст>» (латиница — напрямую, кириллица — "
         "через буфер и ctrl+v), «клавиши <ctrl+c>», «прокрути вверх/вниз». "
         "Пример: «руки нажми Пуск». Экзамен цепочки глаза→руки — «руки, "
         "экзамен»")


def help_text() -> str:
    """«руки» / «что умеют руки» — дружелюбная шпаргалка (23.11).

    Урок живого лога: на «Руки проверить работу микрофона» руки отвечали
    формат-ошибкой, а на «что у тебя за руки» — той же ошибкой. Руки —
    ИСПОЛНИТЕЛЬ (клик, печать, колесо), и рассказать о себе обязаны
    по-человечески: что умеют, чем смотрят, кто включает моторику —
    и что задание живым языком лучше говорить без слова «руки».
    """
    return (
        "МОИ РУКИ — исполнитель на экране, работают на координатах глаз:\n"
        "- «руки нажми <надпись>» — кликнуть по элементу с этой надписью "
        "(например: «руки нажми Пуск»);\n"
        "- «руки напечатай <текст>» — напечатать; кириллицу сама положу "
        "в буфер и вставлю ctrl+v;\n"
        "- «руки клавиши <ctrl+c>» — нажать сочетание клавиш;\n"
        "- «руки прокрути вниз/вверх» — колесо мыши;\n"
        "- «в буфер <текст>» — положить текст в буфер обмена.\n"
        "Руки не смотрят и не слушают: разглядеть — «посмотри» (экран) или "
        "«посмотри в камеру» (веб-камера), проверить слух — «проверь уши».\n"
        "Моторику (настоящие клики) включает Создатель — кнопка 91; без "
        "неё сухой режим: назову точку и план, но не трону мышь.\n"
        "Задание живым языком («проверь микрофон») просто скажи без слова "
        "«руки» — подумаю, как исполнить."
    )


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


def _label(el: dict) -> str:
    """Надпись элемента для честного вопроса Создателю."""
    return str(el.get("text") or el.get("type") or "?").strip()


class AmbiguousTarget(Exception):
    """Несколько элементов подходят под цель — клик без уточнения
    опасен (аудит 336: «Сохранить» и «Сохранить как» были
    неразличимы, бралось первое молча — клик не по той кнопке — самая
    дорогая ошибка модуля). candidates — надписи для вопроса."""

    def __init__(self, candidates: list):
        super().__init__("несколько элементов подходят под цель")
        self.candidates = [str(c) for c in candidates]


def _words_of(s) -> list:
    """Слова нормализованной строки — сверка по ГРАНИЦАМ слов."""
    return [w for w in _norm_text(s).split(" ") if w]


# Слова-указатели рода элемента: «кнопку Сохранить» → «Сохранить»
_KIND_WORDS = (r"(?:кнопк\w+|ссылк\w+|поле|поля|меню|вкладк\w+|"
               r"иконк\w+|окн\w+)")


def find_element(d: dict, target: str,
                 min_conf: Optional[float] = None) -> Optional[dict]:
    """Найти элемент дескриптора по тексту задания.

    Мастер-ТЗ §10: VLM возвращает текст И координаты — руки сверяют
    надпись. §10.3: элементы с confidence < 0.6 — НЕИЗВЕСТНЫЕ, кликать
    нельзя. Порядок сверки: точное совпадение → слова надписи — начала
    слов цели («Пуск» ⊂ «нажми кнопку Пуска») → слова цели — начала
    слов надписи («блокнот» ⊂ «Блокнот — Безымянный»). КРУГ 36 (аудит
    336): сверка по ГРАНИЦАМ слов и началам (не короче 3 симв.) —
    подстроки без границ матчили «ус» к «пуск»; НЕСКОЛЬКО кандидатов —
    AmbiguousTarget (кликать первое молча запрещено). Ничего — None:
    руки не угадывают, честно говорят «не вижу».
    """
    want = _norm_text(target)
    if not want:
        return None
    want = re.sub(r"^%s\s+" % _KIND_WORDS, "", want).strip()
    if not want:
        return None
    want_words = [w for w in want.split(" ") if w]
    thr = config.HANDS_MIN_CONFIDENCE if min_conf is None else min_conf
    els = [e for e in (d.get("elements") or [])
           if isinstance(e, dict) and e.get("bbox")]
    sure = [e for e in els if _conf(e) >= thr]
    # 1) точное совпадение среди уверенных
    exact = [e for e in sure if _norm_text(e.get("text")) == want]
    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1:
        raise AmbiguousTarget([_label(e) for e in exact])
    # 2) слова надписи — начала слов цели («нажми кнопку Пуска» ⊃ «пуск»)
    def _step2(e: dict) -> bool:
        return any(len(tw) >= 3 and any(w.startswith(tw) for w in want_words)
                   for tw in _words_of(e.get("text")))
    hits = [e for e in sure if _step2(e)]
    if len(hits) == 1:
        return hits[0]
    if len(hits) > 1:
        raise AmbiguousTarget([_label(e) for e in hits])
    # 3) слова цели — начала слов надписи («блокнот» ⊂ «Блокнот — Безымянный»)
    def _step3(e: dict) -> bool:
        tws = _words_of(e.get("text"))
        return any(len(w) >= 3 and any(tw.startswith(w) for tw in tws)
                   for w in want_words)
    hits = [e for e in sure if _step3(e)]
    if len(hits) == 1:
        return hits[0]
    if len(hits) > 1:
        raise AmbiguousTarget([_label(e) for e in hits])
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

    КРУГ 36 (аудит 334/335): размеры не полные — ЧЕСТНЫЙ ОТКАЗ, а не
    «страховка» сырыми кадровыми координатами: прежний return x, y —
    промах в левый верхний угол при включённой моторике, не отказ.
    Высоты (обе пары) проверяются наравне с ширинами: нулевая высота
    кадра раньше роняла ZeroDivisionError.
    """
    if (not isinstance(sent_size, (tuple, list)) or len(sent_size) < 2
            or not sent_size[0] or not sent_size[1]
            or not isinstance(real_size, (tuple, list)) or len(real_size) < 2
            or not real_size[0] or not real_size[1]):
        raise ValueError("глаза не дали полные размеры кадра/экрана — "
                         "масштаб клика не считается; кликаю только по "
                         "валидной геометрии (скажи «посмотри» и повтори)")
    kx = float(real_size[0]) / float(sent_size[0])
    ky = float(real_size[1]) / float(sent_size[1])
    px = min(int(round(x * kx)), int(real_size[0]) - 1)
    py = min(int(round(y * ky)), int(real_size[1]) - 1)
    return max(0, px), max(0, py)


def frame_center(el: dict) -> tuple:
    """Центр bbox в координатах КАДРА. КРУГ 36 (аудит 338): без
    валидного бокса — честный отказ, а не KeyError и не мёртвый
    [0,0,0,0]-фальшбэк: центр выдумывать нельзя."""
    bbox = el.get("bbox") if isinstance(el, dict) else None
    if not bbox or len(bbox) != 4:
        raise ValueError("элемент без валидного bbox — центра нет, клик "
                         "не считается")
    x1, y1, x2, y2 = bbox
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
    """Вердикт стража на ОДНО действие рук. real_size нужен только
    клику (границы экрана); остальным действиям экран не нужен — и
    КРУГ 36 (аудит) запрещает подсунуть ему ВЫДУМАННЫЙ экран: прежде
    _do_simple/_do_paste передавали (1920,1080) — интерфейс получал
    ложь о геометрии.

    КРУГ 36 (аудит 339): неизвестное имя действия — ОТКАЗ. Прежний
    fail-open в финальном else разрешал ВСЁ, что страж не знал, —
    страж с дырой; scroll получил свою явную ветку и проверку
    направления."""
    if name == "click":
        if not isinstance(real_size, (tuple, list)) or len(real_size) < 2:
            return guard.Verdict("HIGH", "deny",
                                 "клик без размеров экрана — границы не "
                                 "проверить", "hands.bounds")
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
    if name == "scroll":
        direction = str(args[0] if args else "").strip().lower()
        if direction not in ("up", "down"):
            return guard.Verdict("HIGH", "deny",
                                 "прокрутка «%s» не бывает — только "
                                 "вверх/вниз" % direction,
                                 "hands.scroll.dir")
        return guard.Verdict("LOW", "allow", "прокрутка %s" % direction,
                             "hands.scroll")
    # КРУГ 36 (аудит 339): страж не fail-open — незнакомое действие
    # НЕ исполняется тихо (прежде — LOW/allow для любого мусора)
    return guard.Verdict("HIGH", "deny",
                         "неизвестное действие рук: %s" % name,
                         "hands.unknown")


# ---------------------------------------------------------------
# Исполнение (pyautogui — лениво, честная ошибка без него)
# ---------------------------------------------------------------

def _dpi_aware() -> bool:
    """Физические пиксели для мыши (мастер-ТЗ §10.2): DPI-aware процесс.

    Windows-виртуализация (125%/150%) отдаёт не-aware процессу
    логические координаты — pyautogui жмёт мимо даже при верном
    масштабе. Вызывается ДО ИМПОРТА pyautogui (КРУГ 36, аудит 340:
    прежде импорт кэшировал виртуализованный размер экрана, и вызов
    после ничего уже не исправлял — клик мимо при верном масштабе).
    Повторный вызов безвреден. Возвращает False, если политику
    выставить не вышла, — дом должен ЗНАТЬ, что кликает в
    виртуализованных координатах (аудит: прежде отказы глатались
    молча, без урока и строки в ответе)."""
    if sys.platform != "win32":
        return True
    try:
        import ctypes
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)   # per-monitor
            return True
        except Exception:
            ctypes.windll.user32.SetProcessDPIAware()
            return True
    except Exception:
        return False


def _execute(name: str, args) -> str:
    """Исполнить одобренное действие. Возвращает честную сводку.

    КРУГ 36 (аудит 340): DPI-aware ДО импорта pyautogui — прежде
    импорт кэшировал виртуализованный размер экрана, и _dpi_aware
    после него уже ничего не исправлял. Отказ DPI — честная строка в
    ответе, не молчание."""
    dpi_warn = ""
    if not _dpi_aware():
        dpi_warn = ("; ВНИМАНИЕ: DPI-осознанность не выставилась — при "
                    "масштабе экрана 125%/150% клик может уйти мимо, "
                    "скажи архитектору")
    try:
        import pyautogui
    except ImportError as e:
        return ("не исполнила: нет pyautogui (%s) — "
                "venv\\Scripts\\pip install pyautogui" % e)
    if name == "click":
        x, y = int(args[0]), int(args[1])
        pyautogui.click(x, y)
        return "кликнула (%d, %d)%s" % (x, y, dpi_warn)
    if name == "type":
        pyautogui.write(args[0] or "", interval=0.02)
        return "напечатала %d символов%s" % (len(args[0] or ""), dpi_warn)
    if name == "scroll":
        up = str(args[0]).lower() == "up"
        pyautogui.scroll(300 if up else -300)
        return "прокрутила %s%s" % ("вверх" if up else "вниз", dpi_warn)
    if name == "hotkey":
        parts = [p.strip() for p in str(args[0]).lower().split("+")
                 if p.strip()]
        pyautogui.hotkey(*parts)
        return "нажала %s%s" % ("+".join(parts), dpi_warn)
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
        rec = dict(rec)
        rec.setdefault("ts", dt.datetime.now().isoformat(timespec="seconds"))
        # Ф96 (круг 17): копилка моторных ходов — через дверь ротации
        loghygiene.append_line(p, json.dumps(rec, ensure_ascii=False) + "\n")
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
    """Снимок для пиксельной сверки — тем же инструментом, что и глаза.

    КРУГ 36 (аудит): швы соседа — через getattr с честным отказом:
    переименование в глазах не должно ронять руки МОЛЧА (броня
    съедала AttributeError и говорила «ошибка рук» без причины)."""
    from core import eyes
    err = getattr(eyes, "_VISION_ERROR", "")
    if err:
        raise RuntimeError("глаза не готовы: " + err)
    shot = getattr(eyes, "_screenshot_b64", None)
    if shot is None:
        raise RuntimeError("глаза не дали инструмент снимка — скажи "
                           "архитектору (шов _screenshot_b64 пропал)")
    return shot(eyes.WORK_WIDTH)


# ---------------------------------------------------------------
# Цикл задачи (ТЗ 5): один взгляд глаз — одно действие рук
# ---------------------------------------------------------------

def run(task: str) -> str:
    """Выполнить задание руками на координатах глаз (единое зрение).

    Цепочка: задание словами → дескриптор глаз → элемент по тексту →
    центр bbox → масштаб → СТРАЖ → (исполнить | сухой режим) →
    пиксельная сверка. Сервер зрения не гаснет: VRAM не танцует.

    КРУГ 36 (аудит): метки разглядывания — только в ПОЗИЦИИ глагола
    (задание НАЧИНАЕТСЯ с них): «нажми кнопку Прочитай» и «напечатай
    текст про камеру» — задания рук, а не редирект к глазам; резолюция
    читается ОДИН раз (режим строки и факт действия не расходятся);
    исход — в журнал рук (ok — по содержимому строк ответа); перевод
    строки в латинице уходит в буфер (pyautogui.write не умеет \n).
    """
    task = (task or "").strip()
    # «руки, нажми Пуск» — слово «руки» съедает агент, но на всякий
    # случай снимаем и его сами — ДО меток разглядывания: иначе
    # «руки, посмотри на экран» выглядело заданием про руки
    stripped = re.sub(r"^руки\b[\s,;:—-]*", "", task,
                      flags=re.IGNORECASE).strip() or task
    low = stripped.lower()
    # КРУГ 36 (аудит): метки разглядывания — ГЛАГОЛЬНЫЕ по ПРЕФИКСУ
    # задачи («посмотри…», «опиши…», «прочитай…»), ПРЕДМЕТНЫЕ
    # («камер», «скриншот») — в первых двух словах («включи камеру»,
    # «сделай скриншот»). Прежде подстрока по ВСЕМУ заданию уводила
    # к глазам «нажми кнопку Прочитай» и «напечатай текст про камеру».
    first_words = low.split()[:2]
    if any(low.startswith(m) for m in _LOOKING_MARKS) \
            or any(w.startswith(m) for m in _LOOKING_MARKS
                   for w in first_words):
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
    motor_on = enabled()
    mode = ("моторика ВКЛЮЧЕНА (резолюция Создателя)" if motor_on
            else "сухой режим: план без кликов (включить — кнопка 91)")
    lines = ["РУКИ — задание: %s [%s]" % (task, mode)]
    # эфир: самый долгий шаг рук — взгляд глаз; дальше план мгновенен
    progress.stage("руки: смотрю на экран глазами и ищу цель…")
    started = time.time()
    try:
        if plan["verb"] == "click":
            lines += _do_click(task, plan["target"], motor_on)
        elif plan["verb"] == "type":
            text = plan["text"]
            if any(ord(ch) > 127 for ch in text) \
                    or "\n" in text or "\r" in text:
                # Р-4 закрыт (№18) + КРУГ 36: кириллица/юникод И переводы
                # строк — через буфер и ctrl+v: pyautogui.write не умеет
                # \n, многострочная латиница ломалась прямой печатью
                lines += _do_paste(task, text, motor_on)
            else:
                lines += _do_simple(task, "type", (text,),
                                    'напечатать «%s»' % text, motor_on)
        elif plan["verb"] == "hotkey":
            lines += _do_simple(task, "hotkey", (plan["combo"],),
                                'нажать %s' % plan["combo"], motor_on)
        elif plan["verb"] == "scroll":
            lines += _do_simple(task, "scroll", (plan["direction"],),
                                'прокрутить %s' % plan["direction"], motor_on)
    except Exception as e:
        lines.append("ошибка рук: %s" % e)
        _lesson("руки-ошибка", "%s: %s" % (task, e))
    # КРУГ 36 (аудит): журнал рук отвечает на вопрос «кликнула ли» —
    # ok — по факту строк ответа, не по молчанию
    ok = not any(l.startswith(("СТРАЖ ОТКАЗАЛ", "ошибка рук", "РУКИ не"))
                 for l in lines)
    _log_act({"task": task, "verb": plan["verb"], "ok": ok,
              "secs": round(time.time() - started, 1),
              "mode": "motor" if motor_on else "dry"})
    return "\n".join(lines)


def _eyes_or_honest():
    """Глаза живы? Рукам нужны их координаты — без зрения честный отказ,
    никакого самовольного перезапуска серверов (хозяин VRAM — глаза).

    КРУГ 36 (аудит): шов _VISION_ERROR — через getattr: переименование
    в глазах не роняет руки молча."""
    from core import eyes
    err = getattr(eyes, "_VISION_ERROR", "")
    if err:
        raise RuntimeError("глаза не готовы: " + err)
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
        # КРУГ 36 (аудит): нечисловая статистика — честный ноль, а не
        # ValueError «ошибка рук» без причины
        def _num(v):
            try:
                return int(v)
            except (TypeError, ValueError):
                return 0
        raw = _num(st.get("raw"))
        kept = _num(st.get("kept"))
        dropped = _num(st.get("dropped"))
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
    """Клик по элементу с надписью из задания (ТЗ 5.1).

    КРУГ 36 (аудит 336): несколько подходящих элементов — честный
    ВОПРОС, а не тихий клик по первому. Порог пиксельной сверы 2%
    (аудит: 0.5% ловили мигание курсора и тикающие часы как «цикл
    работает»)."""
    eyes = _eyes_or_honest()
    d, real, sent = eyes.describe_with_sizes()
    try:
        el = find_element(d, target)
    except AmbiguousTarget as amb:
        seen = ", ".join("«%s»" % c for c in amb.candidates[:4])
        _log_act({"task": task, "verb": "click", "ok": False,
                  "why": "неоднозначно", "candidates": amb.candidates[:4]})
        _lesson("руки-неоднозначно", "%s: %s" % (task, seen))
        return [("РУКИ видят НЕСКОЛЬКО подходящих: %s — скажи точнее, "
                 "кликать наугад не буду (не по той кнопке — самая "
                 "дорогая моя ошибка)" % seen)]
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
    elif frac > 0.02:
        lines.append("сверка пикселей: у клика экран изменился на %.0f%% "
                     "области бокса — замкнутый цикл работает" % (frac * 100))
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

    КРУГ 36 (аудит): буфер Создателя — НЕ расходный материал: (1)
    сохраняю ДО записи (не смогла прочитать — честной строкой);
    (2) сверяю ЧТЕНИЕМ после записи — тихое несовпадение лечится
    отказом, а не вставкой прошлого; (3) возвращаю ПОСЛЕ вставки,
    отказ возврата — честной строкой. Раньше печать кириллицы
    уничтожала то, что Создатель скопировал до того.
    """
    from core import hands as _hands
    v = guard_action("paste", (text,), None)
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
    saved = None
    save_note = ""
    try:
        saved = _hands.clipboard_save_raw()
    except Exception as e:
        save_note = ("; старый буфер прочитать не смогла (%s) — если там "
                     "лежало что-то важное, оно затёрто этой печатью" % e)
    try:
        clip_note = _hands.clipboard_write(text)
    except Exception as e:
        _lesson("руки-буфер", "%s: %s" % (task, e))
        return [("БУФЕР не принял текст: %s — вставки не будет: ctrl+v "
                 "без нового буфера вставил бы ПРОШЛОЕ, это хуже, чем "
                 "ничего. Скажи «в буфер %s» — проверим буфер отдельно"
                 % (e, text[:20]))]
    # сверка: в буфере лежит ТО, что кладём — закон этого модуля
    try:
        back = _hands.clipboard_save_raw()
    except Exception:
        back = text            # сверить нечем — не врём про сверку
    if back != text:
        if saved:
            try:
                _hands.clipboard_restore(saved)
            except Exception:
                pass
        _lesson("руки-буфер-подмена", "%s: %d→%d симв."
                % (task, len(text), len(back)))
        return [("БУФЕР подменил текст при записи (клала %d симв., "
                 "прочитала %d) — вставки НЕ будет: ctrl+v вставил бы "
                 "не то. Скажи архитектору" % (len(text), len(back)))]
    res = _execute("hotkey", ("ctrl+v",))
    restore_note = ""
    if saved:
        try:
            _hands.clipboard_restore(saved)
        except Exception as e:
            restore_note = ("; буфер вернуть не смогла: %s — скопированное "
                            "до печати потеряно, прости" % e)
    elif saved == "":
        restore_note = ("; старый буфер был пуст (или не текст — картинкой "
                        "я не распоряжаюсь)")
    lines = ["%s; вставила ctrl+v — «%s» (%d симв.)%s%s"
             % (clip_note.split(".")[0], text[:40], len(text),
                restore_note, save_note), res]
    lines += _pixel_check_after()
    return lines


def _pixel_check_after() -> list:
    """Пиксельная сверка после моторного действия без координат
    (§10.4-3 обещан ВСЕМ действиям, не одному клику — КРУГ 36):
    печать/клавиши/прокрутка меняют экран так же. Сравнить не смогли —
    честно молчим, не выдумываем «работает»."""
    try:
        before, _, _ = _screenshot()
        time.sleep(0.4)
        after, _, _ = _screenshot()
        frac = _pixel_diff(before, after)
        if frac is None:
            return []
        if frac > 0.005:
            return ["сверка пикселей: экран изменился на %.1f%% кадра — "
                    "действие дало эффект" % (frac * 100)]
        return ["сверка пикселей: экран почти не изменился (%.1f%%) — "
                "возможно, действие не сработало; скажи «посмотри»"
                % (frac * 100)]
    except Exception:
        return []       # сверка — не орган дыхания действия


def _do_simple(task: str, name: str, args, human: str,
               motor: bool) -> list:
    """Печать / клавиши / прокрутка — без координат (ТЗ 5.2-5.4).

    КРУГ 36 (аудит): в журнал рук уходит ДЛИНА печати, а не сам текст
    (hands_log.jsonl читается мозгом — печать Создателя не должна
    лежать в читаемой мозгом папке); стражу этих действий экран не
    нужен (прежде передавали выдуманный 1920×1080); после моторного
    действия — пиксельная сверка (§10.4-3 — всем глаголам, не одному
    клику)."""
    v = guard_action(name, args, None)
    guard.decide(v, {"tool": "ui_action", "task": task, "verb": name})
    shown = [len(args[0]) if name in ("type", "paste") and args
             else (args[0] if args else None)]
    _log_act({"task": task, "verb": name, "args": shown,
              "verdict": v.to_dict(), "mode": "motor" if motor else "dry"})
    if not v.allowed():
        _lesson("руки-страж", "%s: %s" % (task, v.reason))
        return ["СТРАЖ ОТКАЗАЛ: %s" % v.reason]
    if not motor:
        return ["СУХОЙ РЕЖИМ: %s. Включить моторику — кнопка 91" % human]
    lines = [_execute(name, args)]
    lines += _pixel_check_after()
    return lines


# ---------------------------------------------------------------
# Экзамен Р-0 v2 (ТЗ 8): цепочка глаза→руки на кнопке Пуск
# ---------------------------------------------------------------

def exam() -> str:
    """Р-0 v2: живой экзамен ЦЕПОЧКИ глаза→руки (единое зрение).

    Глаза дают бокс Пуска из дескриптора, руки считают центр и
    масштаб. Сухой режим — только рассчитанная точка; моторный —
    настоящий клик, пиксельная сверка и Esc (меню закроется). VRAM
    не танцует: сервер зрения один и не гаснет — в этом и экзамен.

    КРУГ 36 (аудит 337/338): экзамен подчиняется ЗАКОНУ модуля, который
    сам же цитирует: §10.3 — элементы с confidence < 0.6 НЕИЗВЕСТНЫЕ,
    экзамен на неуверенном Пуске не проводится (прежде порог действовал
    для кликов, но не для экзамена); элемент без живого bbox — честный
    отказ, а не KeyError сквозь мёртвую защиту [0,0,0,0]. Уборка Esc
    идёт ЧЕРЕЗ СТРАЖА (прежде _execute звался напрямую — надзор
    обходился). Провалы — в журнал рук: экзамен без следа в аудите
    не экзамен.
    """
    lines = ["ЭКЗАМЕН Р-0 v2 (цепочка глаза→руки, единое зрение)"]
    progress.stage("экзамен Р-0: глаза ищут «Пуск», руки меряют клик…")
    motor = enabled()
    try:
        eyes = _eyes_or_honest()
        d, real, sent = eyes.describe_with_sizes()
    except Exception as e:
        _log_act({"exam": True, "ok": False, "why": str(e)[:120],
                  "mode": "motor" if motor else "dry"})
        return "\n".join(lines + ["не смогла спросить глаза: %s" % e])
    el = None
    weak = None
    for cand in d.get("elements", []):
        if not isinstance(cand, dict) or not cand.get("bbox"):
            continue                      # аудит 338: без бокса не экзаменуем
        t = str(cand.get("text", "")).lower()
        if "пуск" in t or "start" in t:
            if _conf(cand) >= config.HANDS_MIN_CONFIDENCE:
                el = cand
                break
            weak = weak or cand           # §10.3: неуверенное — НЕИЗВЕСТНОЕ
    if el is None:
        why = ("глаза видят похожее на Пуск, но неуверенно (%.2f < %.1f — "
               "§10.3: неуверенное — НЕИЗВЕСТНОЕ). Скажи «посмотри» — "
               "глаза опишут экран точнее, и повтори экзамен"
               % (_conf(weak), config.HANDS_MIN_CONFIDENCE)
               if weak is not None else
               "глаза не нашли Пуск в дескрипторе. Глаза читают: %s. "
               "Открой меню Пуска (клавиша Win) и скажи «руки, экзамен» "
               "ещё раз" % _seen_texts(d))
        _log_act({"exam": True, "ok": False,
                  "why": "неуверенный Пуск" if weak is not None
                  else "Пуск не найден",
                  "mode": "motor" if motor else "dry"})
        return "\n".join(lines + ["экзамен не состоялся: " + why])
    bbox = el.get("bbox")
    cx, cy = frame_center(el)
    x, y = scale_point(cx, cy, real, sent)
    lines.append("глаза: «%s» bbox %s (уверенность %s); центр кадра "
                 "(%d, %d) → экран (%d, %d) при масштабе %.2f×%.2f"
                 % (el.get("text"), bbox, el.get("confidence", "?"),
                    cx, cy, x, y,
                    real[0] / float(sent[0] or 1),
                    real[1] / float(sent[1] or 1)))
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
            _log_act({"exam": True, "ok": False, "why": v.reason,
                      "mode": "motor"})
            return "\n".join(lines + ["СТРАЖ ОТКАЗАЛ: %s" % v.reason])
        before, _, _ = _screenshot()
        lines.append(_execute("click", (x, y)))
        time.sleep(0.8)                  # меню Пуска успевает открыться
        after, _, _ = _screenshot()
        frac = _pixel_diff(before, after)
        # уборка за экзаменом: Esc — ЧЕРЕЗ СТРАЖА (аудит: прежде
        # _execute звался напрямую, надзор обходился)
        v_esc = guard_action("hotkey", ("esc",), real)
        guard.decide(v_esc, {"tool": "ui_action", "task": "экзамен Р-0 "
                                                      "(уборка)", "verb": "esc"})
        if v_esc.allowed():
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
                  "mode": "motor", "ok": "ЦЕПОЧКА" in verdict})
        _lesson("руки-экзамен", "(%d,%d): %s" % (x, y, verdict[:80]))
        return "\n".join(lines)
    except Exception as e:
        _log_act({"exam": True, "ok": False, "why": str(e)[:120],
                  "mode": "motor"})
        return "\n".join(lines + ["ошибка экзамена: %s" % e])
