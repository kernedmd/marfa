# -*- coding: utf-8 -*-
"""core/creator_gate.py — КАЛИТКА СОЗДАТЕЛЯ («вичка по-взрослому», v1.0).

Кодовое слово живёт ТОЛЬКО в C:\\Marfa\\.env строкой
    MARFA_CODEWORD=тайное-слово
В код и в чат оно не попадает никогда (Ф105). Проверка идёт в Python
ДО того, как проснётся мозг: мозг не может выболтать то, чего не видел.

Что даёт калитка — НЕ «любую команду», а очерченный список:
    <слово> статус          полный осмотр дома (мозг, RAM, диск, git)
    <слово> тесты           прогон батареи тестов, хвост вывода
    <слово> хвост <имя>     последние строки файла из logs/ (по части имени)
    <слово>                 без команды — подсказка (только после проверки)

Правила:
  - слово < 4 символов считается неустановленным: калитка закрыта;
  - сравнение регистрозависимое и по границе слова: «словостатус» не срабатывает;
  - сравнение постоянного времени (hmac.compare_digest) — по времени не подобрать;
  - неверное слово ничего не меняет и ничего не выдаёт: дом молчит, путь обычный;
  - сообщение со словом НИКОГДА не уходит мозгу — диспетчер отвечает сам.

Запуск не нужен: модуль зовёт диспетчер (core/agent.py) до быстрых команд.
"""
from __future__ import annotations

import hmac
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from core import config

ENV_KEY = "MARFA_CODEWORD"
MIN_LEN = 4                 # короче — не секрет, а пароль из трёх букв
TAIL_LINES = 20             # сколько строк хвоста показывать
TEST_TIMEOUT_SEC = 600      # батарея на Z440 идёт ~25 c, запас на холодный старт
GIT_TIMEOUT_SEC = 10
PROBE_TIMEOUT_SEC = 3


# ---------------------------------------------------------------
# .env (паттерн architect_oncall: utf-8-sig съедает BOM от Блокнота)
# ---------------------------------------------------------------
def load_env() -> dict:
    """Прочитать .env дома в словарь. Нет файла — пусто, калитка закрыта.
    Путь берём в момент вызова: калитка следует за config.HOME_DIR.

    H3 аудита: без exists()-предпроверки — файл мог исчезнуть между
    взглядом и чтением (антивирус, git checkout); OSError — честное
    «калитка закрыта», а не исключение в чат."""
    env: dict = {}
    env_file = config.HOME_DIR / ".env"
    try:
        raw_text = env_file.read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return env
    for raw in raw_text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def _codeword() -> str:
    """Кодовое слово или '' — если не задано/короткое."""
    word = (load_env().get(ENV_KEY) or "").strip()
    return word if len(word) >= MIN_LEN else ""


# ---------------------------------------------------------------
# Команды за калиткой (только чтение, кроме тестов; ничего вне дома)
# ---------------------------------------------------------------
def _cmd_status() -> str:
    """Полный осмотр: мозг, панель, RAM, диск, git, python."""
    lines = []

    try:  # мозг
        with urllib.request.urlopen(config.BRAIN_URL + "/health", timeout=PROBE_TIMEOUT_SEC) as r:
            lines.append("мозг: жив (" + config.BRAIN_URL + ")" if r.status == 200
                         else "мозг: код " + str(r.status))
    except Exception:
        lines.append("мозг: не отвечает")

    try:  # панель
        url = "http://127.0.0.1:%d/health" % config.PORT_WEB
        with urllib.request.urlopen(url, timeout=PROBE_TIMEOUT_SEC) as r:
            lines.append("панель: жива (%d)" % config.PORT_WEB if r.status == 200
                         else "панель: код " + str(r.status))
    except Exception:
        lines.append("панель: не отвечает")

    try:  # RAM — psutil есть на Z440; нет пакета — строку пропускаем
        import psutil
        vm = psutil.virtual_memory()
        lines.append("RAM: %.1f / %.1f ГБ (%.1f%%)" % (
            (vm.total - vm.available) / 2**30, vm.total / 2**30,
            100.0 * vm.used / vm.total))
    except Exception:
        lines.append("RAM: psutil недоступен")

    try:  # диск
        du = shutil.disk_usage(str(config.HOME_DIR))
        lines.append("диск: свободно %.1f ГБ" % (du.free / 2**30))
    except Exception:
        lines.append("диск: не выяснить")

    try:  # git: последняя цена дома и чистота дерева
        head = subprocess.run(
            ["git", "log", "-1", "--oneline"], cwd=str(config.HOME_DIR),
            capture_output=True, text=True, timeout=GIT_TIMEOUT_SEC)
        dirty = subprocess.run(
            ["git", "status", "--porcelain"], cwd=str(config.HOME_DIR),
            capture_output=True, text=True, timeout=GIT_TIMEOUT_SEC)
        n_dirty = len([l for l in (dirty.stdout or "").splitlines() if l.strip()])
        lines.append("git: " + (head.stdout or "").strip())
        lines.append("дерево: " + ("чистое" if n_dirty == 0
                                   else "незакоммичено файлов: %d" % n_dirty))
    except Exception:
        lines.append("git: недоступен")

    lines.append("python: " + sys.version.split()[0])
    return "Полный осмотр дома:\n" + "\n".join("— " + l for l in lines)


def _cmd_tests() -> str:
    """Прогон батареи: venv-интерпретатором, с таймаутом, показать хвост.

    N7 аудита: pytest не установлен — это НЕ «красные тесты», а «не
    запускались»; диагноз не врёт, лечение — одна команда."""
    t0 = time.time()
    try:
        r = subprocess.run(
            [sys.executable, "-m", "pytest", "tests", "-q"],
            cwd=str(config.HOME_DIR), capture_output=True, text=True,
            timeout=TEST_TIMEOUT_SEC)
        if r.returncode != 0 and "No module named" in (r.stderr or "") \
                and "pytest" in (r.stderr or ""):
            return ("тесты НЕ ЗАПУСКАЛИСЬ: в этом интерпретаторе нет pytest "
                    "(%s). Это не красные тесты. Поставь: "
                    "venv\\Scripts\\pip install pytest" % sys.executable)
        tail = "\n".join((r.stdout or "").splitlines()[-TAIL_LINES:])
        verdict = "БАТАРЕЯ ЗЕЛЁНАЯ" if r.returncode == 0 else "ЕСТЬ КРАСНЫЕ ТЕСТЫ (код %d)" % r.returncode
        return "%s за %.0f с. Хвост вывода:\n%s" % (verdict, time.time() - t0, tail)
    except subprocess.TimeoutExpired:
        return "тесты не уложились в %d с — где-то зависло, смотри руками" % TEST_TIMEOUT_SEC
    except Exception as e:
        return "тесты не запустились: " + str(e)


def _cmd_tail(name: str) -> str:
    """Хвост файла из logs/ (по части имени, свежайший) + НЕобязательный
    фильтр по подстроке (№26 роадмапа): «хвост brain ошибка» — только
    строки с «ошибка» из свежайшего brain-лога. Путь наружу невозможен:
    ищем только СРЕДИ файлов logs/, а не склеиваем путь из строки.

    Первое слово после «хвост» — имя файла, остальное — подстрока
    фильтра (регистр не важен). Фильтр ничего не нашёл — честно
    говорим сколько строк смотрели: «в последних N строках нет».
    """
    name = (name or "").strip()
    if not name:
        return ("укажи имя: <слово> хвост <часть имени из logs/> "
                "[<подстрока>]")
    parts = name.split(None, 1)
    file_part = parts[0]
    needle = parts[1].strip() if len(parts) > 1 else ""
    root = Path(config.LOGS_DIR)
    if not root.exists():
        return "logs/ ещё нет — дому нечего показывать"
    matches = [p for p in root.rglob("*")
               if p.is_file() and file_part.lower() in p.name.lower()]
    if not matches:
        return ("в logs/ нет файла с таким именем"
                + (" (фильтр «%s» даже не понадобился)" % needle
                   if needle else ""))
    newest = max(matches, key=lambda p: p.stat().st_mtime)
    try:  # читаем только конец файла: большие логи не тащим целиком
        with newest.open("rb") as f:
            f.seek(0, 2)
            size = f.tell()
            f.seek(max(0, size - 64 * 1024))
            chunk = f.read().decode("utf-8", errors="replace")
        tail = chunk.splitlines()[-TAIL_LINES:]
        if needle:
            low = needle.lower()
            picked = [l for l in tail if low in l.lower()]
            if not picked:
                return ("%s: в последних %d строках нет «%s» — фильтр "
                        "честен, совпадений ноль"
                        % (newest.relative_to(root), len(tail), needle))
            return ("%s (последние %d строк, найдено %d с «%s»):\n%s"
                    % (newest.relative_to(root), len(tail), len(picked),
                       needle, "\n".join(picked)))
        return "%s (последние строки):\n%s" % (newest.relative_to(root),
                                               "\n".join(tail))
    except Exception as e:
        return "не смог прочитать: " + str(e)


HELP = ("калитка Создателя открыта. Команды: статус | тесты | "
        "хвост <часть имени из logs/> [<подстрока> — фильтр строк, №26>."
        " Слово действует только в этом сообщении.")


# ---------------------------------------------------------------
# Калитка
# ---------------------------------------------------------------
def check(user_text: str):
    """Проверить сообщение на кодовое слово.
    Возврат (True, ответ) — сообщение опознано как голос Создателя, диспетчер
    отвечает сам и в мозг текст НЕ уходит. (False, None) — путь обычный."""
    word = _codeword()
    if not word:
        return False, None
    text = (user_text or "").strip()
    if not text:
        return False, None
    if not hmac.compare_digest(text[:len(word)].encode("utf-8"),
                               word.encode("utf-8")):  # bytes: кириллицу str не ест
        return False, None
    rest = text[len(word):]
    if rest and not rest[0].isspace():   # «словостатус» — не калитка
        return False, None
    command = rest.strip().lower()

    if command.startswith("статус"):
        return True, _cmd_status()
    if command.startswith("тест"):
        return True, _cmd_tests()
    if command.startswith("хвост"):
        return True, _cmd_tail(command[len("хвост"):].strip())
    return True, HELP
