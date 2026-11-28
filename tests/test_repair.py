# -*- coding: utf-8 -*-
r"""tests/test_repair.py — САМОЛЕЧЕНИЕ ДОМА v1 (ТЗ_Самолечение_v1, 22.11).

Создатель: «давать Марфе самой себя лечить и доделывать... среди умных
рук у неё есть очень прокачанная модель 7b, которая хорошо знает питон».
qwen2.5-coder-7b проснулась в строй пятым слугой (порт 8085).

Якоря:
- make_patch пишет ТОЛЬКО в песочницу data\patches\ — код дома не
  трогается до команды Создателя «примени патч N»;
- страж патча: только .py, лимит строк, AST-синтаксис, канарейки,
  «вернул без изменений» = брак;
- применение: бэкап + запись через руки (страж), откат возвращает;
- VRAM-танец — тот же, что у рук (швы ensure_server/release).

Швы: _ask_coder / ensure_server / release / _find_model — подменяются,
реальный сервер не нужен.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import agent, config, identity, repair  # noqa: E402
from safety import guard  # noqa: E402

GOOD_CODE = "def greet():\n    return 'привет'\n"


@pytest.fixture
def home(tmp_path, monkeypatch):
    """Изолированный дом: ремонт не трогает файлы станции."""
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


def _seen_prompts(monkeypatch, answer):
    """Кодер «отвечает» answer; возвращаем список промптов, что получил."""
    seen = []
    monkeypatch.setattr(repair, "_ask_coder",
                        lambda prompt, max_tokens=None:
                        (seen.append(prompt) or answer))
    return seen


# ---------- страж патча ----------

def test_extract_code_python_block():
    answer = "Вот файл:\n```python\nprint('hi')\n```\nготово"
    assert repair._extract_code(answer) == "print('hi')\n"


def test_extract_code_plain_block():
    assert repair._extract_code("```\nx = 1\n```") == "x = 1\n"


def test_extract_code_no_block_rejected():
    with pytest.raises(ValueError) as ei:
        repair._extract_code("просто болтовня без кода")
    assert "без блока кода" in str(ei.value)


def test_check_patch_syntax_error_rejected(home):
    with pytest.raises(ValueError) as ei:
        repair._check_patch(home / "x.py", "def broken(:\n")
    assert "не-Python" in str(ei.value)


def test_check_patch_only_py_files(home):
    with pytest.raises(ValueError) as ei:
        repair._check_patch(home / "x.txt", GOOD_CODE)
    assert "только .py" in str(ei.value)


def test_check_patch_line_limit(home):
    big = "\n".join("x = %d" % i for i in range(300)) + "\n"
    with pytest.raises(ValueError) as ei:
        repair._check_patch(home / "x.py", big)
    assert "лимита" in str(ei.value)


def test_check_patch_canary_rejected(home, monkeypatch):
    monkeypatch.setattr(guard, "check_secrets",
                        lambda text: guard.Verdict("CRITICAL", "deny",
                                                   "утечка канарейки",
                                                   "secret.canary"))
    with pytest.raises(ValueError) as ei:
        repair._check_patch(home / "x.py", GOOD_CODE)
    assert "СТРАЖ" in str(ei.value)


def test_check_patch_good_code_passes(home):
    repair._check_patch(home / "x.py", GOOD_CODE)   # не поднял исключений


# ---------- ПС-1: make_patch — патч только в песочницу ----------

def test_make_patch_new_file(home, monkeypatch):
    _seen_prompts(monkeypatch, "```python\n" + GOOD_CODE + "```")
    out = repair.make_patch("scripts/hello.py", "напиши приветствие")
    assert "ГОТОВ" in out and "примени патч 0001" in out
    d = home / "data" / "patches" / "0001"
    assert (d / "hello.py").read_text(encoding="utf-8") == GOOD_CODE
    meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
    assert meta["new_file"] is True and meta["applied"] is False
    assert meta["requirement"] == "напиши приветствие"
    # ГЛАВНЫЙ ЗАКОН: цель не тронута — патч лёг в песочницу
    assert not (home / "scripts" / "hello.py").exists()


def test_make_patch_existing_file(home, monkeypatch):
    target = home / "scripts" / "calc.py"
    target.parent.mkdir(parents=True)
    target.write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    seen = _seen_prompts(monkeypatch,
                         "```python\ndef add(a, b):\n    return a - b\n```")
    out = repair.make_patch("scripts/calc.py", "замени сложение вычитанием")
    assert "ГОТОВ" in out
    # кодер видел ОРИГИНАЛ файла и требование
    assert "def add(a, b):\n    return a + b\n" in seen[0]
    assert "замени сложение вычитанием" in seen[0]
    # цель НЕ изменилась — применение отдельной командой Создателя
    assert "return a + b" in target.read_text(encoding="utf-8")


def test_make_patch_unchanged_rejected(home, monkeypatch):
    target = home / "scripts" / "calc.py"
    target.parent.mkdir(parents=True)
    src = "def add(a, b):\n    return a + b\n"
    target.write_text(src, encoding="utf-8")
    _seen_prompts(monkeypatch, "```python\n" + src + "```")
    out = repair.make_patch("scripts/calc.py", "сделай что-нибудь")
    assert "БЕЗ ИЗМЕНЕНИЙ" in out
    assert not (home / "data" / "patches").exists() or not any(
        (home / "data" / "patches").iterdir())


def test_make_patch_bad_syntax_rejected(home, monkeypatch):
    _seen_prompts(monkeypatch, "```python\ndef broken(:\n```")
    out = repair.make_patch("scripts/bad.py", "сломай всё")
    assert "забракован" in out
    assert not (home / "scripts" / "bad.py").exists()


def test_make_patch_no_server_honest(home, monkeypatch):
    monkeypatch.setattr(repair, "ensure_server",
                        lambda wait_secs=None: (False, "модели нет в чулане"))
    out = repair.make_patch("scripts/x.py", "что-то")
    assert "КОДЕР не поднялся" in out and "модели нет" in out


def test_make_patch_usage_without_requirement(home):
    out = repair.make_patch("", "")
    assert "почини что" in out and "Формат" in out


def test_make_patch_big_file_honest(home):
    # круг 22 (Ф118): корень — не полка (замок R1), большой модуль
    # живёт в подпапке — как в живом доме (core/big.py)
    target = home / "core" / "big.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("\n".join("x = %d" % i for i in range(300)),
                      encoding="utf-8")
    out = repair.make_patch("core/big.py", "измени")
    assert "больше" in out and "архитектору" in out


def test_make_patch_outside_home_rejected(home):
    with pytest.raises(PermissionError):
        repair.make_patch("../outside.py", "сломай защиту")


# ---------- ПС-2: применить / откатить / список ----------

def _make_patch_0001(home, monkeypatch, code=None):
    target = home / "scripts" / "calc.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("OLD = 1\n", encoding="utf-8")
    answer = "```python\n" + (code or "NEW = 2\n") + "```"
    monkeypatch.setattr(repair, "_ask_coder", lambda prompt, max_tokens=None: answer)
    repair.make_patch("scripts/calc.py", "обнови файл")
    return target


def test_apply_patch_writes_and_backs_up(home, monkeypatch):
    target = _make_patch_0001(home, monkeypatch)
    out = repair.apply_patch(1)
    assert "ПРИМЕНЁН" in out
    assert target.read_text(encoding="utf-8") == "NEW = 2\n"
    backup = home / "data" / "patches" / "0001" / "backup_calc.py"
    assert backup.read_text(encoding="utf-8") == "OLD = 1\n"
    meta = json.loads((home / "data" / "patches" / "0001" / "meta.json")
                      .read_text(encoding="utf-8"))
    assert meta["applied"] is True


def test_rollback_restores_original(home, monkeypatch):
    target = _make_patch_0001(home, monkeypatch)
    repair.apply_patch(1)
    out = repair.rollback_patch(1)
    assert "ОТКАЧЕН" in out
    assert target.read_text(encoding="utf-8") == "OLD = 1\n"


def test_apply_missing_patch_honest(home):
    assert "патча №7 нет" in repair.apply_patch(7)
    assert "патча №7 нет" in repair.rollback_patch(7)


def test_apply_rechecks_syntax(home, monkeypatch):
    target = _make_patch_0001(home, monkeypatch)
    # файл патча испортили ПОСЛЕ написания — применение обязано отказаться
    # (круг 35, К4: сперва sha256 ловит подмену содержимого, а мета без
    # подписи — старые патчи — доходит до синтакс-чека)
    (home / "data" / "patches" / "0001" / "calc.py").write_text(
        "def broken(:\n", encoding="utf-8")
    out = repair.apply_patch(1)
    assert ("ИЗМЕНЁН после создания" in out) or ("не применяется" in out)
    assert target.read_text(encoding="utf-8") == "OLD = 1\n"


def test_apply_old_meta_without_sha_still_checked(home, monkeypatch):
    # мета без sha256 (патчи до круга 35) — синтакс-чек живёт
    _make_patch_0001(home, monkeypatch)
    d = home / "data" / "patches" / "0001"
    meta = repair._read_meta(d)
    meta.pop("sha256", None)
    repair._write_meta(d, meta)
    (d / "calc.py").write_text("def broken(:\n", encoding="utf-8")
    out = repair.apply_patch(1)
    assert "не применяется" in out


def test_apply_repeats_refused(home, monkeypatch):
    # К8: повторное применение не затирает бэкап уже-пропатченным файлом
    target = _make_patch_0001(home, monkeypatch)
    first = repair.apply_patch(1)
    assert "ПРИМЕНЁН" in first
    second = repair.apply_patch(1)
    assert "уже применён" in second
    # цель не перезаписана повторным применением (бэкап не тронут)
    assert target.read_text(encoding="utf-8") == "NEW = 2\n"


def test_rollback_new_file_no_backup_honest(home, monkeypatch):
    monkeypatch.setattr(repair, "_ask_coder",
                        lambda prompt, max_tokens=None:
                        "```python\n" + GOOD_CODE + "```")
    repair.make_patch("scripts/fresh.py", "новый файл")
    out = repair.rollback_patch(1)
    # круг 35 (В10): неприменённый патч откатывать нечего — цель живёт
    # новыми правками
    assert "не применён" in out


def test_rollback_new_file_after_apply_unlinks(home, monkeypatch):
    # К5 симметрия: новый файл, применённый и откаченный, исчезает —
    # не «удали руками» (симметрия автоОтката apply_patch)
    monkeypatch.setattr(repair, "_ask_coder",
                        lambda prompt, max_tokens=None:
                        "```python\n" + GOOD_CODE + "```")
    monkeypatch.setattr(repair, "_smoke_test", lambda t: (True, "pytest ок"))
    repair.make_patch("scripts/fresh.py", "новый файл")
    assert "ПРИМЕНЁН" in repair.apply_patch(1)
    out = repair.rollback_patch(1)
    assert "убран" in out
    assert not (home / "scripts" / "fresh.py").is_file()


def test_list_patches_statuses(home, monkeypatch):
    _make_patch_0001(home, monkeypatch)
    listing = repair.list_patches()
    # Ф75: статус «ждёт внедрения» — внедрить может Создатель или сама
    # Марфа (с резолюцией); «ждёт Создателя» больше не вся правда
    assert "ждёт внедрения" in listing and "№0001" in listing
    repair.apply_patch(1)
    listing = repair.list_patches()
    assert "применён" in listing


def test_list_patches_empty_honest(home):
    assert "патчей пока нет" in repair.list_patches()


def test_repair_log_written(home, monkeypatch):
    _make_patch_0001(home, monkeypatch)
    log = (home / "logs" / "repair_log.jsonl").read_text(encoding="utf-8")
    assert "calc.py" in log and '"ok": true' in log


# ---------- агент: команды и инструмент мозга ----------

class FakeBrain:
    def __init__(self):
        self.calls = 0

    def ask_json(self, *a, **k):
        self.calls += 1
        return {"answer": "ок"}


class FakeMemory:
    def remember(self, text):
        pass

    def recall(self, query, top_k=3):
        return []


def test_agent_patches_commands(home, monkeypatch):
    a = agent.Agent(brain=FakeBrain(), memory=FakeMemory())
    monkeypatch.setattr(repair, "list_patches", lambda: "№0001 — ждёт")
    monkeypatch.setattr(repair, "apply_patch", lambda n: "ПРИМЕНЁН %d" % n)
    monkeypatch.setattr(repair, "rollback_patch", lambda n: "ОТКАЧЕН %d" % n)
    assert a.handle("патчи").tool_used == "patches"
    r = a.handle("примени патч 1")
    assert r.tool_used == "patch_apply" and "ПРИМЕНЁН" in r.text
    r = a.handle("откати патч 1")
    assert r.tool_used == "patch_rollback" and "ОТКАЧЕН" in r.text
    assert a.brain.calls == 0


def test_agent_fix_command_parses_colon(home, monkeypatch):
    r"""«почини <файл>: <что сделать>» — путь и требование режутся по
    двоеточию (двоеточие диска C:\ — не разделитель)."""
    a = agent.Agent(brain=FakeBrain(), memory=FakeMemory())
    got = {}
    monkeypatch.setattr(repair, "make_patch",
                        lambda path, req: got.update(path=path, req=req)
                        or "КОДЕР (шов)")
    r = a.handle("почини scripts\\hello.py: добавь приветствие")
    assert r.tool_used == "repair" and a.brain.calls == 0
    assert got["path"] == "scripts\\hello.py"
    assert got["req"] == "добавь приветствие"
    a.handle("почини core/x.py — поправь цикл")
    assert got["path"] == "core/x.py" and got["req"] == "поправь цикл"


def test_agent_brain_tool_code_patch(home, monkeypatch):
    """Мозг ДОВЕРЯЕТ требование кодеру — как ui_action рукам."""
    a = agent.Agent(brain=FakeBrain(), memory=FakeMemory())
    got = {}
    monkeypatch.setattr(repair, "make_patch",
                        lambda path, req: got.update(path=path, req=req)
                        or "патч готов (шов)")
    r = a._act({"tool": "code_patch",
                "args": {"path": "scripts/x.py", "requirement": "фикс"}})
    assert r.tool_used == "code_patch" and "патч готов" in r.text
    assert got == {"path": "scripts/x.py", "req": "фикс"}


# ---------- самопознание знает о ремонтной бригаде ----------

def test_identity_knows_coder(home):
    names = [name for name, _ in identity.TOOLS]
    # Ф75: после code_patch приехал apply_patch — свобода внедрять себя;
    # оба имени — из одного списка TOOLS (единая истина)
    assert names[-2:] == ["code_patch", "apply_patch"]
    assert "code_patch" in identity.tool_names()
    assert "apply_patch" in identity.tool_names()
    assert "почини <файл>: <что сделать>" in identity.FAST_COMMANDS
    assert "внедри патч" in " ".join(identity.FAST_COMMANDS)
    m = identity.manifest()
    assert "code_patch" in m and "песочницу" in m
    assert "apply_patch" in m and "разреши внедрять себя" in m
    rep = identity.capabilities_report(memory=None, eyes_ok=True, ears_ok=True)
    assert "кодер" in rep.lower()


def test_config_law_anchors():
    assert config.PORT_CODER == 8085
    assert config.CODER_MAX_FILE_LINES <= 250      # v1: не расползается
    assert str(config.PATCHES_DIR).endswith("patches")


def test_agent_patch_live_forms(home, monkeypatch):
    r"""УРОК ЖИВОГО ЛОГА (день-18, 28.11): Создатель СЕМЬ раз звал
    внедрить патч №0002 живыми формами — кавычки («совет дома»
    повторён дословно), «№», инфинитив, ответ без глагола. Рефлекс
    понимал только голое «примени патч N» — и мозг ходил по кругу.
    Все живые формы должны попадать в рефлекс, не в мозг."""
    a = agent.Agent(brain=FakeBrain(), memory=FakeMemory())
    got = {}
    monkeypatch.setattr(repair, "apply_patch",
                        lambda n: got.update(n=n) or "ПРИМЕНЁН %d" % n)
    for phrase in ("примени патч 0002",
                   "«примени патч 0002»",
                   "примени патч №0002",
                   "применить патч 0002",
                   "примени 0002",
                   "патч 0002",
                   "№0002",
                   "Патч №0002",
                   "Марфа, примени патч 0002"):
        r = a.handle(phrase)
        assert r.tool_used == "patch_apply", phrase
        assert got["n"] == 2 and a.brain.calls == 0, phrase
    # откаты тем же живым языком
    monkeypatch.setattr(repair, "rollback_patch", lambda n: "ОТКАЧЕН %d" % n)
    r = a.handle("откати патч №0002")
    assert r.tool_used == "patch_rollback" and "ОТКАЧЕН 2" in r.text
    r = a.handle("откатить 0002")
    assert r.tool_used == "patch_rollback" and "ОТКАЧЕН 2" in r.text


def test_agent_bare_patch_number_not_command(home, monkeypatch):
    r"""Голые формы не жадничают: «что меняет патч N» и «покажи патч N»
    — свои маршруты, «патчи» — список. Точное над жадным (круг 25)."""
    a = agent.Agent(brain=FakeBrain(), memory=FakeMemory())
    monkeypatch.setattr(repair, "patch_summary", lambda n: "СВОДКА %d" % n)
    monkeypatch.setattr(repair, "patch_diff", lambda n: "ДИФФ %d" % n)
    monkeypatch.setattr(repair, "list_patches", lambda: "№0001 — ждёт")
    r = a.handle("что меняет патч 0002")
    assert r.tool_used == "patch_summary" and "СВОДКА 2" in r.text
    r = a.handle("покажи патч 0002")
    assert r.tool_used == "patch_diff" and "ДИФФ 2" in r.text
    assert a.handle("патчи").tool_used == "patches"
    assert a.brain.calls == 0


def test_agent_apply_patch_tool_finds_number(home, monkeypatch):
    r"""День-18, мозг: apply_patch звался с номером в text/query —
    ручка читала только patch/n и ходила по кругу «внедрить какой
    патч?». Номер ищется в любом ключе и в тексте; без номера —
    научение СПРОСИТЬ, а не звать вслепую."""
    a = agent.Agent(brain=FakeBrain(), memory=FakeMemory())
    monkeypatch.setattr(repair, "self_apply", lambda n: "ВНЕДРЁН %d" % n)
    for args in ({"text": "патч 0002"}, {"query": "№0002"},
                 {"value": "0002"}, {"patch": 2}, {"n": "0002"},
                 {"patch_id": 2}):
        r = a._act({"tool": "apply_patch", "args": args})
        assert "ВНЕДРЁН 2" in r.text, args
    r = a._act({"tool": "apply_patch", "args": {"text": "какой патч?"}})
    assert "спроси Создателя" in r.text


# ---------- день-18: броня Ф155 встретила живую станцию ----------

def test_smoke_finds_tests_by_real_path(home, monkeypatch):
    r"""УРОК ЖИВОГО ЛОГА (день-18): станция ответила «pytest
    test_krug26_circle.py (код 4) no tests ran» — броня звала тесты
    ГОЛЫМ именем из корня дома, где их нет. Теперь путь tests\<имя>:
    живой pytest-прогон НАХОДИТ и ГОНЯЕТ тест (зелёный случай —
    патч применяется по-настоящему, не по компиляции)."""
    target = _make_patch_0001(home, monkeypatch)
    tdir = home / "tests"
    tdir.mkdir(parents=True)
    (tdir / "test_calc.py").write_text(
        "import sys\nfrom pathlib import Path\n"
        "sys.path.insert(0, str(Path(__file__).resolve().parents[1]))\n"
        "from scripts import calc\n\n"
        "def test_calc_patched():\n    assert calc.NEW == 2\n",
        encoding="utf-8")
    out = repair.apply_patch(1)
    assert "ПРИМЕНЁН" in out
    assert "код 4" not in out and "no tests ran" not in out
    assert "1 passed" in out                  # тест реально гонялся
    assert target.read_text(encoding="utf-8") == "NEW = 2\n"


def test_apply_red_rolls_back_new_file_by_deletion(home, monkeypatch):
    r"""День-18, корень №2: «старый файл ВЕРНУТЬ НЕ УДАЛОСЬ — проверь
    руками!» на НОВОМ файле — бэкапа нет вовсе, а честный откат нового
    файла = вернуть отсутствие (удалить). Красный тест → файл убран,
    совет — исполнимым путём с подпапкой (Ф184/Ф187: совет дома —
    тоже команда, страж R1 голые имена не пускает)."""
    monkeypatch.setattr(repair, "_ask_coder",
                        lambda prompt, max_tokens=None:
                        "```python\nX = 1\n```")
    repair.make_patch("scripts/fresh.py", "новый файл")
    tdir = home / "tests"
    tdir.mkdir(parents=True)
    (tdir / "test_fresh.py").write_text(
        "def test_red():\n    assert False, 'красный по заказу'\n",
        encoding="utf-8")
    out = repair.apply_patch(1)
    assert "НЕ ПРИМЕНЁН" in out
    assert "no tests ran" not in out          # тесты дошли до pytest
    assert "1 failed" in out
    assert "ВЕРНУТЬ НЕ УДАЛОСЬ" not in out
    assert "я его убрала" in out
    assert not (home / "scripts" / "fresh.py").exists(), \
        "новый файл убран — дом как до патча"
    assert "почини scripts/fresh.py" in out   # совет исполним: с подпапкой


def test_agent_fix_bare_name_honest_guard(home):
    r"""День-18, корень №3: совет дома «почини sozday_instrument.py»
    (ГОЛОЕ имя) был неисполним — страж R1 поднимал PermissionError
    ДО обработки, быстрый трек рвался изнутри, ход молча падал в
    мозг («Я позвала кодера, но не назвала ему файл»). Теперь: диагноз
    стража Создателю + исполнимая форма, мозг молчит."""
    a = agent.Agent(brain=FakeBrain(), memory=FakeMemory())
    r = a.handle("почини sozday_instrument.py: исправь подсказку")
    assert r.tool_used == "repair"
    assert a.brain.calls == 0
    assert "СТРАЖ" in r.text and "подпапкой" in r.text


def test_agent_fix_template_requirement_refused(home):
    r"""Ф187: Создатель повторил совет дома дословно — «почини …:
    <что исправить>» с заглушкой в угловых скобках. Шаблон — не
    требование: честный отказ с живым примером (быстрая ветка И
    мозговой code_patch — один закон)."""
    a = agent.Agent(brain=FakeBrain(), memory=FakeMemory())
    r = a.handle("почини core/customtools/sozday_instrument.py: "
                 "<что исправить>")
    assert r.tool_used == "repair"
    assert a.brain.calls == 0
    assert "шаблон" in r.text.lower()
    assert "sozday_instrument" in r.text      # путь назван — можно проще
    r2 = a._act({"tool": "code_patch",
                 "args": {"path": "scripts/x.py",
                          "requirement": "<что сделать>"}})
    assert "шаблон" in r2.text.lower()
    # мозг с голым именем — исполнимая подсказка, не голый отказ
    r3 = a._act({"tool": "code_patch",
                 "args": {"path": "hello.py",
                          "requirement": "поправь приветствие"}})
    assert "СТРАЖ" in r3.text and "подпапкой" in r3.text
