# -*- coding: utf-8 -*-
"""tests/conftest.py — ЗАКОН ПЕСОЧНИЦЫ (день-9, 24.11): каждый тест
живёт в СВОЁМ data/ и logs/, живой дом не течёт в тесты, тесты — в дом.

Урок Ф41 «память ответов»: это орган КАЖДОГО хода, и тест, не патчивший
DATA_DIR, прочитал ответ, сохранённый ЧУЖИМ тестом («Помню — уже
отвечала» вместо свежего хода к мозгу) — протечка шла молча, через
общий файл. Автопесочница закрывает класс проблем разом: ленивые пути
(закон reminders: Path(config.DATA_DIR) / …) следуют за патчем, а
тесты, которым нужен свой путь, патчат его сами — их monkeypatch
ложится ПОВЕРХ автопесочницы (та же фикстура, позже — значит главнее).
"""
import pytest

from core import config, repair


@pytest.fixture(autouse=True)
def _sandbox(tmp_path, monkeypatch):
    """Автопесочница: data/ и logs/ каждого теста — в его tmp_path.

    Только каталоги, о которых дом пишет НА КАЖДОМ ходу (лениво от
    DATA_DIR/LOGS_DIR); константы, вычисленные на импорте (NOTES_FILE
    и родня), тесты патчат явно, как и раньше — у каждого круга своя
    песочница, закон не меняется, только подстилается страховка."""
    data = tmp_path / "data"
    logs = tmp_path / "logs"
    monkeypatch.setattr(config, "DATA_DIR", data)
    monkeypatch.setattr(config, "LOGS_DIR", logs)
    monkeypatch.setattr(config, "BRAIN_LOG_FILE", logs / "brain_log.jsonl")


@pytest.fixture
def home(tmp_path, monkeypatch):
    """Изолированный дом (круг 35: общий для всех круговых якорей):
    ремонт не трогает файлы станции, слуга «на посту» по шву."""
    monkeypatch.setattr(config, "HOME_DIR", tmp_path)
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(config, "LOGS_DIR", tmp_path / "logs")
    monkeypatch.setattr(config, "MODELS_DIR", tmp_path / "models")
    monkeypatch.setattr(config, "PATCHES_DIR", tmp_path / "data" / "patches")
    monkeypatch.setattr(config, "REPAIR_LOG_FILE",
                        tmp_path / "logs" / "repair_log.jsonl")
    monkeypatch.setattr(config, "GUARD_LOG_FILE",
                        tmp_path / "logs" / "guard_log.jsonl")
    monkeypatch.setattr(config, "CANARIES_FILE",
                        tmp_path / "data" / "canaries.json")
    # слуга всегда «на посту» — реальный сервер не нужен
    monkeypatch.setattr(repair, "ensure_server",
                        lambda wait_secs=None: (True, "кодер на посту (шов)"))
    monkeypatch.setattr(repair, "release", lambda: "кодер лёг (шов)")
    return tmp_path
