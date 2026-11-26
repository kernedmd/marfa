# -*- coding: utf-8 -*-
"""Находит и скачивает whisper-server.exe, показывая все варианты."""
import urllib.request
import json
import zipfile
import os
from pathlib import Path

MARFA_ROOT = Path(__file__).resolve().parents[1]
TARGET_DIR = MARFA_ROOT / "llama.cpp"
ZIP_PATH = MARFA_ROOT / "whisper_temp.zip"

print("1. Запрашиваю список файлов последнего релиза whisper.cpp...")
url = "https://api.github.com/repos/ggerganov/whisper.cpp/releases/latest"
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
try:
    with urllib.request.urlopen(req, timeout=30) as response:
        data = json.loads(response.read().decode())
except Exception as e:
    print(f"Ошибка: {e}")
    exit(1)

print(f"Релиз: {data.get('tag_name', 'неизвестно')}\nДоступные архивы (.zip):")

# Собираем все zip-архивы
zips = [a for a in data.get('assets', []) if a['name'].lower().endswith('.zip')]
if not zips:
    print("  (архивов не найдено)")

# Ищем подходящий для Windows x64
target_asset = None
for a in zips:
    name = a['name'].lower()
    print(f"  - {a['name']} ({a.get('size', 0) // 1048576} МБ)")
    # Игнорируем исходный код
    if 'source' in name or 'src' in name:
        continue
    # Ищем признаки Windows-бинарника
    if ('win' in name or 'x64' in name or 'windows' in name) and ('bin' in name or 'cublas' in name or 'main' in name):
        target_asset = a
        print(f"\n✅ ВЫБРАН: {a['name']}")

if not target_asset:
    print("\n⚠️ Не удалось автоматически выбрать бинарник.")
    print("Пожалуйста, скачай вручную с https://github.com/ggerganov/whisper.cpp/releases/latest")
    print("Ищи файл с 'x64' и 'bin' (например, whisper-bin-x64.zip), НО НЕ 'Source code'.")
    exit(1)

print(f"\n2. Скачиваю {target_asset['name']}...")
try:
    urllib.request.urlretrieve(target_asset['browser_download_url'], ZIP_PATH)
    print("   Готово.")
except Exception as e:
    print(f"Ошибка скачивания: {e}")
    exit(1)

print("3. Распаковываю и ищу server.exe...")
TARGET_DIR.mkdir(parents=True, exist_ok=True)
found = False

with zipfile.ZipFile(ZIP_PATH, 'r') as zip_ref:
    for file_info in zip_ref.infolist():
        name_lower = file_info.filename.lower()
        # Ищем любой исполняемый файл с "server" в имени
        if name_lower.endswith('.exe') and 'server' in name_lower:
            zip_ref.extract(file_info, TARGET_DIR)
            extracted = TARGET_DIR / file_info.filename
            final = TARGET_DIR / "whisper-server.exe"
            if extracted != final:
                os.replace(extracted, final)
            print(f"   ✅ Найдено и сохранено как: whisper-server.exe")
            found = True
            break

# Если server.exe не найден, ищем main.exe (иногда сервер называют иначе, но для ear_bridge нужен именно server)
if not found:
    print("   ⚠️ Файл 'server.exe' не найден в архиве. Возможно, в этом релизе его нет.")
    print("   Содержимое архива:")
    with zipfile.ZipFile(ZIP_PATH, 'r') as zip_ref:
        for n in zip_ref.namelist():
            if n.lower().endswith('.exe'):
                print(f"     - {n}")

ZIP_PATH.unlink(missing_ok=True)
print("\n4. Проверка:")
print("   python -X utf8 -c \"from sensors import ear_bridge; print(ear_bridge.selftest())\"")