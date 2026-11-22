# -*- coding: utf-8 -*-
r"""core/doctor.py — №21 «ДОКТОР ДОМА»: осмотр, лечение, автолечение.

Дом не только просыпается при входе в Windows (№22) — он учится лечить
себя сам. Три режима:

- осмотр (check_all): порты мозг/глаза/панель, сердца ушей и стремления,
  venv, веса моделей, .env (только существует — БЕЗ чтения значений),
  свободное место на диске, коммит канона. Ничего не трогает;
- лечение (heal): мёртвый слуга поднимается той же командой, которой
  его поднимает старт дома (start_marfa.json). Конфига нет — лечить
  нечем, честно пишем и не выдумываем;
- автолечение (tick_auto): расписание Ф75 зовёт раз в 5 минут. Слуга,
  мёртвый ДВА осмотра подряд, поднимается сам — и не чаще раза в
  30 минут на слугу (мозг разогревается минутами, панель — секундами;
  вспышки не лечим). Каждое лечение — урок в журнал эволюционера:
  дом учится на каждом переломе.

Создателю: «доктор» / «осмотри дом» в чате — осмотр текстом;
кнопка 84_doctor.bat — осмотр и лечение с подтверждением.
"""
from __future__ import annotations

import datetime as dt
import json
import shlex
import shutil
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Optional

from core import config

CHECK_TIMEOUT_SECS = 2          # осмотр лёгкий: мёртвый порт отвечает отказом
# M7 аудита (раунд 2): критичному слуге доверяем больше — 30B с --mlock
# честно разминается дольше 2 с после старта; поспешный вердикт «мозг
# мёртв» поднимал ВТОРОЙ llama-server на том же порту и устраивал
# драку за RAM. Warn-слуги остаются на лёгком таймауте.
CRIT_CHECK_TIMEOUT_SECS = 10
EARS_FRESH_SECS = 600           # сердце ушей свежее 10 минут — служба слушает
DISK_WARN_GB = 20               # меньше — предупреждение
DISK_CRIT_GB = 10               # меньше — критично, лечить нечем
HEAL_MIN_INTERVAL_SECS = 1800   # одного слугу не лечим чаще раза в 30 минут
AUTO_INTERVAL_SECS = 300        # автодоктор: раз в 5 минут (расписание)

# (id, порт, путь здоровья, ключ команды в start_marfa.json, критичность)
SERVICES = [
    ("brain", 8082, "/health", "brain_cmd", "crit"),
    ("eyes", 8083, "/health", "eyes_cmd", "warn"),
    ("panel", 5001, "/api/status", "panel_cmd", "crit"),
]


def _non_http_services() -> list:
    """Уши и стремление: не-HTTP слуги, живость — по файлу-сердцу.
    Пути — ЛЕНИВО из закона дома (config), чтобы тесты tmp-дома были честны.
    """
    return [
        ("ears", "ears_cmd", "warn", config.EARS_STATUS_FILE,
         EARS_FRESH_SECS),
        ("drive", "drive_cmd", "crit", config.DRIVE_STATUS_FILE,
         config.DRIVE_INTERVAL_SECS * 3),
    ]


def _service_ids() -> list:
    return [s[0] for s in SERVICES] + [s[0] for s in _non_http_services()]

START_CONFIG_FILE = config.HOME_DIR / "start_marfa.json"


# ---------- инструменты осмотра ----------

def _service_urls() -> dict:
    """N6 аудита: адреса осмотра — из таблицы SERVICES (порты больше не
    мёртвая декларация); мозг — из закона дома с env-переопределением
    (тесты и переезд мозга живут на BRAIN_URL)."""
    urls = {}
    for sid, port, path, _key, _level in SERVICES:
        if sid == "brain":
            urls[sid] = config.BRAIN_URL.rstrip("/") + path
        else:
            urls[sid] = "http://127.0.0.1:%d%s" % (port, path)
    return urls


def _http_ok(url: str) -> bool:
    """Жив ли HTTP-слуга. M7: таймаут — по критичности слуги из SERVICES
    (crit разминается дольше warn — не хороним разогревающийся мозг)."""
    try:
        port = urllib.parse.urlsplit(url).port
    except ValueError:
        port = None
    level = {s[1]: s[4] for s in SERVICES}.get(port)
    timeout = CRIT_CHECK_TIMEOUT_SECS if level == "crit" else CHECK_TIMEOUT_SECS
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.status == 200
    except Exception:
        return False


def _fresh(path: Path, secs: float) -> bool:
    """Сердце (JSON с ts) свежее — служба жива."""
    try:
        rec = json.loads(Path(path).read_text(encoding="utf-8"))
        ts = dt.datetime.fromisoformat(rec["ts"])
        return (dt.datetime.now() - ts).total_seconds() <= secs
    except (OSError, ValueError, KeyError, TypeError):
        return False


def _check(level: str, ok: bool, note: str) -> dict:
    return {"level": level, "ok": bool(ok), "note": note}


def check_all(now: Optional[dt.datetime] = None) -> dict:
    """Осмотр дома. Ничего не трогает — только факты."""
    now = now or dt.datetime.now()
    checks: dict = {}

    urls = _service_urls()
    for sid, _port, _path, _key, level in SERVICES:
        ok = _http_ok(urls[sid])
        checks[sid] = _check(level, ok, "жив" if ok else "не отвечает")
    for sid, _key, level, status_file, fresh_secs in _non_http_services():
        ok = _fresh(status_file, fresh_secs)
        checks[sid] = _check(level, ok,
                             "сердце бьётся" if ok else "сердце молчит")

    venv_py = config.HOME_DIR / "venv" / "Scripts" / "python.exe"
    checks["venv"] = _check("warn", venv_py.exists(),
                            "на месте" if venv_py.exists()
                            else "venv не найден")
    for quant, fname in config.GGUF_FILES.items():
        p = config.MODELS_DIR / fname
        checks["model_" + quant] = _check("warn", p.exists(),
                                          "%s" % (fname if p.exists()
                                                  else "файл не найден"))
    env_ok = (config.HOME_DIR / ".env").exists()
    checks["env"] = _check("warn", env_ok,
                           "есть (значения не читаю)" if env_ok else "нет")
    try:
        free_gb = shutil.disk_usage(str(config.HOME_DIR)).free / 2**30
    except OSError:
        free_gb = -1.0
    if free_gb < 0:
        # N5 аудита: «не смогли посмотреть» — это НЕ «всё ок»: осмотр
        # честно говорит, что не посмотрел, и не рисует зелёную галочку
        checks["disk"] = _check("warn", False, "не посмотреть — осмотр диска не удался")
    else:
        checks["disk"] = _check(
            "crit" if free_gb < DISK_CRIT_GB else "warn",
            free_gb >= DISK_WARN_GB,
            "свободно %.1f ГБ" % free_gb)
    head = _git_head()
    checks["canon"] = _check("warn", head is not None,
                             head or "git молчит")

    ok = all(c["ok"] for c in checks.values() if c["level"] == "crit")
    return {"ts": now.isoformat(timespec="seconds"), "ok": ok,
            "checks": checks}


def _git_head() -> Optional[str]:
    try:
        r = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                           cwd=str(config.HOME_DIR), capture_output=True,
                           text=True, timeout=10)
        if r.returncode == 0:
            return r.stdout.strip()
    except Exception:
        pass
    return None


_NAMES = {"brain": "мозг 8082", "eyes": "глаза 8083", "panel": "панель 5001",
          "ears": "уши", "drive": "стремление", "venv": "venv",
          "model_Q4_K_M": "веса Q4_K_M", "model_Q6_K": "веса Q6_K",
          "env": ".env", "disk": "диск", "canon": "канон git"}


def render(report: dict) -> str:
    """Отчёт простым языком — для кнопки, чата и журнала."""
    lines = ["ДОКТОР ДОМА — %s" % report.get("ts", "?")]
    for cid, c in report.get("checks", {}).items():
        mark = "OK " if c["ok"] else ("!! " if c["level"] == "crit"
                                      else "!  ")
        lines.append("%s %-14s %s" % (mark, _NAMES.get(cid, cid), c["note"]))
    lines.append("Вердикт: " + ("дом здоров" if report.get("ok")
                                else "дом просит внимания"))
    return "\n".join(lines)


# ---------- лечение ----------

def _spawn(cmd: str) -> None:
    """Поднять слугу в отдельной консоли — как старт дома.

    M6 аудита (раунд 2): shell=True + команда из start_marfa.json — путь
    к RCE (write_file под стражем писал бы конфиг — доктор выполнял его
    ЦЕЛОЙ shell-строкой: «del C:\Marfa» уезжал бы исполнителем). Теперь —
    список аргументов без shell; shell-метасимволы отвергаются на корню."""
    if any(c in cmd for c in "&|<>^\n\r"):
        raise ValueError("команда старта содержит shell-метасимволы — не выполняю: %s"
                         % cmd)
    argv = _split_cmd(cmd)
    if not argv:
        raise ValueError("пустая команда старта")
    subprocess.Popen(argv, shell=False, cwd=str(config.HOME_DIR),
                     creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0))


def _split_cmd(cmd: str) -> list:
    """Строку команды — в список аргументов. posix=False: обратные слэши
    путей Windows живут; кавычки путей с пробелами снимаем."""
    parts: list[str] = []
    for tok in shlex.split(cmd, posix=False):
        if len(tok) >= 2 and tok[0] == tok[-1] and tok[0] in "\"'":
            tok = tok[1:-1]
        if tok:
            parts.append(tok)
    return parts


def _load_start_config() -> dict:
    """Команды старта дома. Файла нет — пусто: лечить нечем, не выдумываем."""
    try:
        data = json.loads(START_CONFIG_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def heal(dead_ids: list) -> list:
    """Поднять мёртвых слуг командами из start_marfa.json.

    Возвращает список действий («панель: поднят(а)»); лечить нечем —
    честная запись в списке. Ошибка спавна — тоже честно, не молчим.
    """
    cfg = _load_start_config()
    key_by_id = {s[0]: s[3] for s in SERVICES}
    key_by_id.update({s[0]: s[1] for s in _non_http_services()})
    actions: list = []
    for sid in dead_ids:
        cmd = (cfg.get(key_by_id.get(sid, "")) or "").strip()
        if not cmd:
            actions.append("%s: лечить нечем — команды нет в start_marfa.json"
                           % _NAMES.get(sid, sid))
            continue
        try:
            _spawn(cmd)
            actions.append("%s: поднимаю — %s"
                           % (_NAMES.get(sid, sid), cmd))
            _lesson("доктор-лечение", "%s поднят: %s" % (sid, cmd))
        except Exception as e:
            actions.append("%s: не поднялся — %s" % (_NAMES.get(sid, sid), e))
    return actions


def _lesson(kind: str, text: str) -> None:
    try:
        from evolution.journal import log_lesson
        log_lesson(kind, text)
    except Exception:
        pass


# ---------- автолечение (расписание Ф75) ----------

def _load_state() -> dict:
    try:
        data = json.loads(config.DOCTOR_STATE_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_state(state: dict) -> None:
    try:
        config.DOCTOR_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = config.DOCTOR_STATE_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, ensure_ascii=False, indent=1),
                       encoding="utf-8")
        tmp.replace(config.DOCTOR_STATE_FILE)
    except OSError:
        pass


def tick_auto(now: Optional[dt.datetime] = None) -> str:
    """Один осмотр автодоктора: мёртвый два раза подряд — поднимаю.

    Вспышки не лечим: слуга должен помереть в ДВА осмотра подряд.
    Живой слуга стирает свою отметку. Не чаще HEAL_MIN_INTERVAL_SECS
    на слугу — разгружающийся мозг не дёргаем спавнами.
    """
    now = now or dt.datetime.now()
    report = check_all(now=now)
    state = _load_state()
    seen_dead: dict = dict(state.get("seen_dead", {}))
    healed: dict = dict(state.get("healed", {}))
    actions: list = []

    all_ids = _service_ids()
    for sid in all_ids:
        c = report["checks"].get(sid)
        if c is None or c["ok"]:
            seen_dead.pop(sid, None)
            continue
        first_ts = seen_dead.get(sid)
        if first_ts is None:
            seen_dead[sid] = now.isoformat(timespec="seconds")
            continue                      # первый осмотр: сначала убедимся
        try:
            last_heal = dt.datetime.fromisoformat(str(healed.get(sid, "")))
            if (now - last_heal).total_seconds() < HEAL_MIN_INTERVAL_SECS:
                continue                  # недавно лечили — ждём
        except ValueError:
            pass
        actions += heal([sid])
        healed[sid] = now.isoformat(timespec="seconds")
        seen_dead.pop(sid, None)

    _save_state({"ts": now.isoformat(timespec="seconds"),
                 "seen_dead": seen_dead, "healed": healed})
    dead_now = [sid for sid in all_ids
                if not report["checks"].get(sid, {"ok": True})["ok"]]
    note = "мёртвые: %s" % (", ".join(dead_now) if dead_now else "нет")
    if actions:
        note += "; поднято: %d" % len(actions)
        _lesson("доктор-осмотр", note)
    return note


def tick() -> str:
    """Точка входа для расписания Ф75 (интервал AUTO_INTERVAL_SECS)."""
    return tick_auto()


if __name__ == "__main__":
    sys.exit(0)
