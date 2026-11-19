# -*- coding: utf-8 -*-
"""Тесты мозга (ТЗ 3.2, ADR-002): клиент 8082, строгий JSON, fallback."""
import pytest

from core import config, brain
from tests.fake_llama_server import start_fake_brain


class FakeFallback:
    """Подменный GigaChat для тестов."""
    def __init__(self, available: bool = True, answer: str = "фоллбэк-ответ"):
        self._available = available
        self.answer = answer
        self.asked: list[str] = []

    def available(self) -> bool:
        return self._available

    def ask(self, prompt: str) -> str:
        self.asked.append(prompt)
        return self.answer


@pytest.fixture()
def srv(monkeypatch):
    server = start_fake_brain()
    monkeypatch.setattr(config, "BRAIN_URL", server.base_url)
    yield server
    server.shutdown()


@pytest.fixture()
def client(srv):
    return brain.BrainClient(brain_url=srv.base_url)


# ---------- доступность ----------
def test_health_up(client):
    assert client.health() is True


def test_health_down():
    dead = brain.BrainClient(brain_url="http://127.0.0.1:1")
    assert dead.health() is False


# ---------- обычный чат ----------
def test_chat_returns_answer(client, srv):
    srv.reply_content = "Мозг на CPU, 8-16 ток/с"
    assert client.chat([{"role": "user", "content": "привет"}]) == "Мозг на CPU, 8-16 ток/с"


def test_chat_max_tokens_capped(client, srv):
    """0.3: генерация не выше бюджета 768, что бы ни попросили."""
    srv.reply_content = "ок"
    client.chat([{"role": "user", "content": "привет"}], gen_tokens=99999)
    assert srv.calls[-1]["max_tokens"] == config.GENERATION_BUDGET_TOKENS


def test_chat_down_raises(client, monkeypatch):
    monkeypatch.setattr(client, "url", "http://127.0.0.1:1")
    with pytest.raises(brain.BrainError):
        client.chat([{"role": "user", "content": "ты тут?"}])


# ---------- ADR-002: строгий JSON ----------
def test_ask_json_answer_schema(client, srv):
    srv.reply_content = '{"answer": "баланс скобок: ОК"}'
    out = client.ask_json("проверь скобки в (a[1])")
    assert out == {"answer": "баланс скобок: ОК"}


def test_ask_json_action_schema(client, srv):
    srv.reply_content = '{"action": {"tool": "write_file", "args": {"path": "data/x.txt", "content": "привет"}}}'
    out = client.ask_json("запиши привет в файл")
    assert out["action"]["tool"] == "write_file"
    assert out["action"]["args"]["path"] == "data/x.txt"


def test_ask_json_retries_on_garbage(client, srv):
    """Брак → повтор с укором → успех на второй попытке."""
    srv.script = [
        "Вот твой ответ: {\"answer\": ...} (без markdown не получится)",
        '{"answer": "второй раз удачно"}',
    ]
    out = client.ask_json("повтори")
    assert out == {"answer": "второй раз удачно"}
    assert len(srv.calls) == 2  # была вторая попытка
    assert "не был валидным JSON" in srv.calls[-1]["messages"][-1]["content"]


def test_ask_json_no_regex_salvage(client, srv):
    """ADR-002: JSON, завёрнутый в текст, НЕ спасается — после ретраев исключение."""
    srv.reply_content = 'Вот ответ: {"answer": "спасение"} — выше текст, ниже тоже.'
    with pytest.raises(brain.BrainError):
        client.ask_json("спаси", retries=1)


def test_ask_json_fallback_used(client, srv):
    srv.reply_content = "не json"
    fb = FakeFallback(answer="ответ из GigaChat")
    client.fallback = fb
    out = client.ask_json("выручай")
    assert out == {"answer": "ответ из GigaChat", "source": "fallback"}
    assert fb.asked == ["выручай"]


def test_ask_json_no_fallback_raises(client, srv):
    srv.reply_content = "опять не json"
    client.fallback = FakeFallback(available=False)
    with pytest.raises(brain.BrainError):
        client.ask_json("куку", retries=0)


# ---------- usage ----------
def test_usage_tokens(client, srv):
    srv.reply_content = '{"answer": "1234567890123"}'
    data_payload = srv.calls  # пусто до запроса
    client.ask_json("сосчитай")
    # usage берём из сырого ответа сервера: проверим через chat с прямым _post
    raw = client._post("/v1/chat/completions", {"messages": [], "max_tokens": 5})
    assert client.usage_tokens(raw) == max(1, len('{"answer": "1234567890123"}') // 3)
