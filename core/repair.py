# -*- coding: utf-8 -*-
r"""core/repair.py — САМОЛЕЧЕНИЕ ДОМА v1 (ТЗ_Самолечение_v1, 22.11).

Создатель: «надо идти дальше по строению дома, и давать Марфе самой
себя лечить и доделывать, она достаточно умная модель... среди умных
рук у неё есть очень прокачанная модель 7b, которая хорошо знает
питон». qwen2.5-coder-7b-instruct спала в чулане (АРСЕНАЛ: «вернёмся,
когда Марфа начнёт чинить свои кнопки сама») — день наступил.

Пятый слуга-разум — КОДЕР (порт 8085, СЛУГА ПО ВЫЗОВУ, как руки).
Доктрина ролей: МОЗГ (или Создатель) ставит требование, КОДЕР печатает
код, СТРАЖ проверяет, СОЗДАТЕЛЬ применяет. Конвейер:

    «почини <файл>: <что сделать>»
      → файл читается (руки + страж: только внутри дома)
      → кодер поднимается (VRAM-танец: кодер ~4.7 + глаза 3.0 > 6 ГБ,
        глаза присели — та же механика, что у рук)
      → кодер пишет файл ЦЕЛИКОМ в одном блоке ```python
      → страж патча: только .py, лимит строк, AST-синтаксис,
        канарейки, «вернул без изменений» = брак
      → патч ложится в data\patches\000N\ — ПЕСОЧНИЦА, не core\
      → кодер ложится, глаза возвращаются (доктором)
      → Создатель: «примени патч N» (бэкап + запись) / «откати патч N»

Неприкосновенность (главный закон модуля): make_patch НИКОГДА не пишет
вне data\patches\ — код дома меняет только Создатель своей командой,
с бэкапом и откатом. Мозг получает инструмент code_patch с тем же
конвейером: он ДОВЕРЯЕТ требование, как ui_action — задание.

Швы для тестов (tests/test_repair.py подменяет): _ask_coder /
ensure_server / release / _find_model — реальный сервер не нужен.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import subprocess
import time
from pathlib import Path
from typing import Optional

import requests

from core import config, hands, progress
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
        p.parent.mkdir(parents=True, exist_ok=True)
        rec = dict(rec)
        rec.setdefault("ts", dt.datetime.now().isoformat(timespec="seconds"))
        with p.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
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
        meta = {"target": str(p), "file_name": p.name,
                "requirement": requirement, "new_file": not bool(src),
                "applied": False,
                "ts": dt.datetime.now().isoformat(timespec="seconds")}
        (d / "meta.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
        _log({"path": str(p), "requirement": requirement, "ok": True,
              "patch": str(d)})
        _lesson("кодер-патч", "%s: %s" % (p.name, requirement))
        return "\n".join(lines + [
            "патч №%s ГОТОВ: %s" % (d.name, d / p.name),
            "посмотреть можно в блокноте; применить — скажи «примени "
            "патч %s» (старый файл уйдёт в бэкап; откат — «откати "
            "патч %s»)" % (d.name, d.name),
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


def _patch_dir(n: int) -> Optional[Path]:
    d = config.PATCHES_DIR / ("%04d" % n)
    return d if d.is_dir() else None


def apply_patch(n: int) -> str:
    """ПС-2: применить патч №N — воля Создателя, произнесённая командой.

    Бэкап старого файла ложится рядом с патчем; запись идёт через руки
    (страж: путь внутри дома + канарейки). Синтаксис перепроверяется —
    между написанием и применением файл мог быть закодирован заново.
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
    try:
        if target.is_file():
            (d / ("backup_" + target.name)).write_text(
                target.read_text(encoding="utf-8"), encoding="utf-8")
        hands.write_file(target, code)
    except PermissionError as e:
        return "СТРАЖ не пустил: %s" % e
    meta["applied"] = True
    meta["applied_ts"] = dt.datetime.now().isoformat(timespec="seconds")
    (d / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    _log({"apply": n, "target": str(target), "ok": True})
    _lesson("кодер-применение", "%s -> %s" % (n, target.name))
    return ("патч №%d ПРИМЕНЁН: %s\nбэкап старого: %s\nпроверь дом: "
            "«статус»; не понравится — «откати патч %d»"
            % (n, target, d, n))


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
                       "применён" if meta.get("applied") else "ждёт Создателя"))
    if not rows:
        return ("патчей пока нет — «почини <файл>: <что сделать>» напишет "
                "первый")
    return "\n".join(rows)
