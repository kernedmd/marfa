# -*- coding: utf-8 -*-
"""ГОЛОС v3: подъём горла рефлексом, честный рот, закон факта, похвала."""
from pathlib import Path
import py_compile
import re
import shutil
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
V = ROOT / "core" / "voice.py"
A = ROOT / "core" / "agent.py"
for p in (V, A):
    if not p.exists():
        sys.exit("нет %s" % p)
vsrc = V.read_text(encoding="utf-8")
asrc = A.read_text(encoding="utf-8")
stamp = time.strftime("%Y%m%d_%H%M%S")


def sub_i(src, pattern, lines, name):
    m = re.search(pattern, src)
    if not m:
        sys.exit("ЯКОРЬ НЕ НАЙДЕН: " + name)
    i = m.group("i")
    return src[:m.start()] + "\n".join(i + x if x else "" for x in lines) + src[m.end():]


# ---------- voice.py: честный рот ----------
if "произношу вслух ЗАПАСНЫМ РОТОМ" not in vsrc:
    vsrc = sub_i(
        vsrc, r'(?P<i>[ \t]*)return "произношу вслух: «%s»" % preview',
        ['if _throat_alive():',
         '    return "произношу вслух (горло silero): «%s»" % preview',
         'return ("произношу вслух ЗАПАСНЫМ РОТОМ Windows (Ирина, робот) — "',
         '        "горло silero спит: «%s»\\n"',
         '        "Скажи «разбуди горло» или «проверь горло»."',
         '        % preview)'],
        "say preview")

if "def mouth_report" not in vsrc:
    vsrc += '''

# ---------------- ГОЛОС v3 ----------------
_LAST_MOUTH = {"mouth": "", "ts": 0.0}
_speak_v2 = speak


def speak(text: str, limit: int = SAY_LIMIT) -> str:
    out = _speak_v2(text, limit=limit)
    try:
        if "(silero" in out:
            _LAST_MOUTH.update(mouth="silero", ts=time.time())
        elif out.startswith("Сказала вслух"):
            _LAST_MOUTH.update(mouth="sapi", ts=time.time())
    except Exception:
        pass
    return out


def mouth_report() -> str:
    m = _LAST_MOUTH.get("mouth")
    if not m:
        return "рот ещё не говорил — скажи «скажи вслух привет»"
    when = time.strftime("%H:%M:%S", time.localtime(_LAST_MOUTH.get("ts") or 0))
    if m == "silero":
        return "последний раз (%s) говорило ГОРЛО silero — живой голос" % when
    return ("последний раз (%s) говорил ЗАПАСНОЙ рот Windows SAPI (Ирина); "
            "горло спит или не смогло — «разбуди горло»" % when)


def throat_report() -> str:
    root = Path(__file__).resolve().parents[1]
    port = getattr(config, "PORT_THROAT", 8084)
    lines = ["ПРОВЕРКА ГОРЛА (silero), порт %s:" % port]
    model = root / "models" / "voice" / "v5_6_ru.pt"
    lines.append("  · модель: %s" % ("есть (%d МБ)" % (model.stat().st_size // 1048576)
                                     if model.exists() else "НЕТ %s" % model))
    for mod in ("requests", "sounddevice", "torch"):
        try:
            m = __import__(mod)
            lines.append("  · %s: %s" % (mod, getattr(m, "__version__", "есть")))
        except Exception as e:
            lines.append("  · %s: НЕТ — %s" % (mod, e))
    try:
        from core import throat as _t
        alive = _t.alive()
        lines.append("  · слуга: %s" % ("ЖИВ" if alive else "СПИТ — «разбуди горло»"))
        if alive:
            lines.append("  · health: %s" % (_t.health(),))
    except Exception as e:
        lines.append("  · горло не осмотрелось: %s: %s" % (type(e).__name__, e))
    return "\\n".join(lines)
'''

if "def wake_throat" not in vsrc:
    vsrc += '''

def wake_throat() -> str:
    """«разбуди горло» — кнопка 95 [2] словами, без консоли."""
    root = Path(__file__).resolve().parents[1]
    model = root / "models" / "voice" / "v5_6_ru.pt"
    if not model.exists():
        return "модели нет: %s — положи v5_6_ru.pt (кнопка 95 [4])" % model
    missing = []
    for mod in ("requests", "sounddevice"):
        try:
            __import__(mod)
        except Exception:
            missing.append(mod)
    if missing:
        return ("не хватает модулей: %s. Поставь в ТОТ ЖЕ python, что крутит панель:\\n"
                "%s -m pip install %s"
                % (", ".join(missing), sys.executable, " ".join(missing)))
    try:
        from core import throat as _t
        ok, note = _t.ensure_server()
    except Exception as e:
        return "горло не поднялось: %s: %s — пришли это архитектору" % (type(e).__name__, e)
    if ok:
        return ("горло ЖИВО на порту %s. %s\\n"
                "Проба: «скажи вслух привет» — должен быть живой голос, не Ирина."
                % (getattr(config, "PORT_THROAT", 8084), note))
    return ("горло НЕ ОЖИЛО: %s\\nПришли этот вывод; частая причина — загрузка "
            "модели в torch 2.6 (weights_only)." % note)


def lay_throat() -> str:
    try:
        from core import throat as _t
        return _t.lay_to_rest()
    except Exception as e:
        return "горло не уложилось: %s: %s" % (type(e).__name__, e)
'''

# ---------- agent.py: рефлексы горла ----------
if '"разбуди горло"' not in asrc:
    block = ['if lowq in ("разбуди горло", "подними горло", "запусти горло",',
             '            "включи горло", "горло"):',
             '    from core import voice as _voice',
             '    return Reply(_voice.wake_throat(), "python", "throat_wake")',
             'if lowq in ("уложи горло", "останови горло", "выключи горло"):',
             '    from core import voice as _voice',
             '    return Reply(_voice.lay_throat(), "python", "throat_lay")']
    if '"проверь горло"' not in asrc:
        block += ['if lowq in ("проверь горло", "какой рот", "почему ирина",',
                  '            "почему ты говоришь как робот"):',
                  '    from core import voice as _voice',
                  '    if lowq == "какой рот":',
                  '        return Reply(_voice.mouth_report(), "python", "throat")',
                  '    return Reply(_voice.throat_report(), "python", "throat")']
    asrc = sub_i(asrc,
                 r'(?P<i>[ \t]*)if lowq in \("проверь голос", "проверка голоса", "как голос"\):',
                 block + ['if lowq in ("проверь голос", "проверка голоса", "как голос"):'],
                 "проверь голос")

# ---------- agent.py: похвала ----------
if '"какая ты умница"' not in asrc and '"ты лучшая"):' in asrc:
    asrc = asrc.replace(
        '"ты лучшая"):',
        '"ты лучшая", "какая ты умница", "какая умница", '
        '"ты просто умница", "умничка", "какая ты молодец"):', 1)

# ---------- agent.py: закон факта ----------
if "FACT_LAW" not in asrc:
    asrc = asrc.replace(
        "def load_doctrine() -> str:",
        '''FACT_LAW = (
    "ЗАКОН ФАКТА: слова «создано», «готово», «сделала», «починила», "
    "«внедрила» можно говорить ТОЛЬКО после инструмента действия в этом "
    "же ходу (code_patch → apply_patch, write_file, run_python). Озвучка — "
    "не работа: speak произносит слова, а не создаёт файлы. Работа не "
    "сделана — скажи «не сделано» или «инструмент уже есть», без отчёта "
    "о мнимом труде."
)


def load_doctrine() -> str:''', 1)
    old = '+ VOICE_TOOL_NOTE + "\\n\\n" + SPEED_LAW + "\\n\\n" + TONE_LAW'
    new = ('+ VOICE_TOOL_NOTE + "\\n\\n" + FACT_LAW + "\\n\\n" '
           '+ SPEED_LAW + "\\n\\n" + TONE_LAW')
    if old in asrc:
        asrc = asrc.replace(old, new, 1)
    else:
        old2 = '+ SPEED_LAW + "\\n\\n" + TONE_LAW'
        if old2 not in asrc:
            sys.exit("ЯКОРЬ НЕ НАЙДЕН: _static_core")
        asrc = asrc.replace(old2, '+ FACT_LAW + "\\n\\n" + SPEED_LAW + "\\n\\n" + TONE_LAW', 1)

if "_claim_without_work" not in asrc:
    asrc = asrc.replace(
        "def _house_state() -> str:",
        '''_CLAIM_DONE_RE = re.compile(
    r"\\b(создан[аоы]?|создал[аи]|готово|сделал[аи]|написал[аи]|"
    r"починил[аи]|внедрил[аи]|установил[аи]|добавил[аи]|исправил[аи]|"
    r"реализовал[аи]|запустил[аи])\\b", re.IGNORECASE)
_CLAIM_PAST_RE = re.compile(
    r"(уже есть|раньше|вчера|до этого|в прошлый|на прошлой|"
    r"не создавала|не делала|ничего не)", re.IGNORECASE)
_FACT_NOTE = (
    "\\n\\n[факт дома: в этом ходу не было инструмента действия — ничего "
    "не создавалось и не чинилось. Это произнесённые слова, а не работа. "
    "Проверить: «патчи», «что построили».]")


def _claim_without_work(text: str) -> bool:
    t = str(text or "")
    if not t.strip() or _CLAIM_PAST_RE.search(t):
        return False
    return bool(_CLAIM_DONE_RE.search(t))


def _house_state() -> str:''', 1)
    m = re.search(r'(?P<i>[ \t]*)return Reply\(_voice\.say\(said\), "brain", "speak"\)', asrc)
    if m:
        i = m.group("i")
        asrc = asrc[:m.start()] + "\n".join([
            i + 'out = _voice.say(said)',
            i + 'if _claim_without_work(said):',
            i + '    _lesson("слова-без-дела", "speak: %.120s" % said)',
            i + '    out += _FACT_NOTE',
            i + 'return Reply(out, "brain", "speak")',
        ]) + asrc[m.end():]
    else:
        print("ВНИМАНИЕ: speak-ветка не найдена — закон факта в промпт встал, "
              "страховка в _act пропущена (патч speak уже менял этот блок?)")

for p, src in ((V, vsrc), (A, asrc)):
    bak = p.with_name(p.name + ".bak_v3_" + stamp)
    shutil.copy2(p, bak)
    p.write_text(src, encoding="utf-8")
    try:
        py_compile.compile(str(p), doraise=True)
    except Exception as e:
        shutil.copy2(bak, p)
        sys.exit("КОМПИЛЯЦИЯ КРАСНАЯ (%s), откатил: %s" % (p.name, e))
    print("ГОТОВО:", p.name, "| бэкап:", bak.name)