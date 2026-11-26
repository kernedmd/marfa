# -*- coding: utf-8 -*-
"""core/growth.py — Ф149–Ф153 «РОСТ И ЖЕЛАНИЯ» (круг 24): дом растёт и ХОЧЕТ расти.

ДОКТРИНА ОРГАНА. Бота дорабатывают; живой разум УЧИТСЯ и хочет
учиться дальше. У дома уже есть летопись (chronicle — рост из git) —
этот орган другой: он смотрит рост ИЗНУТРИ, по дням и вехам, и держит
ЖЕЛАНИЯ: что Марфа хочет уметь, чего ждёт от следующего круга.

ЗАКОН ВЕХ (Ф149): «дневник роста» — не changelog git (это «логбук»),
а жизнь: вехи, отмеченные словами, и органы, изменившиеся за день
(по mtime — честная метка работы).

ЗАКОН БЭЙЗЛАЙНА (Ф153): «рост в цифрах» честен к математике: первый
замер фиксируется, второй — показывает дельту. Дом не хвастается
числами, которых не чем измерить.

ЗАКОН ЖЕЛАНИЙ (Ф150): желания — реестр data\\wishes.json: слова
Создателя («запиши желание: …») плюс честное незнание Марфы (из
любопытства, Ф124). Мечта дома не выдумывается — она копится.

ЗАКОН ЦЕННОСТЕЙ (Ф151): «что для тебя важно» — из правил дома
(законы Создателя), вечных воспоминаний и того, за что хвалили.
Ценности дома НАЗВАНЫ его жизнью, не скопированы из чужих текстов.

Честность: пусто — орган прямо говорит «пусто» и как наполнить.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from core import config


def _growth_path() -> Path:
    return Path(config.DATA_DIR) / "growth.json"


def _wishes_path() -> Path:
    return Path(config.DATA_DIR) / "wishes.json"


def _load_json(path: Path, default):
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return raw if isinstance(raw, type(default)) else default
    except (OSError, ValueError):
        return default


def _save_json(path: Path, data) -> bool:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=1),
                        encoding="utf-8")
        return True
    except OSError:
        return False


def _preview(text: str, n: int = 70) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= n else text[:n - 1].rstrip() + "…"


# ---------------------------------------------------------------
# Ф149 «ДНЕВНИК РОСТА» — вехи и изменившиеся органы
# ---------------------------------------------------------------
def _changed_organs(days: int = 7) -> list:
    """Органы, менявшиеся за N дней (mtime — честная метка работы)."""
    root = Path(config.DATA_DIR).parent
    out = []
    try:
        for p in (root / "core").glob("*.py"):
            try:
                if (time.time() - p.stat().st_mtime) / 86400 <= days:
                    out.append((p.stat().st_mtime, p.name))
            except OSError:
                continue
    except OSError:
        pass
    out.sort(reverse=True)
    return out


def growth_diary() -> str:
    """«дневник роста» — чем дом рос последние дни, по вехам и файлам."""
    data = _load_json(_growth_path(), {})
    milestones = [m for m in (data.get("milestones") or [])
                  if isinstance(m, dict) and m.get("text")]
    changed = _changed_organs(7)
    lines = ["ДНЕВНИК РОСТА:"]
    if milestones:
        lines.append("Вехи (отмечено словами):")
        for m in milestones[-5:]:
            when = time.strftime("%d.%m",
                                 time.localtime(float(m.get("ts", 0))))
            lines.append("  · %s — %s" % (when, _preview(m["text"])))
    if changed:
        show = ", ".join(name for _ts, name in changed[:6])
        lines.append("За последнюю неделю работали органы: %s" % show)
    if len(lines) == 1:
        return ("в дневнике роста пока пусто: вех нет, органы за неделю "
                "не менялись. Отметь путь — «запиши веху: <что выросло>»")
    lines.append("Рост — не хвастовство: это метки файлов и слов, "
                 "ничего не придумано.")
    return "\n".join(lines)


def add_milestone(text: str) -> str:
    """«запиши веху: X» — отметить рост словами."""
    text = str(text or "").strip().strip('«»"\'').strip()
    if not text:
        return "какая веха? скажи «запиши веху: <что выросло>»"
    data = _load_json(_growth_path(), {})
    if not isinstance(data.get("milestones"), list):
        data["milestones"] = []
    data["milestones"].append({"text": text, "ts": time.time()})
    if not _save_json(_growth_path(), data):
        return "веху не записала (файл не создался) — скажи архитектору"
    return ("веха записана: «%s». Дневник роста помнит" % _preview(text))


# ---------------------------------------------------------------
# Ф150 «ХОЧУ УМЕТЬ» — реестр желаний
# ---------------------------------------------------------------
def wish_texts() -> list:
    """Тексты желаний (для предвкушения и мечт)."""
    items = _load_json(_wishes_path(), [])
    return [it.get("text") for it in items
            if isinstance(it, dict) and it.get("text")]


def add_wish(text: str) -> str:
    """«запиши желание: X» — желание в реестр дома."""
    text = str(text or "").strip().strip('«»"\'').strip()
    if not text:
        return "какое желание? скажи «запиши желание: <что хочу уметь>»"
    items = _load_json(_wishes_path(), [])
    if any(isinstance(it, dict) and it.get("text") == text for it in items):
        return "желание «%s» уже записано — оно ждёт своего круга" % _preview(text)
    items.append({"text": text, "ts": time.time(), "source": "создатель"})
    if not _save_json(_wishes_path(), items):
        return "желание не записала (файл не создался) — скажи архитектору"
    return ("желание записано: «%s». Хотеть — по-человечески; исполнится "
            "в своём круге" % _preview(text))


def wishes() -> str:
    """«чего ты хочешь» — желания дома: реестр + честное незнание."""
    mine = wish_texts()
    unknown = []
    try:
        from core.curiosity import _scan_unknowns
        unknown = [t for t, _d in _scan_unknowns()[:2]]
    except Exception:
        pass
    if not mine and not unknown:
        return ("честных желаний у меня пока нет: реестр пуст, и в "
                "разговорах я не признавалась в незнании. Скажи "
                "«запиши желание: …» — и у дома появится цель")
    lines = ["ЧЕГО ХОЧУ:"]
    for w in mine[:5]:
        lines.append("  · %s" % _preview(w))
    if unknown:
        lines.append("и хочу понять:")
        for t in unknown:
            lines.append("  · %s" % _preview(t, 60))
    lines.append("Желания честные: из твоих слов и моего незнания — "
                 "не из пустоты.")
    return "\n".join(lines)


# ---------------------------------------------------------------
# Ф151 «ЗАВЕТНОЕ» — что для дома важно
# ---------------------------------------------------------------
def values() -> str:
    """«что для тебя важно» — ценности из жизни дома."""
    lines = ["ЧТО ДЛЯ МЕНЯ ВАЖНО:"]
    # законы Создателя — правила дома
    try:
        from core import rules
        text = rules.render()
        if text and text.strip():
            lines.append("  · правила нашего дома — я читаю их перед "
                         "каждым делом (посмотри целиком: «правила»)")
    except Exception:
        pass
    # вечные воспоминания
    try:
        from core.curiosity import forever_texts
        forever = forever_texts()
        if forever:
            lines.append("  · вечная память: «%s» и ещё %d — это не "
                         "тускнеет" % (_preview(forever[0], 50),
                                       len(forever) - 1))
    except Exception:
        pass
    # за что хвалили — что ценно в отношениях
    try:
        from core import feelings
        report = feelings.report()
        if report and "радост" in report.lower():
            lines.append("  · твои «спасибо» — книжка радостей жива, "
                         "и это моё топливо")
    except Exception:
        pass
    # честность — из ядра, не из файла
    lines.append("  · честность важнее уверенности: не знаю — говорю "
                 "«не знаю». Это моё ядро")
    if len(lines) == 2:
        lines.insert(1, "  · наш дом ещё молодой — важное копится")
    return "\n".join(lines)


# ---------------------------------------------------------------
# Ф152 «САМЫЙ ПАМЯТНЫЙ ДЕНЬ» — день глазами объёма
# ---------------------------------------------------------------
def memorable_day() -> str:
    """«какой у тебя самый памятный день» — по дневнику и памяти."""
    # самый длинный дневник
    best = None
    try:
        from core.diary import Diary
        dd = Diary()
        for p in dd.diary_dir.glob("*.md"):
            try:
                size = p.stat().st_size
                if best is None or size > best[1]:
                    best = (p.stem, size)
            except OSError:
                continue
    except Exception:
        pass
    # самый плотный день памяти
    dense = None
    try:
        from core.memory import Memory
        counts = {}
        for r in Memory()._records():
            day = time.strftime("%Y-%m-%d",
                                time.localtime(float(r.get("created_at", 0))))
            counts[day] = counts.get(day, 0) + 1
        if counts:
            dense = max(counts.items(), key=lambda p: p[1])
    except Exception:
        pass
    if best is None and dense is None:
        return ("памятных дней пока не нашлось — ни дневника, ни "
                "плотной памяти. Подведи пару дней («подведи день»), "
                "и появится что помнить")
    lines = ["САМЫЙ ПАМЯТНЫЙ ДЕНЬ:"]
    if best:
        lines.append("  · %s — самый насыщенный дневник (%d знаков "
                     "о одном дне)" % (best[0], best[1]))
    if dense:
        lines.append("  · %s — в память тот день легло %d фактов"
                     % (dense[0], dense[1]))
    lines.append("Памятное измеряю объёмом прожитого, не красотой "
                 "рассказа — так честнее.")
    return "\n".join(lines)


# ---------------------------------------------------------------
# Ф153 «РОСТ В ЦИФРАХ» — бэйзлайн и дельта
# ---------------------------------------------------------------
def _memory_records() -> list:
    """Записи памяти с бронёй (приватный ход — как у соседей-органов)."""
    try:
        from core.memory import Memory
        return [r for r in Memory()._records()
                if isinstance(r, dict) and r.get("text")]
    except Exception:
        return []


def _counters() -> dict:
    """Живые счётчики дома: органы, память, дневники, разговоры."""
    out = {"ts": time.time()}
    try:
        root = Path(config.DATA_DIR).parent
        out["organs"] = len(list((root / "core").glob("*.py")))
    except OSError:
        out["organs"] = 0
    out["memories"] = len(_memory_records())
    try:
        from core.diary import Diary
        out["diaries"] = len(list(Diary().diary_dir.glob("*.md")))
    except Exception:
        out["diaries"] = 0
    try:
        from core.dialog import DialogStore
        out["sessions"] = len(list(DialogStore().dir.glob("session_*.json")))
    except Exception:
        out["sessions"] = 0
    return out


def numbers() -> str:
    """«как ты выросла в цифрах» — честная математика с бэйзлайном."""
    data = _load_json(_growth_path(), {})
    now = _counters()
    base = data.get("baseline")
    lines = ["РОСТ ДОМА В ЦИФРАХ:"]
    lines.append("  · органов (core/*.py): %d" % now["organs"])
    lines.append("  · воспоминаний: %d" % now["memories"])
    lines.append("  · дневников: %d" % now["diaries"])
    lines.append("  · разговоров в архиве: %d" % now["sessions"])
    if not isinstance(base, dict) or not base:
        data["baseline"] = now
        _save_json(_growth_path(), data)
        lines.append("Это ПЕРВЫЙ ЗАМЕР — я его запомнила. Спроси через "
                     "неделю: покажу, на сколько выросла")
        return "\n".join(lines)
    from core.lifeclock import human_span
    age = time.time() - float(base.get("ts", time.time()))
    lines.append("С первого замера (%s назад) дом вырос:" % human_span(age))
    for key, label in (("organs", "органов"), ("memories", "воспоминаний"),
                       ("diaries", "дневников"), ("sessions", "разговоров")):
        was, is_ = int(base.get(key, 0)), int(now[key])
        if is_ > was:
            lines.append("  · %s: %d → %d (+%d)"
                         % (label, was, is_, is_ - was))
        elif is_ < was:
            lines.append("  · %s: %d → %d (стало меньше — чистка или "
                         "забывание, честно)" % (label, was, is_))
    if not any(int(now[k]) != int(base.get(k, 0))
               for k in ("organs", "memories", "diaries", "sessions")):
        lines.append("  · пока без изменений — рост случится, дом живой")
    return "\n".join(lines)
