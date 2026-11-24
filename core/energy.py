# -*- coding: utf-8 -*-
"""core/energy.py — Ф45 «ЭНЕРГИЯ ДОМА» (день-9, 24.11): №44 триажа
(метрики производительности) в чате, без консоли.

Сколько дом сегодня сделал и почём: ходы по видам (рефлекс / мозг /
память ответов), сколько секунд и токенов съел мозг, что сэкономила
память ответов (Ф41). Два источника разной природы:

- logs/brain_log.jsonl — истина по мозгу (одна строка на генерацию,
  писалась с 23.11);
- data/energy.jsonl — счётчик рефлексов (новый, с дня-9: агент пишет
  строку на каждый свой ход, который НЕ дошёл до мозга).

«энергия дома» собирает день в один ответ; пустой день — честно пуст.
Упавший источник — строка пропускает, сводка жива (закон №10 р3).
"""
from __future__ import annotations

import datetime as dt
import json
import time
from pathlib import Path

from core import config, loghygiene


def _file() -> Path:
    """data/energy.jsonl — ЛЕНИВО от DATA_DIR (закон органов каждого хода,
    как reminders: агент пишет строку на КАЖДЫЙ ход, и чужая песочница
    теста не должна протекать в живой дом)."""
    return Path(config.DATA_DIR) / "energy.jsonl"


def note(source: str, secs: float, tok: int | None = None) -> None:
    """Записать один ход дома. Никогда не поднимает шум: журнал —
    топливо статистики, не орган дыхания (урок brain-лога)."""
    try:
        _file().parent.mkdir(parents=True, exist_ok=True)
        with _file().open("a", encoding="utf-8") as f:
            f.write(json.dumps({
                "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
                "source": str(source or "?")[:24],
                "secs": round(float(secs), 3),
                "tok": int(tok) if tok else None,
            }, ensure_ascii=False) + "\n")
    except (OSError, TypeError, ValueError):
        pass


def _today() -> str:
    return dt.date.today().strftime("%Y-%m-%d")


def _counts_today() -> dict:
    """Ходы сегодня по источникам — из счётчика. Рефлекс — «python",
    память ответов — «answercache» (свой штамп в эфире, Ф41). Битые
    строки молча мимо (журнал — недоверенный)."""
    out = {"python": 0, "answercache": 0}
    today = _today()
    try:
        for line in _file().read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or not line.startswith("{"):
                continue
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if not isinstance(rec, dict):
                continue
            if str(rec.get("ts", "")).startswith(today) \
                    and str(rec.get("source")) in out:
                out[str(rec.get("source"))] += 1
    except OSError:
        return out
    return out


def _brain_today() -> dict:
    """Мозг сегодня — из журнала трафика (истина): генерации, секунды,
    токены ответа. Считает ВСЕ генерации: повторы-ретраи тоже честно
    едят время дома.

    Ф98 (круг 17): читаем ограниченное множество recent_paths() —
    текущий файл + архивы ротации: ротация среди дня не роняет
    «сегодня» из бухгалтерии энергии.
    """
    gen = secs = ctok = 0
    today = _today()
    try:
        for p in loghygiene.recent_paths(Path(config.BRAIN_LOG_FILE)):
            for line in p.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or not line.startswith("{"):
                    continue
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(rec, dict):
                    continue
                if not str(rec.get("ts", "")).startswith(today):
                    continue
                gen += 1
                try:
                    secs += float(rec.get("secs") or 0)
                except (TypeError, ValueError):
                    pass
                # день-13, урок живого чтения: журнал мозга ПИШЕТ
                # «completion_tokens» (_log_brain_call, с рождения журнала
                # 23.11), а бухгалтерия читала «ctok» — поле, которого в
                # живом журнале нет; якорь годами проверял свою опечатку
                # против опечатки фикстуры. Читаем живое имя поля
                try:
                    ctok += int(rec.get("completion_tokens") or 0)
                except (TypeError, ValueError):
                    pass
    except OSError:
        pass
    return {"gen": gen, "secs": secs, "ctok": ctok}


def _h(secs: float) -> str:
    """Секунды по-человечески: «47 с», «3 мин 12 с», «12 мин»."""
    secs = int(round(secs))
    if secs < 60:
        return "%d с" % secs
    m, s = divmod(secs, 60)
    return "%d мин %02d с" % (m, s) if s else "%d мин" % m


def render() -> str:
    """«энергия дома» — день в цифрах одним ответом."""
    try:
        from core import answercache
        mem = answercache.stats()
    except Exception:
        mem = {"entries": 0, "hits": 0}
    brain = _brain_today()
    counts = _counts_today()
    reflexes = counts["python"]
    mem_hits = counts["answercache"]
    lines = ["ЭНЕРГИЯ ДОМА (сегодня):"]
    if not (brain["gen"] or reflexes or mem_hits or mem["entries"]):
        return "энергия дома: сегодня ходов ещё не было — дом только проснулся"
    lines.append("  · рефлексов (мозг молчал): %d" % reflexes)
    if brain["gen"]:
        lines.append("  · мозг думал %d раз — %s, %d ток ответов "
                     "(по журналу мозга)"
                     % (brain["gen"], _h(brain["secs"]), brain["ctok"]))
        if brain["secs"] and brain["ctok"]:
            lines.append("  · средняя генерация: %.1f ток/с"
                         % (brain["ctok"] / brain["secs"]))
    else:
        lines.append("  · мозг сегодня не думал (все ходы — рефлексы)")
    if mem_hits:
        # экономия: каждое попадание — несостоявшаяся генерация мозга;
        # средняя генерация сегодня и есть честная цена попадания
        avg = (brain["secs"] / brain["gen"]) if brain["gen"] else 0
        lines.append("  · память ответов сработала %d раз — %d записей "
                     "живёт; сэкономила ~%s мозгового времени"
                     % (mem_hits, mem["entries"],
                        _h(mem_hits * avg) if avg else "секунды"))
    elif mem["entries"]:
        lines.append("  · память ответов: %d записей, сегодня без "
                     "попаданий" % mem["entries"])
    return "\n".join(lines)
