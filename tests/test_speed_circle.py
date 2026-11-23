# -*- coding: utf-8 -*-
"""Тесты круга 7 «Скорость» (Ф41–Ф45, день-9, 24.11): память ответов,
KV-префикс сервера, вес промпта, здоровье мозга, энергия дома."""
import json
import subprocess
import time

import pytest

from core import answercache, brainhealth, config, energy, promptweight


@pytest.fixture()
def home(tmp_path, monkeypatch):
    """Песочница круга 7: все файлы органов — только в tmp_path.

    Память ответов и энергия — органы КАЖДОГО хода: пути резолвятся
    лениво от DATA_DIR (закон reminders), патчим только DATA_DIR."""
    data = tmp_path / "data"
    logs = tmp_path / "logs"
    monkeypatch.setattr(config, "HOME_DIR", tmp_path)
    monkeypatch.setattr(config, "DATA_DIR", data)
    monkeypatch.setattr(config, "LOGS_DIR", logs)
    monkeypatch.setattr(config, "BRAIN_LOG_FILE", logs / "brain_log.jsonl")
    yield tmp_path


# ---------- Ф41 память ответов ----------

def test_cache_store_lookup_hit_and_honesty(home):
    assert answercache.lookup("как дела у дома?") is None
    answercache.store("Как дела у дома??", "Всё хорошо, спасибо.")
    out = answercache.lookup("как дела у дома")
    assert out is not None
    assert "Помню — уже отвечала" in out      # честность — первой строкой
    assert "Всё хорошо, спасибо." in out
    assert answercache.stats()["entries"] == 1
    assert answercache.stats()["hits"] == 1


def test_cache_ttl_expiry_forgets(home, monkeypatch):
    answercache.store("вопрос", "ответ")
    old = time.time() - config.ANSWER_CACHE_TTL_SEC - 10
    items = json.loads(answercache._file().read_text(encoding="utf-8"))
    items[list(items)[0]]["ts"] = old
    answercache._file().write_text(
        json.dumps(items, ensure_ascii=False), encoding="utf-8")
    assert answercache.lookup("вопрос") is None
    # просроченное честно удалилось, а не дожидаясь чистки
    assert answercache.stats()["entries"] == 0


def test_cache_bypass_one_shot(home):
    answercache.store("вопрос", "ответ")
    assert "спрошу у мозга" in answercache.bypass()
    assert answercache.lookup("вопрос") is None   # обход сработал
    assert answercache.lookup("вопрос") is not None  # и только один раз


def test_cache_garbage_not_stored(home):
    assert answercache.store("", "ответ") is False
    assert answercache.store("вопрос", "   ") is False
    assert answercache.store("в" * 500, "ответ") is False  # вопрос-роман


def test_cache_cap_prunes_oldest(home, monkeypatch):
    monkeypatch.setattr(config, "ANSWER_CACHE_CAP", 3)
    for i in range(4):
        answercache.store("вопрос %d" % i, "ответ %d" % i)
        time.sleep(0.01)
    assert answercache.lookup("вопрос 0") is None     # старейший подрезан
    assert answercache.lookup("вопрос 3") is not None


def test_cache_forget_all(home):
    answercache.store("а", "б")
    assert "забыла" in answercache.forget_all()
    assert "нечего забывать" in answercache.forget_all()
    assert answercache.lookup("а") is None


def test_cache_parse_boundaries():
    assert answercache.parse("забудь ответы") == ("forget",)
    assert answercache.parse("забудь что отвечала") == ("forget",)
    assert answercache.parse("забудь всё") is None


def test_cache_broken_file_honest_empty(home):
    answercache._file().parent.mkdir(parents=True, exist_ok=True)
    answercache._file().write_text("не json", encoding="utf-8")
    assert answercache.lookup("вопрос") is None


# ---------- Ф41 проводка агента: мозг не платит дважды ----------

class _FakeBrain:
    def __init__(self):
        self.calls = 0
        self.last_usage = None

    def ask_json(self, text, **kw):
        self.calls += 1
        return {"answer": "Живу и радуюсь нашему дому."}


def _agent_with(home, monkeypatch, brain):
    from core.agent import Agent
    agent = Agent(brain=brain, memory=None, doctrine="Тестовая доктрина")
    return agent


def test_agent_answers_from_memory_on_second_ask(home, monkeypatch):
    brain = _FakeBrain()
    agent = _agent_with(home, monkeypatch, brain)
    r1 = agent.handle("как ты живёшь в доме?")
    assert brain.calls == 1
    r2 = agent.handle("как ты живёшь в доме?")
    assert brain.calls == 1                          # мозг не платил дважды
    assert r2.source == "answercache"
    assert "Помню — уже отвечала" in r2.text
    assert "Живу и радуюсь" in r2.text


def test_agent_answer_differently_bypasses_once(home, monkeypatch):
    brain = _FakeBrain()
    agent = _agent_with(home, monkeypatch, brain)
    agent.handle("как ты живёшь в доме?")
    fast = agent._fast("ответь иначе")
    assert fast is not None and "заново" in fast.text
    agent.handle("ответь иначе")
    agent.handle("как ты живёшь в доме?")            # обход — к мозгу
    assert brain.calls == 2
    agent.handle("как ты живёшь в доме?")            # новый ответ — в память
    assert brain.calls == 2


def test_agent_forget_answers_command(home, monkeypatch):
    brain = _FakeBrain()
    agent = _agent_with(home, monkeypatch, brain)
    agent.handle("как ты живёшь в доме?")
    r = agent.handle("забудь ответы")
    assert "забыла" in r.text
    agent.handle("как ты живёшь в доме?")
    assert brain.calls == 2                          # памяти нет — мозг думает


def test_agent_action_replies_not_cached(home, monkeypatch):
    class _ActionBrain(_FakeBrain):
        def ask_json(self, text, **kw):
            self.calls += 1
            return {"answer": "открываю", "action": {"tool": "browser_search",
                                                 "args": {"query": "x"}}}

    brain = _ActionBrain()
    agent = _agent_with(home, monkeypatch, brain)
    agent.handle("найди погоду")
    agent.handle("найди погоду")
    assert brain.calls == 2              # действие не помнится: повтор слов
    # без дела — врать о мире
    assert answercache.stats()["entries"] == 0


# ---------- Ф42 KV-префикс сервера ----------

def test_kv_prefix_appended_when_supported(tmp_path, monkeypatch):
    import start_marfa
    exe = tmp_path / "llama-server.exe"
    exe.write_bytes(b"fake")
    caps = tmp_path / "data" / "server_caps.json"

    def fake_run(cmd, **kw):
        assert cmd[0] == str(exe) and cmd[1] == "--help"
        return subprocess.CompletedProcess(
            cmd, 0, stdout="--cache-reuse N   min chunk size", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(start_marfa, "HOME", tmp_path)
    cfg = {"brain_cmd": "%s -m model.gguf --port 8082" % exe}
    assert start_marfa._ensure_kv_prefix(cfg) is True
    assert cfg["brain_cmd"].endswith("--cache-reuse 256")
    assert '"' not in cfg["brain_cmd"]          # закон дня-8: без кавычек
    assert caps.exists()                        # проба закэширована


def test_kv_prefix_refused_when_unknown(tmp_path, monkeypatch):
    import start_marfa
    exe = tmp_path / "llama-server.exe"
    exe.write_bytes(b"fake")

    def fake_run(cmd, **kw):
        return subprocess.CompletedProcess(cmd, 0, stdout="-c ctx", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(start_marfa, "HOME", tmp_path)
    cfg = {"brain_cmd": "%s -m model.gguf" % exe}
    assert start_marfa._ensure_kv_prefix(cfg) is False
    assert "--cache-reuse" not in cfg["brain_cmd"]


def test_kv_prefix_uses_cached_probe_no_rerun(tmp_path, monkeypatch):
    import start_marfa
    exe = tmp_path / "llama-server.exe"
    exe.write_bytes(b"fake")
    caps = tmp_path / "data" / "server_caps.json"
    caps.parent.mkdir(parents=True)
    caps.write_text(json.dumps({"exe": str(exe),
                                "mtime": exe.stat().st_mtime,
                                "cache_reuse": True}), encoding="utf-8")
    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(start_marfa, "HOME", tmp_path)
    cfg = {"brain_cmd": "%s -m model.gguf" % exe}
    assert start_marfa._ensure_kv_prefix(cfg) is True
    assert not calls                          # проба из кэша, бинарник не звали


def test_kv_prefix_idempotent_and_no_binary(tmp_path, monkeypatch):
    import start_marfa
    monkeypatch.setattr(start_marfa, "HOME", tmp_path)
    cfg = {"brain_cmd": "llama-server.exe -m m.gguf --cache-reuse 256"}
    assert start_marfa._ensure_kv_prefix(cfg) is False   # уже стоит
    cfg2 = {"brain_cmd": "нет_такого.exe -m m.gguf"}
    assert start_marfa._ensure_kv_prefix(cfg2) is False  # не гадаем без файла


def test_kv_prefix_probe_failure_is_silent(tmp_path, monkeypatch):
    import start_marfa
    exe = tmp_path / "llama-server.exe"
    exe.write_bytes(b"fake")

    def boom(cmd, **kw):
        raise OSError("нет исполнения")

    monkeypatch.setattr(subprocess, "run", boom)
    monkeypatch.setattr(start_marfa, "HOME", tmp_path)
    cfg = {"brain_cmd": "%s -m model.gguf" % exe}
    assert start_marfa._ensure_kv_prefix(cfg) is False
    assert "--cache-reuse" not in cfg["brain_cmd"]


# ---------- Ф43 вес промпта ----------

def _brain_log_line(ptok=0, ctok=0, secs=1.0):
    return json.dumps({"ts": "2026-11-24 12:00:00", "kind": "ask",
                       "ptok": ptok, "ctok": ctok, "secs": secs,
                       "answer": "ok"}, ensure_ascii=False)


def test_promptweight_truth_from_brain_log(home):
    config.BRAIN_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    config.BRAIN_LOG_FILE.write_text(
        _brain_log_line(ptok=2100, ctok=84) + "\n", encoding="utf-8")
    out = promptweight.render()
    assert "2100" in out and "истина от сервера" in out
    assert "из бюджета %d" % config.PROMPT_BUDGET_TOKENS in out
    assert "оценка" in out                      # слои честно подписаны


def test_promptweight_empty_log_honest(home):
    out = promptweight.render()
    assert "журнал мозга ещё пуст" in out
    assert "ядро" in out                        # слои всё равно показаны


def test_promptweight_layers_present(home):
    out = promptweight.render()
    for layer in ("ядро", "доктрина", "состояние дома", "история"):
        assert layer in out


# ---------- Ф44 здоровье мозга ----------

def _battery_log(path, tag, answers, speeds):
    results = []
    for i in range(answers):
        results.append({"id": "F%02d" % (i + 1), "answer": "ответ",
                        "empty": False, "think_tag_remnant": False,
                        "tok_per_s": speeds})
    path.write_text(json.dumps({
        "meta": {"tag": tag, "started": "20261124-120000"},
        "results": results}, ensure_ascii=False), encoding="utf-8")


def test_brainhealth_no_battery_honest(home):
    out = brainhealth.render()
    assert "не измерено" in out and "87_brain_battery" in out


def test_brainhealth_verdict_from_latest_run(home):
    logs = config.LOGS_DIR
    logs.mkdir(parents=True, exist_ok=True)
    # имена как у настоящей батареи: <tag>_<YYYYMMDD-HHMMSS>.json —
    # свежесть решает ШТАМП: алфавит ставил бы «new» раньше «old»
    # и называл бы старое свежим; проверяем именно это
    _battery_log(logs / "brain_battery_old_20261121-100000.json",
                 "old", 15, 12.0)
    _battery_log(logs / "brain_battery_new_20261124-120000.json",
                 "new", 15, 12.5)
    out = brainhealth.render()
    assert "new" in out and "old" not in out       # свежайший, не старый
    assert "пустых ответов: 0" in out
    assert "обрывков think-тегов: 0" in out
    assert "12.50 ток/с" in out
    assert "чисто по порогам" in out
    assert "ВЕРДИКТ_БАТАРЕИ" in out       # факты — работа Создателя, не дома


def test_brainhealth_degradation_warning(home):
    logs = config.LOGS_DIR
    logs.mkdir(parents=True, exist_ok=True)
    _battery_log(logs / "brain_battery_a_20261121-100000.json", "a", 15, 13.0)
    _battery_log(logs / "brain_battery_b_20261124-120000.json", "b", 15, 8.0)
    out = brainhealth.render()
    assert "просела" in out and "38%" in out       # (13-8)/13 ≈ 38%


def test_brainhealth_broken_json_skipped(home):
    logs = config.LOGS_DIR
    logs.mkdir(parents=True, exist_ok=True)
    (logs / "brain_battery_broken_20261120-100000.json").write_text(
        "не json", encoding="utf-8")
    _battery_log(logs / "brain_battery_ok_20261124-120000.json", "ok", 15, 12.0)
    assert "ok" in brainhealth.render()


# ---------- Ф45 энергия дома ----------

def test_energy_empty_day_honest(home):
    out = energy.render()
    assert "ходов ещё не было" in out


def test_energy_counts_from_both_sources(home):
    today = time.strftime("%Y-%m-%d")
    config.BRAIN_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    config.BRAIN_LOG_FILE.write_text("\n".join([
        json.dumps({"ts": today + " 10:00:00", "ctok": 84, "secs": 40.2,
                    "answer": "a"}, ensure_ascii=False),
        json.dumps({"ts": today + " 11:00:00", "ctok": 100, "secs": 59.8,
                    "answer": "b"}, ensure_ascii=False),
        json.dumps({"ts": "2020-01-01 10:00:00", "ctok": 5, "secs": 1.0,
                    "answer": "чужой день"}, ensure_ascii=False),
    ]) + "\n", encoding="utf-8")
    energy.note("python", 0.05)
    energy.note("python", 0.04)
    energy.note("answercache", 0.02)
    out = energy.render()
    assert "рефлексов (мозг молчал): 2" in out
    assert "мозг думал 2 раз" in out
    assert "1 мин 40 с" in out                     # 40,2 + 59,8
    assert "184 ток" in out
    assert "память ответов сработала 1 раз" in out
    assert "сэкономила" in out


def test_energy_note_never_raises(home):
    energy.note("python", "не число")               # мусор в секундах
    energy.note(None, 0.1)                          # мусор в источнике


def test_agent_writes_energy_on_handle(home, monkeypatch):
    brain = _FakeBrain()
    agent = _agent_with(home, monkeypatch, brain)
    agent.handle("как ты живёшь в доме?")           # мозг
    agent.handle("время")                           # рефлекс
    lines = energy._file().read_text(encoding="utf-8").splitlines()
    kinds = [json.loads(l)["source"] for l in lines]
    assert kinds.count("brain") == 1
    assert kinds.count("python") == 1
