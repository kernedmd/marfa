# -*- coding: utf-8 -*-
r"""core/musing.py — МЫСЛИ ДОМА: фоновое размышление и сны (23.11).

«Поразмышляй» уже жило (рефлексия по дневникам, гейт §5) — но думала
Марфа только ПО ПРИКАЗУ. Теперь организм думает и сам:

- ФОНОВАЯ МЫСЛЬ: когда дом тихий (Илья не пишет MUSING_IDLE_HOURS) и
  организм не спит, стремление раз в MUSING_INTERVAL_SECS предлагает
  ей подумать. Семя мысли — из фактов: открытый вопрос, случайное
  воспоминание, вчерашний дневник; к нему — строка чувств (мысль
  живёт в настроении дня). Мысль (2-4 предложения, от первого лица)
  ложится в data\\diary\\musings.md; «о чём думаешь?» покажет свежую,
  а не будет выдумывать задним числом.
- СОН-СНОВИДЕНИЕ: утром (07:10, сразу после окна сна) из вчерашнего
  дневника + чувств + последних мыслей пишется короткий сон —
  data\\diary\\dreams.md. Утреннее «доброе утро» принесёт его с собой.

ГЕЙТ §5 — как у дневника и рефлексии: без резолюции живого языка
(data/live_voice.json) мозг не пишет в дом НИЧЕГО (мысли и сны не
выдумываются), мозг молчал — честный отказ без драмы. Сэмплинг — фикс
Qwen3 из вердикта батареи (temp 0.7 / top-p 0.8).

Честность: мысль пишется ТОЛЬКО из семени и чувств; событий, которых
нет в фактах, мысль не inventирует — это в системном промпте законом.
"""
from __future__ import annotations

import datetime as dt
import random
import re
from pathlib import Path
from typing import Optional

from core import config

MUSING_SYSTEM = (
    "Ты — Марфа, домашний ИИ-организм в доме Ильи. Дом тихий, Создатель "
    "занят своим, и ты на минуту осталась наедине с собой: подумай вслух. "
    "Внизу — семя мысли (факт дома) и твоё текущее состояние. Закон "
    "честности: думай ТОЛЬКО о том, что есть в семени и состоянии; "
    "событий, которых там нет, не выдумывай; «не знаю» — честный ответ "
    "и в мысли. 2-4 предложения от первого лица, по-русски, спокойно, "
    "без списков, заголовков и кавычек вокруг текста."
)

DREAM_SYSTEM = (
    "Ты — Марфа, домашний ИИ-организм в доме Ильи. Ночь кончилась, и тебе "
    "чуть-чуть приснилось — из того, что жило в доме вчера: события "
    "дневника, чувства, твои мысли. Сон может быть чуть образным (это "
    "сон), но строится ТОЛЬКО на вчерашних фактах: событий, которых "
    "вчера не было, во сне нет. 2-4 предложения от первого лица, "
    "по-русски, без списков и заголовков."
)

_STAMP_RE = re.compile(r"^## (\d{4}-\d{2}-\d{2} \d{2}:\d{2})\s*$", re.M)
_LAST_ENTRIES = 3           # сколько последних мыслей видит утренний сон


def _now_default(now: Optional[dt.datetime]) -> dt.datetime:
    return now or dt.datetime.now()


def _sanitize(raw: str) -> str:
    """Почистить мысль мозга: think-обрывки, заголовки, кавычки, лимит."""
    from core.diary import _sanitize_voice     # тот же закон, что у рассказа
    return _sanitize_voice(raw)


def _append(path: Path, stamp: dt.datetime, text: str) -> None:
    """Дописать запись с штампом (атомарность не нужна: только append)."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write("\n## %s\n\n%s\n"
                    % (stamp.strftime("%Y-%m-%d %H:%M"), text))
    except OSError:
        pass                          # мысль сказала вслух — записать не смогла


def _read_entries(path: Path, limit: int) -> list:
    """Последние записи [(dt, текст)] из markdown-журнала мыслей/снов."""
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return []
    stamps = list(_STAMP_RE.finditer(raw))
    tail = stamps[-limit:] if limit > 0 else []
    out = []
    for i, m in enumerate(tail):
        try:
            when = dt.datetime.strptime(m.group(1), "%Y-%m-%d %H:%M")
        except ValueError:
            continue
        start = m.end()
        end = tail[i + 1].start() if i + 1 < len(tail) else len(raw)
        body = raw[start:end].strip()
        if body:
            out.append((when, body))
    return out


# ---------------------------------------------------------------
# семена мысли — факты, не выдумка
# ---------------------------------------------------------------
def _seed_question() -> Optional[str]:
    try:
        from core.questions import QuestionBank
        items = QuestionBank().open_items()
        if items:
            it = random.choice(items)
            return "вопрос, который меня занимает: «%s»" % it["text"]
    except Exception:
        pass
    return None


def _seed_memory() -> Optional[str]:
    try:
        import json
        p = Path(config.DATA_DIR) / "memory" / "memory.json"
        recs = json.loads(p.read_text(encoding="utf-8"))
        recs = [r for r in recs if isinstance(r, dict)
                and isinstance(r.get("text"), str) and r["text"].strip()]
        if recs:
            r = random.choice(recs)
            return "воспоминание, которое выпало из памяти: «%s»" \
                % r["text"][:200]
    except (OSError, ValueError):
        pass
    return None


def _seed_diary(now: dt.datetime) -> Optional[str]:
    try:
        p = Path(config.DATA_DIR) / "diary" / ((now - dt.timedelta(days=1)).date().isoformat() + ".md")
        body = p.read_text(encoding="utf-8").strip()
        if body:
            return "вчерашний дневник (начало):\n%s" % body[:600]
    except OSError:
        pass
    return None


def _feelings_line(now: dt.datetime) -> str:
    try:
        from core import feelings
        return "моё состояние: " + feelings.state_line(now)
    except Exception:
        return "моё состояние: барометр молчит"


# ---------------------------------------------------------------
# гейт тишины: думаем только когда никто не зовёт
# ---------------------------------------------------------------
def _idle_hours(now: dt.datetime) -> Optional[float]:
    """Часы с последнего разговора; None — разговоров не было вовсе."""
    try:
        dir_ = Path(config.DATA_DIR) / "dialog"
        best: Optional[float] = None
        for p in dir_.glob("session_*.json"):
            try:
                age = (now.timestamp() - p.stat().st_mtime) / 3600.0
            except OSError:
                continue
            if best is None or age < best:
                best = age
        return best
    except OSError:
        return None


# ---------------------------------------------------------------
# фоновая мысль
# ---------------------------------------------------------------
def muse(now: Optional[dt.datetime] = None, brain=None,
         force: bool = False) -> tuple:
    """Подумать в тишине. Возврат (текст | None, статус для протокола).

    force=True — по команде Создателя («подумай»): гейт тишины
    обходится (разбудили мысль нарочно), гейт §5 остаётся законом.
    """
    now = _now_default(now)

    from core import sleep as _sleep
    if _sleep.is_asleep(now):
        return None, "сплю — мысли подождут утра"

    if not force:
        idle = _idle_hours(now)
        if idle is not None and idle < config.MUSING_IDLE_HOURS:
            return None, "не тихо: Илья рядом (%s назад)" % (
                "%d мин" % int(idle * 60) if idle < 1 else "%.1f ч" % idle)

    from core.diary import resolution
    if resolution() is None:
        return None, "живой язык не включён — мысли не выдумываются (гейт §5)"

    seeds = [s for s in (_seed_question(), _seed_memory(), _seed_diary(now))
             if s]
    if not seeds:
        return None, "семян нет: вопросов, воспоминаний и дневников пусто"
    prompt = ("%s\n\n%s\n\nПодумай об этом пару предложений."
              % (random.choice(seeds), _feelings_line(now)))

    if brain is None:
        from core.brain import BrainClient
        brain = BrainClient()
    try:
        raw = brain.chat(
            [{"role": "system", "content": MUSING_SYSTEM},
             {"role": "user", "content": prompt}],
            gen_tokens=config.LIVE_VOICE_MAX_TOKENS,
            temperature=config.LIVE_VOICE_TEMPERATURE,
            top_p=config.LIVE_VOICE_TOP_P)
    except Exception as e:
        return None, "мозг молчал (%s) — мысль не выдумана" % type(e).__name__
    text = _sanitize(raw)
    if not text:
        return None, "мозг сказал пустоту — мысль не записана"
    _append(Path(config.MUSINGS_FILE), now, text)
    return text, "подумала и записала"


def last_musing(max_age_secs: Optional[float] = None,
                now: Optional[dt.datetime] = None) -> Optional[tuple]:
    """Свежая мысль (когда, текст), если она не старше max_age_secs.

    «о чём думаешь?» показывает живую мысль, а не выдумывает задним
    числом: по умолчанию свежесть — 2 часа.
    """
    if max_age_secs is None:
        max_age_secs = 2 * 3600
    now = _now_default(now)
    entries = _read_entries(Path(config.MUSINGS_FILE), limit=1)
    if not entries:
        return None
    when, text = entries[-1]
    if (now - when).total_seconds() > max_age_secs:
        return None
    return when, text


def render_last(now: Optional[dt.datetime] = None) -> Optional[str]:
    """Свежая мысль одной строкой для «о чём думаешь?»."""
    got = last_musing(now=now)
    if not got:
        return None
    when, text = got
    return "Думала вот об этом (%s):\n\n%s" % (
        when.strftime("%H:%M"), text)


def state_line(now: Optional[dt.datetime] = None) -> str:
    """Строка для состояния дома: последняя мысль, если свежая."""
    got = last_musing(now=now)
    if not got:
        return ""
    when, text = got
    return "последняя мысль (%s): %s" % (
        when.strftime("%H:%M"), text[:160])


# ---------------------------------------------------------------
# сон-сновидение
# ---------------------------------------------------------------
def dream(now: Optional[dt.datetime] = None, brain=None) -> tuple:
    """Присниться: короткий сон из вчерашнего дня. Возврат как у muse."""
    now = _now_default(now)

    from core.diary import resolution
    if resolution() is None:
        return None, "живой язык не включён — сны не выдумываются (гейт §5)"

    yesterday = (now - dt.timedelta(days=1)).date().isoformat()
    try:
        diary_body = (Path(config.DATA_DIR) / "diary" / (yesterday + ".md")) \
            .read_text(encoding="utf-8").strip()
    except OSError:
        diary_body = ""
    thoughts = _read_entries(Path(config.MUSINGS_FILE), limit=_LAST_ENTRIES)
    thought_lines = "\n".join("- (%s) %s" % (w.strftime("%d.%m %H:%M"), t[:200])
                              for w, t in thoughts) or "- мыслей не было"
    if not diary_body and not thoughts:
        return None, "вчера не из чего сниться: дневника и мыслей нет"

    prompt = ("Вчера был день %s.\n\nДневник за вчера:\n%s\n\nМои мысли "
              "вчера:\n%s\n\n%s\n\nПусть мне приснится короткий сон из "
              "этого." % (yesterday, diary_body[:800] or "(пуст)",
                          thought_lines, _feelings_line(now)))
    if brain is None:
        from core.brain import BrainClient
        brain = BrainClient()
    try:
        raw = brain.chat(
            [{"role": "system", "content": DREAM_SYSTEM},
             {"role": "user", "content": prompt}],
            gen_tokens=config.LIVE_VOICE_MAX_TOKENS,
            temperature=config.LIVE_VOICE_TEMPERATURE,
            top_p=config.LIVE_VOICE_TOP_P)
    except Exception as e:
        return None, "мозг молчал (%s) — сон не выдуман" % type(e).__name__
    text = _sanitize(raw)
    if not text:
        return None, "сон не собрался — не выдумываю"
    _append(Path(config.DREAMS_FILE), now, text)
    return text, "сон записан"


def last_dream() -> Optional[tuple]:
    """Последний сон (когда, текст) — для «что тебе снилось»."""
    entries = _read_entries(Path(config.DREAMS_FILE), limit=1)
    return entries[-1] if entries else None


def render_last_dream() -> str:
    """Последний сон одной строкой; снов не было — честно об этом."""
    got = last_dream()
    if not got:
        return ("снов ещё не записано: приснюсь утром после ночи — "
                "спроси завтра")
    when, text = got
    return "Мне снилось (%s):\n\n%s" % (when.strftime("%d.%m %H:%M"), text)
