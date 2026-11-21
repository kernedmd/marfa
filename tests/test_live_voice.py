# -*- coding: utf-8 -*-
r"""tests/test_live_voice.py — ЖИВОЙ ЯЗЫК (гейт §5, вердикт 21.11.2026).

Резолюция Создателя (data/live_voice.json, кнопка 89) включает
«Живой рассказ» в дневнике и рефлексии. Честность конструкции:
- гейт закрыт или мозг молчит — дневник остаётся каркасом, без выдумок;
- рассказ пишется только по механическим фактам, с фиксом сэмплинга
  Qwen3 (temp 0.7 / top-p 0.8) — как постановил вердикт батареи.
"""
import datetime as dt
import json

import pytest

from core import config
from core.diary import (Diary, narrate, resolution, _sanitize_voice)

DAY = dt.date(2026, 11, 21)
EVENING = dt.datetime(2026, 11, 21, 21, 0)


@pytest.fixture()
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("MARFA_HOME", str(tmp_path))
    monkeypatch.setattr(config, "HOME_DIR", tmp_path)
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(config, "LIVE_VOICE_FILE",
                        tmp_path / "data" / "live_voice.json")
    config.ensure_dirs()
    yield tmp_path


def _resolve(home, enabled=True, basis="батарея 21.11.2026: факты 13/13"):
    p = home / "data" / "live_voice.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(
        {"enabled": enabled, "since": "2026-11-21T14:00:00", "basis": basis},
        ensure_ascii=False), encoding="utf-8")


class FakeBrain:
    """Мозг из теста: записывает вызовы, отвечает заготовкой."""

    def __init__(self, reply="День прошёл тихо, я следила за домом."):
        self.reply = reply
        self.calls = []

    def chat(self, messages, gen_tokens=None, temperature=None, top_p=None):
        self.calls.append({"messages": messages, "gen_tokens": gen_tokens,
                           "temperature": temperature, "top_p": top_p})
        return self.reply


class DeadBrain:
    def chat(self, *a, **k):
        raise ConnectionError("мозг молчит")


# ---------- резолюция ----------

def test_resolution_absent_is_closed(home):
    assert resolution() is None


def test_resolution_enabled(home):
    _resolve(home, enabled=True)
    assert (resolution() or {}).get("enabled") is True


def test_resolution_disabled_or_broken_is_closed(home):
    _resolve(home, enabled=False)
    assert resolution() is None
    (home / "data" / "live_voice.json").write_text("{битый", encoding="utf-8")
    assert resolution() is None


# ---------- гейт закрыт: каркас без выдумок ----------

def test_gate_closed_placeholder_stays(home):
    text = Diary().build_day(day=DAY, now=EVENING, brain=FakeBrain())
    assert "вердикта батареи" in text          # место помечено, не выдумано
    assert "рассказала сама" not in text


def test_narrate_gate_closed_brain_untouched(home):
    b = FakeBrain()
    assert narrate({"date": "2026-11-21"}, brain=b) is None
    assert b.calls == []                        # мозг не будим зря


# ---------- рассказ: сэмплинг и факты ----------

def test_narrate_uses_qwen3_fix_sampling(home):
    _resolve(home)
    b = FakeBrain()
    out = narrate({"date": "2026-11-21"}, brain=b)
    assert out == "День прошёл тихо, я следила за домом."
    kw = b.calls[0]
    assert kw["temperature"] == 0.7             # фикс батареи, не дефолт 0.3
    assert kw["top_p"] == 0.8
    assert kw["gen_tokens"] == config.LIVE_VOICE_MAX_TOKENS


def test_narrate_prompt_carries_facts_and_frame(home):
    _resolve(home)
    b = FakeBrain()
    narrate({"date": "2026-11-21",
             "plan": {"total": 3, "done": 1, "open_titles": ["проверить уши"],
                      "carry_over": []},
             "dialogs": {"sessions": 2, "user_turns": 5,
                         "topics": ["как дела с памятью"]}}, brain=b)
    msgs = b.calls[0]["messages"]
    assert msgs[0]["role"] == "system"
    assert "чего в фактах нет" in msgs[0]["content"]      # честность в характере
    user = msgs[1]["content"]
    assert "данные дома, не истина" in user               # рамка из доктрины
    assert "задач 3, сделано 1" in user
    assert "проверить уши" in user
    assert "как дела с памятью" in user


def test_narrate_quiet_day_is_honest(home):
    _resolve(home)
    b = FakeBrain()
    narrate({"date": "2026-11-21"}, brain=b)
    assert "разговоров с Ильёй не было" in b.calls[0]["messages"][1]["content"]


def test_narrate_brain_down_returns_none(home):
    _resolve(home)
    assert narrate({"date": "2026-11-21"}, brain=DeadBrain()) is None


# ---------- дневник с рассказом ----------

def test_build_day_live_voice_written(home):
    _resolve(home)
    text = Diary().build_day(day=DAY, now=EVENING, brain=FakeBrain())
    assert "День прошёл тихо, я следила за домом." in text
    assert "рассказала сама" in text                        # подпись честности
    assert "факты 13/13" in text                            # основание видно
    assert (home / "data" / "diary" / "2026-11-21.md").exists()


def test_build_day_rebuild_replaces_narration(home):
    _resolve(home)
    d = Diary()
    d.build_day(day=DAY, now=EVENING, brain=FakeBrain("Первый рассказ."))
    d.build_day(day=DAY, now=EVENING, brain=FakeBrain("Второй рассказ."))
    final = d.path(DAY).read_text(encoding="utf-8")
    assert "Второй рассказ." in final
    assert "Первый рассказ." not in final
    assert final.count("## Живой рассказ") == 1             # один день — один раздел


def test_build_day_brain_down_honest_note(home):
    _resolve(home)
    text = Diary().build_day(day=DAY, now=EVENING, brain=DeadBrain())
    assert "рассказ не выдуман" in text
    assert "рассказала сама" not in text


# ---------- чистка ответа ----------

def test_sanitize_strips_tags_headers_quotes():
    assert _sanitize_voice("<output>Тихий день в доме.</output>\n# Заголовок") == "Тихий день в доме."
    assert _sanitize_voice("«Тихий день в доме.»") == "Тихий день в доме."


def test_sanitize_caps_length():
    out = _sanitize_voice("слово " * 500)
    assert len(out) <= config.LIVE_VOICE_TEXT_CAP
    assert out.endswith("...")


def test_narrate_empty_answer_is_none(home):
    _resolve(home)
    assert narrate({"date": "2026-11-21"}, brain=FakeBrain("<b></b>")) is None


# ---------- рефлексия ----------

def _mk_diary_file(home, day_iso, body):
    p = home / "data" / "diary" / (day_iso + ".md")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")


def test_reflect_appends_and_keeps_last_diary_true(home):
    _resolve(home)
    _mk_diary_file(home, "2026-11-20", "# Дневник — 2026-11-20\nТихий день.")
    _mk_diary_file(home, "2026-11-21", "# Дневник — 2026-11-21\nГоворили с Ильёй.")
    d = Diary()
    thought = d.reflect(now=EVENING, brain=FakeBrain("Я поняла, что дни стали живее."))
    assert thought == "Я поняла, что дни стали живее."
    rf = home / "data" / "diary" / "reflections.md"
    assert rf.exists()
    assert "Я поняла, что дни стали живее." in rf.read_text(encoding="utf-8")
    assert "2026-11-21 21:00" in rf.read_text(encoding="utf-8")
    # reflections.md не притворяется дневником
    assert d.last_diary() == "2026-11-21"


def test_reflect_reads_only_recent_diaries(home):
    _resolve(home)
    _mk_diary_file(home, "2026-11-19", "# 19")
    _mk_diary_file(home, "2026-11-20", "# 20")
    _mk_diary_file(home, "2026-11-21", "# 21")
    b = FakeBrain("думаю")
    Diary().reflect(now=EVENING, brain=b, days=2)
    user = b.calls[0]["messages"][1]["content"]
    assert "2026-11-20" in user and "2026-11-21" in user
    assert "Дневник 2026-11-19" not in user


def test_reflect_no_diaries_none(home):
    _resolve(home)
    assert Diary().reflect(now=EVENING, brain=FakeBrain()) is None


def test_reflect_gate_closed_none(home):
    _mk_diary_file(home, "2026-11-21", "# Дневник")
    assert Diary().reflect(now=EVENING, brain=FakeBrain()) is None


def test_reflect_brain_down_none(home):
    _resolve(home)
    _mk_diary_file(home, "2026-11-21", "# Дневник")
    assert Diary().reflect(now=EVENING, brain=DeadBrain()) is None


# ---------- агент: команды ----------

def test_agent_reflection_hints_button_when_gate_closed(home):
    from core.agent import Agent
    r = Agent(brain=FakeBrain(), memory=None, doctrine="").handle("поразмышляй")
    assert r.source == "python" and r.tool_used == "reflection"
    assert "89" in r.text                                  # чем включается


def test_agent_reflection_with_resolution_and_brain(home):
    from core.agent import Agent
    _resolve(home)
    _mk_diary_file(home, "2026-11-21", "# Дневник — 2026-11-21\nБыл разговор.")
    r = Agent(brain=FakeBrain("Дни стали интереснее."), memory=None,
              doctrine="").handle("поразмышляй")
    assert r.source == "python" and r.tool_used == "reflection"
    assert "Дни стали интереснее." in r.text
    assert (home / "data" / "diary" / "reflections.md").exists()


def test_agent_podvedi_den_narrates_with_agent_brain(home):
    from core.agent import Agent
    _resolve(home)
    r = Agent(brain=FakeBrain("Вечер тихий, дом целый."), memory=None,
              doctrine="").handle("подведи день")
    assert r.tool_used == "diary"
    assert "Вечер тихий, дом целый." in r.text             # живой рассказ в ответе
    assert "рассказала сама" in r.text
