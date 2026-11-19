# -*- coding: utf-8 -*-
r"""safety/log_audit.py — Ф81 «АУДИТ ЛОГОВ» (ТЗ 3.7, П1).

Логи — единственный источник правды (6.6). СТРАЖ пишет hash-chain (sha256,
каждая запись сцеплена с предыдущей). Этот модуль доказывает целостность:
подмена/удаление/вставка записи видны по разрыву цепочки.

Запуск: python -m safety.log_audit [путь_к_логу]   (по умолчанию logs\guard_log.jsonl)
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from core import config
from safety.guard import GuardLog, _hash


def audit(log_path: Optional[Path] = None) -> dict:
    """Проверка hash-chain лога СТРАЖА. TAMPERED — цепочка разорвана."""
    path = Path(log_path or config.GUARD_LOG_FILE)
    entries = GuardLog(path).entries()

    by_level: dict[str, int] = {}
    prev = "GENESIS"
    broken_at: Optional[int] = None
    recomputed_bad = 0

    for i, rec in enumerate(entries):
        by_level[rec.get("level", "?")] = by_level.get(rec.get("level", "?"), 0) + 1
        payload = {k: v for k, v in rec.items() if k != "hash"}
        canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        expected = _hash(prev, canonical)
        if expected != rec.get("hash"):
            if broken_at is None:
                broken_at = i
            recomputed_bad += 1
        prev = rec.get("hash", prev)  # идём по записанным хешам: так ловится и удаление

    if entries:
        # дополнительный тест на удаление середины: хвост должен цепляться к предыдущей записи
        last = entries[-1]
        if len(entries) > 1:
            before = entries[-2]
            payload = {k: v for k, v in last.items() if k != "hash"}
            canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True)
            if _hash(before.get("hash", ""), canonical) != last.get("hash") and broken_at is None:
                broken_at = len(entries) - 1

    return {
        "log": str(path),
        "total": len(entries),
        "broken_at": broken_at,
        "by_level": by_level,
        "first_ts": entries[0].get("ts") if entries else None,
        "last_ts": entries[-1].get("ts") if entries else None,
        "verdict": "TAMPERED" if broken_at is not None else "OK",
    }


def print_report(report: dict) -> str:
    """Человекочитаемый отчёт для Ильи и для панели Ф97."""
    lines = [
        f"АУДИТ ЛОГА: {report['log']}",
        f"Записей: {report['total']}",
        f"Период: {report['first_ts']} .. {report['last_ts']}",
        "Уровни: " + (", ".join(f"{k}={v}" for k, v in sorted(report['by_level'].items())) or "-"),
    ]
    if report["verdict"] == "OK":
        lines.append("Вердикт: OK — цепочка целая, логу можно верить (6.6)")
    else:
        lines.append(f"Вердикт: TAMPERED — разрыв цепочки на записи #{report['broken_at']} "
                     f"(подмена/удаление/вставка). Лог не доверять, разбираться вручную.")
    return "\n".join(lines)


def main() -> int:  # pragma: no cover — ручной запуск на Z440
    import argparse
    p = argparse.ArgumentParser(description="Ф81: аудит hash-chain лога СТРАЖА")
    p.add_argument("log", nargs="?", default=None, help="путь к jsonl-логу (по умолчанию из config)")
    args = p.parse_args()
    rep = audit(Path(args.log) if args.log else None)
    print(print_report(rep))
    return 0 if rep["verdict"] == "OK" else 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
