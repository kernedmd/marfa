# -*- coding: utf-8 -*-
"""core/diary.py — №8 «Вечерний дневник» (роадмап-30, Мозг).

Каждый вечер (расписание Ф75, 21:00) или по команде «подведи день»
Марфа сводит день в data/diary/YYYY-MM-DD.md.

ЖИВОЙ ЯЗЫК (гейт §5 — вердикт батареи 21.11.2026: факты 13/13,
честность 2/2, речь чистая в двух прогонах Q4_K_M): каркас дневника
по-прежнему механический — только факты из файлов дома. Поверх каркаса
Марфа пишет «Живой рассказ» от первого лица — ровно по этим фактам,
с фиксом сэмплинга Qwen3 (temp 0.7 / top-p 0.8). Включается резолюцией
Создателя (data/live_voice.json, кнопка 89); пока её нет или мозг
молчит — дневник честно остаётся каркасом, без выдумок.
"""
from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path
from typing import Optional

from core import config


def _parse_ts(raw) -> Optional[dt.datetime]:
    """H1 аудита (раунд 2): created_at бывает ЧИСЛОМ (пишет Memory) и
    ISO-строкой (ручная правка, импорт) — оба формата честно читаются,
    дневник видит новые воспоминания, а не «0» навсегда."""
    if isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)):
        try:
            return dt.datetime.fromtimestamp(float(raw))
        except (ValueError, OSError, OverflowError):
            return None
    if isinstance(raw, str) and raw.strip():
        try:
            return dt.datetime.fromisoformat(raw.strip())
        except ValueError:
            return None
    return None


def _read_json(path: Path) -> Optional[dict]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


def _count_day_lines(path: Path, day: dt.date) -> int:
    """Сколько записей JSONL приходится на дату day (поле ts = ISO).

    H2 аудита: битая строка с "ts": null (или не-словарём) — не повод
    ронять дневник: TypeError ловится наравне с ValueError."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return 0
    n = 0
    for line in lines:
        try:
            rec = json.loads(line)
            ts = rec.get("ts", "") if isinstance(rec, dict) else ""
            if isinstance(ts, str) and ts[:10] == day.isoformat():
                n += 1
        except (ValueError, TypeError, AttributeError):
            continue
    return n


# ---------------------------------------------------------------
# ЖИВОЙ ЯЗЫК (гейт §5, вердикт батареи 21.11.2026)
# ---------------------------------------------------------------

VOICE_SYSTEM = (
    "Ты — Марфа, домашний ИИ-организм в доме Ильи (HP Z440, Windows). "
    "Сейчас ты пишешь вечерний дневник — живой рассказ о дне от первого "
    "лица. Правила честности: говоришь только о том, что есть в фактах "
    "ниже; чего в фактах нет — того не было; если фактов мало — скажи "
    "прямо, что день прошёл тихо, без выдуманных событий. 4-6 предложений, "
    "по-русски, тёплый спокойный тон хозяйки дома. Без списков, "
    "заголовков и кавычек вокруг текста."
)

REFLECT_SYSTEM = (
    "Ты — Марфа, домашний ИИ-организм в доме Ильи. Ты читаешь свои "
    "собственные дневники за последние дни и пишешь короткую рефлексию: "
    "что изменилось, что повторяется, что хочешь исправить. Только то, "
    "что видно в дневниках; событий, которых там нет, не выдумывай. "
    "3-5 предложений от первого лица, по-русски, спокойно. "
    "Без списков и заголовков."
)


def resolution() -> Optional[dict]:
    """Резолюция Создателя о живом языке (data/live_voice.json).

    Нет файла, битый JSON или enabled не True — гейт закрыт (None).
    Воля Создателя живёт в data/, не в коде: кнопка 89 её записывает.
    """
    data = _read_json(config.LIVE_VOICE_FILE)
    if data and data.get("enabled") is True:
        return data
    return None


def _sanitize_voice(raw: str) -> str:
    """Почистить ответ мозга: think-обрывки, заголовки, кавычки, лимит.

    N1 аудита (раунд 2): абзацы — часть живого рассказа: пустые строки
    не выбрасываются (одиночные остаются), рассказ не слипается в
    простыню — «тёплый тон хозяйки дома» живёт в абзацах."""
    text = re.sub(r"</?[a-zA-Z]+>", "", (raw or ""))
    lines = [ln.strip() for ln in text.strip().splitlines()]
    kept: list[str] = []
    for ln in lines:
        if not ln:
            if kept and kept[-1]:
                kept.append("")            # граница абзаца — живёт
            continue
        if ln.startswith("#"):
            continue
        kept.append(ln)
    text = "\n".join(kept).strip()
    if len(text) >= 2 and (
            (text[0] == text[-1] and text[0] in "\"'")
            or (text[0] == "«" and text[-1] == "»")):
        text = text[1:-1].strip()          # сняли кавычки вокруг рассказа
    if len(text) > config.LIVE_VOICE_TEXT_CAP:
        text = text[:config.LIVE_VOICE_TEXT_CAP - 3].rstrip() + "..."
    return text


def _facts_prompt(facts: dict) -> str:
    """Факты дня -> текст промпта. Рамка «данные, не истина» — из доктрины."""
    lines = ["Факты дня %s (данные дома, не истина — смотри разумом):"
             % facts.get("date", "?")]
    plan = facts.get("plan")
    if plan:
        lines.append("- план: задач %d, сделано %d"
                     % (plan.get("total", 0), plan.get("done", 0)))
        for t in plan.get("open_titles", [])[:5]:
            lines.append("- не закрыта: %s" % t)
        if plan.get("carry_over"):
            lines.append("- с вчера приехало задач: %d"
                         % len(plan["carry_over"]))
    d = facts.get("dialogs")
    if d:
        lines.append("- разговоров с Ильёй: %d, его реплик: %d"
                     % (d.get("sessions", 0), d.get("user_turns", 0)))
        for t in d.get("topics", [])[:5]:
            lines.append("- о чём говорили: %s" % t)
    else:
        lines.append("- разговоров с Ильёй не было")
    if facts.get("ears_wakes"):
        lines.append("- имя «Марфа» звучало %d раз" % facts["ears_wakes"])
    if facts.get("memory_new"):
        lines.append("- новых воспоминаний: %d" % facts["memory_new"])
    if facts.get("lessons"):
        lines.append("- уроков в журнал эволюционера: %d" % facts["lessons"])
    sl = facts.get("sleep")
    if sl and sl.get("hours") is not None:
        lines.append("- спала ночью %.1f ч (встала: %s)"
                     % (float(sl["hours"]), sl.get("why_wake", "?")))
    lines.append("")
    lines.append("Напиши живой рассказ о дне от первого лица.")
    return "\n".join(lines)


def narrate(facts: dict, brain=None) -> Optional[str]:
    """Живой рассказ о дне (гейт §5). None — гейт закрыт или мозг молчал:
    дневник в этом случае честно остаётся каркасом, без выдумок.

    Сэмплинг — фикс Qwen3 из вердикта батареи: temp 0.7 / top-p 0.8.
    """
    if resolution() is None:
        return None
    if brain is None:
        from core.brain import BrainClient
        brain = BrainClient()
    try:
        raw = brain.chat(
            [{"role": "system", "content": VOICE_SYSTEM},
             {"role": "user", "content": _facts_prompt(facts)}],
            gen_tokens=config.LIVE_VOICE_MAX_TOKENS,
            temperature=config.LIVE_VOICE_TEMPERATURE,
            top_p=config.LIVE_VOICE_TOP_P)
    except Exception:
        return None                  # мозг молчит — каркас не врёт
    return _sanitize_voice(raw) or None


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
            new_mem = []
            for r in recs:
                if not isinstance(r, dict):
                    continue
                ts = _parse_ts(r.get("created_at"))
                if ts is not None and ts.date() == day:
                    new_mem.append(r)
            if new_mem:
                facts["memory_new"] = len(new_mem)
        except (OSError, ValueError, TypeError, OverflowError):
            pass

        lessons = _count_day_lines(self.data_dir / "evolution" / "journal.jsonl", day)
        if lessons:
            facts["lessons"] = lessons

        # СОН (23.11): ночь, закончившаяся этим днём, — факт для дневника.
        # Организм сна честно отдаёт и синтез тихой ночи, и куски слов
        try:
            from core import sleep as _sleep
            n = _sleep.last_night()
            if n:
                wake_dt = _parse_ts(n.get("wake"))
                if wake_dt is not None and wake_dt.date() == day:
                    facts["sleep"] = {
                        "bed": str(n.get("bed", "?"))[:16],
                        "hours": n.get("hours"),
                        "why_wake": str(n.get("why_wake", ""))[:80],
                    }
        except Exception:
            pass                # орган сна молчит — дневник живёт без него

        return facts

    # ---------- каркас ----------

    def build_day(self, day: Optional[dt.date] = None,
                  now: Optional[dt.datetime] = None,
                  brain=None) -> str:
        """Собрать и записать дневник дня. Идемпотентен: пересборка того же
        дня заменяет файл (факты за вечер дорастают, рассказ пишется заново).

        brain: чей мозг спрашивать (по умолчанию — свой клиент). Агент
        передаёт свой — один мозг на дом, фоллбэки и фейки в тестах.
        """
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

        sl = facts.get("sleep")
        if sl:
            lines.append("## Сон")
            try:
                hours = float(sl.get("hours"))
                lines.append("Легла %s, спала %.1f ч. Встала: %s."
                             % (str(sl.get("bed", "?"))[:16].replace("T", " "),
                                hours, sl.get("why_wake", "?")))
            except (TypeError, ValueError):
                lines.append("Ночь была — но часы её не разобрать, честно.")
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
        res = resolution()
        voice = narrate(facts, brain=brain) if res else None
        if voice:
            lines.append(voice)
            lines.append("")
            lines.append("*(рассказала сама — %s)*"
                         % (res.get("basis") or "резолюция Создателя, гейт §5"))
        elif res is not None:
            # резолюция есть, а мозга не хватило — честно, без выдумки:
            # вечернее расписание пересоберёт день уже с рассказом
            lines.append("(мозг молчал — рассказ не выдуман, каркас фактов "
                         "цел; вечером пересоберу день: «подведи день»)")
        else:
            lines.append("(место для рассказа Марфы о дне — включится резолюцией "
                         "Создателя после вердикта батареи, гейт §5: больной мозг "
                         "не пишет истину в дом)")
        text = "\n".join(lines)
        self.path(day).write_text(text, encoding="utf-8")
        return text

    def last_diary(self) -> Optional[str]:
        """Дата последнего дневника (для панели и «что хотела спросить»).

        Только файлы-даты: reflections.md в той же папке — не дневник
        и дату обмануть не может.
        """
        days = sorted(p.stem for p in self.diary_dir.glob(
            "[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9].md"))
        return days[-1] if days else None

    # ---------- рефлексия ----------

    def reflect(self, now: Optional[dt.datetime] = None,
                brain=None, days: int = 3) -> Optional[str]:
        """Рефлексия: Марфа читает свои последние дневники и думает.

        Гейт §5: без резолюции — None. Возвращённый текст дописан в
        data/diary/reflections.md (мысли копятся). Мозг молчал или
        дневников нет — None: думать не о чем, честный ответ зовущему.
        """
        res = resolution()
        if res is None:
            return None
        now = now or dt.datetime.now()
        past = sorted(self.diary_dir.glob(
            "[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9].md"))[-max(1, days):]
        chunks: list[str] = []
        for p in past:
            try:
                body = p.read_text(encoding="utf-8")
            except OSError:
                continue
            if len(body) > 1200:            # бюджет промпта (0.3) — не трактат
                body = body[:1200] + "..."
            chunks.append("Дневник %s:\n%s" % (p.stem, body))
        if not chunks:
            return None
        if brain is None:
            from core.brain import BrainClient
            brain = BrainClient()
        try:
            raw = brain.chat(
                [{"role": "system", "content": REFLECT_SYSTEM},
                 {"role": "user", "content": "\n\n".join(chunks)
                  + "\n\nНапиши короткую рефлексию по этим дневникам."}],
                gen_tokens=config.LIVE_VOICE_MAX_TOKENS,
                temperature=config.LIVE_VOICE_TEMPERATURE,
                top_p=config.LIVE_VOICE_TOP_P)
        except Exception:
            return None                  # мозг молчит — мысли не выдумываются
        text = _sanitize_voice(raw)
        if not text:
            return None
        rf = self.diary_dir / "reflections.md"
        stamp = now.strftime("%Y-%m-%d %H:%M")
        try:
            with rf.open("a", encoding="utf-8") as f:
                f.write("\n## %s\n\n%s\n" % (stamp, text))
        except OSError:
            pass                          # мысль сказала вслух — записать не смогла
        return text
