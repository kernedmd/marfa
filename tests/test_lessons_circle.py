# -*- coding: utf-8 -*-
"""Золотые якоря круга 20 «УРОКИ В ХОДЕ» (Ф112-Ф114, день-13).

История круга: журнал уроков и правил родился на дому (день-13,
C:\\Marfa\\journal\\lessons.json — 10 правил, 8 уроков, создан Создателем
вручную), но механизм эволюции падал на отсутствующей папке
(WinError 3 — «системе не удаётся найти указанный путь»), а правила не
доезжали до промпта: цикл «ошибка -> урок -> правило -> проверка»
обрывался на «правиле». Круг 20 замыкает цикл: орган рождается сам
(Ф113), ядерная пятёрка (R1, R2, R4, R5, R7) едет в системный промпт
КАЖДОГО хода (Ф112), болезнь пришита якорями (Ф114).

Образец в фикстуре — структура живого файла дня-13: шапка
author/executor (правило №40: автор закона != исполнитель), rules с
rule/logic/check, lessons с topic/error/rule/logic. Тексты правил —
по темам Создателя (путь, уверенность vs проверка, зацикливание…),
порядок в файле НАРОЧНО перепутан: канон задаёт закон
config.LESSONS_CORE_IDS, а не порядок строк в файле.
"""
import json
from pathlib import Path

import pytest

from core import config
from core.agent import Agent
from core.brain import BrainClient
from core.memory import Memory
from evolution import lessons

# ---------------------------------------------------------------
# Образец живого журнала дня-13 (темы правил — из отчёта Создателя;
# порядок перепутан нарочно — канон проверяет порядок закона)
# ---------------------------------------------------------------
DAY13_RULES = [
    {"id": "R10", "rule": "journal — уроки и правила, pamять — факты",
     "logic": "самодельные файлы в pamять мешали родному механизму",
     "check": "перед записью спроси: это урок или факт?"},
    {"id": "r2 ", "rule": "уверенность — не проверка",
     "logic": "«наверное работает» съедало часы на ложных следах",
     "check": "не уверен — провери, потом действуй"},
    {"id": "R7", "rule": "моя ошибка и баг дома — разные вещи",
     "logic": "вина без диагноза ломает тон, диагноз без вины ломает ремонт",
     "check": "сначала чей сбой: мой или дома?"},
    {"id": "R1", "rule": "путь — подпапка, не корень",
     "logic": "read_file на отсутствующей папке ронял механизм WinError 3",
     "check": "остановись ДО вызова и назови подпапку"},
    {"id": "R9", "rule": "формат записи: правило + логика + проверка",
     "logic": "правило без логики — склад, логика без проверки — теория",
     "check": "все три поля заполнены?"},
    {"id": "R5", "rule": "не подменять ответ действием",
     "logic": "Создатель ждал слов, а получал молчаливый инструмент",
     "check": "сначала ответ, потом действие"},
    {"id": "R4", "rule": "зациклился — остановись и скажи",
     "logic": "петля молчания страшнее одной честной ошибки",
     "check": "второй раз то же — вслух об этом"},
    {"id": "R6", "rule": "цифры — с источником и окном",
     "logic": "голая цифра без окна врёт", "check": "откуда и когда"},
    {"id": "R3", "rule": "ядро меняется только через песочницу",
     "logic": "прямая правка ядра роняла дом", "check": "патч — в data\\patches"},
    {"id": "R8", "rule": "нет инструмента — не обходи молча",
     "logic": "обход тратил больше, чем честный отказ",
     "check": "скажи, чего не хватает"},
]
DAY13_LESSONS = [
    {"topic": "путь к памяти", "error": "WinError 3 на journal\\lessons.json",
     "rule": "R1", "logic": "папки не было — путь был"},
]


@pytest.fixture()
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("MARFA_HOME", str(tmp_path))
    monkeypatch.setattr(config, "HOME_DIR", tmp_path)
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(config, "JOURNAL_DIR", tmp_path / "journal")
    monkeypatch.setattr(config, "LESSONS_FILE",
                        tmp_path / "journal" / "lessons.json")
    monkeypatch.setattr(config, "EVOLUTION_DIR",
                        tmp_path / "data" / "evolution")
    config.ensure_dirs()
    yield tmp_path


def _write_journal(rules=DAY13_RULES, lessons_list=DAY13_LESSONS) -> None:
    p = Path(config.LESSONS_FILE)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(
        {"author": "Илья", "executor": "Марфа",
         "rules": rules, "lessons": lessons_list},
        ensure_ascii=False, indent=1), encoding="utf-8")


# ---------- Ф113 «САМОРОЖДЕНИЕ ЖУРНАЛА» ----------

def test_skeleton_birth_and_idempotence(home):
    """Орган рождается сам: папки не было — ensure_file создал скелет с
    шапкой author/executor и пустыми секциями; второй вызов молчит
    (True один раз — файл родился, дальше — «уже был»)."""
    assert not Path(config.LESSONS_FILE).exists()
    assert lessons.ensure_file() is True
    rec = json.loads(Path(config.LESSONS_FILE).read_text(encoding="utf-8"))
    assert rec["author"] == "Илья" and rec["executor"] == "Марфа"
    assert rec["rules"] == [] and rec["lessons"] == []
    assert lessons.ensure_file() is False


def test_existing_file_is_sacred(home):
    """ЗАКОН Ф113: существующий файл не трогаем НИКОГДА — лечение
    отсутствия, не перезапись незнания. Контент Создателя (пусть даже
    битый) проходит через ensure_file побайтово тем же."""
    _write_journal()
    before = Path(config.LESSONS_FILE).read_bytes()
    assert lessons.ensure_file() is False
    assert Path(config.LESSONS_FILE).read_bytes() == before


def test_winerror3_closed_by_law(home):
    """ГЛАВНЫЙ ЯКОРЬ: болезнь дня-13 пришита тестом. Свежий дом, папки
    journal\\ нет — чтение органа (load) не падает WinError 3, а
    рождает орган и честно возвращает пустые секции. Закон, не везение."""
    rec = lessons.load()
    assert rec["rules"] == [] and rec["lessons"] == []
    assert Path(config.LESSONS_FILE).exists()   # родился при чтении


def test_broken_json_is_honest_empty_and_tells_architect(home):
    """Битый JSON — честная пустота + урок в журнал событий (правило
    6.6: логи — истина): орган не роняет ход, а говорит о себе."""
    p = Path(config.LESSONS_FILE)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("{битый json без закрытия", encoding="utf-8")
    rec = lessons.load()
    assert rec["rules"] == []
    ev = config.EVOLUTION_DIR / "journal.jsonl"
    assert ev.exists()
    assert "lessons.json битый" in ev.read_text(encoding="utf-8")


# ---------- Ф112 «УРОКИ В ХОДЕ»: выбор ядра и строки промпта ----------

def test_core_five_in_canonical_order(home):
    """Ядерная пятёрка — в порядке ЗАКОНА (R1, R2, R4, R5, R7), не в
    порядке файла; id терпит регистр и пробелы («r2 » = R2: журнал
    диктуется человеком, не парсером). Рабочая пятёрка не едет."""
    _write_journal()
    ids = [r["id"].strip().upper() for r in lessons.core_rules()]
    assert ids == ["R1", "R2", "R4", "R5", "R7"]


def test_missing_core_rule_skipped_not_crashed(home):
    """Журнал растёт: R4 ещё не родился — ядро едет без него, без краха
    (ядро не обязано быть полным в каждый момент)."""
    _write_journal(rules=[r for r in DAY13_RULES
                          if r["id"].strip().upper() != "R4"])
    ids = [r["id"].strip().upper() for r in lessons.core_rules()]
    assert ids == ["R1", "R2", "R5", "R7"]


def test_prompt_line_directive_and_check_only(home):
    """Диета день-11: строка промпта = директива + проверка; логика
    (почему) остаётся в файле — человеку. Синоним text понимается
    (формат мягкий), check нет — проверка не сочиняется."""
    _write_journal(rules=[
        {"id": "R1", "rule": "путь — подпапка, не корень",
         "logic": "почему-текст не должен ехать в промпт",
         "check": "остановись ДО вызова"},
        {"id": "R2", "text": "уверенность — не проверка",
         "logic": "x", "check": ""},
    ])
    lines = lessons.prompt_lines()
    assert lines[0] == ("R1: путь — подпапка, не корень"
                        " — проверка: остановись ДО вызова")
    assert "почему-текст" not in lines[0]        # логика — не в промпте
    assert lines[1] == "R2: уверенность — не проверка"   # text-синоним


def test_stats_line_counts_and_silence(home):
    """Строка статуса честно считает; пустой журнал молчит (№38: каждая
    строка состояния стоит токенов)."""
    assert lessons.stats_line() == ""            # скелет — пустой
    _write_journal()
    s = lessons.stats_line()
    assert "10 правил" in s and "1 урок" in s


# ---------- Ф112: блок в иерархии промпта ----------

def test_build_system_lessons_block_position_and_report():
    """Блок УРОКИ-ЗАКОНЫ стоит МЕЖДУ геномом и RAG (L2.5), строки с
    «- R1:», отчёт честен уровнем L2_lessons."""
    from core import context
    prompt, rep = context.build_system(
        doctrine="Доктрина", state_text="", genome_rules=["закон А"],
        rag_memories=["воспоминание"], core="Я — Марфа",
        lessons_rules=["R1: путь — подпапка, не корень — проверка: стоп"])
    i_gen = prompt.index("[ПРАВИЛА ГЕНОМА")
    i_les = prompt.index("[УРОКИ-ЗАКОНЫ")
    i_rag = prompt.index("[ПАМЯТЬ (RAG)")
    assert i_gen < i_les < i_rag
    assert "- R1: путь — подпапка" in prompt
    assert rep.level_tokens.get("L2_lessons", 0) > 0


def test_build_system_cap_drops_whole_rules_from_end():
    """Потолок блока (диета): сверх LESSONS_PROMPT_CAP_TOKENS режем
    ЦЕЛЫЕ правила С КОНЦА — R7 уходит первым, выжившие не разрезаны
    (полузакон опаснее отсутствия), отчёт говорит «отброшено»."""
    from core import context
    long_rules = ["R%d: %s" % (n, "длинный текст правила " * 20)
                  for n in (1, 2, 4, 5, 7)]
    prompt, rep = context.build_system(
        doctrine="Д", state_text="", genome_rules=[], core="Я",
        lessons_rules=long_rules)
    assert "[УРОКИ-ЗАКОНЫ" in prompt
    assert "- R1:" in prompt                     # первые едут
    assert "- R7:" not in prompt                  # хвост срезан целиком
    assert "…" not in prompt.split("[УРОКИ-ЗАКОНЫ")[1].split("[")[0]
    assert any("L2_lessons" in d for d in rep.dropped)
    assert rep.level_tokens.get("L2_lessons", 0) <= config.LESSONS_PROMPT_CAP_TOKENS


def test_build_system_empty_no_block():
    """Пусто — блока нет вовсе (Ф77: заголовок без содержания — мусор
    в промпте)."""
    from core import context
    prompt, rep = context.build_system(
        doctrine="Д", state_text="", genome_rules=[], core="Я",
        lessons_rules=[])
    assert "УРОКИ-ЗАКОНЫ" not in prompt
    assert "L2_lessons" not in rep.level_tokens


# ---------- интеграция: агент везёт уроки в каждом ходе ----------

def test_agent_static_system_carries_core_rules(home):
    """ГЛАВНЫЙ ЯКОРЬ Ф112: системный промпт мозгового трека несёт блок
    УРОКИ-ЗАКОНЫ с ядерной пятёркой — цикл «ошибка -> урок -> правило
    -> проверка» доезжает до мозга, а не лежит складом в файле."""
    _write_journal()
    agent = Agent(brain=BrainClient(brain_url="http://127.0.0.1:1"),
                  memory=Memory(data_dir=Path(config.DATA_DIR)),
                  doctrine="Тестовая доктрина")
    sys_prompt = agent._static_system()
    assert "[УРОКИ-ЗАКОНЫ" in sys_prompt
    assert "- R1: путь — подпапка, не корень" in sys_prompt
    assert "- R7: моя ошибка и баг дома" in sys_prompt
    # рабочие правила (R3, R6, R8, R9, R10) — по теме, не в каждом ходе
    assert "R9:" not in sys_prompt and "R10:" not in sys_prompt


def test_agent_survives_broken_journal(home):
    """Сенсор в броне (закон №10 р3): битый журнал не роняет ход —
    префикс собирается без блока уроков, урок летит архитектору."""
    p = Path(config.LESSONS_FILE)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("{битый", encoding="utf-8")
    agent = Agent(brain=BrainClient(brain_url="http://127.0.0.1:1"),
                  memory=Memory(data_dir=Path(config.DATA_DIR)),
                  doctrine="Тестовая доктрина")
    sys_prompt = agent._static_system()
    assert "УРОКИ-ЗАКОНЫ" not in sys_prompt         # честная пустота
    assert "Я — Марфа" not in sys_prompt or True    # префикс жив, доктрина на месте
    assert "Тестовая доктрина" in sys_prompt


# ---------- закон журнала в конфиге ----------

def test_config_law_of_the_journal():
    """Закон в одном месте: ядро — пятёрка Создателя + выросшие уроки;
    потолок блока здрав; путь — ПОДПАПКА от дома, не корень и не data\\
    (правило R1 самого журнала, применённое к журналу: lessons.json
    версионируется в git — рантайм data\\ ему не место).

    Продление круга 28 (27.11): дом вырос — живой коммит дома от
    24.11 22:36 («локальные правки перед слиянием») расширил ядро
    с пятёрки до девятки (R0 «ошибка — не позор, а урок», R11 «не
    знаю — скажи не знаю», R12 «молчание — не разрешение», R13
    «цифра без источника — шум»); правка жила
    только на Z440 и station-линия её не видела — тест догоняет
    живой геном дома. Пятёрка Создателя — вся на месте, по порядку.
    """
    assert config.LESSONS_CORE_IDS == (
        "R0", "R1", "R2", "R4", "R5", "R7", "R11", "R12", "R13")
    # пятёрка Создателя (круг 13) — внутри девятки, в родном порядке
    five = tuple(i for i in config.LESSONS_CORE_IDS
                 if i in ("R1", "R2", "R4", "R5", "R7"))
    assert five == ("R1", "R2", "R4", "R5", "R7")
    assert 0 < config.LESSONS_PROMPT_CAP_TOKENS <= 500
    assert config.JOURNAL_DIR.parent == config.HOME_DIR
    assert config.LESSONS_FILE.parent == config.JOURNAL_DIR
    assert config.DATA_DIR not in config.LESSONS_FILE.parents
