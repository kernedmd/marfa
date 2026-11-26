# -*- coding: utf-8 -*-
r"""core/customtools.py — МАСТЕРСКАЯ ИНСТРУМЕНТОВ (круг 26, Ф161).

Живой лог дня-15 (26.11.2026) заставил Создателя ШЕСТЬ раз просить
«создай инструмент для озвучивания» — и шесть раз дом отвечал либо
шпаргалкой «почини что?», либо выдумкой «Создан инструмент» (закон
факта плакал). Инструменты были списком в коде (identity.TOOLS): что
встроено — то и есть навсегда, новых у Марфы не бывает.

Ф161 меняет закон: инструмент — ФАЙЛ в core\customtools\, и дом
подхватывает его сам. Путь тот же, что у самолечения (кодер-слуга,
песочница патчей, броня Ф155): Создатель говорит «создай инструмент
<имя>: <что делает>» → кодер пишет модуль → патч в песочнице →
«примени патч N» с бронёй → со следующего хода инструмент в руках.
Регистрация НЕ правит agent.py (орган не оперирует сам себе) —
диспетчер спрашивает мастерскую перед «неизвестный инструмент»,
промпт перечисляет живые инструменты из папки.

ФОРМАТ МОДУЛЯ (страж формы — сам орган, на каждом чтении):
    TOOL_NAME = "translate"          # латиница, совпадает с именем файла
    TOOL_ABOUT = "переводит текст"   # одна строка по-русски
    def run(args: dict) -> str: ...  # честный русский текст, не исключение

Больной модуль не роняет дом: список честно пропускает его с уроком
архитектору, вызов отвечает диагностикой. Висящий инструмент не вешает
ход: 30 с потолок, дальше — честное «не дождалась».

Честность (закон факта): «инструмент создан» можно говорить только
после применения патча — design_patch возвращает отчёт КОДЕРА,
а не победу.
"""
from __future__ import annotations

import importlib.util
import re
import threading
import time
from pathlib import Path
from typing import Optional

from core import config

# ---------------------------------------------------------------
# ПАПКА МАСТЕРСКОЙ
# ---------------------------------------------------------------

def tools_dir() -> Path:
    """core/customtools — живая папка инструментов. Лениво от HOME_DIR:
    песочница теста, патчившая дом, получает свою мастерскую."""
    return Path(config.HOME_DIR) / "core" / "customtools"

# потолок ожидания инструмента: ход Создателя не ждёт вечного модуля
CALL_TIMEOUT_SEC = 30.0
# кэш скана: промпт читает список каждым ходом — перечитывать папку
# (и импортировать модули) каждый ход незачем, состояние меняется
# только применением патча
_SCAN_TTL = 5.0
_scan_cache: dict = {"ts": 0.0, "tools": []}

# имя инструмента: латиница/цифры/подчёркивание, начинается с буквы
_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{0,19}$")

# имена, которые мастерская не займёт: встроенные органы и speak —
# чужие имена неприкосновенны (коллизия = тихая подмена инструмента)
_RESERVED = {
    "read_file", "write_file", "run_python", "browser_search",
    "check_brackets", "ui_action", "code_patch", "apply_patch",
    "speak", "memory_add",
}


def _lesson(kind: str, text: str) -> None:
    """Урок архитектору — через журнал уроков, тихо (орган не дыхание)."""
    try:
        from evolution.journal import log_lesson
        log_lesson(kind, text)
    except Exception:
        pass


def _load_module(path: Path):
    """Импорт модуля по пути (без exec: честный importlib)."""
    spec = importlib.util.spec_from_file_location(
        "customtool_%s" % path.stem, path)
    if spec is None or spec.loader is None:
        raise ImportError("spec не собрался")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _shape_ok(mod) -> tuple:
    """Страж формы: (имя, описание) или抛 ValueError с причиной."""
    name = getattr(mod, "TOOL_NAME", None)
    about = getattr(mod, "TOOL_ABOUT", None)
    run = getattr(mod, "run", None)
    if not isinstance(name, str) or not _NAME_RE.match(name):
        raise ValueError("TOOL_NAME обязан быть латиницей: %r" % (name,))
    if not isinstance(about, str) or not about.strip():
        raise ValueError("TOOL_ABOUT обязана быть непустой строкой")
    if not callable(run):
        raise ValueError("run(args) обязан быть функцией")
    return name, about.strip()


def list_tools() -> list:
    """Живые инструменты: [(имя, описание)]. Больные — честно мимо,
    с уроком архитектору (мастерская не притворяется аптекой)."""
    now = time.time()
    if now - _scan_cache["ts"] < _SCAN_TTL and _scan_cache["tools"]:
        return list(_scan_cache["tools"])
    out: list = []
    d = tools_dir()
    try:
        files = sorted(d.glob("*.py"))
    except OSError:
        files = []
    for f in files:
        if f.name.startswith("_"):
            continue
        try:
            name, about = _shape_ok(_load_module(f))
            if name != f.stem:
                raise ValueError("TOOL_NAME %r не совпадает с файлом %s"
                                 % (name, f.name))
            out.append((name, about))
        except Exception as e:
            _lesson("мастерская-модуль-болен",
                    "%s: %s: %s" % (f.name, type(e).__name__, e))
    _scan_cache["ts"] = now
    _scan_cache["tools"] = out
    return list(out)


def names() -> list:
    """Имена живых инструментов — для меню при ошибке."""
    return [n for n, _ in list_tools()]


def call(name: str, args: dict) -> Optional[str]:
    """Вызов инструмента мозгом. None — такого инструмента нет (диспетчер
    пойдёт в «неизвестный инструмент»); строка — честный результат,
    включая диагноз упавшего. Потолок 30 с: вечный модуль не вешает ход."""
    for n, _about in list_tools():
        if n != name:
            continue
        try:
            mod = _load_module(tools_dir() / ("%s.py" % name))
        except Exception as e:
            _lesson("мастерская-не-поднялся", "%s: %s" % (name, e))
            return ("инструмент %s не поднялся: %s — скажи «инструменты», "
                    "проверю мастерскую" % (name, e))
        holder: dict = {}
        def _worker():
            try:
                holder["out"] = mod.run(args if isinstance(args, dict) else {})
            except Exception as e:
                holder["err"] = "%s: %s" % (type(e).__name__, e)
        th = threading.Thread(target=_worker, daemon=True)
        th.start()
        th.join(CALL_TIMEOUT_SEC)
        if th.is_alive():
            _lesson("мастерская-завис", "%s: дольше %d с"
                    % (name, CALL_TIMEOUT_SEC))
            return ("инструмент %s думает дольше %d с — я не дождалась. "
                    "Расскажи архитектору: «почини core\\customtools\\%s.py: "
                    "убери вечный цикл»" % (name, CALL_TIMEOUT_SEC, name))
        if "err" in holder:
            _lesson("мастерская-упал", "%s: %s" % (name, holder["err"]))
            return ("инструмент %s споткнулся: %s — скажи «почини "
                    "core\\customtools\\%s.py: исправить ошибку»"
                    % (name, holder["err"], name))
        out = holder.get("out")
        if not isinstance(out, str) or not out.strip():
            return ("инструмент %s вернул пустоту — скажи «почини "
                    "core\\customtools\\%s.py: всегда возвращать текст»"
                    % (name, name))
        return out
    return None


# ---------------------------------------------------------------
# ВИТРИНА
# ---------------------------------------------------------------

def report() -> str:
    """«инструменты» — вся рука дома одним честным списком."""
    from core import identity
    lines = ["РУКА ДОМА:"]
    lines.append("- встроенные (родились со мной): "
                 + ", ".join(n for n, _ in identity.TOOLS) + ", speak")
    live = list_tools()
    if live:
        lines.append("- мастерская (созданы домом, Ф161):")
        lines.extend("  · %s — %s" % (n, a) for n, a in live)
    else:
        lines.append("- мастерская (Ф161): пока пусто — ни один инструмент "
                     "ещё не создан")
    lines.append("новый инструмент рождается командой «создай инструмент "
                 "<имя>: <что делает>» — кодер напишет модуль, применяешь "
                 "патч с бронёй, инструмент появляется у меня в руках")
    return "\n".join(lines)


def prompt_line() -> str:
    """Строка для промпта мозга: живые инструменты мастерской. Пустая
    папка — пустая строка (промпт не носит мёртвых строк)."""
    live = list_tools()
    if not live:
        return ""
    return ("- Инструменты мастерской (созданы домом, зови как обычные): "
            + "; ".join("%s (%s)" % (n, a) for n, a in live) + ". "
            "Новых инструментов из воздуха не выдумывай: Создатель просит "
            "новый — подскажи команду «создай инструмент <имя>: <что "
            "делает>», и не говори «создано» до внедрения патча.\n")


# ---------------------------------------------------------------
# ПРОЕКТИРОВАНИЕ: «создай инструмент» → патч кодера
# ---------------------------------------------------------------

_CODER_TEMPLATE = '''```python
# -*- coding: utf-8 -*-
"""Инструмент дома «{name}»: {about}. Создан в мастерской (Ф161)."""

TOOL_NAME = "{name}"
TOOL_ABOUT = "{about}"


def run(args: dict) -> str:
    """{about}. Мозг дома зовёт с args; ответ — русский текст."""
    text = str(args.get("text") or args.get("query") or args.get("value")
               or "").strip()
    if not text:
        return "что подать на вход? дай аргумент text"
    # TODO: логика инструмента — честная, без выдумок
    return "инструмент {name} ещё не дописан: расскажи архитектору"
```
'''

_CODER_RULES = """Ты — кодер дома Марфа. Пишешь ОДИН Python-модуль — новый
инструмент для мозгового агента. Формат ЖЁСТКИЙ:

1. Первые три строки после докстринга — ровно:
   TOOL_NAME = "<имя латиницей>"   (совпадает с именем файла)
   TOOL_ABOUT = "<что делает, по-русски, одна строка>"
   затем функция: def run(args: dict) -> str:
2. run принимает словарь args (мозг кладёт данные в text/query/value или
   свои ключи) и возвращает СТРОКУ по-русски. Пустой ввод — честная
   подсказка, что дать. Ошибка — честный текст, не тишина.
3. Разрешены только стандартная библиотека и requests. ЗАПРЕЩЕНЫ:
   subprocess, os.system, socket, потоки, файлы вне data\\ (путь — только
   через Path из аргументов, не выдумывай своих).
4. Никакого print, никакого ввода-вывода консоли — только return.
5. Файл цельком, не больше 80 строк, чистый синтаксис.
6. Никаких выдуманных возможностей: инструмент делает ровно то, что в
   требовании, и честно отказывается от остального.
"""


def normalize_name(raw: str) -> tuple:
    """Имя Создателя → имя файла. Латиница проходит, кириллица
    транслитерируется (дом умеет), мусор чистится.
    Успех: (имя, было_транслитом). Провал: (причина, None)."""
    raw = (raw or "").strip().strip(",;:.!?")
    low = raw.lower().replace(" ", "_").replace("-", "_")
    was_translit = False
    if re.search(r"[а-яё]", low):
        try:
            from core import translit
            low = translit.translit(low).lower().replace(" ", "_")
            was_translit = True
        except Exception:
            pass
    low = re.sub(r"[^a-z0-9_]", "", low).strip("_")
    if not _NAME_RE.match(low):
        return ("имя не получилось из «%s»: дай короткое имя латиницей или "
                "одним русским словом, например: translate, counter, "
                "reminder" % raw, None)
    if low in _RESERVED:
        return ("имя %s занято встроенным органом — придумай другое" % low,
                None)
    return low, was_translit


def design_patch(raw_name: str, about: str) -> str:
    """«создай инструмент <имя>: <что делает>» — ПС-1 мастерской:
    кодер пишет модуль в песочницу патчей. НЕ применяет: «инструмент
    создан» — только после «примени патч N» с бронёй (закон факта)."""
    from core import repair
    about = (about or "").strip().strip(",;:.! ")
    name, ok = normalize_name(raw_name)
    if ok is None:
        return name                      # честная причина, не файл
    if not about:
        return ("что он должен делать? формат: «создай инструмент <имя>: "
                "<что делает>», например: «создай инструмент translate: "
                "переводит текст на английский»")
    note = (" (имя получилось транслитом из «%s»)" % raw_name.strip()
            if ok else "")
    # уже живой или уже в песочнице — честно сказать, не плодить двойников
    if name in names():
        return ("инструмент %s уже живёт в мастерской — «инструменты» "
                "покажет. Хочешь другой — дай другое имя" % name)
    d = tools_dir()
    try:
        if (d / ("%s.py" % name)).is_file():
            return ("файл core\\customtools\\%s.py уже лежит в доме, но не "
                    "поднялся — скажи «почини core\\customtools\\%s.py: "
                    "починить инструмент», кодер разберётся"
                    % (name, name))
    except OSError:
        pass
    requirement = (
        "создай инструмент дома «%s»: %s. Формат модуля жёсткий:\n%s\n"
        "Скелет (обязателен, заполни логику вместо TODO):\n%s"
        % (name, about, _CODER_RULES,
           _CODER_TEMPLATE.replace("{name}", name).replace("{about}", about)))
    out = repair.make_patch("core/customtools/%s.py" % name, requirement)
    # честная надстройка: отчёт кодера + что дальше (закон факта:
    # «создан» не говорим — патч ещё в песочнице). Номер патча — из
    # отчёта кодера, не выдумываем
    import re as _re
    m_num = _re.search(r"патч №(\d+) ГОТОВ", out)
    how = ("примени патч %s" % m_num.group(1)) if m_num else \
        "примени патч N (номер — в отчёте кодера выше)"
    if "ГОТОВ" not in out:
        return out
    return (out + "\nинструмент СПРОЕКТИРОВАН, но ещё не создан%s: скажи "
            "«%s» — броня Ф155 проверит тестами, и со "
            "следующего хода %s появится у меня в руках; проверить — "
            "«инструменты»" % (note, how, name))
