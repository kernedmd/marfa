# -*- coding: utf-8 -*-
r"""start_marfa.py — №22: автозапуск дома одной командой (роадмап 30 фишек).

Поднимает всех слуг дома: мозг 8082 + глаза 8083 + панель 5001.
Запуск из корня дома:
    venv\Scripts\python.exe start_marfa.py
    venv\Scripts\python.exe start_marfa.py --в-планировщик   # + старт при входе в Windows

Как это работает:
- конфиг — start_marfa.json рядом со скриптом; при первом запуске создаётся
  сам (шаблон). Все три команды вписаны из живой кнопки Создателя
  (Старт_Марфа.bat от 17.11.2026): мозг Qwen3-30B-A3B Q4_K_M на CPU,
  глаза Qwen2.5-VL-3B + mmproj на CUDA, панель Flask 5001.
  Сменил модель или квант — правь start_marfa.json;
- уже живой слуга не трогается (можно звать старт повторно, безопасно);
- каждый слуга поднимается в СВОЕЙ консоли — дом живёт своей жизнью,
  а Создатель видит логи каждого;
- глаза: холодный старт CUDA ~50 с — ждём до 90 с; панель — до 15 с;
  мозг на CPU разогревается минутами — не ждём, проверь позже «статус»;
- журнал старта — logs/startup.log.

Живость: мозг и глаза — llama-server, /health; панель — /api/status.
Швы для тестов (tests/test_start_marfa.py): _alive / _spawn / _log —
подменяются, реальные порты и процессы не трогаются.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import requests

HOME = Path(__file__).resolve().parent
CONFIG_FILE = HOME / "start_marfa.json"
LOG_FILE = HOME / "logs" / "startup.log"

# (имя, порт, путь здоровья, поле конфига, сколько секунд ждать старта)
SERVICES = [
    ("мозг", 8082, "/health", "brain_cmd", 0),
    ("глаза", 8083, "/health", "eyes_cmd", 90),
    ("панель", 5001, "/api/status", "panel_cmd", 15),
]

TEMPLATE = {
    "brain_cmd": (
        "llama.cpp\\llama-server.exe -m models\\Qwen3-30B-A3B-Q4_K_M.gguf "
        "--host 127.0.0.1 --port 8082 -ngl 0 --temp 0.3"
    ),
    "eyes_cmd": (
        "llama.cpp\\llama-server.exe -m models\\vlm\\Qwen2.5-VL-3B-"
        "Instruct-Q4_K_M.gguf --mmproj models\\vlm\\mmproj-Qwen2.5-VL-"
        "3B-Instruct-Q8_0.gguf -ngl 99 -c 8192 -t 2 --temp 0.1 "
        "--host 127.0.0.1 --port 8083"
    ),
    "panel_cmd": (
        "venv\\Scripts\\python.exe -m flask --app web.app run "
        "--host 127.0.0.1 --port 5001"
    ),
}


def ensure_config(path: Path) -> dict:
    """Конфиг старта; при первом запуске создаётся шаблон."""
    if not path.exists():
        path.write_text(json.dumps(TEMPLATE, ensure_ascii=False, indent=2),
                        encoding="utf-8")
        print("создан шаблон конфига: " + str(path))
    return json.loads(path.read_text(encoding="utf-8"))


def _alive(port: int, path: str) -> bool:
    """Жив ли слуга: HTTP-код 200 по пути здоровья."""
    try:
        return requests.get("http://127.0.0.1:%d%s" % (port, path),
                            timeout=2).status_code == 200
    except Exception:
        return False


def _spawn(cmd: str) -> None:
    """Поднять слугу в отдельной консоли: дом живёт своей жизнью."""
    subprocess.Popen(cmd, shell=True, cwd=str(HOME),
                     creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0))


def _log(line: str) -> None:
    """Журнал старта — logs/startup.log (не падает, если logs/ нет)."""
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + line + "\n")
    except Exception:
        pass


def _wait(port: int, path: str, timeout: float, poll: float = 2.0) -> bool:
    """Ждать, пока слуга оживёт (глаза: холодный CUDA ~50 с)."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _alive(port, path):
            return True
        time.sleep(min(poll, max(0.0, deadline - time.time())))
    return _alive(port, path)


def register_scheduler() -> bool:
    """Вписать дом в автозагрузку Windows: задача «Марфа» при входе."""
    cmd = [
        "schtasks", "/Create", "/F",
        "/TN", "Марфа",
        "/TR", '"%s" "%s"' % (sys.executable, str(Path(__file__).resolve())),
        "/SC", "ONLOGON",
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True)
        return r.returncode == 0
    except Exception:
        return False


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="автозапуск дома Марфы")
    ap.add_argument("--config", default=str(CONFIG_FILE),
                    help="путь к start_marfa.json (по умолчанию — рядом со скриптом)")
    ap.add_argument("--в-планировщик", dest="scheduler", action="store_true",
                    help="вписать дом в автозагрузку Windows (задача «Марфа»)")
    args = ap.parse_args(argv)

    if args.scheduler:
        ok = register_scheduler()
        print("планировщик: " + ("дом вписан в автозагрузку (задача «Марфа»)"
                                 if ok else "не удалось — запусти от администратора"))
        _log("планировщик: " + ("ок" if ok else "сбой"))
        return 0 if ok else 1

    cfg = ensure_config(Path(args.config))
    first_run_brain_empty = (not cfg.get("brain_cmd")
                             and not _alive(8082, "/health"))

    print("=== Старт дома Марфы ===")
    started, skipped = [], []
    for name, port, path, key, wait_secs in SERVICES:
        cmd = (cfg.get(key) or "").strip()
        if _alive(port, path):
            print("%s %d: уже жив — не трогаю" % (name, port))
            skipped.append(name)
            continue
        if not cmd:
            print("%s %d: не запущен и нет команды — впиши «%s» в %s"
                  % (name, port, key, Path(args.config).name))
            continue
        print("%s %d: поднимаю в отдельной консоли..." % (name, port))
        _spawn(cmd)
        if wait_secs <= 0:
            print("   %s на CPU разогревается минутами — проверь позже «статус»"
                  % name)
            started.append(name)
            continue
        if _wait(port, path, wait_secs):
            print("   ожил за %.0f с" % wait_secs)
            started.append(name)
        else:
            print("   НЕ ожил за %d с — посмотри его консоль" % wait_secs)
    _log("старт: подняты %s; уже жили %s" % (started or "—", skipped or "—"))

    if first_run_brain_empty:
        print("\nМОЗГ: команда старта знает только Создатель — открой %s\n"
              "и впиши её в поле brain_cmd (один раз, насовсем)."
              % Path(args.config).name)
    print("\nдом в сборе: панель http://127.0.0.1:5001 — чат с Марфой там.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
