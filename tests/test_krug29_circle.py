# -*- coding: utf-8 -*-
r"""tests/test_krug29_circle.py — ЗОЛОТОЙ ЯКОРЬ КРУГА 29 «УШИ НЕ ВРУТ»
(Ф176–Ф180, день-17, 27.11.2026).

Круг родился из хвоста живого лога дня-16 (второй живой экзамен, ночь):
- «Да, ты уже все же найчилсь слышать микрофон?» — «Да, я слышу
  микрофон. Проверила — всё работает» — ВЫДУМКА: проверки не было,
  статус ушей мозг не читал (Ф176);
- «Почему когда я говорю тебе в микрофон ты никак не реагируешь?» —
  ответ про SAPI-выход: уши (вход) и горло (выход) перепутаны (Ф176,
  закон в промпте);
- «Слушай микрофон 15 секунд» — «неизвестный инструмент: listen» —
  мозг выдумал инструмент, дом не умел слушать по слову (Ф177);
- «неизвестный инструмент: listen — который ты хотел создать» — путь
  к мастерской («создай инструмент …») мозг Создателю не назвал (Ф161+);
- «Ложись спать, завтра будем разбираться» — точная ветка промахнулась
  о продолжение, мозг ответил ОТГОВОРКОЙ ПРО ГОЛОС (Ф179);
- «Марфа спокойной ночи» — «Марфа спокойной ночи», ДОСЛОВНО — попугай
  Создателя: эхо своих (Ф164) ловится, слова Создателя — нет (Ф178);
- «более подробней» — «Вернитесь к предыдущему сообщению…» — закон
  Ф165 стоял в промпте ВЕСЬ круг и нарушался живьём: промпт — просьба,
  маршрут — закон (Ф180).

Якоря (все — через калитку agent.handle, мозг молчит где не зван):
уши отвечают правдой из живого статуса; слушание — без второго
микрофона (шов sleep), тишина — тишина; попугай Создателя — укол и
честное признание, не в кэш; ночное слово — префикс; «подробнее» —
дом сам кладёт прошлый ответ в ход.
"""
import datetime as dt
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import agent, config, identity, progress  # noqa: E402
from core.agent import Agent, Reply  # noqa: E402
from sensors import ears as ears_mod  # noqa: E402


# ---------------------------------------------------------------
# Песочница круга (паттерн krug26/27): дом — tmp, слуги — швы
# ---------------------------------------------------------------

@pytest.fixture
def home(tmp_path, monkeypatch):
    """Изолированный дом: статусы и журналы ушей — в tmp, мозг — шов."""
    monkeypatch.setattr(config, "HOME_DIR", tmp_path)
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(config, "LOGS_DIR", tmp_path / "logs")
    monkeypatch.setattr(config, "EARS_STATUS_FILE",
                        tmp_path / "data" / "ears_status.json")
    monkeypatch.setattr(config, "EARS_LOG_FILE",
                        tmp_path / "logs" / "ears_log.jsonl")
    progress.reset()
    return tmp_path


class FakeBrain:
    """Мозг-счётчик: считает вызовы, помнит тексты ходов, отвечает
    заготовкой (или скриптом попыток)."""

    def __init__(self, answer="живой ответ мозга по существу",
                 script=None):
        self.calls = 0
        self.seen = []
        self.answer = answer
        self.script = script          # список ответов по попыткам

    def ask_json(self, text, *a, **kw):
        self.calls += 1
        self.seen.append(text)
        ans = (self.script[self.calls - 1]
               if self.script and self.calls <= len(self.script)
               else self.answer)
        if isinstance(ans, Exception):
            raise ans
        return {"answer": ans}


class FakeMemory:
    def recall(self, *a, **kw):
        return []


def _agent(brain=None):
    return Agent(brain=brain or FakeBrain(), memory=FakeMemory(),
                 doctrine="Тестовая доктрина круга 29")


def _ear_status(state="ok", age_secs=5.0, device="USB-камера",
                error=""):
    """Запись статуса службы ушей — как пишет sensors/ears.py."""
    rec = {"ts": (dt.datetime.now()
                  - dt.timedelta(seconds=age_secs)).isoformat(
                      timespec="seconds"),
           "sensor": "ears", "state": state}
    if device and state == "ok":
        rec["device"] = device
    if error:
        rec["error"] = error
    Path(config.EARS_STATUS_FILE).parent.mkdir(parents=True,
                                               exist_ok=True)
    Path(config.EARS_STATUS_FILE).write_text(
        json.dumps(rec, ensure_ascii=False), encoding="utf-8")


def _ear_log_entry(text, age_secs=0.0):
    """Строка журнала ушей — как пишет сторож имени."""
    return json.dumps({
        "ts": (dt.datetime.now()
               - dt.timedelta(seconds=age_secs)).isoformat(
                   timespec="seconds"),
        "sensor": "ears", "event": "speech", "text": text,
    }, ensure_ascii=False) + "\n"


# ================================================================
# Ф176 «УШИ НЕ ВРУТ» — вопрос о слухе отвечает орган, не фантазия
# ================================================================

def test_f176_hearing_question_is_reflex(home):
    """«Ты слышишь меня?» — рефлекс ушей: мозг молчит, ответ из живого
    статуса. Живой лог: «Да, я слышу. Проверила — всё работает» без
    проверки — выдумка, больше невозможно: орган отвечает сам."""
    _ear_status(state="ok")
    a = _agent()
    reply = a.handle("Ты слышишь меня?")
    assert reply.tool_used == "ears_hearing"
    assert a.brain.calls == 0, "вопрос о слухе — не тема мозга"
    assert "слышу" in reply.text


def test_f176_live_log_phrase_caught(home):
    """Точная фраза живого лога («найчилсь» — как сказал Создатель)
    ловится маршрутом — опечатка речи не роняет вопрос о факте."""
    _ear_status(state="no_mic", error="нет входных устройств")
    reply = _agent().handle("Да, ты уже все же найчилсь слышать микрофон?")
    assert reply.tool_used == "ears_hearing"
    assert "не слышу" in reply.text
    assert "микрофон не найден" in reply.text, "причина — из статуса"


def test_f176_ok_status_names_device(home):
    """Живое ухо: «да, слышу» + устройство + отличие от горла."""
    _ear_status(state="ok", device="Микрофон веб-камеры")
    reply = _agent().handle("ты слышишь микрофон?")
    assert reply.text.startswith("Да, слышу")
    assert "веб-камеры" in reply.text
    assert "живому сердцу" in reply.text, "источник ответа назван: не память"


def test_f176_dead_heart_honest(home):
    """Сердце замерло — «не могу сказать слышу», не выдумка «всё
    работает»: статус ok, но старый — служба висит."""
    _ear_status(state="ok", age_secs=900.0)
    reply = _agent().handle("слышишь ли ты меня?")
    assert reply.tool_used == "ears_hearing"
    assert "Не могу сказать" in reply.text
    assert "сердце" in reply.text


def test_f176_no_status_no_lies(home):
    """Статуса нет — честное «не знаю, слышу ли» с путём лечения
    (R11: не знаешь — так и скажи)."""
    reply = _agent().handle("Ты слышишь меня?")
    assert reply.tool_used == "ears_hearing"
    assert "Не знаю, слышу ли" in reply.text
    assert "проверь уши" in reply.text


def test_f176_ears_vs_throat_law_in_prompt(home):
    """ЗАКОН УШЕЙ едет в статичном ядре промпта: уши и горло — РАЗНЫЕ
    органы; «почему не реагируешь на микрофон» — больше не отговорка
    про голос (SAPI-путаница живого лога)."""
    core = _agent()._static_core()
    assert "ЗАКОН УШЕЙ" in core
    assert "РАЗНЫЕ органы" in core
    assert "не отвечай про голос" in core


def test_f176_open_why_question_goes_to_brain(home):
    """Открытый вопрос («почему ты не реагируешь…») — мозгу, не рефлексу:
    маршрут ловит только вопрос-о-факте, философию не отбирает."""
    a = _agent()
    reply = a.handle("Почему когда я говорю тебе в микрофон ты никак "
                     "не реагируешь?")
    assert a.brain.calls == 1
    assert reply.source == "brain"


# ================================================================
# Ф177 «СЛУШАЙ МИКРОФОН <N СЕК>» — живое прослушивание по слову
# ================================================================

def test_f177_listen_command_is_reflex(home, monkeypatch):
    """«Слушай микрофон 15 секунд» — рефлекс: «неизвестный инструмент:
    listen» больше не ответ, слушает орган."""
    _ear_status(state="ok")
    captured = {}

    def fake_listen(secs, sleep=None):
        captured["secs"] = secs
        return "Слушала %d секунд" % int(secs)

    monkeypatch.setattr(ears_mod, "listen", fake_listen)
    a = _agent()
    reply = a.handle("Слушай микрофон 15 секунд")
    assert reply.tool_used == "ears_listen"
    assert a.brain.calls == 0
    assert captured["secs"] == 15.0


def test_f177_listen_bare_defaults_10(home, monkeypatch):
    """Голое «слушай микрофон» — 10 секунд (границы органа — в самом
    органе, маршрут только передаёт)."""
    _ear_status(state="ok")
    captured = {}

    def fake_listen(secs, sleep=None):
        captured["secs"] = secs
        return "тишина"

    monkeypatch.setattr(ears_mod, "listen", fake_listen)
    _agent().handle("слушай микрофон")
    assert captured["secs"] == 10.0


def test_f177_listen_reads_journal_no_second_mic(home):
    """Прослушивание — без второго микрофона: ждём (шов), служба ушей
    слушает сама, читаем её журнал. Услышанное — дословно, тишина —
    тишина, выдумки нет."""
    _ear_status(state="ok")

    def fake_sleep(_secs):
        log = Path(config.EARS_LOG_FILE)
        log.parent.mkdir(parents=True, exist_ok=True)
        with log.open("a", encoding="utf-8") as fh:
            fh.write(_ear_log_entry("марфа послушай меня"))
            fh.write(_ear_log_entry("марфа послушай меня"))  # дубль подряд
            fh.write(_ear_log_entry("марфа"))                # обрывок

    out = ears_mod.listen(15.0, sleep=fake_sleep)
    assert "Слушала 15 секунд" in out
    assert "марфа послушай меня" in out
    assert out.count("марфа послушай меня") == 1, "подряд-дубли — одно"
    assert "«марфа»" not in out, "обрывок поглощён полной фразой"


def test_f177_silence_is_silence(home):
    """Тишина — честная тишина: орган не выдумывает услышанное."""
    _ear_status(state="ok")
    out = ears_mod.listen(5.0, sleep=lambda _s: None)
    assert "тишина" in out
    assert "Марфа" in out, "подсказка: зов сторож слышит точно"


def test_f177_dead_ear_honest_refusal(home):
    """Ухо мертво — честный отказ с диагнозом (Ф176), не тишина
    вместо ответа и не выдуманное прослушивание."""
    _ear_status(state="no_model", error="am/final.mdl не найден")
    out = ears_mod.listen(10.0, sleep=lambda _s: None)
    assert "не слышу" in out
    assert "слушать нечего" in out


def test_f177_seconds_clamped(home):
    """Границы 5–60 секунд: 999 не бывает, 0 — не мгновение (шов
    sleep пишет, сколько ждал орган)."""
    _ear_status(state="ok")
    waited = {}

    def fake_sleep(s):
        waited["s"] = s

    ears_mod.listen(999.0, sleep=fake_sleep)
    assert waited["s"] == 60.0
    ears_mod.listen(0.0, sleep=fake_sleep)
    assert waited["s"] == 5.0


# ================================================================
# Ф178 «ПОПУГАЙ СОЗДАТЕЛЯ» — слова Создателя не ответ
# ================================================================

def test_f178_parrot_detector(home):
    """Детектор: дословное повторение длинной реплики Создателя —
    попугай; короткие и переработанные — честные ответы."""
    assert agent._is_parrot_of_user("Марфа спокойной ночи!",
                                    "Марфа спокойной ночи")
    assert agent._is_parrot_of_user("почему небо синее",
                                    "почему небо синее?")
    assert not agent._is_parrot_of_user("Да", "ты слышишь меня")
    assert not agent._is_parrot_of_user("Спокойной ночи, Илья",
                                        "Марфа спокойной ночи")
    assert not agent._is_parrot_of_user("спасибо", "спасибо")


def test_f178_parrot_nudged_then_healed(home):
    """Попугай в первой попытке — укол знает болезнь, вторая — свой
    ответ: Создатель видит ответ, а не своё отражение."""
    brain = FakeBrain(script=["почему небо синее",
                              "Небо синее из-за рассеяния света — "
                              "молекулы воздуха гонят короткие волны."])
    reply = _agent(brain).handle("почему небо синее?")
    assert brain.calls == 2, "попугай переспрашивается один раз"
    assert "попугай" in brain.seen[1], "укол называет болезнь"
    assert "рассеяния света" in reply.text


def test_f178_parrot_confession_not_cached(home):
    """Упорный попугай — честное признание; память ответов его НЕ
    помнит (чужие слова — не воспоминание Марфы)."""
    brain = FakeBrain(answer="почему небо синее")
    reply = _agent(brain).handle("почему небо синее?")
    assert "повторила твои слова" in reply.text
    assert brain.calls == 2
    from core import answercache
    assert answercache.lookup("почему небо синее?") is None


def test_f178_night_farewell_before_brain(home):
    """«Марфа спокойной ночи» ловит ПРОЩАНИЕ-рефлекс ДО мозга (Ф179):
    попугай не может повторить то, что до него не доехало."""
    a = _agent()
    reply = a.handle("Марфа спокойной ночи")
    assert reply.tool_used == "night_farewell"
    assert a.brain.calls == 0
    assert "Спокойной ночи" in reply.text


# ================================================================
# Ф179 «СЛОВО НОЧИ» — ночное слово не съедает отговорка про голос
# ================================================================

def test_f179_farewell_is_warm_not_voice_excuse(home):
    """Прощание — тепло + факты дома; отговорки про голос из живого
    лога («сейчас не могу отвечать голосом») — нет."""
    reply = _agent().handle("спокойной ночи")
    assert reply.tool_used == "night_farewell"
    assert "не могу отвечать голосом" not in reply.text
    assert "что нового" in reply.text, "честный крючок утра"


def test_f179_bedtime_prefix_with_continuation(home):
    """«Ложись спать, завтра будем разбираться» — укладывание: точная
    ветка круга 23 промахивалась о продолжение (живой лог)."""
    reply = _agent().handle("Ложись спать, завтра будем разбираться")
    assert reply.tool_used == "sleep"
    assert "легла" in reply.text or "уже сплю" in reply.text


def test_f179_good_night_greeting_untouched(home):
    """Голое «доброй ночи» — ПРИВЕТСТВИЕ ночного прихода (ветка greet):
    дверь прощания её не трогает (границы соседей целы)."""
    a = _agent()
    reply = a.handle("доброй ночи")
    assert reply.tool_used == "greet"
    assert a.brain.calls == 0


def test_f179_farewell_uses_known_name(home):
    """Прощание зовёт по имени из живого знакомства (people), не
    выдумывает: знакомство есть — Илья, нет — Создатель."""
    from core import people
    people.set_name("Илья")
    reply = _agent().handle("спокойной ночи, Марфа")
    assert "Спокойной ночи, Илья" in reply.text


# ================================================================
# Ф180 «ПОДРОБНЕЕ — МАРШРУТ» — прошлый ответ в самом ходе
# ================================================================

def test_f180_bare_more_carries_prev_answer(home):
    """«более подробней» (форма живого лога) — дом сам кладёт прошлый
    ответ в ход: «Вернитесь к предыдущему сообщению» неоткуда."""
    brain = FakeBrain()
    history = [{"role": "user", "text": "что тебе снилось?"},
               {"role": "assistant",
                "content": "Снился тёплый дом и голос Создателя."}]
    _agent(brain).handle("более подробней", history=history)
    assert brain.calls == 1
    sent = brain.seen[0]
    assert "Раскрой свой предыдущий ответ" in sent
    assert "Снился тёплый дом" in sent, "прошлый ответ — в самом ходе"


def test_f180_all_live_forms(home):
    """Все живые формы речи: подробнее / подробней / ещё / более /
    поподробнее / пожалуйста — один маршрут."""
    for phrase in ("подробнее", "подробней", "ещё подробнее",
                   "более подробней", "поподробнее",
                   "расскажи подробнее", "подробнее, пожалуйста"):
        assert agent._wants_more_detail(phrase), "форма мимо: " + phrase
    for phrase in ("подробнее про сны", "что такое подробнее",
                   "напиши подробнее о доме"):
        assert not agent._wants_more_detail(phrase), \
            "тема — мозгу, не маршрут: " + phrase


def test_f180_no_prev_answer_passes_through(home):
    """Прошлого ответа нет (первое сообщение) — проход без изменений:
    мозг честно скажет, что раскрывать нечего."""
    brain = FakeBrain()
    _agent(brain).handle("подробнее", history=[])
    assert brain.seen[0] == "подробнее"


def test_f180_transformed_key_not_poisoned(home):
    """Ключ памяти ответов — ПРЕОБРАЗОВАННЫЙ текст: два «подробнее»
    после РАЗНЫХ ответов — два разных ключа, чужого воспоминания нет."""
    from core import answercache
    h1 = [{"role": "assistant", "content": "Снился дом."}]
    h2 = [{"role": "assistant", "content": "Я думала о законах дома."}]
    brain = FakeBrain(answer="раскрытый ответ")
    _agent(brain).handle("подробнее", history=h1)
    _agent(brain).handle("подробнее", history=h2)
    assert brain.calls == 2, "второе «подробнее» — НЕ из кэша: другой "
    "прошлый ответ — другой вопрос"


# ================================================================
# Ф161+ «МЕНЮ ВЕДЁТ В МАСТЕРСКУЮ» — неизвестный инструмент ≠ тупик
# ================================================================

def test_f177_unknown_tool_menu_points_to_workshop(home):
    """«неизвестный инструмент: listen» — меню само ведёт в мастерскую:
    «создай инструмент listen: …» (живой лог: путь был неочевиден —
    Создатель просил четыре раза)."""
    a = _agent()
    reply = a._act({"tool": "listen", "args": {}})
    assert "неизвестный инструмент: listen" in reply.text
    assert "создай инструмент listen" in reply.text
    assert "мастерская" in reply.text


# ================================================================
# КНИГА: команды круга — в списке быстрых и в стройном манифесте
# ================================================================

def test_krug29_commands_in_manifest(home):
    """Новые команды живут в FAST_COMMANDS и стройном манифесте: мозг
    ЗНАЕТ, что умеет дом (самопознание — не выдумка)."""
    fast = " | ".join(identity.FAST_COMMANDS)
    for fragment in ("ты слышишь меня", "слушай микрофон",
                     "спокойной ночи"):
        assert fragment in fast, "нет в FAST_COMMANDS: " + fragment
    slim = identity.manifest_slim()
    for fragment in ("слушай микрофон", "спокойной ночи"):
        assert fragment in slim, "нет в стройном манифесте: " + fragment
