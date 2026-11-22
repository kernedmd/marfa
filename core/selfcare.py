# -*- coding: utf-8 -*-
r"""core/selfcare.py — АПТЕЧКА ДОМА: Марфа ставит модули сама (22.11).

Живой прогон станции (доклад Создателя): «ПОчему ты сам не установишь?» —
а потом руками был запущен pip из C:\Users\User, который ответил
«Requirement already satisfied … python311\lib\site-packages» — и Марфа
всё равно не увидела cv2. Два корня одной беды:

1. ГОЛЫЙ pip НА WINDOWS — ЧУЖОЙ PIP. `pip` без пути берётся из PATH и
   принадлежит СИСТЕМНОМУ Python (c:\users\user\appdata\...\python311),
   а дом живёт в venv (C:\Marfa\venv). «Уже удовлетворено» от чужого
   pip — не про наш venv. Единственно верный путь — pip СВОЕГО
   интерпретатора: sys.executable -m pip. Это и делает аптечка.

2. КОД ЕЗДИТ GIT'ОМ, ЗАВИСИМОСТИ — НЕТ. sync_and_test подтягивал
   коммиты, но requirements.txt не исполнялся — opencv-python приехал
   в requirements раньше, чем в venv. Лечение вторым концом —
   sync_and_test.py теперь ставит зависимости вместе с кодом.

Директива Создателя «почему ты сам не установишь» = резолюция: Марфа
ставит недостающие модули САМА, в момент, когда они понадобились,
рассказывая об этом в чат (эфир: стадия «аптечка: ставлю…» + секунды).

ГРАНИЦЫ АПТЕЧКИ (безопасность):
- WHITELIST: только модули, которые дом ЗАЯВИЛ в requirements.txt;
  «поставь <что угодно из интернета» — не команда аптечке, мозг не
  может расширить список своим текстом;
- только pip, только PyPI-пакеты по имени, без URL, без --index-url
  и без shell=True: список аргументов, а не строка;
- истина установки — ИМПОРТ после pip, а не код возврата: pip может
  «успешно» не поставить то, что просили.

Швы для тестов: module_version / _run_pip — tests/test_selfcare.py
подменяет их, реальный pip в тестах не живёт.
"""
from __future__ import annotations

import importlib
import subprocess
import sys
import time

from core import progress

# Модули, которые дом знает и имеет право ставить сам. Ключ — имя
# импорта, значение — имя пакета в pip (cv2 прячется за opencv-python,
# PIL — за pillow). Всё отсюда уже заявлено в requirements.txt.
KNOWN_MODULES = {
    "cv2": "opencv-python",
    "mss": "mss",
    "PIL": "pillow",
    "sounddevice": "sounddevice",
    "pyautogui": "pyautogui",
}

INSTALL_TIMEOUT_SEC = 900     # opencv + numpy — десятки МБ, сеть бывает медленной


def module_version(import_name: str):
    """Живой импорт: версия модуля или None (шов для тестов).

    Ленивый импорт в живом процессе ловит модуль, поставленный ПОСЛЕ
    старта дома — site-packages перечитывается при каждой попытке."""
    try:
        mod = importlib.import_module(import_name)
        return str(getattr(mod, "__version__", "")).strip() or "?"
    except Exception:
        return None


def _run_pip(cmd: list, timeout: float) -> tuple:
    """Исполнить pip СВОЕГО интерпретатора (шов для тестов).

    Список аргументов без shell — никакой интерполяции текста Создателя
    или мозга в командную строку. Возвращает (код, вывод)."""
    try:
        p = subprocess.run(cmd, capture_output=True, text=True,
                           timeout=timeout, encoding="utf-8",
                           errors="replace")
        return p.returncode, ((p.stdout or "") + (p.stderr or ""))
    except subprocess.TimeoutExpired:
        return 2, "таймаут %d с — сеть, наверное, спит" % timeout
    except Exception as e:
        return 2, repr(e)


def _tail(text: str, lines: int = 4) -> str:
    return "\n".join(text.strip().splitlines()[-lines:])


def pip_command(import_name: str) -> list:
    r"""Команда установки ИМЕННО В ОКРУЖЕНИЕ ДОМА.

    sys.executable — интерпретатор, в котором живёт этот процесс:
    на станции это C:\Marfa\venv\Scripts\python.exe. Голый `pip` из
    PATH так не гарантирует ничего (урок 22.11: чужой python311)."""
    pkg = KNOWN_MODULES.get(import_name, import_name)
    return [sys.executable, "-m", "pip", "install", "--no-input",
            "--disable-pip-version-check", pkg]


def manual_command(import_name: str) -> str:
    """Человеческая команда для Создателя — если аптечка не справилась.

    Путь в кавычках: пробелы в пути Windows не должны ломать команду."""
    pkg = KNOWN_MODULES.get(import_name, import_name)
    return '"%s" -m pip install %s' % (sys.executable, pkg)


def ensure_module(import_name: str,
                  timeout: float = INSTALL_TIMEOUT_SEC) -> dict:
    """Модуль есть? Нет — поставить самому и доложить фактами.

    Возвращает отчёт (только простые значения — он ложится в чат):
    ok — модуль импортируется ПОСЛЕ всех попыток;
    already — был ещё до аптечки;
    version / secs / pkg / rc / tail — чем лечили и что вышло;
    why — "not_whitelisted", если модуль дому не знаком.
    """
    ver = module_version(import_name)
    if ver:
        return {"ok": True, "already": True, "version": ver, "secs": 0.0,
                "import_name": import_name,
                "pkg": KNOWN_MODULES.get(import_name, import_name),
                "rc": None, "tail": "", "why": None}
    if import_name not in KNOWN_MODULES:
        return {"ok": False, "already": False, "version": None, "secs": 0.0,
                "import_name": import_name, "pkg": import_name,
                "rc": None, "tail": "", "why": "not_whitelisted"}
    pkg = KNOWN_MODULES[import_name]
    progress.stage("аптечка: ставлю %s в свой venv — это может занять "
                   "минуту…" % pkg)
    t0 = time.time()
    cmd = pip_command(import_name)
    rc, out = _run_pip(cmd, timeout)
    secs = time.time() - t0
    # истина — импорт, а не код возврата pip
    ver = module_version(import_name)
    return {"ok": bool(ver), "already": False, "version": ver,
            "secs": round(secs, 1), "import_name": import_name,
            "pkg": pkg, "rc": rc,
            "tail": _tail(out) if not ver else "", "why": None}


def render_report(rep: dict) -> str:
    """Отчёт аптечки одной строкой — для чата и самотеста камеры."""
    if rep.get("ok") and rep.get("already"):
        return "модуль %s уже стоит (%s)" % (rep.get("pkg"), rep.get("version"))
    if rep.get("ok"):
        return ("поставила сама за %.0f с (%s %s)"
                % (rep.get("secs", 0.0), rep.get("pkg"),
                   rep.get("version") or ""))
    if rep.get("why") == "not_whitelisted":
        return ("модуль «%s» дому не знаком — аптечка ставит только своё "
                "из requirements.txt" % rep.get("pkg"))
    why = rep.get("tail") or ("код %s" % rep.get("rc"))
    return ("не смогла: %s — поставь руками: %s"
            % (why, manual_command(str(rep.get("import_name") or "cv2"))))
