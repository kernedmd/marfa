# -*- coding: utf-8 -*-
r"""scripts/fix_brain_cmd.py — кнопка 92 «ремонт мозга» (день-8, 23.11).

Причина рождения: терапия §15 (22.11, вечер) вписала в start_marfa.json
хвост «--jinja --chat-template-kwargs "{\"enable_thinking\": false}\"».
Кавычки в этой команде переживают три слоя разбора (JSON → Popen(shell)
→ argv), и сервер получает {enable_thinking: false} БЕЗ кавычек —
невалидный JSON — и умирает на старте. Живой мозг маскировал бомбу
до первого «Стоп → Старт» (23.11, утро): чат Создателя ответил
«мозг недоступен (WinError 10061)», а консоль мозга закрылась, не
успев ничего показать.

Кнопка:
- (1) ЛЕЧИТ команду в start_marfa.json: ядовитый хвост снимается,
      путь модели Создателя сохраняется (лечение — в
      start_marfa._heal_brain_cmd, старт дома лечит тем же лекарством);
- (2) поднимает мозг, если он не жив: отдельная консоль (как старт
      дома), честное ожидание «ожил» до 120 с — не ожил, говорит
      смотреть консоль, а не молчит надеждой;
- идемпотентна: здоровый конфиг не трогается, живой мозг не
  перезапускается (закон старта дома: живого слугу не трогаем).

Запуск: scripts\92_brain_fix.bat (обёртка с venv и pause).
Тесты: tests/test_fix_brain_cmd.py.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import start_marfa as sm  # noqa: E402  (дом: старт и лечение — один закон)

BRAIN_PORT = 8082
BRAIN_HEALTH = "/health"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="ремонт команды мозга + подъём")
    ap.add_argument("--start", action="store_true",
                    help="поднять мозг, если он не жив (кнопка зовёт так)")
    ap.add_argument("--config", default=str(sm.CONFIG_FILE),
                    help="путь к start_marfa.json")
    args = ap.parse_args(argv)
    cfg_path = Path(args.config)

    print("=== Марфа: ремонт мозга (кнопка 92) ===")
    raw_before = ""
    try:
        raw_before = (json.loads(cfg_path.read_text(encoding="utf-8"))
                      .get("brain_cmd") or "")
    except Exception:
        pass                       # файла нет/битый — ensure_config создаст

    cfg = sm.ensure_config(cfg_path)
    cmd = (cfg.get("brain_cmd") or "").strip()
    if raw_before and raw_before.strip() != cmd:
        print("было:  " + raw_before.strip())
        print("стало: " + cmd)
    else:
        print("команда мозга здорова (кавычек и ядовитых хвостов нет)")

    if not args.start:
        return 0

    if sm._alive(BRAIN_PORT, BRAIN_HEALTH):
        print("мозг уже жив на порту %d — не трогаю (живого слугу дом "
              "не перезапускает)" % BRAIN_PORT)
        return 0

    if not cmd:
        print("нет команды мозга — впиши brain_cmd в " + cfg_path.name)
        return 1

    print("поднимаю мозг в отдельной консоли (30B на CPU — десятки "
          "секунд до «жив»)...")
    sm._spawn(cmd)
    if sm._wait(BRAIN_PORT, BRAIN_HEALTH, 120):
        print("мозг ОЖИЛ — карточка «Мозг» на панели 5001 подтвердит")
        sm._log("кнопка 92: мозг поднят после ремонта команды (день-8)")
        return 0
    print("НЕ ожил за 120 с — посмотри консоль мозга: если закрылась "
          "сразу, команду отвергла сборка сервера (не хватает флага — "
          "скажи архитектору, какой); панель → карточка «Мозг»")
    return 1


if __name__ == "__main__":
    sys.exit(main())
