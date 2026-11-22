# -*- coding: utf-8 -*-
"""tests/test_audit_round3.py — якоря аудита Создателя, РАУНД 3 (22.11, ночь).

Создатель разобрал core/agent.py построчно: 18 багов (3 критических,
3 высоких, 5 средних, 7 низких). Порядок дома прежний: каждый фикс
закреплён тестом — баг без якоря возвращается.

Нумерация — из аудита Создателя (№1..№18). Ф75 «свобода внедрять
себя» (директича Создателя в том же сообщении) — отдельным блоком
внизу: резолюция, дым-тест, автоОткат.
"""
import json
import sys
import warnings
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import config, identity, repair  # noqa: E402
from safety import guard  # noqa: E402


# ---------------------------------------------------------------
# Фикстуры (контракт test_agent/test_audit_round2, tmp-дом)
# ---------------------------------------------------------------

@pytest.fixture()
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("MARFA_HOME", str(tmp_path))
    monkeypatch.setattr(config, "HOME_DIR", tmp_path)
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(config, "LOGS_DIR", tmp_path / "logs")
    monkeypatch.setattr(config, "GUARD_LOG_FILE",
                        tmp_path / "logs" / "guard_log.jsonl")
    monkeypatch.setattr(config, "CANARIES_FILE",
                        tmp_path / "data" / "canaries.json")
    monkeypatch.setattr(config, "DOCTRINE_FILE",
                        tmp_path / "data" / "creator_doctrine.json")
    monkeypatch.setattr(config, "GENOME_FILE",
                        tmp_path / "data" / "context_genome.json")
    monkeypatch.setattr(config, "QUESTIONS_FILE",
                        tmp_path / "data" / "questions.json")
    monkeypatch.setattr(config, "PATCHES_DIR", tmp_path / "data" / "patches")
    monkeypatch.setattr(config, "SELF_WRITE_FILE",
                        tmp_path / "data" / "self_write.json")
    monkeypatch.setattr(config, "REPAIR_LOG_FILE",
                        tmp_path / "logs" / "repair_log.jsonl")
    monkeypatch.setattr(config, "DIARY_DIR", tmp_path / "data" / "diary")
    monkeypatch.setattr(config, "LIVE_VOICE_FILE",
                        tmp_path / "data" / "live_voice.json")
    monkeypatch.setattr(guard, "_LOG", None)
    config.ensure_dirs()
    yield tmp_path


@pytest.fixture()
def srv(home, monkeypatch):
    from tests.fake_llama_server import start_fake_brain
    server = start_fake_brain()
    monkeypatch.setattr(config, "BRAIN_URL", server.base_url)
    yield server
    server.shutdown()


@pytest.fixture()
def agent(srv):
    from core.agent import Agent
    from core.brain import BrainClient
    from core.memory import Memory
    return Agent(brain=BrainClient(brain_url=srv.base_url),
                 memory=Memory(data_dir=Path(config.DATA_DIR)),
                 doctrine="Тестовая доктрина")


# ---------------------------------------------------------------
# 🔴 Критические
# ---------------------------------------------------------------

def test_n1_identity_escape_compiles_clean():
    """№1: в agent.py нет невалидных escape — модуль чист даже под
    -W error::SyntaxWarning (Python 3.12+ иначе ругается на C:\\Marfa)."""
    src = (Path(__file__).resolve().parents[1] / "core" / "agent.py") \
        .read_text(encoding="utf-8")
    with warnings.catch_warnings():
        warnings.simplefilter("error", SyntaxWarning)
        compile(src, "agent.py", "exec")


def test_n2_math_pow_dos(agent, srv):
    """№2: 9**9**9**9 и 2**10000000000 не вешают воркер — уходят к мозгу."""
    srv.reply_content = '{"answer": "я подумала"}'
    for bad in ("9**9**9**9", "2**10000000000", "10**1000**1000",
                "9**9999999"):
        r = agent.handle("вычисли " + bad)
        assert r.source == "brain", bad
        assert srv.calls, bad
    # обычная степень — по-прежнему мгновенно на Python
    assert agent.handle("вычисли 2**10").text == "1024"
    assert agent.handle("вычисли 3**5 + 1").text == "244"


def test_n2_math_len_and_nodes_guard(agent, srv):
    """№2: хвост закона — длина и дерево тоже ограничены."""
    srv.reply_content = '{"answer": "слишком длинно"}'
    r = agent.handle("вычисли " + "1+" * 150 + "1")
    assert r.source == "brain"


def test_n3_remember_word_boundary(agent, srv):
    """№3: «помнишь, как мы гуляли?» — вопрос мозгу, не приказ памяти."""
    srv.reply_content = '{"answer": "вспоминаю"}'
    r = agent.handle("помнишь, как мы гуляли?")
    assert r.source == "brain"
    assert not agent.memory.recall("гуляли")
    r = agent.handle("вспомнишь что-нибудь?")
    assert r.source == "brain"
    # а настоящий приказ — работает, и без мусора в payload
    r = agent.handle("помни: купить хлеб")
    assert r.tool_used == "remember" and "запомнила" in r.text
    got = agent.memory.recall("хлеб")
    assert got and got[0]["text"] == "купить хлеб"


def test_n3_remember_infinitive_not_command(agent, srv):
    """№3: «помнить» (инфинитив) — тоже не приказ памяти."""
    srv.reply_content = '{"answer": "философия"}'
    r = agent.handle("помнить — значит жить")
    assert r.source == "brain"


# ---------------------------------------------------------------
# 🟠 Высокие
# ---------------------------------------------------------------

def test_n4_fast_crash_falls_to_brain(agent, srv, monkeypatch):
    """№4: крах быстрой команды не роняет чат — ответ говорит мозг."""
    srv.reply_content = '{"answer": "жива"}'

    def boom(text):
        raise RuntimeError("сенсор умер")
    monkeypatch.setattr(agent, "_fast", boom)
    r = agent.handle("посмотри")
    assert r.source == "brain" and r.text == "жива"


def test_n4_eyes_crash_does_not_kill_turn(agent, srv, monkeypatch):
    """№4: реальный сенсор (глаза) упал — ход живёт."""
    srv.reply_content = '{"answer": "не увидела"}'

    def boom():
        raise RuntimeError("порт сгорел")
    monkeypatch.setattr("core.eyes.health_cached", boom)
    r = agent.handle("статус")
    assert "Состояние дома" in r.text      # команда жива, глаза — честно мертвы
    r = agent.handle("расскажи о вечере")
    assert r.source == "brain"             # мозговой трек тоже жив


def test_n5_act_args_not_dict(agent, srv):
    """№5: args строкой от мозга — брак формата, не краш дома."""
    srv.reply_content = ('{"action": {"tool": "check_brackets", '
                         '"args": "строка"}}')
    r = agent.handle("проверь скобки")
    assert r.tool_used == "check_brackets"
    assert "баланс" in r.text


def test_n5_act_bad_path_type(agent, srv):
    """№5: path: 123 — честный отказ, не TypeError в панели."""
    srv.reply_content = ('{"action": {"tool": "read_file", '
                         '"args": {"path": 123}}}')
    r = agent.handle("загрузи файл конфигурации")
    assert r.source == "brain"
    assert "СТРАЖ" in r.text or "споткнулся" in r.text


def test_n6_creator_gate_crash_does_not_kill_chat(agent, srv, monkeypatch):
    """№6: калитка споткнулась — чат жив, урок летит архитектору."""
    srv.reply_content = '{"answer": "жива"}'

    def boom(text):
        raise RuntimeError("нет .env")
    monkeypatch.setattr("core.creator_gate.check", boom)
    r = agent.handle("привет")
    assert r.source == "brain" and r.text == "жива"


# ---------------------------------------------------------------
# 🟡 Средние
# ---------------------------------------------------------------

def test_n7_answer_no_space_after_colon(agent, home):
    """№7: «ответ 1:текст» и «ответ 1.текст» — тоже ответы."""
    from core.questions import QuestionBank
    qb = QuestionBank()
    qb.add("какой квант?", source="audit")
    r = agent.handle("ответ 1:Q4_K_M")
    assert r.tool_used == "questions"
    assert "Q4_K_M" in r.text
    qb2 = QuestionBank()
    assert qb2.open_items() == []          # вопрос закрыт


def test_n8_trailing_punctuation(agent, srv):
    """№8: «время?», «статус!», «вопросы?», «о чём думаешь?» — команды."""
    assert agent.handle("время?").source == "python"
    assert agent.handle("статус!").tool_used == "status"
    assert agent.handle("вопросы?").tool_used == "questions"
    assert agent.handle("что хотела спросить?").tool_used == "questions"
    assert agent.handle("о чём думаешь?").tool_used == "reflection"
    assert agent.handle("патчи?").tool_used == "patches"
    assert srv.calls == []                 # мозг молчал во всех


def test_n8_calc_trailing_question(agent):
    """№8: «вычисли 2+2?» — посчитано, а не улетело в мозг."""
    assert agent.handle("вычисли 2+2?").text == "4"


def test_n9_answer_null(agent, srv):
    """№9: {"answer": null} — честное «Нет ответа», не строка «None»."""
    srv.reply_content = '{"answer": null}'
    r = agent.handle("привет")
    assert r.text == "Нет ответа"
    srv.reply_content = '{"answer": ""}'
    r = agent.handle("ещё раз")
    assert r.text == "Нет ответа"


def test_n10_house_state_sensor_crash_honest(monkeypatch):
    """№10: упавший сенсор состояния — не «мозг недоступен»."""
    def boom():
        raise RuntimeError("файл статуса битый")
    monkeypatch.setattr(identity, "ears_diagnosis", boom)
    from core.agent import _house_state
    state = _house_state()
    assert "Состояние дома" in state
    assert "диагноз недоступен" in state      # честно, построчно


def test_n10_context_crash_brain_still_answers(agent, srv, monkeypatch):
    """№10: крах сборки промпта — ход живёт на статичном ядре."""
    srv.reply_content = '{"answer": "жива"}'

    def boom(text):
        raise RuntimeError("RAG умер")
    monkeypatch.setattr(agent, "_system_extra", boom)
    r = agent.handle("привет")
    assert r.source == "brain" and r.text == "жива"
    sys_msg = next(m for m in srv.calls[-1]["messages"]
                   if m["role"] == "system")
    assert "ЯДРО — кто я" in sys_msg["content"]   # ядро в промпте живо


def test_n11_status_home_exact(agent, srv):
    """№11: «статус домашнего сервера» — вопрос мозгу, не _house_state."""
    srv.reply_content = '{"answer": "про сервер"}'
    r = agent.handle("статус домашнего сервера")
    assert r.source == "brain"
    r = agent.handle("статус дома")
    assert r.tool_used == "status"


# ---------------------------------------------------------------
# 🟢 Низкие / качество
# ---------------------------------------------------------------

def test_n12_inf_and_complex(agent, srv):
    """№12: inf — «не число», complex — к мозгу."""
    r = agent.handle("вычисли 1e308*10")
    assert r.text == "не число" and r.source == "python"
    srv.reply_content = '{"answer": "мнимые числа — не мой жанр"}'
    r = agent.handle("вычисли (-1)**0.5")
    assert r.source == "brain"


def test_n13_math_bool_rejected(agent, srv):
    """№13: True/False — не числа дома."""
    srv.reply_content = '{"answer": "не понял"}'
    assert agent.handle("вычисли True").source == "brain"


def test_n14_brackets_no_arg_hint(agent, srv):
    """№14: «скобки» без текста — подсказка, не проверка самого слова."""
    r = agent.handle("скобки")
    assert "что проверить" in r.text
    r = agent.handle("скобки (a[b)]")
    assert "НЕСБАЛАНСИРОВАНО" in r.text


def test_n17_minus_zero(agent):
    """№17: -0.0 печатается как «-0» — честные цифры до знака."""
    from core.agent import _fmt_num
    assert _fmt_num(-0.0) == "-0"
    assert _fmt_num(0.0) == "0"
    assert _fmt_num(-0) == "0"              # int нуля знака не имеет


def test_n18_empty_remember_hint(agent, srv):
    """№18: пустой «помни»/«вспомни» — подсказка на месте, не мозг."""
    r = agent.handle("помни")
    assert "что запомнить" in r.text and r.source == "python"
    r = agent.handle("вспомни")
    assert "что вспомнить" in r.text and r.source == "python"
    assert srv.calls == []


def test_n18_answer_number_only_hint(agent, srv):
    """№18 (хвост): «ответ 3» без текста — уточнение на месте."""
    r = agent.handle("ответ 3")
    assert "что ответить" in r.text and r.source == "python"


# ---------------------------------------------------------------
# Ф75. СВОБОДА ВНЕДРЯТЬ СЕБЯ
# ---------------------------------------------------------------

def _make_patch_dir(n: int, target: Path, code: str, req="тест") -> Path:
    d = config.PATCHES_DIR / ("%04d" % n)
    d.mkdir(parents=True, exist_ok=True)
    (d / target.name).write_text(code, encoding="utf-8")
    (d / "meta.json").write_text(
        json.dumps({"target": str(target), "file_name": target.name,
                    "requirement": req, "applied": False},
                   ensure_ascii=False), encoding="utf-8")
    return d


def test_f75_gate_closed_without_resolution(home):
    """Без резолюции — честный отказ, дом не тронут."""
    target = home / "core" / "some_mod.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("x = 1\n", encoding="utf-8")
    _make_patch_dir(1, target, "x = 2\n")
    rep = repair.self_apply(1)
    assert "не разрешено" in rep
    assert "разреши внедрять себя" in rep
    assert target.read_text(encoding="utf-8") == "x = 1\n"


def test_f75_resolution_lifecycle(home):
    """Одна фраза включила, одна выключила — воля в data/, не в коде."""
    assert repair.self_write_resolution() is None
    assert "Резолюция записана" in repair.allow_self_write()
    assert repair.self_write_resolution() is not None
    assert "снята" in repair.forbid_self_write()
    assert repair.self_write_resolution() is None


def test_f75_self_apply_green_path(home):
    """Зелёный дым-тест: файл заменён, meta — applied, бэкап на месте."""
    target = home / "core" / "hello_mod.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("def hi():\n    return 'привет'\n", encoding="utf-8")
    d = _make_patch_dir(1, target, "def hi():\n    return 'привет v2'\n")
    repair.allow_self_write()
    rep = repair.self_apply(1)
    assert "ВНЕДРЁН мною" in rep
    assert "привет v2" in target.read_text(encoding="utf-8")
    meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
    assert meta["applied"] is True and meta["self_applied"] is True
    assert (d / "backup_hello_mod.py").read_text(encoding="utf-8") \
        .startswith("def hi():\n    return 'привет'")
    # повторно не внедряет
    assert "уже применён" in repair.self_apply(1)


def test_f75_red_smoke_rolls_back(home):
    """Красный дым-тест: автоОткат возвращает старый файл на место."""
    target = home / "core" / "bad_mod.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("def f():\n    return 1\n", encoding="utf-8")
    (home / "tests").mkdir(exist_ok=True)
    (home / "conftest.py").write_text(
        "import sys, pathlib\n"
        "sys.path.insert(0, str(pathlib.Path(__file__).parent))\n",
        encoding="utf-8")
    (home / "tests" / "test_bad_mod.py").write_text(
        "from core.bad_mod import f\n\n"
        "def test_f():\n    assert f() == 2\n", encoding="utf-8")
    _make_patch_dir(2, target, "def f():\n    return 3\n",
                    req="сломать, чтобы проверить откат")
    repair.allow_self_write()
    rep = repair.self_apply(2)
    assert "НЕ ВНЕДРЁН" in rep
    assert "я вернула на место" in rep
    assert target.read_text(encoding="utf-8") == "def f():\n    return 1\n"
    meta = json.loads((config.PATCHES_DIR / "0002" / "meta.json")
                      .read_text(encoding="utf-8"))
    assert meta["applied"] is False


def test_f75_make_patch_mentions_self_apply(home, monkeypatch):
    """Кодер написал патч — Марфа сразу говорит, что может внедрить сама."""
    monkeypatch.setattr(repair, "ensure_server",
                        lambda wait_secs=None: (True, "кодер на посту (шов)"))
    monkeypatch.setattr(repair, "release", lambda: "кодер лёг (шов)")
    monkeypatch.setattr(repair, "_ask_coder",
                        lambda prompt, max_tokens=None:
                        "```python\nx = 2\n```")
    target = home / "core" / "some_mod.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("x = 1\n", encoding="utf-8")
    rep = repair.make_patch(str(target), "сделай x = 2")
    assert "ГОТОВ" in rep and "примени" in rep
    assert "внедри" not in rep               # резолюции нет — не предлагает
    repair.allow_self_write()
    rep = repair.make_patch(str(target), "сделай x = 2")
    assert "внедри патч" in rep               # резолюция есть — предлагает


def test_f75_brain_tool_apply_patch(agent, srv, home, monkeypatch):
    """Мозг зовёт apply_patch — та же броня, что у быстрой команды."""
    calls = []
    monkeypatch.setattr(repair, "self_apply",
                        lambda n: calls.append(n) or "внедрила №%d" % n)
    srv.reply_content = ('{"action": {"tool": "apply_patch", '
                         '"args": {"patch": 3}}}')
    r = agent.handle("внедри третий патч, пожалуйста")
    assert r.tool_used == "apply_patch"
    assert calls == [3]
    # номер-мусор — честный вопрос, не краш
    srv.reply_content = ('{"action": {"tool": "apply_patch", '
                         '"args": {"patch": "три"}}}')
    r = agent.handle("внедри")
    assert "какой патч" in r.text


def test_f75_fast_commands(agent, home, monkeypatch):
    """«разреши/запрети внедрять себя» и «внедри патч N» — быстрые."""
    monkeypatch.setattr(repair, "allow_self_write",
                        lambda: "Резолюция записана (шов)")
    monkeypatch.setattr(repair, "forbid_self_write", lambda: "Резолюция снята (шов)")
    seen = []
    monkeypatch.setattr(repair, "self_apply",
                        lambda n: seen.append(n) or "внедрила №%d" % n)
    r = agent.handle("разреши внедрять себя")
    assert r.tool_used == "self_write"
    r = agent.handle("внедри патч 7?")
    assert r.tool_used == "self_apply" and seen == [7]
    r = agent.handle("запрети внедрять себя!")
    assert r.tool_used == "self_write"


def test_f75_manifest_tells_brain_about_freedom():
    """Мозг знает про apply_patch и резолюцию — из одного списка TOOLS."""
    names = [name for name, _ in identity.TOOLS]
    assert "apply_patch" in names
    assert "apply_patch" in identity.manifest()
    assert "разреши внедрять себя" in identity.manifest()
    for cmd in ("внедри патч", "разреши внедрять себя"):
        assert cmd in identity.manifest()
