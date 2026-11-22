# -*- coding: utf-8 -*-
"""core/questions.py — ИНИЦИАТИВА МАРФЫ (Круг Д): вопросы Создателю.

Стремление — это не только делать, но и ХОТЕТЬ знать. Марфа собирает
вопросы к Илье из жизни дома и задаёт их, когда Создатель рядом:

- задачи в очереди висят неделю без движения — «ещё актуально?»;
- уши не слышат сутки (нет микрофона/модели/sounddevice) — «когда
  поправим?»;
- мозг молчит дольше двух часов — «посмотреть консель?»;

Файл: data/questions.json. Ответ Ильи — сразу в память (важное,
importance 3.5): Марфа запоминает решения Создателя.
Дедуп: один и тот же открытый вопрос не плодится.
"""
from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path
from typing import Optional

from core import config

QUEUE_STALE_DAYS = 7        # задача висит дольше — вопрос
EARS_SILENT_HOURS = 24      # уши молчат дольше — вопрос
BRAIN_SILENT_HOURS = 2      # мозг молчит дольше — вопрос


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\wа-яё\s]", " ",
                                      (text or "").lower())).strip()


class QuestionBank:
    """Банк вопросов: add / open / answer / tick (инициатива из файлов дома)."""

    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = Path(path) if path else config.QUESTIONS_FILE

    # ---------- файл ----------

    def _load(self) -> dict:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and isinstance(data.get("items"), list):
                return data
        except (OSError, ValueError):
            pass
        return {"next": 1, "items": []}

    def _save(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1),
                       encoding="utf-8")
        tmp.replace(self.path)

    # ---------- API ----------

    def add(self, text: str, source: str) -> Optional[dict]:
        """Задать вопрос. Уже открыт такой же — молча нет (дедуп)."""
        text = (text or "").strip()
        if not text:
            return None
        norm = _norm(text)
        data = self._load()
        for it in data["items"]:
            if it.get("status") == "open" and it.get("norm") == norm:
                return None
        q = {"id": "q%d" % data["next"], "text": text[:500], "norm": norm,
             "source": source[:100], "status": "open",
             "created_at": dt.datetime.now().isoformat(timespec="seconds")}
        data["next"] += 1
        data["items"].append(q)
        self._save(data)
        return q

    def open_items(self) -> list[dict]:
        return [it for it in self._load()["items"]
                if it.get("status") == "open"]

    def answer(self, qid: str, answer_text: str) -> Optional[dict]:
        """Илья ответил: вопрос закрыт, ответ готов для памяти."""
        answer_text = (answer_text or "").strip()
        data = self._load()
        for it in data["items"]:
            if it.get("id") == qid and it.get("status") == "open":
                if not answer_text:
                    return None
                it["status"] = "answered"
                it["answer"] = answer_text[:1000]
                it["answered_at"] = dt.datetime.now().isoformat(timespec="seconds")
                self._save(data)
                return it
        return None

    # ---------- инициатива ----------

    def tick(self, now: Optional[dt.datetime] = None) -> list[str]:
        """Один такт (раз в минуту, Ф74): обойти дом, собрать вопросы.

        Возвращает тексты НОВЫХ вопросов (для протокола расписания).
        """
        now = now or dt.datetime.now()
        asked: list[str] = []

        # 1) очередь: зависшие задачи
        from core.autonomy import load_queue, save_queue
        tasks = load_queue()
        # гигиена Ф74: дубли по названию — второй и дальше закрываются
        seen_titles: set[str] = set()
        deduped = []
        changed = False
        for t in tasks:
            if t.get("status") != "pending":
                continue
            key = _norm(t.get("title", ""))
            if not key:
                deduped.append(t)
                continue
            if key in seen_titles:
                t["status"] = "cancelled"
                changed = True
                continue
            seen_titles.add(key)
            deduped.append(t)
        if changed:
            save_queue(tasks)
        for t in deduped:
            try:
                age_days = (now - dt.datetime.fromisoformat(
                    str(t.get("created_at", now.isoformat())))).days
            except ValueError:
                continue
            if age_days >= QUEUE_STALE_DAYS:
                q = self.add("Задача «%s» висит с %s без движения — она ещё "
                             "актуальна?" % (t.get("title", "?")[:80],
                                             str(t.get("created_at", ""))[:10]),
                             source="очередь")
                if q:
                    asked.append(q["text"])

        # 2) уши: почему молчат (если служба вообще поднималась)
        try:
            rec = json.loads(config.EARS_STATUS_FILE.read_text(encoding="utf-8"))
            ts = dt.datetime.fromisoformat(rec.get("ts", ""))
            silent_h = (now - ts).total_seconds() / 3600
            state = rec.get("state", "")
            if state in ("no_mic", "no_model", "no_sounddevice") \
                    and silent_h >= EARS_SILENT_HOURS:
                reason = {"no_mic": "микрофона нет",
                          "no_model": "модель ушей не найдена",
                          "no_sounddevice": "не поставлен sounddevice"}[state]
                q = self.add("Уши не слышат уже долго (%s). Когда получится "
                             "поправить?" % reason, source="уши")
                if q:
                    asked.append(q["text"])
        except (OSError, ValueError, KeyError):
            pass

        # 3) мозг: служба стремления видит его молчание (файл статуса)
        try:
            rec = json.loads(config.DRIVE_STATUS_FILE.read_text(encoding="utf-8"))
            down_since = dt.datetime.fromisoformat(rec.get("brain_down_since", ""))
            if (now - down_since).total_seconds() / 3600 >= BRAIN_SILENT_HOURS:
                q = self.add("Мозг молчит с %s — посмотреть его консоль?"
                             % down_since.strftime("%H:%M"), source="мозг")
                if q:
                    asked.append(q["text"])
        except (OSError, ValueError, KeyError):
            pass

        return asked


def tick() -> str:
    """Точка входа для расписания Ф75 (интервал 60 с)."""
    new = QuestionBank().tick()
    if not new:
        return "вопросов нет"
    return "новых вопросов: %d" % len(new)
