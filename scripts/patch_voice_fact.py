# -*- coding: utf-8 -*-
"""ГОЛОС v3: рот называется вслух; ЗАКОН ФАКТА; похвала-рефлекс."""
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


def sub_indent(src, pattern, lines, name):
    m = re.search(pattern, src)
    if not m:
        sys.exit("ЯКОРЬ НЕ НАЙДЕН: " + name)
    ind = m.group("i")
    body = "\n".join(ind + ln if ln else "" for ln in lines)
    return src[:m.start()] + body + src[m.end():]


# ---------- voice.py ----------
if "ПАТЧ_ГОЛОС_V3" in vsrc:
    print("voice.py: патч уже стоит")
else:
    vsrc = sub_indent(
        vsrc,
        r'(?P<i>[ \t]*)return "произношу вслух: «%s»" % preview',
        ['if _throat_alive():',
         '    return "произношу вслух (горло silero): «%s»" % preview',
         'return ("произношу вслух ЗАПАСНЫМ РОТОМ Windows (Ирина, робот) — "',
         '        "горло silero спит: «%s»\\n"',
         '        "Скажи «проверь горло» — покажу точную причину."',
         '        % preview)'],
        "say preview")

    vsrc += '''

# ---------------- ПАТЧ_ГОЛОС_V3 ----------------
_LAST_MOUTH = {"mouth": "", "ts": 0.0}

_speak_v2 = speak


def speak(text: str, limit: int = SAY_LIMIT) -> str:
    """Обёртка: запоминает, КАКОЙ рот говорил (факт для «какой рот»)."""
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
            "горло silero спит или не смогло — скажи «проверь горло»" % when)


def throat_report() -> str:
    """«проверь горло»: почему Ирина, а не Silero — по ступеням."""
    root = Path(__file__).resolve().parents[1]
    port = getattr(config, "PORT_THROAT", 8084)
    lines = ["ПРОВЕРКА ГОРЛА (silero), порт %s:" % port]
    model = root / "models" / "voice" / "v5_6_ru.pt"
    lines.append("  · модель %s: %s" % (
        model, "есть (%d МБ)" % (model.stat().st_size // 1048576)
        if model.exists() else "НЕТ"))
    try:
        import torch
        lines.append("  · torch: %s" % torch.__version__)
    except Exception as e:
        lines.append("  · torch: НЕТ — %s (Silero без него не загрузится)" % e)
    try:
        from core import throat as _t
    except Exception as e:
        lines.append("  · core/throat.py НЕ ИМПОРТИРУЕТСЯ: %s" % e)
        lines.append("  · лечение: нужен слуга-горло (docs\\\\ТЗ_Голос_v2.md, §7)")
        return "\\n".join(lines)
    try:
        alive = _t.alive()
    except Exception as e:
        alive = False
        lines.append("  · alive() упал: %s: %s" % (type(e).__name__, e))
    lines.append("  · слуга: %s" % ("ЖИВ" if alive else "СПИТ"))
    if alive:
        try:
            lines.append("  · health: %s" % (_t.health(),))
        except Exception as e:
            lines.append("  · health упал: %s" % e)
    else:
        bats = sorted((root / "scripts").glob("9*.bat"))
        lines.append("  · кнопки: %s" % (", ".join(b.name for b in bats)
                                         or "нет 9*.bat"))
        lines.append("  · лечение: поднять слугу на %s с моделью v5_6_ru.pt"
                     % port)
    return "\\n".join(lines)
'''

# ---------- agent.py ----------
if "ЗАКОН ФАКТА" in asrc:
    print("agent.py: патч уже стоит")
else:
    # 1. Закон факта — в статичный префикс.
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
        asrc = asrc.replace(
            old2, '+ FACT_LAW + "\\n\\n" + SPEED_LAW + "\\n\\n" + TONE_LAW', 1)

    # 2. Детектор заявления о работе + честная приписка.
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

    m = re.search(r'(?P<i>[ \t]*)return Reply\(_voice\.say\(said\), '
                  r'"brain", "speak"\)', asrc)
    if not m:
        sys.exit("ЯКОРЬ НЕ НАЙДЕН: speak branch (патч speak не стоит?)")
    i = m.group("i")
    asrc = asrc[:m.start()] + "\n".join([
        i + 'out = _voice.say(said)',
        i + 'if _claim_without_work(said):',
        i + '    _lesson("слова-без-дела", "speak: %.120s" % said)',
        i + '    out += _FACT_NOTE',
        i + 'return Reply(out, "brain", "speak")',
    ]) + asrc[m.end():]

    # 3. Похвала: «какая ты умница» — рефлекс, а не 44 с мозга.
    if '"ты лучшая"):' not in asrc:
        sys.exit("ЯКОРЬ НЕ НАЙДЕН: список похвалы")
    asrc = asrc.replace(
        '"ты лучшая"):',
        '"ты лучшая", "какая ты умница", "какая умница", '
        '"ты просто умница", "умничка", "какая ты молодец"):', 1)

    # 4. Рефлексы горла.
    asrc = sub_indent(
        asrc,
        r'(?P<i>[ \t]*)if lowq in \("проверь голос", "проверка голоса", '
        r'"как голос"\):',
        ['if lowq in ("проверь горло", "горло", "какой рот",',
         '            "почему ирина", "почему ты говоришь как робот"):',
         '    from core import voice as _voice',
         '    if lowq == "какой рот":',
         '        return Reply(_voice.mouth_report(), "python", "throat")',
         '    return Reply(_voice.throat_report(), "python", "throat")',
         'if lowq in ("проверь голос", "проверка голоса", "как голос"):'],
        "проверь голос")

for p, src in ((V, vsrc), (A, asrc)):
    bak = p.with_name(p.name + ".bak_fact_" + stamp)
    shutil.copy2(p, bak)
    p.write_text(src, encoding="utf-8")
    try:
        py_compile.compile(str(p), doraise=True)
    except Exception as e:
        shutil.copy2(bak, p)
        sys.exit("КОМПИЛЯЦИЯ КРАСНАЯ (%s), откатил: %s" % (p.name, e))
    print("ГОТОВО:", p.name, "| бэкап:", bak.name)