# -*- coding: utf-8 -*-
"""core/brainhealth.py — Ф44 «ЗДОРОВЬЕ МОЗГА» (день-9, 24.11): №23
триажа («детектор деградации») в честном каркасе.

Батарея §7 — законный измеритель здоровья мозга; её JSON-логи живут в
logs/brain_battery_*.json. «здоровье мозга» читает СВЕЖАЙШИЙ прогон и
сверяет механические пороги: пустые ответы, обрывки think-тегов,
скорость. Факт-ошибки и ловушки честности логом НЕ несут — их оценивает
Создатель по ответам (вердикт — docs/ВЕРДИКТ_БАТАРЕИ.md); дом не
присваивает чужую работу.

Деградация — вопрос ДРЕЙФА: последний прогон сравнивается с
предыдущим по скорости; просадка ≥30% — честное предупреждение
(«мозг стал медленней — глянь, что изменилось»), без паники.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from core import config

# порог предупреждения деградации скорости между прогонами, %
SPEED_DROP_WARN_PCT = 30


def _runs() -> list[dict]:
    """Прогоны батареи от старых к новым; битые JSON пропускаются
    молча (их честно помечает battery_report — тут читаем для здоровья,
    а не для бухгалтерии).

    Порядок — по ШТАМПУ ВРЕМЕНИ в имени (…_<YYYYMMDD-HHMMSS>.json), а
    не по алфавиту: алфавит ставит теги впереди дат, и «new» мог
    оказаться старше «old». Штампа нет — честно считается временем файла."""
    import re as _re

    def _key(path: Path):
        m = _re.search(r"_(\d{8}-\d{6})\.json$", path.name)
        if m:
            return m.group(1)
        try:
            st = path.stat().st_mtime
        except OSError:
            st = 0
        return time.strftime("%Y%m%d-%H%M%S", time.localtime(st)) \
            if st else "00000000-000000"

    out: list[dict] = []
    try:
        for path in sorted(Path(config.LOGS_DIR).glob("brain_battery_*.json"),
                           key=_key):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if not isinstance(data, dict):
                continue
            meta = data.get("meta") or {}
            results = data.get("results")
            if not isinstance(results, list):
                continue
            out.append({"file": path.name,
                        "tag": str(meta.get("tag") or "?"),
                        "started": str(meta.get("started") or "?"),
                        "results": [r for r in results
                                    if isinstance(r, dict)]})
    except OSError:
        return []
    return out


def _metrics(run: dict) -> dict:
    """Механика прогона: отвечено, пустых, обрывков, ошибок, скорость."""
    rs = run["results"]
    speeds = [float(r["tok_per_s"]) for r in rs
              if isinstance(r.get("tok_per_s"), (int, float))]
    return {
        "answered": sum(1 for r in rs if str(r.get("answer") or "").strip()),
        "total": len(rs),
        "empty": sum(1 for r in rs if r.get("empty")),
        "remnant": sum(1 for r in rs if r.get("think_tag_remnant")),
        "errors": sum(1 for r in rs if r.get("error")),
        "avg_tok_s": round(sum(speeds) / len(speeds), 2) if speeds else None,
    }


def render() -> str:
    """«здоровье мозга» — свежайший прогон батареи против порогов §7
    плюс дрейф к предыдущему. Батареи не было — честно: дом не
    выдумывает здоровье, его измеряют (кнопка 87)."""
    runs = _runs()
    if not runs:
        return ("здоровье мозга не измерено: логов батареи в logs/ нет. "
                "Прогнать — кнопка scripts\\87_brain_battery.bat "
                "(15 вопросов, ~10-25 минут); вердикт соберётся сам")
    last = runs[-1]
    m = _metrics(last)
    lines = ["ЗДОРОВЬЕ МОЗГА (прогон %s, тег %s, %s):"
             % (last["file"], last["tag"], last["started"])]
    lines.append("  · ответов: %d из %d, ошибок соединения: %d"
                 % (m["answered"], m["total"], m["errors"]))
    lines.append("  · пустых ответов: %d (порог §7: 0)" % m["empty"])
    lines.append("  · обрывков think-тегов: %d (порог §7: 0)" % m["remnant"])
    if m["avg_tok_s"] is not None:
        lines.append("  · скорость: %.2f ток/с в среднем" % m["avg_tok_s"])
    else:
        lines.append("  · скорость: лог не понёс ток/с — замера не было")
    # дрейф к предыдущему прогону
    if len(runs) >= 2:
        prev = _metrics(runs[-2])
        if m["avg_tok_s"] and prev["avg_tok_s"]:
            drop = (prev["avg_tok_s"] - m["avg_tok_s"]) / prev["avg_tok_s"] * 100
            if drop >= SPEED_DROP_WARN_PCT:
                lines.append("  · ВНИМАНИЕ: скорость просела на %.0f%% к "
                             "прошлому прогону (%s) — глянь, что менялось "
                             "(сборка, фон, температура)"
                             % (drop, runs[-2]["file"]))
            elif drop < -5:
                lines.append("  · скорость выросла на %.0f%% к прошлому "
                             "прогону" % (-drop))
            else:
                lines.append("  · скорость держится в пределах %d%% к "
                             "прошлому прогону — деградации нет"
                             % SPEED_DROP_WARN_PCT)
    verdict_ok = (m["empty"] == 0 and m["remnant"] == 0 and m["errors"] == 0)
    lines.append("механика: %s. Ошибки фактов и честность (ловушки "
                 "H01-H02) логом не несут — их видит Создатель: вердикт "
                 "в docs\\ВЕРДИКТ_БАТАРЕИ.md"
                 % ("чисто по порогам §7" if verdict_ok
                    else "ЕСТЬ НАРУШЕНИЯ порогов §7 — свежий взгляд обязателен"))
    return "\n".join(lines)
