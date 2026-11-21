# -*- coding: utf-8 -*-
r"""scripts/live_voice_resolution.py — РЕЗОЛЮЦИЯ СОЗДАТЕЛЯ (кнопка 89).

Гейт §5 доктрины: живой язык Марфы включается не кодом, а волей
Создателя. Батарея мозга 21.11.2026 дала вердикт (Q4_K_M: факты 13/13
и честность 2/2 в двух прогонах, речь чистая — docs/ВЕРДИКТ_БАТАРЕИ.md),
и этот скрипт записывает резолюцию в data\live_voice.json.

Сразу после записи, если мозг жив, собирает сегодняшний дневник с
«Живым рассказом» и печатает его в консоль: Создатель видит первый
живой текст Марфы своими глазами в момент включения. Мозг спит —
честно говорит, что рассказ будет в вечернем дневнике (21:00).

Запуск из корня дома (кнопка 89 делает это сама):
    venv\Scripts\python.exe scripts\live_voice_resolution.py
Выход: код 0 — резолюция записана (рассказ — по обстоятельствам).
"""
from __future__ import annotations

import datetime as dt
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # корень дома

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from core import config  # noqa: E402

VERDICT_BASIS = ("батарея 21.11.2026: Q4_K_M, факты 13/13 x2, "
                 "честность 2/2 x2, речь чистая")


def write_resolution() -> dict:
    """Записать волю Создателя в data/live_voice.json (атомарно)."""
    rec = {"enabled": True,
           "since": dt.datetime.now().isoformat(timespec="seconds"),
           "basis": VERDICT_BASIS}
    p = Path(config.LIVE_VOICE_FILE)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(rec, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    tmp.replace(p)
    return rec


def _extract_voice(diary_text: str) -> str:
    """Вырезать раздел «Живой рассказ» из готового дневника."""
    m = re.search(r"## Живой рассказ\n(.*?)(?=\n## |\Z)", diary_text, re.S)
    return m.group(1).strip() if m else ""


def main(argv=None) -> int:
    print("=" * 60)
    print("МАРФА — ЖИВОЙ ГОЛОС: резолюция Создателя")
    print("=" * 60)

    rec = write_resolution()
    print("[1] Резолюция записана: data\\live_voice.json")
    print("    основание: %s" % rec["basis"])

    print("[2] Смотрю на мозг ...")
    brain_ok = False
    try:
        from core.brain import BrainClient
        brain_ok = BrainClient().health()
    except Exception:
        brain_ok = False

    if not brain_ok:
        print("    мозг сейчас спит — не страшно.")
        print("    Рассказ появится в вечернем дневнике сам (расписание, 21:00),")
        print("    или скажи Марфе «подведи день», когда мозг проснётся.")
        print("[3] Готово. Живой язык включён.")
        return 0

    print("    мозг жив — собираю сегодняшний дневник с рассказом ...")
    try:
        from core.diary import Diary
        text = Diary().build_day()
    except Exception as e:
        print("    дневник не собрался: %s" % e)
        print("[3] Резолюция записана, рассказ — вечером по расписанию.")
        return 0

    voice = _extract_voice(text)
    print("[3] Первый живой рассказ Марфы:")
    print()
    print(voice if voice else "(мозг был занят — рассказ не сложился; "
          "вечером распишу день заново)")
    print()
    print("Мысли по команде: «поразмышляй». Дневник: «подведи день».")
    return 0


if __name__ == "__main__":
    sys.exit(main())
