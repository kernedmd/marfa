# -*- coding: utf-8 -*-
r"""scripts/clean_home.py — анти-мусор дома: разбор наследия v9.3. v1.0

Протокол синхронизации v1.2, раздел 8: у файла одно имя, одно место,
одна история. Рабочая копия — источник правды; остальное — мусор.

Правила:
  1. Корень дома: точный список устаревшего (огрызки команд, старые
     архивы и кнопки, лекари больной эпохи v9.3, старый канон и пуш) —
     переносится в _trash\ДАТА\.
  2. ROADMAP_30.md в корне — только если каноническая копия уже живёт
     в docs\ (иначе остаётся: она единственная).
  3. Пустышки evolution\, growth\ (одни __init__.py) — в _trash.
  4. По всему дереву, кроме тяжёлых каталогов: __pycache__, *.pyc,
     *.bak, *_broken*, .pytest_cache — в _trash.
  5. Только ДОКЛАД, без переноса: *.bundle вне incoming\ и outgoing\
     (это история — перенеси в incoming\ или удали сам), вложенная
     копия marfa\.

Гарантии: ничего не удаляет насовсем — только перенос в _trash\ (каталог
в .gitignore). Не трогает модели, рантайм, data, logs, .env, docs, core,
safety, sensors, web, tests, scripts, incoming, outgoing, живые кнопки.

Запуск (кнопка Чистка_Дома.bat, шаг 0d кнопки 80_sync, или руками):
    python scripts\clean_home.py            план + вопрос [y/n]
    python scripts\clean_home.py --yes      сразу перенести
    python scripts\clean_home.py --dry      только показать план
Дом по умолчанию — родитель scripts\; переопределяется MARFA_HOME (тесты).
"""
from __future__ import annotations

import os
import shutil
import sys
from datetime import datetime
from fnmatch import fnmatch
from pathlib import Path

ROOT_JUNK_FILES = [
    # огрызки сломанных команд
    "40", "with", "main",
    # старые вложенные архивы
    "marfa-src.zip", "marfa.zip",
    # кнопки v9.3 (заменены Старт/Стоп/Статус/Обновить)
    "start_marfa_all.bat", "stop_marfa_all.bat", "Забрать_Марфу.bat",
    # лекари больной эпохи (до доктрины v1.0)
    "architect.py", "auto_heal.py", "fix.py", "fix_brain.py", "heal.py",
    "make_chat.py", "real_doctor.py", "setup_chat.py",
    "start_healthy_brain.py",
    # старый канон и старый пуш (канон: docs\, пуш: кнопка 80_sync)
    "marfa.md", "marfa_github_upload.ps1", "ИНСТРУКЦИЯ_ПУШ_В_GITHUB.md",
]
ROOT_JUNK_DIRS = ["_backup_heal"]
TRIVIAL_DIRS = ["evolution", "growth"]
PATTERN_FILES = ["*.pyc", "*.bak", "*_broken*"]
PATTERN_DIRS = {"__pycache__", ".pytest_cache"}
# тяжёлое и рантайм — даже не сканируем
SKIP_DIRS = {".git", "_trash", "models", "venv", "python311", "tools",
             "data", "logs", "llama.cpp", "downloads", "incoming",
             "outgoing", "node_modules", "marfa"}


def home_dir() -> Path:
    """Дом: MARFA_HOME или родитель scripts\\ (по месту скрипта)."""
    return Path(os.environ.get("MARFA_HOME")
                or Path(__file__).resolve().parents[1])


def _is_trivial(d: Path) -> bool:
    """Каталог-пустышка: внутри только __init__.py (или совсем ничего)."""
    for p in d.rglob("*"):
        if p.is_file() and p.name != "__init__.py":
            return False
    return True


def scan(root: Path):
    """Вернуть (что переносить, о чём только доложить)."""
    moves, reports = [], []

    for name in ROOT_JUNK_FILES:
        p = root / name
        if p.is_file():
            moves.append(p)
    for name in ROOT_JUNK_DIRS:
        p = root / name
        if p.is_dir():
            moves.append(p)

    roadmap = root / "ROADMAP_30.md"
    if roadmap.is_file() and (root / "docs" / "ROADMAP_30.md").is_file():
        moves.append(roadmap)  # канон приехал в docs\ — корневая копия лишняя

    for name in TRIVIAL_DIRS:
        d = root / name
        if d.is_dir() and _is_trivial(d):
            moves.append(d)

    for dirpath, dirnames, filenames in os.walk(root):
        here = Path(dirpath)
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for d in list(dirnames):
            if d in PATTERN_DIRS:
                moves.append(here / d)
                dirnames.remove(d)
        for f in filenames:
            if any(fnmatch(f, pat) for pat in PATTERN_FILES):
                moves.append(here / f)

    for p in root.glob("*.bundle"):
        reports.append((p, "bundle вне incoming\\outgoing — история; "
                           "перенеси в incoming\\ (архитектору) или удали"))
    return moves, reports


def _size(p: Path) -> int:
    if p.is_file():
        try:
            return p.stat().st_size
        except OSError:
            return 0
    return sum(f.stat().st_size for f in p.rglob("*") if f.is_file())


def apply_moves(root: Path, moves):
    r"""Перенос в _trash\ДАТА\ с сохранением относительных путей."""
    trash = root / "_trash" / datetime.now().strftime("%Y-%m-%d")
    done, errors = [], []
    for p in moves:
        target = trash / p.relative_to(root)
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                errors.append("%s (в _trash уже есть)" % p.name)
                continue
            shutil.move(str(p), str(target))
            done.append(p)
        except (OSError, shutil.Error) as e:
            errors.append("%s (%s)" % (p.name, e))
    return done, errors


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    yes, dry = "--yes" in argv, "--dry" in argv
    root = home_dir()
    print("=" * 60)
    print("МАРФА — чистка дома (v1.0): мусор уезжает в _trash, не удаляется")
    print("=" * 60)
    moves, reports = scan(root)
    if not moves and not reports:
        print("Мусора не найдено — дом чист.")
        return 0
    if moves:
        print("Перенести в _trash (%d):" % len(moves))
        for p in moves:
            print("   -", p.relative_to(root))
        print("объём: %.1f КБ" % (sum(_size(p) for p in moves) / 1024))
    if reports:
        print("Только доклад (не трогаю):")
        for p, msg in reports:
            print("   ?", p.relative_to(root), "—", msg)
    if dry or not moves:
        return 0
    if not yes:
        answer = input("Перенести? [y/N] ").strip().lower()
        if answer not in ("y", "yes", "д", "да"):
            print("Отменено.")
            return 0
    done, errors = apply_moves(root, moves)
    print("Перенесено: %d" % len(done))
    for e in errors:
        print("   [!]", e)
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
