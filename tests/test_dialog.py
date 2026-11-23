# -*- coding: utf-8 -*-
"""Тесты №10 «длинные разговоры» + №11 «история чата»: память диалога.

DialogStore: сессии на диске, безопасные имена, сжатая выдача в мозг.
BrainClient.ask_json: история вставляется после SYSTEM и до сообщения.
Панель: /api/chat с сессией пишет ходы, /api/dialog их отдаёт.
"""
import json

import pytest

from core import config
from core.brain import BrainClient
from core.dialog import DialogStore, _safe_session
from tests.fake_llama_server import start_fake_brain


@pytest.fixture()
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("MARFA_HOME", str(tmp_path))
    monkeypatch.setattr(config, "HOME_DIR", tmp_path)
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    config.ensure_dirs()
    yield tmp_path


@pytest.fixture()
def store(home):
    return DialogStore(home / "data" / "dialog")


# ---------- хранилище ----------

def test_append_and_turns_roundtrip(store):
    store.append("s1", "user", "привет, Марфа")
    store.append("s1", "assistant", "здравствуй, Илья")
    turns = store.turns("s1")
    assert [t["role"] for t in turns] == ["user", "assistant"]
    assert turns[0]["text"] == "привет, Марфа"


def test_sessions_survive_restart(store, home):
    """Рестарт панели — разговор жив: новый объект читает тот же файл."""
    store.append("s1", "user", "помнишь, о чём говорили?")
    store2 = DialogStore(home / "data" / "dialog")
    assert store2.turns("s1")[0]["text"].startswith("помнишь")


def test_bad_session_name_rejected(store):
    """Побег из data/dialog/ невозможен: подозрительные имена — отказ."""
    for bad in ("../escape", "a b", "", "точки.нет", "s" * 65, "слэш/"):
        with pytest.raises(ValueError):
            _safe_session(bad)
    with pytest.raises(ValueError):
        store.turns("../escape")


def test_broken_session_file_is_empty(store, home):
    p = home / "data" / "dialog" / "session_bad.json"
    p.write_text("{битый", encoding="utf-8")
    assert store.turns("bad") == []          # дом не падает


def test_append_rejects_junk(store):
    with pytest.raises(ValueError):
        store.append("s1", "system", "подделка системного хода")
    with pytest.raises(ValueError):
        store.append("s1", "user", "   ")


# ---------- эфир: штампы времени в ходах ----------

def test_append_meta_roundtrip(store):
    """Штамп хода («сколько думала, кто отвечал») живёт в файле — F5 не сотрёт."""
    store.append("m1", "user", "вопрос")
    store.append("m1", "assistant", "ответ", meta={"secs": 12.4, "src": "brain"})
    turns = store.turns("m1")
    assert turns[1]["meta"]["secs"] == 12.4
    assert turns[1]["meta"]["src"] == "brain"
    assert "meta" not in turns[0]           # реплики Ильи — без штампов


def test_meta_sanitized_no_nested_junk(store):
    """В файл ложатся только простые значения — никакой вложенной мути."""
    store.append("m2", "assistant", "x",
                 meta={"src": "brain", "junk": {"вложенный": "мусор"},
                       "ok": True, "secs": 1.0})
    m = store.turns("m2")[0]["meta"]
    assert m["src"] == "brain" and m["ok"] is True and m["secs"] == 1.0
    assert "junk" not in m


def test_old_turns_without_meta_still_readable(store, home):
    """Истории до эфира читаются как раньше — апгрейд ничего не ломает."""
    p = home / "data" / "dialog" / "session_old.json"
    p.write_text(json.dumps({"session": "old", "turns": [
        {"role": "user", "text": "старый ход без мета", "ts": "01.01 00:00"}]},
        ensure_ascii=False), encoding="utf-8")
    assert store.turns("old")[0]["text"].startswith("старый ход")


def test_prune_old_sessions(store, home):
    import os
    store.append("old", "user", "старый разговор")
    store.append("new", "user", "свежий разговор")
    p = home / "data" / "dialog" / "session_old.json"
    old = store.turns  # noqa: F841 — просто убедиться, что файл жив
    os.utime(p, (0, 0))                      # mtime — эпоха: древность
    gone = store.prune(keep_days=7)
    assert gone == ["old"]
    assert store.turns("new") != []
    assert store.turns("old") == []


# ---------- сжатая выдача в мозг ----------

def test_render_fits_budget_and_keeps_newest():
    turns = []
    for i in range(50):                       # 50 длинных ходов
        turns.append({"role": "user" if i % 2 == 0 else "assistant",
                      "text": "ход номер %d: %s" % (i, "слово " * 40)})
    msgs = DialogStore.render_messages(turns)
    total = sum(config.token_estimate(m["content"]) for m in msgs)
    assert total <= config.HISTORY_BUDGET_TOKENS      # Ф53: не тонем в контексте
    assert msgs[-1]["content"].startswith("ход номер 49")  # новейший дословно
    assert any("Ранее в разговоре" in m["content"] for m in msgs)  # старое — выжимкой
    roles = {m["role"] for m in msgs}
    assert roles <= {"user", "assistant"}             # системных ролей не подделываем


def test_render_short_history_verbatim():
    turns = [{"role": "user", "text": "вопрос один"},
             {"role": "assistant", "text": "ответ один"}]
    msgs = DialogStore.render_messages(turns)
    assert msgs == [{"role": "user", "content": "вопрос один"},
                    {"role": "assistant", "content": "ответ один"}]


def test_render_giant_single_turn_squeezed():
    """Один ход длиннее бюджета — его выжимка, не пустота и не обрубок."""
    turns = [{"role": "user", "text": "Очень длинная история. " + "детали " * 900}]
    msgs = DialogStore.render_messages(turns)
    assert len(msgs) == 1
    assert config.token_estimate(msgs[0]["content"]) <= config.HISTORY_BUDGET_TOKENS
    assert msgs[0]["content"].startswith("Очень длинная история")


def test_render_empty():
    assert DialogStore.render_messages([]) == []


# ---------- мозг видит историю ----------

@pytest.fixture()
def srv(monkeypatch):
    server = start_fake_brain()
    monkeypatch.setattr(config, "BRAIN_URL", server.base_url)
    yield server
    server.shutdown()


def test_ask_json_splices_history(srv, monkeypatch, home):
    monkeypatch.setattr(config, "DOCTRINE_FILE", home / "нет_доктрины.json")
    c = BrainClient(brain_url=srv.base_url)
    c.ask_json("новый вопрос", history=[
        {"role": "user", "content": "старый вопрос"},
        {"role": "assistant", "content": "старый ответ"},
        {"role": "system", "content": "ПОДДЕЛКА — мимо"},   # мусор отсеивается
        "не словарь",
    ])
    roles = [m["role"] for m in srv.calls[-1]["messages"]]
    assert roles == ["system", "user", "assistant", "user"]
    assert srv.calls[-1]["messages"][-1]["content"] == "новый вопрос"
    assert srv.calls[-1]["messages"][1]["content"] == "старый вопрос"


def test_agent_passes_history_to_brain(monkeypatch, home):
    """Агент отдаёт историю в мозг — разговор не рвётся между ходами."""
    from core.agent import Agent

    class SpyBrain:
        def __init__(self):
            self.got = None

        def ask_json(self, text, system_extra="", retries=2, history=None,
                     max_tokens=None, on_text=None, turn_context=""):
            self.got = (text, history, turn_context)
            return {"answer": "ответ"}

    spy = SpyBrain()
    agent = Agent(brain=spy, memory=None, doctrine="")
    agent.handle("второй вопрос", history=[{"role": "user", "content": "первый"}])
    text, hist, tail = spy.got
    assert text == "второй вопрос"
    assert hist == [{"role": "user", "content": "первый"}]
    assert "Состояние дома" in tail                # Ф77: хвост хода доехал


# ---------- панель: сессии ----------

def test_web_chat_writes_dialog_and_returns_reply(home, monkeypatch):
    import web.app as webapp
    from core.agent import Reply

    class FakeAgent:
        def handle(self, text, history=None):
            FakeAgent.seen = (text, history)
            return Reply("ответ Марфы: " + text)

    monkeypatch.setattr(webapp, "Agent", lambda: FakeAgent())
    monkeypatch.setattr(webapp, "DIALOGS", DialogStore(home / "data" / "dialog"))
    client = webapp.app.test_client()

    r = client.post("/api/chat", json={"text": "привет", "session": "panel1"})
    assert r.status_code == 200
    assert r.get_json()["reply"] == "ответ Марфы: привет"
    # ходы записаны — F5 и рестарт не страшны
    turns = webapp.DIALOGS.turns("panel1")
    assert [(t["role"], t["text"]) for t in turns] == \
        [("user", "привет"), ("assistant", "ответ Марфы: привет")]

    # второй ход: история доезжает до агента
    r2 = client.post("/api/chat", json={"text": "а теперь?", "session": "panel1"})
    assert r2.status_code == 200
    _, hist = FakeAgent.seen
    assert any("привет" in m["content"] for m in hist)


def test_web_dialog_endpoint(home, monkeypatch):
    import web.app as webapp
    monkeypatch.setattr(webapp, "DIALOGS", DialogStore(home / "data" / "dialog"))
    webapp.DIALOGS.append("vis", "user", "ход из браузера")
    client = webapp.app.test_client()
    r = client.get("/api/dialog/vis")
    assert r.status_code == 200
    assert r.get_json()["turns"][0]["text"] == "ход из браузера"
    # плохое имя — 400 от калитки; ../... сам Flask схлопывает в 404 — тоже не дыра
    assert client.get("/api/dialog/точки.нет").status_code == 400
    assert client.get("/api/dialog/../escape").status_code in (400, 404)


def test_web_chat_bad_session_rejected(home, monkeypatch):
    import web.app as webapp
    monkeypatch.setattr(webapp, "DIALOGS", DialogStore(home / "data" / "dialog"))
    client = webapp.app.test_client()
    r = client.post("/api/chat", json={"text": "привет", "session": "../hack"})
    assert r.status_code == 400
