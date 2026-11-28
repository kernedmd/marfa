# -*- coding: utf-8 -*-
"""Тесты круга 11 «ЧТЕНИЕ И БУФЕР» (Ф61–Ф65, день-10): глаза читают
все надписи списком, экран уезжает в буфер, буфер читается и
запоминается, голос читает живые органы, буфер проверяется живьём.

Законы, которые куются здесь:
- чтение — проза без JSON и без единого примера значений (урок v3);
- буфер не свалка и не бездонный колодец: лимиты записи и чтения
  свои, обрезка — по границе строк и предложений, не по слову;
- проверка не теряет чужое: проба буфера сохраняет и возвращает
  прежнее содержимое (закон «не терять данные», фаза 1 аудита);
- «прочитай вслух» стоит раньше «прочитай экран» и «прочитай буфер»:
  жадность префиксов разводится порядком (урок раунда 3).
"""
import json
import time
from pathlib import Path

import pytest

from core import config, eyes, hands, voice


@pytest.fixture()
def home(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "HOME_DIR", tmp_path)
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    config.ensure_dirs()
    monkeypatch.setattr(voice, "_VOICES_CACHE",
                        {"ts": 0.0, "voices": [], "error": ""})
    yield tmp_path / "data"


class _FakeClip:
    """Буфер-заглушка: копия/вставка через карман, как живой pyperclip."""

    def __init__(self, initial=""):
        self._v = initial
        self.copies = []

    def copy(self, t):
        self.copies.append(t)
        self._v = t

    def paste(self):
        return self._v


def _see_texts(monkeypatch, content):
    """Глаза «читают»: экран и сервер подменены, ответ сенсора — content."""
    monkeypatch.setattr(eyes, "_VISION_ERROR", None)
    monkeypatch.setattr(eyes, "_screenshot_b64",
                        lambda width=eyes.WORK_WIDTH:
                        ("b64", (1920, 1080), (1280, 720)))
    monkeypatch.setattr(eyes, "health", lambda: True)
    monkeypatch.setattr(eyes, "_post_chat",
                        lambda body, timeout=None: {"choices": [{"message":
                                                   {"content": content}}]})


# ---------- Ф61 «прочитай экран» ----------

def test_read_texts_parses_lines(home, monkeypatch):
    _see_texts(monkeypatch, "Файл\nПравка\nВид\n• Пуск\nФайл")
    lines, note = eyes.read_texts_list()
    assert note == "" and lines == ["Файл", "Правка", "Вид", "Пуск"]
    text = eyes.read_texts_text()
    assert "Читаю на ЭКРАНЕ (4 надписей):" in text
    assert "1. Файл" in text and "4. Пуск" in text
    assert "экран в буфер" in text            # подсказка о копировании


def test_read_texts_dead_eyes_honest(home, monkeypatch):
    monkeypatch.setattr(eyes, "_VISION_ERROR", None)
    monkeypatch.setattr(eyes, "health", lambda: False)
    lines, note = eyes.read_texts_list()
    assert lines == [] and "не отвечают" in note
    monkeypatch.setattr(eyes, "health", lambda: True)
    monkeypatch.setattr(eyes, "_VISION_ERROR", "нет модуля зрения")
    lines, note = eyes.read_texts_list()
    assert lines == [] and "не готовы" in note


def test_read_texts_empty_answer_honest(home, monkeypatch):
    _see_texts(monkeypatch, "   ")
    lines, note = eyes.read_texts_list()
    assert lines == [] and "ни одной надписи" in note


def test_read_prompt_has_no_value_examples():
    """Закон v3: ни одного примера ЗНАЧЕНИЙ в промпте сенсора — цифры,
    скобки и кавычки JSON маленькая VL-модель копирует как реальность.
    Двоеточие прозы («списком: каждая») — не пример, а пунктуация."""
    for ch in "0123456789[{\"":
        assert ch not in eyes.READ_PROMPT, (
            "символ %r — пример значений, приглашение списывать" % ch)


# ---------- Ф62 «экран в буфер» ----------

def test_clipboard_write_lines_fits_whole_lines(home, monkeypatch):
    clip = _FakeClip()
    monkeypatch.setattr(hands, "_pyperclip", lambda: clip)
    lines = ["Пуск"] * 40                      # 40×5 = 200 символов
    report = hands.clipboard_write_lines(lines)
    assert "все 40 надписей" in report
    assert clip.copies[-1].count("Пуск") == 40


def test_clipboard_write_lines_caps_by_limit(home, monkeypatch):
    clip = _FakeClip()
    monkeypatch.setattr(hands, "_pyperclip", lambda: clip)
    lines = ["надпись номер %02d" % i for i in range(1, 31)]
    report = hands.clipboard_write_lines(lines)
    assert "первые" in report and "из 30" in report
    sent = clip.copies[-1].splitlines()
    assert len(sent) < 30                       # влезли не все — целиком


def test_clipboard_write_lines_first_too_long(home, monkeypatch):
    clip = _FakeClip()
    monkeypatch.setattr(hands, "_pyperclip", lambda: clip)
    report = hands.clipboard_write_lines(["а" * 600])
    assert "длиннее лимита" in report and clip.copies == []


def test_clipboard_write_lines_empty_refuses(home):
    with pytest.raises(ValueError):
        hands.clipboard_write_lines([])


# ---------- Ф63 «что в буфере» / «запомни буфер» ----------

def test_clipboard_read_shows_and_caps(home, monkeypatch):
    clip = _FakeClip("привет из буфера")
    monkeypatch.setattr(hands, "_pyperclip", lambda: clip)
    assert hands.clipboard_read() == "привет из буфера"
    long = "строка " * 600                      # ~4200 символов
    clip.copy(long)
    out = hands.clipboard_read()
    assert "показала первые 2000" in out and len(out) < 2200
    # сырой буфер — текст без чатовой приписки Ф63, НО обрезка не молчит:
    # круг 34 (В7 аудита): «запомнила из буфера» без слова «обрезано»
    # читалось как «запомнила целиком» — честная пометка уезжает в
    # память вместе с текстом, а не заменяет его
    raw = hands.clipboard_read_raw()
    assert raw.startswith(long[:config.CLIPBOARD_READ_LIMIT])
    assert "обрезано" in raw and "4200" in raw


def test_clipboard_read_empty_and_no_module(home, monkeypatch):
    monkeypatch.setattr(hands, "_pyperclip", lambda: _FakeClip(""))
    assert hands.clipboard_read() == "буфер обмена пуст"

    def _no_module():
        raise ImportError("нет pyperclip")

    monkeypatch.setattr(hands, "_pyperclip", _no_module)
    with pytest.raises(RuntimeError) as e:
        hands.clipboard_read()
    assert "pyperclip" in str(e.value)


# ---------- Ф64 «прочитай вслух <что>» ----------

def _voice_ready(monkeypatch):
    monkeypatch.setattr(voice, "available", lambda: True)
    monkeypatch.setattr(voice, "_VOICES_CACHE",
                        {"ts": time.monotonic(),
                         "voices": [("Microsoft Irina", "ru-RU")],
                         "error": ""})
    spoken = []
    monkeypatch.setattr(voice, "speak_async",
                        lambda t, limit=None: spoken.append(t))
    return spoken


def test_read_aloud_screen(home, monkeypatch):
    _see_texts(monkeypatch, "Пуск\nПроводник")
    spoken = _voice_ready(monkeypatch)
    report = voice.read_aloud("экран")
    assert "читаю вслух надписи экрана (2)" in report
    assert spoken == ["Пуск\nПроводник"]


def test_read_aloud_diary(home, monkeypatch):
    (home / "diary").mkdir(parents=True)
    (home / "diary" / "2026-11-24.md").write_text(
        "День был тихий. Много строила.", encoding="utf-8")
    spoken = _voice_ready(monkeypatch)
    report = voice.read_aloud("дневник")
    assert "дневник за 2026-11-24" in report
    assert spoken == ["День был тихий. Много строила."]


def test_read_aloud_last_reply(home, monkeypatch):
    dlg = home / "dialog"
    dlg.mkdir()
    (dlg / "session_old.json").write_text(json.dumps(
        {"turns": [{"role": "assistant", "text": "старый ответ"}]},
        ensure_ascii=False), encoding="utf-8")
    time.sleep(0.02)
    (dlg / "session_new.json").write_text(json.dumps(
        {"turns": [{"role": "user", "text": "привет"},
                   {"role": "assistant", "text": "новый ответ"}]},
        ensure_ascii=False), encoding="utf-8")
    spoken = _voice_ready(monkeypatch)
    assert "последний ответ" in voice.read_aloud("последний ответ")
    assert spoken == ["новый ответ"]             # свежесть по штампу файла


def test_read_aloud_visitcard_and_unknown(home, monkeypatch):
    from core import personcard
    monkeypatch.setattr(personcard, "render",
                        lambda: "Визитка: Илья, Создатель.")
    spoken = _voice_ready(monkeypatch)
    assert "визитку Создателя" in voice.read_aloud("визитку")
    assert spoken == ["Визитка: Илья, Создатель."]
    assert "не знаю, что это" in voice.read_aloud("стихотворение")


def test_read_aloud_cuts_by_sentence(home, monkeypatch):
    (home / "diary").mkdir(parents=True)
    (home / "diary" / "2026-11-23.md").write_text(
        " ".join("Предложение %d." % i for i in range(1, 300)),
        encoding="utf-8")
    spoken = _voice_ready(monkeypatch)
    report = voice.read_aloud("дневник")
    assert "первые" in report
    assert spoken[0].endswith(".")              # рез по концу фразы
    assert len(spoken[0]) <= voice.REPLY_LIMIT


def test_read_aloud_dry_honest(home, monkeypatch):
    monkeypatch.setattr(voice, "available", lambda: False)
    assert "PowerShell" in voice.read_aloud("экран")
    assert "что прочитать" in voice.read_aloud("")


def test_fit_respects_sentence_boundary():
    text = "Первая фраза. Вторая фраза. " + "хвост " * 200
    head, cut = voice._fit(text, 60)
    assert cut is True and head.endswith(".")
    assert "хвост" not in head or head.count("хвост") < 3


# ---------- Ф65 «проверь буфер» ----------

def test_clipboard_selftest_roundtrip_and_restore(home, monkeypatch):
    clip = _FakeClip("важный текст Создателя")
    monkeypatch.setattr(hands, "_pyperclip", lambda: clip)
    report = hands.clipboard_selftest()
    assert "буфер жив" in report
    assert "в буфер <текст>" in report           # подсказка команд
    # чужое возвращено на место: проверка не ест буфер Создателя
    assert clip.paste() == "важный текст Создателя"


def test_clipboard_selftest_breakage_honest(home, monkeypatch):
    class _Broken:
        def copy(self, t):
            raise OSError("буфер закрыт")
        def paste(self):
            return ""
    monkeypatch.setattr(hands, "_pyperclip", lambda: _Broken())
    report = hands.clipboard_selftest()
    assert "не смогла" in report


def test_clipboard_selftest_no_module_honest(home, monkeypatch):
    def _no_module():
        raise ImportError("нет pyperclip")
    monkeypatch.setattr(hands, "_pyperclip", _no_module)
    report = hands.clipboard_selftest()
    assert "нет модуля pyperclip" in report and "аптечка" in report


# ---------- проводка агента ----------

@pytest.fixture()
def agent(home, monkeypatch):
    from core.agent import Agent
    from core.memory import Memory
    return Agent(memory=Memory(data_dir=Path(config.DATA_DIR)),
                 doctrine="Тестовая доктрина")


def test_agent_read_screen(agent, monkeypatch):
    monkeypatch.setattr(eyes, "read_texts_text",
                        lambda width=eyes.WORK_WIDTH: "Читаю на ЭКРАНЕ (2 надписей)")
    r = agent.handle("прочитай экран")
    assert r.source == "python" and r.tool_used == "read_screen"
    r = agent.handle("Марфа, прочитай что на экране?")
    assert r.tool_used == "read_screen"


def test_agent_screen_to_clipboard(agent, monkeypatch):
    _see_texts(monkeypatch, "Пуск\nПроводник")
    clip = _FakeClip()
    monkeypatch.setattr(hands, "_pyperclip", lambda: clip)
    r = agent.handle("экран в буфер")
    assert r.source == "python" and r.tool_used == "screen_to_clipboard"
    assert "все 2" in r.text and clip.copies[-1] == "Пуск\nПроводник"


def test_agent_clipboard_read_and_remember(agent, monkeypatch):
    clip = _FakeClip("запомни этот факт: небо синее")
    monkeypatch.setattr(hands, "_pyperclip", lambda: clip)
    r = agent.handle("что в буфере")
    assert r.tool_used == "clipboard" and "небо синее" in r.text
    r = agent.handle("запомни буфер")
    assert r.tool_used == "clipboard_remember"
    assert "запомнила из буфера" in r.text
    # память получила ТЕКСТ — «вспомни» находит его дословно
    found = agent.handle("вспомни небо")
    assert "небо синее" in found.text


def test_agent_clipboard_remember_empty(agent, monkeypatch):
    monkeypatch.setattr(hands, "_pyperclip", lambda: _FakeClip("  "))
    r = agent.handle("запомни буфер")
    assert r.tool_used == "clipboard_remember"
    assert "нечего" in r.text


def test_agent_check_clipboard(agent, monkeypatch):
    clip = _FakeClip("текст")
    monkeypatch.setattr(hands, "_pyperclip", lambda: clip)
    r = agent.handle("проверь буфер")
    assert r.tool_used == "clipboard_selftest" and "буфер жив" in r.text


def test_agent_read_aloud_beats_read_prefixes(agent, monkeypatch):
    """«прочитай вслух экран» — не «прочитай экран»: порядок сравнений
    разводит братьев по префиксу (урок раунда 3 о жадности)."""
    seen = {}
    monkeypatch.setattr(voice, "read_aloud",
                        lambda t: "читаю вслух: " + t)
    monkeypatch.setattr(eyes, "read_texts_text",
                        lambda width=eyes.WORK_WIDTH: "Читаю на ЭКРАНЕ")
    r = agent.handle("прочитай вслух экран")
    assert r.tool_used == "read_aloud" and "читаю вслух: экран" in r.text
    r = agent.handle("прочитай экран")
    assert r.tool_used == "read_screen"
    r = agent.handle("прочитай буфер")
    assert r.tool_used == "clipboard"


def test_agent_read_aloud_hint(agent, monkeypatch):
    r = agent.handle("прочитай вслух")
    assert r.tool_used == "read_aloud" and "что прочитать" in r.text


# ---------- зеркало знает новые команды ----------

def test_identity_knows_reading_circle():
    from core import identity
    joined = "; ".join(identity.FAST_COMMANDS)
    for piece in ("прочитай экран", "экран в буфер", "что в буфере",
                  "прочитай вслух", "проверь буфер"):
        assert piece in joined
