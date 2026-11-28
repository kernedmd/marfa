# -*- coding: utf-8 -*-
r"""core/repair.py — САМОЛЕЧЕНИЕ ДОМА v1+v2 + Ф75 СВОБОДА ВНЕДРЯТЬ СЕБЯ.

Создатель: «надо идти дальше по строению дома, и давать Марфе самой
себя лечить и доделывать, она достаточно умная модель... среди умных
рук у неё есть очень прокачанная модель 7b, которая хорошо знает
питон». qwen2.5-coder-7b-instruct спала в чулане (АРСЕНАЛ: «вернёмся,
когда Марфа начнёт чинить свои кнопки сама») — день наступил.

Пятый слуга-разум — КОДЕР (порт 8085, СЛУГА ПО ВЫЗОВУ, как руки).
Доктрина ролей: МОЗГ (или Создатель) ставит требование, КОДЕР печатает
код, СТРАЖ проверяет, применяет — Создатель ИЛИ сама Марфа (Ф75).
Конвейер:

    «почини <файл>: <что сделать>»
      → файл читается (руки + страж: только внутри дома)
      → кодер поднимается (VRAM-танец: кодер ~4.7 + глаза 3.0 > 6 ГБ,
        глаза присели — та же механика, что у рук)
      → кодер пишет файл ЦЕЛИКОМ в одном блоке ```python
      → страж патча: только .py, лимит строк, AST-синтаксис,
        канарейки, «вернул без изменений» = брак
      → Ф154: рядом рождается patch.diff + счётчики строк в meta —
        «что меняет патч N» говорит дифф и AST, не пересказ LLM
      → патч ложится в data\patches\000N\ — ПЕСОЧНИЦА, не core\
      → кодер ложится, глаза возвращаются (доктором)
      → Создатель: «примени патч N» / Марфа: «внедри патч N» —
        оба пути в ОДНОЙ броне (Ф155): бэкап → запись → тесты
        модуля И привязанные тесты → красные? автоОткат

САМОЛЕЧЕНИЕ v2 (круг 25, Ф154–Ф155):
  - Ф154 «ДИФФ ПАТЧА» — каждый патч несёт unified diff и сводку
    фактов (+N −M строк, имена функций/классов новые/задеты/ушли);
    команды «что меняет патч N» и «покажи патч N»;
  - Ф155 «БРОНЯ ПРИМЕНЕНИЯ» — «примени патч N» получает броню
    «внедри патч N»: дым-тест расширен до привязанных тестов
    (чей тест импортирует модуль — тот и задаёт поведение), красный
    прогон = автоОткат для КОГО УГОДНО, кто трогает дом.

Неприкосновенность (главный закон модуля): make_patch НИКОГДА не пишет
вне data\patches\ — код дома меняет только Создатель своей командой
или Марфа с резолюцией (self_apply), всегда с бэкапом, дым-тестом
и откатом. Мозг получает инструменты code_patch (написать) и
apply_patch (внедрить) с тем же конвейером.

Швы для тестов (tests/test_repair.py подменяет): _ask_coder /
ensure_server / release / _find_model / _smoke_test / _run_pytest —
реальный сервер и настоящий pytest не нужны.
"""
from __future__ import annotations

import datetime as dt
import difflib
import json
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

import requests

from core import config, hands, loghygiene, progress
from safety import guard

CODER_PROMPT = (
    "Ты — кодер дома Марфа. Тебе дают файл дома и требование. Верни "
    "ИСПРАВЛЕННЫЙ ФАЙЛ ЦЕЛИКОМ в одном блоке ```python ... ```, без "
    "пояснений до и после.\n"
    "Правила: меняй только то, что требует задание; сохраняй стиль дома "
    "(комментарии по-русски); не удаляй существующие функции; не "
    "выдумывай импорты, которых нет; файл обязан быть рабочим Python."
)


# ---------------------------------------------------------------
# Слуга по вызову: подъём и укладывание (VRAM-танец с глазами)
# ---------------------------------------------------------------

def server_alive() -> bool:
    """Жив ли сервер кодера (8085)."""
    try:
        return requests.get(config.CODER_URL + "/health",
                            timeout=3).status_code == 200
    except Exception:
        return False


def _find_model() -> Optional[Path]:
    """Найти тело кодера в чулане. АРСЕНАЛ зовёт его qwen2.5-coder-7b
    -instruct; точное имя файла/квант могло измениться — ищем по шаблону.
    Нет — None, честно (чинить нечем)."""
    cands = sorted(config.MODELS_DIR.glob("*coder*7b*.gguf"))
    if not cands:
        cands = sorted(config.MODELS_DIR.glob("*coder*.gguf"))
    return cands[0] if cands else None


def _spawn_server(model: Path) -> None:
    """Поднять сервер кодера в отдельной консоли — как старт дома.
    Кодер — текстовая модель: без --mmproj, в отличие от глаз и рук."""
    cmd = ('llama.cpp\\llama-server.exe -m "%s" -ngl 99 -c %d -t 2 '
           '--temp 0.1 --host 127.0.0.1 --port %d'
           % (model, config.CODER_CTX_TOKENS, config.PORT_CODER))
    subprocess.Popen(cmd, shell=True, cwd=str(config.HOME_DIR),
                     creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0))


def ensure_server(wait_secs: Optional[float] = None) -> tuple:
    """Поднять кодера: (жив ли, честная сводка действий).

    VRAM-танец остался только у кодера (Руки v2 «единое зрение»
    больше не танцуют — работают на координатах глаз): кодер ~4.7 ГБ
    + глаза ~3.0 ГБ > 6 ГБ — глаза присаживает на время патча,
    после задачи release() возвращает их доктором.
    """
    from core.vram import stop_llama
    wait_secs = config.CODER_START_WAIT_SECS if wait_secs is None else wait_secs
    if server_alive():
        return True, "кодер уже на посту"
    model = _find_model()
    if model is None:
        return False, ("модели кодера нет в чулане: жду qwen2.5-coder-7b"
                       "*.gguf в %s — проверь, доехал ли файл (АРСЕНАЛ, "
                       "раздел «в строю»)" % config.MODELS_DIR)
    notes = []
    if stop_llama(config.PORT_EYES):
        notes.append("глаза присели (VRAM 6 ГБ: двоим не хватит)")
    try:
        _spawn_server(model)
        notes.append("кодер поднимается (%s с NVMe — десятки секунд)"
                     % model.name)
    except Exception as e:
        return False, "; ".join(notes) + "; не поднялся: %s" % e
    deadline = time.time() + wait_secs
    while time.time() < deadline:
        if server_alive():
            notes.append("кодер на посту")
            return True, "; ".join(notes)
        time.sleep(3.0)
    return False, "; ".join(notes) + " — не ожил за %.0f с, смотри консоль кодера" % wait_secs


def release() -> str:
    """Кодер ложится, глаза возвращаются (церемония заёма — core/vram.py;
    после Рук v2 кодер — единственный танцор VRAM)."""
    from core.vram import stop_llama
    stopped = stop_llama(config.PORT_CODER)
    note = "кодер лёг; " if stopped else "кодера на посту не было; "
    try:
        from core import doctor
        actions = doctor.heal(["eyes"])
        note += "; ".join(a.replace("глаза 8083: ", "") for a in actions)
    except Exception as e:
        note += "глаза не поднять: %s" % e
    return note


# ---------------------------------------------------------------
# Швы HTTP и промпт (тесты подменяют)
# ---------------------------------------------------------------

def _ask_coder(prompt: str, max_tokens: int = None) -> str:
    """Один вопрос кодеру: требование + файл → новый файл."""
    body = {
        "model": "coder",
        "temperature": 0.2,
        "top_p": 0.8,
        "max_tokens": config.CODER_MAX_TOKENS if max_tokens is None else max_tokens,
        "messages": [{"role": "user", "content": prompt}],
    }
    r = requests.post(config.CODER_URL + "/v1/chat/completions",
                      json=body, timeout=config.CODER_TIMEOUT_SEC)
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


# ---------------------------------------------------------------
# СТРАЖ ПАТЧА: синтаксис — истина, не мнение модели
# ---------------------------------------------------------------

def _extract_code(answer: str) -> str:
    """Код из ответа кодера: первый блок ```python ... ``` (или ``` ... ```).
    Нет блока — брак: кодер обязан отвечать кодом, а не болтовнёй."""
    m = re.search(r"```(?:python)?\s*\n(.*?)```", answer or "", re.S)
    if not m:
        raise ValueError("кодер ответил без блока кода: %s"
                         % (answer or "")[:160])
    return m.group(1).strip() + "\n"


def _check_patch(path: Path, code: str) -> None:
    """Вердикт стража на патч. Поднимает ValueError с честной причиной:
    только .py, лимит строк (v1), AST-синтаксис, канарейки."""
    if path.suffix != ".py":
        raise ValueError("чиню только .py файлы (v1): %s" % path.name)
    n_lines = code.count("\n") + 1
    if n_lines > config.CODER_MAX_FILE_LINES:
        raise ValueError("патч %d строк — больше лимита %d (v1: файлы "
                         "меньше; большие — архитектору)"
                         % (n_lines, config.CODER_MAX_FILE_LINES))
    try:
        import ast
        ast.parse(code)
    except SyntaxError as e:
        raise ValueError("кодер написал не-Python (строка %s: %s) — "
                         "патч забракован" % (e.lineno or "?", e.msg))
    v = guard.check_secrets(code)
    if not v.allowed():
        raise ValueError("СТРАЖ: %s" % v.reason)


# Ф167 «КОД-ПАТЧ ГОВОРИТ ЧЕЛОВЕЧЕСКИ» (круг 27, живой лог дня-16):
# «А ты сможешь себя починить?» — мозг повёл кодера патчить МОДЕЛЬ
# горла v5_6_ru.pt (140 МБ) и уронил ход об 2 МБ-лимит чтения:
# «инструмент code_patch споткнулся: файл больше 2097152 байт».
# Категорийная ошибка: спящий слуга — НЕ СЛОМАННЫЙ ФАЙЛ, его
# ПОДНИМАЮТ («разбуди горло», кнопка 95), а не патчат. Кодер —
# врач КОДА, не моделей: страж отказывает ДО чтения, словами,
# которые понятны Создателю без архитектора.
NOT_CODE_EXT = {
    ".pt": "модель", ".pth": "модель", ".gguf": "модель",
    ".onnx": "модель", ".safetensors": "модель", ".bin": "модель",
    ".wav": "звук", ".mp3": "звук", ".ogg": "звук",
    ".exe": "программа", ".dll": "библиотека",
    ".zip": "архив", ".7z": "архив", ".rar": "архив",
    ".jpg": "картинка", ".jpeg": "картинка", ".png": "картинка",
    ".pdf": "документ",
}


def not_code_reply(path: Path) -> "str | None":
    """Честный отказ, если цель патча — не код. None — путь открыт."""
    kind = NOT_CODE_EXT.get(path.suffix.lower())
    if not kind:
        return None
    size = ""
    try:
        size = " (%d МБ)" % (path.stat().st_size // 1048576)
    except OSError:
        pass
    hint = ""
    if path.suffix.lower() in (".pt", ".pth", ".gguf", ".onnx"):
        hint = (" Если речь про горло: спящий слуга — не сломанный файл, "
                "его ПОДНИМАЮТ, а не патчат — скажи «разбуди горло» "
                "(или кнопка scripts\\95_Горло.bat), потом «скажи вслух "
                "привет» — проверим живой голос")
    return ("%s — это %s%s, не код. Кодер — врач кода (.py-файлы до %d "
            "строк), модели и бинарники он не лечит.%s"
            % (path.name, kind, size, config.CODER_MAX_FILE_LINES, hint))


# ---------------------------------------------------------------
# ПЕСОЧНИЦА ПАТЧЕЙ (data\patches\000N\)
# ---------------------------------------------------------------

def _read_meta(d: Path) -> dict:
    try:
        raw = (d / "meta.json").read_text(encoding="utf-8")
        rec = json.loads(raw)
        return rec if isinstance(rec, dict) else {}
    except Exception:
        return {}


def _next_patch_dir() -> Path:
    config.PATCHES_DIR.mkdir(parents=True, exist_ok=True)
    nums = [0]
    for d in config.PATCHES_DIR.iterdir():
        if d.is_dir() and d.name[:4].isdigit():
            nums.append(int(d.name[:4]))
    return config.PATCHES_DIR / ("%04d" % (max(nums) + 1))


def _log(rec: dict) -> None:
    """Лог ремонта — правило 6.6: логи истина, даже когда всё упало."""
    try:
        p = Path(config.REPAIR_LOG_FILE)
        rec = dict(rec)
        rec.setdefault("ts", dt.datetime.now().isoformat(timespec="seconds"))
        # Ф96 (круг 17): копилка ремонта — через дверь ротации, как все
        loghygiene.append_line(p, json.dumps(rec, ensure_ascii=False) + "\n")
    except OSError:
        pass


def _lesson(kind: str, text: str) -> None:
    try:
        from evolution.journal import log_lesson
        log_lesson(kind, text)
    except Exception:
        pass


# ---------------------------------------------------------------
# КОНВЕЙЕР: ПС-1 написать, ПС-2 применить, откат, список
# ---------------------------------------------------------------

def make_patch(path_str: str, requirement: str) -> str:
    """ПС-1: кодер пишет патч — В ПЕСОЧНИЦУ data\\patches, не в core\\.

    Создатель или мозг (инструмент code_patch) дают файл и требование.
    Возвращает честный отчёт: где патч лежит и как его применить.
    """
    requirement = (requirement or "").strip().strip(",;:.! ")
    path_str = (path_str or "").strip()
    if not path_str or not requirement:
        return ("почини что? Формат: «почини <файл>: <что сделать>», "
                "например: «почини scripts\\hello.py: добавь функцию "
                "приветствия». Список готовых — «патчи»")
    p = guard.resolve_path(path_str)
    guard.enforce(guard.check_path(p), {"tool": "code_patch"})
    # Ф167: цель — не код? Отказ ДО кодера и ДО чтения: честный
    # диагноз словами, урок архитектору — патч не поднимается вовсе
    not_code = not_code_reply(p)
    if not_code is not None:
        _lesson("кодер-взялся-за-модель",
                "мозг вёл кодера в %s (%s)" % (p.name, p.suffix or "без суффикса"))
        _log({"path": str(p), "requirement": requirement, "ok": False,
              "note": "не-код: %s" % (p.suffix or "без суффикса")})
        return not_code
    try:
        if p.is_file():
            src = hands.read_file(p)
            if src.count("\n") + 1 > config.CODER_MAX_FILE_LINES:
                return ("файл %s больше %d строк — v1 чинит файлы до %d "
                        "строк, большие оставь архитектору"
                        % (p.name, config.CODER_MAX_FILE_LINES,
                           config.CODER_MAX_FILE_LINES))
        else:
            src = ""      # новый файл — самый лёгкий случай для кодера
    except PermissionError as e:
        return "СТРАЖ не пустил к файлу: %s" % e
    except ValueError as e:
        # Ф167: 2 МБ-лимит чтения раньше улетал в панель загадкой
        # «инструмент споткнулся» — теперь диагноз человеческим языком
        _lesson("кодер-файл-не-по-зубам", "%s: %s" % (p.name, e))
        _log({"path": str(p), "requirement": requirement, "ok": False,
              "note": "не читается: %s" % e})
        return ("файл %s не по зубам кодеру: %s. Кодер v1 читает только "
                "небольшие .py-файлы (до %d строк, до 2 МБ). Если это "
                "модель или слуга — лечение не патч: «разбуди горло» "
                "поднимает слугу, а модели не чинят — их ставят. "
                "Большое и важное — скажи архитектору"
                % (p.name, e, config.CODER_MAX_FILE_LINES))
    # эфир: VRAM-танец — САМОЕ долгое действие дома (десятки секунд,
    # дважды: глаза приседают, кодер поднимается) — чат обязан это видеть
    progress.stage("поднимаю кодера: VRAM-танец — глаза присядут, это десятки секунд…")
    ok, note = ensure_server()
    if not ok:
        _log({"path": str(p), "requirement": requirement, "ok": False,
              "note": note})
        return "КОДЕР не поднялся: %s" % note
    lines = ["КОДЕР — требование: %s" % requirement,
             "файл: %s%s" % (p, " (новый)" if not src else ""), note]
    try:
        prompt = CODER_PROMPT + "\n\nТРЕБОВАНИЕ: " + requirement + "\n\n"
        if src:
            prompt += "ФАЙЛ (целиком):\n```python\n" + src + "```\n"
        else:
            prompt += "ФАЙЛ НОВЫЙ — создай его с нуля по требованию.\n"
        progress.stage("кодер печатает патч: 7B пишет файл целиком…")
        answer = _ask_coder(prompt)
        code = _extract_code(answer)
        _check_patch(p, code)
        if src and code.strip() == src.strip():
            raise ValueError("кодер вернул файл БЕЗ ИЗМЕНЕНИЙ — требование "
                             "не выполнено (скажи точнее, что именно менять)")
        d = _next_patch_dir()
        d.mkdir(parents=True, exist_ok=True)
        (d / p.name).write_text(code, encoding="utf-8")
        # Ф154 «ДИФФ ПАТЧА»: дифф рождается ВМЕСТЕ с патчем — «что
        # меняет патч N» отвечает фактами диффа и AST, а не пересказом
        # требования (гейт §5: истину говорит код, не LLM)
        diff_text = _build_diff(src, code, p.name)
        _patch_diff_path(d).write_text(diff_text, encoding="utf-8")
        add_n, rem_n = _diff_stats(diff_text)
        meta = {"target": str(p), "file_name": p.name,
                "requirement": requirement, "new_file": not bool(src),
                "applied": False, "added": add_n, "removed": rem_n,
                "ts": dt.datetime.now().isoformat(timespec="seconds")}
        (d / "meta.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
        _log({"path": str(p), "requirement": requirement, "ok": True,
              "patch": str(d)})
        _lesson("кодер-патч", "%s: %s" % (p.name, requirement))
        own = ("; мне можно самой — «внедри патч %s»: бэкап, дым-тест, "
               "автоОткат при красном (Ф75)" % d.name
               if self_write_resolution() is not None else "")
        return "\n".join(lines + [
            "патч №%s ГОТОВ: %s" % (d.name, d / p.name),
            "посмотреть можно в блокноте; применить — скажи «примени "
            "патч %s» (старый файл уйдёт в бэкап; откат — «откати "
            "патч %s»)%s" % (d.name, d.name, own),
            release()])
    except ValueError as e:
        _log({"path": str(p), "requirement": requirement, "ok": False,
              "error": str(e)})
        _lesson("кодер-брак", str(e))
        return "\n".join(lines + [str(e), release()])
    except Exception as e:
        _log({"path": str(p), "requirement": requirement, "ok": False,
              "error": str(e)})
        _lesson("кодер-ошибка", str(e))
        return "\n".join(lines + ["ошибка кодера: %s" % e, release()])


# ---------------------------------------------------------------
# Ф154 «ДИФФ ПАТЧА» (круг 25, самолечение v2): патч без диффа —
# чёрный ящик. Кодер пишет файл целиком, а Создатель видит ЧТО
# изменилось: у каждого патча рождается patch.diff (unified, difflib —
# без новых зависимостей) и человеческая сводка из фактов (строки,
# имена функций/классов по AST — гейт §5: истину говорит код, не LLM).
# ---------------------------------------------------------------

def _build_diff(old_text: str, new_text: str, name: str) -> str:
    """Unified diff «было → стало». Новый файл — весь в плюсах."""
    d = list(difflib.unified_diff(
        (old_text or "").splitlines(keepends=True),
        (new_text or "").splitlines(keepends=True),
        fromfile="было/" + name, tofile="стало/" + name))
    if d and not d[-1].endswith("\n"):
        d[-1] += "\n"
    return "".join(d)


def _diff_stats(diff_text: str) -> tuple:
    """(+строк, −строк) по диффу. Строки заголовков не считаются."""
    add = rem = 0
    for line in diff_text.splitlines():
        if line.startswith("+") and not line.startswith("+++"):
            add += 1
        elif line.startswith("-") and not line.startswith("---"):
            rem += 1
    return add, rem


def _ast_names(code: str) -> tuple:
    """(функции, классы) по AST. Не-код — пустые множества, не ошибка."""
    import ast
    funcs: set = set()
    classes: set = set()
    try:
        tree = ast.parse(code or "")
    except SyntaxError:
        return funcs, classes
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            funcs.add(node.name)
        elif isinstance(node, ast.ClassDef):
            classes.add(node.name)
    return funcs, classes


def _names_summary(old_code: str, new_code: str) -> str:
    """Человеческая сводка изменений имён: новая/задета/ушла."""
    of, oc = _ast_names(old_code)
    nf, nc = _ast_names(new_code)
    parts = []
    f_new, f_gone, f_touch = (nf - of, of - nf, nf & of)
    if f_new:
        parts.append("функции: %s (новые)" % ", ".join(sorted(f_new)[:6]))
    if f_touch:
        parts.append("функции: %s (задеты)" % ", ".join(sorted(f_touch)[:6]))
    if f_gone:
        parts.append("функции: %s (ушли)" % ", ".join(sorted(f_gone)[:6]))
    c_new, c_gone = nc - oc, oc - nc
    if c_new:
        parts.append("классы: %s (новые)" % ", ".join(sorted(c_new)[:4]))
    if c_gone:
        parts.append("классы: %s (ушли)" % ", ".join(sorted(c_gone)[:4]))
    return "; ".join(parts) if parts else "имена не менялись"


def _patch_diff_path(d: Path) -> Path:
    return d / "patch.diff"


def _old_source(d: Path, target: Path) -> str:
    """Честное «было» для диффа: бэкап (патч применялся) → сегодняшний
    файл цели (патч ждёт — именно против него писал его кодер) →
    пустота (файл был новым)."""
    backup = next(d.glob("backup_*"), None)
    if backup is not None:
        return backup.read_text(encoding="utf-8")
    try:
        if target.is_file():
            return target.read_text(encoding="utf-8")
    except OSError:
        pass
    return ""


def patch_diff(n: int) -> str:
    """«покажи патч N» — дифф целиком. Патч до v2 (без сохранённого
    диффа) — честная сборка из того, что есть: бэкап (а если его нет —
    пустота) против файла патча; эпоха названа, правда не выдумана."""
    d = _patch_dir(n)
    if d is None:
        return "патча №%d нет — скажи «патчи», покажу список" % n
    meta = _read_meta(d)
    fname = str(meta.get("file_name") or "")
    if not fname or not (d / fname).is_file():
        return "патч №%d битый: файла патча нет в %s" % (n, d)
    dp = _patch_diff_path(d)
    if dp.is_file():
        return dp.read_text(encoding="utf-8").strip() or "дифф пуст — файл не менялся"
    target = guard.resolve_path(str(meta.get("target") or "?"))
    old_src = _old_source(d, target)
    fresh = _build_diff(old_src, (d / fname).read_text(encoding="utf-8"),
                        fname)
    head = ("дифф не сохранился (патч круга до диффов) — вот свежий: "
            "файл патча против %s:\n" % fname)
    return head + (fresh.strip() or "разницы нет")


def patch_summary(n: int) -> str:
    """«что меняет патч N» — человеческая сводка ИЗ ФАКТОВ: строки
    +/−, имена функций/классов (новые/задеты/ушли), требование,
    статус. Никаких мнений LLM — только дифф и AST (гейт §5)."""
    d = _patch_dir(n)
    if d is None:
        return "патча №%d нет — скажи «патчи», покажу список" % n
    meta = _read_meta(d)
    fname = str(meta.get("file_name") or "")
    if not fname or not (d / fname).is_file():
        return "патч №%d битый: файла патча нет в %s" % (n, d)
    new_code = (d / fname).read_text(encoding="utf-8")
    dp = _patch_diff_path(d)
    target = guard.resolve_path(str(meta.get("target") or "?"))
    old_src = _old_source(d, target)
    if dp.is_file():
        diff_text = dp.read_text(encoding="utf-8")
        epoch = ""
    else:
        diff_text = _build_diff(old_src, new_code, fname)
        epoch = " (свежий: дифф v1-патча не сохранялся)"
    add, rem = _diff_stats(diff_text)
    names = _names_summary(old_src, new_code)
    status = ("применён" if meta.get("applied") else "ждёт внедрения")
    return ("патч №%s → %s\n+%d −%d строк%s; %s\nтребование: «%s»\n"
            "статус: %s\nцеликом — «покажи патч %s»"
            % (d.name, meta.get("target", "?"), add, rem, epoch, names,
               (meta.get("requirement") or "?")[:90], status, d.name))


# ---------------------------------------------------------------
# Ф155 «БРОНЯ ПРИМЕНЕНИЯ» (круг 25, самолечение v2): броня — не для
# одного пути, а для закона. «примени патч N» (рука Создателя) жил
# без дым-теста — красный патч мог лечь в дом и встретиться с ним
# только на батарее. Теперь ОБА пути (Создатель и сама Марфа)
# проходят один конвейер: бэкап → запись → тесты модуля И
# ПРИВЯЗАННЫЕ тесты (кто импортирует модуль — тот и задаёт его
# поведение) → красные? автоОткат, старый файл возвращается.
# ---------------------------------------------------------------

def _typed_path(target: Path) -> str:
    """Путь, который Создатель может НАПЕЧАТАТЬ и пройти стража.

    УРОК ЖИВОГО ЛОГА (день-18, 28.11): совет дома «почини %s» с ГОЛЫМ
    именем файла (target.name) был неисполним — страж R1 запрещает
    корень дома («путь рук должен содержать подпапку»), PermissionError
    рвал быстрый трек изнутри, ход молча падал в мозг. Совет дома —
    тоже команда (Ф184): в совете живёт путь с подпапкой, прямой
    слэш — и в печати, и в страже.
    """
    try:
        return (target.resolve()
                .relative_to(Path(config.HOME_DIR).resolve()).as_posix())
    except (ValueError, OSError):
        return target.name


def _related_tests(module_stem: str, limit: int = 3) -> list:
    """Тест-файлы, импортирующие модуль — по строкам импортов.

    «from core import voice», «from core.voice import speak»,
    «from core import voice as v» — все считаются; «voices» — нет
    (сравнение по словам, не подстрока — урок «жадных префиксов»).
    Собственный тест модуля не дублируем — он и так в прогоне.
    Потолок limit: батарея дома 1600+ тестов, дым-тест внедрения —
    не батарея, а его честная тень.
    """
    tdir = config.HOME_DIR / "tests"
    own = "test_%s.py" % module_stem
    if not tdir.is_dir():
        return []
    out = []
    for f in sorted(tdir.glob("test_*.py")):
        if f.name == own or len(out) >= limit:
            continue
        try:
            txt = f.read_text(encoding="utf-8")
        except OSError:
            continue
        for line in txt.splitlines():
            ls = line.strip()
            if not (ls.startswith("from core") or ls.startswith("import core")):
                continue
            tokens = set(re.split(r"[^\w.]+", ls))
            if module_stem in tokens or ("core." + module_stem) in tokens:
                out.append(f.name)
                break
    return out[:limit]


def _run_pytest(files: list, timeout: float) -> tuple:
    """Прогон pytest по списку файлов: (код возврата, хвост вывода)."""
    r = subprocess.run(
        [sys.executable, "-m", "pytest", "-x", "-q"] + list(files),
        cwd=str(config.HOME_DIR), capture_output=True, text=True,
        timeout=timeout)
    tail = "\n".join((r.stdout or "").splitlines()[-6:])
    return r.returncode, tail


def _patch_dir(n: int) -> Optional[Path]:
    d = config.PATCHES_DIR / ("%04d" % n)
    return d if d.is_dir() else None


def apply_patch(n: int) -> str:
    """ПС-2: применить патч №N — воля Создателя, произнесённая командой.

    Бэкап старого файла ложится рядом с патчем; запись идёт через руки
    (страж: путь внутри дома + канарейки). Синтаксис перепроверяется —
    между написанием и применением файл мог быть закодирован заново.
    Ф155 «БРОНЯ ПРИМЕНЕНИЯ» (круг 25): после записи — дым-тест модуля
    и привязанных тестов; красный — автоОткат, старый файл на месте,
    дом не знает о неудаче. Броня одна для всех: Создателю — как
    Марфе (Ф75): дом не краснеет ни от чьей руки.
    """
    d = _patch_dir(n)
    if d is None:
        return "патча №%d нет — скажи «патчи», покажу список" % n
    meta = _read_meta(d)
    fname = str(meta.get("file_name") or "")
    if not fname or not (d / fname).is_file():
        return "патч №%d битый: файла патча нет в %s" % (n, d)
    target = guard.resolve_path(str(meta.get("target") or ""))
    code = (d / fname).read_text(encoding="utf-8")
    try:
        _check_patch(target, code)
    except ValueError as e:
        return "патч №%d не применяется: %s" % (n, e)
    # эфир: применение с бронёй — долгое действие (тесты после патча)
    progress.stage("применяю патч №%d: бэкап → запись → тесты…" % n)
    try:
        if target.is_file():
            (d / ("backup_" + target.name)).write_text(
                target.read_text(encoding="utf-8"), encoding="utf-8")
        hands.write_file(target, code)
    except PermissionError as e:
        return "СТРАЖ не пустил: %s" % e
    ok, report = _smoke_test(target)
    if not ok:
        # автоОткат: не позеленевшие тесты возвращают дом к прежнему
        # состоянию — дом не остаётся с непроверенной правкой (Ф155).
        # День-18: бэкап пишется ТОЛЬКО когда файл существовал — бэкапа
        # нет ⟺ патч создавал НОВЫЙ файл, и честный откат = вернуть
        # отсутствие (убрать файл), а не «ВЕРНУТЬ НЕ УДАЛОСЬ — проверь
        # руками!» (станция так и осталась с непроверенным файлом).
        backup = next(d.glob("backup_*"), None)
        rolled = False
        if backup is not None:
            try:
                hands.write_file(target, backup.read_text(encoding="utf-8"))
                rolled = True
            except Exception as e:
                _lesson("применение-откат-не-удался", "%s: %s"
                        % (target.name, e))
        else:
            try:
                if target.is_file():
                    target.unlink()
                rolled = True
            except OSError as e:
                _lesson("применение-откат-не-удался", "%s: %s"
                        % (target.name, e))
        _log({"apply": n, "target": str(target), "ok": False,
              "smoke": report[:400], "rolled_back": rolled})
        _lesson("применение-откат",
                "%s: тесты после патча не позеленели, откат %s"
                % (target.name, "состоялся" if rolled else "НЕ удался"))
        return ("патч №%d НЕ ПРИМЕНЁН: тесты после патча не позеленели — "
                "%s. Вот что сказали тесты:\n%s\nСкажи «почини %s: "
                "<что исправить>» — кодер перепишет, или расскажи "
                "архитектору."
                % (n,
                   ("старый файл я вернула на место" if backup is not None
                    else "нового файла не было — я его убрала, дом как "
                    "до патча") if rolled
                   else "ВЕРНУТЬ НЕ УДАЛОСЬ — проверь руками!",
                   report, _typed_path(target)))
    meta["applied"] = True
    meta["applied_ts"] = dt.datetime.now().isoformat(timespec="seconds")
    (d / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    _log({"apply": n, "target": str(target), "ok": True,
          "smoke": report[:200]})
    _lesson("кодер-применение", "%s -> %s" % (n, target.name))
    return ("патч №%d ПРИМЕНЁН: %s\nбэкап старого: %s\nтесты после "
            "патча зелёные:\n%s\nпроверь дом: «статус»; не понравится — "
            "«откати патч %d»"
            % (n, target, d, report, n))


def rollback_patch(n: int) -> str:
    """Откат патча №N: бэкап возвращается на место."""
    d = _patch_dir(n)
    if d is None:
        return "патча №%d нет — скажи «патчи», покажу список" % n
    meta = _read_meta(d)
    backup = next(d.glob("backup_*"), None)
    if backup is None:
        target = guard.resolve_path(str(meta.get("target") or "?"))
        return ("патч №%d не откатить: бэкапа нет (файл был новым — "
                "если не нужен, удали руками %s)" % (n, target))
    target = guard.resolve_path(str(meta.get("target") or ""))
    try:
        hands.write_file(target, backup.read_text(encoding="utf-8"))
    except PermissionError as e:
        return "СТРАЖ не пустил: %s" % e
    meta["applied"] = False
    (d / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    _log({"rollback": n, "target": str(target), "ok": True})
    return "патч №%d ОТКАЧЕН: %s вернулся из бэкапа" % (n, target)


def list_patches() -> str:
    """Список патчей песочницы: №, цель, требование, статус."""
    if not config.PATCHES_DIR.is_dir():
        return ("патчей пока нет — «почини <файл>: <что сделать>» напишет "
                "первый")
    rows = []
    for d in sorted(config.PATCHES_DIR.iterdir()):
        if not d.is_dir() or not d.name[:4].isdigit():
            continue
        meta = _read_meta(d)
        rows.append("№%s %s — %s [%s]"
                    % (d.name, meta.get("target", "?"),
                       (meta.get("requirement") or "?")[:80],
                       "применён" if meta.get("applied") else "ждёт внедрения"))
    if not rows:
        return ("патчей пока нет — «почини <файл>: <что сделать>» напишет "
                "первый")
    return "\n".join(rows)


# ---------------------------------------------------------------
# Ф75. СВОБОДА ВНЕДРЯТЬ СЕБЯ (директива Создателя, 22.11)
# ---------------------------------------------------------------

def self_write_resolution() -> Optional[dict]:
    """Резолюция Создателя на самовнедрение (data\\self_write.json).

    Как моторика (hands_enabled.json) и живой язык (live_voice.json):
    воля Создателя живёт в data/, не в коде — одна фраза включает,
    одна выключает. Нет файла / битый JSON / enabled не True — гейт
    закрыт (None), самовнедрение честно отказывает.
    """
    try:
        raw = Path(config.SELF_WRITE_FILE).read_text(encoding="utf-8")
        rec = json.loads(raw)
        if isinstance(rec, dict) and rec.get("enabled") is True:
            return rec
    except Exception:
        pass
    return None


def allow_self_write() -> str:
    """«разреши внедрять себя» — одна фраза Создателя, резолюция на диск."""
    try:
        Path(config.SELF_WRITE_FILE).parent.mkdir(parents=True, exist_ok=True)
        Path(config.SELF_WRITE_FILE).write_text(
            json.dumps({"enabled": True,
                        "ts": dt.datetime.now().isoformat(timespec="seconds"),
                        "note": "Создатель разрешил самовнедрение голосом"},
                       ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError as e:
        return "резолюция не записалась: %s — скажи архитектору" % e
    _log({"self_write": "allowed"})
    _lesson("самовнедрение", "Создатель выдал резолюцию")
    return ("Резолюция записана: теперь я могу внедрять свои патчи сама — "
            "«внедри патч <№>». Каждый раз: бэкап, дым-тест модуля, "
            "автоОткат при красном. Забрать свободу — «запрети "
            "внедрять себя».")


def forbid_self_write() -> str:
    """«запрети внедрять себя» — резолюция снята, патчи снова за Создателем."""
    try:
        p = Path(config.SELF_WRITE_FILE)
        if p.is_file():
            p.unlink()
    except OSError as e:
        return "не получилось снять резолюцию: %s" % e
    _log({"self_write": "forbidden"})
    return ("Резолюция снята: патчи снова внедряет только Создатель — "
            "«примени патч <№>».")


def _smoke_test(target: Path) -> tuple:
    """Дым-тест после внедрения: (можно жить, честный отчёт).

    Ф155 (круг 25): гоняем не только собственный тест модуля, но и
    ПРИВЯЗАННЫЕ — тест-файлы, импортирующие модуль: чей тест импортирует,
    тот и задаёт поведение. Есть хоть один тест — pytest (-x -q, стоп
    на первом красном); тестов нет — хотя бы компиляция. Это цена
    свободы: Марфа не говорит «уже починила», пока её же тесты не
    позеленели — и Создателю тот же закон (броня — не для одного
    пути, а для всех, кто трогает дом).
    """
    test_file = config.HOME_DIR / "tests" / ("test_%s.py" % target.stem)
    related = _related_tests(target.stem)
    # УРОК ЖИВОГО ЛОГА (день-18): станция ответила «pytest test_krug26_circle.py
    # (код 4) no tests ran» — броня звала тесты ГОЛЫМ именем, а pytest
    # бежит из корня дома, где тестов нет (они в tests\). Код 4 — не
    # «красные тесты», а «файл не найден»: броня валила патч молча,
    # не запустив ни одного теста. Путь — tests\<имя>, как их видит
    # pytest из корня дома.
    files = ([str(Path("tests") / test_file.name)] if test_file.is_file()
             else []) + [str(Path("tests") / n) for n in related]
    # Ф161 «МАСТЕРСКАЯ» (круг 26): патч в core\customtools\ проверяется
    # золотым якорем мастерской — тестом, валидирующим КАЖДЫЙ
    # инструмент-файл (форма, подъём, вызов). Красный якорь = откат:
    # кривой инструмент не живёт в доме ни секунды
    try:
        if "customtools" in [p.lower() for p in target.parts]:
            anchor = config.HOME_DIR / "tests" / "test_krug26_circle.py"
            if anchor.is_file() and str(Path("tests") / anchor.name) \
                    not in files:
                files.append(str(Path("tests") / anchor.name))
    except Exception:
        pass
    try:
        if files:
            rc, tail = _run_pytest(files, config.SELF_WRITE_TEST_SEC)
            return (rc == 0,
                    ("pytest %s (код %d)\n%s"
                     % (" ".join(files), rc, tail)).strip())
        import py_compile
        py_compile.compile(str(target), doraise=True)
        return True, ("компиляция ОК (тестов модуля нет: tests/%s)"
                      % test_file.name)
    except subprocess.TimeoutExpired:
        return False, ("дым-тест не уложился в %d с — считаю провалом"
                       % config.SELF_WRITE_TEST_SEC)
    except Exception as e:
        return False, "дым-тест упал: %s: %s" % (type(e).__name__, e)


def self_apply(n: int) -> str:
    """Ф75: Марфа внедряет патч №N САМА — с резолюцией, бэкапом,
    дым-тестом и автоОткатом.

    Директива Создателя (22.11): «дай Марфе свободу, чтоб она могла
    уже сама писать и внедрять себя — она умная модель». Свобода —
    не вседозволенность: без резолюции — честный отказ; с резолюцией —
    конвейер с бронёй: бэкап → запись через руки (страж) → дым-тест
    модуля → красный? автоОткат, старый файл возвращается на место.
    """
    if self_write_resolution() is None:
        return ("самовнедрение не разрешено. Одна фраза Создателя "
                "включает его: «разреши внедрять себя». Пока — «примени "
                "патч %d»: применю я, а внедрит Создатель" % n)
    d = _patch_dir(n)
    if d is None:
        return "патча №%d нет — скажи «патчи», покажу список" % n
    meta = _read_meta(d)
    if meta.get("applied"):
        return "патч №%d уже применён — повторно не внедряю" % n
    fname = str(meta.get("file_name") or "")
    if not fname or not (d / fname).is_file():
        return "патч №%d битый: файла патча нет в %s" % (n, d)
    target = guard.resolve_path(str(meta.get("target") or ""))
    code = (d / fname).read_text(encoding="utf-8")
    try:
        _check_patch(target, code)
    except ValueError as e:
        return "патч №%d не внедряется: %s" % (n, e)
    # эфир: внедрение — долгое действие (дым-тест гоняет тесты модуля)
    progress.stage("внедряю патч №%d: бэкап → запись → дым-тест…" % n)
    try:
        if target.is_file():
            (d / ("backup_" + target.name)).write_text(
                target.read_text(encoding="utf-8"), encoding="utf-8")
        hands.write_file(target, code)
    except PermissionError as e:
        return "СТРАЖ не пустил: %s" % e
    except Exception as e:
        _lesson("самовнедрение-сбой", "запись: %s" % e)
        return "запись не удалась: %s — дом не тронут" % e
    ok, report = _smoke_test(target)
    if not ok:
        # автоОткат: не позеленевший дым-тест возвращает дом к прежнему
        # состоянию. День-18: НОВЫЙ файл (бэкапа нет) — откат = удалить,
        # вернуть отсутствие (зеркало apply_patch, броня одна для всех)
        backup = next(d.glob("backup_*"), None)
        rolled = False
        if backup is not None:
            try:
                hands.write_file(target, backup.read_text(encoding="utf-8"))
                rolled = True
            except Exception as e:
                _lesson("самовнедрение-откат-не-удался", "%s: %s"
                        % (target.name, e))
        else:
            try:
                if target.is_file():
                    target.unlink()
                rolled = True
            except OSError as e:
                _lesson("самовнедрение-откат-не-удался", "%s: %s"
                        % (target.name, e))
        _log({"self_apply": n, "target": str(target), "ok": False,
              "smoke": report[:400], "rolled_back": rolled})
        _lesson("самовнедрение-откат",
                "%s: дым-тест не позеленел, откат %s"
                % (target.name, "состоялся" if rolled else "НЕ удался"))
        return ("патч №%d НЕ ВНЕДРЁН: дым-тест не позеленел — "
                "%s. Вот что сказал тест:\n%s\nСкажи «почини %s: <что "
                "исправить>» — кодер перепишет, или расскажи архитектору."
                % (n,
                   ("старый файл я вернула на место" if backup is not None
                    else "нового файла не было — я его убрала, дом как "
                    "до патча") if rolled
                   else "ВЕРНУТЬ НЕ УДАЛОСЬ — проверь руками!",
                   report, _typed_path(target)))
    meta["applied"] = True
    meta["applied_ts"] = dt.datetime.now().isoformat(timespec="seconds")
    meta["self_applied"] = True
    (d / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    _log({"self_apply": n, "target": str(target), "ok": True,
          "smoke": report[:200]})
    _lesson("самовнедрение", "%s -> %s" % (n, target.name))
    return ("патч №%d ВНЕДРЁН мною: %s\nбэкап старого: %s\nдым-тест "
            "зелёный:\n%s\nне понравится — «откати патч %d»"
            % (n, target, d, report, n))
