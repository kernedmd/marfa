# -*- coding: utf-8 -*-
# =================================================================
# КРУГ 33 «АУДИТ ДИСПЕТЧЕРА» (день-18, 28.11.2026, часть 3):
# разбор agent.py по аудиту Создателя — 88 пунктов, верификация
# каждым жёстким якорем. Пункт аудита = якорь, который не даёт
# болезни вернуться. Паттерн песочницы — test_krug26_circle.
# =================================================================
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import (agent, answercache, config, customtools, creator_gate,  # noqa: E402
                  progress, repair)
from core.agent import Agent  # noqa: E402


# ---------------------------------------------------------------
# песочница круга (паттерн test_krug26_circle)
# ---------------------------------------------------------------
@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "HOME_DIR", tmp_path)
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(config, "LOGS_DIR", tmp_path / "logs")
    monkeypatch.setattr(config, "PATCHES_DIR", tmp_path / "data" / "patches")
    monkeypatch.setattr(config, "REPAIR_LOG_FILE",
                        tmp_path / "logs" / "repair_log.jsonl")
    monkeypatch.setattr(config, "GUARD_LOG_FILE",
                        tmp_path / "logs" / "guard_log.jsonl")
    monkeypatch.setattr(config, "CANARIES_FILE",
                        tmp_path / "data" / "canaries.json")
    monkeypatch.setattr(repair, "ensure_server",
                        lambda wait_secs=None: (True, "кодер на посту (шов)"))
    monkeypatch.setattr(repair, "release", lambda: "кодер лёг (шов)")
    monkeypatch.setattr(customtools, "_scan_cache",
                        {"ts": 0.0, "tools": []})
    progress.reset()
    return tmp_path


class FakeBrain:
    def __init__(self, answer="живой ответ мозга по существу",
                 decision=None):
        self.calls = 0
        self.seen = []
        self.answer = answer
        self.decision = decision

    def ask_json(self, text, *a, **kw):
        self.calls += 1
        self.seen.append(text)
        if self.decision is not None:
            return dict(self.decision)
        return {"answer": self.answer}


class FakeMemory:
    """Память-двойник: помнит, что в неё легло."""

    def __init__(self):
        self.items = []

    def remember(self, text, *a, **kw):
        self.items.append(text)
        return True

    def recall(self, *a, **kw):
        return []


def _agent(brain=None, memory=None):
    return Agent(brain=brain or FakeBrain(),
                 memory=memory if memory is not None else FakeMemory(),
                 doctrine="Тестовая доктрина круга 33")


# ================================================================
# К2 «ДВОЙНАЯ СМЕРТЬ ПОДРОБНЕЕ» — имя больше не глотает маршрут
# ================================================================
def test_k2_name_prefixed_more_detail(home):
    """«Марфа, подробнее» доезжает до маршрута Ф180: прошлый ответ
    кладётся в ход сам, мозг получает раскрытие, а не отмашку."""
    brain = FakeBrain()
    history = [{"role": "assistant",
                "content": "Снился тёплый дом и голос Создателя."}]
    _agent(brain).handle("Марфа, подробнее", history=history)
    assert brain.calls == 1
    assert "Раскрой свой предыдущий ответ" in brain.seen[0]
    assert "Снился тёплый дом" in brain.seen[0]


def test_k2_helper_strips_all_forms():
    for src, want in (("Марфа, подробнее", "подробнее"),
                      ("Марфушка, время", "время"),
                      ("время, Марфа", "время"),
                      ("но что там", "что там")):
        assert agent._without_wake_name(src) == want, src


# ================================================================
# К3 «ВОПРОС О ПАТЧЕ — НЕ ПРИКАЗ» — «патч 0002?» не применяет
# ================================================================
def test_k3_bare_number_with_question_confirms(home):
    r = _agent().handle("патч 0002?")
    assert r.tool_used == "patch_confirm"
    assert "вопрос" in r.text.lower()
    assert "примени патч" in r.text.lower()


def test_k3_hash_number_with_question_confirms(home):
    r = _agent().handle("№2?")
    assert r.tool_used == "patch_confirm"


def test_k3_bare_without_question_still_applies(home):
    """Ф184 жива: ответ на вопрос дома «внедрить какой патч?» —
    голый номер без «?» — выбор, идёт в применение."""
    r = _agent().handle("патч 0002")
    assert r.tool_used == "patch_apply"


# ================================================================
# К4 «ВОПРОС О СНЕ НЕ БУДИТ» — метрика сна жива
# ================================================================
def test_k4_sleep_question_does_not_wake(home, monkeypatch):
    woke = []
    monkeypatch.setattr(agent.sleep, "wake_on_message",
                        lambda *a, **kw: woke.append(1))
    a = _agent()
    # ответ — у старого честного маршрута (sleep.status_text, tool «sleep»):
    # КРУГ 33 не плодит тени — исправляет только ПРОБУЖДЕНИЕ
    r = a.handle("ты спишь?")
    assert r.tool_used == "sleep"
    assert not woke, "вопрос о сне не будит организм"
    # «сколько ты не спала» — метрика честна через орган uptime («не сплю
    # с HH:MM»): маршрут точный (он и был), НО теперь не будит
    r2 = a.handle("сколько ты не спала")
    assert r2.tool_used == "uptime"
    assert not woke


def test_k4_bed_command_does_not_wake(home, monkeypatch):
    """«спи» — укладывание без пробуждения: тряска состояния отменена."""
    woke = []
    monkeypatch.setattr(agent.sleep, "wake_on_message",
                        lambda *a, **kw: woke.append(1))
    monkeypatch.setattr(agent.sleep, "go_to_bed",
                        lambda reason="": "легла (шов)")
    r = _agent().handle("спи")
    assert not woke
    assert r.tool_used == "sleep"


def test_k4_morning_report_not_shadowed(home, monkeypatch):
    """«Доброе утро, как спалось?» — утренний отчёт сна, не сон-вопрос:
    регекс сна строг к полным словам («спалось» — не «спал»)."""
    monkeypatch.setattr(agent.sleep, "wake_on_message",
                        lambda *a, **kw: None)
    r = _agent().handle("Доброе утро, как спалось?")
    assert r.tool_used == "sleep"


# ================================================================
# К6 «КАЛИТКА — FAIL-CLOSED» — слово не едет в мозг при крахе
# ================================================================
def test_k6_gate_crash_keeps_codeword_from_brain(home, monkeypatch):
    def _boom(text):
        raise RuntimeError("без .env не выжила")
    monkeypatch.setattr(creator_gate, "check", _boom)
    monkeypatch.setattr(creator_gate, "_codeword", lambda: "абракадабра")
    brain = FakeBrain()
    a = Agent(brain=brain, memory=FakeMemory(),
              doctrine="доктрина")
    r = a.handle("абракадабра статус")
    assert brain.calls == 0, "слово не едет в мозг"
    assert r.tool_used == "creator_gate"
    assert "споткнулась" in r.text


def test_k6_gate_crash_without_word_lets_turn_live(home, monkeypatch):
    """Крах калитки без кодового слова — дом живёт (честная деградация)."""
    def _boom(text):
        raise RuntimeError("пусто")
    monkeypatch.setattr(creator_gate, "check", _boom)
    monkeypatch.setattr(creator_gate, "_codeword", lambda: "")
    brain = FakeBrain()
    a = Agent(brain=brain, memory=FakeMemory(), doctrine="доктрина")
    a.handle("как дела?")
    assert brain.calls == 1


def test_k6_gate_command_failure_is_honest_text(home, monkeypatch):
    """К6 в калитке: упавшая команда за словом — текст, не исключение."""
    monkeypatch.setattr(creator_gate, "_codeword", lambda: "абракадабра")
    monkeypatch.setattr(creator_gate, "_cmd_status",
                        lambda: (_ for _ in ()).throw(RuntimeError("упала")))
    ok, reply = creator_gate.check("абракадабра статус")
    assert ok and "споткнулась" in reply


# ================================================================
# К7 «ПЕРВОЕ ЧИСЛО ИЗ ТЕКСТА» — запрет больше не гадает
# ================================================================
def test_k7_forbidden_number_not_guessed(home):
    """«не применяй 2, примени 3» у мозга — номер НЕ выдёргивается
    первым встречным: дом спрашивает Создателя и ждёт."""
    a = _agent()
    r = a._act({"tool": "apply_patch",
                "args": {"text": "не применяй 2, примени 3"}})
    assert r.tool_used == "apply_patch"
    assert "внедрить какой патч" in r.text


def test_k7_clean_patch_reference_is_taken(home, monkeypatch):
    """Чистая ссылка в тексте («патч 0002») работает как была (Ф184)."""
    monkeypatch.setattr(repair, "self_apply", lambda n: "ВНЕДРЁН %d" % n)
    a = _agent()
    for args in ({"text": "патч 0002"}, {"query": "№0002"},
                 {"value": "0002"}, {"patch": 2}, {"n": "0002"}):
        r = a._act({"tool": "apply_patch", "args": args})
        assert "ВНЕДРЁН 2" in r.text, args


# ================================================================
# К9 «МЕНЯ ЗОВУТ УСТАЛ» — слово не становится именем
# ================================================================
def test_k9_lowercase_word_is_not_a_name(home):
    from core import people
    a = _agent()
    r = a.handle("меня зовут устал")
    assert r.tool_used == "introduce"
    assert "заглавной" in r.text.lower()
    assert people.get_name() is None


def test_k9_capitalized_name_recorded(home):
    from core import people
    a = _agent()
    r = a.handle("меня зовут Илья")
    assert r.tool_used == "introduce"
    assert people.get_name() == "Илья"


def test_k9_en_dash_name_recorded(home):
    """С4: «я – Илья» (среднее тире) — живая форма."""
    from core import people
    a = _agent()
    r = a.handle("я – Илья")
    assert r.tool_used == "introduce"
    assert people.get_name() == "Илья"


# ================================================================
# К10 «УРОКИ НЕ РВУТ KV-КЭШ» — статика стабильна при любом журнале
# ================================================================
def test_k10_lessons_out_of_static(home, monkeypatch):
    """Уроки — в подвижном хвосте: статичный префикс не меняется от
    хода к ходу, даже когда журнал сыплет уроками (Ф77 цел)."""
    from evolution import lessons
    a = _agent()
    monkeypatch.setattr(lessons, "prompt_lines",
                        lambda: ["R1: путь — подпапка, не корень"])
    static_before = a._static_system()
    assert "ПРАВИЛА УРОКОВ" not in static_before
    monkeypatch.setattr(lessons, "prompt_lines",
                        lambda: ["R1: путь — подпапка, не корень",
                                 "R9: урок второй — префикс стабилен"])
    static_after = a._static_system()
    assert static_before == static_after, \
        "урок в журнале не меняет статичный префикс"
    tail = a._turn_context("привет")
    assert "ПРАВИЛА УРОКОВ" in tail
    assert "R9: урок второй" in tail


# ================================================================
# К11 «КЭШ СЛЕП К КОНТЕКСТУ» — разговорные фразы мимо кэша
# ================================================================
def test_k11_talk_words_skip_cache(home, tmp_path):
    answercache.store("да", "старый ответ чужого диалога")
    brain = FakeBrain()
    r = _agent(brain).handle("да")
    assert brain.calls == 1, "«да» не воспроизводит прошлый ответ"
    assert r.text != "старый ответ чужого диалога"


def test_k11_full_question_still_cached(home):
    """Полноценный вопрос кэшируется, как и было (Ф41 жив)."""
    answercache.store("сколько стоит дом на луне", "из кэша")
    brain = FakeBrain()
    r = _agent(brain).handle("сколько стоит дом на луне")
    assert r.tool_used == "answercache"
    assert "из кэша" in r.text
    assert "Помню" in r.text


# ================================================================
# В1 «ЗАПОМНИ!» — восклицание не падает в память
# ================================================================
def test_v1_bang_not_memory(home):
    mem = FakeMemory()
    r = _agent(memory=mem).handle("запомни!")
    assert r.tool_used == "remember"
    assert "что запомнить" in r.text.lower()
    assert mem.items == []
    r2 = _agent(memory=mem).handle("помни?")
    assert "что запомнить" in r2.text.lower()
    assert mem.items == []


def test_v2_multiline_dictation_lives(home):
    """В2: многострочная диктовка не теряется (DOTALL)."""
    mem = FakeMemory()
    r = _agent(memory=mem).handle("запомни:\nпервая строка\nвторая строка")
    assert r.tool_used == "remember"
    assert len(mem.items) == 1
    assert "первая строка" in mem.items[0]
    assert "вторая строка" in mem.items[0]


# ================================================================
# В21 «ВСПОМНИ X ПО СМЫСЛУ» — живой порядок слов
# ================================================================
def test_v21_tail_order_semantic(home, monkeypatch):
    seen = []
    from core import semantic
    monkeypatch.setattr(semantic, "render", lambda q: seen.append(q) or "смысл")
    r = _agent().handle("вспомни отпуск по смыслу")
    assert r.tool_used == "semantic"
    assert seen and seen[0] == "отпуск"


# ================================================================
# В5 «ЧТО БЫЛО НА ПРОШЛОЙ НЕДЕЛЕ» — вопрос о прошлом не съеден
# ================================================================
def test_v5_natural_past_goes_to_brain(home):
    brain = FakeBrain()
    _agent(brain).handle("что было на прошлой неделе")
    assert brain.calls == 1, "природный вопрос — мозгу, не отказу дневника"


# ================================================================
# В6 «ПЕРЕВЕДИ 3 ФРАЗЫ НА ИТАЛЬЯНСКИЙ» — конвертер не жрёт переводы
# ================================================================
def test_v6_more_languages_skip_units(home):
    for phrase in ("переведи 3 фразы на итальянский",
                   "переведи 2 слова на корейский",
                   "переведи 5 предложений на арабский"):
        brain = FakeBrain()
        _agent(brain).handle(phrase)
        assert brain.calls == 1, phrase


# ================================================================
# В8 «Ё-МАРКЕР ПРИВЕТСТВИЯ» — маркер жив при ё→е
# ================================================================
def test_v8_welcome_marker_alive():
    assert agent._reply_already_welcomes("Мы еще не разговаривали")
    assert agent._reply_already_welcomes("Мы ещё не разговаривали")


# ================================================================
# В9 «ЗАКОН ФАКТА НА ОТРИЦАНИИ» — честное «не готово» без обвинения
# ================================================================
def test_v9_negation_not_a_claim():
    assert not agent._claim_without_work("ещё не готово")
    assert not agent._claim_without_work("не сделано — скажи архитектору")
    assert agent._claim_without_work("всё готово!")


# ================================================================
# В10 «ПОРЯДОК ПРЕПЕНДОВ» — будильник первой строкой
# ================================================================
def test_v10_alarm_above_care(home, monkeypatch):
    from core import care, reminders
    monkeypatch.setattr(reminders, "due_note",
                        lambda: "БУДИЛЬНИК-ТЕСТ")
    monkeypatch.setattr(care, "hello_line",
                        lambda: "ЗАБОТА-ТЕСТ")
    r = _agent().handle("время")
    assert r.text.startswith("БУДИЛЬНИК-ТЕСТ")
    assert "ЗАБОТА-ТЕСТ" in r.text


# ================================================================
# В17/В19 «ЖИВАЯ РЕЧЬ У СЛУГ» — вежливость и границы слов
# ================================================================
def test_v17_polite_throat(home, monkeypatch):
    from core import voice
    monkeypatch.setattr(voice, "wake_throat", lambda: "горло (шов)")
    r = _agent().handle("почини горло пожалуйста")
    assert r.tool_used == "throat_wake"


def test_v19_exam_button_is_hands_work(home, monkeypatch):
    """«нажми кнопку Экзамен» — работа рук, не экзамен диспетчера."""
    from core import motor
    monkeypatch.setattr(motor, "exam",
                        lambda: (_ for _ in ()).throw(
                            AssertionError("экзамен не должен зваться")))
    monkeypatch.setattr(motor, "parse_task", lambda t: {"verb": "unknown"})
    r = _agent().handle("нажми кнопку Экзамен")
    assert r.tool_used != "hands_exam"


# ================================================================
# С1-С3 «ЖРЕБИЙ ДО ВАЛИДАЦИИ» — большие числа идут в подсказку
# ================================================================
def test_s1_big_numbers_reach_validation(home):
    for phrase, mark in (("кубик 1001", "от 2 до 1000"),
                         ("пароль 1000", "от 4 до 128"),
                         ("помидор 1000", "от 1 до 240")):
        r = _agent().handle(phrase)
        assert mark in r.text, phrase


def test_s2_huge_range_reaches_validation(home):
    """С2: «число от 1 до <5000 цифр>» — не ValueError у брони."""
    big = "9" * 30
    brain = FakeBrain()
    r = _agent(brain).handle("число от 1 до %s" % big)
    assert brain.calls == 1, "переполнение — мозгу как было, не краш"
    assert "быстрая-упала" not in (r.text or "").lower()


def test_s3_coin_three_times(home, monkeypatch):
    from core import chance
    monkeypatch.setattr(chance, "coin_times", lambda n: "орлов 2 (шов)")
    r = _agent().handle("монетку 3 раза")
    assert r.tool_used == "chance"
    assert "шов" in r.text


# ================================================================
# С5 «№ В ДИФФЕ ПАТЧА» — «что меняет патч №2» жива
# ================================================================
def test_s5_hash_in_summary_and_diff(home, monkeypatch):
    from core import repair
    monkeypatch.setattr(repair, "patch_summary", lambda n: "сводка (шов)")
    monkeypatch.setattr(repair, "patch_diff", lambda n: "дифф (шов)")
    r1 = _agent().handle("что меняет патч №2")
    assert r1.tool_used == "patch_summary"
    r2 = _agent().handle("покажи патч №2")
    assert r2.tool_used == "patch_diff"


# ================================================================
# С7-С8 «УШИ С ВЕЖЛИВОСТЬЮ» — голый вопрос и хвост вежливости
# ================================================================
def test_s7_bare_hearing_question(home, monkeypatch):
    from sensors import ears
    monkeypatch.setattr(ears, "hearing_answer",
                        lambda: "слышу (шов)")
    r = _agent().handle("ты слышишь?")
    assert r.tool_used == "ears_hearing"
    assert "шов" in r.text


def test_s8_polite_listen(home, monkeypatch):
    from sensors import ears
    monkeypatch.setattr(ears, "listen", lambda secs=10: "тишина (шов)")
    r = _agent().handle("слушай микрофон 15 секунд пожалуйста")
    assert r.tool_used == "ears_listen"


# ================================================================
# С9-В7 «ГОЛОС С ВЕЖЛИВОСТЬЮ» — «скажи вслух пожалуйста» и «прочитай»
# ================================================================
# ================================================================
# В7 «ПРОЧИТАЙ В СЛУХ» — ПРОВЕРКА НЕ ПОДТВЕРДИЛА: владелец read_aloud
# (круг чтения) уже жив — якорь test_reading_circle держит оба маршрута.
# Здесь только С9: вежливость не произносится.
# ================================================================
def test_s9_bare_please_not_spoken(home, monkeypatch):
    said = []
    from core import voice
    monkeypatch.setattr(voice, "say", lambda t: said.append(t) or "звук")
    r = _agent().handle("скажи вслух пожалуйста")
    assert said == [], "вежливость не произносится"
    assert "что сказать" in r.text.lower()


# ================================================================
# С28 «ВЫЧИСЛИ 1/0» — честный отказ арифметики, не две минуты мозга
# ================================================================
def test_s28_zero_division_honest(home):
    brain = FakeBrain()
    r = _agent(brain).handle("вычисли 1/0")
    assert brain.calls == 0
    assert "ноль" in r.text.lower()


# ================================================================
# В22 «МАРФУШКА» и В4 «ХВОСТ ОБРАЩЕНИЯ»
# ================================================================
def test_v22_and_v4_name_forms(home):
    assert _agent().handle("Марфушка, время").tool_used == "time"
    assert _agent().handle("время, Марфа").tool_used == "time"


# ================================================================
# С10 «ИНТОНАЦИЯ ТРЕБОВАНИЯ» — мастерская не режет «!»
# ================================================================
def test_s10_exclamation_kept_in_about(home, monkeypatch):
    """С10: «говорит с жаром!» — требование с интонацией доезжает до
    кодера целиком (с краёв срезается только пунктуация-паузы)."""
    prompts = []
    monkeypatch.setattr(repair, "_ask_coder",
                        lambda prompt, max_tokens=None:
                        prompts.append(prompt)
                        or "```python\nX = 1\n```")
    customtools.design_patch("speakq", "говорит с жаром!")
    assert prompts, "кодер позван"
    assert "говорит с жаром!" in prompts[0]


# ================================================================
# В13 «ПРАВИЛО — ЧЕРЕЗ ТИРЕ» — мёртвая ветка ожила
# ================================================================
def test_v13_dash_rule_lives(home):
    r = _agent().handle("правило — молчание не есть согласие")
    assert r.tool_used == "rules"
    assert "правило №" in r.text or "уже есть" in r.text
