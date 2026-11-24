# -*- coding: utf-8 -*-
r"""sensors/monitor.py — Ф97 «МОНИТОР RAM» (ТЗ 3.9 П1, 0.1).

Следит за фактическим объёмом RAM: 85% — тревога, 92% — критично.
Пишет data\monitor_status.json (для панели web 5001) и лог событий
logs\monitor_log.jsonl (правило 6.6: логи — источник правды).
"""
from __future__ import annotations

import datetime as dt
import json
import time
from pathlib import Path
from typing import Callable, Optional

from core import config, loghygiene


def classify(pct: float) -> str:
    """Уровень по доле фактической RAM (0.1: 85% тревога / 92% критично)."""
    if pct >= config.MONITOR_CRIT_PCT:
        return "CRIT"
    if pct >= config.MONITOR_WARN_PCT:
        return "WARN"
    return "OK"


class RAMMonitor:
    def __init__(self,
                 snapshot: Optional[Callable[[], tuple[float, float]]] = None) -> None:
        """snapshot() -> (used_gb, total_gb). По умолчанию — psutil (на Z440 так)."""
        if snapshot is None:
            def snapshot():  # noqa: F811
                import psutil
                vm = psutil.virtual_memory()
                return vm.used / 2**30, vm.total / 2**30
        self.snapshot = snapshot
        self.status_file = Path(config.MONITOR_STATUS_FILE)
        self.log_file = Path(config.MONITOR_LOG_FILE)
        self.last_level: Optional[str] = None

    # ---------- измерение ----------
    def sample(self) -> dict:
        used, total = self.snapshot()
        pct = round(used / total * 100, 1) if total else 0.0
        return {
            "ts": dt.datetime.now().isoformat(timespec="seconds"),
            "used_gb": round(used, 2),
            "total_gb": round(total, 1),
            "pct": pct,
            "level": classify(pct),
            "warn_pct": config.MONITOR_WARN_PCT,
            "crit_pct": config.MONITOR_CRIT_PCT,
            "budget_plan_gb": config.RAM_BUDGET_GB,
        }

    # ---------- журнал ----------
    def _log_event(self, status: dict) -> None:
        rec = {"ts": status["ts"], "level": status["level"], "pct": status["pct"],
               "used_gb": status["used_gb"]}
        # Ф96 (круг 17): копилка монитора — через дверь ротации, как все
        loghygiene.append_line(self.log_file,
                                json.dumps(rec, ensure_ascii=False) + "\n")

    def observe(self) -> dict:
        """Замер + запись статуса + событие при смене уровня (WARN/CRIT)."""
        status = self.sample()
        self.status_file.parent.mkdir(parents=True, exist_ok=True)
        self.status_file.write_text(
            json.dumps(status, ensure_ascii=False, indent=1), encoding="utf-8")
        if status["level"] != self.last_level:
            # пишем переходы (OK->WARN->CRIT и возвраты) — Ф102 потом подключит реакцию
            if self.last_level is not None or status["level"] != "OK":
                self._log_event(status)
            self.last_level = status["level"]
        return status

    def history(self, limit: int = 50) -> list[dict]:
        if not self.log_file.exists():
            return []
        lines = self.log_file.read_text(encoding="utf-8").splitlines()[-limit:]
        out = []
        for line in lines:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return out

    # ---------- цикл ----------
    def run_loop(self, interval_sec: int = 30, stop=None) -> None:  # pragma: no cover — фон на Z440
        """Фоновый опрос раз в 30 с. stop — threading.Event."""
        while not (stop and stop.is_set()):
            try:
                self.observe()
            except Exception:
                pass  # монитор не должен ронять дом; пропущенный замер — не ЧП
            time.sleep(interval_sec)
