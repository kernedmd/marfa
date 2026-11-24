# -*- coding: utf-8 -*-
r"""core/loghygiene.py — Ф96 «ГИГИЕНА ЖУРНАЛОВ» (день-13, круг 17):
ротация одним законом для всех журналов-копилок дома.

Разведка круга (архитектор, не ТЗ): журналы пишутся КАЖДЫМ ходом и
живут месяцами, а мастер-ТЗ о них молчало. Две тени одной дыры:
  - диск не бесконечен: brain_log.jsonl растёт строкой на каждую
    генерацию (ответ ЦЕЛИКОМ, день-9 — ~150 КБ живого дня), за год
    это десятки МБ; ears/monitor/repair/hands — та же порода;
  - читатель «пульса» тащил файл ЦЕЛИКОМ (daypulse._read_records):
    за месяцы жизни каждая команда «пульс» парсила бы весь архив.

ЗАКОН ПИСАТЕЛЯ (Ф96): один вход — append_line(). Дороже порога
LOG_ROTATE_BYTES (8 МБ) — файл закрывается в архив путь.1.jsonl,
архивы сдвигаются (путь.2 → путь.3 …), хранится LOG_ROTATE_KEEP (3),
старейший уходит честно. Лениво: без ротации цена — один stat.
ИСКЛЮЧЕНИЕ с причиной: guard_log.jsonl — ХЕШ-ЦЕПЬ стража (ТЗ 3.7),
целостность цепи важнее размера — страж через дверь НЕ ходит и
ротации не подлежит (якорь требует этого поимённо).

ЗАКОН ЧИТАТЕЛЯ (Ф98): ротация может случиться среди дня, поэтому
«сегодня» имеет право лежать и в архиве. Читатель берёт
recent_paths() — ограниченное множество «архивы по старшинству +
текущий»: цена чтения ограничена ЗАКОНОМ (keep+1 файлов), а не
календарём жизни организма.

Гигиена — не орган дыхания: ротация упала (OSError) — запись живёт
дальше, честный сбой молчит (как бэкап и печать: правда для архива
не роняет разговор).
"""
from __future__ import annotations

from pathlib import Path

from core import config


def _archive_path(path: Path, n: int) -> Path:
    """brain_log.jsonl → brain_log.1.jsonl (имя узнаваемо для «хвост»)."""
    return path.with_name("%s.%d%s" % (path.stem, n, path.suffix))


def rotate_if_big(path: Path,
                  max_bytes: int | None = None,
                  keep: int | None = None) -> bool:
    """Ленивая ротация ДО записи. True — ротация случилась.

    Сдвиг честный, без пустышек: .2→.3, .1→.2, текущий→.1; старейший
    (.keep) уходит. OSError — не орган дыхания: молча False, запись
    должна жить дальше.
    """
    try:
        limit = config.LOG_ROTATE_BYTES if max_bytes is None else max_bytes
        depth = config.LOG_ROTATE_KEEP if keep is None else keep
        if not path.exists() or path.stat().st_size < limit:
            return False
        oldest = _archive_path(path, depth)
        if oldest.exists():
            oldest.unlink()
        for n in range(depth - 1, 0, -1):
            src = _archive_path(path, n)
            if src.exists():
                src.replace(_archive_path(path, n + 1))
        path.replace(_archive_path(path, 1))
        return True
    except OSError:
        return False


def append_line(path: Path, text: str) -> None:
    """ЕДИНАЯ ДВЕРЬ журналов-копилок: ротация + дописывание строки.

    text — уже готовая строка с \n на конце (как писали раньше); дверь
    не меняет содержимое — только закон объёма. Писать копилки в
    обход двери нельзя (якорь круга проверяет всех писателей).
    Ротация упала — запись всё равно живёт: гигиена не роняет правду.
    """
    try:
        rotate_if_big(path)
    except OSError:
        pass   # не орган дыхания: архив не спорит с разговором
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(text)


def recent_paths(path: Path, keep: int | None = None) -> list[Path]:
    """Читателю (Ф98): существующие [архив старейший … новейший, текущий].

    Порядок старшинства — читатель идёт по списку и видит день в
    хронологии даже после ротации среди дня. Множество ограничено
    тем же законом (keep архивов + текущий) — «пульс» не платит
    календарём жизни организма.
    """
    depth = config.LOG_ROTATE_KEEP if keep is None else keep
    out: list[Path] = []
    for n in range(depth, 0, -1):
        p = _archive_path(path, n)
        if p.exists():
            out.append(p)
    if path.exists():
        out.append(path)
    return out


def journal_paths() -> list[Path]:
    """Журналы-копилки под законом ротации (страж здесь НЕ живёт —
    хеш-цепь, честное исключение с причиной; якорь проверяет)."""
    return [config.BRAIN_LOG_FILE, config.EARS_LOG_FILE,
            config.MONITOR_LOG_FILE, config.REPAIR_LOG_FILE,
            config.HANDS_LOG_FILE]


def _fmt(n: float) -> str:
    """Байты по-человечески, по-русски (запятая — закон дома): «2,1 МБ»."""
    for unit, k in (("МБ", 1024 * 1024), ("КБ", 1024)):
        if n >= k:
            return ("%.1f %s" % (n / k, unit)).replace(".", ",")
    return "%d Б" % n


def render() -> str:
    """Ф99 «ГИГИЕНА ДОМА»: журналы лицом — живые размеры, архивы,
    закон и честное исключение. Мозг молчит: это факты файловой
    системы, а не фантазии 30B."""
    try:
        limit = config.LOG_ROTATE_BYTES
        depth = config.LOG_ROTATE_KEEP
        rows = []
        for path in journal_paths():
            try:
                size = path.stat().st_size if path.exists() else 0
            except OSError:
                size = 0
            arcs = len(recent_paths(path)) - (1 if path.exists() else 0)
            why = ("мозг: строка на каждую генерацию"
                   if path == config.BRAIN_LOG_FILE else "")
            rows.append("  • %s — %s, архивов %d%s"
                        % (path.name, _fmt(size), arcs,
                           (" (" + why + ")") if why else ""))
        return ("ГИГИЕНА ДОМА — журналы: правда для архива, ротация "
                "одним законом.\n"
                "Закон (Ф96): журнал дороже %s закрывается в архив, "
                "хранится %d, старейший уходит; писатели ходят через "
                "одну дверь — мимо нельзя.\n%s\n"
                "Честное исключение: %s — хеш-цепь стража (ТЗ 3.7): "
                "целостность цепи важнее размера, ротации не подлежит.\n"
                "Читатели («пульс», «энергия») читают текущий файл и "
                "архивы — «сегодня» не теряется при ротации среди дня "
                "(Ф98)."
                % (_fmt(limit), depth, "\n".join(rows),
                   config.GUARD_LOG_FILE.name))
    except Exception as e:
        return ("гигиена: не смогла осмотреть журналы (%s: %s) — "
                "скажи архитектору" % (type(e).__name__, e))
