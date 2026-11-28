# -*- coding: utf-8 -*-
"""core/creator_gate.py — КАЛИТКА СОЗДАТЕЛЯ («вичка по-взрослому», v1.1).

Кодовое слово живёт ТОЛЬКО в C:\\Marfa\\.env строкой
    MARFA_CODEWORD=тайное-слово
В код и в чат оно не попадает никогда (Ф105). Проверка идёт в Python
ДО того, как проснётся мозг: мозг не может выболтать то, чего не видел.

Что даёт калитка — очерченный список:
    <слово> статус          полный осмотр дома (мозг, RAM, диск, git)
    <слово> тесты           прогон батареи тестов, хвост вывода
    <слово> хвост <имя>     последние строки файла из logs/ (по части имени)
    <слово> новое слово: X  смена кодового слова (Ф47, два шага)
    <слово> подтверждаю     второй шаг смены
    <слово> включи/выключи моторику       — разрешения Создателя
    <слово> разреши/запрети внедрять себя   (раньше лежали снаружи:
    <слово> следи за экраном / не следи     аудит 284 — сейф стоял не
                                            на той двери)
    <слово>                 без команды — подсказка (только после проверки)

Правила:
  - слово < 4 символов считается неустановленным: калитка закрыта;
  - сравнение регистрозависимое и по границе слова: «словостатус» не
    срабатывает; ЗАПЯТАЯ после слова — законная граница («слово, статус»);
  - обращение «Марфа, <слово> статус» снимается до проверки (аудит 286):
    естественная речь Создателя не должна увозить слово в мозг;
  - сравнение постоянного времени (hmac.compare_digest) — по времени
    не подобрать; промах на одну букву ловится и тормозится попытками
    (аудит 285/297): перебор в чате — не путь в дом;
  - неверное слово ничего не меняет и ничего не выдаёт: дом молчит,
    путь обычный (кроме промаха на букву — там честный локальный ответ
    без слова и без мозга);
  - сообщение со словом НИКОГДА не уходит мозгу — диспетчер отвечает сам.

КРУГ 36 (аудит Создателя, 281–305): ротация больше не СНИЖАЕТ регистр
нового слова (payload режется с исходной строки, а не с lowercased —
аудит 281: калитка закрывалась на ровном месте); намерение ротации
лежит в data/ ШИФРОВАННЫМ (ключ — в корне дома, куда мозгу дорога
закрыта замком Ф118: путь без подпапки — отказ; открытый текст слова
в читаемой мозгом папке — нарушенное обещание «мозг не видел слова»,
аудит 282); .env перезаписывается атомарно (tmp + os.replace — крах
посередине больше не может обрезать файл и запереть Создателя наружу,
аудит 287); коды батареи 4/5 — «тесты не нашлись/не собрались», а не
«КРАСНЫЕ» (урок дня-18, который repair выучил, а калитка — нет,
аудит 288); RAM считается одной арифметикой (аудит 294), не-репозиторий
не выдаёт себя за «чистое дерево» (295), хвост бронируется от исчезающих
файлов (300), время намерения в будущем — снятое намерение (302),
словарные слова и кавычки отбиваются на входе (297/298), события калитки
(команды, ротации, промахи, попытки) пишутся в logs/gate_log.jsonl без
самого слова (289), а разрешения моторики/внедрения/слежения переехали
ЗА слово (284): «разреши внедрять себя» и «следи за экраном» больше не
лежат снаружи калитки.

Запуск не нужен: модуль зовёт диспетчер (core/agent.py) до быстрых команд.
"""
from __future__ import annotations

import base64
import datetime as dt
import hashlib
import hmac
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from typing import Optional

from core import config, loghygiene

ENV_KEY = "MARFA_CODEWORD"
MIN_LEN = 4                 # короче — не секрет, а пароль из трёх букв
TAIL_LINES = 20             # сколько строк хвоста показывать
TEST_TIMEOUT_SEC = 600      # батарея на Z440 идёт ~25 c, запас на холодный старт
GIT_TIMEOUT_SEC = 10
PROBE_TIMEOUT_SEC = 3

# Промах на одну букву (аудит 285/297): ловим, отвечаем локально
# (слово и промах не уезжают мозгу), считаем попытки, тормозим серию.
_NEAR_MISS_DISTANCE = 1
_NEAR_MISS_MIN_WORD = 6     # короткие слова ловить дистанцией — ложные срабатывания
_ATTEMPTS_WINDOW_SEC = 600
_ATTEMPTS_MAX = 5

# Словарные слова и имена — не секрет (аудит 297: «нет проверки на
# словарное слово» — перебор в чате начинался бы со словаря)
_TRIVIAL_WORDS = frozenset((
    "марфа", "марфушка", "марфенька", "пароль", "пароля", "секрет",
    "слово", "илья", "создатель", "привет", "спасибо", "люблю",
    "дом", "домашний", "qwerty", "password", "12345", "123456",
))


# ---------------------------------------------------------------
# Журнал калитки (аудит 289): кто и когда спрашивал, что менялось.
# НИКОГДА — само слово, payload команд или текст промаха: журнал
# читается хвостом за словом, но пишется и без него.
# ---------------------------------------------------------------
def _gate_log(event: str, **fields) -> None:
    try:
        rec = {"ts": dt.datetime.now().isoformat(timespec="seconds"),
               "event": event}
        rec.update(fields)
        p = Path(config.LOGS_DIR) / "gate_log.jsonl"
        loghygiene.append_line(p, json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        pass   # журнал — не орган дыхания; калитка живёт дальше


# ---------------------------------------------------------------
# .env (паттерн architect_oncall: utf-8-sig съедает BOM от Блокнота)
# ---------------------------------------------------------------
def load_env() -> dict:
    """Прочитать .env дома в словарь. Нет файла — пусто, калитка закрыта.
    Путь берём в момент вызова: калитка следует за config.HOME_DIR.

    H3 аудита: без exists()-предпроверки — файл мог исчезнуть между
    взглядом и чтением (антивирус, git checkout); OSError — честное
    «калитка закрыта», а не исключение в чат.

    Аудит 291: «export MARFA_CODEWORD=…» — ключ без «export » (форма
    терминала не запирает калитку молча)."""
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
        k = k.strip()
        if k.lower().startswith("export "):     # аудит 291
            k = k[len("export "):].strip()
        env[k] = v.strip().strip('"').strip("'")
    return env


def _codeword() -> str:
    """Кодовое слово или '' — если не задано/короткое.

    Аудит 290: инлайн-комментарий «MARFA_CODEWORD=слово # моё» больше
    не запирает калитку молча — « #…» срезается (пробел внутри слова
    невозможен по правилам ротации, так что срез безопасен)."""
    word = (load_env().get(ENV_KEY) or "").strip()
    if " #" in word:
        word = word[:word.index(" #")].rstrip()
    return word if len(word) >= MIN_LEN else ""


def codeword() -> str:
    """Публичный шов для СТРАЖА (круг 34): check_secrets не пускает
    кодовое слово наружу (буфер, файлы, поиск) — стражу нужен доступ
    к слову без знания внутренностей калитки."""
    return _codeword()


# ---------------------------------------------------------------
# Промах на букву: дистанция, попытки, тормоз (аудит 285/297)
# ---------------------------------------------------------------
def _edit_distance(a: str, b: str) -> int:
    """Левенштейн с ранним выходом (слова короткие, матрица мала)."""
    if abs(len(a) - len(b)) > 2:
        return 3
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1,
                           prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def _first_token(text: str) -> str:
    """Первое слово сообщения — кандидат на промах по слову."""
    t = (text or "").strip()
    m = re.match(r"^[^\s,.!?:;]+", t)
    return (m.group(0) if m else t).lower()


def _attempts_file() -> Path:
    return Path(config.DATA_DIR) / "gate_attempts.json"


def _count_attempt() -> int:
    """Записать промах и вернуть, сколько их в окне. Диск молчит —
    считаем всё равно (лучше перетормозить, чем впустить перебор)."""
    now = time.time()
    tries: list = []
    try:
        raw = json.loads(_attempts_file().read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            tries = [t for t in (raw.get("ts") or [])
                     if isinstance(t, (int, float))
                     and now - float(t) < _ATTEMPTS_WINDOW_SEC]
    except (OSError, ValueError):
        tries = []
    tries.append(now)
    try:
        _attempts_file().parent.mkdir(parents=True, exist_ok=True)
        _attempts_file().write_text(
            json.dumps({"ts": tries[-50:]}), encoding="utf-8")
    except OSError:
        pass
    return len(tries)


def _near_miss_reply(word: str, text: str) -> Optional[str]:
    """Промах по слову на одну букву/регистр — локальный ответ, мозг
    не видит ни слово, ни попытку. None — промаха нет, путь обычный."""
    m = re.match(r"^[^\s,.!?:;]+", (text or "").strip())
    raw_token = m.group(0) if m else ""
    token = raw_token.lower()
    if not token:
        return None
    if token == word.lower():
        # те же буквы, но точного совпадения не было — значит РЕГИСТР:
        # «Севрюжина статус» с заглавной — подсказка, не молчаливый мозг
        if raw_token != word:
            return ("слово набрано в другом регистре — калитка "
                    "чувствительна к прописным/строчным. Набери слово "
                    "точно как в .env и добавь команду")
        return None
    if len(word) < _NEAR_MISS_MIN_WORD:
        return None
    if _edit_distance(token, word) == _NEAR_MISS_DISTANCE:
        n = _count_attempt()
        _gate_log("near-miss", attempts=n)
        if n >= _ATTEMPTS_MAX:
            return ("слишком много попыток открыть калитку — подожди "
                    "несколько минут. Слова в разговор не называю")
        return ("слово не совпало на одну букву — если звал калитку, "
                "проверь написание и повтори; если просто говорил со "
                "мной — скажи иначе, без тайного слова")
    return None


def _strip_vocative(text: str) -> str:
    """«Марфа, <слово> статус» — обращение снимается ДО проверки слова
    (аудит 286): уменьшительные и падежи — те же формы, что слушают
    уши (config.EARS_WAKE_SHORT_FORMS) ПЛЮС именительные ласковые
    (В22 круга 33: «Марфушка» в списке ушей НЕТ — а Создатель так
    зовёт); иначе естественная речь Создателя увозила слово в мозг."""
    low = text.lower()
    names = (set(config.EARS_WAKE_WORDS) | set(config.EARS_WAKE_SHORT_FORMS)
             | {"марфа", "марфушка", "марфочка", "марфонька"})
    for name in sorted(names, key=len, reverse=True):
        if low.startswith(name):
            tail = text[len(name):]
            if tail[:1] in (",", " ", "!", ".", ":", ";", "-"):
                stripped = tail.lstrip(" ,.!?:;-—")
                if stripped:
                    return stripped
    return text


# ---------------------------------------------------------------
# Команды за калиткой
# ---------------------------------------------------------------
def _safe_url(url: str) -> str:
    """URL без кредитов: userinfo («//user:pass@») в чат не уезжает
    (аудит 299) — адрес показать можно, тайну нельзя."""
    return re.sub(r"//[^/@]+@", "//", url or "")


def _cmd_status() -> str:
    """Полный осмотр: мозг, панель, RAM, диск, git, python."""
    lines = []

    try:  # мозг
        with urllib.request.urlopen(config.BRAIN_URL + "/health",
                                    timeout=PROBE_TIMEOUT_SEC) as r:
            lines.append("мозг: жив (" + _safe_url(config.BRAIN_URL) + ")"
                         if r.status == 200
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

    try:  # RAM — ОДНА арифметика (аудит 294): ГБ и процент — из
        # одного total-available; прежде ГБ было total-available, а
        # процент vm.used/total — на Windows это РАЗНЫЕ числа, строка
        # врала: «48.0 / 64.0 ГБ (0.0%)» при живых 48 занятых
        import psutil
        vm = psutil.virtual_memory()
        used_gb = (vm.total - vm.available) / 2**30
        total_gb = vm.total / 2**30
        lines.append("RAM: %.1f / %.1f ГБ (%.1f%%)" % (
            used_gb, total_gb, 100.0 * used_gb / total_gb))
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
        if head.returncode != 0 or "fatal" in (head.stderr or "").lower():
            # аудит 295: не репозиторий — НЕ «дерево чистое», а правда
            lines.append("git: это не репозиторий (или git молчит) — "
                         "чистоту дерева не покажу")
        else:
            dirty = subprocess.run(
                ["git", "status", "--porcelain"], cwd=str(config.HOME_DIR),
                capture_output=True, text=True, timeout=GIT_TIMEOUT_SEC)
            n_dirty = len([l for l in (dirty.stdout or "").splitlines()
                           if l.strip()])
            lines.append("git: " + (head.stdout or "").strip())
            lines.append("дерево: " + ("чистое" if n_dirty == 0
                                       else "незакоммичено файлов: %d"
                                       % n_dirty))
    except Exception:
        lines.append("git: недоступен")

    lines.append("python: " + sys.version.split()[0])
    return "Полный осмотр дома:\n" + "\n".join("— " + l for l in lines)


def _cmd_tests() -> str:
    """Прогон батареи: venv-интерпретатором, с таймаутом, показать хвост.

    N7 аудита: pytest не установлен — это НЕ «красные тесты», а «не
    запускались»; диагноз не врёт, лечение — одна команда.

    Аудит 288 (урок дня-18, код 4 в живом логе «примени патч 0002»):
    коды 4 (usage error — папки tests/ нет) и 5 (не собралось ни одного
    теста) — НЕ «красные тесты». Красные — только код 1.

    Аудит 296: батарея — единственная команда калитки длиннее минуты:
    эфир дома получает стадию ДО прогона (вне хода — тихий no-op)."""
    try:
        from core import progress
        progress.stage("калитка: гоняю батарею тестов — до %d с, чат "
                       "молчит, пока она идёт…" % TEST_TIMEOUT_SEC)
    except Exception:
        pass
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
        rc = r.returncode
        verdict = {
            0: "БАТАРЕЯ ЗЕЛЁНАЯ",
            1: "ЕСТЬ КРАСНЫЕ ТЕСТЫ",
            2: "ТЕСТЫ ПРЕРВАНЫ (код 2) — кто-то остановил прогон",
            3: "ВНУТРЕННЯЯ ОШИБКА PYTEST (код 3) — скажи архитектору",
            4: ("тесты НЕ НАШЛИСЬ (код 4: usage error — папки tests/ "
                "нет на месте?) — это НЕ красные тесты"),
            5: ("тесты НЕ СОБРАЛИСЬ (код 5: pytest не нашёл ни одного "
                "теста) — это НЕ красные тесты"),
        }.get(rc, "НЕПОНЯТНЫЙ ИСХОД БАТАРЕИ (код %d) — скажи архитектору"
              % rc)
        tail = "\n".join((r.stdout or "").splitlines()[-TAIL_LINES:])
        _gate_log("tests", rc=rc, secs=round(time.time() - t0, 1))
        return "%s за %.0f с. Хвост вывода:\n%s" % (
            verdict, time.time() - t0, tail)
    except subprocess.TimeoutExpired:
        _gate_log("tests", rc="timeout")
        return "тесты не уложились в %d с — где-то зависло, смотри руками" \
            % TEST_TIMEOUT_SEC
    except Exception as e:
        return "тесты не запустились: " + str(e)


def _cmd_tail(name: str) -> str:
    """Хвост файла из logs/ (по части имени, свежайший) + НЕобязательный
    фильтр по подстроке (№26 роадмапа): «хвост brain ошибка» — только
    строки с «ошибка» из свежайшего brain-лога. Путь наружу невозможен:
    ищем только СРЕДИ файлов logs/, а не склеиваем путь из строки.

    Аудит 300: файл, исчезнувший между поиском и чтением, — честное
    «не смогла прочитать», а не споткнувшаяся калитка; сколько строк
    показали — пишем всегда.
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

    def _mtime(p: Path) -> float:
        try:
            return p.stat().st_mtime
        except OSError:
            return -1.0     # исчез между взглядом и замером — не спотыкаемся

    def _shown(p: Path) -> str:
        try:
            return str(p.relative_to(root))
        except ValueError:
            return p.name   # аудит 305: относительный корень не валит хвост

    matches = [p for p in root.rglob("*")
               if p.is_file() and file_part.lower() in p.name.lower()]
    if not matches:
        return ("в logs/ нет файла с таким именем"
                + (" (фильтр «%s» даже не понадобился)" % needle
                   if needle else ""))
    newest = max(matches, key=_mtime)
    if _mtime(newest) < 0:
        return ("файл «%s» исчез, пока я тянулась к нему — попробуй ещё "
                "раз" % file_part)
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
                        % (_shown(newest), len(tail), needle))
            return ("%s (последние %d строк, найдено %d с «%s»):\n%s"
                    % (_shown(newest), len(tail), len(picked),
                       needle, "\n".join(picked)))
        return "%s (последние %d строк):\n%s" % (_shown(newest), len(tail),
                                                 "\n".join(tail))
    except Exception as e:
        return "не смогла прочитать: " + str(e)


# ---------------------------------------------------------------
# Разрешения Создателя за калиткой (аудит 284): прежде «разреши
# внедрять себя», «следи за экраном» и файл моторики лежали СНАРУЖИ
# слова — сейф стоял на библиотеке (статус/тесты/хвост), а мастерская
# была открыта. Теперь опасные разрешения — за словом; безопасные
# «выключи/запрети/не следи» остаются и снаружи.
# ---------------------------------------------------------------
def _cmd_hands(on: bool) -> str:
    from core import motor
    _gate_log("permission", what="hands", on=on)
    return motor.set_enabled(on)


def _cmd_self_write(allow: bool) -> str:
    from core import repair
    _gate_log("permission", what="self_write", on=allow)
    return repair.allow_self_write() if allow else repair.forbid_self_write()


def _cmd_watch(on: bool) -> str:
    from core import eyes
    _gate_log("permission", what="screen_watch", on=on)
    return eyes.set_watch(on)


HELP = ("калитка Создателя открыта. Команды: статус | тесты | "
        "хвост <часть имени из logs/> [<подстрока> — фильтр строк, №26>] | "
        "новое слово: <новое> — смена кодового слова (Ф47, два шага) | "
        "подтверждаю — второй шаг смены | включи/выключи моторику | "
        "разреши/запрети внедрять себя | следи за экраном / не следи. "
        "Слово действует только в этом сообщении.")


# ---------------------------------------------------------------
# Ф47 «РОТАЦИЯ КОДОВОГО СЛОВА» (день-9): смена двумя шагами.
# Шаг 1: «<старое> новое слово: X» — дом запоминает намерение
#        (живёт 10 минут) и просит подтверждение;
# Шаг 2: «<старое> подтверждаю» — сверка намерения, перезапись .env.
# Слово в ответах НИКОГДА не называется — ни старое, ни новое (Ф105);
# сообщение со словом до мозга не доходит, калитка перечитывает .env
# на каждом сообщении — перезапуск дома не нужен.
#
# КРУГ 36 (аудит 281/282): намерение хранится ШИФРОВАННЫМ — открытый
# текст нового слова в data/ (читаемой мозгом) нарушал обещание
# «мозг не видел слова»: мозг мог прочитать будущее слово из
# gate_rotate.json ещё ДО подтверждения. Ключ шифрования — в корне
# дома (.gate_rotate.key): мозгу туда закрыто замком Ф118 (путь без
# подпапки — отказ), тот же класс защиты, что у самого .env.
# ---------------------------------------------------------------
def _rotate_file() -> Path:
    """ЕДИНЫЙ источник правды на ИМЯ файла — config.GATE_ROTATE_FILE
    (аудит 301: два хардкода — один закон). Каталог — ЛЕНИВО от живого
    DATA_DIR: константа конфига вычислена на импорте и не следует за
    песочницей тестов (закон песочницы день-9: ленивые пути — от
    живого config.DATA_DIR, иначе намерение утекает мимо чужого дома)."""
    return Path(config.DATA_DIR) / Path(config.GATE_ROTATE_FILE).name


def _rotate_key() -> Optional[bytes]:
    """32 байта в корне дома. Нет файла — генерируем. Записать не
    смогли — None: шифровать ключом, который не переживёт вызов,
    нельзя (намерение станет нечитаемым)."""
    key_file = config.HOME_DIR / ".gate_rotate.key"
    try:
        data = key_file.read_bytes()
        if len(data) == 32:
            return data
    except OSError:
        pass
    data = os.urandom(32)
    try:
        key_file.write_bytes(data)
        return data
    except OSError:
        return None


def _seal(word: str) -> Optional[dict]:
    """Спрятать слово: XOR-поток из SHA-256(key+nonce+counter) + HMAC.
    Стандартная библиотека, без внешних зависимостей: поднять/прочесть
    без ключа нельзя, подделать без ключа нельзя (mac)."""
    key = _rotate_key()
    if key is None:
        return None
    nonce = os.urandom(16)
    raw = word.encode("utf-8")
    stream = b""
    counter = 0
    while len(stream) < len(raw):
        stream += hashlib.sha256(key + nonce + b"%08d" % counter).digest()
        counter += 1
    box = bytes(a ^ b for a, b in zip(raw, stream))
    mac = hmac.new(key, nonce + box, hashlib.sha256).digest()
    return {"v": 1,
            "nonce": base64.b64encode(nonce).decode("ascii"),
            "box": base64.b64encode(box).decode("ascii"),
            "mac": base64.b64encode(mac).decode("ascii")}


def _unseal(rec) -> Optional[str]:
    """Достать слово из намерения. Ключ пропал/сменён, брак, чужая
    подделка — None: честное «начни заново», не выдумываем."""
    key = _rotate_key()
    if key is None or not isinstance(rec, dict):
        return None
    try:
        nonce = base64.b64decode(rec.get("nonce") or "")
        box = base64.b64decode(rec.get("box") or "")
        mac = base64.b64decode(rec.get("mac") or "")
    except Exception:
        return None
    if not nonce or not box:
        return None
    if not hmac.compare_digest(
            mac, hmac.new(key, nonce + box, hashlib.sha256).digest()):
        return None
    stream = b""
    counter = 0
    while len(stream) < len(box):
        stream += hashlib.sha256(key + nonce + b"%08d" % counter).digest()
        counter += 1
    raw = bytes(a ^ b for a, b in zip(box, stream))
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return None


def _load_pending() -> Optional[dict]:
    try:
        rec = json.loads(_rotate_file().read_text(encoding="utf-8"))
        return rec if isinstance(rec, dict) else None
    except (OSError, ValueError):
        return None


def _save_pending(rec: Optional[dict]) -> bool:
    """Записать/снять намерение. Возвращает ФАКТ (аудит 293: прежде
    глотала OSError и обещала «намерение запомнила» — Создатель ждал,
    слал подтверждение и слышал «нечего подтверждать»)."""
    try:
        _rotate_file().parent.mkdir(parents=True, exist_ok=True)
        if rec is None:
            _rotate_file().unlink(missing_ok=True)
        else:
            _rotate_file().write_text(
                json.dumps(rec, ensure_ascii=False), encoding="utf-8")
        return True
    except OSError:
        return False


def _cmd_rotate_new(payload: str) -> str:
    """Шаг 1: «новое слово: X» — проверить и запомнить намерение.

    Payload приходит в ИСХОДНОМ регистре (аудит 281: прежде резался
    с lowercased-команды — Создатель печатал слово как придумал, а в
    .env ложился нижний регистр: префикс не совпал, калитка закрылась
    навсегда)."""
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
    if new_word.lower() in _TRIVIAL_WORDS:
        return ("новое слово — словарное или имя: такие подбирают "
                "первыми. Придумай то, что знает только Создатель")
    if new_word.strip('"').strip("'") != new_word:
        return ("по краям нового слова кавычка — читатель .env её съест, "
                "и слово сохранится одним, а прочитается другим. Без "
                "кавычек на краях, пожалуйста")
    if "#" in new_word or "=" in new_word:
        return ("в новом слове есть «#» или «=» — строка .env их не "
                "переживёт (комментарий/разделитель). Другими символами, "
                "пожалуйста")
    if new_word == _codeword():
        return ("новое слово совпадает с действующим — смена не нужна "
                "(аудит 305: прежде «сменяла» слово само на себя и "
                "отчитывалась о смене)")
    seal = _seal(new_word)
    if seal is None:
        return ("не смогла спрятать намерение (ключ шифрования не "
                "записался — диск? права?) — слово НЕ запомнила. "
                "Скажи архитектору")
    if not _save_pending(dict(seal, ts=time.time())):
        return ("намерение НЕ записалось (диск полон? права?) — "
                "подтверждать будет нечего. Попробуй ещё раз или скажи "
                "архитектору")
    _gate_log("rotate-new", word_len=len(new_word))
    return ("намерение запомнила — само слово спрятано под ключ в корне "
            "дома, в data/ лежит только шифровка. Подтверди вторым "
            "сообщением: пришли СЕЙЧАС ДЕЙСТВУЮЩЕЕ кодовое слово и "
            "добавь «подтверждаю». У тебя %d минут"
            % (config.GATE_ROTATE_TTL_SEC // 60))


def _rewrite_env(new_word: str) -> bool:
    """Перезаписать .env: чужие строки живы, строка слова — новая.

    Атомарно (аудит 287): tmp + os.replace — прежде write_text по
    живому файлу мог оборваться посередине, файл остался бы обрезан,
    слово потеряно, калитка закрыта навсегда (вход — только руками
    через Блокнот). Для самого чувствительного файла дома крах
    посередине больше не существует.

    Форма строк — как у читателя load_env (аудит 292): «KEY = value»
    с пробелом перед «=» раньше не находился — строка слова ДОПИСЫВАЛАСЬ
    второй, старое слово оставалось в файле навсегда, строки плодились
    с каждой ротацией."""
    env_file = config.HOME_DIR / ".env"
    lines: list[str] = []
    try:
        lines = env_file.read_text(encoding="utf-8-sig",
                                   errors="replace").splitlines()
    except OSError:
        lines = []     # TOCTOU: файл мог исчезнуть после проверки — ветка
                       # жива (аудит 304), создаём .env со словом
    replaced = False
    out: list[str] = []
    for raw in lines:
        k = raw.split("=", 1)[0].strip() if "=" in raw else ""
        if k == ENV_KEY:
            out.append("%s=%s" % (ENV_KEY, new_word))
            replaced = True
        else:
            out.append(raw)
    if not replaced:
        out.append("%s=%s" % (ENV_KEY, new_word))
    tmp = env_file.with_name(env_file.name + ".new")
    try:
        tmp.write_text("\n".join(out) + "\n", encoding="utf-8")
        os.replace(str(tmp), str(env_file))     # атомарно: целиком или никак
        return True
    except OSError:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        return False


def _cmd_rotate_confirm() -> str:
    """Шаг 2: «подтверждаю» — сверить намерение и сменить слово."""
    pending = _load_pending()
    if not pending or not isinstance(pending.get("box"), str):
        return ("нечего подтверждать: смену слова не начинали. Начни — "
                "«…новое слово: <новое>» за калиткой")
    try:
        ts = float(pending.get("ts", 0))
    except (TypeError, ValueError):
        ts = 0.0
    age = time.time() - ts
    if age < -60:
        # аудит 302: намерение «из будущего» — часы прыгнули или файл
        # правили; вечное ожидание подтверждения — не наша история
        _save_pending(None)
        return ("время намерения — в БУДУЩЕМ (часы прыгнули или файл "
                "правили руками?) — намерение снято, слово НЕ менялось. "
                "Начни заново")
    if age > config.GATE_ROTATE_TTL_SEC:
        _save_pending(None)
        return ("время подтверждения вышло (лимит %d минут) — намерение "
                "снято, слово НЕ менялось. Начни заново"
                % (config.GATE_ROTATE_TTL_SEC // 60))
    new_word = _unseal(pending)
    if not new_word or len(new_word) < MIN_LEN:
        _save_pending(None)
        return ("намерение не читается (ключ шифрования сменился или "
                "файл правили?) — слово НЕ менялось. Начни заново")
    if not _rewrite_env(new_word):
        return (".env не записался (диск? права?) — слово НЕ менялось, "
                "намерение живёт; попробуй ещё раз или скажи архитектору")
    _save_pending(None)
    _gate_log("rotate-done", word_len=len(new_word))
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
    отвечает сам и в мозг текст НЕ уходит. (False, None) — путь обычный.

    Промах на одну букву/регистр (аудит 285) — (True, локальный ответ):
    слово и промах не уезжают ни мозгу, ни в историю диалога."""
    word = _codeword()
    if not word:
        return False, None
    text = (user_text or "").strip()
    if not text:
        return False, None
    text = _strip_vocative(text)          # «Марфа, <слово> статус» — тоже калитка
    if not hmac.compare_digest(text[:len(word)].encode("utf-8"),
                               word.encode("utf-8")):  # bytes: кириллицу str не ест
        near = _near_miss_reply(word, text)
        if near is not None:
            return True, near             # промах не едет в мозг (аудит 285)
        return False, None
    rest = text[len(word):]
    if rest and not (rest[0].isspace() or rest[0] in ",.!?:;-—…("):
        return False, None                # «словостатус» — не калитка
    # запятая/тире сразу после слова — законная граница (аудит 286:
    # «слово, статус» прежде не открывал калитку) — срезаем её с пути
    # команды, ИСХОДНЫЙ регистр хвоста не трогаем (аудит 281)
    rest_stripped = rest.strip().lstrip(",.!?:;-—").strip()
    command = rest_stripped.lower()

    # КРУГ 33 (аудит И., К6): команда за словом — в броне. Падение
    # исполнения больше НЕ роняет check (а значит не роняет fail-closed
    # диспетчера): слово опознано — ход уже голос Создателя, честный
    # текст вместо исключения. Слово в мозг и в журнал не уезжает.
    try:
        if command.startswith("статус"):
            _gate_log("hit", cmd="статус")
            return True, _cmd_status()
        if command.startswith("тест"):
            _gate_log("hit", cmd="тесты")
            return True, _cmd_tests()
        if command.startswith("хвост"):
            _gate_log("hit", cmd="хвост")
            return True, _cmd_tail(command[len("хвост"):].strip())
        if command.startswith("новое слово"):
            _gate_log("hit", cmd="ротация-шаг-1")
            return True, _cmd_rotate_new(
                rest_stripped[len("новое слово"):].strip())
        if command.startswith("подтверждаю"):
            _gate_log("hit", cmd="ротация-шаг-2")
            return True, _cmd_rotate_confirm()
        # Разрешения Создателя (аудит 284): за словом
        if command.startswith("включи моторику") \
                or command.startswith("разреши руки"):
            return True, _cmd_hands(True)
        if command.startswith("выключи моторику"):
            return True, _cmd_hands(False)
        if command.startswith("разреши внедрять себя") \
                or command.startswith("разрешаю внедрять себя"):
            return True, _cmd_self_write(True)
        if command.startswith("запрети внедрять себя") \
                or command.startswith("запрещаю внедрять себя"):
            return True, _cmd_self_write(False)
        if command in ("следи за экраном", "смотри за экраном",
                       "следи за экран"):
            return True, _cmd_watch(True)
        if command in ("не следи за экраном", "хватит следить за экраном",
                       "не следи за экран", "перестань следить за экраном"):
            return True, _cmd_watch(False)
        if command:
            # аудит 303: «не поняла» — с указанием ЧЕГО именно
            return True, ("за словом — «%s»: такой команды не знаю. %s"
                          % (command[:40], HELP))
        _gate_log("hit", cmd="подсказка")
        return True, HELP
    except Exception as e:
        _gate_log("error", cmd=command[:40] if command else "",
                  err="%s: %s" % (type(e).__name__, e))
        return True, ("калитка споткнулась (мой сбой, не твой): %s: %s — "
                      "команда за словом не исполнилась, само слово в мозг "
                      "не уехало. Повтори через минуту."
                      % (type(e).__name__, e))
