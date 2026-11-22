# -*- coding: utf-8 -*-
"""Тесты мозга (ТЗ 3.2, ADR-002): клиент 8082, строгий JSON, fallback."""
import json

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


# ---------- №9: темперамент из доктрины Создателя ----------

@pytest.fixture()
def doctrine_home(tmp_path, monkeypatch):
    """Доктрина в tmp: тесты не трогают чужие файлы."""
    monkeypatch.setattr(config, "DOCTRINE_FILE", tmp_path / "creator_doctrine.json")
    yield tmp_path


def _write_mood(path, mood):
    path.write_text(json.dumps({"doctrine": "тест", "mood": mood},
                               ensure_ascii=False), encoding="utf-8")


def test_mood_changes_chat_sampling(client, srv, doctrine_home):
    """Доктрина с настроением — мозг говорит с новой температурой и top_p."""
    _write_mood(config.DOCTRINE_FILE, {"temperature": 0.6, "top_p": 0.8})
    srv.reply_content = "живее!"
    client.chat([{"role": "user", "content": "привет"}])
    call = srv.calls[-1]
    assert call["temperature"] == 0.6
    assert call["top_p"] == 0.8


def test_mood_changes_ask_json_sampling(client, srv, doctrine_home):
    _write_mood(config.DOCTRINE_FILE, {"temperature": 0.5})
    client.ask_json("вопрос")
    assert srv.calls[-1]["temperature"] == 0.5


def test_mood_broken_falls_back_to_default(client, srv, doctrine_home):
    """Брак (temperature вне здравых границ) — характер по умолчанию 0.3."""
    _write_mood(config.DOCTRINE_FILE, {"temperature": 99})
    client.chat([{"role": "user", "content": "привет"}])
    call = srv.calls[-1]
    assert call["temperature"] == 0.3
    assert "top_p" not in call


def test_mood_missing_file_is_default(client, srv, doctrine_home):
    """Нет файла доктрины — дефолт, никаких выдумок о характере."""
    client.chat([{"role": "user", "content": "привет"}])
    assert srv.calls[-1]["temperature"] == 0.3


def test_explicit_temperature_beats_mood(client, srv, doctrine_home):
    """Явный аргумент (выжимки просят холодную голову) сильнее настроения."""
    _write_mood(config.DOCTRINE_FILE, {"temperature": 0.6})
    client.chat([{"role": "user", "content": "сожми"}], temperature=0.2)
    assert srv.calls[-1]["temperature"] == 0.2


# ---------- СКОРОСТЬ v1: бюджет краткости, стрим, think-блоки ----------

def test_ask_json_short_budget_first_attempt(client, srv):
    """Чат-ответ живёт на BRAIN_ANSWER_TOKENS: первый заход — краткий
    бюджет (урок «ответ через две минуты — это очень долго»)."""
    srv.reply_content = '{"answer": "кратко"}'
    client.ask_json("привет", max_tokens=config.BRAIN_ANSWER_TOKENS)
    assert srv.calls[-1]["max_tokens"] == config.BRAIN_ANSWER_TOKENS


def test_ask_json_retry_escalates_budget(client, srv):
    """Брак → повтор с ПОЛНЫМ бюджетом: обрезанный JSON лечится местом,
    а не укором — иначе короткий бюджет превращался бы в вечный брак."""
    srv.script = ["не json совсем", '{"answer": "со второго раза"}']
    client.ask_json("повтори", max_tokens=config.BRAIN_ANSWER_TOKENS)
    assert srv.calls[0]["max_tokens"] == config.BRAIN_ANSWER_TOKENS
    assert srv.calls[1]["max_tokens"] == config.GENERATION_BUDGET_TOKENS


def test_ask_json_strips_think_blocks(client, srv):
    """Qwen3 думает блоками <think>…</think> — грамматика их не
    пускает, но сборка сервера без грамматики обязана не сломать дом:
    стриппер снимает think, JSON остаётся чистым."""
    srv.reply_content = '<think>размышления</think>{"answer": "суть"}'
    out = client.ask_json("вопрос")
    assert out == {"answer": "суть"}


def test_ask_json_usage_captured(client, srv):
    """usage ответа честно лежит в last_usage — для штампа «N ток»."""
    content = '{"answer": "считай меня"}'
    srv.reply_content = content
    client.ask_json("вопрос")
    assert client.last_usage["completion_tokens"] == max(1, len(content) // 3)


def test_ask_json_streams_preview(client, srv):
    """on_text — стрим-превью: дельты летят в эфир по мере генерации.
    Фейк-сервер отвечает обычным JSON — честный фоллбэк зовёт on_text
    один раз, превью всё равно состоится."""
    srv.reply_content = '{"answer": "ответ рождается"}'
    seen = []
    out = client.ask_json("привет", on_text=seen.append)
    assert out == {"answer": "ответ рождается"}
    assert seen and seen[-1] == '{"answer": "ответ рождается"}'
    assert srv.calls[-1]["stream"] is True     # стрим просился по-настоящему


def test_ask_json_broken_on_text_never_breaks_answer(client, srv):
    """Закон эфира: превью — косметика. Сломавшийся колбэк не имеет
    права уронить ответ дома."""
    srv.reply_content = '{"answer": "жива"}'

    def boom(text):
        raise RuntimeError("чат закрылся")

    out = client.ask_json("привет", on_text=boom)
    assert out == {"answer": "жива"}


def test_answer_budget_stays_lean():
    """Бюджет краткости не расползается: 320 — это ~40 с на CPU,
    768 — уже две минуты (урок живого дома)."""
    assert config.BRAIN_ANSWER_TOKENS <= 320
    assert config.BRAIN_ANSWER_TOKENS < config.GENERATION_BUDGET_TOKENS
