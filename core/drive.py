# -*- coding: utf-8 -*-
r"""core/drive.py — СЛУЖБА СТРЕМЛЕНИЯ (Круг Д): сердце дома бьётся само.

Пятый слуга дома (после мозга, глаз, панели и ушей). Раз в минуту:
- гоняет расписание Ф75 (план, дневник, очередь/вопросы, библиотекарь,
  сжатие памяти) — core/schedule.py;
- щупает мозг (/health) и честно пишет, сколько он молчит — по этому
  статусу инициатива спрашивает Илью «посмотреть консоль?»;
- пишет сердцебиение в data\drive_status.json — панель и «статус»
  видят живое стремление.

Запуск из корня дома:
    venv\Scripts\python.exe -m core.drive --service   # вечная служба
    venv\Scripts\python.exe -m core.drive --tick      # один такт (проверка)

Служба не умирает: упавшая работа — урок в журнал эволюционера,
тик продолжается. Выход — Ctrl+C.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import time
from pathlib import Path
from typing import Optional

from core import config


def _read_status() -> dict:
    try:
        data = json.loads(config.DRIVE_STATUS_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _write_status(brain_ok: bool, results: list[dict],
                  now: Optional[dt.datetime] = None) -> dict:
    """Сердцебиение: ts, состояние мозга, протокол последних работ."""
    now = now or dt.datetime.now()
    prev = _read_status()
    if brain_ok:
        brain_down_since = None
    else:
        raw = prev.get("brain_down_since")
        try:
            brain_down_since = (dt.datetime.fromisoformat(raw).isoformat(timespec="seconds")
                                if raw else now.isoformat(timespec="seconds"))
        except ValueError:
            brain_down_since = now.isoformat(timespec="seconds")

    jobs = {}
    for rec in prev.get("jobs", {}).items():
        jobs[rec[0]] = rec[1]
    for r in results:
        jobs[r["id"]] = {"ts": now.isoformat(timespec="seconds"),
                         "ok": bool(r.get("ok")),
                         "note": r.get("note") or r.get("error", "")}

    status = {"ts": now.isoformat(timespec="seconds"), "state": "ok",
              "brain_ok": brain_ok,
              "brain_down_since": brain_down_since,
              "jobs": jobs,
              "last_results": results}
    try:
        config.DRIVE_STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = config.DRIVE_STATUS_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(status, ensure_ascii=False, indent=1),
                       encoding="utf-8")
        tmp.replace(config.DRIVE_STATUS_FILE)
    except OSError:
        pass                     # сердце не пишет — но бьётся
    return status


def _brain_ok() -> bool:
    """Жив ли мозг. Ошибка сети — не ошибка службы."""
    try:
        from core.brain import BrainClient
        return BrainClient().health()
    except Exception:
        return False


def one_tick(now: Optional[dt.datetime] = None) -> dict:
    """Один такт стремления: расписание + здоровье мозга + сердце."""
    from core.schedule import Scheduler, default_jobs
    results = Scheduler().tick(now=now, jobs=default_jobs())
    return _write_status(_brain_ok(), results, now=now)


def serve(interval: float = config.DRIVE_INTERVAL_SECS,
          max_ticks: Optional[int] = None) -> None:
    """Вечная служба. max_ticks — только для тестов."""
    print("=" * 60)
    print("МАРФА — служба стремления (расписание и инициатива)")
    print("Такт: %.0f с. Выход: Ctrl+C." % interval)
    print("=" * 60)
    n = 0
    try:
        while True:
            status = one_tick()
            stamp = dt.datetime.now().strftime("%H:%M:%S")
            ran = ", ".join("%s:%s" % (r["id"], "ок" if r.get("ok") else "СБОЙ")
                            for r in status.get("last_results", []))
            note = ("мозг жив" if status.get("brain_ok")
                    else "мозг молчит с %s" % str(status.get("brain_down_since", "?"))[11:16])
            print("[%s] тик %d: %s%s" % (stamp, n + 1, note,
                                          (" | " + ran) if ran else ""))
            n += 1
            if max_ticks is not None and n >= max_ticks:
                return
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\nслужба стремления остановлена (Ctrl+C)")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="служба стремления Марфы")
    ap.add_argument("--service", action="store_true",
                    help="вечная служба (для автозапуска дома)")
    ap.add_argument("--tick", action="store_true",
                    help="один такт и выход (проверка руками)")
    args = ap.parse_args(argv)
    if args.tick:
        status = one_tick()
        print(json.dumps(status, ensure_ascii=False, indent=1))
        return 0
    serve()                      # --service или без аргументов
    return 0


if __name__ == "__main__":
    sys.exit(main())
