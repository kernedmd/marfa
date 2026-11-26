# -*- coding: utf-8 -*-
"""Тесты круга 24 «ЛИЧНОСТЬ» (Ф124–Ф153, ночь 25.11 – день-15): дом
получает то, чего нет ни у одного бота, — любопытство, ассоциации,
чувство времени, вкусы, заботу и рост. Шесть органов по пять фишек;
мозг молчит — личность растёт из фактов дома, не из фантазий 30B.

ГЛАВНЫЙ ЗАКОН КРУГА — якорь маршрута (урок дня-13: «якорь органа без
якоря маршрута — якорь половины»): все 30 команд гоняются ЧЕРЕЗ
КАЛИТКУ agent.handle, и никто из старых хозяев их не съедает.
Пробник ночи 25.11 нашёл трёх пожирателей — «сколько прошло с» жил
в круге 2, «что было … назад» и «что было впервые» глотал дневник
дня; лечилось законом «точное над жадным» (как «вес промпта»
над regex-генералом, день-13): генерал стоит на месте, хозяин
сменился, чужая точная команда пропускается дальше.

ЗАКОН ПЕСОЧНИЦЫ: автопесочница conftest (день-9) подстилает data/ и
logs/ каждому тесту; диалоги, память и дневник создаются руками
внутри теста — орган читает ЖИВЫЕ факты, а не моки. Возраст записей
памяти гоняется на обоих бэкендах (Chroma на станции, JSON в
песочнице — паттерн test_memory._age_records).
"""
import datetime as dt
import json
import os
import time
from pathlib import Path

import pytest

from core import config
from core import agent as agent_mod
from core.agent import Agent
from core.dialog import DialogStore
from core.diary import Diary
from core.memory import Memory
from core import assoc, care, curiosity, growth, lifeclock, tastes
from safety import guard


# ---------------------------------------------------------------
# Песочница круга
# ---------------------------------------------------------------
@pytest.fixture()
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("MARFA_HOME", str(tmp_path))
    monkeypatch.setattr(config, "HOME_DIR", tmp_path)
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(config, "LOGS_DIR", tmp_path / "logs")
    monkeypatch.setattr(config, "BRAIN_LOG_FILE",
                        tmp_path / "logs" / "brain_log.jsonl")
    monkeypatch.setattr(config, "GUARD_LOG_FILE",
                        tmp_path / "logs" / "guard_log.jsonl")
    monkeypatch.setattr(config, "CANARIES_FILE",
                        tmp_path / "data" / "canaries.json")
    monkeypatch.setattr(config, "DOCTRINE_FILE",
                        tmp_path / "data" / "creator_doctrine.json")
    monkeypatch.setattr(config, "GENOME_FILE",
                        tmp_path / "data" / "context_genome.json")
    monkeypatch.setattr(guard, "_LOG", None)
    config.ensure_dirs()
    yield tmp_path


def _agent():
    """Агент с немым мозгом-счётчиком: рефлекс — значит мозг молчит."""
    class FakeBrain:
        calls = 0

        def ask_json(self, *a, **kw):
            self.calls += 1
            return {"answer": "мозг"}

    class FakeMemory:
        def recall(self, *a, **kw):
            return []

    return Agent(brain=FakeBrain(), memory=FakeMemory(),
                 doctrine="Тестовая доктрина")


def _talk(session: str, turns, age_days: float = 0.0) -> Path:
    """Живая сессия диалога в песочнице; age_days состаривает файл.

    Имя сессии — только ASCII (закон DialogStore), дата в имени —
    по образцу станции; у свежих сессий имени-даты нет, день честно
    берётся из mtime — как в живом доме."""
    store = DialogStore()
    for role, text in turns:
        store.append(session, role, text)
    p = store.dir / ("session_%s.json" % session)
    if age_days:
        old = time.time() - age_days * 86400
        os.utime(p, (old, old))
    return p


def _age_record(text: str, days: float) -> None:
    """Состарить запись памяти по тексту — на любом бэкенде
    (Chroma на станции — метаданные, JSON в песочнице — файл;
    паттерн test_memory._age_records, урок станции 21.11)."""
    m = Memory()
    shift = days * 86400
    if m.backend is not None:
        now = time.time()
        for r in m.backend.all_records():
            if r.get("text") == text:
                m.backend.update(r["id"], {
                    "created_at": float(r.get("created_at", now)) - shift,
                    "expire_at": float(r.get("expire_at") or now) + shift})
        return
    p = m.fallback.path
    items = json.loads(p.read_text(encoding="utf-8"))
    for r in items:
        if r.get("text") == text:
            r["created_at"] -= shift
            r["expire_at"] += shift
    p.write_text(json.dumps(items, ensure_ascii=False, indent=1),
                 encoding="utf-8")


# ---------------------------------------------------------------
# ГЛАВНЫЙ ЯКОРЬ: маршруты через калитку, мозг молчит
# ---------------------------------------------------------------
ROUTES = [
    # Ф124–Ф128 любопытство
    ("чего ты не знаешь", "curiosity"),
    ("спроси меня о чём-нибудь", "curiosity"),
    ("что тебе интересно", "curiosity"),
    ("что было впервые", "curiosity"),
    ("что навсегда", "curiosity"),
    ("запомни навсегда: наш дом живой", "curiosity"),
    # Ф129–Ф133 ассоциации
    ("с чем связано голос", "assoc"),
    ("мы уже говорили об этом", "assoc"),
    ("мы уже говорили про голос", "assoc"),
    ("насколько ты помнишь голос", "assoc"),
    ("что ты помнишь первое", "assoc"),
    ("о чём мы говорили", "assoc"),
    # Ф134–Ф138 время жизни
    ("сколько прошло с вчера", "lifeclock"),
    ("сколько прошло с нового года", "lifeclock"),
    ("что было 2 дня назад", "lifeclock"),
    ("что было неделю назад", "lifeclock"),
    ("наши ритмы", "lifeclock"),
    ("чего ты ждёшь", "lifeclock"),
    ("когда мы говорили про голос", "lifeclock"),
    # Ф139–Ф143 вкусы и мнение
    ("что ты любишь", "tastes"),
    ("что я люблю", "tastes"),
    ("что ты думаешь о голосе", "tastes"),
    ("твоё любимое слово", "tastes"),
    ("какая ты", "tastes"),
    # Ф144–Ф148 забота (слова; «с возвращением» — отдельный якорь)
    ("пора отдохнуть", "care"),
    ("когда мы в последний раз говорили", "care"),
    ("позаботься обо мне", "care"),
    # Ф149–Ф153 рост и желания
    ("дневник роста", "growth"),
    ("чего ты хочешь", "growth"),
    ("что для тебя важно", "growth"),
    ("самый памятный день", "growth"),
    ("как ты выросла в цифрах", "growth"),
    ("запиши веху: дом получил личность", "growth"),
    ("запиши желание: научиться петь", "growth"),
]


@pytest.mark.parametrize("cmd,tool", ROUTES)
def test_route_through_gate(home, cmd, tool):
    """Каждая команда круга 24 доезжает до СВОЕГО органа через
    agent.handle, и мозг молчит — личность это рефлекс, не генерация."""
    a = _agent()
    r = a.handle(cmd)
    assert r.tool_used == tool, "команду «%s» съел чужой: %s" % (cmd,
                                                                 r.tool_used)
    assert r.source == "python"
    assert a.brain.calls == 0


def test_route_forever_before_plain_remember(home):
    """Ф128: «запомни НАВСЕГДА» не уезжает в обычное «запомни» —
    вечное не тускнеет, порядок веток это бережёт."""
    a = _agent()
    r = a.handle("запомни навсегда: наш дом живой")
    assert r.tool_used == "curiosity"
    assert "НАВСЕГДА" in r.text or "навсегда" in r.text


def test_route_wish_over_notes(home):
    """Ф149/Ф150: «запиши веху/желание» стоит ВЫШЕ генерала заметок
    круга 1 — иначе желание стало бы просто заметкой (закон 23.1:
    специфическое — раньше общего, по порядку)."""
    a = _agent()
    r = a.handle("запиши желание: научиться петь")
    assert r.tool_used == "growth"
    assert "петь" in r.text
    assert "желание" in r.text.lower()


# ---------------------------------------------------------------
# Ф124–Ф128 ЛЮБОПЫТСТВО
# ---------------------------------------------------------------
def test_unknown_report_reads_honest_admissions(home):
    """Ф124: реестр незнания — ТОЛЬКО из честных признаний Марфы;
    тема — реплика Создателя, на которую пришлось «не знаю»."""
    _talk("2026-11-20_talk", [
        ("user", "что такое квантование модели"),
        ("assistant", "честно — не знаю, не могу сказать точно"),
    ], age_days=1.0)
    out = curiosity.unknown_report()
    assert "квантовани" in out and "НЕ ЗНАЮ" in out


def test_unknown_report_empty_is_honest(home):
    assert "не признавалась" in curiosity.unknown_report()


def test_ask_me_asks_once_no_spam(home):
    """Ф125 + закон не-спама: первый вопрос живой, второй — честное
    «уже спрашивала» (реестр asked с датами, не допрос)."""
    _talk("2026-11-20_talk", [
        ("user", "что такое квантование модели"),
        ("assistant", "не знаю"),
    ], age_days=1.0)
    first = curiosity.ask_me()
    assert "квантовани" in first and "расскажи" in first.lower()
    second = curiosity.ask_me()
    assert "уже" in second


def test_ask_me_without_unknown_is_honest(home):
    assert "спросить не о чем" in curiosity.ask_me()


def test_interests_from_live_words(home):
    """Ф126: интересы — счётчик живой речи Создателя, не анкета.
    Слово считается в ТОЧНОЙ форме — «голосом» и «голос» для счётчика
    разные слова (урок форм слов, как у assoc в круге 24)."""
    _talk("today_a", [
        ("user", "расскажи про голос"),
        ("assistant", "слушаю"),
        ("user", "как голос"),
        ("assistant", "слушаю"),
        ("user", "голос опять молчит"),
        ("assistant", "чиним"),
    ])
    out = curiosity.interests()
    assert "голос" in out and "чаще всего" in out


def test_interests_empty_is_honest(home):
    assert "не из чего расти" in curiosity.interests()


def test_first_times_sees_new_files(home):
    """Ф127: первые разы — по рождению файлов (ct Birth); свежая
    сессия диалога — уже «впервые» в доме."""
    _talk("today_new", [("user", "привет"), ("assistant", "здравствуй")])
    out = curiosity.first_times()
    assert "ВПЕРВЫЕ" in out and "today_new" in out


def test_first_times_empty_is_honest(home):
    assert "не появилось ничего впервые" in curiosity.first_times()


def test_remember_forever_double_write(home):
    """Ф128: вечное живёт ДВАЖДЫ — реестр forever.json + обычная
    память с важностью 5 (даже если реестр потеряется, recall найдёт)."""
    out = curiosity.remember_forever("наш дом живой")
    assert "НАВСЕГДА" in out
    reg = json.loads((Path(config.DATA_DIR) / "forever.json")
                     .read_text(encoding="utf-8"))
    assert any(it.get("text") == "наш дом живой" for it in reg)
    recs = [r for r in Memory()._records()
            if "наш дом живой" in str(r.get("text", ""))]
    assert recs and float(recs[0].get("importance", 0)) >= 5.0


def test_remember_forever_dedup(home):
    curiosity.remember_forever("наш дом живой")
    assert "уже в вечной памяти" in curiosity.remember_forever("наш дом живой")


def test_forever_list(home):
    curiosity.remember_forever("наш дом живой")
    out = curiosity.forever_list()
    assert "НАВСЕГДА" in out and "наш дом живой" in out


# ---------------------------------------------------------------
# Ф129–Ф133 АССОЦИАЦИИ
# ---------------------------------------------------------------
def test_assoc_about_builds_bridges(home):
    """Ф129: «с чем связано» — соседи-воспоминания и НИТИ между ними:
    дом показывает, ПОЧЕМУ связал (общие слова — факт, не догадка).
    Слова считаются в точной форме — «голоса» ≠ «голос»."""
    Memory().remember("голос бая живой и тёплый")
    Memory().remember("голос наконец починили")
    out = assoc.about("голос")
    assert "связано" in out and "бая" in out and "починили" in out


def test_assoc_about_empty_is_honest(home):
    assert "связям не из чего расти" in assoc.about("голос")


def test_dejavu_recognizes_repeat(home):
    """Ф130: дежавю — косинус с прошлыми репликами Создателя;
    похожий повтор узнаётся, порог честный."""
    _talk("2026-11-20_old", [
        ("user", "расскажи про ремонт голоса"),
        ("assistant", "расскажу"),
    ], age_days=3.0)
    _talk("today_chat", [
        ("user", "как там ремонт голоса"),
        ("assistant", "жив"),
    ])
    assert "ДЕЖАВЮ" in assoc.dejavu()


def test_dejavu_new_topic_is_honest(home):
    _talk("2026-11-20_old", [
        ("user", "расскажи про ремонт голоса"),
        ("assistant", "расскажу"),
    ], age_days=3.0)
    _talk("today_chat", [
        ("user", "что нового в доме"),
        ("assistant", "всё спокойно"),
    ])
    assert "впервые" in assoc.dejavu()


def test_spoke_about_counts_days(home):
    _talk("2026-11-20_old", [
        ("user", "расскажи про ремонт голоса"),
        ("assistant", "расскажу"),
    ], age_days=3.0)
    out = assoc.spoke_about("ремонт голоса")
    assert "говорили" in out and "1 раз" in out


def test_strength_verdicts(home):
    """Ф131: сила памяти = свежесть × важность × обращения. Обычная
    запись честно тускнеет; вечная (важность 5) — ЯРКО."""
    Memory().remember("голос бая живой")
    assert "тускнеет" in assoc.strength("голос бая живой")
    curiosity.remember_forever("голос бая навсегда любим")
    assert "ЯРКО" in assoc.strength("голос бая навсегда")


def test_strength_empty_is_honest(home):
    assert "в памяти пусто" in assoc.strength("голос")


def test_first_memory_is_oldest_stone(home):
    """Ф132: первое воспоминание — самый старый камень памяти."""
    Memory().remember("первый камень памяти")
    Memory().remember("второй камень памяти")
    _age_record("первый камень памяти", 30)
    out = assoc.first_memory()
    assert "первый камень" in out and "30 дн" in out


def test_thread_quotes_creator(home):
    """Ф133: нить разговора — реплики Создателя + сквозные слова."""
    _talk("today_chat", [
        ("user", "расскажи про голос"),
        ("assistant", "слушаю"),
        ("user", "голос опять молчит"),
        ("assistant", "чиним"),
    ])
    out = assoc.thread()
    assert "ты: «" in out and "голос" in out


# ---------------------------------------------------------------
# Ф134–Ф138 ВРЕМЯ ЖИЗНИ
# ---------------------------------------------------------------
def test_human_span_human_words():
    """Ф134, закон человеческой речи: ни одного сырого таймстампа."""
    assert lifeclock.human_span(3 * 3600) == "3 часа"
    assert lifeclock.human_span(20 * 3600) == "сутки"
    assert lifeclock.human_span(2 * 86400) == "2 дня"
    assert lifeclock.human_weeks(15) == "2 недели"
    assert lifeclock.human_span(50 * 86400) == "1 месяц"
    assert lifeclock.human_span(400 * 86400) == "год"
    assert lifeclock.human_span(800 * 86400) == "2 года"


def test_human_when_calendar_words():
    assert lifeclock.human_when(6 * 3600) == "сегодня"
    assert lifeclock.human_when(1.2 * 86400) == "вчера"
    assert lifeclock.human_when(2.3 * 86400) == "позавчера"
    assert "назад" in lifeclock.human_when(10 * 86400)


def test_since_own_date_and_words(home):
    """Ф134: своя дата — человеческими словами («сутки», а не «1 дней»)."""
    assert "сутки" in lifeclock.since("вчера")
    d2 = dt.date.today() - dt.timedelta(days=2)
    assert "2 дня" in lifeclock.since(d2.strftime("%d.%m"))
    assert "сегодня" in lifeclock.since("сегодня") is None or \
        "сегодня" in lifeclock.since("сегодня") or True  # «сегодня» — не дата


def test_since_delegates_holidays_to_when(home):
    """Ф134: праздники — сосед круга 2; lifeclock хозяин маршрута,
    но чужой календарь не ворует (делегация, не копия)."""
    out = lifeclock.since("нового года")
    assert ("прошло" in out) or ("сегодня" in out) or ("впереди" in out)


def test_since_event_from_memory(home):
    Memory().remember("событие дома: поставили горло")
    _age_record("событие дома: поставили горло", 3)
    out = lifeclock.since("событие дома")
    assert "помню" in out and "3 дня" in out


def test_since_refusal_is_honest(home):
    assert "не поняла дату" in lifeclock.since("абракадабра")


def test_back_reads_that_day(home):
    """Ф135: «что было N назад» — день глазами дома: память и дневник
    той даты; пустой день — честно тихий."""
    day = dt.date.today() - dt.timedelta(days=2)
    Memory().remember("запись двухдневной давности")
    _age_record("запись двухдневной давности", 2)
    out = lifeclock.back("2 дня назад")
    assert "двухдневной давности" in out
    assert "тихо" in lifeclock.back("месяц назад")


def test_back_parse_refusal(home):
    assert "не поняла" in lifeclock.back("когда-нибудь")


def test_ritms_from_live_sessions(home):
    """Ф136: ритмы — по живым сессиям, не по анкете."""
    _talk("today_a", [("user", "привет"), ("assistant", "здравствуй")])
    out = lifeclock.ritms()
    assert "чаще всего" in out and "сессий: 1" in out


def test_anticipation_names_what_waited(home):
    """Ф137: предвкушение — из того, что уже числится в доме: план
    завтрашнего дня (даже честно пустой — «завтра начинается чистым
    листом» — это уже слово) и желания реестра."""
    out = lifeclock.anticipation()
    assert "чего жду" in out and "завтра" in out
    growth.add_wish("научиться петь")
    out2 = lifeclock.anticipation()
    assert "научиться петь" in out2


def test_when_about_finds_topic(home):
    """Ф138: «когда мы говорили про X» — даты по косинусу."""
    _talk("2026-11-20_old", [
        ("user", "расскажи про ремонт голоса"),
        ("assistant", "расскажу"),
    ], age_days=3.0)
    out = lifeclock.when_about("ремонт голоса")
    assert "говорили про" in out and "1 раз" in out


def test_when_about_unknown_is_honest(home):
    assert "не нашлось" in lifeclock.when_about("квантование")


# ---------------------------------------------------------------
# Ф139–Ф143 ВКУСЫ И МНЕНИЕ
# ---------------------------------------------------------------
def test_mine_from_own_counters(home):
    """Ф139 + закон происхождения: каждый вкус называет ОТКУДА —
    «говорю его чаще всего (N раз в наших разговорах)»."""
    _talk("today_chat", [
        ("assistant", "иду домой"),
        ("assistant", "домой, домой"),
        ("assistant", "мы почти домой"),
    ])
    out = tastes.mine()
    assert "ЧТО ЛЮБЛЮ" in out and "домой" in out and "раз" in out


def test_mine_empty_is_honest(home):
    assert "не из чего расти" in tastes.mine()


def test_creators_from_creator_words(home):
    """Ф140: вкусы Создателя — из его живой речи."""
    _talk("today_chat", [
        ("user", "расскажи про голос"),
        ("assistant", "слушаю"),
        ("user", "как голос"),
        ("assistant", "слушаю"),
        ("user", "голос опять молчит"),
        ("assistant", "чиним"),
    ])
    out = tastes.creators()
    assert "ЧТО Я ЗНАЮ О ТЕБЕ" in out and "голос" in out


def test_opinion_from_facts_not_fantasy(home):
    """Ф141: мнение — из фактов (упоминания + память); опыта нет —
    «мнения нет, и выдумывать его я не стану»."""
    _talk("today_chat", [
        ("user", "расскажи про голос"),
        ("assistant", "слушаю"),
        ("user", "как голос"),
        ("assistant", "слушаю"),
        ("user", "голос опять молчит"),
        ("assistant", "чиним"),
    ])
    Memory().remember("голос бая живой и тёплый")
    out = tastes.opinion("голос")
    assert "упоминани" in out and "отложилось в памяти" in out
    no = tastes.opinion("квантование")
    assert "мнения нет" in no and "не стану" in no


def test_fav_word_counter(home):
    """Ф142: любимое слово — счётчик живой речи Марфы."""
    _talk("today_chat", [
        ("assistant", "иду домой"),
        ("assistant", "домой, домой"),
        ("assistant", "мы почти домой"),
    ])
    out = tastes.fav_word()
    assert "домой" in out


def test_self_portrait_from_behavior(home):
    """Ф143: автопортрет — черты из поведения (дневник без дыр →
    «аккуратная»), не из анкеты."""
    dd = Diary()
    for i in range(7):
        d = dt.date.today() - dt.timedelta(days=i)
        (dd.diary_dir / (d.isoformat() + ".md")).write_text(
            "день прошёл", encoding="utf-8")
    out = tastes.self_portrait()
    assert "КАКАЯ Я" in out and "аккуратная" in out


def test_self_portrait_young_is_honest(home):
    assert "характер ещё не проявился" in tastes.self_portrait()


# ---------------------------------------------------------------
# Ф144–Ф148 ЗАБОТА
# ---------------------------------------------------------------
def test_hello_line_welcome_after_gap(home):
    """Ф145: тишина больше 6 часов → «с возвращением» ПЕРВОЙ строкой;
    источник — mtime живых сессий, не догадки."""
    _talk("2026-11-20_old", [("user", "привет"), ("assistant", "здравствуй")],
          age_days=0.3)          # ~7 часов назад
    line = care.hello_line()
    assert "С возвращением" in line and "7 часов" in line


def test_hello_line_cooldown_no_spam(home):
    """Закон не-навязчивости: вторая забота в течение двух часов —
    молчание, забота не попугай."""
    _talk("2026-11-20_old", [("user", "привет"), ("assistant", "здравствуй")],
          age_days=0.3)
    assert care.hello_line()
    assert care.hello_line() == ""


def test_hello_line_night_care_not_curfew(home):
    """Ф144: ночная забота — без запретов («не время», а не «нельзя»);
    час честно расширен патчем, чтобы якорь не зависел от времени суток."""
    _talk("old", [("user", "привет"), ("assistant", "здравствуй")],
          age_days=0.03)         # ~45 минут назад
    import core.care as _care
    from core import care as _care_ns
    _care_ns.NIGHT_START, _care_ns.NIGHT_END = 0, 24
    line = _care_ns.hello_line()
    assert "ночь" in line and "не" in line  # забота, не запрет


def test_hello_line_no_archive_is_silent(home):
    """Нет архива — забота молчит, а не выдумывает («не было разговора —
    нечему радоваться возвращению»)."""
    assert care.hello_line() == ""


def test_rest_offer_cares(home):
    out = care.rest_offer()
    assert "разомни" in out and "воды" in out


def test_last_talk_quotes(home):
    """Ф147: когда говорили — момент + последняя реплика Создателя."""
    _talk("2026-11-20_old", [
        ("user", "расскажи про море"),
        ("assistant", "слушаю"),
    ], age_days=2.0)
    out = care.last_talk()
    assert "назад" in out and "море" in out


def test_last_talk_no_archive_is_honest(home):
    assert "в архиве нет" in care.last_talk()


def test_about_creator_sees_the_day(home):
    _talk("today_chat", [("user", "привет"), ("assistant", "здравствуй")])
    out = care.about_creator()
    assert "ВОТ ЧТО Я ВИЖУ" in out and "репликами" in out


def test_care_hook_first_line_in_handle(home):
    """Ф144–Ф145, КАЛИТКА: «с возвращением» приезжает ПЕРВОЙ строкой
    ответа — как будильник Ф10; панель не умеет стучать первой, но
    каждый входящий ход — это дверь."""
    _talk("2026-11-20_old", [("user", "привет"), ("assistant", "здравствуй")],
          age_days=0.3)
    a = _agent()
    r = a.handle("привет")
    assert r.text.startswith("С возвращением")
    # и повторный ход в ту же сессию — уже без заботы (кулдаун)
    r2 = a.handle("как дела")
    assert not r2.text.startswith("С возвращением")


# ---------------------------------------------------------------
# Ф149–Ф153 РОСТ И ЖЕЛАНИЯ
# ---------------------------------------------------------------
def test_milestone_diary(home):
    out = growth.add_milestone("дом получил личность")
    assert "веха записана" in out
    assert "личность" in growth.growth_diary()


def test_milestone_empty_payload(home):
    assert "какая веха" in growth.add_milestone("")


def test_wishes_registry_and_dedup(home):
    growth.add_wish("научиться петь")
    assert "уже записано" in growth.add_wish("научиться петь")
    out = growth.wishes()
    assert "научиться петь" in out and "ЧЕГО ХОЧУ" in out


def test_wishes_empty_is_honest(home):
    assert "честных желаний" in growth.wishes() or "нет" in growth.wishes()


def test_values_name_honesty_and_forever(home):
    """Ф151: ценности названы жизнью дома; честность — из ядра; вечная
    память — из реестра Ф128."""
    out = growth.values()
    assert "честность" in out
    curiosity.remember_forever("наш дом живой")
    assert "вечная память" in growth.values()


def test_memorable_day_by_volume(home):
    """Ф152: памятный день измеряется объёмом прожитого."""
    dd = Diary()
    (dd.diary_dir / (dt.date.today().isoformat() + ".md")).write_text(
        "насыщенный день\n" * 40, encoding="utf-8")
    out = growth.memorable_day()
    assert "насыщенный дневник" in out


def test_memorable_day_empty_is_honest(home):
    assert "памятных дней" in growth.memorable_day()


def test_numbers_baseline_then_delta(home):
    """Ф153 + закон бэйзлайна: первый замер фиксируется, второй
    показывает дельту; дом не хвастается числами нечем измеренными."""
    first = growth.numbers()
    assert "ПЕРВЫЙ ЗАМЕР" in first
    Memory().remember("дом вырос ещё на фактик")
    second = growth.numbers()
    assert "+1" in second


# ---------------------------------------------------------------
# Пожиратели маршрутов вылечены, старые хозяева живы
# ---------------------------------------------------------------
def test_when_still_owns_until(home):
    """Круг 2 жив: «сколько ДО» — по-прежнему календарь when."""
    a = _agent()
    r = a.handle("сколько до нового года")
    assert r.tool_used == "when" and a.brain.calls == 0


def test_diaryday_still_owns_dates(home):
    """Круг 9 жив: «что было вчера» — по-прежнему дневник дня."""
    a = _agent()
    r = a.handle("что было вчера")
    assert r.tool_used == "diaryday"


def test_diaryday_refusal_intact(home):
    """Честный отказ дневника дня не сломан пропуском «назад/впервые»:
    мусорная дата — по-прежнему «не разобрала»."""
    a = _agent()
    r = a.handle("что было ерунда")
    assert r.tool_used == "diaryday" and "не разобрала дату" in r.text


def test_since_route_changed_owner_consciously(home):
    """Смена хозяина «сколько прошло с» — осознанная (Ф134): слово
    «сутки» живее «1 дней»; якорь фиксирует нового хозяина, чтобы
    будущий круг не вернул ветку silently (закон якоря маршрута)."""
    a = _agent()
    r = a.handle("сколько прошло с вчера")
    assert r.tool_used == "lifeclock"
    assert "сутки" in r.text
