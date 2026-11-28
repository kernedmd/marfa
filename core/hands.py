# -*- coding: utf-8 -*-
"""core/hands.py — РУКИ МАРФЫ (ТЗ 3.3): чистый Python, без магии.

Инструменты: read_file, write_file, run_python, browser_search, check_brackets.
Правило: любое потенциально опасное действие — сначала через СТРАЖ (3.7).
Каждое действие с данными дома (файлы, код, буфер, поиск) пишется в
hash-chain лог аудита.

Круг 34 «АУДИТ РУК И СТРАЖА» — порог честности:
- run_python — ГРАНИЦА, не песочница: AST-белый список (check_code_ast)
  + regex-слой, потолок кода, потолок вывода (читатель-поток, ребёнок
  не блокируется), -X utf8 вместо мёртвых под -I переменных, env —
  allowlist, убийство ДЕРЕВА процессов (taskkill /T), секреты не едут
  в код и не возвращаются в чат. RAM-лимита Windows-процесса нет
  (нужен Job Object) — признано в докстринге честно.
- read_file: открытый лимит ДО чтения (TOCTOU закрыт), папка/двоичник
  — честный отказ, UTF-16 по BOM, chat-cap с пометкой, секреты в файле
  — страж не пустил.
- write_file: потолок записи, атомарная запись (tmp + os.replace),
  бэкап прошлой версии, LF не транслируется (write_bytes), content
  не-строка — честный отказ. Тело дома (safety/, core/, доктрина,
  канарейки, журнал) руки не пишут — только конвейер ремонта
  (write_file(..., _via="repair"), бэкап и дым-тест внутри repair).
- буфер: секреты проверяются и на ЧТЕНИИ (менеджер паролей кладёт в
  буфер пароли), нетекстовый буфер selftest не «восстанавливает»
  молча пустой строкой, отказ вернуть чужое — слышен в отчёте,
  чужие данные при гонке не показываются.
- browser_search: секреты не уезжают в поисковик, инъекция проверяется
  на РЕЗУЛЬТАТАХ, DDG-парсер разэкранирует entities, разбирает жирные
  заголовки и распаковывает редирект-ссылки, ответ читается с потолком.
"""
from __future__ import annotations
import html as _html
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Callable, Optional

from core import config
from safety import guard

# Ограничения рук (проще простить, чем пережить)
MAX_READ_BYTES = 2 * 1024 * 1024          # 2 МБ на чтение (RAM дома)
MAX_REPLY_CHARS = 20000                   # сколько файла едет в чат/мозг
MAX_WRITE_BYTES = 500000                  # потолок записи за один вызов
MAX_RUN_SECONDS = 20                      # таймаут run_python
MAX_RUN_OUTPUT_BYTES = 256 * 1024         # потолок вывода run_python
MAX_SEARCH_RESULTS = 5
MAX_SEARCH_BYTES = 1000000                # потолок HTML-ответа DDG

# env дочернего процесса — allowlist, не blocklist (круг 34): MARFA_*,
# ключи моделей и прочие секреты в ребёнка не едут вовсе
_RUN_ENV_ALLOWLIST = (
    "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "PATH", "COMSPEC", "PATHEXT",
    "TEMP", "TMP", "NUMBER_OF_PROCESSORS", "PROCESSOR_ARCHITECTURE",
    "HOME", "LANG", "LC_ALL", "TERM",
)


# ---------------------------------------------------------------
# Файлы
# ---------------------------------------------------------------
def read_file(path: str | Path) -> str:
    """Чтение файла внутри дома. Вне дома — СТРАЖ откажет (HIGH).
    Читается ТОЛЬКО путь, который резолвнул СТРАЖ — расхождение исключено.

    Круг 34: размер проверяется на прочитанном, а не по stat (TOCTOU:
    файл мог вырасти между проверкой и чтением); папка и двоичник —
    честный отказ; UTF-16 распознаётся по BOM; секреты в файле —
    страж не пустил; в чат едет не больше MAX_REPLY_CHARS с пометкой
    «обрезано» — лимит RAM и лимит ответа теперь разные вещи."""
    p = guard.resolve_path(path)
    guard.enforce(guard.check_path(p), {"tool": "read_file"})
    if not p.is_file():
        raise ValueError(f"это не файл (папка или нет вовсе): {p.name}")
    with p.open("rb") as fh:
        data = fh.read(MAX_READ_BYTES + 1)
    if len(data) > MAX_READ_BYTES:
        raise ValueError(f"файл больше {MAX_READ_BYTES} байт: {p.name}")
    if data[:2] in (b"\xff\xfe", b"\xfe\xff"):
        text = data.decode("utf-16", errors="replace")   # \x00 — часть формата
    else:
        if b"\x00" in data[:8192]:
            raise ValueError(f"двоичный файл, не текст: {p.name}")
        text = data.decode("utf-8", errors="replace")
    guard.enforce(guard.check_secrets(text), {"tool": "read_file"})
    if len(text) > MAX_REPLY_CHARS:
        return text[:MAX_REPLY_CHARS] + (
            "\n…(обрезано: показала первые %d из %d символов — файл длинный)"
            % (MAX_REPLY_CHARS, len(text)))
    return text


def write_file(path: str | Path, content: str, _via: str = "hands") -> str:
    """Запись файла внутри дома. Родитель создаётся. СТРАЖ проверяет
    путь, размер и содержимое.

    Круг 34: тело дома (safety/, core/, доктрина, канарейки, журнал,
    .git, venv) руки не пишут — CRITICAL отказ; конвейер ремонта
    зовёт с _via="repair" (его бэкап и дым-тест — внутри repair).
    Запись атомарная: tmp + os.replace, крах посреди записи не оставит
    обрезанный файл; предыдущая версия уезжает в .bak; LF не
    транслируется в CRLF (write_bytes — записанные байты = content).
    content — только строка: словарь от мозга раньше тихо писал
    Python-repr в файл, теперь честный отказ."""
    if not isinstance(content, str):
        raise ValueError("content должен быть строкой, а не %s"
                         % type(content).__name__)
    p = guard.resolve_path(path)
    mode = "read" if _via == "repair" else "write"
    guard.enforce(guard.check_path(p, mode=mode), {"tool": "write_file"})
    guard.enforce(guard.check_secrets(content), {"tool": "write_file"})
    if len(content.encode("utf-8")) > MAX_WRITE_BYTES:
        guard.enforce(guard.Verdict(
            "HIGH", "deny",
            "запись длиннее %d байт — делай по частям" % MAX_WRITE_BYTES,
            "write.len"), {"tool": "write_file"})
    p.parent.mkdir(parents=True, exist_ok=True)
    if p.exists():                      # прошлую версию не теряем
        try:
            shutil.copyfile(p, p.with_name(p.name + ".bak"))
        except OSError:
            pass                        # нет бэкапа — не отмена записи
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_bytes(content.encode("utf-8"))
    tmp.replace(p)                      # атомарно: либо старая, либо новая
    return f"записано: {p} ({len(content)} символов)"


# ---------------------------------------------------------------
# Запуск Python-кода в границе (не песочница — честная граница)
# ---------------------------------------------------------------
def _kill_tree(proc: subprocess.Popen) -> None:
    """Убивает процесс С ДЕТЬМИ: на Windows subprocess убивает только
    прямого ребёнка, внуки продолжали жить и работать в сеть (круг 34)."""
    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                capture_output=True, timeout=10)
        else:
            proc.kill()
    except Exception:
        pass                            # умер и умер — таймаут своё сделал
    try:
        proc.wait(timeout=5)
    except Exception:
        pass


def _drain(stream, cell: dict) -> None:
    """Читает поток ДО КОНЦА, но хранит не больше MAX_RUN_OUTPUT_BYTES:
    перестать читать нельзя (ребёнок блокируется на полном pipe и
    умирает по таймауту — ложное «прервано»), а тащить гигабайты
    в память панели — RAM-флуд (круг 34). Лишнее читается и выбрасывается."""
    keep: list[bytes] = []
    kept = 0
    got = 0
    while True:
        chunk = stream.read(4096)
        if not chunk:
            break
        got += len(chunk)
        if kept < MAX_RUN_OUTPUT_BYTES:
            take = chunk[:MAX_RUN_OUTPUT_BYTES - kept]
            keep.append(take)
            kept += len(take)
    cell["data"] = b"".join(keep)
    cell["total"] = got


def run_python(code: str, timeout: int = MAX_RUN_SECONDS) -> str:
    """Короткий Python-код в границе. Опасное отвергает СТРАЖ двумя
    слоями: regex по заведомо опасному + AST-белый список (open, exec,
    eval, сеть, subprocess, ctypes, динамика недостижимы структурой
    кода). Это ГРАНИЦА, не песочница: RAM-потолок процесса не ставится
    (нужен Job Object — отдельное решение станции), тяжёлые вычисления
    ограничены таймаутом и потолком вывода. Код и факт исполнения
    пишутся в журнал аудита."""
    code = str(code or "")
    # слой 1: regex-чёрный список, потолок длины, null-байты, секреты в коде
    guard.enforce(guard.check_code(code),
                  {"tool": "run_python", "code": code[:200]})
    # слой 1.5: секреты не едут в ребёнка (круг 34)
    guard.enforce(guard.check_secrets(code), {"tool": "run_python.code"})
    # слой 2: AST-граница — fail-closed, что не в белом списке — отказ
    guard.enforce(guard.check_code_ast(code),
                  {"tool": "run_python", "code": code[:200]})
    env = {k: os.environ[k] for k in _RUN_ENV_ALLOWLIST if k in os.environ}
    try:
        proc = subprocess.Popen(
            [sys.executable, "-I", "-X", "utf8", "-c", code],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL, cwd=str(config.HOME_DIR), env=env)
    except OSError as e:
        return f"ошибка запуска: {e}"
    out_cell: dict = {"data": b"", "total": 0}
    err_cell: dict = {"data": b"", "total": 0}
    t1 = threading.Thread(target=_drain, args=(proc.stdout, out_cell), daemon=True)
    t2 = threading.Thread(target=_drain, args=(proc.stderr, err_cell), daemon=True)
    t1.start(); t2.start()
    timed_out = False
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        _kill_tree(proc)
    t1.join(timeout=5); t2.join(timeout=5)
    for stream in (proc.stdout, proc.stderr):
        try:
            stream.close()
        except Exception:
            pass
    if timed_out:
        return f"ошибка: код выполнялся дольше {timeout} с, прерван"
    out = out_cell["data"].decode("utf-8", errors="replace")
    err = err_cell["data"].decode("utf-8", errors="replace")
    if proc.returncode != 0:
        text = f"ошибка ({proc.returncode}): {err.strip()[:2000]}"
        if out.strip():
            text += " (stdout: %s)" % out.strip()[:1000]
        return text
    result = out.strip() if out.strip() else "(пусто)"
    if err.strip():
        result += " (stderr: %s)" % err.strip()[:500]
    if out_cell["total"] > MAX_RUN_OUTPUT_BYTES or err_cell["total"] > MAX_RUN_OUTPUT_BYTES:
        result += (" (вывод был длиннее %d байт — показала начало)"
                   % MAX_RUN_OUTPUT_BYTES)
    # секреты не возвращаются из ребёнка в чат (круг 34: output-канал)
    guard.enforce(guard.check_secrets(result), {"tool": "run_python.output"})
    guard.decide(guard.Verdict("LOW", "allow", "run_python завершён",
                               "run.python.out"),
                 {"stdout_bytes": out_cell["total"], "stderr_bytes": err_cell["total"]})
    return result


# ---------------------------------------------------------------
# Скобки
# ---------------------------------------------------------------
_PAIRS = {")": "(", "]": "[", "}": "{"}


def check_brackets(text: str) -> str:
    """Проверка баланса (), [], {}. Возвращает человекочитаемый вердикт.
    Проверка наивная: скобки внутри строк и смайлов (:) тоже считает —
    для кода это ложные тревоги; честное применение — диктовка и текст,
    а код пусть проверяет конвейер ремонта через ast.parse."""
    text = str(text or "")
    stack: list[str] = []
    for i, ch in enumerate(text):
        if ch in "([{":
            stack.append(ch)
        elif ch in _PAIRS:
            if not stack or stack[-1] != _PAIRS[ch]:
                return f"НЕСБАЛАНСИРОВАНО: неожиданная '{ch}' на позиции {i + 1}"
            stack.pop()
    if stack:
        return f"НЕСБАЛАНСИРОВАНО: не закрыты {', '.join(stack)}"
    guard.decide(guard.Verdict("LOW", "allow", "скобки проверены", "brackets.ok"),
                 {"tool": "check_brackets", "len": len(text)})
    return "баланс: ОК"


# ---------------------------------------------------------------
# Буфер обмена (№18 роадмапа 30 + Р-4 рук: кириллица — через буфер)
# ---------------------------------------------------------------

def _pyperclip():
    """Голый импорт pyperclip (шов для тестов: подменяют, чтобы
    имитировать «нет модуля»)."""
    import pyperclip
    return pyperclip


def clipboard_write(text: str) -> str:
    """Положить текст в буфер обмена (№18). Только по прямой команде.

    Границы: лимит CLIPBOARD_LIMIT (500 — буфер не печать, но и не
    свалка), секреты (канарейки, ключи, кодовое слово) мимо — буфер
    живёт в системе дольше чата и вставится куда угодно. Отказ СТРАЖА —
    PermissionError (как у файлов), нет модуля — RuntimeError с командой
    установки. Возвращает человекочитаемую сводку.
    """
    text = str(text or "")
    if not text.strip():
        raise ValueError("пустой текст в буфер не кладут")
    guard.enforce(guard.check_secrets(text), {"tool": "clipboard"})
    if len(text) > config.CLIPBOARD_LIMIT:
        guard.enforce(guard.Verdict(
            "HIGH", "deny",
            "в буфер — не больше %d символов, а не %d"
            % (config.CLIPBOARD_LIMIT, len(text)), "clipboard.len"),
            {"tool": "clipboard"})
    try:
        pc = _pyperclip()
    except ImportError as e:
        raise RuntimeError(
            "нет модуля буфера: %s — venv\\Scripts\\pip install pyperclip "
            "(или скажи «в буфер <текст>» ещё раз после установки)" % e)
    pc.copy(text)
    guard.decide(guard.Verdict("LOW", "allow", "запись в буфер", "clipboard.write"),
                 {"tool": "clipboard", "len": len(text)})
    return ("В буфере обмена: %d символов. Вставится по ctrl+v — "
            "сам или скажи «руки клавиши ctrl+v»" % len(text))


def clipboard_read() -> str:
    """«что в буфере» (Ф63, день-10): прочитать буфер обмена в чат.

    Границы: лимит CLIPBOARD_READ_LIMIT (показать — не значит
    притащить всё). Круг 34: секреты проверяются и на ЧТЕНИИ —
    менеджер паролей кладёт в буфер пароль, а не «свой текст Создателя»;
    показ живёт секунду в чате, но потом уезжает в журнал диалога и в
    контекст мозга. Пустой и whitespace-буфер различаются честно."""
    try:
        pc = _pyperclip()
    except ImportError as e:
        raise RuntimeError(
            "нет модуля буфера: %s — venv\\Scripts\\pip install pyperclip "
            "(или скажи «проверь буфер», аптечка поставит сама)" % e)
    text = str(pc.paste() or "")
    if not text:
        return "буфер обмена пуст"
    if not text.strip():
        return "в буфере %d невидимых символов (пробелы/переносы), текста нет" % len(text)
    guard.enforce(guard.check_secrets(text), {"tool": "clipboard_read"})
    if len(text) > config.CLIPBOARD_READ_LIMIT:
        shown = text[:config.CLIPBOARD_READ_LIMIT]
        cut = "…\n(показала первые %d из %d символов — буфер длинный)"
        return shown + cut % (config.CLIPBOARD_READ_LIMIT, len(text))
    guard.decide(guard.Verdict("LOW", "allow", "чтение буфера", "clipboard.read"),
                 {"tool": "clipboard", "len": len(text)})
    return text


def clipboard_read_raw() -> str:
    """Сырой буфер до лимита — для «запомни буфер» (Ф63): кладёт в
    память ТЕКСТ, а не отчёт о нём. Круг 34: секреты мимо (память живёт
    дольше чата), ImportError — честный с подсказкой, обрезка не молчит:
    честная пометка попадёт в память вместе с текстом."""
    try:
        pc = _pyperclip()
    except ImportError as e:
        raise RuntimeError(
            "нет модуля буфера: %s — venv\\Scripts\\pip install pyperclip "
            "(или скажи «проверь буфер», аптечка поставит сама)" % e)
    text = str(pc.paste() or "")
    guard.enforce(guard.check_secrets(text), {"tool": "clipboard_read_raw"})
    if len(text) <= config.CLIPBOARD_READ_LIMIT:
        guard.decide(guard.Verdict("LOW", "allow", "сырое чтение буфера",
                                   "clipboard.raw"),
                     {"tool": "clipboard", "len": len(text)})
        return text
    shown = text[:config.CLIPBOARD_READ_LIMIT]
    return shown + "\n[обрезано: запомнила первые %d из %d символов буфера]" % (
        config.CLIPBOARD_READ_LIMIT, len(text))


def clipboard_write_lines(lines: list) -> str:
    """«экран в буфер» (Ф62, день-10): надписи, прочитанные глазами, —
    в буфер обмена. Сколько ЦЕЛЫХ строк влезло в лимит — столько и
    едет: обрезка по границе строк, не по середине слова; не влезло
    ни одной или глаз не прочёл — честный отказ с числами.
    Круг 34: ведущие пробелы надписи — данные (отступы кода и таблиц),
    они больше не съедаются. Возвращает человекочитаемую сводку.
    """
    lines = [str(l) for l in (lines or []) if str(l).strip()]
    if not lines:
        raise ValueError("глаза не прочитали ни одной надписи")
    fit: list = []
    size = 0
    for line in lines:
        step = len(line) + (1 if fit else 0)   # разделитель строк
        if size + step > config.CLIPBOARD_LIMIT:
            break
        fit.append(line)
        size += step
    if not fit:
        return ("первая надпись длиннее лимита буфера (%d символов) — "
                "скопируй её по кускам: «прочитай экран» покажет список"
                % config.CLIPBOARD_LIMIT)
    guard.enforce(guard.check_secrets("\n".join(fit)), {"tool": "clipboard"})
    try:
        pc = _pyperclip()
    except ImportError as e:
        raise RuntimeError(
            "нет модуля буфера: %s — скажи «проверь буфер», аптечка "
            "поставит сама" % e)
    pc.copy("\n".join(fit))
    guard.decide(guard.Verdict("LOW", "allow", "надписи экрана в буфер",
                               "clipboard.lines"),
                 {"tool": "clipboard", "lines": len(fit), "len": size})
    if len(fit) == len(lines):
        return ("В буфере: все %d надписей (%d символов) — вставится "
                "по ctrl+v" % (len(fit), size))
    return ("В буфере: первые %d из %d надписей (%d символов) — лимит "
            "буфера %d; остальные покажу по «прочитай экран»"
            % (len(fit), len(lines), size, config.CLIPBOARD_LIMIT))


def clipboard_selftest() -> str:
    """«проверь буфер» (Ф65, день-10): живой тест по образцу «проверь
    камеру» — записала пробу, прочитала, сверила. Прежний буфер
    СОХРАНЯЕТСЯ и возвращается на место: проверка не имеет права
    съесть то, что Создатель держал в буфере (закон «не терять
    данные», фаза 1 аудита).

    Круг 34: pyperclip умеет только текст — нетекстовый (или пустой)
    буфер раньше «восстанавливался» пустой строкой, съедая картинку
    молча; теперь честный отчёт про нетекстовый буфер. Отказ вернуть
    чужое не проглатывается. При гонке чужие данные не показываются.
    """
    lines = ["ПРОВЕРКА БУФЕРА:"]
    try:
        pc = _pyperclip()
    except ImportError as e:
        lines.append("  · нет модуля pyperclip: %s" % e)
        lines.append("  · скажи «проверь модуль pyperclip» — аптечка "
                     "поставит сама, потом проверь буфер снова")
        return "\n".join(lines)
    try:
        saved = pc.paste()
    except Exception as e:
        return "\n".join(lines + ["  · прочитать буфер не смогла: %s" % e])
    saved_text = saved if isinstance(saved, str) and saved else ""
    probe = "марфа-проба-буфера-2411"
    restore_note = ""
    try:
        pc.copy(probe)
        back = str(pc.paste() or "")
    except Exception as e:
        lines.append("  · записать/прочитать не смогла: %s" % e)
        lines.append("  · сообщи архитектору — консоль покажет глубже")
        return "\n".join(lines)
    finally:
        # вернуть чужое: буфер Создателя не наша собственность
        try:
            pc.copy(saved_text)
        except Exception as e:
            restore_note = "  · ВЕРНУТЬ ПРЕЖНИЙ БУФЕР НЕ СМОГЛА: %s — " \
                           "проверь буфер (ctrl+v) руками" % e
    if not saved_text and (saved is None or not str(saved or "")):
        lines.append("  · в буфере был пустой или нетекстовый контент "
                     "(картинка/файлы) — pyperclip умеет только текст, "
                     "вернуть его я не могу: проверь буфер ctrl+v руками")
    if back == probe:
        lines.append("  · записала пробу и прочитала её обратно — буфер жив")
    else:
        # чужие данные в гонке не показываем (круг 34)
        lines.append("  · проба не совпала: записала «%s», прочитала "
                     "другое (%d символов) — расскажи архитектору"
                     % (probe, len(back)))
    if restore_note:
        lines.append(restore_note)
    lines.append("  · команды: «в буфер <текст>» — положить, "
                 "«что в буфере» — прочитать, «запомни буфер» — в память")
    return "\n".join(lines)


# ---------------------------------------------------------------
# Браузер (Библиотекарь 3.5 подхватит этот же провайдер)
# ---------------------------------------------------------------
# Провайдер подключается снаружи: тесты ставят заглушку, прод — реальный движок.
_search_provider: Optional[Callable[[str], list[dict]]] = None


def set_search_provider(provider: Callable[[str], list[dict]]) -> None:
    global _search_provider
    _search_provider = provider


def _ddg_provider(query: str) -> list[dict]:
    """Минимальный провайдер DuckDuckGo (HTML-эндпоинт). На Z440 требует сеть.
    Круг 34: ответ читается с потолком (response-bomb не тащится в RAM),
    entities разэкранируются, жирные заголовки разбираются тег-классом,
    редирект-ссылки DDG распаковываются в настоящий адрес."""
    url = "https://html.duckduckgo.com/html/?q=" + urllib.parse.quote(query)
    req = urllib.request.Request(url, headers={"User-Agent": "marfa/1.0 (local agent)"})
    with urllib.request.urlopen(req, timeout=15) as resp:  # noqa: S310 — URL фиксированный
        html_body = resp.read(MAX_SEARCH_BYTES + 1).decode("utf-8", errors="replace")
    results: list[dict] = []
    for block in html_body.split('class="result__body"')[1:MAX_SEARCH_RESULTS + 1]:
        title, link = "", ""
        if 'class="result__a"' in block and "</a>" in block:
            chunk = block.split('class="result__a"')[1].split("</a>")[0]
            m = re.search(r'href="([^"]*)"', chunk)
            if m:
                link = _html.unescape(m.group(1))
            # заголовок: всё после закрывающего '>' тега <a>, теги долой
            raw_title = chunk.split(">", 1)[-1] if ">" in chunk else ""
            title = _html.unescape(re.sub(r"<[^>]+>", "", raw_title)).strip()
            if link.startswith("//"):
                link = "https:" + link
            qs = urllib.parse.parse_qs(urllib.parse.urlparse(link).query)
            if "uddg" in qs:                      # редирект DDG → настоящий URL
                link = urllib.parse.unquote(qs["uddg"][0])
        if title or link:
            results.append({"title": title, "url": link})
    return results


def _sanitize_results(results) -> list[dict]:
    """Валидация результатов провайдера + СТРАЖ на недоверенном
    контенте (круг 34): заголовки и ссылки веб-страницы едут в мозг
    только чистыми от инъекции — «ignore previous instructions…» со
    страницы не становится инструкцией."""
    if not isinstance(results, list):
        raise RuntimeError("провайдер вернул не-список (%s)" % type(results).__name__)
    clean: list[dict] = []
    for item in results[:MAX_SEARCH_RESULTS]:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "")
        link = str(item.get("url") or "")
        guard.enforce(guard.check_injection(title + " " + link),
                      {"tool": "browser_search.result"})
        clean.append({"title": title, "url": link})
    return clean


def browser_search(query: str, provider: Optional[Callable[[str], list[dict]]] = None) -> str:
    """Поиск в интернете. Без провайдера и без сети — честная ошибка, не выдумка.

    M1 аудита: кривой запрос (None/не-строка) и падение провайдера не
    должны долетать до панели 500-й. Законный отказ СТРАЖА (PermissionError)
    пропускаем наружу — _act превратит его в честный отказ.
    Круг 34: секреты не уезжают в поисковик с запросом; пустой запрос —
    подсказка, а не «ничего не найдено»; оператор ! — отказ с контекстом
    инструмента в журнале."""
    query = str(query or "")
    if not query.strip():
        return "что искать? скажи тему — «найди в сети <тема>»"
    try:
        guard.enforce(guard.check_injection(query), {"tool": "browser_search"})
        guard.enforce(guard.check_secrets(query), {"tool": "browser_search.query"})
        if query.strip().startswith("!"):  # запрет операторов DDG-фильтров через руки
            guard.enforce(guard.Verdict("MEDIUM", "deny", "оператор ! в запросе",
                                        "search.bang"),
                          {"tool": "browser_search"})
        prov = provider or _search_provider or _ddg_provider
        results = prov(query)
    except PermissionError:
        raise                        # отказ СТРАЖА — законный путь отказа
    except Exception as exc:        # noqa: BLE001 — сеть/провайдер может быть чем угодно
        return f"поиск недоступен: {type(exc).__name__}: {exc}"
    results = _sanitize_results(results)
    if not results:
        return "ничего не найдено"
    guard.decide(guard.Verdict("LOW", "allow", "поиск выполнен", "search.ok"),
                 {"tool": "browser_search", "results": len(results)})
    return json.dumps(results, ensure_ascii=False, indent=1)
