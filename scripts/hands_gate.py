# -*- coding: utf-8 -*-
r"""scripts/hands_gate.py — кнопка 91: резолюция Создателя на моторику рук.

Воля Создателя живёт в data/ (в git не попадает) — как резолюция живого
языка (кнопка 89). Пишет/удаляет data\hands_enabled.json:
  есть файл  — руки ИСПОЛНЯЮТ действия (клики, печать) под стражем;
  нет файла  — сухой режим: руки называют точку, но мышь не трогают.

Руки v2 «единое зрение» (ТЗ_Руки_v2): своей модели у рук нет — они
исполняют координаты глаз (Qwen2.5-VL, порт 8083), поэтому проверять
модель в чулане не нужно; нужен живой сенсор зрения. Код дома НИКОГДА
не пишет этот файл сам — только эта кнопка по живому выбору Создателя.
Перед включением рекомендуется экзамен Р-0: «руки, экзамен» в чате —
цепочка глаза→руки на кнопке Пуск.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core import config  # noqa: E402


def main() -> int:
    print("=" * 60)
    print("МАРФА — РУКИ: резолюция Создателя на моторику")
    print("=" * 60)
    enabled_now = config.HANDS_ENABLED_FILE.is_file()
    print("Сейчас: %s" % ("моторика ВКЛЮЧЕНА (руки кликают по-настоящему)"
                          if enabled_now
                          else "сухой режим (руки называют точку, мышь не трогают)"))
    print("Руки v2 — на координатах глаз: своя модель не нужна,")
    print("нужен живой сенсор зрения 8083 (глаза должны быть запущены).")
    print()
    print("Перед включением рекомендую экзамен цепочки глаза→руки:")
    print("  в чате Марфы: «руки, экзамен» — Р-0 из ТЗ Рук v2.")
    print("  В сухом режиме он рассчитает точку клика; после включения")
    print("  моторики — кликнет и сверит пиксели (меню закроет Esc).")
    print()
    print("[1] включить моторику (реальные клики и печать)")
    print("[2] выключить (сухой режим)")
    print("[3] ничего не менять")
    try:
        choice = input("выбор: ").strip()
    except (EOFError, KeyboardInterrupt):
        choice = "3"
    if choice == "1":
        config.HANDS_ENABLED_FILE.parent.mkdir(parents=True, exist_ok=True)
        rec = {"ts": dt.datetime.now().isoformat(timespec="seconds"),
               "resolution": "моторика рук включена Создателем (кнопка 91)",
               "basis": "ТЗ_Руки_v2 (единое зрение); экзамен Р-0 "
                        "рекомендован до первого настоящего клика"}
        tmp = config.HANDS_ENABLED_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(rec, ensure_ascii=False, indent=1),
                       encoding="utf-8")
        tmp.replace(config.HANDS_ENABLED_FILE)
        print("\nМоторика ВКЛЮЧЕНА. Руки исполняют действия под стражем:")
        print(" whitelist клавиш, лимит печати, клики только в пределах экрана.")
        print(" Выключить — снова эта кнопка [2] или удалить "
              "data\\hands_enabled.json.")
    elif choice == "2":
        try:
            config.HANDS_ENABLED_FILE.unlink()
            print("\nМоторика выключена — руки снова в сухом режиме.")
        except FileNotFoundError:
            print("\nМоторика и так была выключена (файла нет).")
    else:
        print("\nНичего не меняю.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
