# -*- coding: utf-8 -*-
r"""МАРФА — inventory_audit.py: инвентаризация дома перед коммитом. v1.0

Отвечает на вопрос Создателя перед пушем в GitHub: «что именно уйдёт в git,
что останется в доме и сколько это весит» (правило 2.4: рантайм в git не
попадает; крупные файлы — LFS или исключение).

Где запускать:
    Z440:    cd C:\Marfa && venv\Scripts\python.exe scripts\inventory_audit.py
    станция: python3 scripts/inventory_audit.py [--root ПУТЬ]

Что делает за один запуск:
  1. Обходит дерево дома (символические ссылки не преследует, циклы режет).
  2. Выносит вердикт каждому файлу: В GIT или ИГНОР — по настоящему .gitignore
     (git check-ignore, если репозиторий найден), иначе по встроенному списку
     канона (models/, venv/, *.gguf, .env и т.д.).
  3. Показывает расхождения: правила канона, которых нет в .gitignore дома.
  4. Считает размеры: итог, по каталогам первого уровня, топ-N самых больших.
  5. Флаги: файлы >50 МБ (их уберёт 80_sync_github.bat) и >100 МБ (LFS или
     исключение).
  6. Предупреждения: .env вне игнора, вложенные git-копии.
  7. Пишет отчёт в консоль и в logs\inventory_audit.log (если logs/ есть),
     по желанию — машинный JSON (--json ПУТЬ).

Токены и содержимое .env не читает и не печатает. Выходной код: 0 — чисто,
1 — есть критические предупреждения (что-то опасное могло бы попасть в коммит).

Зависимости: только стандартная библиотека; git — опционально.
"""

import argparse
import fnmatch
import json
import os
import subprocess
import sys
from datetime import datetime

# --- канон исключений (зеркало ensure_gitignore из 80_sync_github.bat) -------

DIR_IGNORE = {
    "models", "downloads", "venv", "python311", "tools", "data", "logs",
    "incoming", "outgoing", "__pycache__", ".pytest_cache", "llama.cpp",
    "node_modules", "marfa", ".git", ".idea", ".vscode",
}
FILE_GLOBS = ["*.gguf", "*.safetensors", "*.bundle", "*.pyc", ".env", ".env.*"]

MB = 1024 * 1024
BIG_50 = 50 * MB    # страховка 80_sync_github.bat
BIG_100 = 100 * MB  # порог LFS из задачи Создателя
WALK_CAP = 500_000  # предохранитель от циклов и гигантских деревьев


def human(n):
    """Размер в человеческих единицах, десятичная запятая."""
    x = float(n)
    for unit in ("Б", "КБ", "МБ", "ГБ", "ТБ"):
        if x < 1024 or unit == "ТБ":
            s = ("%d" % x) if unit == "Б" else ("%.1f" % x)
            return s.replace(".", ",") + " " + unit
        x /= 1024


def num(n):
    return format(n, ",").replace(",", " ")


def files_word(n):
    """Файл/файла/файлов — русская плюрализация."""
    n = abs(n) % 100
    if 11 <= n <= 14:
        return "файлов"
    n %= 10
    if n == 1:
        return "файл"
    if 2 <= n <= 4:
        return "файла"
    return "файлов"


def now():
    return datetime.now().strftime("%d.%m.%Y %H:%M")


def relname(path, root):
    """Относительный путь с прямыми слэшами — канон для git и отчёта."""
    return os.path.relpath(path, root).replace(os.sep, "/")


def builtin_verdict(rel, is_dir=False):
    """Вердикт по встроенному списку канона: True = игнорировать."""
    parts = rel.split("/")
    if is_dir:
        return parts[-1].lower() in DIR_IGNORE
    if any(fnmatch.fnmatch(parts[-1].lower(), g.lower()) for g in FILE_GLOBS):
        return True
    return any(p.lower() in DIR_IGNORE for p in parts[:-1])


def _check_ignore(root, chunk):
    """Один вызов git check-ignore. None — если git/репозиторий недоступны."""
    cmd = ["git", "-C", root, "check-ignore", "-z", "--stdin"]
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0")
    try:
        proc = subprocess.run(cmd, input="\x00".join(chunk), capture_output=True,
                              text=True, encoding="utf-8", errors="replace",
                              env=env, timeout=120)
    except Exception:
        return None
    if proc.returncode not in (0, 1):
        return None
    ignored = set(x for x in proc.stdout.split("\x00") if x)
    return {p: (p in ignored) for p in chunk}


def git_verdicts(root, paths):
    """Вердикты по настоящему .gitignore. None при сбое (смена источника)."""
    out = {}
    for i in range(0, len(paths), 1000):
        r = _check_ignore(root, paths[i:i + 1000])
        if r is None:
            return None
        out.update(r)
    return out


def _quick_size(dirpath, root):
    """Размер игнорируемого поддерева одним проходом + крупные файлы (>50 МБ)."""
    total, cnt, big = 0, 0, []
    for dp, _dn, fns in os.walk(dirpath, followlinks=False):
        for name in fns:
            try:
                s = os.lstat(os.path.join(dp, name)).st_size
            except OSError:
                continue
            total += s
            cnt += 1
            if s > BIG_50:
                big.append((relname(os.path.join(dp, name), root), s))
    return total, cnt, big


def walk_tree(root):
    """Обход дерева. Элемент: (rel, size, is_dir_quick, files_inside|None)."""
    entries, errors, seen = [], [], set()
    quick_bigs = []
    count = 0
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False,
                                                onerror=lambda e: errors.append(str(e))):
        if count > WALK_CAP:
            errors.append("обход остановлен: больше %d файлов" % WALK_CAP)
            break
        dp_real = os.path.realpath(dirpath)
        if dp_real != os.path.realpath(root) and dp_real in seen:
            dirnames[:] = []
            continue
        seen.add(dp_real)
        rel_dir = relname(dirpath, root)
        if rel_dir != "." and builtin_verdict(rel_dir, is_dir=True):
            total, cnt, big = _quick_size(dirpath, root)
            entries.append((rel_dir, total, True, cnt))
            quick_bigs.extend(big)
            dirnames[:] = []
            continue
        for name in filenames:
            fp = os.path.join(dirpath, name)
            try:
                st = os.lstat(fp)
            except OSError as e:
                errors.append("%s: %s" % (relname(fp, root), e))
                continue
            entries.append((relname(fp, root), st.st_size, False, None))
            count += 1
    return entries, errors, quick_bigs


def main():
    ap = argparse.ArgumentParser(description="МАРФА: инвентаризация дома перед коммитом")
    ap.add_argument("--root", default=os.getcwd(), help="корень дома (по умолчанию текущий)")
    ap.add_argument("--top", type=int, default=20, help="сколько самых больших файлов показать")
    ap.add_argument("--json", help="путь для машинного отчёта JSON")
    ap.add_argument("--log", help="путь файла отчёта (по умолчанию logs/inventory_audit.log)")
    args = ap.parse_args()

    root = os.path.abspath(args.root)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    lines = []
    def say(s=""):
        print(s)
        lines.append(s)

    say("=" * 64)
    say(" МАРФА — инвентаризация дома перед коммитом")
    say(" Корень: %s · %s · python %s" % (root, now(), sys.version.split()[0]))

    entries, errors, quick_bigs = walk_tree(root)

    # вердикты: встроенный канон, затем уточнение настоящим .gitignore
    builtin = {}
    for rel, _s, is_dir, _c in entries:
        builtin[rel] = builtin_verdict(rel.rstrip("/"), is_dir=is_dir)
    for rel, _s in quick_bigs:  # крупные внутри игнорируемых каталогов
        builtin[rel] = True
    gv = git_verdicts(root, list(builtin.keys()))
    if gv is None:
        verdicts = builtin
        say(" Источник вердиктов: встроенный список канона (git недоступен)")
    else:
        verdicts = gv
        say(" Источник вердиктов: git check-ignore (настоящий .gitignore)")
    # .git не бывает в правилах .gitignore — исключён самим git; ставим вердикт сами
    for rel in list(verdicts):
        if ".git" in rel.split("/"):
            verdicts[rel] = True
    for rel, _s in quick_bigs:  # крупные из игнорируемых каталогов — тоже игнор
        verdicts[rel] = True

    total_n = total_b = git_n = git_b = ign_n = ign_b = 0
    by_top = {}
    largest = []
    over50, over100 = [], []          # крупные, которые пошли бы в коммит
    over50_all, over100_all = [], []  # все крупные дома (вопрос LFS/исключения)
    mismatches = []

    for rel, size, is_dir, cnt in entries:
        parts = rel.split("/")
        top = parts[0] if (len(parts) > 1 or is_dir) else "(корень)"
        ign = verdicts[rel]
        if not is_dir and builtin.get(rel) and not ign:
            mismatches.append(rel)  # канон говорит «игнор», .gitignore — нет
        n = cnt if is_dir else 1
        total_n += n
        total_b += size
        d = by_top.setdefault(top, {"n": 0, "b": 0, "ign_n": 0, "ign_b": 0})
        d["n"] += n
        d["b"] += size
        if ign:
            ign_n += n
            ign_b += size
            d["ign_n"] += n
            d["ign_b"] += size
        else:
            if is_dir:  # не игнорируемый «быстрый» каталог не бывает, но защитимся
                continue
            git_n += 1
            git_b += size
        largest.append((rel, size, ign))
        if not is_dir:
            if size > BIG_50:
                over50_all.append((rel, size, ign))
            if size > BIG_100:
                over100_all.append((rel, size, ign))
            if not ign:
                if size > BIG_50:
                    over50.append((rel, size))
                if size > BIG_100:
                    over100.append((rel, size))
    for rel, size in quick_bigs:  # крупные жильцы игнорируемых каталогов
        over50_all.append((rel, size, True))
        if size > BIG_100:
            over100_all.append((rel, size, True))
        largest.append((rel, size, True))

    nested_repos = []
    for top in sorted(by_top):
        if top != "(корень)" and os.path.isdir(os.path.join(root, top, ".git")):
            nested_repos.append(top + "/")
    if os.path.isdir(os.path.join(root, "marfa")):
        if "marfa/" not in nested_repos:
            nested_repos.append("marfa/")

    critical = []
    if os.path.exists(os.path.join(root, ".env")) and not verdicts.get(".env", True):
        critical.append(".env НЕ в .gitignore — секрет уйдёт в git!")
    for rel, _s in over50:
        critical.append("файл >50 МБ идёт в git: %s — добавь правило в .gitignore" % rel)

    say("=" * 64)
    say(" ИТОГ")
    say("   файлов учтено:        %s · %s" % (num(total_n), human(total_b)))
    say("   В GIT ПОЙДЁТ:         %s %s · %s" % (num(git_n), files_word(git_n), human(git_b)))
    say("   ОСТАНЕТСЯ В ДОМЕ:     %s %s · %s (игнор)" % (num(ign_n), files_word(ign_n), human(ign_b)))
    say("")
    say(" ПО КАТАЛОГАМ ПЕРВОГО УРОВНЯ")
    for top in sorted(by_top, key=lambda t: -by_top[t]["b"]):
        d = by_top[top]
        verdict = "ИГНОР" if d["ign_b"] >= d["b"] * 0.98 else \
                  ("В GIT" if d["ign_b"] == 0 else "СМЕШАННЫЙ")
        say("   %-24s %8s шт  %10s  %s" % (top[:24], num(d["n"]), human(d["b"]), verdict))
    say("")
    say(" САМЫЕ БОЛЬШИЕ ФАЙЛЫ И КАТАЛОГИ (топ-%d)" % args.top)
    for rel, size, ign in sorted(largest, key=lambda x: -x[1])[:args.top]:
        say("   %-54s %10s  %s" % (rel[:54], human(size), "ИГНОР" if ign else "В GIT"))
    say("")
    say(" ФЛАГИ КРУПНЫХ ФАЙЛОВ (весь дом, не только коммит)")
    if over100_all:
        safe100 = all(ign for _r, _s, ign in over100_all)
        say("   >100 МБ: %s %s — %s" % (num(len(over100_all)), files_word(len(over100_all)),
            "все уже исключены из коммита (LFS не нужен)" if safe100
            else "ЕСТЬ ИДУЩИЕ В КОММИТ — LFS или исключение до пуша!"))
        for rel, size, ign in sorted(over100_all, key=lambda x: -x[1])[:10]:
            say("     · %-52s %10s  %s" % (rel[:52], human(size), "ИГНОР" if ign else "В GIT!!"))
    else:
        say("   >100 МБ: 0 — крупных файлов в доме нет")
    if over50_all:
        safe50 = all(ign for _r, _s, ign in over50_all)
        say("   >50 МБ:  %s %s — %s" % (num(len(over50_all)), files_word(len(over50_all)),
            "все уже исключены; страховка 80_sync_github.bat на страже" if safe50
            else "ЕСТЬ ИДУЩИЕ В КОММИТ — страховка 80_sync_github.bat снимет их сама"))
    else:
        say("   >50 МБ:  0")
    say("")
    say(" ПРЕДУПРЕЖДЕНИЯ")
    env_safe = not os.path.exists(os.path.join(root, ".env")) or verdicts.get(".env", True)
    say("   [OK] .env вне коммита" if env_safe else "   [!!] .env НЕ игнорируется!")
    for nr in nested_repos:
        say("   [!] вложенная копия проекта: %s — в git не идёт (правило канона marfa/)" % nr)
    for rel in mismatches[:10]:
        say("   [!] канон требует игнора, но в .gitignore правила нет: %s — допишет 80_sync_github.bat" % rel)
    if mismatches:
        say("       всего расхождений: %d" % len(mismatches))
    if errors:
        say("   [!] ошибок обхода: %d (первая: %s)" % (len(errors), errors[0][:80]))
        for e in errors[:5]:
            say("       %s" % e[:100])
    if env_safe and not nested_repos and not mismatches and not errors:
        say("   [OK] вложенных git-копий и расхождений нет")
    say("=" * 64)
    say(" Вердикт: " + ("КРИТИЧЕСКИХ НЕТ — пуш безопасен" if not critical
                        else "ЕСТЬ КРИТИЧЕСКИЕ — сначала закрой предупреждения"))
    for c in critical:
        say("   [!!] %s" % c)

    log_path = args.log
    if not log_path and os.path.isdir(os.path.join(root, "logs")):
        log_path = os.path.join(root, "logs", "inventory_audit.log")
    if log_path:
        try:
            os.makedirs(os.path.dirname(os.path.abspath(log_path)), exist_ok=True)
            with open(log_path, "a", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n\n")
            say(" Отчёт дописан: %s" % log_path)
        except OSError as e:
            say(" [!] отчёт не записан: %s" % e)

    if args.json:
        payload = {
            "root": root, "generated": now(),
            "total_files": total_n, "total_bytes": total_b,
            "git_files": git_n, "git_bytes": git_b,
            "ignored_files": ign_n, "ignored_bytes": ign_b,
            "dirs": [{"name": t, **by_top[t]} for t in sorted(by_top)],
            "over50": [{"path": p, "bytes": s} for p, s in over50],
            "over100": [{"path": p, "bytes": s} for p, s in over100],
            "over50_all": [{"path": p, "bytes": s, "ignored": i} for p, s, i in over50_all],
            "over100_all": [{"path": p, "bytes": s, "ignored": i} for p, s, i in over100_all],
            "warnings": {"env_unsafe": not env_safe, "nested_repos": nested_repos,
                         "canon_mismatches": mismatches[:50],
                         "walk_errors": errors[:20]},
            "critical": critical,
        }
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        say(" JSON: %s" % args.json)

    return 1 if critical else 0


if __name__ == "__main__":
    sys.exit(main())
