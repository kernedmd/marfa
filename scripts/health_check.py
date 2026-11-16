# -*- coding: utf-8 -*-
"""health_check.py — пункт №31 волны 0 бэклога Марфы v9.4.

Стартовая проверка дома: мозг на 8082, панель на 5001, GPU, диск, RAM,
venv, модели, .env (только имена ключей — значения не читаем и не печатаем
никогда, Ф105). Честный отчёт вместо падения: любая беда описывается
словами, скрипт не падает.

Зависимости: только stdlib Python 3.11.

Запуск из корня дома:
    venv\\Scripts\\python.exe scripts\\health_check.py
Флаги:
    --root C:\\Marfa      корень дома (по умолчанию: MARFA_ROOT или C:\\Marfa)
    --brain-url URL       адрес мозга (по умолчанию http://127.0.0.1:8082)
    --json                машинный отчёт в stdout (для логов)
Коды выхода: 0 — всё зелёное; 1 — есть жёлтые или красные пункты;
             2 — сам корень дома не найден.
"""
import argparse
import ctypes
import json
import os
import platform
import shutil
import socket
import subprocess
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PORTS = {"Мозг (llama-server)": 8082, "Панель Марфы": 5001}
DISK_MIN_GB = 20.0      # меньше — жёлтый флаг
RAM_LOAD_RED = 92.0     # % занятой RAM — красный (Ф97 следит за 85)


def mb(x):
    return round(x / (1024 * 1024), 1)


def gb(x):
    return round(x / (1024 ** 3), 1)


def ram_stats():
    """(total, avail, load%) — Windows через ctypes, иначе /proc/meminfo."""
    try:
        if platform.system() == "Windows":
            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong),
                            ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong),
                            ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong),
                            ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong),
                            ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
            st = MEMORYSTATUSEX()
            st.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st))
            return st.ullTotalPhys, st.ullAvailPhys, float(st.dwMemoryLoad)
        with open("/proc/meminfo", encoding="ascii") as f:
            vals = {}
            for line in f:
                k, v = line.split(":", 1)
                vals[k] = int(v.strip().split()[0]) * 1024
            total = vals["MemTotal"]
            avail = vals.get("MemAvailable", vals.get("MemFree", 0))
            return total, avail, round(100.0 * (total - avail) / total, 1)
    except Exception as e:
        return 0, 0, -1.0,  # хвост-кортеж не используется — см. ниже


def ram_stats_safe():
    try:
        r = ram_stats()
        if len(r) == 3:
            return r
    except Exception:
        pass
    return 0, 0, -1.0


def tcp_ok(port, host="127.0.0.1", timeout=2.0):
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def brain_info(base_url, timeout=10):
    """GET /v1/models: список id моделей, если мозг жив."""
    try:
        with urllib.request.urlopen(base_url.rstrip("/") + "/v1/models", timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8", "replace"))
        return [m.get("id", "?") for m in data.get("data", [])]
    except Exception as e:
        return None


def gpu_info():
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total,memory.used,temperature.gpu",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10)
        if out.returncode == 0 and out.stdout.strip():
            parts = [p.strip() for p in out.stdout.strip().splitlines()[0].split(",")]
            if len(parts) == 4:
                return {"name": parts[0], "vram_total_mb": parts[1],
                        "vram_used_mb": parts[2], "temp_c": parts[3]}
    except Exception:
        pass
    return None


def env_keys(path):
    """Только имена ключей из .env — значения не читаем (Ф105)."""
    keys = []
    try:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            keys.append(line.split("=", 1)[0].strip())
    except Exception:
        pass
    return keys


def main():
    ap = argparse.ArgumentParser(description="Стартовая проверка дома Марфы")
    ap.add_argument("--root", default=None, help="корень дома")
    ap.add_argument("--brain-url", default="http://127.0.0.1:8082")
    ap.add_argument("--json", action="store_true", help="машинный отчёт")
    args = ap.parse_args()

    root = Path(args.root or os.environ.get("MARFA_ROOT") or
                ("C:\\Marfa" if platform.system() == "Windows" else "."))
    report = {"time": datetime.now().isoformat(timespec="seconds"),
              "root": str(root), "checks": [], "status": "OK"}
    lines = []
    yellow = red = 0

    def add(name, state, detail):
        nonlocal yellow, red
        report["checks"].append({"name": name, "state": state, "detail": detail})
        mark = {"OK": "[ OK  ]", "WARN": "[ВНИМ ]", "FAIL": "[ПЛОХО]"}.get(state, "[ ??  ]")
        if state == "WARN":
            yellow += 1
        elif state == "FAIL":
            red += 1
        lines.append("%s %-28s %s" % (mark, name, detail))

    # 1. Корень дома
    if root.is_dir():
        add("Корень дома", "OK", str(root))
    else:
        add("Корень дома", "FAIL", "не найден: %s" % root)
        report["status"] = "FAIL"
        finish(args, report, lines, 2)

    # 2. Мозг
    models = brain_info(args.brain_url)
    if models:
        add("Мозг (порт 8082)", "OK", "жив, модели: %s" % ", ".join(models))
    elif tcp_ok(8082):
        add("Мозг (порт 8082)", "WARN", "порт открыт, но /v1/models не ответил")
    else:
        add("Мозг (порт 8082)", "WARN", "не отвечает — запускай scripts\\start_llama_server.bat")

    # 3. Панель и соседние порты
    for name, port in PORTS.items():
        if port == 8082:
            continue
        add(name + " (порт %d)" % port, "OK" if tcp_ok(port) else "WARN",
            "жив" if tcp_ok(port) else "не отвечает")
    add("Порт 5000 (чужой)", "OK" if not tcp_ok(5000) else "WARN",
        "свободен" if not tcp_ok(5000) else "занят кем-то — правило 6.4: не трогаем, только смотрим")

    # 4. RAM
    total, avail, load = ram_stats_safe()
    if total:
        state = "FAIL" if load >= RAM_LOAD_RED else ("WARN" if load >= 85.0 else "OK")
        add("Оперативная память", state,
            "%s ГБ занято %s%% (свободно %s ГБ); порог Ф97 — 85%%" % (gb(total), load, gb(avail)))
    else:
        add("Оперативная память", "WARN", "не удалось измерить")

    # 5. Диск
    try:
        du = shutil.disk_usage(str(root if root.exists() else root.anchor or "."))
        state = "OK" if du.free / 1024 ** 3 >= DISK_MIN_GB else "WARN"
        add("Диск дома", state, "свободно %s ГБ (порог %s ГБ)" % (gb(du.free), DISK_MIN_GB))
    except Exception:
        add("Диск дома", "WARN", "не удалось измерить")

    # 6. GPU
    g = gpu_info()
    if g:
        add("GPU", "OK", "%s, VRAM %s/%s МБ, %s C" %
            (g["name"], g["vram_used_mb"], g["vram_total_mb"], g["temp_c"]))
    else:
        add("GPU", "WARN", "nvidia-smi недоступен — смотрим только CPU-сторону")

    # 7. venv
    venv_py = root / "venv" / ("Scripts" if platform.system() == "Windows" else "bin") / \
        ("python.exe" if platform.system() == "Windows" else "python")
    add("venv", "OK" if venv_py.exists() else "WARN",
        "на месте" if venv_py.exists() else "не найден: %s" % venv_py)

    # 8. Модели
    models_dir = root / "models"
    if models_dir.is_dir():
        ggufs = sorted(models_dir.glob("*.gguf"))
        if ggufs:
            sizes = "; ".join("%s — %s ГБ" % (f.name, gb(f.stat().st_size)) for f in ggufs)
            add("Модели (GGUF)", "OK", sizes)
        else:
            add("Модели (GGUF)", "WARN", "папка пуста")
    else:
        add("Модели (GGUF)", "WARN", "папка models/ не найдена")

    # 9. .env — только имена ключей
    env_path = root / ".env"
    if env_path.is_file():
        keys = env_keys(env_path)
        add(".env", "OK" if keys else "WARN",
            ("ключи: " + ", ".join(keys)) if keys else "файл есть, ключей не видно")
    else:
        add(".env", "WARN", "файл не найден (значения всё равно никогда не печатаем)")

    # 10. Логи
    logs_dir = root / "logs"
    if logs_dir.is_dir():
        try:
            newest = max(logs_dir.iterdir(), key=lambda p: p.stat().st_mtime, default=None)
            add("Логи", "OK", "папка жива, свежий: %s" %
                (newest.name if newest else "пусто"))
        except Exception:
            add("Логи", "OK", "папка жива")
    else:
        add("Логи", "WARN", "папка logs/ не найдена")

    report["status"] = "FAIL" if red else ("WARN" if yellow else "OK")
    finish(args, report, lines, 1 if (red or yellow) else 0)


def finish(args, report, lines, code):
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=1))
    else:
        print("=" * 64)
        print("  ПРОВЕРКА ДОМА МАРФЫ — " + report["time"])
        print("  Корень: " + report["root"])
        print("=" * 64)
        for ln in lines:
            print(ln)
        print("-" * 64)
        if report["status"] == "OK":
            print("Итог: дом в порядке, все проверки зелёные.")
        else:
            print("Итог: %s — смотри строки с [ВНИМ ] и [ПЛОХО] выше." % report["status"])
        print("Отчёт честный, не паникующий: жёлтое — план действий, а не авария.")
    # однострочная запись в лог дома, если папка есть — молча
    try:
        logs = Path(report["root"]) / "logs"
        if logs.is_dir():
            with open(logs / "health_check.log", "a", encoding="utf-8") as f:
                f.write("%s\t%s\texit=%d\n" % (report["time"], report["status"], code))
    except Exception:
        pass
    sys.exit(code)


if __name__ == "__main__":
    main()
