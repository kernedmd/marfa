# -*- coding: utf-8 -*-
"""sync_and_test.py v1.0 — забрать обновления из GitHub и прогнать тесты.

Это задача (б): архитектор пушит в GitHub, Создатель (или сам дом) запускает
одну команду — дом подтягивает изменения и доказывает тестами, что жив.

БЕЗОПАСНОСТЬ:
  - НИКОГДА не пушит и не делает force-что-либо (только fetch + ff-merge);
  - НИКОГДА не трогает .env, models/, logs/, data/;
  - при грязном дереве останавливается (или прячет изменения в stash с --force);
  - полный лог каждого запуска: logs/sync/sync_ДАТА_ВРЕМЯ.txt.

Запуск из C:\\Marfa:
    venv\\Scripts\\python.exe sync_and_test.py            # синк + тесты
    venv\\Scripts\\python.exe sync_and_test.py --no-tests # только синк
    venv\\Scripts\\python.exe sync_and_test.py --force    # спрятать грязь в stash

Коды выхода: 0 = зелено, 1 = красные тесты или отказ по безопасности,
2 = проблема с git/сетью.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LOGS_DIR = ROOT / "logs" / "sync"
TEST_TIMEOUT_SEC = 600
FETCH_TIMEOUT_SEC = 90
DEPS_TIMEOUT_SEC = 900      # opencv+numpy — десятки МБ на медленной сети


def _utf8_console() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            if stream.encoding and stream.encoding.lower().replace("-", "") != "utf8":
                stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def run(cmd: list, timeout: float = 60) -> tuple:
    """Выполнить команду в корне дома. Возвращает (код, stdout+stderr)."""
    try:
        p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True,
                           timeout=timeout, encoding="utf-8", errors="replace")
        out = ((p.stdout or "") + (p.stderr or "")).strip()
        return p.returncode, out
    except subprocess.TimeoutExpired:
        return 2, "таймаут " + str(timeout) + " с: " + " ".join(cmd)
    except Exception as e:
        return 2, repr(e)


def venv_python() -> str:
    """Python из venv дома; если нет — текущий интерпретатор."""
    for cand in (ROOT / "venv" / "Scripts" / "python.exe",
                 ROOT / "venv" / "bin" / "python"):
        if cand.exists():
            return str(cand)
    return sys.executable


def tail(text: str, lines: int = 25) -> str:
    return "\n".join(text.splitlines()[-lines:])


def main() -> int:
    _utf8_console()
    parser = argparse.ArgumentParser(description="Синк из GitHub + тесты дома Марфа")
    parser.add_argument("--force", action="store_true",
                        help="спрятать незакоммиченные изменения в git stash")
    parser.add_argument("--no-tests", action="store_true",
                        help="только подтянуть изменения, тесты не гонять")
    args = parser.parse_args()

    log_parts: list = []
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    print("=" * 56)
    print("  СИНК ДОМА МАРФА — " + stamp)
    print("=" * 56)

    def log(text: str = "") -> None:
        print(text)
        log_parts.append(text)

    # --- 0. Это вообще git-репозиторий? ---
    rc, _ = run(["git", "rev-parse", "--is-inside-work-tree"])
    if rc != 0:
        log("ОТКАЗ: C:\\Marfa не является git-репозиторием. Нечего синкать.")
        return 2

    # --- 1. Чистота дерева (безопасность) ---
    rc, porcelain = run(["git", "status", "--porcelain"])
    dirty = len([ln for ln in porcelain.splitlines() if ln.strip()])
    if dirty:
        if not args.force:
            log("ОТКАЗ: незакоммичено файлов: " + str(dirty) +
                ". Сначала commit/push, либо запусти с --force (спрячу в stash).")
            log("Вот они:")
            log(tail(porcelain, 15))
            return 1
        rc, out = run(["git", "stash", "push", "-u", "-m",
                       "auto-stash before sync " + time.strftime("%Y%m%d_%H%M%S")])
        if rc != 0:
            log("ОТКАЗ: не удалось спрятать изменения в stash. Ничего не менял.")
            log(tail(out, 10))
            return 1
        log("Изменения (" + str(dirty) + " файлов) спрятаны в git stash.")

    # --- 2. Забрать с GitHub ---
    log("")
    log("[1/4] git fetch origin ...")
    rc, out = run(["git", "fetch", "origin"], timeout=FETCH_TIMEOUT_SEC)
    if rc != 0:
        log("ОТКАЗ: fetch не прошёл (сеть? ключи?). Дом НЕ изменён.")
        log(tail(out, 10))
        return 2
    log("fetch OK")

    # --- 3. Насколько отстали и ff-merge ---
    _, branch = run(["git", "branch", "--show-current"])
    branch = branch or "main"
    rc, counts = run(["git", "rev-list", "--left-right", "--count",
                      "HEAD...origin/" + branch])
    try:
        ahead, behind = (int(x) for x in counts.split())
    except Exception:
        ahead, behind = 0, 0
    log("")
    if behind == 0:
        log("[2/4] Локальная ветка " + branch + " уже актуальна (ahead=" +
            str(ahead) + ", behind=0).")
    else:
        log("[2/4] Сзади " + str(behind) + " коммитов, ahead=" + str(ahead) +
            ". Подтягиваю (только fast-forward)...")
        rc, out = run(["git", "merge", "--ff-only", "origin/" + branch])
        if rc != 0:
            log("ОТКАЗ: ff-merge не прошёл (истории разошлись). Дом НЕ изменён.")
            log(tail(out, 10))
            return 2
        _, last = run(["git", "log", "-1", "--oneline"])
        log("Обновлено. Теперь HEAD: " + last)

    # --- 3.5 Зависимости едут с кодом (урок cv2, 22.11) ---
    # Код приезжает git'ом, а requirements.txt — нет: opencv-python
    # был заявлен в requirements раньше, чем оказался в venv, и Марфа
    # осталась без камеры. pip идемпотентен и быстр, когда всё уже стоит;
    # ставим ВСЕГДА, а не только после merge — синк может быть первым
    # после ручного git pull из бандла. Только venv-интерпретатор
    # (голый pip на Windows — чужой, системный).
    log("")
    log("[3/4] Зависимости дома (pip install -r requirements.txt)...")
    py = venv_python()
    rc, out = run([py, "-m", "pip", "install", "--no-input",
                   "--disable-pip-version-check", "-r", "requirements.txt"],
                  timeout=DEPS_TIMEOUT_SEC)
    if rc == 0:
        log("зависимости на месте")
    else:
        log("ВНИМАНИЕ: зависимости не поставились — тесты и камера могут "
            "покраснеть. Хвост вывода:")
        log(tail(out, 8))

    # --- 4. Тесты ---
    if args.no_tests:
        log("")
        log("[4/4] Тесты пропущены (--no-tests).")
        log("ИТОГ: синк прошёл, тесты не гонялись.")
        _save_log(log_parts)
        return 0

    log("")
    log("[4/4] Прогоняю тесты (до 10 минут)...")
    rc, out = run([py, "-m", "pytest", "tests/", "-q", "--tb=short"],
                  timeout=TEST_TIMEOUT_SEC)
    log("")
    log(tail(out, 30))
    _save_log(log_parts + ["", "--- полный вывод pytest ---", out])
    if rc == 0:
        log("")
        log("ИТОГ: ЗЕЛЁНО. Дом обновлён и здоров.")
        return 0
    if "No module named pytest" in out:
        log("")
        log("ИТОГ: pytest не установлен в venv. Поставь: " + py + " -m pip install pytest")
        return 1
    log("")
    log("ИТОГ: КРАСНО. Код подтянут, но тесты упали — читай лог выше.")
    return 1


def _save_log(parts: list) -> None:
    """Сохранить протокол запуска. Ошибка лога не ломает синк."""
    try:
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        path = LOGS_DIR / ("sync_" + time.strftime("%Y%m%d_%H%M%S") + ".txt")
        path.write_text("\n".join(parts), encoding="utf-8")
        print("Лог сохранён: " + str(path))
    except Exception as e:
        print("Лог не сохранён (не критично): " + repr(e))


if __name__ == "__main__":
    sys.exit(main())
