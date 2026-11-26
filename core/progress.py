# -*- coding: utf-8 -*-
"""core/progress.py — ЭФИР ДОМА: что Марфа делает прямо сейчас.

Урок живого чата (22.11, вечер-4): «ответы очень долгие, надо в чат
прописать время, и вообще не понятно, пока не запустишь консоль, что
вообще происходит». Мозг на CPU думает минутами, глаза — десятками
секунд, а в чате — тишина без часов. Создатель не должен открывать
консоль, чтобы понять, жива ли Марфа: ЧТО происходит и СКОЛЬКО уже
длится — видно в самом чате, живьём.

Эфир — правда одной строкой:
- begin(session): ход начался (панель приняла реплику Создателя);
- stage(text): что происходит СЕЙЧАС — «снимаю экран…», «глаза читают
  экран…», «мозг думает…», «кодер поднимается (VRAM-танец)…»;
- preview(text): ЖИВОЙ ЧЕРНОВИК ответа (стрим мозга, СКОРОСТЬ v1) —
  чат показывает текст ПО МЕРЕ генерации, а не тишину до последнего
  токена; живёт хвостом (последние 400 символов) — важно то, что
  печатается сейчас, а не первые слова минутной давности;
- finish(secs, source): ход завершён — сколько думала и кто отвечал
  (мозг / рефлекс дома / фоллбэк) — штамп ложится в ход диалога;
- snapshot(sid): для /api/progress — занята ли, стадия, секунды хода
  и секунды стадии, превью, последний завершённый ход.

Законы эфира:
- ОН НИКОГДА НЕ РВЁТ РАБОТУ ДОМА: любая поломка проглатывается —
  лучше молчащий эфир, чем упавший ответ;
- stage ВНЕ хода игнорируется (скрипты, тесты, голосовой трек — эфир
  свободен, врать «думаю» некому и незачем);
- ход всегда заканчивается: begin нового хода снимает зависший прошлый
  (панель перезапустили посреди думания — эфир не застревает в «вечно
  занята» навсегда);
- часы — код, а не модель: elapsed считается time.time(), источник —
  из Reply.source; никакие «примерно минута» от LLM в эфир не попадают.

Потокобезопасно: панель многопоточная, /api/progress опрашивается
параллельно думанию. Кто отвечает — source_label по-человечески:
«мозг», «рефлекс дома», «фоллбэк» (урок живого лога 23.11: «дом
(без мозга)» читалось как «безмозглая» — быстрые команды и есть
ум дома, рефлекс организма, а не его отсутствие).
"""
from __future__ import annotations

import threading
import time
from typing import Optional

_lock = threading.Lock()

# текущий ход: {"busy": bool, "sid": str, "stage": str, "preview": str,
#               "draft": str, "t0": float, "stage_t0": float}
_walk = {"busy": False, "sid": "", "stage": "", "preview": "", "draft": "",
         "t0": 0.0, "stage_t0": 0.0}

# последний ЗАВЕРШЁННЫЙ ход — панель показывает его в «сейчас делает»
_last = {"sid": "", "secs": 0.0, "source": "", "ts": ""}

SOURCE_LABELS = {
    "python": "рефлекс дома",
    "brain": "мозг",
    "fallback": "фоллбэк",
    "answercache": "память ответов",   # Ф41 (день-9): мгновенно, честно
}

_START_STAGE = "приняла сообщение, думаю…"

# Ф156 «СТРИМ-КАНАЛ» (круг 25, №15 роадмапа): подписчики эфира. Пока
# ход живёт, каждое событие (стадия, черновик) улетает подписчикам —
# стрим-канал панели отдаёт их браузеру без опроса. Закон эфира
# работает и здесь: поломка подписчика глотается — стрим умер, а ход
# живёт. Список под замком, вызовы — ВНЕ замка (подписчик имеет право
# сам звать эфир, замок не должен зациклиться).
_listeners: list = []


def _notify(kind: str, payload) -> None:
    """Разбудить подписчиков. Вне замка и всегда с бронёй."""
    with _lock:
        subs = list(_listeners)
    for cb in subs:
        try:
            cb(kind, payload)
        except Exception:
            pass          # закон: подписчик не рвёт эфир


def subscribe(cb) -> None:
    """Подписаться на события хода (stage/preview). Повторно — один раз."""
    try:
        with _lock:
            if cb not in _listeners:
                _listeners.append(cb)
    except Exception:
        pass


def unsubscribe(cb) -> None:
    """Отписаться. Нет такого — тихо мимо (закон эфира)."""
    try:
        with _lock:
            if cb in _listeners:
                _listeners.remove(cb)
    except Exception:
        pass


def source_label(source: str) -> str:
    """Кто отвечал — по-человечески. Незнакомый источник — как есть."""
    s = str(source or "").strip()
    return SOURCE_LABELS.get(s, s or "дом")


def reset() -> None:
    """Стереть эфир (тесты; живому дому не нужно — процесс новый)."""
    with _lock:
        _walk.update(busy=False, sid="", stage="", preview="", draft="",
                     t0=0.0, stage_t0=0.0)
        _last.update(sid="", secs=0.0, source="", ts="")


def begin(sid: str = "") -> None:
    """Ход начался. Снимает зависший прошлый ход — эфир не застревает."""
    try:
        with _lock:
            _walk.update(busy=True, sid=str(sid or "")[:64],
                         stage=_START_STAGE, preview="", draft="",
                         t0=time.time(), stage_t0=time.time())
        _notify("stage", _START_STAGE)
    except Exception:
        pass                       # закон: эфир не рвёт работу


def stage(text: str) -> None:
    """Что происходит сейчас. Вне хода — тихо мимо: врать некому."""
    try:
        with _lock:
            if _walk["busy"]:
                _walk["stage"] = str(text or "").strip()[:200] or _START_STAGE
                _walk["stage_t0"] = time.time()
                out = _walk["stage"]
            else:
                return
        _notify("stage", out)
    except Exception:
        pass                       # закон: эфир не рвёт работу


def preview(text: str) -> None:
    """Живой черновик ответа — стрим мозга печатается в чат (СКОРОСТЬ v1).

    Вне хода — тихо мимо. Ф157 (круг 25): эфир хранит ДВА взгляда на
    черновик — «preview» (хвост 400, как при СКОРОСТИ v1: при 6 ток/с
    важно то, что печатается сейчас) и «draft» (полный растущий текст,
    потолок 4000 — ответ 320 ток в него влезает целиком): стрим-канал
    №15 отдаёт браузеру весь ответ, а не хвост, и длинный черновик
    не обрезает начало без честного «…».
    """
    try:
        s = str(text or "")
        with _lock:
            if _walk["busy"] and s.strip():
                _walk["preview"] = ("…" + s[-400:]) if len(s) > 400 else s
                _walk["draft"] = ("…" + s[-4000:]) if len(s) > 4000 else s
                full = _walk["draft"]
            else:
                return
        _notify("preview", full)
    except Exception:
        pass                       # закон: эфир не рвёт работу


def finish(secs: Optional[float] = None, source: str = "") -> None:
    """Ход завершён. secs не передан — эфир считает сам от начала хода."""
    try:
        with _lock:
            if _walk["busy"]:
                took = (float(secs) if secs is not None
                        else time.time() - _walk["t0"])
                _last.update(sid=_walk["sid"], secs=round(max(0.0, took), 1),
                             source=source_label(source),
                             ts=time.strftime("%H:%M:%S"))
            _walk.update(busy=False, sid="", stage="", preview="", draft="",
                         t0=0.0, stage_t0=0.0)
    except Exception:
        pass                       # закон: эфир не рвёт работу


def draft() -> str:
    """Полный черновик текущего хода (Ф157). Вне хода — пусто."""
    try:
        with _lock:
            return _walk["draft"] if _walk["busy"] else ""
    except Exception:
        return ""


def snapshot(sid: str = "") -> dict:
    """Правда эфира для /api/progress (чат и панель).

    mine: ход этой сессии (пустой sid — «спрашиваю вообще», тоже True —
    панель показывает, чем занят дом, без привязки к разговору).
    """
    try:
        with _lock:
            last = dict(_last)
            if not _walk["busy"]:
                return {"busy": False, "sid": "", "stage": "", "preview": "",
                        "draft": "", "elapsed": 0.0, "stage_secs": 0.0,
                        "mine": False, "last": last}
            now = time.time()
            return {
                "busy": True,
                "sid": _walk["sid"],
                "stage": _walk["stage"],
                "preview": _walk["preview"],
                "draft": _walk["draft"],
                "elapsed": round(max(0.0, now - _walk["t0"]), 1),
                "stage_secs": round(max(0.0, now - _walk["stage_t0"]), 1),
                "mine": (not sid) or sid == _walk["sid"],
                "last": last,
            }
    except Exception:
        return {"busy": False, "sid": "", "stage": "", "preview": "",
                "draft": "", "elapsed": 0.0, "stage_secs": 0.0,
                "mine": False, "last": {}}
