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
    data = p.read_bytes()
    if len(data) > MAX_READ_BYTES:
        raise ValueError(f"файл больше {MAX_READ_BYTES} байт: {p.name}")
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
    proc = subprocess.run(
        [sys.executable, "-I", "-c", code],          # -I: без site/user-пакетов — изоляция
        capture_output=True, text=True, timeout=timeout,
        cwd=str(config.HOME_DIR), env=env,
    )
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
    """Поиск в интернете. Без провайдера и без сети — честная ошибка, не выдумка."""
    guard.enforce(guard.check_injection(query), {"tool": "browser_search"})
    if query.strip().startswith("!"):  # запрет операторов DDG-фильтров через руки
        guard.enforce(guard.Verdict("MEDIUM", "deny", "оператор ! в запросе", "search.bang"))
    prov = provider or _search_provider or _ddg_provider
    try:
        results = prov(query)
    except Exception as exc:  # noqa: BLE001 — сеть может быть чем угодно
        return f"поиск недоступен: {type(exc).__name__}: {exc}"
    if not results:
        return "ничего не найдено"
    return json.dumps(results, ensure_ascii=False, indent=1)
