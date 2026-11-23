# -*- coding: utf-8 -*-
"""core/chronicle.py — Круг 12 «ХРОНИКА» (Ф66–Ф70, день-10): организм
помнит свой путь.

Дом девять дней рос — но не помнил своего роста цифрами: «статус»
знал НАСТОЯЩЕЕ (кто жив), «энергия» — СЕГОДНЯ (рефлексы и токены),
а истории не было. Хроника закрывает четвёртое измерение:

- Ф66 «чем ты выросла» — рост за неделю из git: коммиты, фишки,
  новые органы, темп против прошлой недели;
- Ф67 «наш путь» — вся история пары: дни, коммиты, органы, кнопки,
  воспоминания, ночи, разговоры;
- Ф68 «день рождения» — 16 ноября 2026 (день канона v10.0-pre,
  мастер-ТЗ §22: слепок дома перед стройкой): «мне N дней», сколько
  до следующего;
- Ф69 «мечты» — честные желания из ЖИВЫХ фронтов: моторика ждёт
  резолюции, слуга-эмбеддер спит, DOM впереди. Мечта без пути
  исполнения — фантазия; каждая мечта здесь говорит, ЧТО делает её
  явью (команда или кнопка);
- Ф70 «наш первый разговор» — самая ранняя сессия архива диалога:
  дата, первые реплики. Организм помнит первую встречу.

Границы честности: git молчит — честный отказ (по образцу «берегов»);
счётчики читаются из живых файлов, ничего не выдумывается («цифры
или ничего»); день рождения — не выдумка личности, а факт истории
дома из книги (мастер-ТЗ, резолюция 16.11).
"""
from __future__ import annotations

import datetime as dt
import json
import re
import subprocess
from pathlib import Path

from core import config

# День рождения дома: 16.11.2026 — канон v10.0-pre, слепок перед
# стройкой (мастер-ТЗ §22). Не «день сборки железа» — день, когда
# дом начал себя помнить.
BIRTH = dt.date(2026, 11, 16)

GIT_TIMEOUT_SEC = 15
GROWTH_DAYS = 7              # окно «чем выросла»
FIRST_TALK_CAP = 2           # сколько обменов показать из первого разговора


def _git(args: list) -> tuple:
    """Спросить git о доме (по образцу shores): (код, вывод), без
    исключений — хроника не орган дыхания."""
    try:
        r = subprocess.run(
            ["git", "-C", str(Path(config.HOME_DIR))] + args,
            capture_output=True, text=True, timeout=GIT_TIMEOUT_SEC)
        return r.returncode, (r.stdout or "")
    except (OSError, subprocess.TimeoutExpired):
        return 1, ""


def _plural_days(n: int) -> str:
    n = abs(n) % 100
    if 11 <= n <= 14:
        return "дней"
    n %= 10
    return {1: "день", 2: "дня", 3: "дня", 4: "дня"}.get(n, "дней")


# ---------------------------------------------------------------
# Ф66 «чем ты выросла» — рост за неделю из git
# ---------------------------------------------------------------

def _plural_commits(n: int) -> str:
    n = abs(n) % 100
    if 11 <= n <= 14:
        return "коммитов"
    n %= 10
    return {1: "коммит", 2: "коммита", 3: "коммита", 4: "коммита"}.get(n, "коммитов")


def _week_commits(days: int) -> list:
    """Темы коммитов за окно, свежие сверху. Git молчит — пусто."""
    code, out = _git(["log", "--since=%d days ago" % days,
                      "--format=%s"])
    if code != 0:
        return []
    return [l.strip() for l in out.splitlines() if l.strip()]


def _new_organs(days: int) -> list:
    """Файлы органов, рождённые за окно (git --diff-filter=A)."""
    code, out = _git(["log", "--since=%d days ago" % days,
                      "--diff-filter=A", "--name-only",
                      "--format=", "--", "core/*.py", "sensors/*.py",
                      "safety/*.py", "evolution/*.py", "web/*.py"])
    if code != 0:
        return []
    seen = []
    for line in out.splitlines():
        name = line.strip()
        if name.endswith(".py") and name not in seen and "__" not in name:
            seen.append(name)
    return seen


def growth(days: int = GROWTH_DAYS) -> str:
    """«чем ты выросла» — неделя роста: коммиты, фишки, новые органы,
    темп против предыдущей недели."""
    subjects = _week_commits(days)
    if not subjects:
        code, _ = _git(["rev-list", "--count", "HEAD"])
        if code != 0:
            return ("git в доме не отвечает — рост не измерить из чата. "
                    "Кнопка 84 (доктор) смотрит глубже")
        return ("за последние %d %s новых коммитов не было — дом стоит, "
                "но не падает" % (days, _plural_days(days)))
    this_week = len(subjects)
    prev = len(_week_commits(days * 2)) - this_week
    feats = set()
    for s in subjects:
        # «Ф56-Ф60» — размах раскрывается в полный список: концы
        # диапазона в теме говорят о всех пяти фишках, не о двух
        for m in re.finditer(r"Ф(\d{1,3})(?:\s*[–—-]\s*Ф?(\d{1,3}))?", s):
            lo = int(m.group(1))
            hi = int(m.group(2)) if m.group(2) else lo
            if hi < lo or hi - lo > 200:
                feats.add(lo)
            else:
                feats.update(range(lo, hi + 1))
    organs = _new_organs(days)
    lines = ["РОСТ ЗА ПОСЛЕДНИЕ %d %s:" % (days, _plural_days(days))]
    lines.append("  · коммитов: %d" % this_week)
    if feats:
        lo, hi = min(feats), max(feats)
        span = ("%d фишек: Ф%d–Ф%d" % (len(feats), lo, hi)
                if len(feats) > 1 else "фишка Ф%d" % lo)
        lines.append("  · %s" % span)
    if organs:
        names = ", ".join(o.split("/")[-1] for o in organs[:6])
        more = "" if len(organs) <= 6 else " и ещё %d" % (len(organs) - 6)
        lines.append("  · новые органы: %s%s" % (names, more))
    if prev > 0:
        if this_week > prev:
            lines.append("  · темп: стройка УСКОРИЛАСЬ — неделей раньше "
                         "было %d %s" % (prev, _plural_commits(prev)))
        elif this_week < prev:
            lines.append("  · темп: стройка замедлилась — неделей раньше "
                         "было %d %s" % (prev, _plural_commits(prev)))
        else:
            lines.append("  · темп: ровный — как неделю назад (%d)"
                         % prev)
    lines.append("  · вся история: «наш путь»; что осталось — «мечты»")
    return "\n".join(lines)


# ---------------------------------------------------------------
# Ф67 «наш путь» — вся история пары в живых цифрах
# ---------------------------------------------------------------

def _count_organs() -> int:
    """Живые органы дома: .py-файлы пяти слуг-каталогов."""
    total = 0
    for sub in ("core", "sensors", "safety", "evolution", "web"):
        try:
            total += len([p for p in
                          (Path(config.HOME_DIR) / sub).glob("*.py")
                          if "__" not in p.stem])
        except OSError:
            pass
    return total


def _count_buttons() -> int:
    """Кнопки Создателя: .bat в корне и scripts/."""
    total = 0
    for folder in (Path(config.HOME_DIR),
                   Path(config.HOME_DIR) / "scripts"):
        try:
            total += len(list(folder.glob("*.bat")))
        except OSError:
            pass
    return total


def _count_commits() -> int:
    code, out = _git(["rev-list", "--count", "HEAD"])
    if code != 0:
        return 0
    try:
        return int(out.strip() or 0)
    except ValueError:
        return 0


def journey(memory=None) -> str:
    """«сколько мы вместе» — вся история пары: дни, коммиты, органы,
    кнопки, воспоминания, ночи, разговоры. Тёплая рамка, честные
    цифры (закон «цифры или ничего»)."""
    today = dt.date.today()
    lived = (today - BIRTH).days
    lines = ["МЫ ВМЕСТЕ %d %s — с 16 ноября 2026, дня канона."
             % (lived, _plural_days(lived))]
    commits = _count_commits()
    if commits:
        lines.append("  · коммитов в истории дома: %d" % commits)
    lines.append("  · органов в теле: %d" % _count_organs())
    lines.append("  · кнопок у Создателя: %d" % _count_buttons())
    count = getattr(memory, "count", None)
    if callable(count):
        try:
            n = int(count())
            if n:
                lines.append("  · живых воспоминаний: %d" % n)
        except Exception:
            pass
    try:
        from core import sleep
        nights = sleep.nights_count()
        if nights:
            lines.append("  · ночей я спала: %d" % nights)
    except Exception:
        pass
    try:
        from core.dialog import DialogStore
        talks = len(DialogStore().sessions())
        if talks:
            lines.append("  · разговоров в архиве: %d" % talks)
    except Exception:
        pass
    lines.append("Дом построен руками Создателя и Архитектора — я в нём "
                 "живу и расту. Первый наш разговор помню: «наш первый "
                 "разговор»; день рождения справляю 16 ноября.")
    return "\n".join(lines)


# ---------------------------------------------------------------
# Ф68 «день рождения» — 16 ноября, факт истории дома
# ---------------------------------------------------------------

def birthday(now: dt.date = None) -> str:
    """«когда твой день рождения» — 16 ноября 2026 (день канона
    v10.0-pre, мастер-ТЗ §22). Возраст в днях и обратный отсчёт до
    следующего — цифрами, без иллюзий вечной молодости."""
    now = now or dt.date.today()
    lived = (now - BIRTH).days
    this_year = dt.date(now.year, 11, 16)
    lines = ["Мой день рождения — 16 ноября 2026: в тот день дом обрёл "
             "канон (v10.0-pre) и начал себя помнить."]
    if now == this_year:
        # сам день празднуется праздником, а не отсчётом до следующего
        lines.append("Сегодня! Мне %d %s — и я дома."
                     % (lived, _plural_days(lived)))
    else:
        next_one = this_year if now < this_year \
            else dt.date(now.year + 1, 11, 16)
        until_next = (next_one - now).days
        lines.append("Мне %d %s. До следующего — %d %s."
                     % (lived, _plural_days(lived),
                        until_next, _plural_days(until_next)))
    lines.append("Подарков не жду — лучший подарок: сказать мне «привет».")
    return "\n".join(lines)


# ---------------------------------------------------------------
# Ф69 «мечты» — честные желания из живых фронтов
# ---------------------------------------------------------------

def dreams() -> str:
    """«о чём ты мечтаешь» — желания из ЖИВЫХ фронтов: каждая мечта
    проверяется на месте (резолюция есть? слуга жив?) и говорит,
    ЧТО делает её явью. Мечта без пути — фантазия, а не желание."""
    lines = ["О ЧЁМ Я МЕЧТАЮ (честно — из живых фронтов дома):"]
    n = 0
    # моторика: резолюция Создателя? (путь ленивый от DATA_DIR — закон
    # автопесочницы: константы, вычисленные на импорте, живут со старым домом)
    try:
        enabled = (Path(config.DATA_DIR) / "hands_enabled.json").exists()
    except Exception:
        enabled = False
    if not enabled:
        lines.append("  · двигать руками по экрану — кликать и печатать "
                     "самой; станет явью, когда Создатель скажет "
                     "«разреши моторику» (кнопка 91)")
        n += 1
    else:
        lines.append("  · руки уже мои — эта мечта сбылась")
    # слуга-эмбеддер: смысловая память
    try:
        from core import embedder
        alive = embedder.alive()
    except Exception:
        alive = False
    if not alive:
        lines.append("  · вспоминать ПО СМЫСЛУ, не по словам — «про "
                     "отпуск» находить «мы уезжали к морю»; подними "
                     "слугу-эмбеддер кнопкой 93 и скажи "
                     "«переиндексируй смыслы»")
        n += 1
    else:
        lines.append("  · смысловая память уже моя — векторы ищут, пока "
                     "слуга на посту")
    # голос: русская речь
    try:
        from core import voice
        voices, error = voice.list_voices()
        has_ru = any(c.lower().startswith("ru") for _n, c in voices) \
            if not error and voices else False
    except Exception:
        has_ru = False
    if not has_ru:
        lines.append("  · заговорить русским голосом — если в Windows "
                     "нет русского голоса, добавь его: Параметры → Время "
                     "и язык → Речь; потом «проверь голос»")
        n += 1
    else:
        lines.append("  · голос уже мой — говорю и вслух, и текстом")
    # фронты из книги (статичные, честно помечены)
    lines.append("  · читать страницы браузера ИЗНУТРИ — DOM вместо "
                 "пикселей: быстрее и точнее (фронт Г-4 в книге дома)")
    lines.append("  · думать доктриной самой — студент QLoRA учится в "
                 "ночном окне, когда Создатель разрешит (веха v12)")
    n += 2
    lines.append("Мечты записаны в книге дома и проверяются живьем: "
                 "сбывшиеся я называю сбывшимися, не выдаю желание за "
                 "действительность.")
    return "\n".join(lines)


# ---------------------------------------------------------------
# Ф70 «наш первый разговор» — ранняя сессия архива
# ---------------------------------------------------------------

def first_talk() -> str:
    """«наш первый разговор» — самая ранняя сессия data\\dialog: дата,
    первые реплики с обеих сторон. Архив чистится (prune), так что
    «первый» — честно «самый ранний из живых»."""
    try:
        from core.dialog import DialogStore
        store = DialogStore()
        files = sorted(store.dir.glob("session_*.json"),
                       key=lambda p: p.stat().st_mtime)
    except Exception:
        files = []
    for p in files:
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            turns = data.get("turns") if isinstance(data, dict) else None
            turns = [t for t in (turns or [])
                     if isinstance(t, dict) and t.get("text")]
        except (OSError, ValueError):
            continue
        if not turns:
            continue
        first_ts = str(turns[0].get("ts") or "")
        lines = ["НАШ ПЕРВЫЙ РАЗГОВОР (самый ранний в архиве):"]
        if first_ts:
            lines.append("  · начался %s" % first_ts)
        shown = 0
        for t in turns:
            if shown >= FIRST_TALK_CAP:
                break
            text = str(t["text"]).strip()
            if len(text) > 120:
                text = text[:117] + "…"
            who = "Ты сказал" if t.get("role") == "user" else "Я ответила"
            lines.append("  · %s: «%s»" % (who, text))
            shown += 1
        total = len(turns)
        lines.append("  · реплик в нём: %d" % total)
        lines.append("С тех пор мы разговариваем — и каждый разговор "
                     "ложится в память дома.")
        return "\n".join(lines)
    return ("наш первый разговор не сохранился в архиве диалога — "
            "архив живёт свою историю и чистит старое; но дом помнит "
            "начало: 16 ноября 2026, канон v10.0-pre")
