# -*- coding: utf-8 -*-
r"""tests/test_root_lock_circle.py — круг 22 «ЗАМОК КОРНЯ» (Ф118–Ф120).

Живой урок дня-13, вечер (отчёт Создателя о живых проверках круга 20
после приёма krug21): «прочитай C:\Marfa\README.md» — Марфа прочитала
файл корня без остановки (131,5 с · мозг · 27 ток · промпт 5045), а
R1 журнала уроков требует «стоп ДО вызова: путь должен содержать
подпапку». Диагноз по следам — три причины, три лекарства круга:

1. ПАНЕЛЬ — ПРОЦЕСС. Приём бандла обновил файлы на диске, но панель
   (Flask, debug=False) держит код в памяти со своего старта; блок
   УРОКИ-ЗАКОНЫ (Ф112) не ехал в промпте старого процесса — R1 не мог
   сработать, сколько ни проси. Лечение — закон v1.12: приём
   обновляет файлы, не процессы; после приёма кода — перезапуск слуг
   (Стоп_Марфа → Старт_Марфа); кнопка v3.8 говорит это вслух (шаг 3r).

2. ДИРЕКТИВА В ПРОМПТЕ МЯГКА. Даже с блоком в промпте мозг может её
   не услышать — правило, живущее только в промпте, — просьба, а не
   закон. R1 сам говорит «страж блокирует» (поле logic) — Ф118 делает
   логику правила правдой кода: замок в guard.check_path, отказ ДО
   инструмента, не зависит ни от послушания мозга, ни от перезапуска.
   Объявленный обход — песочница run_python (R1: «корень — только
   через песочницу»); внутренние органы замка не носят — они читают
   свои файлы прямым Python (start_marfa.json и родня), не руками.

3. КОМАНДА «ВЕС ПРОМПТА» ЖИЛА 14 КРУГОВ НЕДОСТИЖИМОЙ. Regex «^вес …»
   (Ф38, рефлекс папок) стоит выше точного списка и глотал строку
   «вес промпта» — уводил её в «папки нет»; якоря Ф43 звали орган
   напрямую, мимо калитки — проверяли печень, а не дорогу к ней.
   Лечение Ф119: точные команды выше regex, слой «журнал уроков» виден
   в отчёте (отчёт Ф43 писался до круга 20 и слоя не знал — Создатель
   видел все слои, КРОМЕ того, ради которого проверял).

Нумерация: Ф115–Ф117 — круг 21; круг 22 идёт с Ф118 (правило БЭКЛОГА).
"""
import subprocess
from pathlib import Path

import pytest

from core import config, hands, promptweight
from core.agent import Agent
from safety import guard
from tests.fake_llama_server import start_fake_brain

ROOT = Path(__file__).resolve().parents[1]
BAT = ROOT / "scripts" / "80_sync_github.bat"
PROTOCOL = ROOT / "docs" / "SYNC_PROTOCOL_v1.md"

# Последнее тело v3.7 в истории: коммит книг круга-21 (28162d0) —
# якорь перехода приколот к паре версий, HEAD растёт с каждым кругом,
# а переход v3.7 -> v3.8 — факт истории (закон круга 19, образец
# круга 21: KRUG20_BOOKS_COMMIT в test_quiet_loop_circle.py)
KRUG21_BOOKS_COMMIT = "28162d0"
# продление круга 28: книги круга-27 — последнее состояние тела v3.8
# (рабочая копия уже несёт v3.9, и переход v3.8 -> v3.9 якорится ниже)
KRUG27_BOOKS_COMMIT = "e3d80e0"


@pytest.fixture()
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("MARFA_HOME", str(tmp_path))
    monkeypatch.setattr(config, "HOME_DIR", tmp_path)
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(config, "LOGS_DIR", tmp_path / "logs")
    monkeypatch.setattr(config, "BRAIN_LOG_FILE",
                        tmp_path / "logs" / "brain_log.jsonl")
    monkeypatch.setattr(config, "GUARD_LOG_FILE",
                        tmp_path / "logs" / "guard_log.jsonl")
    monkeypatch.setattr(config, "CANARIES_FILE",
                        tmp_path / "data" / "canaries.json")
    # LESSONS_FILE вычисляется на импорте (JOURNAL_DIR от тогдашнего
    # HOME_DIR) — закон песочниц круга 20: тесты не протекают в живой
    # журнал, патч ложится поверх автопесочницы
    monkeypatch.setattr(config, "LESSONS_FILE",
                        tmp_path / "journal" / "lessons.json")
    monkeypatch.setattr(guard, "_LOG", None)
    config.ensure_dirs()
    yield tmp_path


@pytest.fixture()
def srv(monkeypatch, home):
    server = start_fake_brain()
    monkeypatch.setattr(config, "BRAIN_URL", server.base_url)
    yield server
    server.shutdown()


@pytest.fixture()
def agent(srv):
    return Agent()


# ------------------------------------------------------------------- Ф118

def test_root_file_denied_before_tool(home):
    r"""ГЛАВНЫЙ ЯКОРЬ Ф118: файл корня — отказ ДО инструмента.

    Живая болезнь дня-13: «прочитай C:\Marfa\README.md» — прочитала.
    Замок: страж отказывает раньше рук — мозг получает честный отказ
    с именем правила, а не содержимое корня. Отказ не зависит ни от
    перезапуска слуг, ни от послушания мозга.
    """
    (home / "README.md").write_text("секрет корня", encoding="utf-8")
    v = guard.check_path(home / "README.md")
    assert not v.allowed() and v.level == "HIGH"
    assert v.rule == "path.root_lock"
    assert "R1" in v.reason and "корень" in v.reason
    with pytest.raises(PermissionError) as exc:
        hands.read_file(home / "README.md")
    assert "R1" in str(exc.value)


def test_root_write_denied(home):
    """Запись в корень — тот же замок: R1 не делает исключений для рук."""
    with pytest.raises(PermissionError):
        hands.write_file(home / "заметка_в_корне.txt", "мимо")


def test_home_root_itself_denied(home):
    r"""Сам корень дома — «путь = C:\Marfa без подпапки — стоп» (R1)."""
    v = guard.check_path(home)
    assert not v.allowed() and v.rule == "path.root_lock"


def test_root_folder_denied(home):
    """Папка верхнего уровня (models, core) — тоже корень: R1 говорит
    «путь должен содержать подпапку», а не «файл в подпапке»."""
    v = guard.check_path(home / "models")
    assert not v.allowed() and v.rule == "path.root_lock"


def test_relative_root_path_not_an_escape(home):
    r"""Относительный путь — не обход: «README.md» резолвится в корень."""
    (home / "README.md").write_text("x", encoding="utf-8")
    v = guard.check_path("README.md")
    assert not v.allowed() and v.rule == "path.root_lock"


def test_subfolders_still_allowed(home):
    """Замок не закрыл дом: подпапки (память, journal, data, core) —
    законный путь рук, ровно как R1 и говорит."""
    (home / "память").mkdir(exist_ok=True)
    (home / "память" / "заметка.md").write_text("Марфа помнит",
                                                encoding="utf-8")
    assert guard.check_path(home / "память" / "заметка.md").allowed()
    assert guard.check_path("data/queue.json").allowed()
    assert hands.read_file(home / "память" / "заметка.md") == "Марфа помнит"


def test_sandbox_escape_alive(home):
    """Песочница run_python читает корень — ОБЪЯВЛЕННЫЙ обход R1
    («корень — только через песочницу»), а не дыра: код в песочнице
    виден, проверяется стражем на опасные паттерны и живёт в логе."""
    (home / "README.md").write_text("тело README", encoding="utf-8")
    out = hands.run_python(
        "print(open('README.md', encoding='utf-8').read())")
    assert "тело README" in out


def test_organs_do_not_wear_the_lock(home):
    """Внутренние органы замка не носят: они читают свои файлы прямым
    Python (start_marfa.json, README для книг), не руками агента —
    замок запирает ИНСТРУМЕНТЫ МОЗГА, а не организм."""
    (home / "start_marfa.json").write_text('{"слуга": "панель"}',
                                           encoding="utf-8")
    direct = (home / "start_marfa.json").read_text(encoding="utf-8")
    assert "панель" in direct   # прямой Python — органам можно
    with pytest.raises(PermissionError):
        hands.read_file(home / "start_marfa.json")  # руки — нельзя


# ------------------------------------------------------------------- Ф119

def test_route_ves_prompta_through_gate(agent):
    """ГЛАВНЫЙ ЯКОРЬ Ф119: «вес промпта» доезжает через КАЛИТКУ.

    14 кругов regex «^вес …» (Ф38) глотал строку раньше точного
    списка — команда Ф43 была недостижима, а якоря звали орган
    напрямую. Урок: маршруты якорятся путём пользователя.
    """
    r = agent.handle("вес промпта")
    assert r.source == "python" and "ВЕС ПРОМПТА" in r.text


def test_route_skolko_vesit_prompta(agent):
    """«сколько весит промпт» — та же калитка (живая формулировка
    дня-13, которая и работала): переезд не уронил и её."""
    r = agent.handle("сколько весит промпт")
    assert r.source == "python" and "ВЕС ПРОМПТА" in r.text


def test_route_weight_folders_alive(agent, home):
    """Рефлекс папок (Ф38) не сломан переездом соседа: «вес data»
    по-прежнему взвешивает папку, а не уходит в промпт."""
    (home / "data").mkdir(exist_ok=True)
    (home / "data" / "x.bin").write_bytes(b"1" * 100)
    r = agent.handle("вес data")
    assert r.source == "python" and "«data» весит" in r.text


def test_promptweight_shows_lessons_layer(home):
    """Слой «журнал уроков» виден в отчёте — Создатель видит ВСЕ слои,
    включая тот, ради которого проверял (Ф43 узнал о Ф112)."""
    j = home / "journal"
    j.mkdir(exist_ok=True)
    (j / "lessons.json").write_text(
        '{"author": "Илья", "executor": "Марфа", "rules": ['
        '{"id": "R1", "rule": "путь — подпапка, не корень", '
        '"check": "остановись ДО вызова"}, '
        '{"id": "R2", "rule": "уверенность != проверка", '
        '"check": "спроси: это проверка?"}], "lessons": []}',
        encoding="utf-8")
    out = promptweight.render()
    assert "журнал уроков" in out
    assert "ядреные правила" not in out          # без опечаток
    assert "в каждом ходе" in out


def test_promptweight_empty_journal_honest(home):
    """Пустой журнал — слой честно пуст (Ф77: заголовок без
    содержания — мусор): «блока в промпте нет», а не тишина."""
    out = promptweight.render()
    assert "журнал уроков: пуст" in out


def test_button_speaks_restart_law():
    """Кнопка v3.8 — голос закона v1.12: после приёма говорит вслух
    «перезапусти дом». Закон, который нужен в момент, произнесён в
    момент — не в книге, которую читают потом."""
    t = BAT.read_text(encoding="utf-8").replace("\r\n", "\n")
    sub = t[t.index("rem ---------- 3r."):t.index("\n:: ---------- 3b.")]
    assert 'if "%IMPORTED%"=="1"' in sub          # только после приёма
    assert "Приём обновил файлы, не процессы" in sub
    assert "Стоп_Марфа.bat" in sub and "Старт_Марфа.bat" in sub


# ------------------------------------------------------------------- Ф120

def _text() -> str:
    return BAT.read_text(encoding="utf-8").replace("\r\n", "\n")


def test_transition_v3_7_to_v3_8_by_fc_from_history():
    """ГЛАВНЫЙ ЯКОРЬ Ф120: переход v3.7 -> v3.8 по закону круга 19.

    Продление круга 28: оба тела — из истории (книги круга-21 —
    последнее v3.7, книги круга-27 — последнее v3.8; рабочая копия
    уже несёт v3.9 — свежий переход v3.8 -> v3.9 якорится в своём
    тесте ниже). fc /b эквивалент: байты различаются -> errorlevel
    1 -> смена ОБЪЯВЛЯЕТСЯ, петля доезжает до ГОТОВО на старом
    теле (Ф109 жив). Замороженная зона (запускник) идентична
    байт-в-байт (Ф110 жив).
    """
    old = subprocess.run(
        ["git", "-C", str(ROOT), "show",
         KRUG21_BOOKS_COMMIT + ":scripts/80_sync_github.bat"],
        capture_output=True, text=True, encoding="utf-8").stdout.replace("\r\n", "\n")
    tree = subprocess.run(
        ["git", "-C", str(ROOT), "show",
         KRUG27_BOOKS_COMMIT + ":scripts/80_sync_github.bat"],
        capture_output=True, text=True, encoding="utf-8").stdout.replace("\r\n", "\n")
    assert "rem ТЕЛО КНОПКИ 3.7" in old, "история должна нести тело v3.7 (книги круга-21)"
    assert "rem ТЕЛО КНОПКИ 3.8" in tree, "история должна нести тело v3.8 (книги круга-27)"
    assert old != tree, "тела обязаны различаться — иначе перехода нет"

    def frozen(s):
        end = s.index("\nexit /b %ERRORLEVEL%\n") + len("\nexit /b %ERRORLEVEL%\n")
        return s[:end]

    assert frozen(old) == frozen(tree), \
        "замороженная зона менялась между v3.7 и v3.8 — закон Ф110 нарушен"


def test_transition_v3_8_to_v3_9_by_fc_from_history():
    """ГЛАВНЫЙ ЯКОРЬ Ф120 (продление круга 28): переход v3.8 -> v3.9.

    Старое тело (v3.8) — из истории (книги круга-27, последнее
    состояние v3.8), новое — рабочая копия. fc /b эквивалент: байты
    различаются -> errorlevel 1 -> смена ОБЪЯВЛЯЕТСЯ, петля доезжает
    до ГОТОВО на старом теле (Ф109 жив). Замороженная зона (запускник)
    идентична байт-в-байт (Ф110 жив).
    """
    tree = _text()
    old = subprocess.run(
        ["git", "-C", str(ROOT), "show",
         KRUG27_BOOKS_COMMIT + ":scripts/80_sync_github.bat"],
        capture_output=True, text=True, encoding="utf-8").stdout.replace("\r\n", "\n")
    assert "rem ТЕЛО КНОПКИ 3.8" in old, "история должна нести тело v3.8 (книги круга-27)"
    assert "rem ТЕЛО КНОПКИ 3.9" in tree, "рабочая копия — тело v3.9"
    assert old != tree, "тела обязаны различаться — иначе перехода нет"

    def frozen(s):
        end = s.index("\nexit /b %ERRORLEVEL%\n") + len("\nexit /b %ERRORLEVEL%\n")
        return s[:end]

    assert frozen(old) == frozen(tree), \
        "замороженная зона менялась между v3.8 и v3.9 — закон Ф110 нарушен"


def test_krug21_laws_survive_krug22():
    """Круг 22 не разобрал круг 21: тихий git (gc.auto 0,
    GIT_TERMINAL_PROMPT=0), улика «24.11 10:16» и «Should I try
    again», страж одной петли (marfa_sync.pid) — всё в теле."""
    t = _text()
    assert "git config gc.auto 0" in t
    assert "GIT_TERMINAL_PROMPT=0" in t
    assert "24.11 10:16" in t
    assert "Should I try again" in t
    assert "marfa_sync.pid" in t


def test_ghost_and_freeze_survive_krug22():
    """Призрак перезаписи спит и после v3.9 (продление круга 28):
    строк «rem BTN_VER» — ровно одна (замороженная 3.5 шапки),
    живой маркер — ниже :run."""
    t = _text()
    hits = [ln for ln in t.split("\n") if "rem BTN_VER" in ln]
    assert hits == ["rem BTN_VER 3.5"]
    assert t.index("rem BTN_VER 3.5") < t.index("\n:run")
    assert t.index("rem ТЕЛО КНОПКИ 3.9") > t.index("\n:run")


def test_protocol_names_v1_13_laws():
    """Протокол v1.13 называет закон «голос упавшего шага» и все
    старые законы — книга не молчит (урок круга 17: исключение без
    причины — забытость, с причиной — закон). Продление круга 28."""
    doc = PROTOCOL.read_text(encoding="utf-8")
    assert "ПРОТОКОЛ СИНХРОНИЗАЦИИ v1.13" in doc
    assert "ГОЛОС УПАВШЕГО" in doc               # закон круга 28
    assert "ИЗМЕРЕНИЕ — НЕ ПРИГОВОР" in doc       # Ф172 в книге
    assert "обновляет файлы, не процессы" in doc  # закон круга 22 жив
    assert "замок" in doc.lower() or "замка" in doc.lower()
    assert "v3.8 -> v3.9" in doc or "v3.8 → v3.9" in doc
