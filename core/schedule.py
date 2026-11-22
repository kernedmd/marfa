# -*- coding: utf-8 -*-
"""core/schedule.py — Ф75 «РАСПИСАНИЕ» (ТЗ 3.9): сердце стремления Марфы.

Три вида работы:
- daily HH:MM   — раз в день (план 08:00, дневник 21:00);
- weekly WD HH:MM — раз в неделю (сжатие памяти, вс 23:00);
- interval N    — каждые N секунд (очередь/вопросы 60 с, библиотекарь час).

Честность конструкции:
- состояние в data/schedule_state.json — «что уже отработано»;
  перезапуск службы не гонит одну работу дважды в один день;
- работа упала — ошибка честно пишется в результат и в журнал уроков
  (evolution), расписание не останавливается;
- время — местные часы дома (Z440 живёт по времени Создателя).
"""
from __future__ import annotations

import datetime as dt
import inspect
import json
from pathlib import Path
from typing import Callable, Optional

from core import config

_WEEKDAYS = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4,
             "sat": 5, "sun": 6}


def _parse_hhmm(s: str) -> tuple[int, int]:
    h, m = s.split(":")
    return int(h), int(m)


def job(job_id: str, kind: str, what: str, run: Callable[[], object], **kw):
    """Спецификация работы. kind: daily | weekly | interval."""
    spec = {"id": job_id, "kind": kind, "what": what, "run": run}
    spec.update(kw)
    return spec


def default_jobs() -> list[dict]:
    """Расписание дома. Действия импортируются ЛЕНИВО: без циклов импорта
    и без тяжёлых подъёмов на этапе чтения модуля.

    Работа может объявить параметр now — тогда тик передаёт ей своё
    «сейчас» (урок 22.11: план, построенный по реальным часам, а не по
    часам тика, — это работа из другого дня; тест, зелёный только в
    свою дату, — не тест).
    """
    from core import diary as _diary
    from core import librarian as _librarian
    from core import questions as _questions
    from core.autonomy import DayPlanner

    def _plan(now: Optional[dt.datetime] = None) -> str:
        plan = DayPlanner().tick(now)
        return "план построен" if plan else "план уже был"

    def _diary_day() -> str:
        text = _diary.Diary().build_day()
        return "дневник: %d строк" % len(text.splitlines())

    def _compress() -> str:
        from core.memory import Memory
        stats = Memory().compress_old(days=7)
        return "сжато %d воспоминаний" % stats["compressed"]

    def _doctor_tick() -> str:
        from core import doctor
        return doctor.tick_auto()

    def _backup() -> str:
        from core import backup
        return backup.tick()

    return [
        job("plan", "daily", at="08:00", what="план дня (Ф71)", run=_plan),
        job("diary", "daily", at="21:00", what="вечерний дневник (№8)",
            run=_diary_day),
        job("backup", "daily", at="23:30", what="бэкап души дома (№23)",
            run=_backup),
        job("queue", "interval", every=60,
            what="очередь и вопросы (Ф74)", run=_questions.tick),
        job("doctor", "interval", every=300,
            what="автодоктор: осмотр и лечение дома (№21)", run=_doctor_tick),
        job("librarian", "interval", every=3600,
            what="библиотекарь: чтение дома", run=_librarian.tick),
        job("memory-compress", "weekly", weekday="sun", at="23:00",
            what="сжатие памяти (№7)", run=_compress),
    ]


class Scheduler:
    """Тикает раз в минуту (служба стремления), гоняет то, что пора."""

    def __init__(self, state_path: Optional[Path] = None) -> None:
        self.state_path = Path(state_path) if state_path else config.SCHEDULE_STATE_FILE

    # ---------- состояние ----------

    def _load_state(self) -> dict:
        try:
            data = json.loads(self.state_path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def _save_state(self, state: dict) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.state_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, ensure_ascii=False, indent=1),
                       encoding="utf-8")
        tmp.replace(self.state_path)

    @staticmethod
    def _last_ts(state: dict, job_id: str) -> Optional[dt.datetime]:
        raw = state.get(job_id)
        if not raw:
            return None
        try:
            return dt.datetime.fromisoformat(raw)
        except ValueError:
            return None

    # ---------- пора ли ----------

    def _due(self, j: dict, now: dt.datetime, state: dict) -> bool:
        last = self._last_ts(state, j["id"])
        if j["kind"] == "daily":
            h, m = _parse_hhmm(j["at"])
            slot = now.replace(hour=h, minute=m, second=0, microsecond=0)
            return now >= slot and (last is None or last.date() < now.date())
        if j["kind"] == "weekly":
            wd = _WEEKDAYS[j["weekday"]]
            h, m = _parse_hhmm(j["at"])
            days_ahead = (wd - now.weekday()) % 7
            slot = (now + dt.timedelta(days=days_ahead)).replace(
                hour=h, minute=m, second=0, microsecond=0)
            # ближайшее прошедшее вхождение: сегодня или в течение недели назад
            if slot > now:
                slot -= dt.timedelta(days=7)
            return now >= slot and (last is None or last < slot)
        if j["kind"] == "interval":
            return last is None or (now - last).total_seconds() >= j["every"]
        return False

    def due(self, now: Optional[dt.datetime] = None,
            jobs: Optional[list[dict]] = None) -> list[dict]:
        now = now or dt.datetime.now()
        state = self._load_state()
        return [j for j in (jobs if jobs is not None else default_jobs())
                if self._due(j, now, state)]

    # ---------- такт ----------

    @staticmethod
    def _invoke(run: Callable, now: dt.datetime):
        """Позвать работу. Объявила параметр now — тик передаёт своё
        «сейчас»: расписание и его работы живут в одном времени. Без
        параметра — работа зовётся как раньше, без аргументов."""
        try:
            wants_now = len(inspect.signature(run).parameters) >= 1
        except (TypeError, ValueError):
            wants_now = False
        return run(now) if wants_now else run()

    def tick(self, now: Optional[dt.datetime] = None,
             jobs: Optional[list[dict]] = None) -> list[dict]:
        """Один такт: исполнить всё, что пора. Возврат — протокол честности:
        [{id, what, ok, note}] и для упавших — error."""
        now = now or dt.datetime.now()
        jobs = jobs if jobs is not None else default_jobs()
        state = self._load_state()
        results = []
        for j in jobs:
            if not self._due(j, now, state):
                continue
            rec = {"id": j["id"], "what": j["what"]}
            try:
                note = self._invoke(j["run"], now)
                rec.update(ok=True, note=str(note)[:300] if note else "ок")
            except Exception as e:   # работа упала — расписание живо
                rec.update(ok=False, error=str(e)[:300])
                _log_lesson(j, e)
            state[j["id"]] = now.isoformat(timespec="seconds")
            results.append(rec)
        if results:
            self._save_state(state)
        return results


def _log_lesson(j: dict, e: Exception) -> None:
    """Упавшая работа — урок в журнал эволюционера (не роняя тик)."""
    try:
        from evolution.journal import log_lesson
        log_lesson("расписание-сбой",
                   "работа «%s» упала: %s" % (j["id"], e))
    except Exception:
        pass   # журнала нет или молчит — расписание не рвётся
