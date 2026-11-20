# -*- coding: utf-8 -*-
r"""scripts/fix_ears_model.py — МАРФА: ремонт раскладки модели ушей. v1.0

Кнопка 85_fix_ears.bat зовёт этот скрипт. Причина рождения — первый
живой прогон ушей на Z440 (20.11.2026): тест «модель жива» упал, vosk
ответил английским «Folder does not contain model files». Разбор показал
классику Windows: архив vosk-model-small-ru-0.22.zip с сайта содержит
внутри ещё одну папку с тем же именем, а «Извлечь всё» в Проводнике
предлагает destination с именем архива — модель ложится ВЛОЖЕННО,
двойным матрёшкой: models\vosk-...\vosk-...\am\final.mdl.

Что делает (идемпотентно — запускать можно сколько угодно раз):
  1. модель уже на месте → «всё в порядке», ничего не трогает;
  2. нашёл вложенную папку → поднимает модель на уровень выше,
     остатки распаковки убирает;
  3. нашёл нераспакованный zip (рядом с папкой или внутри неё) →
     распаковывает как положено, архив после проверки удаляет;
  4. не нашёл ничего → честная инструкция: что скачать и куда положить.
После успешного ремонта — живая проверка: грузит модель и слушает
секунду тишины (нужен vosk из venv Марфы).

Запуск на Z440:
  scripts\85_fix_ears.bat                                (кнопка)
  C:\Marfa\venv\Scripts\python.exe scripts\fix_ears_model.py
  C:\Marfa\venv\Scripts\python.exe scripts\fix_ears_model.py <путь-к-папке-модели>
"""
from __future__ import annotations

import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import config           # noqa: E402
from sensors.ears import model_files_ok  # noqa: E402

MODEL_URL = "https://alphacephei.com/vosk/models/vosk-model-small-ru-0.22.zip"


def repair(model_dir) -> str:
    """Починить раскладку модели ушей. Возвращает отчёт по-русски.

    Первое слово отчёта — статус: OK / ИСПРАВЛЕНО / ПРОВАЛ / НЕЧЕГО.
    Ничего не скачивает и не удаляет сверх названного в отчёте.
    """
    model_dir = Path(model_dir)
    name = model_dir.name
    parent = model_dir.parent

    # 0) уже здорово — пальцем не трогаем
    if model_files_ok(model_dir):
        return "OK: модель ушей уже на месте — %s" % model_dir

    # 1) классика жанра: вложенная папка с тем же именем
    nested = model_dir / name
    if model_files_ok(nested):
        wrapper = parent / (name + "_wrapper_tmp")
        shutil.rmtree(wrapper, ignore_errors=True)
        model_dir.rename(wrapper)            # старая обёртка — в сторону
        (wrapper / name).rename(model_dir)   # настоящая модель — на место
        shutil.rmtree(wrapper)               # остатки распаковки — на выброс
        if model_files_ok(model_dir):
            return ("ИСПРАВЛЕНО: модель лежала вложенно — поднял на уровень "
                    "выше, остатки распаковки убрал: %s" % model_dir)
        return "ПРОВАЛ: поднятие не получилось — посмотри %s руками" % model_dir

    # 2) рядом или внутри лежит нераспакованный архив
    for zip_path in (parent / (name + ".zip"), model_dir / (name + ".zip")):
        if zip_path.is_file():
            parent.mkdir(parents=True, exist_ok=True)
            try:
                with zipfile.ZipFile(zip_path) as z:
                    z.extractall(parent)   # в архиве корень = нужная папка
            except (zipfile.BadZipFile, OSError) as e:
                return "ПРОВАЛ: архив %s не читается (%s)" % (zip_path, e)
            if model_files_ok(model_dir):
                zip_path.unlink()          # архив представлен распакованной моделью
                return "ИСПРАВЛЕНО: модель распакована из %s" % zip_path
            return ("ПРОВАЛ: распаковал %s, а файлов модели всё равно нет — "
                    "архив битый, скачай заново с %s" % (zip_path, MODEL_URL))

    # 3) пусто — честно говорим, что скачать и куда положить
    if model_dir.is_dir():
        inside = ", ".join(sorted(p.name for p in model_dir.iterdir())[:8]) or "(пусто)"
        now = "в папке сейчас: %s" % inside
    else:
        now = "самой папки ещё нет"
    return ("НЕЧЕГО ЧИНИТЬ: %s. Скачай %s и положи zip в %s — "
            "запусти кнопку ещё раз, распакую сам"
            % (now, MODEL_URL, parent))


def main() -> int:
    print("=" * 60)
    print("МАРФА — ремонт модели ушей (vosk-model-small-ru-0.22)")
    print("=" * 60)
    model_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(config.EARS_MODEL_DIR)
    print("Смотрю: %s" % model_dir)
    msg = repair(model_dir)
    print(msg)
    if not (msg.startswith("OK") or msg.startswith("ИСПРАВЛЕНО")):
        return 1

    # живая проверка: грузим модель и слушаем секунду тишины
    try:
        from sensors.ears import check
        print(check(model_dir))
        print("Уши здоровы. Дальше по плану: scripts\\run_tests.bat")
    except Exception as e:
        print("Модель на месте, но живая проверка не прошла: %s" % e)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
