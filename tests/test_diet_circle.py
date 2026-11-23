# -*- coding: utf-8 -*-
"""КРУГ 13 «КОНТЕКСТ-ДИЕТА» (день-11, 24.11) — Ф76-Ф80.

Живой лог Создателя (23-24.11): «чат накопился за несколько дней и
количество токенов заметно убивают Марфу». Разбор по штампам: промпт
рос 3650 -> 7419 ток за дни, ответы 90-200 с, «мозг недоступен» на
ровном месте. Три корня: манифест 3197 ток (полный каталог команд
каждым ходом), часы состояния в системе (рвали KV-кэш префикса КАЖДЫЙ
ход — мозг пересчитывал всё заново) и скрытая бомба бюджета — закон
считал историю «внутри» 6500, а она ехала поверх: 6500+1000+768 =
8268 > 8192, живой лог стоял в пяти токенах от обреза ЯДРА.

Пять фишек круга: Ф76 диета манифеста (стройный в промпте, полный —
зеркалу), Ф77 стабильный префикс (состояние+RAG — в хвост хода),
Ф78 честный закон контекста + потолок RAG, Ф79 свежее утро (прошлые
дни истории — выжимкой), Ф80 закон инструмента (переспрос
пусто-аргументных действий — лечит «баланс: ОК» живого лога)."""
import json
from pathlib import Path

import pytest

from core import config
from core.agent import Agent, _action_is_empty
from core.brain import BrainClient
from core.dialog import DialogStore
from core.identity import manifest, manifest_slim
from core.memory import Memory
from safety import guard
from tests.fake_llama_server import start_fake_brain


@pytest.fixture()
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("MARFA_HOME", str(tmp_path))
    monkeypatch.setattr(config, "HOME_DIR", tmp_path)
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(config, "LOGS_DIR", tmp_path / "logs")
    monkeypatch.setattr(config, "BRAIN_LOG_FILE", tmp_path / "logs" / "brain_log.jsonl")
    monkeypatch.setattr(config, "GUARD_LOG_FILE", tmp_path / "logs" / "guard_log.jsonl")
    monkeypatch.setattr(config, "CANARIES_FILE", tmp_path / "data" / "canaries.json")
    monkeypatch.setattr(config, "DOCTRINE_FILE", tmp_path / "data" / "creator_doctrine.json")
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
    mem = Memory(data_dir=Path(config.DATA_DIR))
    return Agent(brain=BrainClient(brain_url=srv.base_url), memory=mem,
                 doctrine="Тестовая доктрата диеты")


# ---------- Ф76 «ДИАЕТА МАНИФЕСТА» ----------

def test_slim_manifest_half_the_weight():
    """Главный жалобщик промпта — манифест 3197 ток. Стройная версия
    легче полного каталога НЕ МЕНЕЕ чем вдвое: диета, а не стрижка."""
    slim_tok = config.token_estimate(manifest_slim())
    full_tok = config.token_estimate(manifest())
    assert slim_tok * 2 <= full_tok, (
        "стройный манифест %d ток не легче половины полного %d"
        % (slim_tok, full_tok))


def test_slim_manifest_keeps_contracts():
    """Диета не рвёт контракты, которые лечили живые болезни: точные
    имена инструментов, все имена быстрых команд, «memory_add нет»,
    закон фактов, сухой режим рук."""
    slim = manifest_slim()
    for tool in ("read_file", "write_file", "run_python", "browser_search",
                 "check_brackets", "ui_action", "code_patch", "apply_patch"):
        assert tool in slim, "стройный манифест потерял инструмент: " + tool
    for cmd in ("время", "статус", "посмотри", "руки <задача>",
                "скажи вслух <текст>", "запиши правило"):
        assert cmd in slim, "стройный манифест потерял команду: " + cmd
    assert "memory_add" in slim.lower()
    assert "ЗАКОН ФАКТОВ" in slim
    assert "СУХОМ режиме" in slim


def test_full_manifest_stays_for_mirror():
    """Полный каталог не выброшен — зеркало «изучи себя» показывает
    его целиком, с пояснениями команд."""
    full = manifest()
    assert "память v2, 23.11" in full          # аннотации на месте
    assert config.token_estimate(full) > config.token_estimate(manifest_slim())


def test_agent_prompt_uses_slim(agent):
    """Агент собирает систему из СТРОЙНОГО манифеста — полный в промпт
    не ездит (экономия ~1600 ток с каждого хода)."""
    sys_text = agent._static_core()
    assert "МОИ ВОЗМОЖНОСТИ" in sys_text
    # аннотация полного каталога в стройной версии отрезана
    assert "память v2, 23.11" not in sys_text


# ---------- Ф77 «СТАБИЛЬНЫЙ ПРЕФИКС» ----------

def test_system_static_between_turns(agent, srv):
    """СУПЕР-РЕШЕНИЕ круга: сообщение-система не меняется от хода к
    ходу — часы и RAG уехали в хвост. KV-кэш llama-server живёт,
    префилл падает с ~7400 ток до хвоста."""
    srv.reply_content = '{"answer": "первый"}'
    agent.handle("первый вопрос")
    first_sys = next(m for m in srv.calls[-1]["messages"]
                     if m["role"] == "system")["content"]
    srv.reply_content = '{"answer": "второй"}'
    agent.handle("второй вопрос, время идёт")
    second_sys = next(m for m in srv.calls[-1]["messages"]
                      if m["role"] == "system")["content"]
    assert first_sys == second_sys            # префикс стабилен
    assert "Состояние дома" not in second_sys  # часы — не в системе


def test_turn_context_rides_with_user(agent, srv):
    """Состояние и RAG едят свой хлеб в сообщении Создателя: живое
    чтение каждым ходом, слова Создателя — после служебного блока."""
    agent.memory.remember("диета контекста — закон дня-11")
    srv.reply_content = '{"answer": "вижу"}'
    agent.handle("что ты помнишь о диете?")
    user_msg = next(m for m in srv.calls[-1]["messages"] if m["role"] == "user")
    assert "КОНТЕКСТ ДОМА НА ЭТОТ ХОД" in user_msg["content"]
    assert "Состояние дома" in user_msg["content"]
    assert "диета контекста — закон дня-11" in user_msg["content"]
    assert "конец служебного контекста" in user_msg["content"]
    # слова Создателя — последними, живыми
    assert user_msg["content"].rstrip().endswith("что ты помнишь о диете?")


def test_history_between_system_and_user(agent, srv):
    """Порядок сообщений: система (статика) -> история -> хвостовый
    user. Префикс растёт append-only — кэш не рвётся серединой."""
    from core.dialog import DialogStore as DS
    history = DS.render_messages([
        {"role": "user", "text": "старый вопрос"},
        {"role": "assistant", "text": "старый ответ"},
    ])
    srv.reply_content = '{"answer": "ок"}'
    agent.handle("новый вопрос", history=history)
    roles = [m["role"] for m in srv.calls[-1]["messages"]]
    assert roles == ["system", "user", "assistant", "user"]


# ---------- Ф78 «ЧЕСТНЫЙ ЗАКОН КОНТЕКСТА» + ПОТОЛОК RAG ----------

def test_context_law_counts_history():
    """БОМБА 8268 обезврежена: закон считает историю ПОВЕРХ системы.
    Живой лог стоял на 7419+768 = 8187 — в пяти токенах от обреза
    ЯДРА (то самое нарушение №51, только изнутри)."""
    assert config.PROMPT_BUDGET_TOKENS + config.HISTORY_BUDGET_TOKENS \
        + config.GENERATION_BUDGET_TOKENS <= config.CONTEXT_TOKENS


def test_rag_memory_capped(agent):
    """«Запомни буфер» кладёт до 2000 симв (~660 ток): без потолка три
    таких воспоминания съедали 2000 ток каждый ход. Потолок Ф78 —
    обрезка по границе слов с честным многоточием."""
    fat = "жирное воспоминание " + "деталь " * 600   # ~4200 симв
    agent.memory.remember(fat)
    lines = agent._rag_lines("жирное воспоминание")
    assert lines, "воспоминание не нашлось"
    cap_chars = config.RAG_MEMORY_CAP_TOKENS * config.CHARS_PER_TOKEN_EST
    assert len(lines[0]) <= cap_chars + 1      # в потолке (многоточие — +1)
    assert lines[0].endswith("…")              # честная обрезка
    assert not lines[0].endswith(" …")         # по границе слов, не «деталь …»


def test_rag_total_tail_cheap(agent):
    """Три жирных воспоминания + состояние — хвост дешевле истории
    (1000): хвост не может стать второй историей."""
    for i in range(3):
        agent.memory.remember("жирное %d: %s" % (i, "деталь " * 600))
    tail = agent._turn_context("жирное")
    assert config.token_estimate(tail) <= 1000


# ---------- Ф79 «СВЕЖЕЕ УТРО» ----------

def _ts(days_ago: int, hhmm: str = "12:00") -> str:
    import datetime as dt
    day = dt.date.today() - dt.timedelta(days=days_ago)
    return day.strftime("%d.%m") + " " + hhmm


def test_past_days_fold_to_digest():
    """«Чат накопился за несколько дней»: сессия, живущая днями, больше
    не тащит вчерашние разговоры дословно — прошлые дни сворачиваются
    в выжимку, свежий день едет как есть."""
    turns = [
        {"role": "user", "text": "вчерашний вопрос", "ts": _ts(1)},
        {"role": "assistant", "text": "вчерашний ответ", "ts": _ts(1)},
        {"role": "user", "text": "сегодняшний вопрос", "ts": _ts(0)},
        {"role": "assistant", "text": "сегодняшний ответ", "ts": _ts(0)},
    ]
    msgs = DialogStore.render_messages(turns)
    digest = [m for m in msgs if "прошлые дни" in m["content"]]
    assert digest, "выжимки прошлых дней нет"
    assert "вчерашний вопрос" in digest[0]["content"]   # свёрнуто, но живо
    tail_text = "\n".join(m["content"] for m in msgs)
    assert "сегодняшний вопрос" in tail_text            # сегодня — дословно
    assert "сегодняшний ответ" in tail_text
    # вчерашнего НЕТ дословно — только выжимкой
    verbatim_yesterday = [m for m in msgs
                          if m["content"] == "вчерашний вопрос"]
    assert not verbatim_yesterday


def test_same_day_overflow_keeps_old_behaviour():
    """Переполнение одного дня сворачивается как раньше (Ф53 жива):
    выжимка зовётся «ранее в разговоре», новейший ход — дословно."""
    turns = []
    for i in range(50):
        turns.append({"role": "user" if i % 2 == 0 else "assistant",
                      "text": "ход %d: %s" % (i, "слово " * 40),
                      "ts": _ts(0, "1%d:00" % (i % 10))})
    msgs = DialogStore.render_messages(turns)
    assert msgs[-1]["content"].startswith("ход 49")        # новейший дословно
    assert any("Ранее в разговоре" in m["content"] for m in msgs)
    assert not any("прошлые дни" in m["content"] for m in msgs)


def test_broken_stamp_counts_as_fresh():
    """Битый штамп — консервативно «свежий»: лучше лишняя строка
    дословно, чем молча потерянный день."""
    turns = [
        {"role": "user", "text": "ход без штампа", "ts": ""},
        {"role": "user", "text": "живой ход", "ts": _ts(0)},
    ]
    msgs = DialogStore.render_messages(turns)
    assert msgs[-1]["content"] == "живой ход"
    assert not any("прошлые дни" in m["content"] for m in msgs)


def test_newest_always_verbatim_multiday():
    """Гарантия Ф53 держится и на многодневной сессии: новейший ход —
    всегда дословно, каким бы длинным ни был вчерашний хвост."""
    turns = [{"role": "user", "text": "вчера %s" % ("слово " * 300),
              "ts": _ts(2)},
             {"role": "assistant", "text": "позавчера", "ts": _ts(3)},
             {"role": "user", "text": "сейчас", "ts": _ts(0)}]
    msgs = DialogStore.render_messages(turns)
    assert msgs[-1]["content"] == "сейчас"


# ---------- Ф80 «ЗАКОН ИНСТРУМЕНТА» ----------

def test_action_is_empty_verdicts():
    """«баланс: ОК» живого лога: мозг звал инструменты с пустыми
    аргументами. Приговор — по значениям, не по наличию ключей."""
    assert _action_is_empty({"tool": "check_brackets", "args": {}})
    assert _action_is_empty({"tool": "code_patch", "args": {"path": "  "}})
    assert _action_is_empty({"tool": "check_brackets"})
    assert not _action_is_empty({"tool": "check_brackets",
                                 "args": {"text": "(())"}})
    assert not _action_is_empty({"tool": "run_python",
                                 "args": {"code": 123}})


def test_empty_action_retried_then_honest(agent, srv):
    """Пусто-аргументное действие без слов — переспрашивается ОДИН раз
    с уколом «ответь текстом»; после второго промаха ход не роняется —
    инструмент честно отвечает своей шпаргалкой."""
    srv.script = [
        json.dumps({"action": {"tool": "check_brackets", "args": {}}},
                   ensure_ascii=False),
        '{"answer": "звала инструмент зря — вот мои мысли текстом"}',
    ]
    r = agent.handle("я предлагаю новое правило, найди изъян")
    assert r.source == "brain"
    assert "мысли текстом" in r.text
    assert len(srv.calls) == 2                    # был переспрос
    last_user = next(m for m in srv.calls[-1]["messages"]
                     if m["role"] == "user")["content"]
    assert "БЕЗ аргументов" in last_user          # укол доехал до мозга
    # повторный промах — честный результат, не тишина
    srv.script = [
        json.dumps({"action": {"tool": "check_brackets", "args": {}}},
                   ensure_ascii=False),
        json.dumps({"action": {"tool": "check_brackets", "args": {}}},
                   ensure_ascii=False),
    ]
    r2 = agent.handle("ещё раз про правило")
    assert r2.text.strip()                        # шпаргалка инструмента жива


def test_preamble_carries_tool_law(agent, srv):
    """Закон инструмента — в преамбуле каждого мозгового хода: разговор
    о мыслях и правилах — текстом, инструмент — по явной просьбе."""
    srv.reply_content = '{"answer": "поняла"}'
    agent.handle("поговорим о правилах")
    sys_msg = next(m for m in srv.calls[-1]["messages"]
                   if m["role"] == "system")["content"]
    assert "ЯВНО" in sys_msg
    assert "ТЕКСТОМ" in sys_msg


def test_action_with_real_args_not_nudged(agent, srv):
    """Настоящее действие (с аргументами) законом не задето: маршрут
    действия работает как раньше, с первой попытки."""
    srv.script = [
        json.dumps({"action": {"tool": "check_brackets",
                               "args": {"text": "(()"}}},
                   ensure_ascii=False),
    ]
    r = agent.handle("проверь скобки (()")
    assert r.tool_used == "check_brackets"
    assert len(srv.calls) == 1                    # переспроса не было
