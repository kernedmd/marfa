# -*- coding: utf-8 -*-
"""core/seal.py — Ф46 «ПЕЧАТЬ ДНЯ» (день-9, 24.11): №2 триажа
(«хеш-цепочка логов») в честном упрощении.

Полная хеш-цепочка на каждую строку логов — тяжёлая броня для домашнего
организма; печать решает ту же задачу по-домашнему: перед ночным бэкапом
(23:25, за пять минут до него) дом ставит ПЕЧАТЬ — sha256-манифест души
и быта (правила, память, дневники, заметки, разговоры…). Утром
«печати целы?» сверяет: файл менялся после печати — честно назван,
пропал — честно назван, цел — цел.

Меняться — не значит нарушать: день шёл, заметки писались. Печать не
судья, а свидетель: она говорит ЧТО и КОГДА, а «нормально ли это» —
решает Создатель (ночью дом спит, и меняться там нечему — вот ночная
печать и есть страж тишины). Печать можно поставить и днём руками —
«печать»; история последних печатей — «печати».
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import time
from pathlib import Path

from core import config

MAX_FILES = 500          # потолок файлов в печати: душа дома, не склад
HISTORY_CAP = 30         # сколько печатей помнит дом


def _file() -> Path:
    """data/seals.json — ЛЕНИВО от DATA_DIR (закон песочницы)."""
    return Path(config.DATA_DIR) / "seals.json"


def _targets() -> list[tuple[Path, str]]:
    """Душа и быт — что защищает печать. Пути ленивые: песочница теста
    и живой дом получают каждый свою печать. Файла может не быть —
    попадёт в «честно не было» при постановке."""
    d = lambda name: Path(config.DATA_DIR) / name  # noqa: E731
    return [
        (d("rules.json"), "правила дома (№40)"),
        (d("memory"), "память"),
        (d("diary"), "дневники и мысли"),
        (d("dialog"), "разговоры"),
        (d("notes.json"), "заметки (Ф11)"),
        (d("habits.json"), "привычки (Ф15)"),
        (d("shopping.json"), "покупки (Ф12)"),
        (d("birthdays.json"), "дни рождения (Ф16)"),
        (d("expenses.json"), "расходы (Ф14)"),
        (d("worklog.json"), "трекер времени (Ф13)"),
        (d("mood.json"), "настроение (Ф35)"),
    ]


def _walk(root: Path) -> list[Path]:
    """Файлы цели: сам файл ИЛИ рекурсивно каталог. Битые симлинки и
    недоступное — молча мимо: печать защищает душу, а не воюет с ОС."""
    if root.is_file():
        return [root]
    if not root.is_dir():
        return []
    out: list[Path] = []
    try:
        for p in sorted(root.rglob("*")):
            if p.is_file():
                out.append(p)
                if len(out) >= MAX_FILES:
                    break
    except OSError:
        pass
    return out


def _fingerprint(path: Path) -> dict:
    """size + sha256 — паспорт файла для печати."""
    h = hashlib.sha256()
    size = 0
    with path.open("rb") as f:
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            size += len(chunk)
            h.update(chunk)
    return {"size": size, "sha256": h.hexdigest()[:16]}


def _load() -> list[dict]:
    try:
        rec = json.loads(_file().read_text(encoding="utf-8"))
        return [s for s in rec if isinstance(s, dict)] \
            if isinstance(rec, list) else []
    except (OSError, ValueError):
        return []


def _save(seals: list[dict]) -> None:
    try:
        _file().parent.mkdir(parents=True, exist_ok=True)
        _file().write_text(
            json.dumps(seals, ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError:
        pass  # печать не записалась — день всё равно жил честно


def place() -> str:
    """«печать» — поставить печать сейчас. Расписание зовёт в 23:25."""
    files: dict[str, dict] = {}
    labels: dict[str, str] = {}
    missing: list[str] = []
    for root, label in _targets():
        found = _walk(root)
        if not found:
            if root.exists():
                files[str(root.name)] = {"size": 0, "sha256": "пусто"}
            else:
                missing.append(label)
            continue
        for p in found:
            try:
                files[str(p.relative_to(Path(config.DATA_DIR)))] = \
                    _fingerprint(p)
                labels[str(p.relative_to(Path(config.DATA_DIR)))] = label
            except (OSError, ValueError):
                continue
    seals = _load()
    seals.append({
        "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
        "files": files,
        "labels": labels,
    })
    if len(seals) > HISTORY_CAP:
        seals = seals[-HISTORY_CAP:]
    _save(seals)
    out = ["ПЕЧАТЬ ПОСТАВЛЕНА (%s): %d файлов души под защитой"
           % (time.strftime("%d.%m %H:%M"), len(files))]
    if missing:
        out.append("честно не было: %s" % ", ".join(missing))
    out.append("сверка — «печати целы?» (утром: ночь должна быть тихой)")
    return "\n".join(out)


def verify() -> str:
    """«печати целы?» — сверить живые файлы с последней печатью."""
    seals = _load()
    if not seals:
        return ("печатей нет — дому не с чем сверяться. Поставить: "
                "«печать» (или дождись 23:25 — печать перед сном дома)")
    last = seals[-1]
    stamped = last.get("files") if isinstance(last.get("files"), dict) else {}
    labels = last.get("labels") if isinstance(last.get("labels"), dict) else {}
    intact = changed = gone = 0
    names: list[str] = []
    for rel, fp in sorted(stamped.items()):
        path = Path(config.DATA_DIR) / rel
        if not fp or fp.get("sha256") == "пусто":
            continue
        if not path.exists():
            gone += 1
            if len(names) < 5:
                names.append("пропал: %s (%s)" % (rel, labels.get(rel, "?")))
            continue
        try:
            live = _fingerprint(path)
        except OSError:
            continue
        if live == fp:
            intact += 1
        else:
            changed += 1
            if len(names) < 5:
                names.append("менялся: %s (%s)" % (rel, labels.get(rel, "?")))
    lines = ["ПЕЧАТИ (последняя %s): целы %d · менялись %d · пропали %d"
             % (str(last.get("ts", "?"))[:16], intact, changed, gone)]
    lines.extend("  · " + n for n in names)
    if changed + gone > 5:
        lines.append("  … и ещё %d" % (changed + gone - 5))
    if changed == 0 and gone == 0:
        lines.append("душа дома не менялась с печати — всё спокойно")
    else:
        lines.append("меняться — не значит нарушать (день шёл, записи "
                     "росли); печать называет что и когда — решает Создатель")
    return "\n".join(lines)


def history() -> str:
    """«печати» — история печатей дома."""
    seals = _load()
    if not seals:
        return "печатей ещё не было — первая встанет в 23:25 или по «печать»"
    out = ["ПЕЧАТИ ДОМА (последние %d):" % len(seals)]
    for s in seals[-8:]:
        files = s.get("files")
        n = len(files) if isinstance(files, dict) else 0
        out.append("  · %s — %d файлов" % (str(s.get("ts", "?"))[:16], n))
    return "\n".join(out)


def tick() -> str:
    """Работа расписания (23:25): печать перед сном, для журнала стремления."""
    return place()
