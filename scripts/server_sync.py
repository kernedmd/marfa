# -*- coding: utf-8 -*-
r"""МАРФА — server_sync.py: забор, распаковка и тесты на станции архитектора. v1.0

Станция = персистентная Linux-песочница архитектора (Z.ai). Файлы станции
переживают смену контекста — это долгосрочная память архитектора.

Петля (docs/SYNC_PROTOCOL_v1.md):
    Z440 --(80_sync_github.bat)--> GitHub + outgoing\marfa-*.bundle --(в чат)-->
    станция: upload\*.bundle --(server_sync.py)--> рабочая копия marfa\ + тесты
    + журнал ARCHITECT_LOG.md --(bundle)--> обратно Создателю.

Что делает этот скрипт за один запуск:
  1. Находит в upload/ самый свежий *.bundle Создателя — забирает историю в git.
  2. Находит самый свежий *.zip — распаковывает поверх рабочей копии (приём файлов).
  3. Прогоняет тесты станции: compileall (синтаксис всего кода) + pytest, если есть.
  4. Дописывает запись в docs/ARCHITECT_LOG.md — память архитектора.
  5. Обновляет bundle станции в download/ — для отправки Создателю.

Запуск (на станции):  python3 scripts/server_sync.py
Зависимости: git, python3. pytest — опционально.
"""
import os
import subprocess
import sys
import zipfile
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UPLOAD = os.path.abspath(os.path.join(ROOT, "..", "upload"))
DOWNLOAD = os.path.abspath(os.path.join(ROOT, "..", "download"))
LOG = os.path.join(ROOT, "docs", "ARCHITECT_LOG.md")

GIT = ["git", "-C", ROOT]


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def now():
    """Время Создателя (Europe/Moscow); при недоступной zoneinfo — локальное."""
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("Europe/Moscow")).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return datetime.now().strftime("%Y-%m-%d %H:%M")


def sh(*cmd):
    r = run(list(cmd))
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def git(*args):
    return sh(*GIT, *args)


def head_rev():
    """Короткий хеш HEAD или пустая строка, если коммитов ещё нет."""
    code, out = git("rev-parse", "--short", "HEAD")
    return out.strip() if code == 0 else ""


def newest(pattern):
    if not os.path.isdir(UPLOAD):
        return None
    files = [os.path.join(UPLOAD, f) for f in os.listdir(UPLOAD)
             if f.lower().endswith(pattern) and not f.startswith(".")]
    return max(files, key=os.path.getmtime) if files else None


def ensure_repo():
    if not os.path.isdir(os.path.join(ROOT, ".git")):
        code, _ = git("init", "-b", "main")
        if code != 0:
            print("git init не удался")
            sys.exit(1)
        git("config", "user.name", "Z.ai Архитектор")
        git("config", "user.email", "architect@marfa.local")
        return "репозиторий станции создан (main)"
    return None


def import_bundle(path):
    """Забор истории из bundle Создателя."""
    base = os.path.basename(path)
    code, out = git("fetch", path, "main")
    if code != 0:
        return "ПРОВАЛ fetch %s: %s" % (base, out.strip()[:200])
    before = head_rev()
    code, _ = git("merge", "FETCH_HEAD", "--no-edit",
                  "-m", "приём: bundle Создателя %s" % base)
    if code != 0:
        git("merge", "--abort")
        code, _ = git("merge", "FETCH_HEAD", "--no-edit",
                      "--allow-unrelated-histories",
                      "-m", "приём: bundle Создателя %s (несвязанные истории)" % base)
        if code != 0:
            git("merge", "--abort")
            return "ПРОВАЛ merge %s — конфликт, нужен архитектор руками" % base
    after = head_rev()
    if before:
        _, n = git("rev-list", "--count", "%s..%s" % (before, after))
        return "bundle %s: +%s коммит(ов)" % (base, n.strip() or "?")
    return "bundle %s: история принята (первый контакт станции)" % base


def import_zip(path):
    """Распаковка zip поверх рабочей копии (приём файлов Создателя)."""
    base = os.path.basename(path)
    try:
        with zipfile.ZipFile(path) as z:
            z.extractall(ROOT)
    except Exception as e:
        return "ПРОВАЛ распаковки %s: %s" % (base, e)
    git("add", "-A")
    code, _ = git("commit", "-m", "приём: архив Создателя %s" % base)
    return "zip %s: распакован и закоммичен" % base if code == 0 else \
           "zip %s: распакован, новых изменений нет" % base


def run_tests():
    """Тесты станции: синтаксис всего кода + pytest, если он есть и есть тесты."""
    results = []
    code, out = sh(sys.executable, "-m", "compileall", "-q",
                   os.path.join(ROOT, "scripts"), os.path.join(ROOT, "tests"),
                   os.path.join(ROOT, "core") if os.path.isdir(os.path.join(ROOT, "core")) else ROOT)
    ok = code == 0
    results.append(("compileall (синтаксис кода)", "OK" if ok else "ПРОВАЛ\n" + out[-500:]))

    tests_dir = os.path.join(ROOT, "tests")
    has_pytests = os.path.isdir(tests_dir) and any(
        f.startswith("test_") and f.endswith(".py") for f in os.listdir(tests_dir))
    if has_pytests:
        code, out = sh(sys.executable, "-m", "pytest", tests_dir, "-q")
        results.append(("pytest дома", "OK\n" + out.strip()[-800:] if code == 0
                        else "ПРОВАЛ (код %s)\n%s" % (code, out.strip()[-800:])))
    else:
        results.append(("pytest дома", "НЕТ test_*.py на станции — жду bundle с кодом дома"))
    return results


def append_log(events, tests):
    head = head_rev()
    lines = ["", "## %s — синхронизация станции" % now(), "- HEAD: `%s`" % head]
    for e in events:
        lines.append("- %s" % e)
    for name, res in tests:
        first = res.splitlines()[0] if res else ""
        lines.append("- тесты: %s — %s" % (name, first))
    with open(LOG, "a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    git("add", "-A")
    git("commit", "-m", "журнал станции: %s" % now())


def export_bundle():
    stamp = now().replace("-", "").replace(":", "").replace(" ", "-")
    out = os.path.join(DOWNLOAD, "marfa-station-%s.bundle" % stamp)
    code, _ = git("bundle", "create", out, "main")
    return out if code == 0 else None


def main():
    print("=" * 60)
    print("МАРФА — станция архитектора: синхронизация")
    print("=" * 60)

    msg = ensure_repo()
    events = [msg] if msg else []

    b = newest(".bundle")
    if b:
        events.append(import_bundle(b))
        print("[1]", events[-1])
    else:
        print("[1] Bundle в upload/ нет — станция работает с текущим состоянием")

    z = newest(".zip")
    if z and "architect_pack" not in z:
        events.append(import_zip(z))
        print("[2]", events[-1])
    else:
        print("[2] Архивов от Создателя нет")

    print("[3] Тесты станции:")
    tests = run_tests()
    for name, res in tests:
        print("    -", name, "->", res.splitlines()[0])

    append_log([e for e in events if e], tests)
    print("[4] Журнал дополнен:", LOG)

    out = export_bundle()
    if out:
        print("[5] Bundle станции:", out)
        print("    (отправь его Создателю — он положит в C:\\Marfa\\incoming\\")
        print("     и нажмёт scripts\\80_sync_github.bat)")
    print("=" * 60)


if __name__ == "__main__":
    main()
