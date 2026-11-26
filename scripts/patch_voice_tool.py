# -*- coding: utf-8 -*-
"""Патч: speak для мозга + честный code_patch + правда о голосе в ядре.

Ставится по якорям, не по номерам строк. Если якорь не найден —
ничего не пишет, выходит с ошибкой. Перед записью — бэкап.
После записи — py_compile; при красном откатывает бэкап.
"""
from pathlib import Path
import py_compile
import re
import shutil
import sys
import time

P = Path("core/agent.py")
if not P.exists():
    sys.exit("нет core/agent.py — запускай из корня дома")

src = P.read_text(encoding="utf-8")
orig = src


def need(anchor: str) -> None:
    if anchor not in src:
        sys.exit("ЯКОРЬ НЕ НАЙДЕН: %r" % anchor[:100])


# 1. Ядро больше не врёт, что голоса нет.
need("Голоса пока нет — отвечаю текстом.")
src = src.replace(
    "Голоса пока нет — отвечаю текстом.",
    "Голос есть: рефлекс «скажи вслух <текст>»; мозг озвучивает "
    "инструментом speak с полем text.",
    1,
)

# 2. Подсказка мозгу: голос — орган, не задача для кодера.
need("def load_doctrine() -> str:")
NOTE = '''VOICE_TOOL_NOTE = (
    "ГОЛОС — ИНСТРУМЕНТ МОЗГА: у дома есть рефлекс «скажи вслух <текст>» "
    "для текста Создателя, а у тебя есть инструмент speak. Хочешь озвучить "
    "свои слова — позови speak и положи текст в args.text. Не зови code_patch "
    "ради озвучки: голос уже орган дома, создавать его не нужно."
)


'''
src = src.replace("def load_doctrine() -> str:", NOTE + "def load_doctrine() -> str:", 1)

# 3. Подсказка попадает в статичный промпт.
need('+ SPEED_LAW + "\\n\\n" + TONE_LAW')
src = src.replace(
    '+ SPEED_LAW + "\\n\\n" + TONE_LAW',
    '+ VOICE_TOOL_NOTE + "\\n\\n" + SPEED_LAW + "\\n\\n" + TONE_LAW',
    1,
)

# 4. Алиасы полей: мозг зовёт file/task вместо path/requirement.
need('return "" if v is None else str(v)')
src = src.replace(
    'return "" if v is None else str(v)',
    '''return "" if v is None else str(v)

        def _pick(*keys: str) -> str:
            for k in keys:
                v = args.get(k)
                if isinstance(v, str) and v.strip():
                    return v.strip()
            return ""''',
    1,
)

# 5. Дверь мозга к голосу.
need('        try:\n            if tool == "write_file":')
src = src.replace(
    '        try:\n            if tool == "write_file":',
    '''        try:
            if tool in ("speak", "say", "voice", "speak_aloud", "озвучить"):
                from core import voice as _voice
                said = _pick("text", "content", "message", "phrase", "answer")
                if not said:
                    return Reply("что озвучить? дай текст в args.text",
                                 "brain", "speak")
                return Reply(_voice.say(said), "brain", "speak")
            if tool == "write_file":''',
    1,
)

# 6. Кодер не принимает пустоту и не показывает шпаргалку как ответ.
pat = re.compile(
    r'(?P<indent>[ \t]*)return Reply\(repair\.make_patch\('
    r'_s\("path"\), _s\("requirement"\)\),\s*"brain", "code_patch"\)'
)
m = pat.search(src)
if not m:
    sys.exit("ЯКОРЬ НЕ НАЙДЕН: return Reply(repair.make_patch(_s(path)...")
ind = m.group("indent")
new = ind + 'path = _pick("path", "file", "filename", "target", "module")\n'
new += ind + 'req = _pick("requirement", "req", "task", "description",\n'
new += ind + '            "what", "todo", "instruction")\n'
new += ind + 'if not path or not req:\n'
new += ind + '    _lesson("кодер-без-полей",\n'
new += ind + '            "мозг дал ключи: %s" % ", ".join(args))\n'
new += ind + '    return Reply(\n'
new += ind + '        "кодеру нужны ДВА поля: path и requirement. "\n'
new += ind + '        "Ты дал: %s. Позови с обоими: path — какой файл, "\n'
new += ind + '        "requirement — что сделать."\n'
new += ind + '        % (", ".join(args) or "ничего"),\n'
new += ind + '        "brain", "code_patch")\n'
new += ind + 'return Reply(repair.make_patch(path, req), "brain", "code_patch")'
src = src[:m.start()] + new + src[m.end():]

# 7. Неизвестный инструмент: speak теперь в списке своих.
need("identity.tool_names() +")
src = src.replace("identity.tool_names() +", 'identity.tool_names() + ", speak" +', 1)

if src == orig:
    sys.exit("ничего не изменилось — патч уже стоит?")

bak = P.with_name(P.name + ".bak_voice_%s" % time.strftime("%Y%m%d_%H%M%S"))
shutil.copy2(P, bak)
P.write_text(src, encoding="utf-8")
try:
    py_compile.compile(str(P), doraise=True)
except Exception as e:
    shutil.copy2(bak, P)
    sys.exit("КОМПИЛЯЦИЯ КРАСНАЯ, откатил: %s" % e)

print("ГОТОВО: speak + честный code_patch + правда о голосе")
print("бэкап:", bak)