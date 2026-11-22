# -*- coding: utf-8 -*-
"""core/people.py — КРУГ «ЗНАКОМСТВА» (Ф2, 23.11): дом знает, как тебя зовут.

Урок живого лога: Илья ждёт от домашнего организма памяти о СЕБЕ —
«меня зовут…» не должно улетать в мозг и растворяться в общих словах.
Имя живёт в data\\people.json (переживает рестарт и RAG) и дублируется
в память дома с тегом «знакомство» (для «вспомни»). Битый файл — не
крах: дом честно говорит, что имени не знает.

Создатель по умолчанию — Илья (ЯДРО личности); «меня зовут X» меняет
СПИКЕРА (кто сейчас говорит с домом), а не Создателя канона.
"""
from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path
from typing import Optional

from core import config

# Честное имя: буквы (в т.ч. кириллица), дефис, 2-30 знаков
_NAME_RX = re.compile(r"^[A-Za-zА-Яа-яЁё][A-Za-zА-Яа-яЁё\- ]{1,29}$")


def people_file() -> Path:
    """Где живёт знакомство: data\\people.json."""
    return Path(config.DATA_DIR) / "people.json"


def _load() -> dict:
    try:
        rec = json.loads(people_file().read_text(encoding="utf-8"))
        return rec if isinstance(rec, dict) else {}
    except Exception:
        return {}


def _save(rec: dict) -> None:
    people_file().parent.mkdir(parents=True, exist_ok=True)
    people_file().write_text(json.dumps(rec, ensure_ascii=False, indent=1),
                             encoding="utf-8")


def get_name() -> Optional[str]:
    """Имя спикера; нет файла/поля — None, не исключение."""
    name = str(_load().get("name") or "").strip()
    return name or None


def met_on() -> Optional[str]:
    """Когда познакомились (дата первой встречи)."""
    return str(_load().get("met") or "").strip() or None


def set_name(raw_name: str, memory=None) -> str:
    """«меня зовут X»: записать имя спикера + в память дома.

    Имя чистится (регистр, края) и проверяется по-человечески:
    цифры и мусор — не имя. Перезапись честна: люди поправляются.
    """
    name = re.sub(r"\s+", " ", str(raw_name or "").strip())
    if not _NAME_RX.match(name):
        return ("«%s» — не похоже на имя (буквы и дефис, 2-30 знаков). "
                "Скажи ещё раз: «меня зовут <имя>»" % name[:40])
    name = name.title()
    old = get_name()
    rec = _load()
    rec["name"] = name
    if not rec.get("met"):
        rec["met"] = dt.date.today().strftime("%d.%m.%Y")
    _save(rec)
    if memory is not None:
        try:
            memory.remember("Создателя зовут %s" % name,
                            tags=["знакомство"], importance=4.0)
        except Exception:
            pass          # RAG не рвёт знакомство: файл уже записан
    if old and old != name:
        return ("Запомнила: теперь тебя зовут %s (было %s). Приятно, %s."
                % (name, old, name))
    return ("Очень приятно, %s! Запомнила навсегда — data хранит имена "
            "лучше нейронов." % name)


def forget_name() -> str:
    """«забудь моё имя»: честная чистка — имя стирается из файла."""
    if get_name() is None:
        return "твоего имени у меня и не было"
    rec = _load()
    rec.pop("name", None)
    rec.pop("met", None)
    _save(rec)
    return ("забыла имя. Напомнишь — скажи «меня зовут <имя>»")


def who_am_i(memory=None, eyes_face: Optional[str] = None) -> str:
    """«кто я»: всё, что дом знает о спикере, из первых рук.

    Имя (файл) + зрительная память (передаёт глаза) + воспоминания
    (RAG по тегу «знакомство»). Каждая часть честна отдельно: чего
    нет — того нет, без выдумок «мы давно знакомы».
    """
    name = get_name()
    met = met_on()
    lines = []
    if name:
        lines.append("Ты — %s%s." % (name, (" (знакомы с %s)" % met)
                                     if met else ""))
    else:
        lines.append("Имени твоего я пока не знаю — скажи «меня зовут "
                     "<имя>», запомню навсегда.")
    if eyes_face:
        lines.append("Зрительно помню: " + eyes_face)
    if memory is not None:
        try:
            found = memory.recall("зовут знакомство создатель", top_k=3)
        except Exception:
            found = []
        extra = [str(r.get("text", "")) for r in found or []
                 if isinstance(r, dict) and r.get("text")]
        for piece in extra[:2]:
            if name and name.lower() in piece.lower():
                lines.append("Из памяти: " + piece)
    return "\n".join(lines)
