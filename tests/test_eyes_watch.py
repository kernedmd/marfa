# -*- coding: utf-8 -*-
"""tests/test_eyes_watch.py — №6 роадмапа 30: «глаза как контекст
мозга» (закрывает Г-3).

Флаг «Илья за компьютером»: резолюция Создателя «следи за экраном» —
и каждый мозговой трек получает свежую строку о экране в СОСТОЯНИИ
ДОМА (промпт мозгового трека). Контракт:

  - слежение выключено — строки нет, промпт не дорожает;
  - включено — строка «экран сейчас: …» в состоянии дома, взгляд
    честно датирован («взгляд только что» / «N мин назад»);
  - кэш TTL: один взгляд живёт 5 минут, второй ход не платит
    сенсору по 9 секунд;
  - взгляд — тоже взгляд: кадр становится эталоном №3;
  - глаза мертвы — честная строка «не прочитан» (кэшируется:
    каждый ход не ждёт мёртвый сенсор), ход не падает;
  - резолюция — как моторика: файл data/screen_watch.json пишут
    только команды «следи/не следи за экраном»;
  - промпт слежения — без единого примера значений (урок v3).
"""
import json
import re
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import agent, config, eyes  # noqa: E402


@pytest.fixture()
def home(monkeypatch, tmp_path):
    monkeypatch.setenv("MARFA_HOME", str(tmp_path))
    monkeypatch.setattr(config, "HOME_DIR", tmp_path)
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(config, "SCREEN_WATCH_FILE",
                        tmp_path / "data" / "screen_watch.json")
    yield tmp_path


def _watch_sees(monkeypatch, prose, calls=None):
    """Слежение видит prose; сенсор, экран и здоровье подменены."""
    monkeypatch.setattr(eyes, "_VISION_ERROR", None)
    monkeypatch.setattr(eyes, "health_cached", lambda period=30.0: True)
    monkeypatch.setattr(eyes, "_screenshot_b64",
                        lambda width=eyes.WORK_WIDTH:
                        ("WATCH-B64", (1920, 1080), (1280, 720)))

    def fake_ask(b64, prompt, schema, max_tokens=eyes.WATCH_MAX_TOKENS,
                 timeout=None):
        if calls is not None:
            calls.append(1)
        return (prose, None)

    monkeypatch.setattr(eyes, "_ask", fake_ask)


def _enable(monkeypatch, tmp_path):
    monkeypatch.setattr(eyes, "_watch_cache", {"line": None, "ts": 0.0})
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)
    (tmp_path / "data" / "screen_watch.json").write_text(
        json.dumps({"enabled": True}), encoding="utf-8")


# ---------- выключено: промпт не дорожает ----------

def test_disabled_no_context_line(home, monkeypatch):
    monkeypatch.setattr(eyes, "health_cached", lambda period=30.0: True)
    assert eyes.screen_context_line() is None
    s = agent._house_state()
    assert "экран сейчас" not in s


# ---------- включено: строка в состоянии дома ----------

def test_enabled_adds_line_to_house_state(home, monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    _watch_sees(monkeypatch, "Открыт браузер с документацией")
    monkeypatch.setattr(eyes, "health_cached", lambda period=30.0: True)
    s = agent._house_state()
    assert "экран сейчас: Открыт браузер с документацией" in s
    assert "взгляд только что" in s


def test_watch_glance_is_also_reference(home, monkeypatch, tmp_path):
    """Взгляд слежения — тоже взгляд: кадр становится эталоном №3."""
    monkeypatch.setattr(eyes, "_last_frame", {})
    _enable(monkeypatch, tmp_path)
    _watch_sees(monkeypatch, "рабочий стол")
    eyes.screen_context_line()
    assert eyes._last_frame["b64"] == "WATCH-B64"


def test_watch_cache_ttl(home, monkeypatch, tmp_path):
    """Один взгляд живёт 5 минут: второй ход берёт кэш, сенсор не
    платится дважды (урок health_cached — теперь и для контекста)."""
    _enable(monkeypatch, tmp_path)
    calls = []
    _watch_sees(monkeypatch, "Открыт редактор кода", calls=calls)
    first = eyes.screen_context_line()
    second = eyes.screen_context_line()
    assert "Открыт редактор кода" in first and "Открыт редактор кода" in second
    assert len(calls) == 1                       # второй — из кэша
    # кэш устарел — снова взгляд
    monkeypatch.setattr(eyes, "_watch_cache",
                        {"line": "старое", "ts": time.time() - 301.0})
    eyes.screen_context_line()
    assert len(calls) == 2


def test_watch_age_dated_honestly(home, monkeypatch, tmp_path):
    """Свежесть взгляда — в тексте: «5 мин назад», а не вечное «сейчас»."""
    _enable(monkeypatch, tmp_path)
    _watch_sees(monkeypatch, "почта открыта")
    monkeypatch.setattr(eyes, "_watch_cache",
                        {"line": "почта открыта", "ts": time.time() - 240.0})
    line = eyes.screen_context_line()
    assert "4 мин назад" in line


# ---------- честные отказы ----------

def test_watch_eyes_dead_honest_cached(home, monkeypatch, tmp_path):
    """Сенсор мёртв — честная строка вместо выдумки, И она кэшируется:
    каждый следующий ход не ждёт мёртвый сенсор по 9 секунд."""
    _enable(monkeypatch, tmp_path)
    monkeypatch.setattr(eyes, "_VISION_ERROR", None)
    monkeypatch.setattr(eyes, "health_cached", lambda period=30.0: False)
    calls = []

    def dead_ask(*a, **kw):
        calls.append(1)
        raise RuntimeError("не должен был зваться")

    monkeypatch.setattr(eyes, "_ask", dead_ask)
    line1 = eyes.screen_context_line()
    assert "не прочитан" in line1 and "8083" in line1
    line2 = eyes.screen_context_line()
    assert "не прочитан" in line2
    assert calls == []                            # сенсор не дёргаем


def test_watch_no_module_honest(home, monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    monkeypatch.setattr(eyes, "_VISION_ERROR", "нет модуля зрения: x")
    assert "не прочитан" in eyes.screen_context_line()


def test_watch_glance_crash_armored_in_state(home, monkeypatch, tmp_path):
    """№10 р3: слежение упало — состояние дома деградирует построчно,
    ход жив; «мозг недоступен» из-за глаз — ложный диагноз."""
    _enable(monkeypatch, tmp_path)

    def boom(force=False):
        raise RuntimeError("взорвалось")

    monkeypatch.setattr(eyes, "screen_context_line", boom)
    monkeypatch.setattr(eyes, "health_cached", lambda period=30.0: True)
    s = agent._house_state()                      # не поднялось наверх
    assert "Состояние дома" in s and "экран сейчас" not in s


def test_watch_prompt_no_parrotable_example():
    """Урок v3 един для всех промптов сенсора: ни одной цифры-примера."""
    assert not re.search(r"\[\s*\d+\s*,\s*\d+\s*,", eyes.WATCH_PROMPT)
    assert eyes.WATCH_MAX_TOKENS <= 200           # фон — не отчёт


def test_watch_line_capped(home, monkeypatch, tmp_path):
    """Контекст — не роман: строка слежения урезана потолком."""
    _enable(monkeypatch, tmp_path)
    _watch_sees(monkeypatch, "д" * 1000)
    line = eyes.screen_context_line()
    assert len(line.split(" (взгляд")[0]) <= eyes.WATCH_LINE_CAP


# ---------- резолюция Создателя ----------

def test_set_watch_on_off(home, monkeypatch, tmp_path):
    """Воля живёт в data/: включение пишет файл, выключение убирает;
    кэш сбрасывается — новый режим виден сразу."""
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)
    assert eyes.set_watch(True).startswith("Теперь слежу")
    assert eyes.watch_enabled() is True
    assert eyes.set_watch(False).startswith("Больше не слежу")
    assert eyes.watch_enabled() is False
    # повторное выключение не падает (файла уже нет)
    assert eyes.set_watch(False).startswith("Больше не слежу")


def test_agent_commands_toggle_watch(home, monkeypatch, tmp_path):
    """КРУГ 36 (аудит 284, ритуал продления): ВКЛЮЧЕНИЕ слежения — за
    калиткой Создателя (прежде любая фраза показывала мозгу весь
    экран); ВЫКЛЮЧЕНИЕ — свободно (безопасное направление); «смотри за
    экраном» — та же резолюция, тоже за словом."""
    class FakeBrain:
        calls = 0

        def ask_json(self, *a, **kw):
            self.calls += 1
            return {"answer": "мозг"}

    class FakeMemory:
        def recall(self, *a, **k):
            return []

    word = "тайное-слово-калитки"
    (tmp_path / ".env").write_text("MARFA_CODEWORD=%s\n" % word,
                                   encoding="utf-8")
    a = agent.Agent(brain=FakeBrain(), memory=FakeMemory())

    # без слова — честный указатель, экран мозгу не показывается
    r = a.handle("следи за экраном")
    assert r.tool_used == "screen_watch" and "калитк" in r.text
    assert eyes.watch_enabled() is False
    assert a.brain.calls == 0

    # со словом — резолюция Создателя
    r = a.handle(word + " следи за экраном")
    assert r.tool_used == "creator_gate"
    assert eyes.watch_enabled() is True
    assert a.brain.calls == 0          # слово и команда — мимо мозга

    # выключение — свободно
    r = a.handle("не следи за экраном")
    assert r.tool_used == "screen_watch" and "Больше не слежу" in r.text
    assert eyes.watch_enabled() is False

    # «смотри за экраном» — та же резолюция за словом
    a.handle(word + " смотри за экраном")
    assert eyes.watch_enabled() is True
    a.handle("не следи за экраном")
    assert eyes.watch_enabled() is False
