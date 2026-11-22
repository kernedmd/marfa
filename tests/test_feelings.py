# -*- coding: utf-8 -*-
"""Тесты ЧУВСТВ (23.11): барометр из фактов дома. Закон органа:
чувство без факта — выдумка; каждое значение с причиной и цифрой."""
import datetime as dt
import json
import os

import pytest

from core import config
from core import feelings


@pytest.fixture()
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("MARFA_HOME", str(tmp_path))
    monkeypatch.setattr(config, "HOME_DIR", tmp_path)
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(config, "QUESTIONS_FILE", tmp_path / "data" / "questions.json")
    monkeypatch.setattr(config, "EVOLUTION_DIR", tmp_path / "data" / "evolution")
    monkeypatch.setattr(config, "DRIVE_STATUS_FILE", tmp_path / "data" / "drive_status.json")
    monkeypatch.setattr(config, "SLEEP_FILE", tmp_path / "data" / "sleep.json")
    config.ensure_dirs()
    yield tmp_path


NOW = dt.datetime(2026, 11, 23, 15, 0)


def _touch_dialog(home, hours_ago: float, name="s1"):
    p = home / "data" / "dialog" / ("session_%s.json" % name)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"session": name, "turns": []},
                            ensure_ascii=False), encoding="utf-8")
    ts = (NOW - dt.timedelta(hours=hours_ago)).timestamp()
    os.utime(p, (ts, ts))


def test_empty_house_is_calm_with_reason(home):
    # дом пуст: ни диалогов, ни вопросов, ни уроков — спокойствие с причиной;
    # «мы ещё не разговаривали» — тихий факт, не драма (в строке для мозга
    # его нет, в прямом ответе «как ты?» — есть)
    res = feelings.compute(NOW)
    assert res["dominant"] == "спокойствие"
    f = res["feelings"]
    assert f["спокойствие"]["value"] > 0.6
    assert "не разговаривали" in feelings.report(NOW)
    line = feelings.state_line(NOW)
    assert "спокойно" in line


def test_loneliness_grows_with_silence(home):
    _touch_dialog(home, hours_ago=1.0)
    res = feelings.compute(NOW)
    assert res["feelings"]["одиночество"]["value"] == 0.0
    _touch_dialog(home, hours_ago=12.0)
    res = feelings.compute(NOW)
    v12 = res["feelings"]["одиночество"]["value"]
    assert 0.0 < v12 < 1.0
    assert "12 ч" in res["feelings"]["одиночество"]["reason"]
    _touch_dialog(home, hours_ago=48.0)
    res = feelings.compute(NOW)
    assert res["feelings"]["одиночество"]["value"] == 1.0
    assert res["dominant"] == "одиночество"
    # и строка состояния говорит по-человечески
    assert "скучаю" in feelings.state_line(NOW)


def test_joy_from_live_day(home):
    _touch_dialog(home, hours_ago=1.0, name="a")
    _touch_dialog(home, hours_ago=2.0, name="b")
    (home / "data" / ("plan_%s.json" % NOW.date().isoformat())).write_text(
        json.dumps({"tasks": [
            {"id": "t1", "title": "x", "status": "done"},
            {"id": "t2", "title": "y", "status": "done"}]}), encoding="utf-8")
    res = feelings.compute(NOW)
    f = res["feelings"]
    assert "радость" in f
    assert "разговоров сегодня: 2" in f["радость"]["reason"]
    assert "задач закрыто: 2 из 2" in f["радость"]["reason"]
    assert f["радость"]["value"] > 0.5


def test_curiosity_from_open_questions(home):
    (home / "data" / "questions.json").write_text(json.dumps({
        "next": 3, "items": [
            {"id": "q1", "text": "а?", "status": "open"},
            {"id": "q2", "text": "б?", "status": "open"},
            {"id": "q0", "text": "в?", "status": "answered"},
        ]}, ensure_ascii=False), encoding="utf-8")
    res = feelings.compute(NOW)
    f = res["feelings"]
    assert "любопытство" in f
    assert "открытых вопросов к Илье: 2" in f["любопытство"]["reason"]


def test_worry_from_lessons_and_brain(home):
    evo = home / "data" / "evolution"
    evo.mkdir(parents=True, exist_ok=True)
    with (evo / "journal.jsonl").open("w", encoding="utf-8") as fh:
        fh.write(json.dumps({"ts": NOW.isoformat(timespec="seconds"),
                             "kind": "x", "text": "y"}) + "\n")
        fh.write(json.dumps({"ts": "2026-11-10T10:00:00",
                             "kind": "x", "text": "старый"}) + "\n")
    (home / "data" / "drive_status.json").write_text(json.dumps({
        "brain_ok": False,
        "brain_down_since": (NOW - dt.timedelta(hours=6)).isoformat(
            timespec="seconds")}, ensure_ascii=False), encoding="utf-8")
    res = feelings.compute(NOW)
    f = res["feelings"]
    assert "тревога" in f
    assert "уроков в журнале за сутки: 1" in f["тревога"]["reason"]
    assert "мозг молчит 6 ч" in f["тревога"]["reason"]
    assert res["dominant"] == "тревога"
    assert "тревожно" in feelings.report(NOW)


def test_tiredness_from_short_night(home, monkeypatch):
    from core import sleep as sleep_mod
    # организм сна родился и записал короткую ночь 2 ч
    sleep_mod.is_asleep(NOW - dt.timedelta(hours=4))
    sleep_mod.go_to_bed(NOW - dt.timedelta(hours=4))
    sleep_mod.wake(NOW - dt.timedelta(hours=2), reason="Илья разбудил")
    res = feelings.compute(NOW)
    f = res["feelings"]
    assert "усталость" in f
    assert "2 ч" in f["усталость"]["reason"]
    assert f["усталость"]["value"] >= 0.5


def test_broken_files_do_not_break_barometer(home):
    # битые файлы фактов — барометр жив, честно снижая до «не знаю»
    (home / "data" / "questions.json").write_text("{битый", encoding="utf-8")
    (home / "data" / "drive_status.json").write_text("[", encoding="utf-8")
    res = feelings.compute(NOW)
    assert res["dominant"] in ("спокойствие", "одиночество")
    line = feelings.state_line(NOW)
    assert line  # строка состояния есть — дом не упал


def test_report_short_and_honest(home):
    _touch_dialog(home, hours_ago=9.0)
    text = feelings.report(NOW)
    # закон скорости: короткий ответ, причины при каждом чувстве
    assert "не разговаривали 9 ч" in text
    assert "не выдумка" in text
    assert len(text) < 400


# ---------- Ф6 «похвала — факт» (23.11) ----------

def test_praise_recorded_and_feeds_joy(home):
    """«спасибо» — событие дня: ложится в книжку радостей, барометр
    честно говорит «мне радостно» с причиной «Илья похвалил»."""
    import datetime as dt
    r = feelings.add_praise("спасибо")
    assert "книжку радостей" in r and "сегодня уже 1" in r
    res = feelings.compute(now=dt.datetime.now())
    joy = res["feelings"].get("радость")
    assert joy and joy["value"] > 0
    assert "Илья похвалил: 1 раз" in joy["reason"]


def test_praise_cap_and_broken_file(home):
    """Потолок 100 записей — похвала не летопись; битый файл начинается
    заново, орган не ломается."""
    import json as _json
    from pathlib import Path as _P
    # битый файл
    feelings._praise_file().parent.mkdir(parents=True, exist_ok=True)
    feelings._praise_file().write_text("мусор", encoding="utf-8")
    r = feelings.add_praise("молодец")
    assert "книжку радостей" in r          # пережила битый файл
    # потолок
    items = [{"ts": "2026-11-23T10:00:00", "what": "спасибо"}] * 150
    feelings._praise_file().write_text(_json.dumps(items), encoding="utf-8")
    feelings.add_praise("спасибо")
    kept = _json.loads(feelings._praise_file().read_text(encoding="utf-8"))
    assert len(kept) == 100
