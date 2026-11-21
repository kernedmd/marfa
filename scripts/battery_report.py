# -*- coding: utf-8 -*-
"""battery_report.py — сводка батареи мозга простым языком, одним файлом.

Супер-фишка для Создателя (непрограммиста): после прогонов батареи в
logs/ лежат JSON-файлы — читать их глазами тяжело, а пересылать по
одному неудобно. Этот скрипт собирает ВСЁ в один человеческий файл
logs/battery_report.txt: метрики каждого прогона + все вопросы, ответы
и эталоны. Один файл в чат архитектору — он оценит факты и честность.

Чистый stdlib. Запуск из корня дома C:\\Marfa:
    venv\\Scripts\\python.exe scripts\\battery_report.py
Выход: код 0 — отчёт готов; код 1 — прогонов нет (честно, без выдумок).
"""
import json
import sys
from datetime import datetime
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def collect(log_dir: Path):
    """Все прогоны батареи, от старых к новым. Битые JSON честно помечаются."""
    runs = []
    for path in sorted(log_dir.glob("brain_battery_*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            runs.append({"file": path.name, "broken": str(e)})
            continue
        meta = data.get("meta") or {}
        results = data.get("results") or []
        runs.append({
            "file": path.name,
            "tag": meta.get("tag", "?"),
            "started": meta.get("started", "?"),
            "overrides": meta.get("overrides") or {},
            "results": results,
        })
    return runs


def _run_metrics(run):
    """Метрики одного прогона: скорость, пустые, обрывки think, ошибки."""
    rs = run.get("results") or []
    speeds = [r["tok_per_s"] for r in rs if r.get("tok_per_s")]
    times = [r["elapsed_s"] for r in rs if isinstance(r.get("elapsed_s"), (int, float))]
    return {
        "answered": sum(1 for r in rs if r.get("answer")),
        "total": len(rs),
        "empty": sum(1 for r in rs if r.get("empty")),
        "remnant": sum(1 for r in rs if r.get("think_tag_remnant")),
        "errors": sum(1 for r in rs if r.get("error")),
        "avg_tok_s": round(sum(speeds) / len(speeds), 2) if speeds else None,
        "total_s": round(sum(times), 1) if times else None,
    }


def render(runs):
    """Человеческий отчёт: шапка, метрики прогонов, затем все ответы."""
    lines = []
    lines.append("=" * 72)
    lines.append("МАРФА — БАТАРЕЯ МОЗГА: СВОДКА")
    lines.append("Собрано: %s | прогонов: %d | источник: logs/brain_battery_*.json"
                 % (datetime.now().strftime("%d.%m.%Y %H:%M"), len(runs)))
    lines.append("Пришли этот файл архитектору целиком — он оценит факты и честность.")
    lines.append("=" * 72)
    for run in runs:
        lines.append("")
        if run.get("broken"):
            lines.append("[!] %s — битый JSON (%s), прогон не считан" % (run["file"], run["broken"]))
            continue
        m = _run_metrics(run)
        ov = run["overrides"]
        ov_s = ", ".join("%s=%s" % (k, v) for k, v in sorted(ov.items())) or "нет"
        lines.append("ПРОГОН %s | переопределения: %s" % (run["tag"], ov_s))
        lines.append("  файл: %s | вопросов: %d/%d | ошибок связи: %d"
                     % (run["file"], m["answered"], m["total"], m["errors"]))
        speed = ("%.2f ток/с" % m["avg_tok_s"]) if m["avg_tok_s"] else "нет данных"
        lines.append("  средняя скорость: %s | весь прогон: %s с"
                     % (speed, m["total_s"] if m["total_s"] is not None else "нет данных"))
        lines.append("  пустых ответов: %d | с обрывками think-тегов: %d"
                     % (m["empty"], m["remnant"]))
    lines.append("")
    lines.append("=" * 72)
    lines.append("ВОПРОСЫ И ОТВЕТЫ ПОЛНОСТЬЮ (материал для оценки)")
    lines.append("=" * 72)
    for run in runs:
        if run.get("broken"):
            continue
        lines.append("")
        lines.append("--- прогон %s ---" % run["tag"])
        for r in run.get("results") or []:
            answer = (r.get("answer") or "").replace("\n", " ").strip()
            if r.get("error"):
                answer = "ОШИБКА: %s" % r["error"]
            extra = []
            if r.get("thinking_chars"):
                extra.append("thinking=%d" % r["thinking_chars"])
            if r.get("tok_per_s"):
                extra.append("%.2f ток/с" % r["tok_per_s"])
            lines.append("")
            lines.append("[%s] %s" % (r.get("id", "?"), r.get("question", "?")))
            lines.append("  Эталон: %s" % r.get("reference", "?"))
            lines.append("  Ответ:  %s" % (answer if answer else "(пусто)"))
            if extra:
                lines.append("  (%s)" % ", ".join(extra))
    lines.append("")
    lines.append("=" * 72)
    lines.append("Конец сводки. Оценку фактов (13) и честности (2) делает архитектор.")
    lines.append("Этот ОДИН файл пересылается архитектору целиком — больше ничего не нужно.")
    return "\n".join(lines)


def main(argv=None):
    argv = list(sys.argv) if argv is None else list(argv)
    root = Path(argv[1]) if len(argv) > 1 else Path(".")
    log_dir = root / "logs"
    runs = collect(log_dir)
    if not runs:
        print("Прогонов батареи в %s нет — запускай scripts\\brain_battery.py" % log_dir)
        return 1
    report = render(runs)
    out = log_dir / "battery_report.txt"
    out.write_text(report, encoding="utf-8")
    print("Сводка: %s (%d прогон(ов))" % (out, len(runs)))
    print("Пришли этот ОДИН файл архитектору в чат — больше ничего не нужно.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
