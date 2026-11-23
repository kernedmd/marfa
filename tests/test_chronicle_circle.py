# -*- coding: utf-8 -*-
"""Тесты круга 12 «ХРОНИКА» (Ф66–Ф70, день-10): организм помнит свой
путь — рост из git, вся история пары, день рождения, честные мечты,
первый разговор.

Законы, которые куются здесь:
- «цифры или ничего»: каждый счётчик читается из живого источника
  (git, файлы дома), сбывшаяся мечта называется сбывшейся — желание
  не выдаётся за действительность;
- день рождения — факт истории дома из книги (мастер-ТЗ §22), не
  выдумка личности;
- «первый разговор» честно называет себя «самым ранним из живых»:
  архив чистится, память — не музей;
- якоря по живому выводу с русскими падежами (урок дня-9: «коммит,
  коммита, коммитов» — все читаются).
"""
import datetime as dt
import json
from pathlib import Path

import pytest

from core import chronicle, config


@pytest.fixture()
def home(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "HOME_DIR", tmp_path)
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    config.ensure_dirs()
    yield tmp_path


# ---------- Ф66 «чем ты выросла» ----------

def test_growth_counts_commits_feats_organs(home, monkeypatch):
    subjects = ["круг 10 «ГОЛОС» — Ф56-Ф60 из дня-10",
                "круг 11 «ЧТЕНИЕ И БУФЕР» — Ф61-Ф65",
                "мелочь без фишки"]
    added = ["core/voice.py", "tests/test_voice_circle.py"]

    def fake_git(args):
        if args[:1] == ["log"] and "--format=%s" in args:
            return 0, "\n".join(subjects)
        if "--diff-filter=A" in args:
            return 0, "\n".join(added)
        if args[:2] == ["rev-list", "--count"]:
            return 0, "163\n"
        return 0, ""

    monkeypatch.setattr(chronicle, "_git", fake_git)
    out = chronicle.growth()
    assert "коммитов: 3" in out
    assert "10 фишек: Ф56–Ф65" in out
    assert "новые органы: voice.py" in out
    assert "тест" not in out.split("новые органы")[1].split("\n")[0]


def test_growth_tempo_against_previous_week(home, monkeypatch):
    """Две недели в истории: темп честно сравнивается (ускорилась,
    замедлилась, ровный) — падеж числа коммитов выживает (урок дня-9)."""
    calls = {"n": 0}

    def fake_git(args):
        if args[:1] == ["log"] and "--format=%s" in args:
            calls["n"] += 1
            return 0, "\n".join(["c%d" % i for i in range(5)]) \
                if calls["n"] == 1 else "\n".join(["c%d" % i for i in range(8)])
        return 0, ""

    monkeypatch.setattr(chronicle, "_git", fake_git)
    out = chronicle.growth()
    # за окно 14 дней — 8, из них 5 на этой неделе: неделей раньше — 3
    assert "коммитов: 5" in out and "было 3 коммита" in out
    assert "УСКОРИЛАСЬ" in out


def test_growth_silent_git_honest(home, monkeypatch):
    monkeypatch.setattr(chronicle, "_git", lambda args: (1, ""))
    out = chronicle.growth()
    assert "git в доме не отвечает" in out


def test_growth_empty_week_honest(home, monkeypatch):
    def fake_git(args):
        if args[:2] == ["rev-list", "--count"]:
            return 0, "163\n"
        return 0, ""
    monkeypatch.setattr(chronicle, "_git", fake_git)
    out = chronicle.growth()
    assert "новых коммитов не было" in out


# ---------- Ф67 «наш путь» ----------

def test_journey_counts_living_house(home, monkeypatch):
    monkeypatch.setattr(chronicle, "_git",
                        lambda args: (0, "165\n")
                        if args[:2] == ["rev-list", "--count"] else (0, ""))
    # живые органы и кнопки — настоящие файлы песочницы
    (home / "core").mkdir(exist_ok=True)
    (home / "core" / "voice.py").write_text("# орган", encoding="utf-8")
    (home / "core" / "__init__.py").write_text("", encoding="utf-8")
    (home / "scripts").mkdir(exist_ok=True)
    (home / "scripts" / "94_voice.bat").write_text("@echo off", encoding="utf-8")

    class _Mem:
        def count(self):
            return 42

    out = chronicle.journey(memory=_Mem())
    today = dt.date.today()
    lived = (today - chronicle.BIRTH).days
    assert ("МЫ ВМЕСТЕ %d" % lived) in out
    assert "коммитов в истории дома: 165" in out
    assert "органов в теле: 1" in out          # __init__ не считается
    assert "кнопок у Создателя: 1" in out
    assert "живых воспоминаний: 42" in out
    assert "наш первый разговор" in out        # мост к Ф70


def test_journey_survives_dead_organs(home, monkeypatch):
    """Упавший орган не роняет путь (закон №10 р3): счётчики в броне."""
    monkeypatch.setattr(chronicle, "_git", lambda args: (1, ""))
    out = chronicle.journey(memory=None)
    assert "МЫ ВМЕСТЕ" in out


def test_plural_days_russian_cases():
    assert chronicle._plural_days(1) == "день"
    assert chronicle._plural_days(2) == "дня"
    assert chronicle._plural_days(5) == "дней"
    assert chronicle._plural_days(11) == "дней"
    assert chronicle._plural_days(21) == "день"


# ---------- Ф68 «день рождения» ----------

def test_birthday_age_and_countdown():
    out = chronicle.birthday(dt.date(2026, 11, 24))
    assert "16 ноября 2026" in out
    assert "Мне 8 дней" in out
    assert "До следующего — 357 дней" in out
    # на самом дне рождения — праздник, а не отсчёт до следующего
    # (2027 не високосный: 365 дней, 2028 — високосный: до него 366)
    out = chronicle.birthday(dt.date(2027, 11, 16))
    assert "Сегодня" in out and "365 дней" in out


def test_birthday_is_history_fact_not_fantasy():
    """День рождения — из книги дома (мастер-ТЗ §22: канон 16.11),
    не выдумка личности: якорь стоит на факте канона."""
    assert chronicle.BIRTH == dt.date(2026, 11, 16)
    assert "канон" in chronicle.birthday(dt.date(2026, 11, 24))


# ---------- Ф69 «мечты» ----------

def test_dreams_honest_from_live_fronts(home, monkeypatch):
    out = chronicle.dreams()
    assert "двигать руками" in out and "кнопка 91" in out
    # падеж живого вывода — «кнопкой 93» (урок дня-9: падеж убивает якоря)
    assert "вспоминать ПО СМЫСЛУ" in out and "кнопкой 93" in out
    assert "заговорить русским голосом" in out       # голоса нет в песочнице
    assert "DOM" in out and "QLoRA" in out

    def fake_alive():
        return True

    from core import embedder
    monkeypatch.setattr(embedder, "alive", fake_alive)
    out = chronicle.dreams()
    assert "смысловая память уже моя" in out          # сбывшаяся — названа


def test_dreams_fulfilled_motorika(home, monkeypatch):
    (config.DATA_DIR / "hands_enabled.json").write_text("{}", encoding="utf-8")
    out = chronicle.dreams()
    assert "руки уже мои" in out


# ---------- Ф70 «наш первый разговор» ----------

def _write_session(home, name, turns, mtime):
    d = home / "data" / "dialog"
    d.mkdir(parents=True, exist_ok=True)
    p = d / name
    p.write_text(json.dumps({"turns": turns}, ensure_ascii=False),
                 encoding="utf-8")
    import os
    os.utime(p, (mtime, mtime))


def test_first_talk_shows_earliest(home):
    _write_session(home, "session_new.json",
                   [{"role": "user", "text": "привет снова",
                     "ts": "25.11 10:00"},
                    {"role": "assistant", "text": "и снова здравствуй"}],
                   mtime=2000000000)
    _write_session(home, "session_old.json",
                   [{"role": "user", "text": "Марфа, ты меня слышишь?",
                     "ts": "16.11 21:04"},
                    {"role": "assistant", "text": "Слышу. Меня зовут "
                     "Марфа, и я теперь живу здесь."},
                    {"role": "user", "text": "третья реплика"}],
                   mtime=1000000000)
    out = chronicle.first_talk()
    assert "НАШ ПЕРВЫЙ РАЗГОВОР" in out
    assert "16.11 21:04" in out
    assert "Ты сказал: «Марфа, ты меня слышишь?»" in out
    assert "Я ответила" in out and "живу здесь" in out
    assert "реплик в нём: 3" in out
    assert "привет снова" not in out            # свежая сессия не в деле


def test_first_talk_long_phrase_capped(home):
    _write_session(home, "session_one.json",
                   [{"role": "user", "text": "очень " * 60, "ts": "16.11 21:00"}],
                   mtime=1000000000)
    out = chronicle.first_talk()
    assert "…" in out                            # длинная реплика подрезана


def test_first_talk_empty_archive_honest(home):
    out = chronicle.first_talk()
    assert "не сохранился" in out and "16 ноября 2026" in out


# ---------- проводка агента ----------

@pytest.fixture()
def agent(home, monkeypatch):
    from core.agent import Agent
    from core.memory import Memory
    return Agent(memory=Memory(data_dir=Path(config.DATA_DIR)),
                 doctrine="Тестовая доктрина")


def test_agent_chronicle_commands(agent, monkeypatch):
    monkeypatch.setattr(chronicle, "growth", lambda days=7: "РОСТ: неделя")
    monkeypatch.setattr(chronicle, "journey",
                        lambda memory=None: "МЫ ВМЕСТЕ: история")
    monkeypatch.setattr(chronicle, "birthday", lambda now=None: "ДЕНЬ РОЖДЕНИЯ")
    monkeypatch.setattr(chronicle, "dreams", lambda: "МЕЧТЫ: фронты")
    monkeypatch.setattr(chronicle, "first_talk", lambda: "ПЕРВЫЙ РАЗГОВОР")
    checks = (
        ("чем ты выросла", "growth", "РОСТ"),
        ("Марфа, сколько мы вместе?", "journey", "МЫ ВМЕСТЕ"),
        ("когда твой день рождения", "birthday", "ДЕНЬ РОЖДЕНИЯ"),
        ("о чём ты мечтаешь", "dreams", "МЕЧТЫ"),
        ("наш первый разговор", "first_talk", "ПЕРВЫЙ РАЗГОВОР"),
    )
    for text, tool, marker in checks:
        r = agent.handle(text)
        assert r.source == "python" and r.tool_used == tool, text
        assert marker in r.text


def test_identity_knows_chronicle():
    from core import identity
    joined = "; ".join(identity.FAST_COMMANDS)
    for piece in ("чем ты выросла", "сколько мы вместе", "день рождения",
                  "о чём ты мечтаешь", "наш первый разговор"):
        assert piece in joined
