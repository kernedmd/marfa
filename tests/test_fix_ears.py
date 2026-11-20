# -*- coding: utf-8 -*-
"""tests/test_fix_ears.py — ремонт раскладки модели ушей (кнопка 85_fix_ears).

Ремонтник грузится по пути (scripts/ — не пакет, имя с цифры),
как clean_home в test_clean_home.py. Все случаи разводятся на
временных папках: реальный дом и реальные 46-мегабайтные архивы
не трогаются. Главный герой — вложенная распаковка («Извлечь всё»
в Проводнике кладёт модель двойным матрёшком).
"""
import importlib.util
import sys
import zipfile
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "fix_ears_model.py"
_spec = importlib.util.spec_from_file_location("fix_ears_model", _SCRIPT)
fix = importlib.util.module_from_spec(_spec)
sys.modules["fix_ears_model"] = fix
_spec.loader.exec_module(fix)

NAME = "vosk-model-small-ru-0.22"


def _healthy(base: Path) -> Path:
    """Построить здоровую модель-заглушку (маркер am/final.mdl на месте)."""
    md = base / NAME
    (md / "am").mkdir(parents=True, exist_ok=True)
    (md / "am" / "final.mdl").write_text("stub")
    return md


def _fake_zip(dest: Path) -> None:
    """Архив-заглушка с той же структурой корня, что у настоящего с сайта."""
    with zipfile.ZipFile(dest, "w") as z:
        z.writestr(NAME + "/am/final.mdl", "stub")
        z.writestr(NAME + "/README", "stub")
        z.writestr(NAME + "/conf/mfcc.conf", "stub")


# ---------- случай 0: уже здорово — пальцем не трогаем ----------

def test_repair_ok_untouched(tmp_path):
    md = _healthy(tmp_path)
    before = (md / "am" / "final.mdl").read_text()
    msg = fix.repair(md)
    assert msg.startswith("OK")
    assert (md / "am" / "final.mdl").read_text() == before


def test_repair_ok_idempotent_twice(tmp_path):
    md = _healthy(tmp_path)
    assert fix.repair(md).startswith("OK")
    assert fix.repair(md).startswith("OK")   # второй прогон — без вреда


# ---------- случай 1: вложенная распаковка — поднимаем ----------

def test_repair_nested_lifted(tmp_path):
    md = tmp_path / NAME
    (md / NAME / "am").mkdir(parents=True)
    (md / NAME / "am" / "final.mdl").write_text("stub")
    (md / "мусор от распаковки.txt").write_text("остатки")
    msg = fix.repair(md)
    assert msg.startswith("ИСПРАВЛЕНО")
    assert fix.model_files_ok(md)                 # модель на месте
    assert not (md / NAME).exists()               # вложенной больше нет
    assert not (tmp_path / (NAME + "_wrapper_tmp")).exists()  # и обёртки
    assert not (md / "мусор от распаковки.txt").exists()      # мусор убран


def test_repair_nested_keeps_model_content(tmp_path):
    md = tmp_path / NAME
    (md / NAME / "am").mkdir(parents=True)
    (md / NAME / "am" / "final.mdl").write_text("настоящая модель")
    fix.repair(md)
    assert (md / "am" / "final.mdl").read_text() == "настоящая модель"


# ---------- случай 2: нераспакованный архив ----------

def test_repair_zip_beside_folder(tmp_path):
    """Zip лежит рядом с папкой (в models\\) — распаковываем, zip убираем."""
    _fake_zip(tmp_path / (NAME + ".zip"))
    msg = fix.repair(tmp_path / NAME)
    assert msg.startswith("ИСПРАВЛЕНО")
    assert fix.model_files_ok(tmp_path / NAME)
    assert not (tmp_path / (NAME + ".zip")).exists()   # архив представлен моделью


def test_repair_zip_inside_folder(tmp_path):
    """Zip лежит ВНУТРИ папки модели — распаковываем в родителя, не матрёшкой."""
    md = tmp_path / NAME
    md.mkdir()
    _fake_zip(md / (NAME + ".zip"))
    msg = fix.repair(md)
    assert msg.startswith("ИСПРАВЛЕНО")
    assert fix.model_files_ok(md)
    assert not (md / (NAME + ".zip")).exists()
    assert not (md / NAME).exists()              # второй матрёшки не появилось


def test_repair_broken_zip_honest(tmp_path):
    """Битый архив — честный ПРОВАЛ, ничего не выдумываем."""
    (tmp_path / (NAME + ".zip")).write_bytes("это не zip".encode("utf-8"))
    msg = fix.repair(tmp_path / NAME)
    assert msg.startswith("ПРОВАЛ")
    assert not (tmp_path / NAME).exists()        # кривых папок не наставили


# ---------- случай 3: пусто — честная инструкция ----------

def test_repair_nothing_honest(tmp_path):
    msg = fix.repair(tmp_path / NAME)
    assert msg.startswith("НЕЧЕГО")
    assert "alphacephei.com" in msg              # где скачать
    assert str(tmp_path) in msg                  # куда положить


def test_repair_empty_folder_lists_contents(tmp_path):
    md = tmp_path / NAME
    md.mkdir()
    (md / "какой-то файл.txt").write_text("x")
    msg = fix.repair(md)
    assert "какой-то файл.txt" in msg            # показываем, что нашли внутри
