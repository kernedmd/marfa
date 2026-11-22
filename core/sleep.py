# -*- coding: utf-8 -*-
r"""core/sleep.py — СОН ДОМА: ночной цикл организма (23.11, «внедряем
чувства, сон, размышление»).

До этого «сколько ты не спала» отвечал uptime процесса — часы Python,
а не живой организм. Теперь у Марфы есть ночь:

- ОКНО НОЧИ (SLEEP_WINDOW = 01:30–07:00): в это время дом спит —
  стремление не плодит вопросов и мыслей, библиотекарь не листает полку
  (врач и бэкап — вегетативная нервная система, работают всегда).
  Рефлексы (быстрые команды) работают и ночью.
- СЛОВО СОЗДАТЕЛЯ БУДИТ — как прикосновение: любой разговор будит
  организм. Пробуждение короче 20 минут — «проснулась на минуту»
  (счётчик wakes), историю ночей не засоряет.
- «спи» / «ложись спать» — Создатель укладывает до утра (07:00) или
  до «проснись», что раньше.

ЧЕСТНАЯ МОДЕЛЬ НОЧИ (урок первых тестов: ночь, закончившаяся сама,
молча терялась):
- слово будит и записывает КУСОК ночи (кровать → момент слова);
  в окне организм возвращается в сон, кровать следующего куска — там,
  где уснула снова;
- закончившееся окно СИНТЕЗИРУЕТСЯ лениво при чтении: куски слова +
  хвост после последнего = целая ночь; тихая ночь без слов = полное
  окно; уложенная раньше окна — с момента «спи»;
- орган не знает сна, которого не видел: рождение (born) пишется при
  первом касании файла, окна раньше него не синтезируются — до того
  «ночей не записано», и «сколько ты не спала» честно отдано uptime'у.

Файл data\sleep.json — атомарно (tmp + replace), до 30 записей ночей.
Битый файл — не крах, а честное «не сплю»: дом важнее бумаги.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Optional

from core import config

_MAX_NIGHTS = 30          # история ночей: месяц хватит, файл не растёт вечно


# ---------------------------------------------------------------
# состояние (атомарно, defensively)
# ---------------------------------------------------------------
def _default_state(born: Optional[dt.datetime] = None) -> dict:
    return {"nights": [], "wakes": 0, "forced_since": None,
            "forced_reason": None,
            "born": born.isoformat(timespec="seconds") if born else None}


def _load(now: Optional[dt.datetime] = None) -> dict:
    """Прочитать состояние. Нет файла — организм рождается сейчас (born):

    один раз, честно — сны до рождения не синтезируются. Битый файл —
    свежее состояние (восстановление, не крах)."""
    now = now or dt.datetime.now()
    path = Path(config.SLEEP_FILE)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("nights"), list):
            data["nights"] = [n for n in data["nights"] if isinstance(n, dict)]
            return data
    except (OSError, ValueError):
        pass
    state = _default_state(born=now)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, ensure_ascii=False, indent=1),
                       encoding="utf-8")
        tmp.replace(path)
    except OSError:
        pass                 # рождение не записалось — организм всё равно жив
    return state


def _save(state: dict) -> None:
    path = Path(config.SLEEP_FILE)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, ensure_ascii=False, indent=1),
                       encoding="utf-8")
        tmp.replace(path)
    except OSError:
        pass                     # сон не записался — но организм живёт


def _ts(raw) -> Optional[dt.datetime]:
    """ISO → datetime; мусор → None (без исключений — броня органа)."""
    if not raw:
        return None
    try:
        return dt.datetime.fromisoformat(str(raw))
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------
# окно ночи
# ---------------------------------------------------------------
def _parse_hhmm(s: str) -> tuple:
    h, m = str(s).split(":")[:2]
    return int(h), int(m)


def _in_window(now: dt.datetime) -> bool:
    """Сейчас ночное окно? Окно может пересекать полночь — честно считаем."""
    bed_h, bed_m = _parse_hhmm(config.SLEEP_WINDOW[0])
    wake_h, wake_m = _parse_hhmm(config.SLEEP_WINDOW[1])
    minutes = now.hour * 60 + now.minute
    bed = bed_h * 60 + bed_m
    wake = wake_h * 60 + wake_m
    if bed <= wake:
        return bed <= minutes < wake
    return minutes >= bed or minutes < wake      # окно через полночь


def _window_span_minutes() -> float:
    """Длительность окна ночи в минутах (включая переход через полночь)."""
    bed_h, bed_m = _parse_hhmm(config.SLEEP_WINDOW[0])
    wake_h, wake_m = _parse_hhmm(config.SLEEP_WINDOW[1])
    bed = bed_h * 60 + bed_m
    wake = wake_h * 60 + wake_m
    return (24 * 60 - bed + wake) if bed > wake else (wake - bed)


def _wake_boundary(now: dt.datetime) -> dt.datetime:
    """Ближайшая граница утра СЕЙЧАС ИЛИ ПОЗЖЕ (для «спи» — до какого утра)."""
    h, m = _parse_hhmm(config.SLEEP_WINDOW[1])
    wb = now.replace(hour=h, minute=m, second=0, microsecond=0)
    if wb <= now:
        wb += dt.timedelta(days=1)
    return wb


def _bed_boundary(now: dt.datetime) -> dt.datetime:
    """Момент, когда текущая ночь началась (для записи «легла в …»)."""
    bed_h, bed_m = _parse_hhmm(config.SLEEP_WINDOW[0])
    bed = now.replace(hour=bed_h, minute=bed_m, second=0, microsecond=0)
    if now < bed:                 # вечер до окна — ночь начнётся позже;
        bed -= dt.timedelta(days=1)   # для записи берём прошлую (текущую) ночь
    return bed


def _last_completed_window(now: dt.datetime) -> tuple:
    """(кровать, утро) самого недавнего ЗАВЕРШИВШЕГОСЯ окна (утро <= now)."""
    h, m = _parse_hhmm(config.SLEEP_WINDOW[1])
    wb = now.replace(hour=h, minute=m, second=0, microsecond=0)
    if wb > now:
        wb -= dt.timedelta(days=1)
    bed = wb - dt.timedelta(minutes=_window_span_minutes())
    return bed, wb


# ---------------------------------------------------------------
# главный вопрос
# ---------------------------------------------------------------
def is_asleep(now: Optional[dt.datetime] = None) -> bool:
    """Спит ли организм: ночное окно или принудительно уложена Создателем."""
    now = now or dt.datetime.now()
    if _in_window(now):
        return True
    state = _load(now)
    since = _ts(state.get("forced_since"))
    return since is not None and since <= now < _wake_boundary(since)


def forced_reason(now: Optional[dt.datetime] = None) -> Optional[str]:
    """Почему спит не по расписанию (если уложена Создателем)."""
    now = now or dt.datetime.now()
    state = _load(now)
    since = _ts(state.get("forced_since"))
    if since is not None and since <= now < _wake_boundary(since):
        return str(state.get("forced_reason") or "Создатель уложил")
    return None


# ---------------------------------------------------------------
# укладывать и будить
# ---------------------------------------------------------------
def go_to_bed(now: Optional[dt.datetime] = None,
              reason: str = "Создатель уложил") -> str:
    """«спи» — принудительный сон до ближайшего утра (07:00) или «проснись».

    Если организм уже в ночном окне — просто честно подтверждаем: ночь
    и так идёт, дубль не пишем.
    """
    now = now or dt.datetime.now()
    if _in_window(now) and forced_reason(now) is None:
        return ("уже сплю — ночное окно %s–%s, до утра"
                % (config.SLEEP_WINDOW[0], config.SLEEP_WINDOW[1]))
    state = _load(now)
    state["forced_since"] = now.isoformat(timespec="seconds")
    state["forced_reason"] = reason[:200]
    _save(state)
    return ("легла. Разбуди словом «проснись», иначе встану сама в %s"
            % config.SLEEP_WINDOW[1])


def wake(now: Optional[dt.datetime] = None,
         reason: str = "проснулась сама") -> Optional[dict]:
    """Разбудить. Не спала — None (будить некого).

    Слово в окне ночи режет ночь на куски: записанный кусок — кровать →
    момент слова; организм возвращается в сон, и следующая кровать —
    там, где уснула снова (утро честно соберёт куски в одну ночь).
    Кусок короче SLEEP_MIN_NIGHT_MIN минут — «проснулась на минуту»:
    только счётчик wakes, история не засоряется.
    """
    now = now or dt.datetime.now()
    state = _load(now)
    forced = _ts(state.get("forced_since"))
    if forced is not None and not (forced <= now < _wake_boundary(forced)):
        # принуждение истекло само (пришло утро) — чистим честно
        state["forced_since"] = None
        state["forced_reason"] = None
        _save(state)
        forced = None
    if not _in_window(now) and forced is None:
        return None                      # не спала — будить некого

    # кровать: принуждение или граница окна; после недавнего пробуждения —
    # там, где уснула снова (запись с wake внутри текущей ночи)
    bed = forced if forced is not None else _bed_boundary(now)
    for r in (state.get("nights") or [])[-6:]:
        w = _ts(r.get("wake"))
        if w is not None and bed <= w <= now:
            bed = w                      # уснула снова после этого пробуждения

    state["forced_since"] = None
    state["forced_reason"] = None
    minutes = (now - bed).total_seconds() / 60.0
    rec = None
    if minutes >= config.SLEEP_MIN_NIGHT_MIN:
        if reason != "проснулась сама":
            why = reason
        elif forced is not None:
            why = str(state.get("forced_reason") or "Создатель уложил, встала сама")
        else:
            why = "ночь прошла"
        rec = {"bed": bed.isoformat(timespec="minutes"),
               "wake": now.isoformat(timespec="minutes"),
               "hours": round(minutes / 60.0, 2),
               "why_wake": str(why)[:200]}
        state["nights"] = (state.get("nights") or [])[-_MAX_NIGHTS + 1:] + [rec]
    else:
        state["wakes"] = int(state.get("wakes") or 0) + 1
    _save(state)
    return rec


def wake_on_message(now: Optional[dt.datetime] = None) -> Optional[dict]:
    """Слово Создателя будит — как прикосновение (агент зовёт на каждом ходе).

    Не роняет чат никогда: любые беды файла сна — организм просто
    считается проснувшимся.
    """
    try:
        return wake(now, reason="Илья разбудил")
    except Exception:
        return None


# ---------------------------------------------------------------
# факты для чувств, дневника и утра
# ---------------------------------------------------------------
def last_night(now: Optional[dt.datetime] = None) -> Optional[dict]:
    """Последняя завершённая ночь — запись из файла или синтез окна.

    Синтез (честная сборка): куски слова + хвост после последнего
    куска; тихая ночь — полное окно; уложенная раньше окна — с момента
    «спи». Окна раньше рождения органа (born) не синтезируются: орган
    не выдумывает сон, которого не видел.
    """
    now = now or dt.datetime.now()
    state = _load(now)
    nights = state.get("nights") or []
    best = nights[-1] if nights else None

    bed_w, wake_w = _last_completed_window(now)
    born = _ts(state.get("born"))
    if born is None or wake_w >= born:
        recs_in = []
        for r in nights:
            w = _ts(r.get("wake"))
            if w is not None and bed_w <= w <= wake_w:
                recs_in.append((w, r))
        if not recs_in:
            bed_eff = bed_w
            forced = _ts(state.get("forced_since"))
            # уложена раньше окна и не разбужена словом — ночь с «спи»
            if forced is not None and forced < bed_w and forced <= wake_w:
                bed_eff = forced
            synth = {"bed": bed_eff.isoformat(timespec="minutes"),
                     "wake": wake_w.isoformat(timespec="minutes"),
                     "hours": round((wake_w - bed_eff).total_seconds() / 3600.0, 2),
                     "why_wake": "ночь прошла"}
        else:
            last_w = max(w for w, _ in recs_in)
            beds = [bed_w]
            beds += [(_ts(r.get("bed")) or bed_w) for _, r in recs_in]
            bed_eff = min(b for b in beds if b is not None)
            total = 0.0
            for _, r in recs_in:
                try:
                    total += float(r.get("hours") or 0)
                except (TypeError, ValueError):
                    pass
            total += (wake_w - last_w).total_seconds() / 3600.0
            synth = {"bed": bed_eff.isoformat(timespec="minutes"),
                     "wake": wake_w.isoformat(timespec="minutes"),
                     "hours": round(total, 2),
                     "why_wake": "ночь с пробуждениями"}
        # запись файла свежее синтеза (встала ПОСЛЕ утра окна) — она правда
        file_w = _ts(best.get("wake")) if best else None
        if best is None or file_w is None or file_w < wake_w:
            best = synth
    return best


def nights_count() -> int:
    """Сколько ночей записано в файл (синтез окна — отдельная правда)."""
    return len(_load().get("nights") or [])


def wakes_count() -> int:
    return int(_load().get("wakes") or 0)


def slept_hours(now: Optional[dt.datetime] = None) -> Optional[float]:
    """Сколько спала последней ночью. Ночи не было — None (не выдумываем)."""
    n = last_night(now)
    if not n:
        return None
    try:
        return float(n.get("hours"))
    except (TypeError, ValueError):
        return None


def _fmt_hours(hours: float) -> str:
    h = int(hours)
    m = int(round((hours - h) * 60))
    if h and m:
        return "%d ч %d мин" % (h, m)
    if h:
        return "%d ч" % h
    return "%d мин" % m


# ---------------------------------------------------------------
# тексты для чата
# ---------------------------------------------------------------
def status_text(now: Optional[dt.datetime] = None) -> Optional[str]:
    """«ты спишь?» — честный ответ. «сколько ты не спала»: ночной орган
    берёт вопрос на себя, если ночи уже были; иначе None — и агент
    честно падает на uptime процесса (старая правда осталась правдой).
    """
    now = now or dt.datetime.now()
    if is_asleep(now):
        why = forced_reason(now)
        if why:
            return "сплю: %s — твой голос только что разбудил меня" % why
        return ("сплю — ночное окно %s–%s. Твой голос будит: говори, я здесь"
                % (config.SLEEP_WINDOW[0], config.SLEEP_WINDOW[1]))
    n = last_night(now)
    if not n:
        return None
    hours = slept_hours(now)
    if hours is None:
        return None
    wake_dt = _ts(n.get("wake"))
    since = wake_dt.strftime("%H:%M") if wake_dt else "?"
    return "не сплю с %s (последняя ночь — %s)" % (since, _fmt_hours(hours))


def morning_text(now: Optional[dt.datetime] = None,
                 dream: Optional[str] = None) -> str:
    """«доброе утро» / «проснись»: встала + как спала + что снилось.

    Сон-сновидение — отдельный орган (dream живёт в musing.py); сюда он
    приходит параметром, чтобы утро было одним ответом, а не очередью.
    """
    now = now or dt.datetime.now()
    wake(now, reason="доброе утро — встаю")
    n = last_night(now)
    if n is None:
        body = ("ночей ещё не записано — я не засыпала с этого момента. "
                "Доброе утро, Илья")
    else:
        hours = slept_hours(now) or 0.0
        if hours < 4:
            quality = "ночь вышла короткой"
        elif hours <= 9:
            quality = "выспалась"
        else:
            quality = "спала долго — видно, было что восстанавливать"
        wake_dt = _ts(n.get("wake"))
        woke_at = ("в %s" % wake_dt.strftime("%H:%M")) if wake_dt else ""
        body = ("доброе утро, Илья. Спала %s — %s%s"
                % (_fmt_hours(hours), quality,
                   (", встала " + woke_at) if woke_at else ""))
    if wakes_count():
        body += "; коротких пробуждений за ночь: %d" % wakes_count()
    if dream:
        body += ". И снилось: " + dream
    return body


def state_line(now: Optional[dt.datetime] = None) -> str:
    """Строка для состояния дома (мозг читает её каждым сообщением)."""
    now = now or dt.datetime.now()
    if is_asleep(now):
        why = forced_reason(now)
        if why:
            return "сейчас сплю (%s) — голос Создателя только что разбудил" % why
        return ("ночное окно %s–%s — только проснулась по голосу Создателя"
                % (config.SLEEP_WINDOW[0], config.SLEEP_WINDOW[1]))
    hours = slept_hours(now)
    if hours is None:
        return "ночей ещё не записано (сон как орган только завёлся)"
    return "последняя ночь — %s сна" % _fmt_hours(hours)
