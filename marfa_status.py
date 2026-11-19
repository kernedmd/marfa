# -*- coding: utf-8 -*-
"""marfa_status.py v1.0 — «Как дома дела?» Одна команда, полная картина.

ЧИТАЕТ ВСЁ, НЕ МЕНЯЕТ НИЧЕГО. Гейт батареи не нарушает: ни памяти,
ни доктрины, только наблюдение.

Проверяет: мозг 8082, панель 5001, RAM (Ф97: 85/92), диск C:, файл модели,
Python в venv (ADR-011: дом живёт на 3.11), чистота git-дерева, .env
(только ИМЕНА ключей — значения не печатаются никогда, Ф105).

Запуск из C:\\Marfa:
    venv\\Scripts\\python.exe marfa_status.py
Выходной код: 0 = FAIL'ов нет, 1 = есть FAIL (удобно для .bat и планировщика).
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

OK, WARN, FAIL, INFO = "OK", "WARN", "FAIL", "INFO"
MARK = {OK: "[ OK ]", WARN: "[WARN]", FAIL: "[FAIL]", INFO: "[INFO]"}
RESULTS: list = []


def add(level: str, text: str) -> None:
    RESULTS.append((level, text))
    print(MARK[level] + " " + text)


def _utf8_console() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            if stream.encoding and stream.encoding.lower().replace("-", "") != "utf8":
                stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


# ---------- чистые функции (их проверяет tests/test_status.py) ----------

def fmt_gb(num_bytes: float) -> float:
    """Байты -> гигабайты (округление до 0.1)."""
    return round(num_bytes / 1024 ** 3, 1)


def ram_verdict(pct: float, warn_pct: float = 85, crit_pct: float = 92) -> str:
    """Вердикт Ф97 по проценту RAM: 85+ тревога, 92+ критично."""
    if pct >= crit_pct:
        return FAIL
    if pct >= warn_pct:
        return WARN
    return OK


def parse_porcelain(out: str) -> int:
    """Сколько файлов изменено/не в треке по выводу git status --porcelain."""
    return len([ln for ln in out.splitlines() if ln.strip()])


def env_key_names(text: str) -> list:
    """ИМЕНА ключей из .env. Значения не возвращаются никогда (Ф105)."""
    names = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        names.append(line.split("=", 1)[0].strip())
    return sorted(set(names))


# ---------- зонды ----------

def probe(url: str, timeout: float = 3.0) -> bool:
    """GET без зависаний: True только при HTTP 200."""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.status == 200
    except Exception:
        return False


def git(args: list, timeout: float = 20) -> tuple:
    """Запуск git в корне дома. Возвращает (код, вывод)."""
    try:
        p = subprocess.run(["git"] + args, cwd=ROOT, capture_output=True,
                           text=True, timeout=timeout, encoding="utf-8", errors="replace")
        return p.returncode, (p.stdout or "").strip()
    except Exception as e:
        return 1, str(e)


# ---------- главный проход ----------

def main() -> int:
    _utf8_console()
    print("=" * 56)
    print("  ДОМ МАРФА — СТАТУС  " + __doc__.splitlines()[0].split("—")[1].strip())
    print("=" * 56)

    # 0. Закон дома: core/config.py
    config = None
    try:
        from core import config  # noqa: F401
        add(OK, "core/config.py читается (закон дома на месте)")
    except Exception as e:
        add(FAIL, "core/config.py НЕ импортируется: " + repr(e))

    # 1. Мозг (8082) и панель (5001)
    brain_url = (config.BRAIN_URL if config else "http://127.0.0.1:8082").rstrip("/")
    if probe(brain_url + "/health"):
        add(OK, "Мозг жив: " + brain_url)
    else:
        add(FAIL, "Мозг не отвечает: " + brain_url + " (грузится? запусти Старт_Марфа)")
    if probe("http://127.0.0.1:5001/health"):
        add(OK, "Панель жива: http://127.0.0.1:5001")
    else:
        add(FAIL, "Панель не отвечает: http://127.0.0.1:5001")

    # 2. RAM (Ф97) — проценты от фактического объёма
    try:
        import psutil
        vm = psutil.virtual_memory()
        warn_pct = config.MONITOR_WARN_PCT if config else 85
        crit_pct = config.MONITOR_CRIT_PCT if config else 92
        used_gb = fmt_gb(vm.total - vm.available)
        total_gb = fmt_gb(vm.total)
        verdict = ram_verdict(vm.percent, warn_pct, crit_pct)
        line = "RAM: " + str(used_gb) + " / " + str(total_gb) + " ГБ (" + str(vm.percent) + "%)"
        line += "  пороги Ф97: " + str(warn_pct) + "/" + str(crit_pct)
        add(verdict, line)
    except ImportError:
        add(INFO, "psutil не установлен — RAM не проверена (pip install psutil)")

    # 3. Диск (резерв дома: 10 ГБ на распаковку моделей)
    du = shutil.disk_usage(ROOT)
    free_gb = fmt_gb(du.free)
    if free_gb < 20:
        add(WARN, "Диск " + str(ROOT.anchor) + " свободно всего " + str(free_gb) + " ГБ (резерв дома 10 ГБ)")
    else:
        add(OK, "Диск " + str(ROOT.anchor) + " свободно " + str(free_gb) + " ГБ")

    # 4. Модель мозга на месте? (без неё дом не перезапустить)
    model_name = config.GGUF_FILES["Q4_K_M"] if config else "Qwen3-30B-A3B-Q4_K_M.gguf"
    expected_gb = config.MODEL_QUANTS_GB["Q4_K_M"] if config else 18.63
    model_path = ROOT / "models" / model_name
    if model_path.exists():
        real_gb = fmt_gb(model_path.stat().st_size)
        if abs(real_gb - expected_gb) > expected_gb * 0.1:
            add(WARN, "Модель " + model_name + ": " + str(real_gb) + " ГБ (ожидалось ~" + str(expected_gb) + ")")
        else:
            add(OK, "Модель на месте: " + model_name + " (" + str(real_gb) + " ГБ)")
    else:
        add(WARN, "Модель не найдена: " + str(model_path))

    # 5. Python в venv — дом живёт на 3.11 (ADR-011)
    vpy = ROOT / "venv" / "Scripts" / "python.exe"
    if not vpy.exists():
        vpy = ROOT / "venv" / "bin" / "python"
    if vpy.exists():
        try:
            p = subprocess.run([str(vpy), "-V"], capture_output=True, text=True,
                               timeout=15, encoding="utf-8", errors="replace")
            ver = (p.stdout or p.stderr or "").strip()
            if ver.startswith("Python 3.11"):
                add(OK, "venv: " + ver + " (как требует ADR-011)")
            else:
                add(WARN, "venv: " + ver + " — дом собирается на 3.11, прочее не проверялось")
        except Exception as e:
            add(WARN, "venv не отвечает: " + repr(e))
    else:
        add(WARN, "venv не найден: " + str(vpy))

    # 6. Git-дерево: чистота, ветка, последний коммит
    rc, _ = git(["rev-parse", "--is-inside-work-tree"])
    if rc != 0:
        add(INFO, "Не git-репозиторий (архив без .git) — синка не будет")
    else:
        _, branch = git(["branch", "--show-current"])
        _, porcelain = git(["status", "--porcelain"])
        dirty = parse_porcelain(porcelain)
        _, last = git(["log", "-1", "--oneline"])
        if dirty:
            add(WARN, "Git: ветка " + branch + ", НЕЗАКОММИЧЕНО файлов: " + str(dirty))
        else:
            add(OK, "Git: ветка " + branch + ", дерево чистое")
        add(INFO, "Последний коммит: " + last)

    # 7. .env — только имена ключей (Ф105: значения не печатаются)
    env_path = ROOT / ".env"
    if env_path.exists():
        names = env_key_names(env_path.read_text(encoding="utf-8-sig", errors="replace"))
        if names:
            add(OK, ".env найден, ключи: " + ", ".join(names))
        else:
            add(INFO, ".env найден, но ключей в нём нет")
    else:
        add(INFO, ".env не найден (ROUTERAI_API_KEY и прочие живут там же)")

    # Итог
    fails = sum(1 for lvl, _ in RESULTS if lvl == FAIL)
    warns = sum(1 for lvl, _ in RESULTS if lvl == WARN)
    print("-" * 56)
    if fails:
        print("ИТОГ: " + str(fails) + " FAIL, " + str(warns) + " WARN — дом требует внимания")
    elif warns:
        print("ИТОГ: 0 FAIL, " + str(warns) + " WARN — живём, но следи")
    else:
        print("ИТОГ: дом в порядке")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
