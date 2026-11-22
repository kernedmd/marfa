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


def _unique_path(path: Path) -> Path:
    """K3 аудита: путь, не затирающий существующий файл (расписание 23:30 +
    «сохрани себя» в ту же секунду — два архива, а не один обрезанный)."""
    if not path.exists():
        return path
    i = 1
    while True:
        cand = path.with_name("%s_b%d%s" % (path.stem, i, path.suffix))
        if not cand.exists():
            return cand
        i += 1


def _zip_add(z: zipfile.ZipFile, f: Path, files: list, skipped: list) -> None:
    """Один файл в архив. K4 аудита: путь вне дома или OSError — честный
    пропуск со списком, а не поломка архива на середине (частичный zip
    выглядел нормальным и попадал в ротацию как целый)."""
    try:
        arc = f.relative_to(config.HOME_DIR)
    except ValueError:
        arc = Path("_вне_дома") / f.name   # живёт вне дома — но душа едет
    try:
        z.write(f, arc)
        files.append(str(arc))
    except OSError as e:
        skipped.append("%s: %s" % (f.name, e))


def create_backup(now: Optional[dt.datetime] = None) -> dict:
    """Собрать архив души дома. Возвращает {path, size, files, missing, skipped}."""
    now = now or dt.datetime.now()
    backup_dir = _backup_dir()
    backup_dir.mkdir(parents=True, exist_ok=True)
    # K3: секунды в штампе — два бэкапа в одну минуту не затирают друг друга
    stamp = now.strftime("%Y%m%d_%H%M%S")
    path = _unique_path(backup_dir / ("marfa_backup_%s.zip" % stamp))
    # K4: собираем во временный файл, на полку ложим ЦЕЛИКОВЫЙ архив
    tmp = path.with_suffix(".tmp")

    files: list[str] = []
    missing: list[str] = []
    skipped: list[str] = []
    try:
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
            for src, title in _soul():
                src = Path(src)
                if src.is_symlink():
                    # M8: симлинк — дверь к 18 ГБ весов; «модели не ездят» — обещание
                    skipped.append(title + " (симлинк — тело, не душа)")
                    continue
                if not src.exists():
                    missing.append(title)
                    continue
                if src.is_dir():
                    links = 0
                    for f in sorted(src.rglob("*")):
                        if f.is_symlink():
                            links += 1
                            continue
                        if f.is_file():
                            _zip_add(z, f, files, skipped)
                    if links:
                        skipped.append("%s: пропущено симлинков — %d "
                                       "(тело, не душа)" % (title, links))
                else:
                    _zip_add(z, src, files, skipped)
    except Exception:
        try:
            tmp.unlink()          # фатальная поломка — недоделанный архив
        except OSError:           # не остаётся на полке и в ротации
            pass
        raise
    tmp.replace(path)
    _rotate()
    return {"path": path, "size": path.stat().st_size,
            "files": files, "missing": missing, "skipped": skipped}


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
            target = trash / old.name
            if target.exists():
                # M9: закон дома — ничего не удаляется насовсем: прошлый
                # архив с тем же именем не перезаписываем, а живёт рядом
                target = trash / ("%s_%s%s" % (
                    old.stem, dt.datetime.now().strftime("%Y%m%d_%H%M%S"),
                    old.suffix))
            old.replace(target)
            moved.append(old.name)
        except OSError:
            pass                      # не переехал — переживём: пусть живёт
    return moved


def render(report: dict) -> str:
    """Отчёт простым языком: куда легло, что внутри, чего не было
    и что не взяли — всё честно, без молчаливых пропусков."""
    kb = report["size"] / 1024
    lines = ["Сохранила себя: %s" % report["path"],
             "Внутри %d файлов, %.1f КБ." % (len(report["files"]), kb)]
    if report.get("skipped"):
        lines.append("Не взяла (честно): %s." % ", ".join(report["skipped"]))
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
