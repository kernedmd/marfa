# -*- coding: utf-8 -*-
"""Почему горло спит: факты по ступеням, без догадок."""
import importlib
import socket
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core import config

port = getattr(config, "PORT_THROAT", 8084)
print("PORT_THROAT =", port)
s = socket.socket(); s.settimeout(1.0)
print("порт слушает:", s.connect_ex(("127.0.0.1", port)) == 0)
s.close()

for p in (ROOT / "core" / "throat.py", ROOT / "models" / "voice" / "v5_6_ru.pt"):
    print(p, "есть" if p.exists() else "НЕТ",
          p.stat().st_size if p.exists() else "")
print("кнопки:", [b.name for b in sorted((ROOT / "scripts").glob("9*.bat"))])

for mod in ("torch", "sounddevice", "numpy"):
    try:
        m = importlib.import_module(mod)
        print(mod, getattr(m, "__version__", "?"))
    except Exception as e:
        print(mod, "НЕТ:", e)

try:
    from core import throat
    print("SPEAKERS:", getattr(throat, "SPEAKERS", None))
    print("DEFAULT:", getattr(throat, "DEFAULT_SPEAKER", None))
    print("пути:", {n: getattr(throat, n) for n in dir(throat)
                    if "MODEL" in n.upper() or "PATH" in n.upper()})
    for name in ("alive", "health"):
        try:
            print("%s() =" % name, getattr(throat, name)())
        except Exception:
            traceback.print_exc()
    try:
        ok, data = throat.synthesize("Марфа на связи.", "baya", 0, 100)
        print("synthesize ok=", ok, "bytes=", len(data or b""))
    except Exception:
        traceback.print_exc()
except Exception:
    traceback.print_exc()