# -*- coding: utf-8 -*-
r"""МАРФА — server_sync.py: забор, распаковка и тесты на станции архитектора. v1.2

Станция = персистентная Linux-песочница архитектора (Z.ai) или любой сервер,
где работает архитектор. Файлы станции переживают смену контекста — это
долгосрочная память архитектора.

Петля (docs/SYNC_PROTOCOL_v1.md):
    Z440 --(80_sync_github.bat)--> GitHub + outgoing\marfa-*.bundle --(в чат)-->
    станция: upload\*.bundle --(server_sync.py)--> рабочая копия marfa\ + тесты
    + журнал ARCHITECT_LOG.md --(bundle)--> обратно Создателю.

Что делает этот скрипт за один запуск:
  0. Если в .env (или в переменных окружения) есть MARFA_GH_TOKEN — прямой
     забор из GitHub (fetch + merge). Токен не печатается и не попадает
     в логи: всё, что вернул git, маскируется звёздочками.
  1. Находит в upload/ самый свежий *.bundle Создателя — забирает историю в git.
  2. Находит самый свежий *.zip — распаковывает поверх рабочей копии (приём файлов).
  3. Прогоняет тесты станции: compileall (синтаксис всего кода) + pytest, если есть.
  4. Дописывает запись в docs/ARCHITECT_LOG.md — память архитектора.
  5. Обновляет bundle станции в download/ — для отправки Создателю.
  6. Если MARFA_GH_PUSH=1 и токен есть — пуш коммитов станции в GitHub
     (по умолчанию ВЫКЛЮЧЕН: канон — пуш делает только Создатель; включается
     явной резолюцией Создателя, SYNC_PROTOCOL_v1.md, раздел 4а).

Запуск (на станции):  python3 scripts/server_sync.py
Зависимости: git, python3. pytest — опционально.

.env (кладёт Создатель на сервере руками, НИКОГДА не через чат — Ф105):
    MARFA_GH_TOKEN=github_pat_...     # fine-grained PAT, Contents: Read-only
    MARFA_GH_REPO=kernedmd/marfa      # необязательно, это значение по умолчанию
    MARFA_GH_PUSH=1                   # необязательно, включает шаг 6
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

ENV_FILES = [os.path.join(ROOT, ".env"),
             os.path.abspath(os.path.join(ROOT, "..", ".env"))]
TOKEN_KEYS = ["MARFA_GH_TOKEN", "GITHUB_TOKEN", "GH_TOKEN"]
DEFAULT_REPO = "kernedmd/marfa"

CODE_DIRS = ["core", "safety", "sensors", "evolution", "growth", "web",
             "scripts", "tests"]
GIT_ENV = dict(os.environ, GIT_TERMINAL_PROMPT="0", GIT_ASKPASS="echo")

_secrets = []  # всё, что нельзя показывать (токены) — маскируется в выводе


def run(cmd, timeout=600, **kw):
    return subprocess.run(cmd, capture_output=True, text=True,
                          env=GIT_ENV, timeout=timeout, **kw)


def now():
    """Время Создателя (Europe/Moscow); при недоступной zoneinfo — локальное."""
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("Europe/Moscow")).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return datetime.now().strftime("%Y-%m-%d %H:%M")


def sh(*cmd, timeout=600):
    try:
        r = run(list(cmd), timeout=timeout)
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except subprocess.TimeoutExpired:
        return 124, "таймаут %s с: %s" % (timeout, cmd[0])


def git(*args, timeout=600):
    return sh("git", "-C", ROOT, *args, timeout=timeout)


def mask(text):
    """Спрятать токены в любом выводе — Ф105 работает и в логах станции."""
    for s in _secrets:
        if s:
            text = text.replace(s, "***")
    return text


def load_env():
    """Читает .env (KEY=VALUE) без печати значений; окружение важнее файла."""
    env = {}
    for path in ENV_FILES:
        try:
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip().strip('"').strip("'")
        except OSError:
            continue
    for k in list(env):
        if k in os.environ:
            env[k] = os.environ[k]
    for k in TOKEN_KEYS + ["MARFA_GH_REPO", "MARFA_GH_PUSH"]:
        if k in os.environ:
            env[k] = os.environ[k]
    return env


def token_of(env):
    for k in TOKEN_KEYS:
        v = env.get(k, "")
        if v:
            _secrets.append(v)
            return v
    return None


def head_rev():
    code, out = git("rev-parse", "--short", "HEAD")
    return out.strip() if code == 0 else ""


def merge_fetch_head(label):
    """Слить FETCH_HEAD; при несвязанных историях — вторая попытка."""
    code, _ = git("merge", "FETCH_HEAD", "--no-edit",
                  "-m", "приём: %s" % label)
    if code != 0:
        git("merge", "--abort")
        code, _ = git("merge", "FETCH_HEAD", "--no-edit",
                      "--allow-unrelated-histories",
                      "-m", "приём: %s (несвязанные истории)" % label)
        if code != 0:
            git("merge", "--abort")
            return False
    return True


def count_since(before):
    after = head_rev()
    if before and after:
        _, n = git("rev-list", "--count", "%s..%s" % (before, after))
        return n.strip() or "0"
    return "?"


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


def github_fetch(env):
    """Шаг 0: прямой забор из GitHub, если на сервере есть токен (Ф105: .env)."""
    token = token_of(env)
    if not token:
        return None  # канал выключен — это норма, работаем через bundle
    repo = env.get("MARFA_GH_REPO", DEFAULT_REPO).strip("/")
    url = "https://x-access-token:%s@github.com/%s.git" % (token, repo)
    before = head_rev()
    code, out = git("fetch", url, "main", timeout=300)
    out = mask(out)
    if code != 0:
        return "GitHub: недоступен (%s) — работаю дальше по bundle" % out.strip()[:120]
    if not merge_fetch_head("GitHub %s" % repo):
        return "GitHub: КОНФЛИКТ слияния — нужен архитектор руками (git status)"
    n = count_since(before)
    if n == "0":
        return "GitHub %s: уже актуально" % repo
    return "GitHub %s: +%s коммит(ов) — прямой забор" % (repo, n)


def github_push(env):
    """Шаг 6 (опция, MARFA_GH_PUSH=1): вернуть коммиты станции в GitHub."""
    if env.get("MARFA_GH_PUSH") != "1":
        return None
    token = token_of(env)
    if not token:
        return "GitHub пуш: токена нет — пропущен"
    repo = env.get("MARFA_GH_REPO", DEFAULT_REPO).strip("/")
    url = "https://x-access-token:%s@github.com/%s.git" % (token, repo)
    code, out = git("push", url, "main:main", timeout=300)
    out = mask(out)
    return ("GitHub пуш: OK" if code == 0
            else "GitHub пуш: не прошёл (%s)" % out.strip()[:120])


def import_bundle(path):
    """Забор истории из bundle Создателя."""
    base = os.path.basename(path)
    code, out = git("fetch", path, "main")
    if code != 0:
        return "ПРОВАЛ fetch %s: %s" % (base, mask(out).strip()[:200])
    before = head_rev()
    if not merge_fetch_head("bundle Создателя %s" % base):
        return "ПРОВАЛ merge %s — конфликт, нужен архитектор руками" % base
    n = count_since(before)
    if before:
        return "bundle %s: +%s коммит(ов)" % (base, n)
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
    """Тесты станции: синтаксис всего кода + pytest, если тесты есть."""
    results = []
    targets = [os.path.join(ROOT, d) for d in CODE_DIRS
               if os.path.isdir(os.path.join(ROOT, d))]
    if not targets:
        targets = [ROOT]
    code, out = sh(sys.executable, "-m", "compileall", "-q", *targets)
    results.append(("compileall (синтаксис кода)",
                    "OK" if code == 0 else "ПРОВАЛ\n" + out[-500:]))

    has_pytests = False
    tests_dir = os.path.join(ROOT, "tests")
    if os.path.isdir(tests_dir):
        for _dp, _dn, fns in os.walk(tests_dir):
            if any(f.startswith("test_") and f.endswith(".py") for f in fns):
                has_pytests = True
                break
    if has_pytests:
        code, out = sh(sys.executable, "-m", "pytest", tests_dir, "-q",
                       timeout=900)
        results.append(("pytest дома",
                        "OK\n" + out.strip()[-800:] if code == 0
                        else "ПРОВАЛ (код %s)\n%s" % (code, out.strip()[-800:])))
    else:
        results.append(("pytest дома",
                        "НЕТ test_*.py на станции — жду код дома (bundle/GitHub)"))
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
    try:
        os.makedirs(DOWNLOAD, exist_ok=True)
    except OSError:
        return None
    out = os.path.join(DOWNLOAD, "marfa-station-%s.bundle" % stamp)
    code, _ = git("bundle", "create", out, "main")
    return out if code == 0 else None


def main():
    print("=" * 60)
    print("МАРФА — станция архитектора: синхронизация (v1.2)")
    print("=" * 60)

    msg = ensure_repo()
    events = [msg] if msg else []
    env = load_env()

    g = github_fetch(env)
    if g is not None:
        events.append(g)
        print("[0]", g)
    else:
        print("[0] GitHub-токена нет — прямой забор выключен (канал: bundle)")

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

    p = github_push(env)
    if p:
        events.append(p)
        print("[6]", p)
    print("=" * 60)


if __name__ == "__main__":
    main()
