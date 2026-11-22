# -*- coding: utf-8 -*-
"""Тесты ЭФИРА ДОМА: Марфа говорит, что делает, и сколько думала.

Урок живого чата 22.11 (вечер-4): «ответы очень долгие, надо в чат
прописать время, и вообще не понятно, пока не запустишь консоль, что
вообще происходит». Эфир — begin/stage/finish/snapshot + источник
по-человечески. Закон: эфир НИКОГДА не рвёт работу дома.
"""
import time

import pytest

from core import progress


@pytest.fixture(autouse=True)
def quiet_air():
    """Каждый тест начинает с чистого эфира — и оставляет чистым."""
    progress.reset()
    yield
    progress.reset()


# ---------- полный ход ----------

def test_idle_snapshot_is_honest():
    s = progress.snapshot()
    assert s["busy"] is False
    assert s["stage"] == ""
    assert s["elapsed"] == 0.0


def test_begin_stage_finish_full_walk():
    progress.begin("s1")
    s = progress.snapshot("s1")
    assert s["busy"] is True and s["mine"] is True
    assert s["sid"] == "s1"
    assert s["stage"]                    # «приняла сообщение, думаю…»
    assert s["elapsed"] >= 0.0
    progress.stage("глаза читают экран…")
    s = progress.snapshot("s1")
    assert s["stage"] == "глаза читают экран…"
    assert s["stage_secs"] >= 0.0
    progress.finish(secs=12.3, source="brain")
    s = progress.snapshot("s1")
    assert s["busy"] is False            # эфир свободен сразу
    assert s["last"]["secs"] == 12.3
    assert s["last"]["source"] == "мозг"
    assert s["last"]["sid"] == "s1"
    assert s["last"]["ts"]               # штамп времени доезжает


def test_stage_outside_walk_ignored():
    """Скрипты и голос без хода эфир не занимают: врать «думаю» некому."""
    progress.stage("мусор от скрипта")
    assert progress.snapshot()["busy"] is False


def test_foreign_session_sees_other_talk():
    """Второе окно чата видит: Марфа отвечает в другом разговоре."""
    progress.begin("mine")
    progress.stage("думаю")
    s = progress.snapshot("other")
    assert s["busy"] is True
    assert s["mine"] is False
    # а панель спрашивает без сессии — ей показываем любой ход
    assert progress.snapshot("")["mine"] is True


def test_new_begin_resets_stale_walk():
    """Панель перезапустили посреди думания — эфир не застревает навсегда."""
    progress.begin("dead")
    progress.stage("вечно думаю…")
    progress.begin("fresh")
    s = progress.snapshot("fresh")
    assert s["busy"] is True
    assert s["sid"] == "fresh"
    assert "вечно" not in s["stage"]     # стадия прошлого хода стёрлась


def test_finish_counts_secs_itself_when_not_given():
    progress.begin("s")
    time.sleep(0.02)
    progress.finish(source="python")
    assert progress.snapshot()["last"]["secs"] >= 0.0
    assert progress.snapshot()["last"]["source"] == "дом (без мозга)"


def test_source_labels_human():
    assert progress.source_label("brain") == "мозг"
    assert progress.source_label("python") == "дом (без мозга)"
    assert progress.source_label("fallback") == "фоллбэк"
    assert progress.source_label("глаза") == "глаза"      # незнакомый — как есть
    assert progress.source_label("") == "дом"


def test_air_never_raises():
    """ЗАКОН: даже мусор в эфир не рвёт работу дома."""
    progress.stage(None)                                  # type: ignore[arg-type]
    progress.begin(None)                                  # type: ignore[arg-type]
    progress.finish(secs=None, source=None)
    assert progress.snapshot("плохое имя с пробелами")["busy"] is False


# ---------- слуги выходят в эфир ----------

def test_eyes_stages_go_on_air(monkeypatch):
    """Глаза докладывают стадии: «снимаю экран…» → «читают…»."""
    from core import eyes

    seen = []
    progress.begin("web")
    monkeypatch.setattr(eyes, "_VISION_ERROR", None)
    monkeypatch.setattr(eyes, "health", lambda: True)

    def fake_shot(width=eyes.WORK_WIDTH):
        seen.append(progress.snapshot()["stage"])
        return ("b64", (1920, 1080), (1280, 720))

    def fake_ask(b64, prompt, schema, max_tokens=eyes.ELEMENTS_MAX_TOKENS):
        seen.append(progress.snapshot()["stage"])
        return ("{}", None)

    monkeypatch.setattr(eyes, "_screenshot_b64", fake_shot)
    monkeypatch.setattr(eyes, "_ask", fake_ask)
    monkeypatch.setattr(eyes, "parse_json", lambda text: {"elements": []})
    eyes.describe_text()
    assert seen[0] == "снимаю экран…"
    assert "читают экран" in seen[1]


def test_brain_track_announces_thinking(monkeypatch, tmp_path):
    """Мозговой трек — в эфире: «собираю контекст…» и «мозг думает…»."""
    from core.agent import Agent

    seen = []

    class SpyBrain:
        def ask_json(self, *a, **k):
            seen.append(progress.snapshot()["stage"])
            return {"answer": "готово"}

    progress.begin("web")
    agent = Agent(brain=SpyBrain(), memory=None, doctrine="")
    reply = agent.handle("сложный вопрос")
    progress.finish(source=reply.source)
    assert reply.text == "готово"
    assert any("мозг думает" in s for s in seen)
    assert progress.snapshot()["last"]["source"] == "мозг"


# ---------- СКОРОСТЬ v1: превью — мозг печатает ответ живьём ----------

def test_preview_lives_only_during_walk():
    """Превью — часть хода: вне хода мимо (врать некому), finish стирает."""
    progress.reset()
    progress.preview("печатаю ответ…")
    assert progress.snapshot()["preview"] == ""      # вне хода — мимо
    progress.begin("pv1")
    progress.preview("печатаю ответ…")
    snap = progress.snapshot("pv1")
    assert snap["busy"] is True
    assert snap["preview"] == "печатаю ответ…"
    progress.finish(secs=1.0, source="brain")
    snap = progress.snapshot()
    assert snap["busy"] is False and snap["preview"] == ""


def test_preview_keeps_tail():
    """Долгий ответ — показываем ХВОСТ: важно то, что печатается сейчас,
    а не первые слова минутной давности."""
    progress.reset()
    progress.begin("pv2")
    progress.preview("а" * 500)
    snap = progress.snapshot("pv2")
    assert snap["preview"].startswith("…")
    assert len(snap["preview"]) == 401              # …+ хвост 400
    progress.finish(source="brain")


def test_begin_resets_stale_preview():
    """Новый ход не наследует черновик прошлого (рестарт панели)."""
    progress.reset()
    progress.begin("pv3")
    progress.preview("старый черновик")
    progress.begin("pv3")
    assert progress.snapshot("pv3")["preview"] == ""
    progress.finish(source="")
