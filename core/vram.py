# -*- coding: utf-8 -*-
"""core/vram.py — ХОЗЯИН VRAM: глаза никогда не приседают ради рук.

Принцип хозяина ресурса (мастер-ТЗ, раздел 4): у VRAM 6 ГБ один
хозяин — сенсор зрения 8083 (Qwen2.5-VL-3B + mmproj), смена хозяина
только по расписанию. Руки v2 «единое зрение» (ТЗ_Руки_v2) этот закон
соблюдают буквально: у них НЕТ своей модели, они исполняют координаты
глаз и сервер зрения не трогают.

Единственный законный заёмщик VRAM после Рук v2 — кодер-слуга
(qwen2.5-coder-7b, порт 8085, core/repair.py): он текстовый и тяжёлый
(~4.7 ГБ + глаза ~3.0 ГБ > 6 ГБ), поэтому на время патча глаза
присаживает и возвращает их доктором после. Церемония заёма живёт
здесь — одна механика, одна истина, один танцор.

КРУГ 36 (аудит Создателя, vram 269–280): церемония стала ЧЕСТНОЙ.
Прежний stop_llama возвращал bool, которым врал трижды: terminate()
без wait() «уложил» живой процесс (драйвер отдаёт VRAM асинхронно —
ensure_server тут же спавнил кодера в ещё занятые 6 ГБ → OOM); False
означал «сервера нет», «psutil не стоит» и «AccessDenied» ОДНОВРЕМЕННО
(«не смогла» ≠ «не нужно» — закон факта); порт искался по ЛЮБОМУ токену
командной строки («-c 8083» убивал чужой сервер, форма --port=8083 не
находилась вовсе), имя — подстрокой по всем аргументам («tail
llama-server.log» — «сервер»); порт 8082 (мозг) ничто не удерживало —
готовый примитив «убей свой мозг»; убийство не логировалось и не
подтверждалось. Теперь: lay_down() возвращает StopResult с пятью
честными исходами, смерть подтверждается фактом (wait → kill →
is_running), порт читается ТОЛЬКО из аргумента --port (обе формы),
имя — по бинарнику argv[0], порт проверяется по закону церемонии
(глаза/кодер/вложитель/шёпот — можно; мозг/панель/горло — никогда),
всё пишется в logs/vram_log.jsonl, параллельные танцоры (repair и
ear_bridge — разные процессы) разводятся файловым замком, и хозяин
ресурса наконец ИЗМЕРЯЕТ ресурс: vram_free_mb() по nvidia-smi.

История: до 22.11 VRAM-танцем танцевали и руки (UI-TARS на 8084,
ТЗ_Руки_v1) — живой прогон показал цену: десятки секунд на каждую
смену, слепая камера, «посмотри» в очереди. Создатель вернул дом к
доктрине: руки — на координатах глаз, UI-TARS — в чулане.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import subprocess
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Optional

from core import config, loghygiene

# Закон портов (аудит 275): укладывать можно только СЛУГ, которым
# процессы принадлежат по расписанию арсенала. Мозг (8082) и панель
# (5001) — неприкосновенны: пока core/ писал и страж, «убей свой мозг»
# был одним вызовом stop_llama(config.PORT_BRAIN). Горло (8084) — слуга
# по вызову, но не llama-сервер: церемония его не касается.
_LAYABLE_PORT_ATTRS = ("PORT_EYES", "PORT_CODER", "PORT_EMBEDDER",
                       "PORT_WHISPER")

_TERMINATE_WAIT_SEC = 10     # terminate → ждать столько, потом kill
_KILL_WAIT_SEC = 5           # kill → ждать подтверждения смерти
_LOCK_WAIT_SEC = 15          # сколько ждать замок от соседнего органа
_LOCK_STALE_SEC = 120        # протухший замок (крах между обрести/снять)

_proc_lock = threading.Lock()   # один танцор ВНУТРИ процесса


def _layable_ports() -> tuple:
    """Порты, на которых церемония имеет право укладывать слуг."""
    return tuple(int(getattr(config, name)) for name in _LAYABLE_PORT_ATTRS)


def _log(rec: dict) -> None:
    """logs/vram_log.jsonl (правило 6.6: логи — истина). Убийство слуги —
    значимое действие дома: PID, порт, причина, свободная VRAM — всё
    пишется (аудит 277: прежде церемония не оставляла следа)."""
    try:
        rec = dict(rec)
        rec.setdefault("ts", dt.datetime.now().isoformat(timespec="seconds"))
        p = Path(config.LOGS_DIR) / "vram_log.jsonl"
        loghygiene.append_line(p, json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        pass   # журнал — не орган дыхания; церемония живёт дальше


def _arg_tokens(cmdline) -> list:
    """Аргументы командной строки — строками. bytes декодируем честно:
    str(b"--port") давал бы "b'--port'" и ТОЧНОЕ сравнение порта
    умирало бы на каждой чужой кодировке (аудит 280)."""
    out: list = []
    for c in cmdline or []:
        if isinstance(c, bytes):
            try:
                c = c.decode("utf-8", "replace")
            except Exception:
                continue
        out.append(str(c))
    return out


def _port_of(tokens: list) -> Optional[int]:
    """Порт процесса — ТОЛЬКО из его аргумента --port, обе формы:
    «--port 8083» (два токена) и «--port=8083» (один). Контекстный
    аргумент «-c 8083» портом НЕ считается (аудит 273): раньше
    llama-server --port 8085 -c 8083 умирал от stop_llama(8083) —
    по числу в контексте, а не по порту."""
    i = 0
    while i < len(tokens):
        t = tokens[i]
        if t == "--port" and i + 1 < len(tokens):
            try:
                return int(tokens[i + 1])
            except ValueError:
                return None
        if t.startswith("--port="):
            try:
                return int(t[len("--port="):])
            except ValueError:
                return None
        i += 1
    return None


def vram_free_mb() -> Optional[int]:
    """Свободная VRAM (МБ) по nvidia-smi — хозяин ресурса обязан его
    ВИДЕТЬ (аудит 272: прежде «ХОЗЯИН VRAM» не измерял ничего — весь
    принцип хозяина был поиском по строке в cmdline). Нет карты или
    утилиты — None: не выдумываем цифру."""
    try:
        r = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.free",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=10)
        if r.returncode != 0:
            return None
        lines = (r.stdout or "").strip().splitlines()
        if not lines:
            return None
        return int(lines[0].strip())
    except Exception:
        return None


@contextmanager
def _file_lock(timeout: float = _LOCK_WAIT_SEC):
    """Межпроцессный замок церемонии (аудит 278): repair.ensure_server и
    ear_bridge (whisper) — РАЗНЫЕ процессы, threading.Lock их не
    разводит, и два танцора итерировали и убивали одновременно.
    data/vram.lock: атомарное создание O_CREAT|O_EXCL, ожидание с
    таймаутом, протухший замок (крах между обрести и снять) снимается
    по возрасту. yield True — замок наш, False — не дождались."""
    lock = Path(config.DATA_DIR) / "vram.lock"
    ours: Optional[str] = None          # pid в замке, если взяли
    deadline = time.time() + max(0.0, timeout)
    try:
        while True:
            try:
                lock.parent.mkdir(parents=True, exist_ok=True)
                fd = os.open(str(lock),
                             os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                try:
                    ours = "%d" % os.getpid()
                    os.write(fd, ours.encode("utf-8"))
                finally:
                    os.close(fd)
                break
            except FileExistsError:
                # замок занят: протухший (крах хозяина) — снимаем
                try:
                    age = time.time() - lock.stat().st_mtime
                    if age > _LOCK_STALE_SEC:
                        lock.unlink(missing_ok=True)
                        _log({"act": "lock-stale-removed", "age": round(age, 1)})
                        continue
                except OSError:
                    pass
                if time.time() >= deadline:
                    _log({"act": "lock-busy", "waited": round(timeout, 1)})
                    break
                time.sleep(0.2)
            except OSError as e:
                _log({"act": "lock-error", "error": str(e)})
                break
        yield ours is not None
    finally:
        if ours is not None:
            try:
                lock.unlink(missing_ok=True)
            except OSError:
                pass


class StopResult:
    """Честный исход церемонии (аудит 270: bool означал три вещи сразу).

    status:
      "laid"      — уложили И ПОДТВЕРДИЛИ смерть (факт, не намерение);
      "no-server" — слуги на порту не было («не нужно»);
      "could-not" — видела, но не смогла уложить («не смогла»);
      "no-psutil" — нечем видеть процессы вовсе (нет зависимости);
      "forbidden" — порт вне закона церемонии (мозг/панель/чужой);
      "busy"      — замок церемонии не дождались (сосед танцует).
    """

    __slots__ = ("status", "text", "pids")

    def __init__(self, status: str, text: str = "", pids=()):
        self.status = status
        self.text = text
        self.pids = list(pids)

    @property
    def ok(self) -> bool:
        return self.status == "laid"

    def __bool__(self) -> bool:
        return self.ok

    def __repr__(self) -> str:
        return "StopResult(%s, pids=%s)" % (self.status, self.pids)


def lay_down(port: int, server_name: str = "llama-server") -> StopResult:
    """Уложить слугу на порту и ПОДТВЕРДИТЬ смерть (аудит 269/279).

    Ищем процесс по ИМЕНИ БИНАРНИКА (argv[0], не любой аргумент —
    «tail ...\\llama-server.log» не сервер) и его аргументу --port.
    Церемония: terminate → wait(10) → kill → wait(5) → is_running.
    «Уложили» — подтверждённая смерть, а не факт вызова terminate().
    Всё пишется в logs/vram_log.jsonl с PID, портом и свободной VRAM.
    """
    port = int(port)
    if port not in _layable_ports():
        _log({"act": "refuse-forbidden-port", "port": port,
              "server_name": server_name})
        return StopResult(
            "forbidden",
            "порт %d не принадлежит церемонии: глаза/кодер/вложитель/"
            "шёпот — можно, мозг и панель — неприкосновенны" % port)
    try:
        import psutil
    except ImportError as e:
        _log({"act": "no-psutil", "port": port, "error": str(e)})
        return StopResult(
            "no-psutil",
            "нет psutil (%s) — не вижу процессов, укладывать некому: "
            "venv\\Scripts\\pip install psutil" % e)
    with _proc_lock:
        with _file_lock() as locked:
            if not locked:
                return StopResult(
                    "busy",
                    "VRAM-церемония занята другим органом — подожди и "
                    "повтори")
            targets: list = []
            access_denied = 0
            for proc in psutil.process_iter(["pid", "cmdline", "name"]):
                try:
                    info = proc.info or {}
                    tokens = _arg_tokens(info.get("cmdline"))
                    head = (tokens[0] if tokens else "") \
                        or str(info.get("name") or "")
                    if server_name not in head:
                        continue
                    if _port_of(tokens) != port:
                        continue
                    targets.append(proc)
                except psutil.AccessDenied:
                    access_denied += 1
                except Exception:
                    continue
            if not targets:
                if access_denied:
                    _log({"act": "could-not", "port": port,
                          "why": "AccessDenied", "denied": access_denied})
                    return StopResult(
                        "could-not",
                        "не смогла прочитать чужие процессы (%d отказов "
                        "доступа) — слугу на порту %d не нашла, но "
                        "«не вижу» ≠ «его нет»" % (access_denied, port))
                _log({"act": "no-server", "port": port,
                      "server_name": server_name})
                return StopResult("no-server", "")
            dead: list = []
            survivors: list = []
            for proc in targets:
                pid = None
                try:
                    pid = proc.pid
                    proc.terminate()
                    try:
                        proc.wait(timeout=_TERMINATE_WAIT_SEC)
                    except psutil.TimeoutExpired:
                        proc.kill()                 # эскалация (аудит 276)
                        proc.wait(timeout=_KILL_WAIT_SEC)
                    dead.append(pid)
                except Exception as e:
                    if pid is not None:
                        survivors.append((pid, str(e)))
            # подтверждение: смерть — ФАКТ is_running, не факт вызова (279)
            confirmed: list = []
            for pid in dead:
                try:
                    psutil.Process(pid)
                    # процесс ещё числится — не подтверждаем смерть
                except psutil.NoSuchProcess:
                    confirmed.append(pid)
                except Exception:
                    confirmed.append(pid)   # не смогли спросить — не врём
            free = vram_free_mb()
            _log({"act": "lay_down", "port": port,
                  "server_name": server_name, "pids": confirmed,
                  "survivors": survivors, "vram_free_mb": free})
            if survivors or len(confirmed) < len(dead):
                return StopResult(
                    "could-not",
                    "не смогла уложить %s на порту %d (погибли %s, "
                    "выжили %s) — скажи архитектору"
                    % (server_name, port, confirmed or "—",
                       [p for p, _ in survivors] or "—"))
            return StopResult(
                "laid",
                "уложила %s на порту %d (pid %s; VRAM свободно: %s МБ)"
                % (server_name, port, confirmed,
                   "не измерить" if free is None else free), confirmed)


def stop_llama(port: int, server_name: str = "llama-server") -> bool:
    """СОВМЕСТИМЫЙ шов (bool): True — только «уложили и подтвердили».

    Новые вызывающие зовут lay_down(): он различает «нет слуги»,
    «не смогла», «нет psutil», «порт вне закона» и «замок занят» —
    пять исходов, которые прежний bool сваливал в одну ложь (аудит 270).
    """
    return lay_down(port, server_name).ok
