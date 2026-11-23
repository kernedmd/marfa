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
  (evolution), расписание не останавливается; упавшая работа НЕ
  помечается выполненной: interval повторит себя своим интервалом,
  daily/weekly — через паузу 30 минут (K7 аудита 22.11);
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

RETRY_DELAY_SEC = 30 * 60      # K7: пауза между попытками упавшей daily/weekly работы

_bad_spec_seen: set[tuple] = set()   # урок о кривой работе — раз за процесс (не спамим каждую минуту)


def _parse_hhmm(s: str) -> tuple[int, int]:
    """ЧЧ:ММ с валидацией (M9 аудита): «8», «08:00:00», «25:00» —
    честный ValueError, а не падение расписания на ровном месте."""
    parts = str(s).split(":")
    if len(parts) != 2 or not parts[0].strip().isdigit() \
            or not parts[1].strip().isdigit():
        raise ValueError("время расписания — ЧЧ:ММ, получено «%s»" % s)
    h, m = int(parts[0]), int(parts[1])
    if not (0 <= h <= 23 and 0 <= m <= 59):
        raise ValueError("время вне суток: «%s»" % s)
    return h, m


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

    # ВНУТРЕННЯЯ ЖИЗНЬ (23.11): сон и мысли в ритме стремления.
    # Ночью дом спит: вопросы и библиотекарь молчат (врач и бэкап —
    # вегетативная нервная система, работают всегда); мысль и сон
    # пишутся только бодрствующим организмом с живым языком (гейт §5)
    def _dream() -> str:
        from core import musing
        _text, status = musing.dream()
        return status

    def _muse() -> str:
        from core import musing
        _text, status = musing.muse()
        return status

    def _questions_awake() -> str:
        from core import sleep as _sleep
        if _sleep.is_asleep():
            return "дом спит — вопросы подождут утра"
        from core import questions
        return questions.tick()

    def _librarian_awake() -> str:
        from core import sleep as _sleep
        if _sleep.is_asleep():
            return "дом спит — полка подождёт утра"
        from core import librarian
        return librarian.tick()

    def _weekly_audit() -> str:
        # №29: еженедельный доклад архитектора (вс 20:00) — тесты,
        # коммиты, диск, дрейф канона; отчёт в logs/architect/weekly_*.md.
        # Вечная служба переживает упавший источник (закон №10 р3)
        import architect_oncall
        text = architect_oncall.weekly_report()
        return "доклад архитектора: %d строк" % len(text.splitlines())

    def _seal() -> str:
        # Ф46 (день-9): печать души перед сном — за 5 минут до бэкапа,
        # чтобы архив увозил ЗАПЕЧАТАННОЕ состояние (сверка — «печати целы?»)
        from core import seal
        return seal.tick()

    return [
        job("plan", "daily", at="08:00", what="план дня (Ф71)", run=_plan),
        job("diary", "daily", at="21:00", what="вечерний дневник (№8)",
            run=_diary_day),
        job("dream", "daily", at="07:10",
            what="сон-сновидение после ночи (мысли)", run=_dream),
        job("backup", "daily", at="23:30", what="бэкап души дома (№23)",
            run=_backup),
        job("seal", "daily", at="23:25", what="печать души перед сном (Ф46)",
            run=_seal),
        job("queue", "interval", every=60,
            what="очередь и вопросы (Ф74)", run=_questions_awake),
        job("doctor", "interval", every=300,
            what="автодоктор: осмотр и лечение дома (№21)", run=_doctor_tick),
        job("librarian", "interval", every=3600,
            what="библиотекарь: чтение дома", run=_librarian_awake),
        job("musing", "interval", every=config.MUSING_INTERVAL_SECS,
            what="фоновая мысль в тишине (мысли)", run=_muse),
        job("architect-weekly", "weekly", weekday="sun", at="20:00",
            what="доклад архитектора: тесты, коммиты, диск, канон (№29)",
            run=_weekly_audit),
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
        # успех и провалы живут в состоянии РАЗДЕЛЬНО (K7 аудита):
        # state[id] — только удачные прогоны; провалы — под ключом «id!fail»
        last = self._last_ts(state, j["id"])
        fail = self._last_ts(state, j["id"] + "!fail")
        if last is not None and last > now:
            last = None            # M11: часы прыгнули назад — считаем, что не было
        if fail is not None and fail > now:
            fail = None
        try:
            if j["kind"] == "daily":
                h, m = _parse_hhmm(j["at"])
                slot = now.replace(hour=h, minute=m, second=0, microsecond=0)
                due = now >= slot and (last is None or last.date() < now.date())
                if due and fail is not None \
                        and (now - fail).total_seconds() < RETRY_DELAY_SEC:
                    return False    # недавно падала — пауза между попытками
                return due
            if j["kind"] == "weekly":
                wd = _WEEKDAYS[j["weekday"]]
                h, m = _parse_hhmm(j["at"])
                days_ahead = (wd - now.weekday()) % 7
                slot = (now + dt.timedelta(days=days_ahead)).replace(
                    hour=h, minute=m, second=0, microsecond=0)
                # ближайшее прошедшее вхождение: сегодня или в течение недели назад
                if slot > now:
                    slot -= dt.timedelta(days=7)
                due = now >= slot and (last is None or last < slot)
                if due and fail is not None \
                        and (now - fail).total_seconds() < RETRY_DELAY_SEC:
                    return False
                return due
            if j["kind"] == "interval":
                # последняя попытка любого исхода — свой интервал и есть
                # политика повтора
                refs = [x for x in (last, fail) if x is not None]
                ref = max(refs) if refs else None
                return ref is None or (now - ref).total_seconds() >= j["every"]
        except (ValueError, KeyError, TypeError) as e:
            # M9/M10: кривая работа (время, weekday, every) — урок ОДИН раз
            # на уникальную ошибку, расписание живо, работа не готова к запуску
            key = (str(self.state_path), j["id"], type(e).__name__, str(e)[:200])
            if key not in _bad_spec_seen:
                _bad_spec_seen.add(key)
                _log_lesson(j, e)
            return False
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
                # K7 аудита: только УСПЕШНЫЙ прогон помечается выполненным;
                # успех стирает память о провалах
                state[j["id"]] = now.isoformat(timespec="seconds")
                state.pop(j["id"] + "!fail", None)
            except Exception as e:   # работа упала — расписание живо
                rec.update(ok=False, error=str(e)[:300])
                _log_lesson(j, e)
                # K7: провал ≠ «сегодня сделано». Работа повторится:
                # interval — своим интервалом, daily/weekly — через паузу
                # RETRY_DELAY_SEC (не каждую минуту — не заваливаем уроками)
                state[j["id"] + "!fail"] = now.isoformat(timespec="seconds")
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
