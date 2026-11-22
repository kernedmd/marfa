# -*- coding: utf-8 -*-
"""architect_oncall.py v0.1 — дежурный архитектор дома Марфа (RouterAI).

Задача (б): архитектор по вызову. Собирает контекст проекта, спрашивает
модель через RouterAI, печатает ответ и сохраняет протокол в logs/architect/.

ПРАВИЛА ДОМА (Ф105): ключ живёт ТОЛЬКО в C:\\Marfa\\.env строкой
    ROUTERAI_API_KEY=...
В код и в чат ключ не попадает никогда.

v0.1 — только советует: печатает диагноз и патч, НИЧЕГО не меняет на диске.
Применяет правки рука Создателя (или архитектор Z.ai в чате).

Запуск из C:\\Marfa:
    venv\\Scripts\\python.exe architect_oncall.py "почему /api/chat отдаёт 500"
    venv\\Scripts\\python.exe architect_oncall.py --files web/app.py,core/brain.py "доработай X"

Модель по умолчанию: deepseek/deepseek-v4-pro-0813
Сменить: в .env строка  MARFA_ARCHITECT_MODEL=anthropic/claude-sonnet-5.5
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ENV_FILE = ROOT / ".env"
ARCHIVE_DIR = ROOT / "logs" / "architect"
API_URL = "https://routerai.ru/api/v1/chat/completions"
DEFAULT_MODEL = "deepseek/deepseek-v4-pro-0813"
DEFAULT_FILES = "core/config.py,web/app.py,core/agent.py,core/brain.py"
MAX_FILE_CHARS = 40000          # один файл — не больше 40 000 символов в контекст
TIMEOUT_SEC = 300

SYSTEM_PROMPT = (
    "Ты — дежурный архитектор дома Марфа, локального ИИ-дома на C:\\Marfa "
    "(Windows, Flask на порту 5001, llama.cpp на 8082, мозг Qwen3-30B-A3B). "
    "Создатель дома — Илья. Ты даёшь советы и точечные патчи по коду, "
    "но сам ничего не исполняешь и не пишешь на диск. Правила дома: "
    "1) ничего вне C:\\Marfa; 2) токены только в .env, никогда в код и логи; "
    "3) порт 5000 не трогать; 4) изменения мастер-ТЗ — только резолюцией Создателя. "
    "Отвечай по-русски и по структуре: ДИАГНОЗ -> ПАТЧ (точный код) -> КАК ПРОВЕРИТЬ."
)


def _utf8_console() -> None:
    """Чиним вывод русского текста в консоль Windows (cp866/1251)."""
    for stream in (sys.stdout, sys.stderr):
        try:
            if stream.encoding and stream.encoding.lower().replace("-", "") != "utf8":
                stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def load_env() -> dict:
    """Прочитать C:\\Marfa\\.env в словарь. utf-8-sig съедает BOM от Блокнота."""
    env: dict = {}
    if ENV_FILE.exists():
        for raw in ENV_FILE.read_text(encoding="utf-8-sig", errors="replace").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def build_context(rel_files: list) -> str:
    """Собрать текст контекста из файлов проекта (каждый с шапкой-путём)."""
    parts = []
    for rel in rel_files:
        p = ROOT / rel
        if not p.exists():
            parts.append(f"### {rel}\n(файл не найден на диске)\n")
            continue
        text = p.read_text(encoding="utf-8", errors="replace")[:MAX_FILE_CHARS]
        parts.append(f"### {rel}\n```\n{text}\n```\n")
    return "\n".join(parts)


def ask_routerai(task: str, context: str, model: str, api_key: str) -> tuple:
    """Один запрос к RouterAI. Возвращает (ответ, usage-строка)."""
    import requests

    user_msg = f"ЗАДАЧА ОТ СОЗДАТЕЛЯ:\n{task}\n\nКОНТЕКСТ ПРОЕКТА:\n{context}"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ],
        "temperature": 0.3,
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    resp = requests.post(API_URL, headers=headers, json=payload, timeout=TIMEOUT_SEC)
    if resp.status_code != 200:
        snippet = resp.text[:500] if resp.text else ""
        raise RuntimeError(f"RouterAPI HTTP {resp.status_code}: {snippet}")
    data = resp.json()
    answer = data["choices"][0]["message"]["content"]
    usage = data.get("usage") or {}
    usage_line = (
        f"токены: вход {usage.get('prompt_tokens', '?')}, "
        f"выход {usage.get('completion_tokens', '?')}"
    )
    return answer, usage_line


def save_transcript(task: str, rel_files: list, model: str,
                    answer: str, usage_line: str) -> Path:
    """Сохранить протокол: ни один ответ архитектора не теряется."""
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    path = ARCHIVE_DIR / f"architect_{stamp}.md"
    head = [
        f"# Протокол дежурного архитектора — {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"- модель: {model}",
        f"- файлы в контексте: {', '.join(rel_files)}",
        f"- {usage_line}",
        "",
        "## Задача",
        task,
        "",
        "## Ответ",
        answer,
        "",
    ]
    path.write_text("\n".join(head), encoding="utf-8")
    return path


# ---------------------------------------------------------------
# v2 (№29 роадмапа 30): ЕЖЕНЕДЕЛЬНЫЙ АУДИТ ДОМА — тесты, коммиты,
# здоровье дисков, дрейф канона; отчёт Создателю (команда «доклад
# архитектора» + расписание вс 20:00). Источники — швы (_src_*),
# тесты подменяют их: реальный pytest/git/диск не нужны.
# ---------------------------------------------------------------

WEEKLY_TEST_TIMEOUT_SEC = 600
WEEKLY_GIT_TIMEOUT_SEC = 15
DISK_MIN_FREE_GB = 20.0        # меньше — WARN в отчёте


def _iso_week() -> str:
    """«2026-W47» — имя отчёта недели."""
    y, w, _ = time.strftime("%G-%V-%u").split("-")
    return "%s-W%s" % (y, w)


def _src_services() -> str:
    """Живость слуг: мозг, глаза, панель — по /health (кэша нет:
    раз в неделю можно и поспросить по-честному)."""
    import urllib.request
    lines = []
    for name, port in (("мозг", 8082), ("глаза", 8083), ("панель", 5001)):
        try:
            with urllib.request.urlopen(
                    "http://127.0.0.1:%d/health" % port, timeout=3) as r:
                ok = r.status == 200
        except Exception:
            ok = False
        lines.append("%s (%d): %s" % (name, port, "жив" if ok else "НЕ ОТВЕЧАЕТ"))
    return "; ".join(lines)


def _src_tests() -> str:
    """Батарея тестов одной строкой. N7: нет pytest — «НЕ ЗАПУСКАЛИСЬ»,
    а не «красные»: диагноз не врёт."""
    try:
        r = subprocess.run(
            [sys.executable, "-m", "pytest", "tests", "-q"],
            cwd=str(ROOT), capture_output=True, text=True,
            timeout=WEEKLY_TEST_TIMEOUT_SEC)
        if r.returncode != 0 and "No module named" in (r.stderr or "") \
                and "pytest" in (r.stderr or ""):
            return "тесты НЕ ЗАПУСКАЛИСЬ: нет pytest в этом интерпретаторе"
        tail = [l for l in (r.stdout or "").splitlines() if l.strip()]
        last = tail[-1].strip() if tail else "код %d" % r.returncode
        return ("БАТАРЕЯ %s — %s"
                % ("ЗЕЛЁНАЯ" if r.returncode == 0 else "ЕСТЬ КРАСНЫЕ", last))
    except subprocess.TimeoutExpired:
        return "тесты не уложились в %d с" % WEEKLY_TEST_TIMEOUT_SEC
    except Exception as e:
        return "тесты не запустились: %s" % e


def _src_commits(days: int = 7) -> str:
    """Коммиты недели: сколько и последний."""
    try:
        r = subprocess.run(
            ["git", "log", "--since=%d days" % days, "--oneline"],
            cwd=str(ROOT), capture_output=True, text=True,
            timeout=WEEKLY_GIT_TIMEOUT_SEC, encoding="utf-8", errors="replace")
        lines = [l.strip() for l in (r.stdout or "").splitlines() if l.strip()]
        if not lines:
            return "коммитов за %d дней НЕТ — дом стоит, стройка молчит" % days
        last = lines[0][:90]
        return "%d коммитов за %d дней; последний: %s" % (len(lines), days, last)
    except Exception as e:
        return "git не ответил: %s" % e


def _src_disk() -> str:
    """Здоровье диска: свободное место против порога."""
    du = shutil.disk_usage(str(ROOT))
    free_gb = du.free / 2**30
    verdict = "ОК" if free_gb >= DISK_MIN_FREE_GB else "МАЛО МЕСТА (< %d ГБ)" % DISK_MIN_FREE_GB
    return "свободно %.0f ГБ из %.0f — %s" % (free_gb, du.total / 2**30, verdict)


def _src_canon_drift() -> str:
    """Дрейф канона: незакоммиченные правки — книги дома (docs/) живут
    в git; правка мимо git — канон уже не канон."""
    try:
        r = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(ROOT), capture_output=True, text=True,
            timeout=WEEKLY_GIT_TIMEOUT_SEC, encoding="utf-8", errors="replace")
        lines = [l.strip() for l in (r.stdout or "").splitlines() if l.strip()]
        if not lines:
            return "дерево чистое — канон и код в одной правде"
        docs = [l for l in lines if "docs/" in l or "docs\\" in l]
        note = ("; из них книги docs/: %d — КАНОН ДРЕЙФУЕТ"
                % len(docs)) if docs else ""
        return "незакоммичено файлов: %d%s" % (len(lines), note)
    except Exception as e:
        return "git не ответил: %s" % e


_WEEKLY_SOURCES = (
    ("СЛУЖБЫ", "_src_services"),
    ("ТЕСТЫ", "_src_tests"),
    ("КОММИТЫ", "_src_commits"),
    ("ДИСК", "_src_disk"),
    ("КАНОН", "_src_canon_drift"),
)


def weekly_report(save: bool = True) -> str:
    """Еженедельный аудит дома: все источники — каждый в своей броне
    (закон №10 р3): упавший источник — честная строка «не ответил»,
    отчёт жив. Сохраняется в logs/architect/weekly_<год>-W<неделя>.md
    (одна неделя — один файл, перезапись честна: отчёт снимок, не дневник).

    Источники разрешаются ПО ИМЕНИ в момент вызова — шов честен:
    тесты подменяют _src_* модуля, и отчёт видит подмену (урок
    мёртвого кода: ссылка, захваченная при импорте, мока не видит).
    """
    stamp = time.strftime("%Y-%m-%d %H:%M")
    lines = [
        "# Доклад архитектора — неделя %s" % _iso_week(),
        "(собран %s; команда «доклад архитектора», расписание — вс 20:00)" % stamp,
        "",
    ]
    for title, src_name in _WEEKLY_SOURCES:
        try:
            body = getattr(sys.modules[__name__], src_name)()
        except Exception as e:
            body = "не ответил: %s: %s" % (type(e).__name__, e)
        lines.append("## %s" % title)
        lines.append("- %s" % body)
        lines.append("")
    lines.append("Отчёт — снимок недели: цифры или ничего, без утешений.")
    text = "\n".join(lines)
    if save:
        try:
            ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
            (ARCHIVE_DIR / ("weekly_%s.md" % _iso_week())).write_text(
                text, encoding="utf-8")
        except OSError:
            pass          # отчёт в чате жив и без файла
    return text


def main() -> int:
    _utf8_console()
    parser = argparse.ArgumentParser(description="Дежурный архитектор дома Марфа (RouterAI)")
    parser.add_argument("task", help="задача архитектору обычным текстом")
    parser.add_argument("--files", default=DEFAULT_FILES,
                        help="файлы контекста через запятую (по умолчанию ключевые файлы)")
    args = parser.parse_args()

    env = load_env()
    api_key = env.get("ROUTERAI_API_KEY", "").strip()
    if not api_key:
        print("НЕТ КЛЮЧА: добавь в C:\\Marfa\\.env строку  ROUTERAI_API_KEY=... "
              "(ключ из личного кабинета routerai.ru; в чат его не показывать)")
        return 1
    model = env.get("MARFA_ARCHITECT_MODEL", "").strip() or DEFAULT_MODEL

    rel_files = [f.strip().replace("\\", "/") for f in args.files.split(",") if f.strip()]
    print(f"[архитектор] модель: {model}")
    print(f"[архитектор] контекст: {', '.join(rel_files)}")
    context = build_context(rel_files)
    print(f"[архитектор] контекст собран: {len(context)} символов; спрашиваю RouterAI...")

    try:
        answer, usage_line = ask_routerai(args.task, context, model, api_key)
    except Exception as e:
        print(f"[архитектор] ОШИБКА: {e}")
        return 2

    path = save_transcript(args.task, rel_files, model, answer, usage_line)
    print()
    print("=" * 60)
    print(answer)
    print("=" * 60)
    print(f"[архитектор] {usage_line}")
    print(f"[архитектор] протокол сохранён: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
