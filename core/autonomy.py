# -*- coding: utf-8 -*-
r"""core/autonomy.py — Ф71 «ПЛАНИРОВЩИК ДНЯ» (ТЗ 3.9).

Каждое утро в 08:00 Марфа строит план дня -> data\plan_YYYY-MM-DD.json:
- задачи дня из очереди data\queue.json (Ф74-каркас) + незавершённые задачи вчера;
- окна дня: QLoRA 04:30-06:30 (0.4), Библиотекарь раз в час (3.5), план в 08:00;
- слоты фишек: не более 3-5 в неделю (Раздел 5).
Декомпозиция (Ф72), параллель (Ф73), очередь каждую минуту (Ф74) и расписание
(Ф75) — Приоритет 2, в этот модуль войдут следующими фишками.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import uuid
from pathlib import Path
from typing import Optional

from core import config


# ---------------------------------------------------------------
# Очередь задач (каркас Ф74: формат очереди фиксируем уже сейчас)
# ---------------------------------------------------------------
def load_queue(queue_path: Optional[Path] = None) -> list[dict]:
    path = Path(queue_path or config.QUEUE_FILE)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        tasks = data.get("tasks", []) if isinstance(data, dict) else data
        return [t for t in tasks if isinstance(t, dict)]
    except (OSError, ValueError, AttributeError):
        # M11 аудита: OSError шире FileNotFoundError — файл занят антивирусом
        # или ACL на Windows не должен ронять службу. Битая очередь не роняет
        # дом — планируем без неё.
        return []


def save_queue(tasks: list[dict], queue_path: Optional[Path] = None) -> None:
    """M3 аудита: атомарно (tmp + replace) — краш посреди записи не
    оставляет обрезанный queue.json, вся очередь не теряется."""
    path = Path(queue_path or config.QUEUE_FILE)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps({"tasks": tasks}, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    tmp.replace(path)


def add_task(title: str, priority: str = "normal", queue_path: Optional[Path] = None) -> dict:
    """Добавить задачу в очередь (пользователь или сам агент).

    K5 аудита: id — uuid, а не секунда: две задачи в одну секунду
    (агент пачкой, дважды Enter) больше не неразличимы."""
    tasks = load_queue(queue_path)
    task = {
        "id": "t" + uuid.uuid4().hex[:12],
        "title": title.strip(),
        "priority": priority if priority in ("low", "normal", "high") else "normal",
        "status": "pending",
        "created_at": dt.datetime.now().isoformat(timespec="seconds"),
    }
    tasks.append(task)
    save_queue(tasks, queue_path)
    return task


# ---------------------------------------------------------------
# План дня
# ---------------------------------------------------------------
class DayPlanner:
    def __init__(self, data_dir: Optional[Path] = None) -> None:
        self.data_dir = Path(data_dir) if data_dir else Path(config.DATA_DIR)
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def plan_path(self, day: dt.date) -> Path:
        return self.data_dir / f"plan_{day.isoformat()}.json"

    def load_plan(self, day: Optional[dt.date] = None) -> Optional[dict]:
        day = day or dt.date.today()
        try:
            return json.loads(self.plan_path(day).read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except json.JSONDecodeError:
            return None  # битый план считаем отсутствующим

    def _carry_over(self, yesterday: dt.date,
                    exclude_ids: Optional[set] = None) -> list[str]:
        """Незавершённые задачи из вчерашнего плана — переезжают в сегодня.

        K6 аудита: задача, которая уже сидит в сегодняшней очереди (и так
        войдёт в tasks), в carry_over НЕ дублируется. M5: отменённая —
        не «незавершённая», она не переезжает."""
        prev = self.load_plan(yesterday)
        if not prev:
            return []
        exclude = exclude_ids or set()
        out = []
        for t in prev.get("tasks", []):
            if not (isinstance(t, dict) and t.get("status") not in ("done", "cancelled")):
                continue
            if t.get("id") in exclude:
                continue          # уже в сегодняшнем плане из очереди
            out.append(f"[с вчера] {t.get('title', 'без названия')}")
        return out

    def build_plan(self, day: Optional[dt.date] = None,
                   now: Optional[dt.datetime] = None,
                   force: bool = False) -> dict:
        """Собрать план дня. Идемпотентен: за день план один; force=True —
        пересобрать (новая задача после 08:00 видна сегодня, а не завтра).
        Статусы уже отмеченных сегодня задач force-пересборка сохраняет."""
        now = now or dt.datetime.now()
        day = day or now.date()   # дата плана — от момента времени, а не от часов машины
        existing = self.load_plan(day)
        if existing is not None and not force:
            return existing
        # force-пересборка не стирает работу дня: задачи, уже живущие в
        # плане (вместе со статусами — сделанное остаётся сделанным),
        # остаются; сверху приезжают новенькие из очереди
        kept = [t for t in (existing or {}).get("tasks", [])
                if isinstance(t, dict) and t.get("id")]
        known_ids = {t.get("id") for t in kept}

        yesterday = day - dt.timedelta(days=1)
        tasks = load_queue()
        # зомби-защита: закрытая вчера (в плане) задача не воскресает из
        # очереди, даже если очередь не узнала о закрытии
        prev = self.load_plan(yesterday) or {}
        closed_yesterday = {
            t.get("id") for t in prev.get("tasks", [])
            if isinstance(t, dict) and t.get("status") in ("done", "cancelled")}
        pending = [t for t in tasks
                   if t.get("status") == "pending"
                   and t.get("id") not in closed_yesterday]
        pending.sort(key=lambda t: {"high": 0, "normal": 1, "low": 2}.get(t.get("priority"), 1))

        plan = {
            "date": day.isoformat(),
            "generated_at": now.isoformat(timespec="seconds"),
            "tasks": kept + [
                {"id": t.get("id"), "title": t["title"],
                 "priority": t.get("priority", "normal"), "status": "pending"}
                for t in pending[:20] if t.get("id") not in known_ids
            ],
            "carry_over": self._carry_over(
                yesterday, {t.get("id") for t in kept} | {t.get("id") for t in pending[:20]}),
            "windows": [
                {"time": "04:30-06:30", "what": "QLoRA-окно (студент учится, правило 0.4)"},
                {"time": "08:00", "what": "план дня (Ф71)"},
                {"time": "каждый час", "what": "Библиотекарь: поиск -> память (3.5)"},
            ],
            # Раздел 5: не более 3-5 фишек в неделю — слоты дня не больше 1
            "feature_slots": 1 if day.weekday() < 5 else 0,   # пн-пт
            "questions_to_ilya": [],
        }
        self.plan_path(day).write_text(
            json.dumps(plan, ensure_ascii=False, indent=1), encoding="utf-8")
        return plan

    def mark_task(self, task_id: str, status: str, day: Optional[dt.date] = None) -> bool:
        """Отметить задачу в плане дня (pending/in_progress/done/cancelled).

        M5 аудита: статус валидируется — «думаю»/«xyz» не проходят.
        Отметка синхронизируется с очередью: закрытая задача не
        воскресает завтра из queue.json (K6: план и очередь — одна правда)."""
        if status not in ("pending", "in_progress", "done", "cancelled"):
            raise ValueError("статус задачи: pending/in_progress/done/cancelled, «%s» не бывает" % status)
        day = day or dt.date.today()
        plan = self.load_plan(day)
        if not plan:
            return False
        for t in plan.get("tasks", []):
            if t.get("id") == task_id:
                t["status"] = status
                self.plan_path(day).write_text(
                    json.dumps(plan, ensure_ascii=False, indent=1), encoding="utf-8")
                try:   # очередь узнаёт ту же правду (кроме дней-наблюдений)
                    tasks = load_queue()
                    for q in tasks:
                        if q.get("id") == task_id:
                            q["status"] = status
                    save_queue(tasks)
                except OSError:
                    pass          # очередь не записалась — план всё равно прав
                return True
        return False

    # ---------- такт планировщика ----------
    def should_run(self, now: Optional[dt.datetime] = None) -> bool:
        """Пора ли строить план: после 08:00 и если за сегодня его ещё нет."""
        now = now or dt.datetime.now()
        if now.hour < config.PLAN_HOUR:
            return False
        return self.load_plan(now.date()) is None

    def tick(self, now: Optional[dt.datetime] = None) -> Optional[dict]:
        """Один такт внешнего цикла (Ф75 подключит расписание) — возвращает план или None."""
        if self.should_run(now):
            return self.build_plan(now=now)
        return None
