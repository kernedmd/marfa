# -*- coding: utf-8 -*-
"""Тесты круга 23 «ГОЛОС v2» (Ф121–Ф123, день-14): слуга-горло Silero
v5_6 на порту 8084, цепь silero → SAPI → честный отказ, смена голоса
командой — и ПЕРВЫЙ ЖИВОЙ ЯКОРЬ ОРГАНА В ПЕСОЧНИЦЕ АРХИТЕКТОРА.

Законы, которые куются здесь:
- глотка отделена от рта: слуга отдаёт WAV-байты, рот (winsound) живёт
  в теле дома — разделение проверяется швами (synthesize/_play_wav);
- цепь честна: горло спит или подавилось — SAPI подхватывает; оба
  молчат — честный отказ с путём лечения (закон эфира для голоса);
- один голос в один момент: MOUTH_LOCK держит ОБА рта (закон Ф56);
- числа — прописью ДО синтеза (орган Ф23 работает и для горла);
- lazy-torch: модуль слуги импортируется БЕЗ torch — дом без посылки
  не падает, якоря читают код (круг 22), пока орган спит;
- ЖИВОЙ ЯКОРЬ (Ф123): torch.package кроссплатформенен — песочница
  архитектора СЛЫШИТ те же байты, что услышит станция. Прежние якоря
  читали код — этот слушает голос. Орган спит (нет torch / нет
  модели) — честный skip с путём лечения, не зелёная ложь.
"""
import json
import math
import struct
import subprocess
import sys
import threading
from pathlib import Path

import pytest

from core import config, throat, voice
from core.agent import Agent
from safety import guard
from tests.fake_llama_server import start_fake_brain


@pytest.fixture()
def home(tmp_path, monkeypatch):
    """Свой дом на тест (по образцу круга 22: патч поверх автопесочницы
    conftest — настройка голоса пишется в data\voice_settings.json,
    агент не протекает в живые логи)."""
    monkeypatch.setattr(config, "HOME_DIR", tmp_path)
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(config, "LOGS_DIR", tmp_path / "logs")
    monkeypatch.setattr(config, "BRAIN_LOG_FILE",
                        tmp_path / "logs" / "brain_log.jsonl")
    monkeypatch.setattr(config, "GUARD_LOG_FILE",
                        tmp_path / "logs" / "guard_log.jsonl")
    monkeypatch.setattr(config, "CANARIES_FILE",
                        tmp_path / "data" / "canaries.json")
    monkeypatch.setattr(config, "LESSONS_FILE",
                        tmp_path / "journal" / "lessons.json")
    monkeypatch.setattr(guard, "_LOG", None)
    monkeypatch.setattr(voice, "_VOICES_CACHE",
                        {"ts": 0.0, "voices": [], "error": ""})
    config.ensure_dirs()
    yield tmp_path / "data"


@pytest.fixture()
def srv(monkeypatch, home):
    """Фальшивый мозг (образец круга 22): рефлекс голоса — чистый
    Python, но агент живёт в честном окружении, а не в пустоте."""
    server = start_fake_brain()
    monkeypatch.setattr(config, "BRAIN_URL", server.base_url)
    yield server
    server.shutdown()


@pytest.fixture()
def agent(srv):
    return Agent()


def _throat_asleep(monkeypatch):
    """Горло спит — цепь честно уйдёт в SAPI (общий случай батареи)."""
    monkeypatch.setattr(voice, "_throat_alive", lambda: False)


# ------------------------------------------------------------------- Ф121

def test_speaker_aliases(home):
    """Живые имена голосов → id спикеров: кириллица живой речи, латиница
    напрямую, «смени голос на …» — тоже; чужое имя — честный None."""
    assert throat.normalize_speaker("бая") == "baya"
    assert throat.normalize_speaker("Байя") == "baya"
    assert throat.normalize_speaker("Ксения") == "kseniya"
    assert throat.normalize_speaker("ксения-латинская") == "xenia"
    assert throat.normalize_speaker("смени голос на айдар") == "aidar"
    assert throat.normalize_speaker("поменяй голос на евгений") == "eugene"
    assert throat.normalize_speaker("eugene") == "eugene"
    assert throat.normalize_speaker("ирину") is None      # это SAPI, не горло
    assert throat.normalize_speaker("") is None


def test_normalize_text_numbers_and_markdown(home):
    """Глотка слышит чистый текст: markdown-шум снят, целые числа —
    прописью (Ф23); дроби, даты и «007» честно остаются цифрами —
    прописывать их работа смысла, не глотки (закон numeral.py)."""
    out = throat.normalize_text("В **круге 23** дом получил голос: 2026 год")
    assert "круге двадцать три" in out and "две тысячи двадцать шесть" in out
    assert "*" not in out
    honest = throat.normalize_text("3,5 метра от 25.11.2026 и код 007")
    assert "3,5" in honest and "25.11.2026" in honest and "007" in honest
    assert throat.normalize_text("   много   пробелов   ") == "много пробелов"


def test_rate_prosody_ladder(home):
    """Шкала Ф58 (−5..5) ложится на prosody Silero ступенями; 0 — родной
    темп без обёрток (меньше SSML — меньше сюрпризов)."""
    assert throat.rate_to_prosody(-5) == "x-slow"
    assert throat.rate_to_prosody(-3) == "x-slow"
    assert throat.rate_to_prosody(-2) == "slow"
    assert throat.rate_to_prosody(-1) == "slow"
    assert throat.rate_to_prosody(0) is None
    assert throat.rate_to_prosody(1) == "fast"
    assert throat.rate_to_prosody(2) == "fast"
    assert throat.rate_to_prosody(3) == "x-fast"
    assert throat.rate_to_prosody(5) == "x-fast"


def test_ssml_escape_and_wrap(home):
    """SSML строится только при сдвинутом темпе; XML-побеги честны —
    чужой текст никогда не рвёт разметку слуги."""
    assert throat.build_ssml("тихо", 0) is None
    ssml = throat.build_ssml("быстрее & громче <чем> обычно", 4)
    assert ssml == ('<speak><prosody rate="x-fast">'
                    'быстрее &amp; громче &lt;чем&gt; обычно'
                    '</prosody></speak>')


def test_wav_bytes_duration_by_header(home):
    """Чтение длительности ПО ЗАГОЛОВКУ (закон фактов: якорь верит
    байтам, не словам сервера): живой WAV — секунды, мусор — 0.0."""
    import sensors.throat as servant
    sr = 48000
    samples = [math.sin(2 * math.pi * 440 * i / sr) * 0.4
               for i in range(sr // 2)]          # 0.5 с синуса
    wav = servant.pcm_to_wav(samples, sr)
    assert wav[:4] == b"RIFF" and wav[8:12] == b"WAVE"
    assert abs(throat.wav_duration_sec(wav) - 0.5) < 0.01
    assert throat.wav_duration_sec(b"") == 0.0
    assert throat.wav_duration_sec(b"NOTAWAVENOTAWAVENOTAWAVENOTAWAVE") == 0.0


def test_lazy_torch_law(home):
    """ЗАКОН ЛЕНИВОГО TORCH: модуль слуги импортируется БЕЗ torch —
    дом без посылки не падает (панель и якоря живут). Проверка в
    чистом подпроцессе: батарея сама torch не тянет."""
    code = ("import sys, sensors.throat; "
            "assert 'torch' not in sys.modules, 'слуга потянул torch на "
            "импорте — закон ленивого torch нарушен'; print('чист')")
    r = subprocess.run([sys.executable, "-c", code],
                       capture_output=True, text=True, timeout=60,
                       cwd=str(Path(__file__).resolve().parents[1]))
    assert r.returncode == 0 and "чист" in r.stdout


# ------------------------------------------------------------------- Ф122

class _FakeThroat:
    """Шов горла: помнит вызовы; успех/отказ/крах — по рецепту теста."""

    def __init__(self, ok=True, data=b"RIFF-pad", crash=False):
        self.calls = []
        self._ok, self._data, self._crash = ok, data, crash

    def __call__(self, text, speaker="baya", rate=0, volume=100,
                 timeout=None):
        self.calls.append((text, speaker, rate, volume))
        if self._crash:
            raise RuntimeError("горло подавилось")
        return self._ok, self._data


def test_speak_throat_first(home, monkeypatch):
    """ГЛАВНЫЙ Ф122: горло живо — говорит ГОРИЛО: голосом бая (silero),
    SAPI не трогается (запасной рот молчит), MOUTH_LOCK держит оба
    рта (один голос в один момент — закон Ф56 цел)."""
    monkeypatch.setattr(voice, "_throat_alive", lambda: True)
    fake = _FakeThroat(ok=True, data=b"RIFF" + b"\x00" * 500)
    monkeypatch.setattr(throat, "synthesize", fake)
    played = []
    monkeypatch.setattr(voice, "_play_wav",
                        lambda data: played.append(data) or True)
    sapi = []
    monkeypatch.setattr(voice, "available", lambda: sapi.append("ps") or True)
    out = voice.speak("Марфа дома! Слышно меня?")
    assert "silero" in out and "бая" in out
    assert len(fake.calls) == 1 and fake.calls[0][1] == "baya"
    assert played and played[0].startswith(b"RIFF")
    assert not sapi                     # запасной рот не будили


def test_speak_falls_to_sapi_when_throat_chokes(home, monkeypatch):
    """ЦЕПЬ ЧЕСТНА: горло отказало — SAPI говорит тем же законом, что и
    до круга 23 (сообщение прежнее, якоря круга 10 целы)."""
    monkeypatch.setattr(voice, "_throat_alive", lambda: True)
    monkeypatch.setattr(throat, "synthesize",
                        _FakeThroat(ok=False, data="горло отказало"))
    monkeypatch.setattr(voice, "_play_wav", lambda data: False)
    monkeypatch.setattr(voice, "available", lambda: True)
    monkeypatch.setattr(voice, "_VOICES_CACHE",
                        {"ts": 1e12, "voices": [("Microsoft Irina", "ru-RU")],
                         "error": ""})
    called = []
    monkeypatch.setattr(voice, "_ps",
                        lambda script, timeout: called.append(script)
                        or (0, ""))
    out = voice.speak("привет")
    assert "Microsoft Irina" in out
    assert called and "$s.Speak(" in called[0]


def test_speak_throat_crash_does_not_break_house(home, monkeypatch):
    """ЗАКОН ЭФИРА: горло упало КРАХОМ — дом не молчит: SAPI подхватил,
    исключение не вырвалось наружу (голос не рвёт дом)."""
    monkeypatch.setattr(voice, "_throat_alive", lambda: True)
    monkeypatch.setattr(throat, "synthesize", _FakeThroat(crash=True))
    monkeypatch.setattr(voice, "_play_wav", lambda data: False)
    monkeypatch.setattr(voice, "available", lambda: True)
    monkeypatch.setattr(voice, "_VOICES_CACHE",
                        {"ts": 1e12, "voices": [("Microsoft Irina", "ru-RU")],
                         "error": ""})
    monkeypatch.setattr(voice, "_ps", lambda script, timeout: (0, ""))
    out = voice.speak("привет")
    assert "Microsoft Irina" in out


def test_speak_throat_alive_but_mouth_dead_honest(home, monkeypatch):
    """Честность до конца: горло сказало, но рта нет (winsound не завёлся,
    станция разработки) — отказ называет ОБЕ ступени, а не валит всё
    на PowerShell, которого тут и не спрашивали."""
    monkeypatch.setattr(voice, "_throat_alive", lambda: True)
    monkeypatch.setattr(throat, "synthesize",
                        _FakeThroat(ok=True, data=b"RIFF" + b"\x00" * 99))
    monkeypatch.setattr(voice, "_play_wav", lambda data: False)
    monkeypatch.setattr(voice, "available", lambda: False)
    out = voice.speak("привет")
    assert "рот" in out and "winsound" in out


def test_say_skips_sapi_gate_when_throat_alive(home, monkeypatch):
    """«скажи вслух» при живом горле не требует PowerShell-голосов:
   -preview честен, SAPI-гейт обойдён (горло — первый рот)."""
    monkeypatch.setattr(voice, "_throat_alive", lambda: True)
    monkeypatch.setattr(voice, "available",
                        lambda: pytest.fail("SAPI не должны спрашивать"))
    out = voice.say("Привет, Илья")
    assert out.startswith("произношу вслух")


def test_set_speaker_persists_and_reports(home, monkeypatch):
    """«голос ксения» — настройка в файле (переживает перезапуск),
    ответ честен про спящее горло: смена произойдёт, услышит после
    пробуждения. Чужое имя — честный список голосов."""
    _throat_asleep(monkeypatch)
    out = voice.set_speaker("ксения")
    assert "ксения" in out and "горло спит" in out
    settings = json.loads((home / "voice_settings.json").read_text(
        encoding="utf-8"))
    assert settings["throat_speaker"] == "kseniya"
    out2 = voice.set_speaker("ирину")
    assert "не знаю такого голоса" in out2 and "бая" in out2


def test_settings_default_and_armor(home):
    """Броня настроек: битый файл — честный бая по умолчанию; кривое
    имя спикера в файле — не падение, а возврат к канону."""
    settings = voice._load_settings()
    assert settings["throat_speaker"] == "baya"
    (home / "voice_settings.json").write_text(
        "{не json", encoding="utf-8")
    assert voice._load_settings()["throat_speaker"] == "baya"
    (home / "voice_settings.json").write_text(
        json.dumps({"throat_speaker": "чужой", "rate": 99}),
        encoding="utf-8")
    fixed = voice._load_settings()
    assert fixed["throat_speaker"] == "baya" and fixed["rate"] == 5


def test_route_voice_commands_through_gate(agent, home, monkeypatch):
    """ГЛАВНЫЙ МАРШРУТА Ф122 (урок дня-13: якорь органа без якоря
    маршрута — якорь половины): «голос бая» доезжает ЧЕРЕЗ КАЛИТКУ
    agent.handle — путём пользователя, не прямым вызовом органа."""
    _throat_asleep(monkeypatch)
    r = agent.handle("голос бая")
    assert r.source == "python" and r.tool_used == "voice"
    assert "бая" in r.text
    settings = json.loads((home / "voice_settings.json").read_text(
        encoding="utf-8"))
    assert settings["throat_speaker"] == "baya"
    r2 = agent.handle("смени голос на ксения")
    assert r2.source == "python" and "ксения" in r2.text
    r3 = agent.handle("какой голос")
    assert r3.source == "python" and "горло" in r3.text
    r4 = agent.handle("какие голоса")
    assert r4.source == "python" and "ксения" in r4.text \
        and "айдар" in r4.text


def test_voice_report_sleeping_throat_honest(home, monkeypatch):
    """«какой голос» при спящем горле и живом SAPI: честно называет
    запасной рот; оба спят — путь лечения (кнопка 95)."""
    _throat_asleep(monkeypatch)
    monkeypatch.setattr(voice, "available", lambda: True)
    monkeypatch.setattr(voice, "_VOICES_CACHE",
                        {"ts": 1e12, "voices": [("Microsoft Irina", "ru-RU")],
                         "error": ""})
    rep = voice.voice_report()
    assert "запасной рот" in rep and "Microsoft Irina" in rep
    monkeypatch.setattr(voice, "available", lambda: False)
    monkeypatch.setattr(voice, "_VOICES_CACHE",
                        {"ts": 0.0, "voices": [], "error": ""})
    rep2 = voice.voice_report()
    assert "голоса нет" in rep2 and "95" in rep2


def test_selftest_reports_sleeping_throat(home, monkeypatch):
    """«проверь голос» при спящем горле: прежний тест SAPI + честная
    строка про горло с путём пробуждения (якорь круга 10 «сухом
    режиме» цел — строка прежняя, новая добавлена, не подменена)."""
    _throat_asleep(monkeypatch)
    monkeypatch.setattr(voice, "available", lambda: False)
    out = voice.selftest()
    assert "сухом режиме" in out
    assert "горло (silero): спит" in out and "95_Горло.bat" in out


def test_diagnosis_mentions_throat_when_alive(home, monkeypatch):
    """Диагноз «статуса» видит цепь: горло живо — диагноз называет
    голосом бая и порт; якорь круга 10 при спящем горле цел."""
    monkeypatch.setattr(voice, "_throat_alive", lambda: True)
    assert "горло silero" in voice.diagnosis() and "бая" in voice.diagnosis()
    _throat_asleep(monkeypatch)
    monkeypatch.setattr(voice, "available", lambda: False)
    assert "PowerShell" in voice.diagnosis()


# ------------------------------------------------------------------- Ф123
# ЖИВОЙ ЯКОРЬ: орган кроссплатформенен (torch.package) — песочница
# архитектора слышит те же байты, что услышит станция. Орган спит
# (нет torch / нет модели — посылка не приехала) — честный skip.

@pytest.fixture(scope="module")
def live_throat():
    """Поднимает слугу В ПРОЦЕССЕ тестов (HTTPServer в потоке, модель
    грузится один раз на модуль). Живой слуга уже на порту (станция) —
    якорь гоняется по нему. Орган спит — честный skip с путём лечения."""
    if not throat.torch_present():
        pytest.skip("torch не установлен — орган спит; посылка: "
                    "docs/ТЗ_Голос_v2.md, раздел 7 (кнопка 95)")
    if not throat.find_model():
        pytest.skip("модели горла нет в чулане (models/voice/v5_6_ru.pt) — "
                    "посылка не приехала; ТЗ_Голос_v2.md, раздел 7")
    if throat.alive():
        yield None                     # станция: слуга уже служит
        return
    import sensors.throat as servant
    servant.load_model()
    from http.server import HTTPServer
    srv = HTTPServer(("127.0.0.1", config.PORT_THROAT), servant._Handler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    time0 = 0.0
    yield srv
    srv.shutdown()
    srv.server_close()


def test_live_throat_health(live_throat):
    """ЖИВОЙ /health: модель та самая (v5_6_ru), пять спикеров, порт
    8084 — слуга отчитывается о себе честно."""
    h = throat.health()
    assert h and h.get("ok") is True
    assert h.get("model") == "v5_6_ru.pt"
    assert set(h.get("speakers") or []) == {"baya", "kseniya", "xenia",
                                            "aidar", "eugene"}


def test_live_throat_speaks(live_throat):
    """ГЛАВНЫЙ ЖИВОЙ ЯКОРЬ Ф123: фраза → WAV-байты живы — RIFF-заголовок,
    длительность в человеческих рамках, не пустышка. Прежние якоря
    читали код — этот СЛЫШИТ голос (песочница = станция, орган
    кроссплатформен)."""
    ok, data = throat.synthesize("Марфа на связи. Слышно меня?", "baya")
    assert ok, data
    assert data[:4] == b"RIFF" and len(data) > 10000
    dur = throat.wav_duration_sec(data)
    assert 0.5 < dur < 30.0


def test_live_throat_intonation_alive(live_throat):
    """Интонация ЖИВА (вердикт Создателя: «восклицание — норм»): один
    текст, разные знаки — модель читает их сама, волны РАЗЛИЧАЮТСЯ
    байтами. Это то, за что выбрана v5_6 (v5_ru так не умела)."""
    ok_q, wav_q = throat.synthesize("Ты меня слышишь", "baya")
    ok_d, wav_d = throat.synthesize("Ты меня слышишь.", "baya")
    ok_e, wav_e = throat.synthesize("Ты меня слышишь!", "baya")
    assert ok_q and ok_d and ok_e
    assert wav_q != wav_d and wav_e != wav_d


def test_live_throat_speakers_differ(live_throat):
    """Смена голоса — не декларация: бая и ксения говорят одну фразу
    РАЗНЫМИ байтами (команда «голос ксения» меняет звучание дома)."""
    ok_b, wav_b = throat.synthesize("Привет, Илья", "baya")
    ok_k, wav_k = throat.synthesize("Привет, Илья", "kseniya")
    assert ok_b and ok_k and wav_b != wav_k


# ------------------------------------------------------------- круг 23-2
# РОТ v2.1: живой приём круга 23 вскрыл — в RDP-сеансе winsound (winmm)
# МОЛЧА отказывает: синтез есть (счётчик фраз слуги растёт), звука нет,
# цепь честно уходит в SAPI (Ирину слышно — WASAPI жив, winmm нет).
# Второй рот — PortAudio (sounddevice, стек ушей), БЕЗ NUMPY (закон
# правки 23.1: «почти наверняка есть — не закон»).


def _wav_bytes(rate=48000, n=2000):
    """Минимальный честный RIFF/PCM mono 16-bit — как отдаёт слуга."""
    header = (b"RIFF" + struct.pack("<I", 36 + n * 2) + b"WAVE"
              + b"fmt " + struct.pack("<IHHIIHH", 16, 1, 1, rate,
                                      rate * 2, 2, 16)
              + b"data" + struct.pack("<I", n * 2))
    return header + b"\x01\x00" * n


def test_mouth_second_rot_saves_silero(home, monkeypatch):
    """ГЛАВНЫЙ 23-2: winsound мёртв (живой урок RDP-станции), PortAudio
    жив — Марфа говорит ГОРИЛОМ: приговор silero/бая, SAPI не будили,
    байты доехали до второго рта ЦЕЛИКОМ."""
    monkeypatch.setattr(voice, "_throat_alive", lambda: True)
    wav = _wav_bytes()
    monkeypatch.setattr(throat, "synthesize",
                        lambda *a, **k: (True, wav))
    monkeypatch.setattr(voice, "_play_wav_winsound", lambda data: False)
    played = []
    monkeypatch.setattr(voice, "_play_wav_portaudio",
                        lambda data: played.append(data) or True)
    sapi = []
    monkeypatch.setattr(voice, "available",
                        lambda: sapi.append("ps") or True)
    out = voice.speak("Марфа на связи. Слышно меня?")
    assert "silero" in out and "бая" in out
    assert played and played[0] == wav      # второй рот получил те же байты
    assert not sapi                         # запасной рот не будили


def test_mouth_portaudio_numpy_free_and_honest(home):
    """Закон правки 23.1 — numpy «почти наверняка есть» НЕ закон: второй
    рот собран на stdlib + sounddevice (RawOutputStream ест байты, док:
    «NumPy is not necessary for using this»). Якорь читает исходник:
    ни одного numpy-импорта внутри органа; мусорный буфер — честный
    False, не крах (закон эфира)."""
    import ast
    tree = ast.parse(Path(voice.__file__).read_text(encoding="utf-8"))
    func = [n for n in ast.walk(tree)
            if isinstance(n, ast.FunctionDef)
            and n.name == "_play_wav_portaudio"]
    assert func, "орган второго рта не найден"
    imports = [ast.dump(n) for n in ast.walk(func[0])
               if isinstance(n, (ast.Import, ast.ImportFrom))]
    assert not any("numpy" in s for s in imports), \
        "второй рот нанял numpy — закон 23.1 нарушен"
    assert voice._play_wav_portaudio(b"NOTAWAVE" + b"\x00" * 99) is False
    assert voice._play_wav_portaudio(_wav_bytes()[:30]) is False


def test_mouth_fall_prints_honest_trace(home, monkeypatch, capsys):
    """Молчаливых ртов больше нет (урок круга 23-2): падение winsound
    печатает след в консоль дома — архитектор видит ступень, а не
    угадывает её по тишине."""
    monkeypatch.setattr(voice, "_play_wav_winsound", lambda data: False)
    monkeypatch.setattr(voice, "_play_wav_portaudio", lambda data: True)
    assert voice._play_wav(_wav_bytes()) is True
    outp = capsys.readouterr().out
    assert "PortAudio" in outp and "winsound" in outp
