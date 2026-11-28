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
import json
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from typing import Optional

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
        "хвост <часть имени из logs/> [<подстрока> — фильтр строк, №26>] | "
        "новое слово: <новое> — смена кодового слова (Ф47, два шага) | "
        "подтверждаю — второй шаг смены. Слово действует только в этом "
        "сообщении.")


# ---------------------------------------------------------------
# Ф47 «РОТАЦИЯ КОДОВОГО СЛОВА» (день-9): смена двумя шагами.
# Шаг 1: «<старое> новое слово: <новое>» — дом запоминает намерение
#        (живёт 10 минут) и просит подтверждение;
# Шаг 2: «<старое> подтверждаю» — сверка намерения, перезапись .env.
# Слово в ответах НИКОГДА не называется — ни старое, ни новое (Ф105);
# сообщение со словом до мозга не доходит, калитка перечитывает .env
# на каждом сообщении — перезапуск дома не нужен.
# ---------------------------------------------------------------
def _rotate_file() -> Path:
    """data/gate_rotate.json — ЛЕНИВО от DATA_DIR (закон песочницы)."""
    return Path(config.DATA_DIR) / "gate_rotate.json"


def _load_pending() -> Optional[dict]:
    try:
        rec = json.loads(_rotate_file().read_text(encoding="utf-8"))
        return rec if isinstance(rec, dict) else None
    except (OSError, ValueError):
        return None


def _save_pending(rec: Optional[dict]) -> None:
    try:
        _rotate_file().parent.mkdir(parents=True, exist_ok=True)
        if rec is None:
            _rotate_file().unlink(missing_ok=True)
        else:
            _rotate_file().write_text(
                json.dumps(rec, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass  # намерение не записалось — подтверждение честно не найдётся


def _cmd_rotate_new(payload: str) -> str:
    """Шаг 1: «новое слово: X» — проверить и запомнить намерение."""
    new_word = payload.lstrip(":-— ").strip()
    if not new_word:
        return ("напиши так: «…новое слово: <новое слово>» — и вторым "
                "сообщением подтверди (придёт подсказка)")
    if len(new_word) < MIN_LEN:
        return ("новое слово короче %d символов — это не секрет, а пароль "
                "из трёх букв; придумай подлиннее" % MIN_LEN)
    if any(c.isspace() for c in new_word):
        return ("в новом слове есть пробел — калитка режет сообщение по "
                "границе слова, пробелы её ломают; одним словом, пожалуйста")
    _save_pending({"new": new_word, "ts": time.time()})
    return ("намерение запомнила. Подтверди вторым сообщением: пришли "
            "СЕЙЧАС ДЕЙСТВУЮЩЕЕ кодовое слово и добавь «подтверждаю». "
            "У тебя %d минут" % (config.GATE_ROTATE_TTL_SEC // 60))


def _rewrite_env(new_word: str) -> bool:
    """Перезаписать .env: чужие строки живы, строка слова — новая.
    Файла не было — создаём только со словом (другие ключи не выдумываем)."""
    env_file = config.HOME_DIR / ".env"
    lines: list[str] = []
    try:
        lines = env_file.read_text(encoding="utf-8-sig",
                                   errors="replace").splitlines()
    except OSError:
        lines = []
    replaced = False
    out: list[str] = []
    for raw in lines:
        if raw.strip().startswith(ENV_KEY + "="):
            out.append("%s=%s" % (ENV_KEY, new_word))
            replaced = True
        else:
            out.append(raw)
    if not replaced:
        out.append("%s=%s" % (ENV_KEY, new_word))
    try:
        env_file.write_text("\n".join(out) + "\n", encoding="utf-8")
        return True
    except OSError:
        return False


def _cmd_rotate_confirm() -> str:
    """Шаг 2: «подтверждаю» — сверить намерение и сменить слово."""
    pending = _load_pending()
    if not pending or not str(pending.get("new") or "").strip():
        return ("нечего подтверждать: смену слова не начинали. Начни — "
                "«…новое слово: <новое>» за калиткой")
    try:
        age = time.time() - float(pending.get("ts", 0))
    except (TypeError, ValueError):
        age = 1e9
    if age > config.GATE_ROTATE_TTL_SEC:
        _save_pending(None)
        return ("время подтверждения вышло (лимит %d минут) — намерение "
                "снято, слово НЕ менялось. Начни заново"
                % (config.GATE_ROTATE_TTL_SEC // 60))
    if not _rewrite_env(str(pending["new"]).strip()):
        return (".env не записался (диск? права?) — слово НЕ менялось, "
                "намерение живёт; попробуй ещё раз или скажи архитектору")
    _save_pending(None)
    return ("кодовое слово сменено: старое больше не открывает калитку, "
            "новое — работает сразу (калитка перечитывает .env на каждом "
            "сообщении, перезапуск не нужен). В чате я его не назову — "
            "оно теперь наша тайна")


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

    # КРУГ 33 (аудит И., К6): команда за словом — в броне. Падение
    # исполнения больше НЕ роняет check (а значит не роняет fail-closed
    # диспетчера): слово опознано — ход уже голос Создателя, честный
    # текст вместо исключения. Слово в мозг и в журнал не уезжает.
    try:
        if command.startswith("статус"):
            return True, _cmd_status()
        if command.startswith("тест"):
            return True, _cmd_tests()
        if command.startswith("хвост"):
            return True, _cmd_tail(command[len("хвост"):].strip())
        if command.startswith("новое слово"):
            return True, _cmd_rotate_new(command[len("новое слово"):].strip())
        if command.startswith("подтверждаю"):
            return True, _cmd_rotate_confirm()
        return True, HELP
    except Exception as e:
        return True, ("калитка споткнулась (мой сбой, не твой): %s: %s — "
                      "команда за словом не исполнилась, само слово в мозг "
                      "не уехало. Повтори через минуту."
                      % (type(e).__name__, e))
