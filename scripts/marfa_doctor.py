# -*- coding: utf-8 -*-
r"""scripts/marfa_doctor.py — кнопка 84: доктор дома одной кнопкой.

Осмотр всего дома простым языком (порты, сердца, venv, веса, .env, диск,
канон) и — по желанию Создателя — лечение мёртвых слуг командами старта
дома. Ничего не выдумывает: лечить нечем — так и говорит.

Запуск из корня дома (кнопка делает это сама):
    venv\Scripts\python.exe scripts\marfa_doctor.py           # осмотр
    venv\Scripts\python.exe scripts\marfa_doctor.py --heal    # + лечение
Выход: 0 — осмотр прошёл (здоровье дома — в тексте отчёта).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # корень дома

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from core import doctor  # noqa: E402


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    heal_mode = "--heal" in argv

    print("=" * 60)
    print("МАРФА — ДОКТОР ДОМА")
    print("=" * 60)
    report = doctor.check_all()
    print()
    print(doctor.render(report))
    print()

    dead = [sid for sid, c in report["checks"].items()
            if not c["ok"] and sid in ("brain", "eyes", "panel",
                                       "ears", "drive")]
    if not dead:
        print("Лечить некого — дом в сборе.")
        return 0

    print("Мёртвые слуги: %s" % ", ".join(
        doctor._NAMES.get(s, s) for s in dead))
    if not heal_mode:
        print("Лечение — кнопкой ещё раз (она спросит) или командой")
        print("«доктор» в чате. Автодоктор лечит сам — раз в 5 минут.")
        return 0

    answer = input("Полечить? (y — да, иначе нет): ").strip().lower()
    if answer not in ("y", "yes", "д", "да"):
        print("Отменил — никого не трогаю.")
        return 0

    print()
    for line in doctor.heal(dead):
        print("  " + line)
    print()
    print("Поднял. Разогрев зависит от слуги: панель — секунды,")
    print("мозг — минуты. Проверь: «статус» в чате или кнопка Статус.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
