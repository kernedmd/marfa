# -*- coding: utf-8 -*-
"""Тесты круга 9 «Смыслы и архив» (Ф51–Ф55, день-9, 24.11): слуга-эмбеддер,
смысловая память (сухой режим, фейковый слуга), дневник за дату, визитка
Создателя, экспорт разговора."""
import datetime as dt
import hashlib
import json

import pytest

from core import config, diaryday, semantic


@pytest.fixture()
def home(tmp_path, monkeypatch):
    data = tmp_path / "data"
    monkeypatch.setattr(config, "HOME_DIR", tmp_path)
    monkeypatch.setattr(config, "DATA_DIR", data)
    monkeypatch.setattr(config, "VECTORS_DIR", data / "vectors")
    monkeypatch.setattr(config, "EXPORTS_DIR", data / "exports")
    for const, fname in (
            ("RULES_FILE", "rules.json"),
            ("HABITS_FILE", "habits.json"),
            ("BIRTHDAYS_FILE", "birthdays.json"),
            ("MOODLOG_FILE", "mood.json")):
        monkeypatch.setattr(config, const, data / fname)
    yield data


TODAY = dt.date(2026, 11, 24)


# ---------- Ф52 смысловая память (фейковый слуга) ----------

def _fake_embed(texts):
    """Детерминированный «смысл»: слова хешируются в ФИКСИРОВАННУЮ
    размерность (64) — векторы стабильны между вызовами (запрос отдельно,
    куски отдельно), косинус честно растёт от общих слов."""
    out = []
    for t in texts:
        v = [0.0] * 64
        for word in str(t).lower().split():
            word = word.strip(".,!?;:()\"'-")
            if not word:
                continue
            dim = int(hashlib.md5(word.encode("utf-8")).hexdigest(), 16) % 64
            v[dim] += 1.0
        out.append(v)
    return out


@pytest.fixture()
def fake_servant(monkeypatch):
    """Слуга «жив» и векторизует мешком слов — якоря честно считают
    косинус, а не притворяются."""
    from core import embedder
    monkeypatch.setattr(embedder, "alive", lambda: True)
    monkeypatch.setattr(embedder, "embed", _fake_embed)
    return embedder


def _make_soul(home):
    (home / "diary").mkdir(parents=True, exist_ok=True)
    (home / "diary" / "2026-11-22.md").write_text(
        "Мы уезжали к морю на электричке.\n\nВолны были высокие, "
        "а чайки наглые.\n", encoding="utf-8")
    (home / "diary" / "2026-11-23.md").write_text(
        "Чинили старт мозга: кавычки убили сервер.\n\nКнопка 92 лечит "
        "конфиг честно.\n", encoding="utf-8")
    home.mkdir(parents=True, exist_ok=True)
    (home / "rules.json").write_text(json.dumps({"rules": [
        {"n": 1, "text": "Молчание — не разрешение."},
        {"n": 2, "text": "Цифры или ничего."},
    ]}, ensure_ascii=False), encoding="utf-8")


def test_semantic_reindex_and_search(home, fake_servant):
    _make_soul(home)
    out = semantic.reindex()
    assert "смыслы индексированы" in out
    assert "кусков" in out
    # «волны чайки» по смыслу ложатся на вечер у моря (2 общих слова
    # из 4 — косинус честно выше порога; кавычки и кнопки — мимо)
    found = semantic.search("волны чайки")
    assert found
    assert found[0]["sim"] >= 0.35
    assert "Волны" in found[0]["text"] or "Чайки" in found[0]["text"]
    text = semantic.render("волны чайки")
    assert "ПО СМЫСЛУ" in text and "похожесть" in text


def test_semantic_rules_found(home, fake_servant):
    _make_soul(home)
    semantic.reindex()
    found = semantic.search("молчание разрешение")
    assert any("правило" in r["source"] for r in found)


def test_semantic_cache_saves_vectors(home, fake_servant, monkeypatch):
    _make_soul(home)
    calls = []
    real = _fake_embed

    def counting(texts):
        calls.append(len(texts))
        return real(texts)

    monkeypatch.setattr(fake_servant, "embed", counting)
    semantic.reindex()
    first = len(calls)
    out = semantic.reindex()               # второй прогон — всё из кэша
    assert "0 новых векторов" in out
    assert len(calls) == first             # слуга не зря не будился


def test_semantic_servant_asleep_honest(home):
    _make_soul(home)
    out = semantic.render("отпуск")
    # индекса нет → честно про индексацию; поднимем индекс без слуги нельзя
    assert "не читала душу" in out or "переиндексируй" in out


def test_semantic_asleep_after_index(home, monkeypatch):
    from core import embedder
    _make_soul(home)
    monkeypatch.setattr(embedder, "alive", lambda: True)
    monkeypatch.setattr(embedder, "embed", _fake_embed)
    semantic.reindex()
    monkeypatch.setattr(embedder, "alive", lambda: False)   # слуга уснул
    out = semantic.render("море")
    assert "спит" in out and "93_embedder" in out
    assert "что я говорил" in out           # дословные органы предложены


def test_semantic_nothing_found_honest(home, fake_servant):
    _make_soul(home)
    semantic.reindex()
    out = semantic.render("квантовая физика кварки")
    assert "не нашлось" in out


def test_semantic_broken_index_is_empty(home, fake_servant):
    semantic._index_file().parent.mkdir(parents=True, exist_ok=True)
    semantic._index_file().write_text("не json", encoding="utf-8")
    assert "не читала душу" in semantic.render("что угодно")


# ---------- Ф51 слуга-эмбеддер: орган ----------

def test_embedder_asleep_exception(home):
    from core import embedder
    with pytest.raises(embedder.EmbedderAsleep):
        embedder.embed(["текст"])          # порт мёртв — честный отказ


def test_embedder_empty_batch_is_not_error(home):
    from core import embedder
    assert embedder.embed([]) == []


def test_embedder_button_exists():
    from pathlib import Path
    btn = Path(__file__).resolve().parent.parent / "scripts" / "93_embedder.bat"
    assert btn.is_file()
    text = btn.read_text(encoding="utf-8")
    assert "8087" in text or "bge-m3" in text
    assert "вспомни по смыслу" in text     # кнопка учит первой фразе


def test_embedder_find_model_pattern(home):
    from core import embedder
    models = home.parent / "models"
    models.mkdir(exist_ok=True)
    (models / "bge-m3-Q8_0.gguf").write_bytes(b"x")
    monkeypatch_target = config
    import core.config as _c
    saved = _c.MODELS_DIR
    _c.MODELS_DIR = models
    try:
        assert embedder.find_model() is not None
        assert embedder.find_model().name == "bge-m3-Q8_0.gguf"
    finally:
        _c.MODELS_DIR = saved


# ---------- Ф53 дневник за дату ----------

def test_diaryday_parse_dates():
    assert diaryday.parse_date("вчера", TODAY) == dt.date(2026, 11, 23)
    assert diaryday.parse_date("позавчера", TODAY) == dt.date(2026, 11, 22)
    assert diaryday.parse_date("20 ноября", TODAY) == dt.date(2026, 11, 20)
    assert diaryday.parse_date("20.11", TODAY) == dt.date(2026, 11, 20)
    assert diaryday.parse_date("20.11.2025", TODAY) == dt.date(2025, 11, 20)
    assert diaryday.parse_date("2026-01-05", TODAY) == dt.date(2026, 1, 5)
    assert diaryday.parse_date("31 февраля", TODAY) is None    # не выдумываем
    assert diaryday.parse_date("какой-то текст", TODAY) is None


def test_diaryday_render_and_missing(home):
    (home / "diary").mkdir(parents=True, exist_ok=True)
    (home / "diary" / "2026-11-22.md").write_text(
        "# Вечер\n\nМоре, чайки, электричка.\n", encoding="utf-8")
    out = diaryday.render(dt.date(2026, 11, 22))
    assert "ВЕЧЕР 22.11.2026" in out
    assert "чайки" in out
    miss = diaryday.render(dt.date(2026, 11, 20))
    assert "нет" in miss and "2026-11-22" in miss   # подсказка что записано


def test_diaryday_dispatch(home, monkeypatch):
    (home / "diary").mkdir(parents=True, exist_ok=True)
    # «вчера» считает живой орган по живым часам — пишем файл
    # настоящего вчера, не константы теста
    yesterday = (dt.date.today() - dt.timedelta(days=1)).isoformat()
    (home / "diary" / (yesterday + ".md")).write_text("Чинили дом.\n",
                                                    encoding="utf-8")
    from core.agent import Agent

    class _NoBrain:
        def ask_json(self, *a, **k):
            raise AssertionError("мозг не должен просыпаться")

    agent = Agent(brain=_NoBrain(), memory=None, doctrine="")
    r = agent.handle("что было вчера")
    assert r.tool_used == "diaryday" and "Чинили дом" in r.text
    r = agent.handle("что было 31 февраля")
    assert "не разобрала дату" in r.text
    r = agent.handle("что было")
    assert r.tool_used != "diaryday"      # голое «что было» — дайджест, не дата


# ---------- Ф54 визитка Создателя ----------

def test_personcard_full_and_empty(home):
    from core import personcard
    empty = personcard.render()
    assert "почти пусто" in empty
    home.mkdir(parents=True, exist_ok=True)
    (home / "rules.json").write_text(json.dumps({"rules": [
        {"n": 1, "text": "Молчание — не разрешение."}]},
        ensure_ascii=False), encoding="utf-8")
    (home / "habits.json").write_text(json.dumps({"habits": [
        {"name": "вода"}], "marks": {}}), encoding="utf-8")
    (home / "mood.json").write_text(json.dumps([
        {"mood": "отличное", "ts": "24.11 09:00"}], ensure_ascii=False),
        encoding="utf-8")
    card = personcard.render()
    assert "ЧТО Я ПОМНЮ О СОЗДАТЕЛЕ" in card
    assert "законов нашего дома" in card
    assert "вода" in card
    assert "отличное" in card
    assert "не выдумала" in card


def test_personcard_dispatch(home, monkeypatch):
    from core.agent import Agent
    from core import personcard

    class _NoBrain:
        def ask_json(self, *a, **k):
            raise AssertionError("мозг не должен просыпаться")

    agent = Agent(brain=_NoBrain(), memory=None, doctrine="")
    r = agent.handle("что ты помнишь обо мне")
    assert r.tool_used == "personcard"
    # пустой дом честно пуст — визитка не выдумывает Создателя
    assert "почти пусто" in r.text


# ---------- Ф55 сохрани разговор ----------

def _make_dialog(home):
    dlg = home / "dialog"
    dlg.mkdir(parents=True, exist_ok=True)
    (dlg / "session_web.json").write_text(json.dumps({
        "session": "web",
        "turns": [
            {"role": "user", "text": "Привет, Марфа!", "ts": "24.11 10:00"},
            {"role": "assistant", "text": "Привет! Рад тебя слышать.",
             "ts": "24.11 10:00", "meta": {"secs": 41.5, "src": "brain"}},
            {"role": "user", "text": "Как дела?", "ts": "24.11 10:05"},
        ]}, ensure_ascii=False), encoding="utf-8")
    return dlg


def test_dialogexport_export_and_list(home):
    from core import dialogexport
    _make_dialog(home)
    out = dialogexport.export()
    assert "сохранён" in out and "3 реплик" in out
    files = list((home / "exports").glob("dialog_*.md"))
    assert len(files) == 1
    text = files[0].read_text(encoding="utf-8")
    assert "Илья" in text and "Марфа" in text
    assert "Привет, Марфа!" in text
    assert "41,5 с" in text or "41.5 с" in text
    listing = dialogexport.list_exports()
    assert "СОХРАНЁННЫЕ РАЗГОВОРЫ" in listing
    assert files[0].name in listing


def test_dialogexport_empty_and_broken(home):
    from core import dialogexport
    assert "нечего" in dialogexport.export() or "не говорили" in \
        dialogexport.export()
    dlg = home / "dialog"
    dlg.mkdir(parents=True, exist_ok=True)
    (dlg / "session_bad.json").write_text("не json", encoding="utf-8")
    out = dialogexport.export()
    assert "пуста" in out or "нечего" in out or "не говорили" in out
    assert "сохранённых разговоров нет" in dialogexport.list_exports()


def test_dialogexport_dispatch(home, monkeypatch):
    _make_dialog(home)
    from core.agent import Agent

    class _NoBrain:
        def ask_json(self, *a, **k):
            raise AssertionError("мозг не должен просыпаться")

    agent = Agent(brain=_NoBrain(), memory=None, doctrine="")
    r = agent.handle("сохрани наш разговор")
    assert r.tool_used == "dialogexport" and "сохранён" in r.text
    r = agent.handle("разговоры")
    assert r.tool_used == "dialogexport"


# ---------- Ф52 проводка: смыслы в диспетчере ----------

def test_semantic_dispatch(home, fake_servant, monkeypatch):
    _make_soul(home)
    from core.agent import Agent

    class _NoBrain:
        def ask_json(self, *a, **k):
            raise AssertionError("мозг не должен просыпаться")

    agent = Agent(brain=_NoBrain(), memory=None, doctrine="")
    r = agent.handle("переиндексируй смыслы")
    assert r.tool_used == "semantic"
    assert "индексированы" in r.text
    r = agent.handle("вспомни по смыслу море")
    assert r.tool_used == "semantic"
    assert "ПО СМЫСЛУ" in r.text or "не нашлось" in r.text
    # дословное «вспомни» живёт при своих смыслах
    r = agent.handle("вспомни море")
    assert r.tool_used == "recall"
