# -*- coding: utf-8 -*-
r"""core/fix_chroma_v4.py — разовая миграция memory.py v3 → v4 (история).

Аудит 22.11 (K1) вскрыл: ПОВТОРНЫЙ запуск старой версии скрипта был
разрушающим — вырезал всё между импортами и class Memory (в живом файле
там _norm, _tokens, _sentence, _cosine_tokens, JsonBackend, ChromaBackend),
а py_compile замечал только синтаксис: файл компилировался, [OK]
печатался, бэкап никто не откатывал. Первый же remember падал с
NameError: name '_norm' is not defined.

Правила новой версии:
- ИДЕМПОТЕНТНОСТЬ: в файле уже есть все имена — выход без единого касания;
- подозрительное состояние (есть _clean_metadata, нет остальных имён —
  след повторного запуска старого скрипта) — отказ и честный совет
  чинить из git, миграция не само-лекарство;
- бэкап с меткой времени — не затирает прежний (.v3_broken старого
  формата тоже остаётся);
- после py_compile — AST-проверка, что ВСЕ необходимые имена живы
  (M12 аудита: .pyc синтаксически целого, но семантически битого
  файла маскировал поломку до первого вызова); не живы — откат.
"""
from __future__ import annotations

import ast
import re
import shutil
import py_compile
import time
from pathlib import Path

REQUIRED_NAMES = {"_clean_metadata", "_norm", "_tokens", "_sentence",
                  "_cosine_tokens", "JsonBackend", "ChromaBackend", "Memory"}


def _top_names(text: str) -> set[str]:
    """Имена верхнего уровня (функции и классы) — по AST, не по строкам."""
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return set()
    return {n.name for n in ast.walk(tree)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}


def _find_import_end(lines: list[str]) -> int:
    import_end = 0
    seen = False
    for i, line in enumerate(lines):
        s = line.strip()
        if not s or s.startswith("#"):
            if seen:
                break
            continue
        if s.startswith(("import ", "from ")):
            import_end = i + 1
            seen = True
        elif seen:
            break
    return import_end


def _find_class_memory(lines: list[str], start: int) -> int | None:
    for i in range(start, len(lines)):
        if lines[i].startswith("class Memory"):
            return i
    return None


def apply(fp: Path) -> bool:
    """Применить миграцию v3 → v4. True — файл изменён, False — не тронут."""
    fp = Path(fp)
    if not fp.exists():
        print("[FAIL] нет файла: %s" % fp)
        return False

    text = fp.read_text(encoding="utf-8")
    names = _top_names(text)

    # 1) Идемпотентность (K1): уже исправленный файл не трогаем ВООБЩЕ
    if REQUIRED_NAMES <= names:
        print("[OK] уже применён: все имена на месте (%s) — файл не тронут"
              % ", ".join(sorted(REQUIRED_NAMES)))
        return False

    # 2) Подозрительное состояние — не лечим вслепую
    if "_clean_metadata" in names:
        print("[FAIL] файл в подозрительном состоянии: _clean_metadata есть, "
              "а остальных имён нет — похоже на след ПОВТОРНОГО запуска "
              "старой версии скрипта (K1 аудита).")
        print("       Чини из git: git checkout -- core/memory.py "
              "(и позови архитектора)")
        return False
    if "Memory" not in names:
        print("[FAIL] нет class Memory — не тот файл, миграция отменена")
        return False

    lines = text.split("\n")
    import_end = _find_import_end(lines)
    class_start = _find_class_memory(lines, import_end)
    if class_start is None:
        print("[FAIL] Не найден 'class Memory' после блока импортов.")
        return False

    print(f"\n[DIAG] import_end={import_end}, class_start={class_start}")
    print(f"[DIAG] Заменяю {class_start - import_end} строк между импортами "
          f"и class Memory:")
    print("-" * 60)
    for i in range(import_end, class_start):
        print(f"{i+1:3} | {lines[i]}")
    print("-" * 60)

    clean_func = '''def _clean_metadata(md):
    """Готовит метаданные для ChromaDB add/upsert: убирает None и пустые списки."""
    if not md:
        return {}
    out = {}
    for k, v in md.items():
        if v is None:
            continue
        if isinstance(v, (list, tuple)):
            items = [x for x in v if x is not None and isinstance(x, (bool, int, float, str))]
            if not items:
                continue
            t = type(items[0])
            items = [x for x in items if type(x) is t]
            if items:
                out[k] = items
            continue
        if isinstance(v, (bool, int, float, str)):
            out[k] = v
    return out'''

    new_lines = lines[:import_end] + ["", "", clean_func, "", ""] + lines[class_start:]
    new_text = "\n".join(new_lines)

    # обёртки metadatas=[var] — без двойной обёртки
    new_text = re.sub(
        r'metadatas=\[(?!_clean_metadata)([a-zA-Z_][a-zA-Z0-9_]*)\]',
        r'metadatas=[_clean_metadata(\1)]',
        new_text,
    )

    # бэкап с меткой времени — прежние бэкапы не затираются
    backup = fp.with_name("%s.v3_broken.%d" % (fp.name, int(time.time())))
    shutil.copy(fp, backup)
    print(f"[BACKUP] {backup}")

    fp.write_text(new_text, encoding="utf-8")

    # 3) Компиляция + SEMANTIC-проверка по AST (M12): синтаксис цел И все
    #    имена живы — иначе откат. py_compile одиноко не честен.
    try:
        py_compile.compile(str(fp), doraise=True)
        alive = _top_names(fp.read_text(encoding="utf-8"))
        missing = REQUIRED_NAMES - alive
        if missing:
            raise py_compile.PyCompileError(
                "нет имён после миграции: %s" % ", ".join(sorted(missing)))
        print("[OK] memory.py исправлен, компилируется, имена живы:")
        print("-" * 60)
        for i, l in enumerate(new_text.split("\n")[:40], 1):
            print(f"{i:3} | {l}")
        print("-" * 60)
        return True
    except py_compile.PyCompileError as e:
        shutil.copy(backup, fp)
        print(f"[FAIL] компиляция/имена: {e}")
        print("[RESTORED] Откат из бэкапа. Пришлите вывод [DIAG] выше.")
        return False


if __name__ == "__main__":
    # разовая миграция уже исполнена домом (memory.py — v4);
    # повторный запуск теперь безопасен: скажет «уже применён» и выйдет
    apply(Path(r"C:\Marfa\core\memory.py"))
