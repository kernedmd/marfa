# -*- coding: utf-8 -*-
"""core/hands.py — РУКИ МАРФЫ (ТЗ 3.3): чистый Python, без магии.

Инструменты: read_file, write_file, run_python, browser_search, check_brackets.
Правило: любое потенциально опасное действие — сначала через СТРАЖ (3.7).
Всё, что разрешено, пишется в hash-chain лог аудита.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Callable, Optional

from core import config
from safety import guard

# Ограничения рук (проще простить, чем пережить)
MAX_READ_BYTES = 2 * 1024 * 1024          # 2 МБ на чтение
MAX_RUN_SECONDS = 20                      # таймаут run_python
MAX_SEARCH_RESULTS = 5


# ---------------------------------------------------------------
# Файлы
# ---------------------------------------------------------------
def read_file(path: str | Path) -> str:
    """Чтение файла внутри дома. Вне дома — СТРАЖ откажет (HIGH).
    Читается ТОЛЬКО путь, который резолвнул СТРАЖ — расхождение исключено."""
    p = guard.resolve_path(path)
    guard.enforce(guard.check_path(p), {"tool": "read_file"})
    # K2 аудита: размер — ДО чтения. 18-гигабайтный файл весов внутри дома
    # проходит калитку стража, и read_bytes() тащил его в RAM целиком
    size = p.stat().st_size
    if size > MAX_READ_BYTES:
        raise ValueError(f"файл больше {MAX_READ_BYTES} байт: {p.name}")
    data = p.read_bytes()
    return data.decode("utf-8", errors="replace")


def write_file(path: str | Path, content: str) -> str:
    """Запись файла внутри дома. Родитель создаётся. СТРАЖ проверяет и путь, и содержимое."""
    p = guard.resolve_path(path)
    guard.enforce(guard.check_path(p), {"tool": "write_file"})
    guard.enforce(guard.check_secrets(content), {"tool": "write_file"})  # канарейки не утекают
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return f"записано: {p} ({len(content)} символов)"


# ---------------------------------------------------------------
# Запуск Python-кода в изоляции
# ---------------------------------------------------------------
def run_python(code: str, timeout: int = MAX_RUN_SECONDS) -> str:
    """Короткий Python-код в отдельном процессе. Опасные паттерны отвергает СТРАЖ."""
    guard.enforce(guard.check_code(code), {"tool": "run_python"})
    env = {k: v for k, v in os.environ.items() if not k.startswith(("PYTHON", "MARFA"))}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    # K3 аудита: TimeoutExpired — не OSError, долетал до панели 500-й.
    # Ловим здесь и возвращаем честный текст: код прерван, дом жив.
    try:
        proc = subprocess.run(
            [sys.executable, "-I", "-c", code],          # -I: без site/user-пакетов — изоляция
            capture_output=True, text=True, timeout=timeout,
            cwd=str(config.HOME_DIR), env=env,
        )
    except subprocess.TimeoutExpired:
        return f"ошибка: код выполнялся дольше {timeout} с, прерван"
    except OSError as e:            # питон не поднялся — тоже честный текст
        return f"ошибка запуска: {e}"
    out = proc.stdout.strip()
    err = proc.stderr.strip()
    if proc.returncode != 0:
        return f"ошибка ({proc.returncode}): {err[:2000]}"
    return out if out else "(пусто)"


# ---------------------------------------------------------------
# Скобки
# ---------------------------------------------------------------
_PAIRS = {")": "(", "]": "[", "}": "{"}


def check_brackets(text: str) -> str:
    """Проверка баланса (), [], {}. Возвращает человекочитаемый вердикт."""
    stack: list[str] = []
    for i, ch in enumerate(text):
        if ch in "([{":
            stack.append(ch)
        elif ch in _PAIRS:
            if not stack or stack[-1] != _PAIRS[ch]:
                return f"НЕСБАЛАНСИРОВАНО: неожиданная '{ch}' на позиции {i}"
            stack.pop()
    if stack:
        return f"НЕСБАЛАНСИРОВАНО: не закрыты {', '.join(stack)}"
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
    свалка), секреты (канарейки, ключи) мимо — буфер живёт в системе
    дольше чата и вставится куда угодно. Отказ СТРАЖА — PermissionError
    (как у файлов), нет модуля — RuntimeError с командой установки.
    Возвращает человекочитаемую сводку.
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
    return ("В буфере обмена: %d символов. Вставится по ctrl+v — "
            "сам или скажи «руки клавиши ctrl+v»" % len(text))


def clipboard_read() -> str:
    """«что в буфере» (Ф63, день-10): прочитать буфер обмена в чат.

    Границы: лимит CLIPBOARD_READ_LIMIT (показать — не значит
    притащить всё, что туда скопировали), пустой буфер — честное
    «пусто», а не выдумка. Секреты НЕ проверяем на чтении: буфер
    читает Создатель про СВОЙ текст (проверка нужна была на записи —
    туда секреты не кладут); показ живёт секунду в чате.
    Возвращает текст или поднимает RuntimeError (нет модуля) —
    вызывающий покажет честный отказ с аптечкой.
    """
    try:
        pc = _pyperclip()
    except ImportError as e:
        raise RuntimeError(
            "нет модуля буфера: %s — venv\\Scripts\\pip install pyperclip "
            "(или скажи «проверь буфер», аптечка поставит сама)" % e)
    text = str(pc.paste() or "")
    if not text.strip():
        return "буфер обмена пуст"
    if len(text) > config.CLIPBOARD_READ_LIMIT:
        shown = text[:config.CLIPBOARD_READ_LIMIT]
        cut = "…\n(показала первые %d из %d символов — буфер длинный)"
        return shown.rstrip() + cut % (config.CLIPBOARD_READ_LIMIT, len(text))
    return text


def clipboard_read_raw() -> str:
    """Сырой буфер до лимита — без чатовой приписки про обрезку
    (Ф63): «запомни буфер» кладёт в память ТЕКСТ, а не отчёт о нём."""
    pc = _pyperclip()
    return str(pc.paste() or "")[:config.CLIPBOARD_READ_LIMIT]


def clipboard_write_lines(lines: list) -> str:
    """«экран в буфер» (Ф62, день-10): надписи, прочитанные глазами, —
    в буфер обмена. Сколько ЦЕЛЫХ строк влезло в лимит — столько и
    едет: обрезка по границе строк, не по середине слова; не влезло
    ни одной или глаз не прочёл — честный отказ с числами.
    Возвращает человекочитаемую сводку (швы pyperclip — как у записи).
    """
    lines = [str(l).strip() for l in lines if str(l).strip()]
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
    probe = "марфа-проба-буфера-2411"
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
            if saved is not None:
                pc.copy(saved)
        except Exception:
            pass
    if back == probe:
        lines.append("  · записала пробу и прочитала её обратно — буфер жив")
    else:
        lines.append("  · проба не совпала: записала «%s», прочитала «%s» — "
                     "расскажи архитектору" % (probe, back[:80]))
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
    """Минимальный провайдер DuckDuckGo (HTML-эндпоинт). На Z440 требует сеть."""
    url = "https://html.duckduckgo.com/html/?q=" + urllib.parse.quote(query)
    req = urllib.request.Request(url, headers={"User-Agent": "marfa/1.0 (local agent)"})
    with urllib.request.urlopen(req, timeout=15) as resp:  # noqa: S310 — URL фиксированный
        html = resp.read().decode("utf-8", errors="replace")
    results: list[dict] = []
    for block in html.split('class="result__body"')[1:MAX_SEARCH_RESULTS + 1]:
        title, link = "", ""
        if 'class="result__a"' in block and "</a>" in block:
            chunk = block.split('class="result__a"')[1].split("</a>")[0]
            if 'href="' in chunk:
                link = chunk.split('href="')[1].split('"')[0]
            title = chunk.split(">")[-1].strip()
        if title or link:
            results.append({"title": title, "url": link})
    return results


def browser_search(query: str, provider: Optional[Callable[[str], list[dict]]] = None) -> str:
    """Поиск в интернете. Без провайдера и без сети — честная ошибка, не выдумка.

    M1 аудита: кривой запрос (None/не-строка) и падение провайдера не
    должны долетать до панели 500-й. Законный отказ СТРАЖА (PermissionError)
    пропускаем наружу — _act превратит его в честный отказ."""
    query = str(query or "")
    try:
        guard.enforce(guard.check_injection(query), {"tool": "browser_search"})
        if query.strip().startswith("!"):  # запрет операторов DDG-фильтров через руки
            guard.enforce(guard.Verdict("MEDIUM", "deny", "оператор ! в запросе", "search.bang"))
        prov = provider or _search_provider or _ddg_provider
        results = prov(query)
    except PermissionError:
        raise                        # отказ СТРАЖА — законный путь отказа
    except Exception as exc:        # noqa: BLE001 — сеть/провайдер может быть чем угодно
        return f"поиск недоступен: {type(exc).__name__}: {exc}"
    if not results:
        return "ничего не найдено"
    return json.dumps(results, ensure_ascii=False, indent=1)
