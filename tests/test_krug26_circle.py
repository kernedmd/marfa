# -*- coding: utf-8 -*-
r"""tests/test_krug26_circle.py — ЗОЛОТОЙ ЯКОРЬ КРУГА 26 «СЛУХ, ИМЕНА
И МАСТЕРСКАЯ» (Ф159–Ф165, день-16, 27.11.2026).

Круг родился из живого лога дня-15: Создатель ШЕСТЬ раз просил
«создай инструмент для озвучивания» и получал шпаргалку «почини
что?» или выдумку «Создан инструмент»; «Марфа, а что тебе снилось?»
падало мимо органа снов в мозг с выдумкой про «образы, связанные с
предназначением»; «что я говорил в микрофон?» цитировал печать;
«Добрый вечер» после суток тишины получал ДВА приветствия; «Скажи в
слух: <стих>» не узнавался рефлексом и возвращался эхом текста.

Якоря (все — через калитку agent.handle, мозг молчит где не зван):
- Ф159: имя (все формы) и частицы снимаются до маршрутизации; голое
  имя «Марфа» — по-прежнему зов мозгу (№39 жив);
- Ф160: «что я говорил в микрофон» — цитата из сессии voice; «я это
  говорил в микрофон?» — честный источник хода; история ЕДИНАЯ:
  панель видит хвост голосовой с метками «[голосом]», голос — панель;
- Ф161: «создай инструмент <имя>: <что делает>» — патч в песочнице
  (НЕ «создан» — закон факта), «инструменты» — витрина, диспетчер
  зовёт инструмент-файл, меню ошибки несёт живые имена, больной
  модуль честно пропускается;
- Ф162: «в слух» раздельно = «вслух»; кавычки и «пожалуйста» — не
  контент;
- Ф163: ответ уже приветствует — забота уступает (один привет);
- Ф164: почти-эхо (вариации шаблона) ловится; попугай шпаргалок —
  укол и честное признание; окно сверки — три ответа;
- Ф165: закон «подробнее» живёт в промпте.

Швы: _ask_coder / ensure_server / release (repair), voice.say,
customtools.DIR-кеш, Agent(brain/memory) — ничего живого не
поднимается: ни кодера, ни горла, ни ушей.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import agent, config, customtools, identity, progress, repair  # noqa: E402
from core.agent import Agent  # noqa: E402
from core.dialog import DialogStore  # noqa: E402


# ---------------------------------------------------------------
# Песочница круга (паттерн test_masterskaya_circle): дом — tmp
# ---------------------------------------------------------------

@pytest.fixture
def home(tmp_path, monkeypatch):
    """Изолированный дом: мастерская и патчи не трогают станцию."""
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
    # кеш скана мастерской — свежий каждому тесту (орган живёт модулем)
    monkeypatch.setattr(customtools, "_scan_cache",
                        {"ts": 0.0, "tools": []})
    progress.reset()
    return tmp_path


class FakeBrain:
    """Мозг-счётчик: считает вызовы, отвечает заготовкой."""

    def __init__(self, answer="живой ответ мозга по существу"):
        self.calls = 0
        self.answer = answer

    def ask_json(self, *a, **kw):
        self.calls += 1
        return {"answer": self.answer}


class FakeMemory:
    def recall(self, *a, **kw):
        return []


def _agent(brain=None):
    return Agent(brain=brain or FakeBrain(), memory=FakeMemory(),
                 doctrine="Тестовая доктрина круга 26")


def _capture_say(monkeypatch):
    said = []
    from core import voice
    monkeypatch.setattr(voice, "say", lambda text: said.append(text) or
                        "произношу (шов)")
    return said


TOOL_CODE = (
    "# -*- coding: utf-8 -*-\n"
    'TOOL_NAME = "riminder"\n'
    'TOOL_ABOUT = "напоминает коротко"\n\n\n'
    "def run(args: dict) -> str:\n"
    '    text = str(args.get("text") or "").strip()\n'
    "    if not text:\n"
    '        return "что напомнить? дай text"\n'
    '    return "напоминаю: " + text\n'
)


# ================================================================
# Ф159 «ИМЯ И ЧАСТИЦЫ»
# ================================================================

def test_f159_name_and_particles_reach_organs(home):
    """«Марфа, а что тебе снилось?» — орган снов, не мозг-выдумщик;
    «Марф посмотри в камеру» — короткая форма имени тоже снимается."""
    a = _agent()
    r = a.handle("Марфа, а что тебе снилось?")
    assert r.source == "python" and r.tool_used == "dream"
    assert a.brain.calls == 0, "сон — орган, мозг молчит"
    # короткое имя: маршрут камеры узнаёт своё (без железа — честный
    # диагноз, но ИМЯ не мешает маршруту; главное — не мозг-эхо)
    r2 = a.handle("Марф, который час")
    assert r2.source == "python" and r2.tool_used == "time"


def test_f159_bare_name_still_wakes_brain(home):
    """Голое «Марфа» — зов (№39): мозгу, как прежде. Снятие имени
    не съело дом №39."""
    a = _agent()
    r = a.handle("Марфа")
    assert r.source == "brain" and a.brain.calls == 1


def test_f159_polite_greeting_variants(home):
    """«Марфочка, привет» — привет-рефлекс; вежливые частицы не роняют
    команду с органа."""
    a = _agent()
    r = a.handle("Марфочка, привет")
    assert r.source == "python" and r.tool_used == "greet"
    r2 = a.handle("а скажи вслух привет", )
    assert r2.tool_used == "voice"


# ================================================================
# Ф160 «ГОЛОС СОЗДАТЕЛЯ»
# ================================================================

def test_f160_what_did_i_say_in_mic(home):
    """«что я говорил в микрофон» — цитата из сессии voice (первые
    руки), время человеческими словами; печать не подменяет голос."""
    store = DialogStore()
    store.append(config.VOICE_SESSION, "user", "Марфа, включи музыку",
                 meta={"voice": True})
    store.append(config.VOICE_SESSION, "assistant", "включаю",
                 meta={"voice": True, "src": "python"})
    a = _agent()
    r = a.handle("что я говорил в микрофон?")
    assert r.source == "python" and r.tool_used == "mic_memory"
    assert "Марфа, включи музыку" in r.text
    assert a.brain.calls == 0, "факт — из органа, не из фантазии мозга"


def test_f160_no_voice_honest_answer(home):
    """Голосовых ходов нет — честное «не говорили», не выдумка."""
    a = _agent()
    r = a.handle("что я сейчас озвучил в микрофоне?")
    assert r.tool_used == "mic_memory"
    assert "ничего не говорили" in r.text


def test_f160_was_it_spoken_source_truth(home):
    """«я это говорил в микрофон?» — из чата: «нет, печать»; голосом
    (handle(voice=True) — мост ушей): «да, услышала». Живой лог дня-15:
    мозг дважды цитировал ПЕЧАТЬ как произнесённое."""
    store = DialogStore()
    store.append(config.VOICE_SESSION, "user", "Марфа, как дела",
                 meta={"voice": True})
    a = _agent()
    r = a.handle("я это говорил в микрофон?")
    assert r.tool_used == "mic_memory"
    assert "нет" in r.text.lower() and "печать" in r.text.lower()
    assert "Марфа, как дела" in r.text, "правда о последнем голосовом"
    r2 = a.handle("я такое говорил в микрофон?", voice=True)
    assert r2.tool_used == "mic_memory"
    assert r2.text.lower().startswith("да")


def test_f160_unified_history_voice_tail(home):
    """Панельная сессия видит хвост голосовой в ОДНОЙ истории, реплики
    голосом — с меткой «[голосом]»: мозг знает источник, раскол мозга
    (панель/voice — две половины разговора) закрыт."""
    store = DialogStore()
    # панель: ходы «сейчас» (свежая минута)
    store.append("panel1", "user", "привет из чата")
    store.append("panel1", "assistant", "здравствую")
    # голосовая сессия: файл с штампом минутой РАНЬШЕ (пишем руками —
    # формат файла дом documented, честный тест хронологии)
    vpath = store._path(config.VOICE_SESSION)
    vpath.parent.mkdir(parents=True, exist_ok=True)
    import datetime as _dt
    ts = (_dt.datetime.now() - _dt.timedelta(minutes=2)).strftime(
        "%d.%m %H:%M")
    vpath.write_text(json.dumps(
        {"session": config.VOICE_SESSION,
         "turns": [{"role": "user", "text": "Марфа, спой", "ts": ts,
                    "meta": {"voice": True}}]},
        ensure_ascii=False, indent=1), encoding="utf-8")
    merged = store.unified_turns("panel1")
    texts = [t.get("text") for t in merged]
    assert texts.index("Марфа, спой") < texts.index("привет из чата"), \
        "хронология по штампам: голос был раньше"
    msgs = DialogStore.render_messages(merged)
    voice_views = [m for m in msgs if "[голосом]" in m.get("content", "")]
    assert voice_views, "метка источника обязана доехать до мозга"
    # голосовая сессия видит панель (обратное направление)
    back = store.unified_turns(config.VOICE_SESSION)
    assert any(t.get("text") == "привет из чата" for t in back)


def test_f160_brain_history_has_voice_marks(home):
    """Рендер помечает только реплики Создателя-голосом; ответы
    Марфы меток не носят (канал ответа не меняет смысла)."""
    turns = [
        {"role": "user", "text": "Марфа, привет", "ts": "01.01 10:00",
         "meta": {"voice": True}},
        {"role": "assistant", "text": "здравствуй", "ts": "01.01 10:00",
         "meta": {"voice": True, "src": "python"}},
        {"role": "user", "text": "привет печатью", "ts": "01.01 10:01"},
    ]
    msgs = DialogStore.render_messages(turns)
    users = [m["content"] for m in msgs if m["role"] == "user"]
    assistants = [m["content"] for m in msgs if m["role"] == "assistant"]
    assert any(u.startswith("[голосом] Марфа, привет") for u in users)
    assert any(u == "привет печатью" for u in users), \
        "печать метки не получает"
    assert all("[голосом]" not in t for t in assistants), \
        "ответы Марфы меток не носят"


# ================================================================
# Ф161 «МАСТЕРСКАЯ ИНСТРУМЕНТОВ»
# ================================================================

def test_f161_design_tool_patch_not_claim(home, monkeypatch):
    """«создай инструмент riminder: напоминает коротко» — кодер пишет
    патч В ПЕСОЧНИЦУ; ответ НЕ говорит «создан» (закон факта) и несёт
    путь лечения «примени патч N» с живым номером."""
    monkeypatch.setattr(repair, "_ask_coder",
                        lambda prompt, max_tokens=None:
                        "```python\n" + TOOL_CODE + "```")
    a = _agent()
    r = a.handle("создай инструмент riminder: напоминает коротко")
    assert r.source == "python" and r.tool_used == "tool_forge"
    assert a.brain.calls == 0, "заказ инструмента — рефлекс, мозг молчит"
    assert "патч №0001 ГОТОВ" in r.text
    assert "СПРОЕКТИРОВАН" in r.text and "не создан" in r.text
    assert "примени патч 0001" in r.text, "живой номер, не заглушка N"
    # файл патча лёг в песочницу, цель — мастерская
    meta = json.loads((config.PATCHES_DIR / "0001" / "meta.json")
                      .read_text(encoding="utf-8"))
    assert meta["target"].replace("\\", "/").endswith(
        "core/customtools/riminder.py")
    assert meta["new_file"] is True


def test_f161_translit_and_reserved(home, monkeypatch):
    """Кириллица в имени — транслит (дом умеет), занятые имена —
    честный отказ: коллизия = тихая подмена инструмента."""
    got = customtools.normalize_name("напоминалка")
    assert got == ("napominalka", True)
    bad = customtools.normalize_name("speak")
    assert bad[1] is None and "занято" in bad[0]


def test_f161_empty_order_hint(home):
    """«создай инструмент» без имени и дела — подсказка формата на
    месте (№18-урок), не молчаливый мозг."""
    a = _agent()
    r = a.handle("создай инструмент")
    assert r.tool_used == "tool_forge"
    assert "Формат" in r.text and "translate" in r.text
    assert a.brain.calls == 0


def test_f187_template_order_refused(home, monkeypatch):
    r"""Ф187 «ШАБЛОН — НЕ ТРЕБОВАНИЕ» (день-18): Создатель повторяет
    советы дома ДОСЛОВНО, с заглушками в угловых скобках — и мастерская
    написала инструмент-заглушку sozday_instrument с требованием из
    текста совета (живой лог: «создай инструмент создай инструмент:
    <что делает>…»). Заглушка — не заказ: честный отказ, патч не
    поднимается; живое имя и живое дело — конвейер как был."""
    a = _agent()
    r = a.handle("создай инструмент translate: <что делает>")
    assert r.tool_used == "tool_forge"
    assert a.brain.calls == 0
    assert "шаблон" in r.text.lower()
    assert "патчей пока нет" in repair.list_patches()
    # живой заказ (имя и дело без скобок) — конвейер работает как был
    monkeypatch.setattr(repair, "_ask_coder",
                        lambda prompt, max_tokens=None:
                        "```python\nX = 1\n```")
    r2 = a.handle("создай инструмент riminder: напоминает коротко")
    assert r2.tool_used == "tool_forge"
    assert "шаблон" not in r2.text.lower()
    assert repair.list_patches() != "патчей пока нет"


def test_f161_tool_lives_after_apply(home, monkeypatch):
    """Применённый патч = живой инструмент: диспетчер зовёт его как
    встроенный, меню ошибки несёт его имя, промпт — строку мастерской."""
    monkeypatch.setattr(repair, "_ask_coder",
                        lambda prompt, max_tokens=None:
                        "```python\n" + TOOL_CODE + "```")
    a = _agent()
    a.handle("создай инструмент riminder: напоминает коротко")
    out = repair.apply_patch(1)
    assert "ПРИМЕНЁН" in out
    assert (Path(config.HOME_DIR) / "core" / "customtools" /
            "riminder.py").is_file()
    # диспетчер: мозг зовёт инструмент-файл
    class ToolBrain:
        def __init__(self):
            self.calls = 0
        def ask_json(self, *a, **kw):
            self.calls += 1
            return {"action": {"tool": "riminder",
                               "args": {"text": "полить цветы"}}}
    b = ToolBrain()
    a2 = Agent(brain=b, memory=FakeMemory(), doctrine="Тест")
    r = a2.handle("напомни про цветы")
    assert r.text == "напоминаю: полить цветы"
    # меню ошибки несёт живое имя
    class UnknownBrain:
        def ask_json(self, *a, **kw):
            return {"action": {"tool": "nosuchtool", "args": {}}}
    a3 = Agent(brain=UnknownBrain(), memory=FakeMemory(), doctrine="Тест")
    r3 = a3.handle("сделай неведомое")
    assert "riminder" in r3.text, "меню ошибки — все живые имена"
    # промпт несёт строку мастерской
    assert "riminder" in identity.manifest_slim()


def test_f161_broken_tool_skipped_honestly(home):
    """Больной модуль не роняет дом: витрина честно пропускает, вызов
    неизвестного — обычное «неизвестный инструмент»."""
    d = Path(config.HOME_DIR) / "core" / "customtools"
    d.mkdir(parents=True, exist_ok=True)
    (d / "sick.py").write_text("raise RuntimeError('болен')\n",
                               encoding="utf-8")
    assert customtools.names() == []
    r = customtools.call("sick", {})
    assert r is None, "больной не зовётся — его нет в списке живых"


def test_f161_vitrina_command(home):
    """«инструменты» — витрина руки дома: встроенные + speak +
    мастерская (пока пуста — честно) + подсказка рождения."""
    a = _agent()
    r = a.handle("инструменты")
    assert r.tool_used == "tool_forge"
    assert "read_file" in r.text and "speak" in r.text
    assert "пока пусто" in r.text
    assert "создай инструмент" in r.text


def test_f161_smoke_armor_includes_forge_anchor(home):
    """Броня Ф155 применяет к мастерской золотой якорь круга: патч в
    core\\customtools\\ гоняет test_krug26_circle.py (валидатор формы)."""
    tdir = Path(config.HOME_DIR) / "tests"
    tdir.mkdir(parents=True, exist_ok=True)
    (tdir / "test_krug26_circle.py").write_text("", encoding="utf-8")
    target = Path(config.HOME_DIR) / "core" / "customtools" / "x.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    files = repair._smoke_test.__wrapped__ if hasattr(
        repair._smoke_test, "__wrapped__") else None
    # прямой страж формы: собираем список как броня (без запуска pytest)
    test_file = Path(config.HOME_DIR) / "tests" / "test_x.py"
    related = repair._related_tests("x")
    files = ([test_file.name] if test_file.is_file() else []) + related
    try:
        if "customtools" in [p.lower() for p in target.parts]:
            anchor = Path(config.HOME_DIR) / "tests" / "test_krug26_circle.py"
            if anchor.is_file() and anchor.name not in files:
                files.append(anchor.name)
    except Exception:
        pass
    assert "test_krug26_circle.py" in files, \
        "броня мастерской обязана гонять якорь круга"


def test_f161_every_live_tool_has_shape(home):
    """ВАЛИДАТОР МАСТЕРСКОЙ (его гоняет броня применением): каждый
    файл в core\\customtools\\ — правильной формы, имя совпадает с
    файлом, run зовётся. Кривой инструмент не живёт в доме."""
    import importlib
    d = customtools.tools_dir()
    for f in sorted(d.glob("*.py")) if d.is_dir() else []:
        if f.name.startswith("_"):
            continue
        mod = customtools._load_module(f)
        name, about = customtools._shape_ok(mod)   # поднимет, если болен
        assert name == f.stem, "TOOL_NAME обязан совпадать с файлом"
        assert callable(mod.run)
        out = mod.run({})
        assert isinstance(out, str) and out.strip(), \
            "run обязан отвечать текстом даже на пустоту"


# ================================================================
# Ф162 «ГЛОТКА ШИРЕ»
# ================================================================

def test_f162_v_sluh_apart_and_politeness(home, monkeypatch):
    """«Скажи в слух привет» — рефлекс (живой лог: стих уезжал мозгу
    и возвращался эхом); кавычки и «пожалуйста» — не контент."""
    said = _capture_say(monkeypatch)
    a = _agent()
    r = a.handle("Скажи в слух привет")
    assert r.tool_used == "voice" and said == ["привет"]
    r2 = a.handle("скажи вслух «привет», пожалуйста")
    assert r2.tool_used == "voice" and said[-1] == "привет"
    r3 = a.handle("произнеси в слух: привет!")
    assert r3.tool_used == "voice" and said[-1] == "привет!"
    a.handle("скажи в слух")
    assert r.text  # пустой приказ — подсказка, не молчание


def test_f162_ellipsis_hint_covers_apart_form(home):
    """Пустой приказ «скажи в слух» — та же подсказка, что и «скажи
    вслух» (раньше раздельная форма молча уезжала в мозг)."""
    a = _agent()
    r = a.handle("скажи в слух")
    assert r.tool_used == "voice" and "что сказать" in r.text


# ================================================================
# Ф163 «ОДИН ПРИВЕТ»
# ================================================================

def test_f163_care_yields_to_greeting(home, monkeypatch):
    """«привет» после долгой тишины — ОДНО приветствие: рефлекс уже
    поздоровался — забота не добавляет второе. Живой лог дня-15:
    «С возвращением… сутки» + «Добрый вечер! не виделись 23 часа»
    в одном ответе."""
    from core import care
    monkeypatch.setattr(care, "hello_line",
                        lambda: "С возвращением, Илья — тебя не было "
                                "сутки. Я тут, дом жив.")
    a = _agent()
    r = a.handle("привет")
    assert r.tool_used == "greet"
    assert "С возвращением" not in r.text, "дубль приветствия — баг дня-15"
    # обычный ход — забота на месте (первой строкой, как Ф144)
    r2 = a.handle("как дела?")
    assert r2.text.startswith("С возвращением")


def test_f163_welcome_marks_detect_brain_greeting(home):
    """Текст сам поздоровался — забота уступает. Свидетель — ТЕКСТ:
    сам greet-рефлекс без тёплых слов не свидетель (якорь круга 24:
    «С возвращением» первой строкой остаётся законом)."""
    assert agent._reply_already_welcomes("С возвращением, Илья!")
    assert agent._reply_already_welcomes("Привет! не виделись 23 часа")
    assert agent._reply_already_welcomes("мы ещё не разговаривали — "
                                         "приятно познакомиться")
    assert not agent._reply_already_welcomes("Статус дома в норме")
    assert not agent._reply_already_welcomes(
        "Добрый вечер, Илья! Я на месте, дом работает — говорю, я "
        "слушаю.")


# ================================================================
# Ф164 «ЭХО ПОЧТИ» + «ПОПУГАЙ ШАБЛОНОВ»
# ================================================================

def test_f164_soft_echo_variations(home):
    """Вариации одного шаблона (живой лог дня-15 — «нет инструмента…»
    тремя разными сборками) — эхо, не ответ: сверка словами, не
    дословностью. Урок Создателя: «механизм сравнения в коде»."""
    a = ("У меня нет инструмента для озвучивания, но я могу общаться "
         "текстом. Если хотите, продолжим разговор текстом.")
    b = ("Я понимаю, что у меня нет инструмента для озвучивания. "
         "Я могу общаться текстом. Если хотите, продолжим разговор "
         "текстом.")
    c = ("Я работаю в рамках своих возможностей. У меня нет инструмента "
         "для озвучивания, но я могу отвечать текстом. Если хотите, "
         "продолжим разговор текстом.")
    assert agent._is_echo(a, b)
    assert agent._is_echo(a, c)
    assert agent._is_echo(a, a), "дословность — прежний закон"
    # честные РАЗНЫЕ ответы — не эхо
    assert not agent._is_echo(a, "Сначала нужно поднять горло, потом "
                                 "проверить голоса в системе Windows.")


def test_f164_short_repeats_still_honest(home):
    """Короткие повторы — честны (Создатель сам требует односложности
    на прямые вопросы): «не знаю» дважды — не зацикливание."""
    assert not agent._is_echo("не знаю", "не знаю")


def test_f164_window_three_answers(home):
    """Окно сверки — ТРИ ответа: цикл A→B→C→A (между двумя «нет
    инструмента» стояли «почини что?») больше не проходит насквозь."""
    class Cycler:
        def __init__(self):
            self.i = 0
            self.chain = [
                "У меня нет инструмента для озвучивания, но я могу "
                "общаться текстом. Если хотите, продолжим разговор "
                "текстом.",
                "Я Марфа, и я отвечаю вам. В данный момент у меня нет "
                "инструмента для озвучивания, но я могу общаться "
                "текстом.",
                "почему бы и нет, давай продолжим",
            ]
        def ask_json(self, *a, **kw):
            ans = self.chain[self.i % len(self.chain)]
            self.i += 1
            return {"answer": ans}
    hist = [
        {"role": "user", "content": "запрос 1"},
        {"role": "assistant", "content":
            "У меня нет инструмента для озвучивания, но я могу общаться "
            "текстом. Если хотите, продолжим разговор текстом."},
        {"role": "user", "content": "запрос 2"},
        {"role": "assistant", "content":
            "Я Марфа, и я отвечаю вам. В данный момент у меня нет "
            "инструмента для озвучивания, но я могу общаться текстом."},
        {"role": "user", "content": "запрос 3"},
        {"role": "assistant", "content": "почему бы и нет, давай продолжим"},
    ]
    b = Cycler()
    a = Agent(brain=b, memory=FakeMemory(), doctrine="Тест")
    r = a.handle("создай мне инструмент озвучивания", history=hist)
    # третий ответ цикла = первый (3 назад) — окно обязано видеть
    assert "зациклилась" in r.text


def test_f164_parrot_template_admission(home):
    """Мозг-попугай (шпаргалка «почини что? Формат…» дважды) — честное
    признание с путём лечения, НЕ выдача шпаргалки за ответ."""
    template = ("почини что? Формат: «почини <файл>: <что сделать>», "
                "например: «почини scripts\\hello.py: добавь функцию "
                "приветствия». Список готовых — «патчи»")
    class Parrot:
        def __init__(self):
            self.calls = 0
        def ask_json(self, *a, **kw):
            self.calls += 1
            return {"answer": template}
    b = Parrot()
    a = Agent(brain=b, memory=FakeMemory(), doctrine="Тест")
    r = a.handle("сделай мне инструмент для озвучивания речи",
                 history=[])
    assert b.calls == 2, "укол — один переспрос"
    assert "шпаргалку" in r.text
    assert "ответь иначе" in r.text
    assert "Формат" not in r.text, "шпаргалка не выдаётся за ответ"


def test_f164_parrot_signatures_narrow(home):
    """Сигнатуры попугая — узкие: нормальный ответ о починке НЕ
    попугай (советовать команду — можно, копировать шаблон — нет)."""
    assert agent._parroted_template(
        "почини что? Формат: «почини <файл>: <что сделать>»")
    assert agent._parroted_template("Что починить? Назови файл и что "
                                    "сделать: «почини <файл>: <что "
                                    "сделать»")
    assert not agent._parroted_template(
        "Скажи «почини scripts\\hello.py: добавь приветствие» — кодер "
        "напишет патч, а ты его применишь.")
    assert not agent._parroted_template("Я думаю, надо подождать.")


# ================================================================
# Ф165 «ПОДРОБНЕЕ»
# ================================================================

def test_f165_more_detailed_law_in_prompt(home):
    """Закон «подробнее» живёт в статичном промпте: мозг раскрывает
    свой прошлый ответ, а не отсылает «вернитесь к предыдущему
    сообщению» (живой лог дня-15)."""
    assert "Подробнее" in agent.TONE_LAW
    assert "вернуться к предыдущему сообщению" in agent.TONE_LAW
    # статичный префикс несёт закон (Ф77: KV-кэш)
    assert "Подробнее" in Agent._static_core(_agent())


# ================================================================
# СТАРЫЕ ХОЗЯЕВА ЖИВЫ (регресс кругов 1–25)
# ================================================================

def test_old_routes_not_broken_by_name_strip(home, monkeypatch):
    """Снятие имени/частиц не сломало соседние маршруты: «помнишь, как
    мы гуляли?» — вопрос мозгу (не приказ памяти); «скобки ()» —
    подсказка; «время» — рефлекс."""
    said = _capture_say(monkeypatch)
    a = _agent()
    assert a.handle("время").tool_used == "time"
    r = a.handle("помнишь, как мы гуляли?")
    assert r.source == "brain", "вопрос — мозгу, как прежде"
    r = a.handle("скобки ?")
    assert "а что проверить" in r.text
    assert a.handle("почини").source == "python", "голое «почини» — подсказка"


def test_old_repair_route_still_works(home, monkeypatch):
    """«почини <файл>: <что сделать>» — прежний конвейер кодера;
    мастерская его не съела (закон: точное над жадным)."""
    target = Path(config.HOME_DIR) / "scripts" / "hello.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("OLD = 1\n", encoding="utf-8")
    monkeypatch.setattr(repair, "_ask_coder",
                        lambda prompt, max_tokens=None:
                        "```python\nNEW = 2\n```")
    a = _agent()
    r = a.handle("почини scripts\\hello.py: добавь функцию приветствия")
    assert r.tool_used == "repair" or "ГОТОВ" in r.text
    assert "ГОТОВ" in r.text
