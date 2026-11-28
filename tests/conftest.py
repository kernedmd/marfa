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
    песочница, закон не меняется, только подстилается страховка.

    КРУГ 36 (аудит brain 329): скорость дозвона мозга в тестах —
    ЗДЕСЬ, а не веткой PYTEST_CURRENT_TEST в боевом коде (переменную
    окружения наследуют дочерние процессы run_python — тестовая ветка
    попадала в прод). Батарея не спит 45 с ради симуляции погрузки.
    """
    data = tmp_path / "data"
    logs = tmp_path / "logs"
    monkeypatch.setattr(config, "DATA_DIR", data)
    monkeypatch.setattr(config, "LOGS_DIR", logs)
    monkeypatch.setattr(config, "BRAIN_LOG_FILE", logs / "brain_log.jsonl")
    monkeypatch.setattr(config, "BRAIN_CONNECT_BACKOFF_SEC", 0)
    # КРУГ 36: журнал уроков — тоже песочница. EVOLUTION_DIR вычислен на
    # импорте от dev-дома (/home/z/marfa_dev на берегу, C:\Marfa — на
    # станции): БЕЗ этой строки уроки батарей утекали в НАСТОЯЩИЙ
    # журнал, прорастали правилами в состояние дома и рвали чужие
    # якоря диеты (живой случай круга 36: «уроков за сутки: 1263»)
    monkeypatch.setattr(config, "EVOLUTION_DIR", data / "evolution")
    # КРУГ 36: резолюции и файлы органов — тоже песочница. Эти константы
    # вычислены на импорте: тесты калитки/глаз/ремонта писали
    # screen_watch.json, self_write.json и родню в НАСТОЯЩИЙ dev-дом —
    # и состояние дома (которое их читает) росло, рвая чужие якоря
    # диеты. Потребители читают константы лениво — патч ложится
    # поверх, тесты со своими патчами — ещё выше (закон песочницы).
    monkeypatch.setattr(config, "SCREEN_WATCH_FILE", data / "screen_watch.json")
    monkeypatch.setattr(config, "SELF_WRITE_FILE", data / "self_write.json")
    monkeypatch.setattr(config, "HANDS_ENABLED_FILE", data / "hands_enabled.json")
    monkeypatch.setattr(config, "SLEEP_FILE", data / "sleep.json")
    monkeypatch.setattr(config, "GATE_ROTATE_FILE", data / "gate_rotate.json")


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
