import re
import shutil
import py_compile
from pathlib import Path

fp = Path(r"C:\Marfa\core\memory.py")
backup = fp.with_suffix(".py.v3_broken")
shutil.copy(fp, backup)
print(f"[BACKUP] {backup}")

text = fp.read_text(encoding="utf-8")
lines = text.split("\n")

# 1) Конец блока импортов
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

# 2) Начало class Memory
class_start = None
for i in range(import_end, len(lines)):
    if lines[i].startswith("class Memory"):
        class_start = i
        break

if class_start is None:
    print("[FAIL] Не найден 'class Memory'. Первые 40 строк для диагностики:")
    for i in range(min(40, len(lines))):
        print(f"{i+1:3} | {lines[i]}")
    raise SystemExit(1)

# 3) Показываем, что удаляем (для контроля)
print(f"\n[DIAG] import_end={import_end}, class_start={class_start}")
print(f"[DIAG] Удаляем {class_start - import_end} строк между импортами и class Memory:")
print("-" * 60)
for i in range(import_end, class_start):
    print(f"{i+1:3} | {lines[i]}")
print("-" * 60)

# 4) Чистая функция
clean_func = '''def _clean_metadata(md):
    """Готовит метаданные для ChromaDB add/upsert: убирает None и пустые списки."""
    if not md:
        return None
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
    return out if out else None'''

new_lines = lines[:import_end] + ["", "", clean_func, "", ""] + lines[class_start:]
text = "\n".join(new_lines)

# 5) Обёртки metadatas=[var] — без двойной обёртки
text = re.sub(
    r'metadatas=\[(?!_clean_metadata)([a-zA-Z_][a-zA-Z0-9_]*)\]',
    r'metadatas=[_clean_metadata(\1)]',
    text,
)

fp.write_text(text, encoding="utf-8")

# 6) Компиляция с откатом при ошибке
try:
    py_compile.compile(str(fp), doraise=True)
    print("[OK] memory.py исправлен и компилируется. Первые 40 строк:")
    print("-" * 60)
    for i, l in enumerate(text.split("\n")[:40], 1):
        print(f"{i:3} | {l}")
    print("-" * 60)
except py_compile.PyCompileError as e:
    shutil.copy(backup, fp)
    print(f"[FAIL] Не компилируется: {e}")
    print("[RESTORED] Откат из бэкапа. Пришлите вывод [DIAG] выше.")