# -*- coding: utf-8 -*-
"""evolution/changelog.py — №24 «ЛОГБУК ФИШЕЙ»: CHANGELOG.md из git log.

Роадмап просил маску «Г-N:», но живой дом выработал свой канон: ПЕРВАЯ
СТРОКА КОММИТА и есть выжимка фичи (орган + № + суть). Логбук честен
к канону: каждая строка CHANGELOG — первый предложенный кусок коммита,
длинные режутся, тег «№N» выделяется жирным.

Сборка: git log --date=short --pretty=format:%h|%ad|%s → группировка
по дням → CHANGELOG.md в корне репозитория. Команда «логбук».
Швы: _git_log / _repo_root — тесты подменяют, реальный git не нужен.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

from core import config

SUBJECT_CAP = 160        # первая строка коммита — уже выжимка; дальше — обрезаем
GIT_TIMEOUT_SEC = 30

# тег фичи в начале строки: «глаза №2 «найди на экране»:» — до двоеточия
_TAG_RX = re.compile(r"^(.*?№\d+[^:：]*)[：:]\s*")


def _git_log(root: Path) -> list:
    """git log одной строкой на коммит: hash|date|subject. Шов для тестов."""
    r = subprocess.run(
        ["git", "log", "--date=short", "--pretty=format:%h|%ad|%s"],
        cwd=str(root), capture_output=True, text=True, timeout=GIT_TIMEOUT_SEC,
        encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise RuntimeError("git log не вышел: %s"
                           % (r.stderr or "").strip()[:120])
    return [l for l in (r.stdout or "").splitlines() if l.strip()]


def _repo_root() -> Path:
    """Корень репозитория КОДА — логбук пишет в книгу того дома, чей
    это код (на станции — сам C:\\Marfa).

    УРОК ДЕГРАДАЦИИ КНИГИ (23.11, утро): корень резолвился от HOME_DIR,
    а в песочнице и симуляциях станции HOME_DIR — посторонний git-контекст
    (или его нет вовсе); туда же добавилась утечка теста, писавшего в
    Path(".") — батарея от корня перезаписывала настоящий CHANGELOG.md
    фикстурой из пяти коммитов. Порядок теперь строгий:
    СНАЧАЛА rev-parse от папки этого модуля (папка кода живёт в его
    репозитории — станция, песочница и клоны симуляции получают каждый
    свою книгу), ПОТОМ от HOME_DIR (код установлен россыпью — книгу
    ведём у дома). Не вышло — HOME_DIR как есть: логбук живёт у дома,
    а не у cwd (урок N4: запуск из другой папки дом не переезжает).
    """
    for base in (Path(__file__).resolve().parent.parent, config.HOME_DIR):
        try:
            r = subprocess.run(["git", "rev-parse", "--show-toplevel"],
                               cwd=str(base), capture_output=True,
                               text=True, timeout=10)
            if r.returncode == 0 and r.stdout.strip():
                return Path(r.stdout.strip())
        except Exception:
            continue
    return Path(config.HOME_DIR)


def parse_log(lines) -> list:
    """Строки «hash|date|subject» → записи. Мусор (не тройка, пустые
    поля) пропускается молча — логбук не падает от кривой строки."""
    entries = []
    for line in lines:
        parts = str(line).split("|", 2)
        if len(parts) != 3:
            continue
        h, date, subj = parts[0].strip(), parts[1].strip(), parts[2].strip()
        if not h or not date or not subj:
            continue
        entries.append({"hash": h, "date": date, "subject": subj})
    return entries


def _plural_commits(n: int) -> str:
    if n % 10 == 1 and n % 100 != 11:
        return "%d коммит" % n
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return "%d коммита" % n
    return "%d коммитов" % n


def commits_note(rep: dict) -> str:
    """Человекоческая строка о собранном логбуке (для чата)."""
    return _plural_commits(int(rep.get("commits") or 0))


def render_changelog(entries) -> str:
    """Markdown: дни секциями (новые сверху), в дне — по коммиту."""
    days: list = []
    cur_date, cur = None, []
    for e in entries:
        if e["date"] != cur_date:
            if cur:
                days.append((cur_date, cur))
            cur_date, cur = e["date"], []
        cur.append(e)
    if cur:
        days.append((cur_date, cur))
    first = entries[0]["date"] if entries else "—"
    last = entries[-1]["date"] if entries else "—"
    lines = [
        "# Марфа — логбук фишек (CHANGELOG)",
        "",
        "История дома из git log: первая строка каждого коммита в этом",
        "доме — выжимка фичи. Собрано командой «логбук»:",
        "%s, %s — %s." % (_plural_commits(len(entries)), last, first),
        "",
    ]
    for date, day in days:
        lines.append("## %s — %s" % (date, _plural_commits(len(day))))
        lines.append("")
        for e in day:
            subj = e["subject"]
            if len(subj) > SUBJECT_CAP:
                subj = subj[:SUBJECT_CAP - 1].rstrip() + "…"
            m = _TAG_RX.match(subj)
            if m:
                lines.append("- **%s** — %s" % (m.group(1).strip(),
                                                subj[m.end():]))
            else:
                lines.append("- %s" % subj)
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def write_changelog(root=None) -> dict:
    """Собрать и записать CHANGELOG.md в корень репозитория.
    Возвращает {commits, days, file}. Пустой лог — честный отказ.

    Корень резолвится в АБСОЛЮТНЫЙ путь (урок деградации: относительный
    корень из теста дотянулся до настоящего файла книги) — путь в отчёте
    всегда показывает, КУДА легла книга, без двусмысленности cwd.
    """
    root = (Path(root) if root is not None else _repo_root()).resolve()
    entries = parse_log(_git_log(root))
    if not entries:
        raise RuntimeError("git log пуст — логбук не из чего собирать")
    md = render_changelog(entries)
    out = root / "CHANGELOG.md"
    out.write_text(md, encoding="utf-8")
    return {"commits": len(entries),
            "days": len({e["date"] for e in entries}),
            "file": str(out)}
