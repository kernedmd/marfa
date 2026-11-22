# -*- coding: utf-8 -*-
"""Тесты диспетчера (ТЗ 3.1): быстрые команды → Python, остальное → 30B."""
import json
from pathlib import Path

import pytest

from core import config
from core.agent import Agent, Reply, load_doctrine
from core.brain import BrainClient
from core.memory import Memory
from safety import guard
from tests.fake_llama_server import start_fake_brain


@pytest.fixture()
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("MARFA_HOME", str(tmp_path))
    monkeypatch.setattr(config, "HOME_DIR", tmp_path)
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(config, "GUARD_LOG_FILE", tmp_path / "logs" / "guard_log.jsonl")
    monkeypatch.setattr(config, "CANARIES_FILE", tmp_path / "data" / "canaries.json")
    monkeypatch.setattr(config, "DOCTRINE_FILE", tmp_path / "data" / "creator_doctrine.json")
    monkeypatch.setattr(config, "GENOME_FILE", tmp_path / "data" / "context_genome.json")
    monkeypatch.setattr(guard, "_LOG", None)
    config.ensure_dirs()
    yield tmp_path


@pytest.fixture()
def srv(monkeypatch, home):
    server = start_fake_brain()
    monkeypatch.setattr(config, "BRAIN_URL", server.base_url)
    yield server
    server.shutdown()


@pytest.fixture()
def agent(srv):
    mem = Memory(data_dir=Path(config.DATA_DIR))
    return Agent(brain=BrainClient(brain_url=srv.base_url), memory=mem, doctrine="Тестовая доктрина")


# ---------- быстрые команды: Python, мозг молчит ----------
def test_fast_brackets(agent, srv):
    r = agent.handle("скобки (a[1]{x})")
    assert "баланс: ОК" in r.text and r.tool_used == "check_brackets"
    assert srv.calls == []            # к 30B не ходили — 0 сек
    assert r.source == "python"


def test_fast_calc(agent, srv):
    r = agent.handle("вычисли (12 + 8) * 3")
    assert r.text == "60" and srv.calls == []


def test_fast_calc_not_math_goes_to_brain(agent, srv):
    srv.reply_content = '{"answer": "спроси у калькулятора"}'
    r = agent.handle("вычисли как жить")
    assert r.source == "brain" and len(srv.calls) == 1


def test_fast_remember(agent, srv):
    r = agent.handle("помни квант по умолчанию Q4_K_M")
    assert r.tool_used == "remember" and "запомнила" in r.text
    got = agent.memory.recall("квант по умолчанию")
    assert got and "Q4_K_M" in got[0]["text"]


def test_fast_recall(agent):
    agent.memory.remember("веб-панель живёт на 5001")
    r = agent.handle("вспомни веб-панель")
    assert "5001" in r.text and r.tool_used == "recall"


def test_fast_time_and_status(agent, srv):
    assert agent.handle("время").source == "python"
    r = agent.handle("статус")
    assert "Состояние дома" in r.text and srv.calls == []


# ---------- мозговой трек ----------
def test_brain_answer(agent, srv):
    srv.reply_content = '{"answer": "Контекст 4096 — закон доктрины"}'
    r = agent.handle("какой максимальный контекст?")
    assert r.text == "Контекст 4096 — закон доктрины" and r.source == "brain"


def test_brain_action_write_file(agent, srv):
    """{"action"} → руки. Путь и содержимое СТРАЖ проверяет внутри рук."""
    srv.reply_content = ('{"action": {"tool": "write_file", "args": '
                         '{"path": "data/заметка.txt", "content": "привет от мозга"}}}')
    r = agent.handle("запиши привет в data/заметка.txt")
    assert r.tool_used == "write_file" and "записано" in r.text
    assert (config.DATA_DIR / "заметка.txt").read_text(encoding="utf-8") == "привет от мозга"


def test_brain_action_guard_denies_outside(agent, srv):
    """Мозг просит записать вне дома → СТРАЖ отказывает, агент не падает.
    Путь платформонезависимый: соседняя папка рядом с домом."""
    import json
    outside = str(config.HOME_DIR.parent / "evil.txt")
    srv.reply_content = json.dumps(
        {"action": {"tool": "write_file", "args": {"path": outside, "content": "нет"}}},
        ensure_ascii=False,
    )
    r = agent.handle("запиши вне дома")
    assert r.tool_used == "write_file"
    assert "СТРАЖ" in r.text or "отказал" in r.text


def test_brain_unknown_tool(agent, srv):
    srv.reply_content = '{"action": {"tool": "format_c", "args": {}}}'
    r = agent.handle("отформатируй всё")
    assert "неизвестный инструмент" in r.text


def test_brain_down_honest(agent, monkeypatch):
    monkeypatch.setattr(agent.brain, "url", "http://127.0.0.1:1")
    r = agent.handle("длинный вопрос, требующий размышлений")
    assert "мозг недоступен" in r.text and r.source == "fallback"


# ---------- контекст ----------
def test_doctrine_and_rag_injected(agent, srv):
    """В промпт попадают доктрина, состояние и RAG-воспоминания (3.1)."""
    agent.memory.remember("дом Марфа живёт в C:\\Marfa")
    srv.reply_content = '{"answer": "принято"}'
    agent.handle("напомни, где живёт дом")
    sys_msg = next(m for m in srv.calls[-1]["messages"] if m["role"] == "system")
    assert "Тестовая доктрина" in sys_msg["content"]
    assert "Состояние дома" in sys_msg["content"]
    assert "C:\\Marfa" in sys_msg["content"]


def test_doctrine_file_loaded(home):
    import json
    (config.DATA_DIR / "creator_doctrine.json").write_text(
        json.dumps({"doctrine": "Я — Марфа. Служу Илье."}, ensure_ascii=False), encoding="utf-8")
    assert "Служу Илье" in load_doctrine()


def test_doctrine_missing_falls_back(home):
    assert "Марфа" in load_doctrine()  # каркасный минимум, не фантазия


# ---------- СКОРОСТЬ v1: краткость — закон дома ----------

def test_speed_law_in_brain_prompt(agent):
    """«ответ через две минуты — очень долго»: мозг ВИДИТ закон
    краткости в каждом системном промпте (статично — KV-кэш цел)."""
    extra = agent._system_extra("привет")
    assert "ЗАКОН СКОРОСТИ" in extra
    assert "одно-четыре предложения" in extra


def test_brain_track_short_budget_and_tokens(agent, srv):
    """Чат-ответ: бюджет BRAIN_ANSWER_TOKENS + штамп несёт токены —
    по ним видно, кто съел время, если снова две минуты."""
    srv.reply_content = '{"answer": "кратко и по делу"}'
    r = agent.handle("привет, как дела?")
    assert r.source == "brain"
    assert srv.calls[-1]["max_tokens"] == config.BRAIN_ANSWER_TOKENS
    assert srv.calls[-1]["stream"] is True          # превью просилось
    assert isinstance(r.meta, dict) and r.meta["tok"] >= 1


# ---------- РУКИ v2.1 (23.11): живой язык — мозгу, шпаргалка — по просьбе ----------

def test_hands_natural_language_goes_to_brain(agent, srv):
    """Урок живого лога: «Руки проверить работу микрофона» билось в
    формат-ошибку рук. Живой язык — работа МОЗГА: руки не притворяются
    глухим форматом, задание уходит думать мозгу."""
    srv.reply_content = '{"answer": "проверю уши, минуту"}'
    r = agent.handle("Руки проверить работу микрофона")
    assert r.source == "brain" and len(srv.calls) == 1
    assert "проверю уши" in r.text


def test_hands_bare_and_help_are_friendly(agent, srv):
    """«руки» и «что умеют руки» — шпаргалка по-человечески, а не тот же
    формат-отказ (второй урок того же лога: на вопрос о руках рука
    отвечала примером формата)."""
    for msg in ("руки", "руки?", "руки помощь", "что умеют руки",
                "что ты можешь руками"):
        r = agent.handle(msg)
        assert r.source == "python" and r.tool_used == "hands_help", msg
        assert "нажми" in r.text and "буфер" in r.text, msg
        assert srv.calls == [], msg


def test_hands_known_verbs_still_direct(agent, srv, monkeypatch):
    """Настоящие задания рук не ушли мозгу: «нажми Пуск» — по-прежнему
    руки, мозг молчит (сухой режим честно скажет про кнопку 91)."""
    from core import motor
    called = []

    def fake_run(task):
        called.append(task)
        return "РУКИ — задание: %s [сухой режим]" % task

    monkeypatch.setattr(motor, "run", fake_run)
    r = agent.handle("руки нажми Пуск")
    assert r.source == "python" and r.tool_used == "hands"
    assert called and "Пуск" in called[0]
    assert srv.calls == []


def test_hands_looking_redirect_survives(agent, srv, monkeypatch):
    """«руки посмотри на меня» — честный редирект рук на глаза (урок
    22.11 жив и с новым маршрутом: неизвестный глагол с «посмотр» не
    уходит мозгу молча, а получает свою подсказку)."""
    from core import motor
    monkeypatch.setattr(motor, "run", lambda task: "РУКИ не смотрят — «посмотри»")
    r = agent.handle("руки посмотри на меня")
    assert r.source == "python" and r.tool_used == "hands"
    assert "не смотрят" in r.text
    assert srv.calls == []


# ---------- ЗРЕНИЕ v2 (23.11): ДВА источника, ответ подписан ----------

def test_webcam_synonyms_route_to_camera(agent, srv, monkeypatch):
    """Урок живого лога: «посмотри веб-камерой» не имел маршрута — Создатель
    просил веб-камеру, а читал про экран сервера. Синонимы веб-камеры
    собраны в одну ветку ДО экранной."""
    from core import eyes
    seen = []
    monkeypatch.setattr(eyes, "describe_camera_text",
                        lambda: (seen.append(1), "Вижу в ВЕБ-КАМЕРЕ: тест")[1])
    for msg in ("включи веб-камеру", "что в веб-камере", "веб-камера",
                "посмотри веб-камерой", "посмотри в камеру, что там?",
                "глянь в веб-камеру", "что ты видишь в камере?",
                "кто в камере"):
        r = agent.handle(msg)
        assert r.tool_used == "camera", msg
        assert "ВЕБ-КАМЕРЕ" in r.text, msg
    assert len(seen) == 8
    assert srv.calls == []          # мозг молчит — маршрут мгновенный


def test_screen_commands_still_route_to_screen(agent, srv, monkeypatch):
    """Экран не пострадал от камеры: «посмотри», «что на экране» —
    по-прежнему экран, подпись источника честная."""
    from core import eyes
    monkeypatch.setattr(eyes, "describe_text",
                        lambda *a, **kw: "Вижу на ЭКРАНЕ: рабочий стол")
    for msg in ("посмотри", "что на экране", "что ты видишь",
                "посмотри, что открыто"):
        r = agent.handle(msg)
        assert r.tool_used == "eyes", msg
        assert "ЭКРАНЕ" in r.text, msg


def test_camera_selftest_not_hijacked(agent, monkeypatch):
    """«проверь камеру» — ЭКСПЕРИМЕНТ (импорт→сенсор→кадр), а не взгляд:
    живой тест не превратился в описание из-за новых синонимов."""
    from core import eyes
    monkeypatch.setattr(eyes, "camera_selftest", lambda: "ПРОВЕРКА КАМЕРЫ: жива")
    r = agent.handle("проверь камеру")
    assert r.tool_used == "camera_selftest"
    assert "ПРОВЕРКА КАМЕРЫ" in r.text


# ---------- УШИ v2 (23.11): осмотр с рецептом, а не «не могу слышать» ----------

def test_ears_selftest_command(agent, srv, monkeypatch):
    """«проверь уши» / «проверь микрофон» — живой осмотр по ступеням:
    урок лога («не могу слышать голос» без пути лечения) закрыт."""
    import sensors.ears as ears_mod
    monkeypatch.setattr(ears_mod, "selftest",
                        lambda: "ПРОВЕРКА УШЕЙ (вживую):\n- служба слуха: живы")
    for msg in ("проверь уши", "проверь микрофон", "уши?",
                "проверь слух, пожалуйста"):
        r = agent.handle(msg)
        assert r.tool_used == "ears_selftest", msg
        assert "ПРОВЕРКА УШЕЙ" in r.text, msg
        assert srv.calls == [], msg


def test_ears_selftest_crash_is_honest(agent, srv, monkeypatch):
    """Осмотр упал — чат жив, честный отказ с зовом архитектору
    (броня №4 р3: орган не роняет дом)."""
    import sensors.ears as ears_mod

    def boom():
        raise RuntimeError("статус не читается")

    monkeypatch.setattr(ears_mod, "selftest", boom)
    r = agent.handle("проверь уши")
    assert r.tool_used == "ears_selftest"
    assert "не собрался" in r.text and "архитектору" in r.text
    assert srv.calls == []          # мозг не будим — это честный отказ дома


# ---------- ЗАКОН РАЗГОВОРА (23.11): тон в системном промпте ----------

def test_tone_law_in_system_prompt(agent, srv):
    """Закон разговора едет в ЯДРЕ промпта (статично — KV-кэш цел):
    шаблоны поддержки запрещены, «Поняла» — не ответ, чувства/сон/мысли
    — органы, «просто языковая модель» — не про Марфу."""
    srv.reply_content = '{"answer": "хорошо"}'
    agent.handle("расскажи о законах дома")
    sys_text = srv.calls[-1]["messages"][0]["content"]
    assert "ЗАКОН РАЗГОВОРА" in sys_text
    assert "Как я могу вам помочь" in sys_text          # запрет назван явно
    assert "Илья" in sys_text
    assert "чувства, сон и мысли" in sys_text.lower()


def test_identity_names_feelings_organs(agent, srv):
    """ЯДРО личности называет чувства/сон/мысли живыми органами — урок
    лога: «не имею личных мыслей или эмоций» противоречил дому."""
    srv.reply_content = '{"answer": "ок"}'
    agent.handle("расскажи, что ты за существо")   # не «кто ты» — тот быстрый
    sys_text = srv.calls[-1]["messages"][0]["content"]
    assert "Чувства, сон и мысли" in sys_text
    assert "организм" in sys_text


# ---------- Ф1: зрительная память Создателя (23.11) ----------

def test_face_memory_commands(agent, srv, monkeypatch):
    """«запомни меня» / «узнай меня» — быстрые команды, мозг молчит:
    урок лога (мужчина в полосатой футболке ждёт, что его запомнят)."""
    from core import eyes
    monkeypatch.setattr(eyes, "remember_creator",
                        lambda memory=None: "Запомнила: тест")
    monkeypatch.setattr(eyes, "recognize_creator",
                        lambda: "Сверяю с памятью: тест")
    r1 = agent.handle("запомни меня")
    r2 = agent.handle("узнай меня")
    r3 = agent.handle("ты меня помнишь?")
    assert r1.tool_used == "face_remember" and "Запомнила" in r1.text
    assert r2.tool_used == "face_recognize" and "Сверяю" in r2.text
    assert r3.tool_used == "face_recognize"
    assert srv.calls == []


# ---------- Ф2: знакомство — команды ----------

def test_agent_introduce_and_who(agent, srv):
    """«меня зовут X» — имя в файл знакомства (переживает рестарт),
    «кто я» — вся картина; мозг молчит: знакомство — рефлекс."""
    r = agent.handle("меня зовут Илья")
    assert r.tool_used == "introduce" and "Илья" in r.text
    r = agent.handle("кто я")
    assert r.tool_used == "who_am_i" and "Илья" in r.text
    assert srv.calls == []


def test_agent_natural_phrases_not_introductions(agent, srv):
    """«я устал» — живая речь для мозга, не знакомство (тире в «я — X»
    обязательно: урок жадных префиксов раунда 3, второй раз)."""
    srv.reply_content = '{"answer": "отдохни"}'
    r = agent.handle("я устал")
    assert r.source == "brain" and len(srv.calls) == 1


def test_agent_forget_name(agent, srv):
    agent.handle("меня зовут Илья")
    r = agent.handle("забудь моё имя")
    assert "забыла" in r.text
    assert srv.calls == []


# ---------- Ф3/Ф4: приветствие и дайджест — команды ----------

def test_agent_greet_command(agent, srv):
    """«привет» — рефлекс: время суток + имя + отсутствие; мозг молчит
    (в приветствии нечего думать — всё знает дом)."""
    r = agent.handle("привет")
    assert r.tool_used == "greet" and r.source == "python"
    assert "Илья" in r.text
    assert srv.calls == []


def test_agent_digest_command(agent, srv):
    """«что нового» — дайджест жизни дома за отсутствие."""
    r = agent.handle("что нового")
    assert r.tool_used == "digest" and r.source == "python"
    assert srv.calls == []


def test_agent_good_morning_still_wakes_organism(agent, srv, monkeypatch):
    """«доброе утро» — команда пробуждения организма (сон важнее
    приветствия), не попала в новый список приветствий."""
    from core import sleep as _sleep
    monkeypatch.setattr(_sleep, "morning_text", lambda dream=None: "утро организма")
    r = agent.handle("доброе утро")
    assert r.tool_used == "sleep"
    assert srv.calls == []


# ---------- Ф5: сырые числа — по-человечески ----------

def test_agent_run_python_humanized(agent, srv):
    """Мозг выполнил код с крупными числами — Создатель читает людей:
    сырьё целиком + расшифровка в хвосте (урок лога: голые байты)."""
    import json
    srv.reply_content = json.dumps({"action": {
        "tool": "run_python",
        "args": {"code": "print(68621991936)"}}}, ensure_ascii=False)
    r = agent.handle("сколько всего памяти")
    assert r.tool_used == "run_python"
    assert "68621991936" in r.text          # сырьё на месте
    assert "63.9 ГБ" in r.text              # и перевод рядом
    assert "если это байты" in r.text


# ---------- Ф6: похвала — факт ----------

def test_agent_praise_command(agent, srv):
    """«спасибо» — рефлекс с чувством, мозг молчит; «спасибо, что…»
    (с хвостом) остаётся живой речью для мозга."""
    r = agent.handle("спасибо")
    assert r.tool_used == "praise" and "книжку радостей" in r.text
    assert srv.calls == []
    srv.reply_content = '{"answer": "на здоровье"}'
    r2 = agent.handle("спасибо, что объяснила про контекст")
    assert r2.source == "brain"


# ---------- Ф7: случайные решения ----------

def test_agent_chance_commands(agent, srv):
    """Монетка, кубик, жребий — чистый рефлекс, мозг молчит."""
    r1 = agent.handle("брось монетку")
    assert r1.tool_used == "chance" and "Монетка" in r1.text
    r2 = agent.handle("кубик 20")
    assert r2.tool_used == "chance" and "d20" in r2.text
    r3 = agent.handle("выбери: чай или кофе")
    assert r3.tool_used == "chance" and "Жребий" in r3.text
    r4 = agent.handle("выбери")
    assert "что выбрать" in r4.text
    assert srv.calls == []


# ---------- Ф8: план дня одной командой ----------

def test_agent_dayplan_command(agent, srv, monkeypatch):
    """«план дня» — снимок планировщика без консоли, мозг молчит."""
    from core import dayplan
    monkeypatch.setattr(dayplan, "today_plan", lambda now=None: "ПЛАН НА СЕГОДНЯ: тест")
    for msg in ("план дня", "план", "что по плану?"):
        r = agent.handle(msg)
        assert r.tool_used == "dayplan", msg
        assert "ПЛАН" in r.text, msg
    assert srv.calls == []
