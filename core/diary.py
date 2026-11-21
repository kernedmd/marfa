# -*- coding: utf-8 -*-
"""core/diary.py — №8 «Вечерний дневник» (роадмап-30, Мозг).

Каждый вечер (расписание Ф75, 21:00) или по команде «подведи день»
Марфа сводит день в data/diary/YYYY-MM-DD.md.

ЧЕСТНОСТЬ КОНСТРУКЦИИ (гейт качества, доктрина §5): каркас дневника
механический — только факты из файлов дома (план, разговоры, уши,
память, уроки). Никаких LLM-саммари, пока батарея Этапа 1 не дала
вердикта: больной мозг не пишет «истину», которая останется в доме.
Место для живого рассказа в каркасе помечено и включится резолюцией
Создателя после вердикта.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Optional

from core import config


def _read_json(path: Path) -> Optional[dict]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


def _count_day_lines(path: Path, day: dt.date) -> int:
    """Сколько записей JSONL приходится на дату day (поле ts = ISO)."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return 0
    n = 0
    for line in lines:
        try:
            ts = json.loads(line).get("ts", "")
            if ts[:10] == day.isoformat():
                n += 1
        except ValueError:
            continue
    return n


class Diary:
    """Дневник дома: собрать факты дня -> markdown-каркас."""

    def __init__(self, data_dir: Optional[Path] = None) -> None:
        self.data_dir = Path(data_dir) if data_dir else Path(config.DATA_DIR)
        self.diary_dir = self.data_dir / "diary"
        self.diary_dir.mkdir(parents=True, exist_ok=True)

    def path(self, day: dt.date) -> Path:
        return self.diary_dir / (day.isoformat() + ".md")

    # ---------- факты ----------

    def collect_facts(self, day: dt.date) -> dict:
        """Механические факты дня из файлов дома. Нет файла — ноль, не выдумка."""
        facts: dict = {"date": day.isoformat()}

        plan = _read_json(self.data_dir / ("plan_%s.json" % day.isoformat()))
        if plan:
            tasks = [t for t in plan.get("tasks", []) if isinstance(t, dict)]
            done = [t for t in tasks if t.get("status") == "done"]
            facts["plan"] = {
                "total": len(tasks),
                "done": len(done),
                "open_titles": [t.get("title", "?") for t in tasks
                                if t.get("status") != "done"][:10],
                "carry_over": [c for c in plan.get("carry_over", [])
                               if isinstance(c, str)][:10],
            }

        # разговоры: сессии, жившие в этот день (mtime), темы — первые вопросы
        dialogs_dir = self.data_dir / "dialog"
        sessions, turns_total, topics = 0, 0, []
        if dialogs_dir.is_dir():
            for p in sorted(dialogs_dir.glob("session_*.json")):
                try:
                    if dt.date.fromtimestamp(p.stat().st_mtime) != day:
                        continue
                except OSError:
                    continue
                data = _read_json(p) or {}
                turns = [t for t in data.get("turns", [])
                         if isinstance(t, dict) and t.get("role") == "user"]
                if not turns:
                    continue
                sessions += 1
                turns_total += len(turns)
                first = (turns[0].get("text") or "").strip()
                if first and len(topics) < 5:
                    topics.append(first[:80])
        if sessions:
            facts["dialogs"] = {"sessions": sessions, "user_turns": turns_total,
                                "topics": topics}

        wakes = _count_day_lines(config.EARS_LOG_FILE, day)
        if wakes:
            facts["ears_wakes"] = wakes

        memory_file = self.data_dir / "memory" / "memory.json"
        try:
            recs = json.loads(memory_file.read_text(encoding="utf-8"))
            new_mem = [r for r in recs if isinstance(r, dict)
                       and dt.datetime.fromtimestamp(
                           float(r.get("created_at", 0))).date() == day]
            if new_mem:
                facts["memory_new"] = len(new_mem)
        except (OSError, ValueError, TypeError, OverflowError):
            pass

        lessons = _count_day_lines(self.data_dir / "evolution" / "journal.jsonl", day)
        if lessons:
            facts["lessons"] = lessons

        return facts

    # ---------- каркас ----------

    def build_day(self, day: Optional[dt.date] = None,
                  now: Optional[dt.datetime] = None) -> str:
        """Собрать и записать дневник дня. Идемпотентен: пересборка того же
        дня заменяет файл (факты за вечер дорастают)."""
        now = now or dt.datetime.now()
        day = day or now.date()
        facts = self.collect_facts(day)
        lines = ["# Дневник Марфы — %s" % day.isoformat(), ""]

        plan = facts.get("plan")
        if plan:
            lines.append("## План дня")
            lines.append("Задач: %d, сделано: %d." % (plan["total"], plan["done"]))
            if plan["open_titles"]:
                lines.append("Не закрыты:")
                lines += ["- " + t for t in plan["open_titles"]]
            if plan["carry_over"]:
                lines.append("Приехало с вчера: %d." % len(plan["carry_over"]))
            lines.append("")

        dialogs = facts.get("dialogs")
        if dialogs:
            lines.append("## Разговоры")
            lines.append("Сессий: %d, моих реплик в ответ: %d."
                         % (dialogs["sessions"], dialogs["user_turns"]))
            if dialogs["topics"]:
                lines.append("О чём говорили:")
                lines += ["- " + t for t in dialogs["topics"]]
            lines.append("")

        if facts.get("ears_wakes"):
            lines.append("## Уши")
            lines.append("Имя «Марфа» звучало %d раз." % facts["ears_wakes"])
            lines.append("")

        if facts.get("memory_new"):
            lines.append("## Память")
            lines.append("Новых воспоминаний: %d." % facts["memory_new"])
            lines.append("")

        if facts.get("lessons"):
            lines.append("## Уроки (эволюционер)")
            lines.append("Событий в журнал уроков: %d." % facts["lessons"])
            lines.append("")

        lines.append("## Что хочу завтра")
        wants: list[str] = []
        if plan and plan["open_titles"]:
            wants += ["закрыть: " + plan["open_titles"][0]]
        if not dialogs:
            wants.append("поговорить с Ильёй — день прошёл молча")
        if not wants:
            wants.append("хороший тихий дом; главное — не выдумывать заботу")
        lines += ["- " + w for w in wants[:3]]
        lines.append("")

        lines.append("## Живой рассказ")
        lines.append("(место для рассказа Марфы о дне — включится резолюцией "
                     "Создателя после вердикта батареи, гейт §5: больной мозг "
                     "не пишет истину в дом)")
        text = "\n".join(lines)
        self.path(day).write_text(text, encoding="utf-8")
        return text

    def last_diary(self) -> Optional[str]:
        """Дата последнего дневника (для панели и «что хотела спросить»)."""
        days = sorted(p.stem for p in self.diary_dir.glob("*.md"))
        return days[-1] if days else None
