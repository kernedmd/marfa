# -*- coding: utf-8 -*-
"""Тесты МЫСЛЕЙ и СНОВ (23.11): фоновое размышление в тишине, гейт §5,
семена из фактов, «о чём думаешь?» — свежая мысль, утренний сон."""
import datetime as dt
import json
import os

import pytest

from core import config
from core import musing


@pytest.fixture()
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("MARFA_HOME", str(tmp_path))
    monkeypatch.setattr(config, "HOME_DIR", tmp_path)
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(config, "QUESTIONS_FILE", tmp_path / "data" / "questions.json")
    monkeypatch.setattr(config, "LIVE_VOICE_FILE", tmp_path / "data" / "live_voice.json")
    monkeypatch.setattr(config, "MUSINGS_FILE", tmp_path / "data" / "diary" / "musings.md")
    monkeypatch.setattr(config, "DREAMS_FILE", tmp_path / "data" / "diary" / "dreams.md")
    monkeypatch.setattr(config, "SLEEP_FILE", tmp_path / "data" / "sleep.json")
    config.ensure_dirs()
    yield tmp_path


NOW = dt.datetime(2026, 11, 23, 15, 0)


class FakeBrain:
    """Мозг-подделка: говорит то, что ему велели, и помнит промпты."""

    def __init__(self, answer="Мысль по делу. Вторая фраза."):
        self.answer = answer
        self.prompts = []

    def chat(self, messages, **kw):
        self.prompts.append(messages)
        return self.answer


def _allow_live_voice(home):
    (home / "data" / "live_voice.json").write_text(json.dumps({
        "enabled": True, "basis": "тест"}), encoding="utf-8")


def _quiet_house(home, hours=5.0):
    """Дом тихий N часов: сессия диалога с mtime в прошлом."""
    p = home / "data" / "dialog" / "session_s.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("{}", encoding="utf-8")
    ts = (NOW - dt.timedelta(hours=hours)).timestamp()
    os.utime(p, (ts, ts))


def _seed_memory(home, text="Илья любит тишину по утрам"):
    p = home / "data" / "memory" / "memory.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps([{"text": text}], ensure_ascii=False),
                 encoding="utf-8")


def test_muse_gates_in_order(home):
    # 1) спит — мысль ждёт утра (окно ночи: NOW-15ч = 00:00 23.11? нет —
    #    кладём организм принудительно днём)
    from core import sleep as sleep_mod
    sleep_mod.go_to_bed(NOW)
    text, status = musing.muse(NOW, brain=FakeBrain(), force=True)
    assert text is None and "сплю" in status
    sleep_mod.wake(NOW + dt.timedelta(minutes=1), reason="тест")

    # 2) не тихо (Илья рядом) — мысль вежливо молчит
    _quiet_house(home, hours=0.2)
    _allow_live_voice(home)
    text, status = musing.muse(NOW, brain=FakeBrain())
    assert text is None and "не тихо" in status

    # 3) тихо, но гейт §5 закрыт — мысли не выдумываются
    _quiet_house(home, hours=5.0)
    (home / "data" / "live_voice.json").unlink()
    text, status = musing.muse(NOW, brain=FakeBrain())
    assert text is None and "гейт" in status

    # 4) гейт открыт, но семян нет — думать не о чем
    _allow_live_voice(home)
    text, status = musing.muse(NOW, brain=FakeBrain())
    assert text is None and "семян нет" in status


def test_muse_thinks_and_writes(home):
    _allow_live_voice(home)
    _quiet_house(home, hours=5.0)
    _seed_memory(home)
    brain = FakeBrain("Интересное воспоминание про утро. Подумаю об этом.")
    text, status = musing.muse(NOW, brain=brain)
    assert text is not None and "воспоминание" in text
    assert status == "подумала и записала"
    # семя и состояние дошли до мозга
    joined = "\n".join(m["content"] for m in brain.prompts[0])
    assert "Илья любит тишину" in joined
    assert "моё состояние" in joined
    # мысль легла в журнал со штампом
    raw = (home / "data" / "diary" / "musings.md").read_text(encoding="utf-8")
    assert "## 2026-11-23 15:00" in raw
    assert "воспоминание" in raw


def test_muse_brain_silent_honest(home):
    _allow_live_voice(home)
    _quiet_house(home, hours=5.0)
    _seed_memory(home)

    class DeadBrain:
        def chat(self, *a, **kw):
            raise TimeoutError("нет ответа")

    text, status = musing.muse(NOW, brain=DeadBrain())
    assert text is None and "не выдуман" in status


def test_last_musing_freshness(home):
    _allow_live_voice(home)
    _quiet_house(home, hours=5.0)
    _seed_memory(home)
    musing.muse(NOW, brain=FakeBrain("Думала про дом. Тихо и хорошо."))
    # свежая мысль (тот же час) — видна
    got = musing.last_musing(now=NOW + dt.timedelta(minutes=10))
    assert got is not None
    assert "Думала про дом" in got[1]
    line = musing.render_last(now=NOW + dt.timedelta(minutes=10))
    assert line is not None and "15:00" in line
    # через три часа — уже не «думаю», а «думала» старое: честно скрыта
    assert musing.last_musing(now=NOW + dt.timedelta(hours=3)) is None
    assert musing.state_line(now=NOW + dt.timedelta(hours=3)) == ""


def test_muse_force_bypasses_idle_not_gate(home):
    # «подумай» от Создателя: тишина не нужна, гейт §5 — закон
    _quiet_house(home, hours=0.1)
    _allow_live_voice(home)
    _seed_memory(home)
    text, status = musing.muse(NOW, brain=FakeBrain("Мысль по заказу."), force=True)
    assert text is not None and "по заказу" in text


def test_dream_from_yesterday(home):
    _allow_live_voice(home)
    diary_dir = home / "data" / "diary"
    diary_dir.mkdir(parents=True, exist_ok=True)
    (diary_dir / "2026-11-22.md").write_text(
        "# Дневник\n\n## Разговоры\nСессий: 2.\n", encoding="utf-8")
    # вчерашние мысли — семя для сна
    (diary_dir / "musings.md").write_text(
        "## 2026-11-22 14:00\n\nДумала о планах на неделю.\n",
        encoding="utf-8")
    brain = FakeBrain("Приснилось, что дом дышит тихо. Утро длинное.")
    text, status = musing.dream(NOW, brain=brain)
    assert text is not None and "дышит" in text
    assert status == "сон записан"
    joined = "\n".join(m["content"] for m in brain.prompts[0])
    assert "2026-11-22" in joined          # дневник вчера
    assert "Думала о планах" in joined     # и мысли
    raw = (home / "data" / "diary" / "dreams.md").read_text(encoding="utf-8")
    assert "## 2026-11-23 15:00" in raw
    got = musing.last_dream()
    assert got is not None and "дышит" in got[1]
    assert "снилось" in musing.render_last_dream()


def test_dream_nothing_to_dream_about(home):
    _allow_live_voice(home)
    text, status = musing.dream(NOW, brain=FakeBrain())
    assert text is None and "не из чего" in status


def test_dream_gate_closed(home):
    text, status = musing.dream(NOW, brain=FakeBrain())
    assert text is None and "гейт" in status


def test_render_last_dream_empty_honest(home):
    assert "снов ещё не записано" in musing.render_last_dream()


def test_read_entries_limit_edge(home):
    # журнал из одной записи, лимит 3 — индексация не роняет чтение
    p = home / "data" / "diary" / "musings.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("## 2026-11-23 10:00\n\nОдна-единственная мысль.\n",
                 encoding="utf-8")
    entries = musing._read_entries(p, limit=3)
    assert len(entries) == 1
    assert entries[0][1] == "Одна-единственная мысль."
