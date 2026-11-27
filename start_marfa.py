# -*- coding: utf-8 -*-
r"""start_marfa.py — №22: автозапуск дома одной командой (роадмап 30 фишек).

Поднимает всех слуг дома: мозг 8082 + глаза 8083 + панель 5001 + уши
(служба) + стремление (служба: план дня, дневник, вопросы, чтение).
Запуск из корня дома:
    venv\Scripts\python.exe start_marfa.py
    venv\Scripts\python.exe start_marfa.py --в-планировщик   # автомат навсегда

Как это работает:
- конфиг — start_marfa.json рядом со скриптом; при первом запуске создаётся
  сам (шаблон). Все команды вписаны из живой кнопки Создателя
  (Старт_Марфа.bat от 17.11.2026): мозг Qwen3-30B-A3B Q4_K_M на CPU,
  глаза Qwen2.5-VL-3B + mmproj на CUDA, панель Flask 5001.
  Сменил модель или квант — правь start_marfa.json;
- уже живой слуга не трогается (можно звать старт повторно, безопасно);
- каждый слуга поднимается в СВОЕЙ консоли — дом живёт своей жизнью,
  а Создатель видит логи каждого;
- глаза: холодный старт CUDA ~50 с — ждём до 90 с; панель — до 15 с;
- уши — не HTTP-слуга, а вечная служба (sensors\ears.py --service):
  живость — по статус-файлу data\ears_status.json (сердцебиение ≤2 мин
  назад). Нет микрофона/модели — служба не умирает, ждёт и пишет честный
  статус; воткнешь микрофон — ухо проснётся само;
- МОЗГ ЖДЁТ ЧЕСТНО (день-8, 23.11): до 120 с на «ожил» — старт без
  ожидания прятал смерть команды (кавычки терапии §15 убили сервер
  в первый же рестарт, а старт говорил «проверь позже»); не ожил —
  старт говорит посмотреть консоль мозга, а не молчит надеждой;
- KV-ПРЕФИКС (день-9, Ф42): сборка llama-server пробуется на
  --cache-reuse (запуск --help); знает — brain_cmd получает флаг, и
  статичное ядро промпта не пересчитывается на каждом ходу.
  Не знает — честный отказ, флаг не ставится (закон дня-8: неизвестный
  флаг убивает сервер на старте);
- --в-планировщик вписывает в планировщик Windows ДВЕ задачи:
  «Марфа» — поднять дом при входе в систему;
  «Марфа-синхронизация» — scripts\80_sync_github.bat /auto каждые 2 часа
  ( петля дом<-^>GitHub<-^>архитектор ходит сама, без нажатий);
- журнал старта — logs/startup.log.

Живость: мозг и глаза — llama-server, /health; панель — /api/status.
Швы для тестов (tests/test_start_marfa.py): _alive / _spawn / _log —
подменяются, реальные порты и процессы не трогаются.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import requests

HOME = Path(__file__).resolve().parent
CONFIG_FILE = HOME / "start_marfa.json"
LOG_FILE = HOME / "logs" / "startup.log"
EARS_STATUS_FILE = HOME / "data" / "ears_status.json"  # пишет служба ушей
EARS_FRESH_SECS = 120        # сердцебиение свежее этого — ухо живо
DRIVE_STATUS_FILE = HOME / "data" / "drive_status.json"  # служба стремления
DRIVE_FRESH_SECS = 180      # 3 такта по 60 с — сердце стремления живо
BRIDGE_STATUS_FILE = HOME / "data" / "voice" / "status.json"  # мост ушей
BRIDGE_FRESH_SECS = 120     # тик моста 30 с — как у ушей, два тика запаса

# (имя, порт, путь здоровья, поле конфига, сколько секунд ждать старта)
# МОЗГ ЖДЁТ 120 с (день-8): 30B с mmap поднимается десятками секунд;
# умершая на старте команда (кавычки/флаги против сборки) обязана
# быть ЗАМЕЧЕННОЙ на старте, а не «проверь позже».
SERVICES = [
    ("мозг", 8082, "/health", "brain_cmd", 120),
    ("глаза", 8083, "/health", "eyes_cmd", 90),
    ("панель", 5001, "/api/status", "panel_cmd", 15),
]

# ЯДОВИТЫЕ ХВОСТЫ в brain_cmd (день-8, 23.11): терапия §15 вписала
# --jinja --chat-template-kwargs "{\"enable_thinking\": false}" — и в JSON
# \", и в командной строке кавычки съедаются разбором argv: сервер
# получает {enable_thinking: false} без кавычек — НЕВАЛИДНЫЙ JSON —
# и умирает на старте. WinError 10061 в чате Создателя — вот эта бомба.
# Лечение: команда старта мозга НЕ СОДЕРЖИТ КАВЫЧЕК ВООБЩЕ (закон);
# выключение мышления живёт на КЛИЕНТЕ (chat_template_kwargs в каждом
# запросе + «/no_think» — работает на любой сборке сервера).
_POISON_MARKERS = ("chat-template-kwargs", "--jinja")

TEMPLATE = {
    "brain_cmd": (
        "llama.cpp\\llama-server.exe -m models\\Qwen3-30B-A3B-Q4_K_M.gguf "
        "--host 127.0.0.1 --port 8082 -ngl 0 "
        # терапия §15 (23.11): контекст 8192 (дефолт был 4096 — промпт
        # 4143 ток резал ЯДРО), сэмплинг без мышления 0.7/0.8.
        # Мышление выкл — НА КЛИЕНТЕ (brain.py), не в старте сервера:
        # кавычки kwargs убили старт в первый же рестарт (день-8)
        "-c 8192 --temp 0.7 --top-p 0.8 --top-k 20 --repeat-penalty 1.0"
    ),
    "eyes_cmd": (
        "llama.cpp\\llama-server.exe -m models\\vlm\\Qwen2.5-VL-3B-"
        "Instruct-Q4_K_M.gguf --mmproj models\\vlm\\mmproj-Qwen2.5-VL-"
        "3B-Instruct-Q8_0.gguf -ngl 99 -c 8192 -t 2 --temp 0.1 "
        "--host 127.0.0.1 --port 8083"
    ),
    "panel_cmd": (
        "venv\\Scripts\\python.exe -m flask --app web.app run "
        "--host 127.0.0.1 --port 5001"
    ),
    "ears_cmd": "venv\\Scripts\\python.exe sensors\\ears.py --service",
    "drive_cmd": "venv\\Scripts\\python.exe -m core.drive --service",
    # Ф182 (круг 30): мост ушей — шестой слуга; до него службу поднимали
    # руками — и после каждого закрытого окна консоли слух фраз умирал
    # незаметно (живой лог дня-17: «служба моста: сердцебиения нет» —
    # дважды за один день, при живых ушах-стороже)
    "bridge_cmd": "venv\\Scripts\\python.exe sensors\\ear_bridge.py --service",
}


def _heal_brain_cmd(cfg: dict) -> bool:
    """День-8: вылечить отравленную команду мозга в живом конфиге.

    Кнопка 92 и старт дома зовут это перед подъёмом слуг: конфиг с
    ядовитым хвостом (кавычки терапии §15) пересобирается из шаблона,
    старая команда — в журнал старта (правило 6.6: логи — истина).
    Возвращает True, если лечение состоялось. Чужая правка модели/кванта
    не теряется зря: путь модели переносится из старой команды, если
    он менялся и не содержит яда.
    """
    cmd = (cfg.get("brain_cmd") or "").strip()
    if not cmd or not any(m in cmd for m in _POISON_MARKERS):
        return False
    healed = TEMPLATE["brain_cmd"]
    # путь модели переносится из живой команды, если Создатель его менял
    # (яда в пути нет — лечим хвост, а не личную жизнь)
    tokens = cmd.split()
    m = None
    for i, piece in enumerate(tokens):
        if piece == "-m" and i + 1 < len(tokens):
            m = tokens[i + 1]
            break
    if m and m not in healed:
        healed = healed.replace(
            "models\\Qwen3-30B-A3B-Q4_K_M.gguf", m)
    cfg["brain_cmd"] = healed
    return True


def ensure_config(path: Path) -> dict:
    """Конфиг старта; при первом запуске создаётся шаблон.

    День-8: конфиг с ядовитой командой мозга (кавычки терапии §15)
    лечится при каждом старте — бомба ждала первого рестарта,
    не дать ей ждать второго.
    День-9 (Ф42): сборка сервера ПРОБИЕТСЯ на знание --cache-reuse и,
    если знает, команда мозга получает KV-префикс — статичное ядро
    промпта (~2-3 тыс ток) больше не пересчитывается на каждом ходу.
    Проба не угадывает: только ответ --help решает (закон дня-8 —
    неизвестный флаг убивает сервер на старте). Ответ пробы живёт
    в data/server_caps.json и перепроверяется по времени бинарника.
    """
    if not path.exists():
        path.write_text(json.dumps(TEMPLATE, ensure_ascii=False, indent=2),
                        encoding="utf-8")
        print("создан шаблон конфига: " + str(path))
    cfg = json.loads(path.read_text(encoding="utf-8"))
    if _heal_brain_cmd(cfg):
        path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2),
                        encoding="utf-8")
        print("КОМАНДА МОЗГА ВЫЛЕЧЕНА: кавычки терапии §15 ломали старт "
              "сервера (WinError 10061) — хвост снят, мышление выключено "
              "на клиенте; старая команда — в журнале старта")
        _log("конфиг: brain_cmd вылечен от кавычек терапии §15 (день-8)")
    if _ensure_kv_prefix(cfg):
        path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2),
                        encoding="utf-8")
        print("KV-ПРЕФИКС: сборка llama-server знает --cache-reuse — "
              "статичное ядро промпта больше не пересчитывается на "
              "каждом ходу (мозг на CPU ускоряется на длинных промптах)")
        _log("конфиг: brain_cmd получил --cache-reuse (Ф42, проба сборки)")
    return cfg


# Ф42: сколько токенов должен иметь общий кусок, чтобы кэш имел смысл.
# Ядро промпта (личность+манифест+законы+доктрина) — ~2-3 тыс ток,
# 256 — консервативный минимум куска переиспользования.
KV_REUSE_CHUNK = 256


def _caps_file() -> Path:
    return HOME / "data" / "server_caps.json"


def _probe_cache_reuse(exe: str):
    """Спросить у бинарника, знает ли он --cache-reuse. True/False —
    ответ сборки; None — спросить не вышло (не угадываем, флага не
    ставим: неизвестный флаг убивает сервер — урок дня-8)."""
    try:
        r = subprocess.run([exe, "--help"], capture_output=True, text=True,
                           timeout=30, cwd=str(HOME))
        blob = (r.stdout or "") + (r.stderr or "")
        return "cache-reuse" in blob
    except Exception:
        return None


def _ensure_kv_prefix(cfg: dict) -> bool:
    """Добавить --cache-reuse в brain_cmd, если сборка его знает.

    Возвращает True, если команда ИЗМЕНИЛАСЬ (конфиг надо сохранить).
    Закон дня-8 не нарушается: флаг и значение — без кавычек. Проба
    стоит один запуск --help (доли секунды) и кэшируется в
    data/server_caps.json по пути+времени бинарника: смена сборки
    llama.cpp — новая проба, обычный старт — без пробы.
    """
    cmd = (cfg.get("brain_cmd") or "").strip()
    if not cmd or "--cache-reuse" in cmd:
        return False
    exe = cmd.split()[0]
    exe_path = Path(exe)
    if not exe_path.is_absolute():
        exe_path = HOME / exe_path
    try:
        mtime = exe_path.stat().st_mtime
    except OSError:
        return False  # бинарника нет — старт сам скажет честно, не гадаем
    caps = {}
    try:
        caps = json.loads(_caps_file().read_text(encoding="utf-8"))
        if not isinstance(caps, dict):
            caps = {}
    except (OSError, ValueError):
        caps = {}
    if caps.get("exe") == str(exe_path) and caps.get("mtime") == mtime \
            and isinstance(caps.get("cache_reuse"), bool):
        supported = caps["cache_reuse"]
    else:
        supported = _probe_cache_reuse(str(exe_path))
        if supported is None:
            return False
        try:
            _caps_file().parent.mkdir(parents=True, exist_ok=True)
            _caps_file().write_text(json.dumps(
                {"exe": str(exe_path), "mtime": mtime,
                 "cache_reuse": bool(supported)},
                ensure_ascii=False, indent=1), encoding="utf-8")
        except OSError:
            pass  # кэш пробы не записался — просто спросим в следующий раз
    if not supported:
        _log("конфиг: сборка не знает --cache-reuse — KV-префикс не ставлю "
             "(честный отказ, Ф42)")
        return False
    cfg["brain_cmd"] = cmd + " --cache-reuse %d" % KV_REUSE_CHUNK
    return True


def _alive(port: int, path: str) -> bool:
    """Жив ли слуга: HTTP-код 200 по пути здоровья."""
    try:
        return requests.get("http://127.0.0.1:%d%s" % (port, path),
                            timeout=2).status_code == 200
    except Exception:
        return False


def _spawn(cmd: str) -> None:
    """Поднять слугу в отдельной консоли: дом живёт своей жизнью."""
    subprocess.Popen(cmd, shell=True, cwd=str(HOME),
                     creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0))


def _log(line: str) -> None:
    """Журнал старта — logs/startup.log (не падает, если logs/ нет)."""
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + line + "\n")
    except Exception:
        pass


def _wait(port: int, path: str, timeout: float, poll: float = 2.0) -> bool:
    """Ждать, пока слуга оживёт (глаза: холодный CUDA ~50 с)."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _alive(port, path):
            return True
        time.sleep(min(poll, max(0.0, deadline - time.time())))
    return _alive(port, path)


# Ф84 «ПРОГРЕВ МОЗГА» (день-12, живой лог: первый ход после старта —
# 91,3 с за 9 ток): холодный KV-кэш — самый дорогой ход дня. Мозг
# только что поднялся, префикс никто не считал — и первый же вопрос
# Создателя платит полный префилл статики (~2,6 тыс ток) своим
# ожиданием. Супер-решение: пусть его платит СТАРТ, а не Создатель —
# как только /health ожил, дом в фоне отправляет один крошечный
# запрос ТЕМ ЖЕ путём ask_json (преамбула+ядро+доктрина+/no_think —
# байт-в-байт системный префикс живого хода), и llama-server
# кладёт его в KV-кэш. Создатель тем временем открывает панель —
# и его первый вопрос едет по тёплым рельсам: префилл только
# хвоста хода. retries=1 — прогрев не имеет права платить дважды
# за кривой JSON; max_tokens=16 — сам ответ не важен, важен префикс.
# Прогрев — не орган дыхания: любая поломка молчит (панель уже
# открыта, чат жив, ход Создателя всё равно доедет сам).
def _warmup_brain() -> None:
    """Заплатить префилл статичного префикса мозга — в фоне, один раз."""
    try:
        from core.agent import Agent
        agent = Agent()
        agent.brain.ask_json(
            "Прогрев дома — служебный ход, отвечать Создателю не нужно.",
            system_extra=agent._static_system(),
            max_tokens=16, retries=1)
        _log("прогрев: статичный префикс мозга оплачен — первый ход "
             "Создателя поедет по тёплому KV-кэшу (Ф84)")
    except Exception as e:
        _log("прогрев мозга не вышел (не орган дыхания): %s" % e)


def _start_warmup():
    """Пустить прогрев фоновым потоком, если мозг жив. None — не пустили.

    Батарея не греет настоящий сервер: PYTEST_CURRENT_TEST — тот же
    дом-паттерн, что у дозвона мозга (brain._urlopen) — тесты честные,
    побочных потоков в соседние порты не пускаем.
    """
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return None
    if not _alive(8082, "/health"):
        return None
    t = threading.Thread(target=_warmup_brain, daemon=True,
                         name="marfa-warmup")
    t.start()
    return t


def register_scheduler() -> bool:
    r"""Вписать дом в автозагрузку Windows — обе задачи (Требование Создателя:
    «всё, что мы делаем, запускается автоматом»).

    «Марфа»               — поднять дом при входе в Windows (start_marfa.py);
    «Марфа-синхронизация» — scripts\80_sync_github.bat /auto каждые 2 часа:
    петля дом<-^>GitHub<-^>архитектор ходит сама, без нажатий кнопки.
    """
    tasks = [
        ("Марфа",
         ["schtasks", "/Create", "/F",
          "/TN", "Марфа",
          "/TR", '"%s" "%s"' % (sys.executable, str(Path(__file__).resolve())),
          "/SC", "ONLOGON"]),
        ("Марфа-синхронизация",
         ["schtasks", "/Create", "/F",
          "/TN", "Марфа-синхронизация",
          "/TR", '"%s" /auto'
          % str(HOME / "scripts" / "80_sync_github.bat"),
          "/SC", "HOURLY", "/MO", "2"]),
    ]
    ok_all = True
    for _name, cmd in tasks:
        try:
            r = subprocess.run(cmd, capture_output=True, text=True)
            ok_all = ok_all and r.returncode == 0
        except Exception:
            ok_all = False
    return ok_all


def _ears_alive() -> bool:
    """Живость ушей: служба пишет сердцебиение в data\\ears_status.json;
    свежее %d с — ухо слушает. Файла/свежести нет — не живо.""" % EARS_FRESH_SECS
    try:
        rec = json.loads(EARS_STATUS_FILE.read_text(encoding="utf-8"))
        ts = dt.datetime.fromisoformat(rec["ts"])
        return (dt.datetime.now() - ts).total_seconds() <= EARS_FRESH_SECS
    except (OSError, ValueError, KeyError):
        return False


def _drive_alive() -> bool:
    """Живость стремления: сердцебиение в data\\drive_status.json;
    свежее %d с (3 такта) — расписание и инициатива работают.""" % DRIVE_FRESH_SECS
    try:
        rec = json.loads(DRIVE_STATUS_FILE.read_text(encoding="utf-8"))
        ts = dt.datetime.fromisoformat(rec["ts"])
        return (dt.datetime.now() - ts).total_seconds() <= DRIVE_FRESH_SECS
    except (OSError, ValueError, KeyError):
        return False


def _bridge_alive() -> bool:
    """Живость моста ушей (Ф182, круг 30): служба пишет сердце в
    data\\voice\\status.json; свежее %d с — сторож имени + ловец фраз
    + whisper по зову слушают. Файла/свежести нет — мост не поднят
    (до круга 30 это молча значило «голосовые фразы не доходят»).""" % BRIDGE_FRESH_SECS
    try:
        rec = json.loads(BRIDGE_STATUS_FILE.read_text(encoding="utf-8"))
        ts = dt.datetime.fromisoformat(rec["ts"])
        return (dt.datetime.now() - ts).total_seconds() <= BRIDGE_FRESH_SECS
    except (OSError, ValueError, KeyError):
        return False


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="автозапуск дома Марфы")
    ap.add_argument("--config", default=str(CONFIG_FILE),
                    help="путь к start_marfa.json (по умолчанию — рядом со скриптом)")
    ap.add_argument("--в-планировщик", dest="scheduler", action="store_true",
                    help="вписать дом в автозагрузку Windows (задача «Марфа»)")
    args = ap.parse_args(argv)

    if args.scheduler:
        ok = register_scheduler()
        print("планировщик: " + ("дом вписан в автозагрузку — «Марфа» (при входе) "
                                 "и «Марфа-синхронизация» (каждые 2 часа)"
                                 if ok else "не удалось — запусти от администратора"))
        _log("планировщик: " + ("ок" if ok else "сбой"))
        return 0 if ok else 1

    cfg = ensure_config(Path(args.config))
    first_run_brain_empty = (not cfg.get("brain_cmd")
                             and not _alive(8082, "/health"))

    print("=== Старт дома Марфы ===")
    started, skipped = [], []
    for name, port, path, key, wait_secs in SERVICES:
        cmd = (cfg.get(key) or "").strip()
        if _alive(port, path):
            print("%s %d: уже жив — не трогаю" % (name, port))
            skipped.append(name)
            continue
        if not cmd:
            print("%s %d: не запущен и нет команды — впиши «%s» в %s"
                  % (name, port, key, Path(args.config).name))
            continue
        print("%s %d: поднимаю в отдельной консоли..." % (name, port))
        _spawn(cmd)
        if wait_secs <= 0:
            print("   %s разогревается — проверь позже «статус»" % name)
            started.append(name)
            continue
        if _wait(port, path, wait_secs):
            print("   ожил")
            started.append(name)
        else:
            print("   НЕ ожил за %d с — посмотри консоль %s"
                  % (wait_secs, name))
            if key == "brain_cmd":
                print("     консоль мозга закрылась сразу? команду отвергла"
                      " сборка сервера — чинит и поднимает кнопка"
                      " scripts\\92_brain_fix.bat")

    # -- уши: четвёртый слуга, не HTTP — живость по статус-файлу ----------
    # старые конфиги без ears_cmd получают команду по умолчанию (апгрейд на лету)
    ears_cmd = (cfg.get("ears_cmd") or TEMPLATE["ears_cmd"]).strip()
    if _ears_alive():
        print("уши: уже жив — слушают, не трогаю")
        skipped.append("уши")
    else:
        print("уши: поднимаю службу слуха...")
        _spawn(ears_cmd)
        print("   ухо без микрофона не умирает: пишет статус и ждёт, пока воткнёшь")
        started.append("уши")

    # -- стремление: пятый слуга — расписание и инициатива (Круг Д) -----
    # план в 08:00, дневник в 21:00, вопросы раз в минуту, чтение раз в час
    drive_cmd = (cfg.get("drive_cmd") or TEMPLATE["drive_cmd"]).strip()
    if _drive_alive():
        print("стремление: уже жив — расписание крутится, не трогаю")
        skipped.append("стремление")
    else:
        print("стремление: поднимаю службу (план, дневник, вопросы, чтение)...")
        _spawn(drive_cmd)
        print("   тик раз в минуту; упавшая работа — урок, служба не сдаётся")
        started.append("стремление")

    # -- мост ушей: шестой слуга (Ф182, круг 30) — вторая ступень слуха.
    # Уши-сторож (ступень 1) дом поднимал с рождения; мост (ступень 2:
    # ловец фраз + whisper по зову) до круга 30 ждал человеческой памяти:
    # окно консоли закрылось — и голосовые фразы умирали молча при живых
    # ушах (живой лог дня-17, дважды за день). Живость — по статус-файлу,
    # как у ушей (не HTTP-слуга). Старые конфиги без bridge_cmd получают
    # команду по умолчанию (апгрейд на лету — прецедент ears_cmd).
    bridge_cmd = (cfg.get("bridge_cmd") or TEMPLATE["bridge_cmd"]).strip()
    if _bridge_alive():
        print("мост ушей: уже жив — ловит фразы, не трогаю")
        skipped.append("мост ушей")
    else:
        print("мост ушей: поднимаю службу (сторож + фразы + whisper по зову)...")
        _spawn(bridge_cmd)
        print("   без микрофона и модели не умирает: статус и ожидание, как у ушей")
        started.append("мост ушей")

    # -- прогрев мозга (Ф84): слуги подняты — пока Создатель открывает
    #    панель, дом в фоне платит префилл статики; первый вопрос не
    #    будет стоить минуту холодного кэша
    _start_warmup()

    _log("старт: подняты %s; уже жили %s" % (started or "—", skipped or "—"))

    if first_run_brain_empty:
        print("\nМОЗГ: команда старта знает только Создатель — открой %s\n"
              "и впиши её в поле brain_cmd (один раз, насовсем)."
              % Path(args.config).name)
    print("\nдом в сборе: панель http://127.0.0.1:5001 — чат с Марфой там.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
