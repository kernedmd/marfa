# -*- coding: utf-8 -*-
r"""core/backup.py — №23 «СОХРАНИ СЕБЯ»: бэкап души дома.

Вторая жизнь дублёта: доктрина Создателя, память, дневники с мыслями,
вопросы, разговоры, уроки эволюционера — всё, что делает Марфу Марфой, —
укладывается в один zip с датой в data/backup/. Модели, venv и логи
не ездят: это тело, а бэкап — душа (и 113 ГБ в data не тащим).

- команда Создателя: «сохрани себя» / «бэкап» — прямо сейчас;
- расписание Ф75: каждый день в 23:30, после вечернего дневника;
- ротация: живёт BACKUP_KEEP последних архивов, старшие переезжают
  в _trash/backup_old/ — по правилу дома ничего не удаляется насовсем.

Чистый stdlib (zipfile). Выход: путь к архиву и честный список того,
что вошло и чего не было.
"""
from __future__ import annotations

import datetime as dt
import zipfile
from pathlib import Path
from typing import Optional

from core import config

BACKUP_KEEP = 14               # столько свежих архивов живёт в data/backup/


def _backup_dir() -> Path:
    return Path(config.DATA_DIR) / "backup"


def _trash_dir() -> Path:
    return Path(config.HOME_DIR) / "_trash" / "backup_old"


def _soul() -> list:
    """(откуда, что это) — только душа дома; пути ЛЕНИВО из закона
    дома (config), чтобы tmp-дом тестов был честен. Файла может не
    быть — попадёт в «честно не было»."""
    d = lambda name: Path(config.DATA_DIR) / name  # noqa: E731
    return [
        (Path(config.DOCTRINE_FILE), "доктрина Создателя"),
        (Path(config.QUESTIONS_FILE), "вопросы Илье"),
        (d("memory"), "память"),
        (Path(config.DIARY_DIR), "дневники и мысли"),
        (d("dialog"), "разговоры"),
        (d("evolution"), "журнал уроков"),
        (d("screenshots"), "запомненные экраны"),
        (d("librarian_state.json"), "полка библиотекаря"),
        (Path(config.LIVE_VOICE_FILE), "резолюция живого языка"),
    ]


def create_backup(now: Optional[dt.datetime] = None) -> dict:
    """Собрать архив души дома. Возвращает {path, size, files, missing}."""
    now = now or dt.datetime.now()
    backup_dir = _backup_dir()
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = now.strftime("%Y%m%d_%H%M")
    path = backup_dir / ("marfa_backup_%s.zip" % stamp)

    files: list[str] = []
    missing: list[str] = []
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for src, title in _soul():
            src = Path(src)
            if not src.exists():
                missing.append(title)
                continue
            if src.is_dir():
                for f in sorted(src.rglob("*")):
                    if f.is_file():
                        z.write(f, f.relative_to(config.HOME_DIR))
                        files.append(str(f.relative_to(config.HOME_DIR)))
            else:
                z.write(src, src.relative_to(config.HOME_DIR))
                files.append(str(src.relative_to(config.HOME_DIR)))
    _rotate()
    return {"path": path, "size": path.stat().st_size,
            "files": files, "missing": missing}


def _rotate(keep: int = BACKUP_KEEP) -> list:
    """Свежие живут, старшие — в _trash/backup_old (не насовсем)."""
    try:
        archives = sorted(_backup_dir().glob("marfa_backup_*.zip"))
    except OSError:
        return []
    moved = []
    for old in archives[:-keep] if keep > 0 else archives:
        try:
            trash = _trash_dir()
            trash.mkdir(parents=True, exist_ok=True)
            old.replace(trash / old.name)
            moved.append(old.name)
        except OSError:
            pass                      # не переехал — переживём: пусть живёт
    return moved


def render(report: dict) -> str:
    """Отчёт простым языком: куда легло, что внутри, чего не было."""
    kb = report["size"] / 1024
    lines = ["Сохранила себя: %s" % report["path"],
             "Внутри %d файлов, %.1f КБ." % (len(report["files"]), kb)]
    if report["missing"]:
        lines.append("Чего не было (честно): %s."
                     % ", ".join(report["missing"]))
    else:
        lines.append("Душа дома целиком: доктрина, память, дневники, "
                     "разговоры, уроки.")
    return "\n".join(lines)


def tick() -> str:
    """Точка входа для расписания Ф75 (ежедневно, 23:30)."""
    report = create_backup()
    return "бэкап: %d файлов, %.0f КБ" % (len(report["files"]),
                                          report["size"] / 1024)
