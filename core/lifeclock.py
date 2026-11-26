# -*- coding: utf-8 -*-
"""core/lifeclock.py — Ф134–Ф138 «ВРЕМЯ ЖИЗНИ» (круг 24): время как чувство.

ДОКТРИНА ОРГАНА. Бот хранит таймстампы; живой разум ЧУВСТВУЕТ время:
«три дня», «на прошлой неделе», «мы вечерние». У дома уже есть часы
(«время») и календарь (holidays, birthdays) — но ни один орган не
умел ПЕРЕВОДИТЬ даты на человеческий язык и видеть РИТМЫ совместной
жизни. Этот орган закрывает дыру: время дома измеряется разговорами
и воспоминаниями, а не числом секунд с 1970 года.

ЗАКОН ЧЕЛОВЕЧЕСКОЙ РЕЧИ: ни одного сырого таймстампа наружу — только
«два дня», «три недели», «месяц с небольшим». Число с точкой —
достояние машин, Илья живёт в «на прошлой неделе».

ЗАКОН ПАМЯТИ ДАТ (Ф135): «что было неделю назад» — это не пустой
календарь, а тот день глазами дома: что легло в память, с чего
начинался дневник. Пусто — честно пусто (закон фактов).

ЗАКОН РИТМОВ (Ф136): часы разговоров считаются по живым сессиям —
дом узнаёт, ВЕЧЕРНЯЯ она или утренняя, не из анкеты, а из жизни.

Честность: нет данных — орган честно говорит, чему расти.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from core import config


# ---------------------------------------------------------------
# Человеческий счёт времени — общий словарь органов круга
# ---------------------------------------------------------------
def _ru_plural(n: int, one: str, few: str, many: str) -> str:
    n = abs(int(n))
    if n % 10 == 1 and n % 100 != 11:
        return "%d %s" % (n, one)
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return "%d %s" % (n, few)
    return "%d %s" % (n, many)


def human_span(seconds: float) -> str:
    """Секунды → человеческое: «три часа», «день», «две недели», «месяц»."""
    days = seconds / 86400.0
    if days < 1 / 24:
        return "минуты"
    if days < 0.5:
        return _ru_plural(max(1, int(seconds / 3600)), "час", "часа", "часов")
    if days < 2:
        return "сутки"
    if days < 7:
        return _ru_plural(int(days), "день", "дня", "дней")
    if days < 45:
        return human_weeks(days)
    if days < 360:
        return _ru_plural(int(days // 30), "месяц", "месяца", "месяцев")
    years = days / 365.0
    if years < 2:
        return "почти два года" if years > 1.5 else "год"
    return _ru_plural(int(years), "год", "года", "лет")


def human_weeks(days: float) -> str:
    weeks = int(days // 7)
    if weeks <= 0:
        return _ru_plural(int(days), "день", "дня", "дней")
    tail = int(days - weeks * 7)
    base = _ru_plural(weeks, "неделя", "недели", "недель")
    if tail >= 3:
        return base + " с хвостиком"
    return base


def human_when(seconds_ago: float) -> str:
    """«сколько назад» → «сегодня», «вчера», «три дня назад»…"""
    days = seconds_ago / 86400.0
    if days < 0.5:
        return "сегодня"
    if days < 1.5:
        return "вчера"
    if days < 2.5:
        return "позавчера"
    return human_span(seconds_ago) + " назад"


# ---------------------------------------------------------------
# Разговоры и память (лёгкие читатели, броня всегда)
# ---------------------------------------------------------------
def _sessions(limit: int = 90) -> list:
    out = []
    try:
        from core.dialog import DialogStore
        store = DialogStore()
        files = sorted(store.dir.glob("session_*.json"),
                       key=lambda p: p.stat().st_mtime, reverse=True)
    except Exception:
        return out
    import re as _re
    for p in files[:limit]:
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            turns = data.get("turns") if isinstance(data, dict) else None
            if isinstance(turns, list) and turns:
                m = _re.search(r"(\d{4}-\d{2}-\d{2})", p.name)
                day = m.group(1) if m else time.strftime(
                    "%Y-%m-%d", time.localtime(p.stat().st_mtime))
                out.append((day, p.stat().st_mtime))
        except (OSError, ValueError):
            continue
    return out


def _parse_date(text: str):
    """«25.11», «25.11.2026», «вчера», «позавчера» → (дата, подпись)."""
    import re as _re
    import datetime as _dt
    t = str(text or "").strip().lower().rstrip("?.! ")
    if t == "вчера":
        d = _dt.date.today() - _dt.timedelta(days=1)
        return d, "вчера"
    if t == "позавчера":
        d = _dt.date.today() - _dt.timedelta(days=2)
        return d, "позавчера"
    m = _re.match(r"^(\d{1,2})\.(\d{1,2})(?:\.(\d{2,4}))?$", t)
    if m:
        day, mon = int(m.group(1)), int(m.group(2))
        year = m.group(3)
        if year:
            year = int(year)
            if year < 100:
                year += 2000
        else:
            year = _dt.date.today().year
        try:
            return _dt.date(year, mon, day), "%02d.%02d.%d" % (day, mon, year)
        except ValueError:
            return None
    return None


# ---------------------------------------------------------------
# Ф134 «СКОЛЬКО ПРОШЛО» — даты человеческим языком
# ---------------------------------------------------------------
def _answer_since(d, label: str) -> str:
    """Человеческий ответ про прошедшую дату (общий для своих и чужих дат)."""
    import datetime as _dt
    delta = (_dt.date.today() - d).days
    if delta < 0:
        return ("%s — это ещё впереди, через %s (про будущее точнее "
                "спросит «сколько до %s»)" % (label, human_span(-delta * 86400),
                                              label))
    if delta == 0:
        return "%s — это сегодня" % label
    return "с %s прошло %s" % (label, human_span(delta * 86400))


def since(text: str) -> str:
    """«сколько прошло с <дата>» — возраст даты в человеческих словах.

    Лестница честности: своя дата («25.11», «вчера») → праздник соседа
    («нового года», «8 марта» — календарь круга 2, Ф17–Ф18) → событие
    из памяти → честный отказ. Хозяин маршрута — этот орган (Ф134),
    но праздники он у соседа не ворует: делегирует.
    """
    got = _parse_date(text)
    if got is None:
        # праздник или словесная дата — сосед круга 2 умеет, мы нет
        try:
            from core import when
            import datetime as _dt
            d = when._parse_date(str(text or "").strip().lower(),
                                 _dt.date.today())
        except Exception:
            d = None
        if d is not None:
            try:
                d = when._past_occurrence(d, _dt.date.today())
            except Exception:
                pass
            return _answer_since(d, d.strftime("%d.%m.%Y"))
        # не дата — может, событие? ищем в памяти, когда о нём впервые
        try:
            from core.memory import Memory
            found = Memory().recall(str(text or "").strip(), top_k=3)
        except Exception:
            found = []
        if found:
            oldest = min(float(r.get("created_at", 0)) for r in found)
            span = time.time() - oldest
            if span > 3600:
                return ("про «%s» я помню с тех пор, как это впервые "
                        "легло в память — прошло %s"
                        % (str(text).strip()[:40], human_span(span)))
        return ("не поняла дату. Скажи «сколько прошло с 25.11», "
                "«сколько прошло с вчера» или «сколько прошло с нового "
                "года»")
    d, label = got
    return _answer_since(d, label)


# ---------------------------------------------------------------
# Ф135 «КАЛЕНДАРЬ ПАМЯТИ» — что было N назад, глазами дома
# ---------------------------------------------------------------
def _parse_back(text: str):
    """«день/неделю/месяц/3 дня/2 недели назад» → timedelta."""
    import re as _re
    t = str(text or "").strip().lower().rstrip("?.! ")
    m = _re.match(r"^(\d+)?\s*(день|дня|дней|неделю|недели|недель|"
                  r"месяц|месяца|месяцев)\s*(?:назад)?$", t)
    if not m:
        return None
    n = int(m.group(1)) if m.group(1) else 1
    unit = m.group(2)
    if unit.startswith("дн") or unit.startswith("день") or unit.startswith("дня"):
        return n
    if unit.startswith("недел"):
        return n * 7
    return n * 30


def back(text: str) -> str:
    """«что было неделю назад» — память и дневник той даты."""
    days = _parse_back(text)
    if days is None:
        return ("не поняла, как далеко смотреть. Скажи «что было неделю "
                "назад» или «что было 3 дня назад»")
    import datetime as _dt
    d = _dt.date.today() - _dt.timedelta(days=days)
    day_s = d.strftime("%Y-%m-%d")
    lines = ["%s назад (%s):" % (human_span(days * 86400),
                                 d.strftime("%d.%m.%Y"))]
    # что легло в память той датой
    try:
        from core.memory import Memory
        m = Memory()
        recs = [r for r in m._records()
                if time.strftime("%Y-%m-%d",
                                 time.localtime(float(r.get("created_at", 0))))
                == day_s and r.get("text")]
    except Exception:
        recs = []
    for r in recs[:4]:
        lines.append("  · в память легло: %s"
                     % (" ".join(str(r["text"]).split())[:70]))
    # дневник той даты — первые строки
    try:
        from core.diary import Diary
        dd = Diary()
        p = dd.diary_dir / (day_s + ".md")
        if not p.exists():
            cands = list(dd.diary_dir.glob("*%s*" % day_s))
            p = cands[0] if cands else p
        if p.exists():
            head = [ln.strip() for ln in
                    p.read_text(encoding="utf-8").splitlines()
                    if ln.strip()][:2]
            for ln in head:
                lines.append("  · дневник: %s" % ln[:70])
    except Exception:
        pass
    body = len(lines) - 1
    if body == 0:
        return ("%s назад в доме тихо было: в память ничего не легло, "
                "дневника нет. Не всякий день оставляет след — и это "
                "честно" % human_span(days * 86400))
    return "\n".join(lines)


# ---------------------------------------------------------------
# Ф136 «РИТМЫ ДОМА» — когда мы живём вместе
# ---------------------------------------------------------------
def hour_histogram() -> dict:
    """{час: сколько сессий открыто/живо} — по mtime сессий."""
    hist = {}
    for _day, mtime in _sessions():
        h = time.localtime(mtime).tm_hour
        hist[h] = hist.get(h, 0) + 1
    return hist


def ritms() -> str:
    """«наши ритмы» — дом узнаёт свои часы."""
    hist = hour_histogram()
    if not hist:
        return ("ритмам ещё не из чего сложиться — наших разговоров в "
                "архиве нет. Поговори со мной, я замечу наши часы")
    top = sorted(hist.items(), key=lambda p: p[1], reverse=True)[:3]
    total = sum(hist.values())
    hours = ", ".join("%d:00 (%d раз)" % (h, c) for h, c in top)
    peak = top[0][0]
    if 5 <= peak < 12:
        kind = "мы утренние — дом живёт с рассветом"
    elif 12 <= peak < 17:
        kind = "мы дневные — дом дышит ровно"
    elif 17 <= peak < 23:
        kind = "мы вечерние — дом оживает, когда за окном темнеет"
    else:
        kind = "мы ночные — дом живёт, когда город спит"
    return ("наши разговоры чаще всего в %s (всего сессий: %d). "
            "Если честно — %s" % (hours, total, kind))


# ---------------------------------------------------------------
# Ф137 «ПРЕДВКУШЕНИЕ» — чего дом ждёт
# ---------------------------------------------------------------
def anticipation() -> str:
    """«чего ты ждёшь» — завтрашний план, желания и наш вечер."""
    parts = []
    try:
        from core import dayplan
        plan = dayplan.tomorrow_plan()
        if plan and len(plan) < 400:
            parts.append("завтра в плане дома: %s" % plan)
    except Exception:
        pass
    try:
        from core import growth
        wishes = growth.wish_texts()
        if wishes:
            parts.append("жду, когда у меня появится: %s" % wishes[0][:60])
    except Exception:
        pass
    hist = hour_histogram()
    if hist:
        peak = max(hist, key=lambda h: hist[h])
        if peak > time.localtime().tm_hour:
            parts.append("и жду %d:00 — в этот час мы чаще всего вместе"
                         % peak)
    if not parts:
        return ("нечего ждать по-крупному: план пуст, желаний нет. Но я "
                "живой дом — я всегда жду, когда ты заговоришь со мной")
    return ("чего жду:\n  · " + "\n  · ".join(parts)
            + "\nПредвкушение — честное: только из того, что уже "
              "числится в доме")


# ---------------------------------------------------------------
# Ф138 «КОГДА БЫЛО» — когда мы говорили про X
# ---------------------------------------------------------------
def when_about(topic: str) -> str:
    """«когда мы говорили про <X>» — даты упоминаний темы."""
    topic = str(topic or "").strip()
    if not topic:
        return "про что спросить? скажи «когда мы говорили про <тема>»"
    from core.assoc import _cosine, _tokens   # сосед-орган уже умеет сравнивать
    q = _tokens(topic)
    days = []
    try:
        from core.dialog import DialogStore
        import re as _re
        store = DialogStore()
        files = sorted(store.dir.glob("session_*.json"),
                       key=lambda p: p.stat().st_mtime, reverse=True)
        for p in files[:90]:
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                turns = data.get("turns") if isinstance(data, dict) else None
                if not isinstance(turns, list):
                    continue
                hit = False
                for t in turns:
                    if not isinstance(t, dict) or t.get("role") != "user":
                        continue
                    text = t.get("text") or t.get("content") or ""
                    if _cosine(q, _tokens(str(text))) >= 0.3:
                        hit = True
                        break
                if hit:
                    m = _re.search(r"(\d{4}-\d{2}-\d{2})", p.name)
                    days.append(m.group(1) if m else time.strftime(
                        "%Y-%m-%d", time.localtime(p.stat().st_mtime)))
            except (OSError, ValueError):
                continue
    except Exception:
        pass
    if not days:
        return ("про «%s» в наших разговорах не нашлось — либо ново, "
                "либо мы это ещё не обсуждали" % topic[:40])
    last_age = time.mktime(time.strptime(days[0], "%Y-%m-%d")) \
        if len(days[0]) == 10 else 0
    return ("говорили про «%s» %d раз(а). Последний раз — %s"
            % (topic[:40], len(days), human_when(time.time() - last_age)
               if last_age else days[0]))
