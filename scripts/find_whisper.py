# -*- coding: utf-8 -*-
"""Находит и скачивает whisper-server.exe — GitHub, потом зеркало.

Ф183 (круг 30, день-17): GitHub с релиза v1.9.4 ПЕРЕСТАЛ прикладывать
бинарники whisper.cpp — в релизах только «Source code», и старый скрипт
честно разводил руками («архивов не найдено»), хотя бинарники живы —
на SourceForge-зеркале, последний билд с ними: b4938 (август 2026,
whisper-bin-x64.zip, 38 файлов, whisper-server.exe внутри — проверено
архитектором по манифесту и строкам бинарника: флаг --inference-path
сборка знает).

Дом для слуги — C:\\Marfa\\whisper.cpp\\ (НЕ llama.cpp — там живой мозг
со своими свежими dll; урок дня-17: 38 файлов зеркала поверх = подмена
dll мозга постарше, закон «работающий файл не трогаем»). Мост ищет
бинарник именно там: find_whisper_server() — homes: llama.cpp,
whisper.cpp, C:\\Marfa.

Распаковываем ВСЕ файлы архива вместе: whisper-server.exe без соседних
dll (whisper.dll, ggml*.dll, llama.dll, SDL2.dll) не запустится.
"""
import json
import os
import urllib.request
import zipfile
from pathlib import Path

MARFA_ROOT = Path(__file__).resolve().parents[1]
TARGET_DIR = MARFA_ROOT / "whisper.cpp"   # Ф183: свой дом, не спальня мозга
ZIP_PATH = MARFA_ROOT / "whisper_temp.zip"

# Зеркало SourceForge: последний билд whisper.cpp с Windows-бинарниками.
# GitHub-релизы (v1.9.4+) их больше не прикладывают.
MIRROR_URL = ("https://sourceforge.net/projects/whisper-cpp.mirror/files/"
              "b4938/whisper-bin-x64.zip/download")
MIRROR_ABOUT = ("https://sourceforge.net/projects/whisper-cpp.mirror/files/b4938/ "
                "— whisper-bin-x64.zip, 8.4 МБ")


def github_zip_choice():
    """GitHub: список zip релиза и выбор Windows-бинарника. None — нет."""
    print("1. Запрашиваю список файлов последнего релиза whisper.cpp (GitHub)...")
    url = "https://api.github.com/repos/ggml-org/whisper.cpp/releases/latest"
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            data = json.loads(response.read().decode())
    except Exception as e:
        print(f"   GitHub не ответил: {e}")
        return None
    print(f"Релиз: {data.get('tag_name', 'неизвестно')}\nДоступные архивы (.zip):")
    zips = [a for a in data.get('assets', []) if a['name'].lower().endswith('.zip')]
    if not zips:
        print("  (архивов не найдено — GitHub перестал прикладывать бинарники)")
    for a in zips:
        name = a['name'].lower()
        print(f"  - {a['name']} ({a.get('size', 0) // 1048576} МБ)")
        if 'source' in name or 'src' in name:
            continue
        if ('win' in name or 'x64' in name or 'windows' in name) \
                and ('bin' in name or 'cublas' in name or 'main' in name):
            print(f"\n✅ ВЫБРАН с GitHub: {a['name']}")
            return a['browser_download_url']
    return None


def main() -> int:
    url = github_zip_choice()
    if url is None:
        print("\n1б. GitHub бинарников не дал — иду на зеркало SourceForge (b4938)...")
        url = MIRROR_URL
        print(f"   {MIRROR_ABOUT}")

    print(f"\n2. Скачиваю {url.rsplit('/', 1)[-1] or 'архив'}...")
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=300) as r, open(ZIP_PATH, 'wb') as f:
            f.write(r.read())
        print("   Готово.")
    except Exception as e:
        print(f"Ошибка скачивания: {e}")
        return 1

    print(f"3. Распаковываю ВСЁ в {TARGET_DIR} (exe без dll-соседей не живёт)...")
    TARGET_DIR.mkdir(parents=True, exist_ok=True)
    found_server = False
    with zipfile.ZipFile(ZIP_PATH, 'r') as zip_ref:
        for file_info in zip_ref.infolist():
            if file_info.is_dir():
                continue
            # срезаем вложенность Release\ — файлы ложатся прямо в дом
            flat = TARGET_DIR / Path(file_info.filename).name
            with open(flat, 'wb') as out:
                out.write(zip_ref.read(file_info))
            if flat.name.lower() == "whisper-server.exe":
                found_server = True
    n_files = len([p for p in TARGET_DIR.iterdir() if p.is_file()])
    print(f"   распаковано файлов: {n_files}")

    if found_server:
        print("   ✅ whisper-server.exe на месте")
    else:
        print("   ⚠️ whisper-server.exe в архиве не оказалось. exe-файлы архива:")
        with zipfile.ZipFile(ZIP_PATH, 'r') as zip_ref:
            for n in zip_ref.namelist():
                if n.lower().endswith('.exe'):
                    print(f"     - {n}")

    ZIP_PATH.unlink(missing_ok=True)
    print("\n4. Проверка:")
    print('   venv\\Scripts\\python.exe -X utf8 -c '
          '"from sensors import ear_bridge; print(ear_bridge.selftest())"')
    return 0 if found_server else 1


if __name__ == "__main__":
    exit(main())
