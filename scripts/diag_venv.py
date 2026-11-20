# -*- coding: utf-8 -*-
r"""diag_venv.py — диагностика venv одним прогоном (урок 13.11.2026, коммит 27).

selftest упал с «1 error during collection», а verify показал только хвост —
причины не было видно. Этот скрипт импортирует КАЖДЫЙ пакет, нужный офлайн-тестам,
отдельно и печатает версию или точную ошибку — по нему видно, какой модуль битый.

Запуск: venv\Scripts\python.exe scripts\diag_venv.py
Код 0 = все импорты живы; 1 = есть провалы (список в конце).

Урок 13.11.2026 (коммит 28): печать ТОЛЬКО латиницей. Вывод уходит в verify.ps1
через пайп (Invoke-ExeProbe), python на Windows кодирует пайп локальной OEM-
кодировкой — кириллица превращалась в «????» на консоли и в журнале. Латиница
не зависит от кодовой страницы. DeprecationWarning от flask.__version__ давим:
это шум в диагностике.
"""
import importlib
import os
import sys
import warnings

warnings.filterwarnings("ignore")

# Запуск как файла кладёт в sys.path[0] папку scripts\, а не корень дома — без этой
# вставки sensors.monitor / web.app не найдутся и диагноcтика врала бы «FAIL».
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

MODULES = [
    ("flask", "web-panel (web.app, port 5001)"),
    ("psutil", "RAM-monitor (sensors.monitor)"),
    ("requests", "brain-client (core.brain)"),
    ("pytest", "selftest audit"),
    ("torch", "QLoRA-stack (step 04)"),
    ("transformers", "QLoRA-stack (step 04)"),
    ("sensors.monitor", "RAM sensor"),
    ("web.app", "whole panel 5001"),
]

def main():
    bad = []
    for name, why in MODULES:
        try:
            mod = importlib.import_module(name)
            ver = str(getattr(mod, "__version__", "")).strip()
            print("OK   {} {}".format(name, ver).rstrip())
        except Exception as e:  # noqa: BLE001 — любая причина импорта = провал позиции
            print("FAIL {} ({}): {}: {}".format(name, why, type(e).__name__, e))
            bad.append(name)
    try:
        import importlib.metadata as md
        for pkg in ("flask", "werkzeug", "itsdangerous", "jinja2", "click",
                    "psutil", "requests", "pytest", "transformers", "torch"):
            try:
                print("meta {}=={}".format(pkg, md.version(pkg)))
            except Exception:
                print("meta {}: NOT INSTALLED (no metadata)".format(pkg))
    except Exception as e:  # noqa: BLE001
        print("meta unavailable: {}".format(e))
    if bad:
        print("FAILS: {}".format(", ".join(bad)))
        return 1
    print("All imports alive.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
