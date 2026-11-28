# -*- coding: utf-8 -*-
"""tests/test_krug36_circle.py — якоря круга 36 «ХОЗЯИН VRAM, КАЛИТКА,
МОЗГ И РУКИ» (аудит Создателя, день-18 28.11.2026, части 4-5:
vram.py 269–280, creator_gate.py 281–305, brain.py 306–331,
motor.py 332–357).

Раздел 0 аудита (306–309) — ПРОВЕРЕН ПО ОРИГИНАлу И ЗАКРЫТ КАК
АРТЕФАКТЫ РЕНДЕРА (4/4, тот же почерк, что в пяти предыдущих файлах):
_VERBS_CLICK без хвостовых пробелов («нажми пуск» разбирается),
класс _norm_text экранирован (re.error не было), type(e).__name__ и
__init__ целы, split("+") без пробела. Пункты ниже — якоря на
ПОДТВЕРЖДЁННОЕ и починенное.
"""
from __future__ import annotations

import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from core import config, creator_gate, motor, vram
from safety import guard
from tests.fake_llama_server import start_fake_brain

WORD = "севрюжина"     # тестовое слово калитки (как в test_creator_gate)


@pytest.fixture()
def srv(monkeypatch):
    """Подставной мозг — как в test_brain.py (фикстуры не переезжают
    между файлами, закон pytest)."""
    server = start_fake_brain()
    monkeypatch.setattr(config, "BRAIN_URL", server.base_url)
    yield server
    server.shutdown()


@pytest.fixture()
def client(srv):
    from core import brain as brain_mod
    return brain_mod.BrainClient(brain_url=srv.base_url)


@pytest.fixture()
def repair_home(tmp_path, monkeypatch):
    """Дом для ремонтных якорей: в отличие от `home`, ensure_server и
    release НЕ подменены швами — проверяем САМУ церемонию заёма VRAM."""
    monkeypatch.setattr(config, "HOME_DIR", tmp_path)
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(config, "LOGS_DIR", tmp_path / "logs")
    monkeypatch.setattr(config, "MODELS_DIR", tmp_path / "models")
    monkeypatch.setattr(config, "PATCHES_DIR", tmp_path / "data" / "patches")
    monkeypatch.setattr(config, "REPAIR_LOG_FILE",
                        tmp_path / "logs" / "repair_log.jsonl")
    monkeypatch.setattr(config, "GUARD_LOG_FILE",
                        tmp_path / "logs" / "guard_log.jsonl")
    monkeypatch.setattr(config, "CANARIES_FILE",
                        tmp_path / "data" / "canaries.json")
    return tmp_path


# ================================================================
# VRAM: честная церемония (269–280)
# ================================================================

def test_forbidden_ports_refused(home):
    """Аудит 275: «убей свой мозг» больше не примитив. Мозг, панель и
    горло — вне закона церемонии; отказ громкий, с причиной."""
    res = vram.lay_down(config.PORT_BRAIN)
    assert res.status == "forbidden" and not res.ok
    assert "неприкосновенны" in res.text
    assert vram.lay_down(config.PORT_WEB).status == "forbidden"
    assert vram.lay_down(9999).status == "forbidden"
    # законные слуги — не отказ (даже если их там нет)
    assert vram.lay_down(config.PORT_EYES).status in ("no-server",
                                                      "could-not")


def test_port_of_reads_only_dash_port(home):
    """Аудит 273: порт — ТОЛЬКО аргумент --port (обе формы);
    контекстный -c 8083 портом не считается."""
    assert vram._port_of(["llama-server", "--port", "8083"]) == 8083
    assert vram._port_of(["llama-server", "--port=8083"]) == 8083
    assert vram._port_of(["llama-server", "--port", "8085",
                          "-c", "8083"]) == 8085
    assert vram._port_of(["tail", "-f", "llama-server.log"]) is None
    assert vram._port_of(["llama-server", "--port", "abc"]) is None


def test_arg_tokens_decode_bytes(home):
    """Аудит 280: bytes-аргументы декодируются, а не «b'--port'»."""
    toks = vram._arg_tokens([b"llama-server", b"--port", b"8083"])
    assert toks == ["llama-server", "--port", "8083"]


def test_lay_down_no_server_is_honest(home, monkeypatch):
    """Аудит 270: «сервера нет» — отдельный исход, не ложь в общем False."""
    seen = []

    class FakeProc:
        def __init__(self, info):
            self.info = info
            self.pid = 424242

    def iter_procs(attrs):
        seen.append(attrs)
        # ни один процесс не похож на слугу
        return iter([FakeProc({"pid": 1, "cmdline": ["bash"], "name": "bash"})])

    monkeypatch.setattr("psutil.process_iter", iter_procs)
    res = vram.lay_down(config.PORT_EYES)
    assert res.status == "no-server" and not res.ok
    assert seen  # процессы смотрели честно


def test_lay_down_no_psutil_is_a_status(home, monkeypatch):
    """Аудит 271: нет зависимости — это «не смогла», не «не нужно»:
    честная строка с лечением, а не молчаливый False."""
    import builtins
    real_import = builtins.__import__

    def no_psutil(name, *a, **kw):
        if name == "psutil":
            raise ImportError("нет psutil в этом доме")
        return real_import(name, *a, **kw)

    monkeypatch.setattr(builtins, "__import__", no_psutil)
    res = vram.lay_down(config.PORT_EYES)
    assert res.status == "no-psutil"
    assert "psutil" in res.text          # лечение — в строке, не в догадке


def test_lay_down_confirms_death_and_escalates(home, monkeypatch):
    """Аудит 269/276/279: terminate → wait → kill → wait → is_running:
    «уложили» — факт смерти, не факт вызова terminate()."""

    class FakeProc:
        def __init__(self):
            self.pid = 424243
            self.info = {"pid": 424243,
                         "cmdline": ["llama-server", "--port",
                                     str(config.PORT_EYES)],
                         "name": "llama-server"}
            self.terminated = 0
            self.killed = 0

        def terminate(self):
            self.terminated += 1

        def wait(self, timeout=None):
            if self.killed == 0 and self.terminated:
                # SIGTERM «перехвачен» — выжил (аудит: dev-Linux)
                import psutil
                raise psutil.TimeoutExpired(424243)

        def kill(self):
            self.killed += 1

    fake = FakeProc()
    monkeypatch.setattr("psutil.process_iter",
                        lambda attrs: iter([fake]))

    class DeadProcess:
        pass

    def process_of(pid):
        if pid == fake.pid and fake.killed:
            raise monkeypatch._module_stats and _NoProcess()
        raise _NoProcess()

    class _NoProcess(Exception):
        pass

    import psutil
    monkeypatch.setattr(psutil, "NoSuchProcess", _NoProcess)
    monkeypatch.setattr(psutil, "Process", process_of)
    res = vram.lay_down(config.PORT_EYES)
    assert res.status == "laid" and res.ok
    assert fake.terminated == 1 and fake.killed == 1   # эскалация была
    assert res.pids == [fake.pid]      # «уложили» — подтверждено фактом


def test_vram_ceremony_logged(home):
    """Аудит 277: убийство/поиск слуги — в logs/vram_log.jsonl: PID, порт,
    причина, свободная VRAM. «Логи — истина» работает и для церемонии."""
    vram.lay_down(config.PORT_EYES)      # хоть no-server — строка пишется
    log = Path(config.LOGS_DIR) / "vram_log.jsonl"
    assert log.is_file()
    rec = json.loads(log.read_text(encoding="utf-8").splitlines()[-1])
    assert rec["act"] == "no-server" and rec["port"] == config.PORT_EYES


def test_ensure_server_refuses_dance_when_eyes_stuck(repair_home, monkeypatch):
    """Аудит 269–271 (прописано Создателем): repair ОТКАЗЫВАЕТСЯ от
    танца, если глаза не уложены, — не идёт дальше в занятую VRAM."""
    from core import repair
    monkeypatch.setattr(repair, "server_alive", lambda: False)
    monkeypatch.setattr(repair, "_find_model",
                        lambda: Path(config.HOME_DIR) / "coder.gguf")
    monkeypatch.setattr(repair, "_spawn_server", lambda m: None)
    monkeypatch.setattr(vram, "lay_down",
                        lambda port, server_name="llama-server":
                        vram.StopResult("could-not", "не смогла"))
    ok, note = repair.ensure_server(wait_secs=1)
    assert ok is False
    assert "танец отменён" in note and "не смогла" in note


def test_ensure_server_eyes_absent_is_fine(repair_home, monkeypatch):
    """Аудит 270: «глаз не было» — НЕ отказ: VRAM свободна, танец честен."""
    from core import repair
    # кодер уже на посту; глаза на посту НЕ БЫЛО — не отказ, не «присели»:
    # честная строка «глаз на посту не было» вместо старой лжи одним bool
    monkeypatch.setattr(repair, "server_alive", lambda: True)
    monkeypatch.setattr(vram, "lay_down",
                        lambda port, server_name="llama-server":
                        vram.StopResult("no-server", ""))
    ok, note = repair.ensure_server(wait_secs=1)
    assert ok is True
    assert "глаз на посту не было" in note
    # и в танце подъёма: «глаза и не стояли» — не «присели» и не отказ
    monkeypatch.setattr(repair, "server_alive", lambda: False)
    monkeypatch.setattr(repair, "_find_model",
                        lambda: Path(config.HOME_DIR) / "coder.gguf")
    monkeypatch.setattr(repair, "_spawn_server", lambda m: None)
    ok, note = repair.ensure_server(wait_secs=1)
    assert ok is False                       # не ожил за 1 с — но не в этом суть
    assert "глаза и не стояли" in note


def test_release_does_not_raise_eyes_into_busy_vram(repair_home, monkeypatch):
    """Аудит 269: кодер НЕ лёг — глаза НЕ поднимаются: 4.7 занятых + 3.0
    свежих > 6 ГБ. Дом не изображает здоровье."""
    from core import repair
    healed = []
    monkeypatch.setattr(vram, "lay_down",
                        lambda port, server_name="llama-server":
                        vram.StopResult("could-not", "выжил"))
    import core.doctor as doctor
    monkeypatch.setattr(doctor, "heal", lambda organs: healed.append(1))
    note = repair.release()
    assert "НЕ ЛЁГ" in note and not healed


def test_vram_lock_released_after_ceremony(home):
    """Аудит 278: файловый замок разводит танцоров и СНИМАЕТСЯ за собой
    (протухший — по возрасту, живой — в finally)."""
    vram.lay_down(config.PORT_EYES)
    assert not (Path(config.DATA_DIR) / "vram.lock").exists()
    # повторная церемония не ждёт снятия собственного замка
    vram.lay_down(config.PORT_EYES)


# ================================================================
# КАЛИТКА: ротация, шифрование, атомарность, промахи (281–305)
# ================================================================

@pytest.fixture()
def gate_home(home):
    """Дом с живым .env: калитка открыта тестовым словом."""
    (Path(config.HOME_DIR) / ".env").write_text(
        "MARFA_CODEWORD=%s\n" % WORD, encoding="utf-8")
    return home


def test_rotation_keeps_creator_case(gate_home):
    """Аудит 281: payload режется с ИСХОДНОЙ строки — «ЧечевиЦа» не
    превращается в «чечевица» в .env (калитка больше не запирается
    регистром на ровном месте)."""
    hit, out = creator_gate.check(WORD + " новое слово: ЧечевиЦа")
    assert hit and "намерение запомнила" in out
    hit, out = creator_gate.check(WORD + " подтверждаю")
    assert hit and "сменено" in out
    env = (Path(config.HOME_DIR) / ".env").read_text(encoding="utf-8")
    assert "MARFA_CODEWORD=ЧечевиЦа" in env


def test_rotation_pending_is_sealed(gate_home):
    """Аудит 282: новое слово НЕ лежит открытым текстом в читаемой
    мозгом data/ — только шифровка под ключом из корня дома."""
    creator_gate.check(WORD + " новое слово: ТайноеСлово7")
    raw = (Path(config.DATA_DIR) / "gate_rotate.json").read_text(
        encoding="utf-8")
    assert "ТайноеСлово7" not in raw       # ни в каком виде
    rec = json.loads(raw)
    assert {"nonce", "box", "mac"} <= set(rec)   # это шифровка, не текст
    # ключ — в корне дома (мозгу туда закрыто замком Ф118)
    assert (Path(config.HOME_DIR) / ".gate_rotate.key").is_file()
    # и цикл цел: подтверждение расшифровывает и меняет слово
    hit, out = creator_gate.check(WORD + " подтверждаю")
    assert hit and "сменено" in out
    env = (Path(config.HOME_DIR) / ".env").read_text(encoding="utf-8")
    assert "MARFA_CODEWORD=ТайноеСлово7" in env


def test_env_rewrite_is_atomic_and_form_matched(gate_home):
    """Аудит 287/292: .env перезаписывается атомарно (tmp+replace, без
    обрезки живого файла) и находит строку с пробелом вокруг «=» —
    слово не плодит вторую строку, старое не остаётся навсегда."""
    env_file = Path(config.HOME_HOME if False else config.HOME_DIR) / ".env"
    env_file.write_text(
        "OTHER_KEY = 1\nMARFA_CODEWORD = %s\n" % WORD, encoding="utf-8")
    creator_gate.check(WORD + " новое слово: НовоеСлово9")
    hit, out = creator_gate.check(WORD + " подтверждаю")
    assert hit and "сменено" in out
    text = env_file.read_text(encoding="utf-8")
    assert text.count("MARFA_CODEWORD") == 1        # одна строка, не две
    assert "MARFA_CODEWORD=НовоеСлово9" in text
    assert "OTHER_KEY = 1" in text                  # чужие строки живы
    assert not (Path(config.HOME_DIR) / ".env.new").exists()  # tmp убран


def test_rotation_rejects_weak_and_distorting_words(gate_home):
    """Аудит 297/298/305: словарное слово, кавычки на краях, «#»/«=»
    (читатель .env их исказит) и ротация в то же слово — честные
    отказы, слово не меняется."""
    for bad in ("пароль", "слово'", "слово#", "слoво=1"):
        hit, out = creator_gate.check(WORD + " новое слово: " + bad)
        assert hit and "сменено" not in out, bad
    hit, out = creator_gate.check(WORD + " новое слово: " + WORD)
    assert hit and "совпадает с действующим" in out


def test_battery_codes_are_honest(gate_home, monkeypatch):
    """Аудит 288 (урок дня-18): коды 4 и 5 — «тесты НЕ НАШЛИСЬ / НЕ
    СОБРАЛИСЬ», а не «ЕСТЬ КРАСНЫЕ ТЕСТЫ». Красные — только код 1."""

    class FakeRun:
        def __init__(self, rc, out=""):
            self.returncode = rc
            self.stdout = out
            self.stderr = ""

    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd)
        return FakeRun(codes.pop(0), "строка вывода")

    codes = [4]
    monkeypatch.setattr("subprocess.run", fake_run)
    monkeypatch.setattr(creator_gate, "_gate_log", lambda *a, **kw: None)
    hit, out = creator_gate.check(WORD + " тесты")
    assert hit and "НЕ НАШЛИСЬ" in out and "КРАСНЫЕ" not in out
    codes = [5]
    hit, out = creator_gate.check(WORD + " тесты")
    assert hit and "НЕ СОБРАЛИСЬ" in out and "КРАСНЫЕ" not in out
    codes = [1]
    hit, out = creator_gate.check(WORD + " тесты")
    assert hit and "ЕСТЬ КРАСНЫЕ ТЕСТЫ" in out


def test_near_miss_intercepted_not_forwarded(gate_home, monkeypatch):
    """Аудит 285: промах на одну букву — локальный ответ: слово и промах
    не уезжают ни мозгу, ни в историю. Слова в ответе НЕТ."""
    hit, out = creator_gate.check("севрюжинв статус")
    assert hit is True
    assert "одну букву" in out
    assert WORD not in out
    # далёкое слово — путь обычный (False, None), как прежде
    hit2, out2 = creator_gate.check("селёдка статус")
    assert (hit2, out2) == (False, None)


def test_near_miss_case_mismatch_hint(gate_home):
    """Аудит 286: «Севрюжина статус» (заглавная) — подсказка про
    регистр, не молчаливый путь в мозг."""
    hit, out = creator_gate.check("Севрюжина статус")
    assert hit is True and "регистре" in out and WORD not in out


def test_near_miss_rate_limited(gate_home, monkeypatch):
    """Аудит 297: серия промахов — тормоз: после 5 попыток в окне калитка
    отвечает «слишком много», не давая перебирать в чате."""
    monkeypatch.setattr(creator_gate, "_ATTEMPTS_WINDOW_SEC", 600)
    seen = set()
    for i in range(creator_gate._ATTEMPTS_MAX + 2):
        hit, out = creator_gate.check("севрюжин%s статус" % chr(ord("а") + i))
        seen.add("тормоз" if "слишком много" in out else "мягко")
        assert hit is True
    assert "тормоз" in seen


def test_vocative_and_comma_boundary_open_gate(gate_home, monkeypatch):
    """Аудит 286: «Марфа, <слово> статус» и «<слово>, статус» —
    естественные формы речи Создателя открывают калитку; слитное
    «словостатус» — по-прежнему нет."""
    monkeypatch.setattr(creator_gate, "_cmd_status", lambda: "ОСМОТР")
    hit, out = creator_gate.check("Марфа, " + WORD + " статус")
    assert hit is True and out == "ОСМОТР"
    hit, out = creator_gate.check("Марфушка, " + WORD + " статус")
    assert hit is True
    hit, out = creator_gate.check(WORD + ", статус")
    assert hit is True and out == "ОСМОТР"
    hit, out = creator_gate.check(WORD + "статус")
    assert (hit, out) == (False, None)      # граница слова свята


def test_env_reader_forgives_export_and_comment(gate_home):
    """Аудит 290/291: «export MARFA_CODEWORD=…» и инлайн-комментарий
    «слово # моё» больше не запирают калитку молча."""
    (Path(config.HOME_DIR) / ".env").write_text(
        "export MARFA_CODEWORD=%s # моё слово\n" % WORD, encoding="utf-8")
    assert creator_gate._codeword() == WORD
    hit, _ = creator_gate.check(WORD + " статус")
    assert hit is True


def test_status_ram_one_arithmetic_and_url_sanitized(gate_home, monkeypatch):
    """Аудит 294/299: RAM — ОДНА арифметика (ГБ и процент из одного
    used); URL с кредитами в чат не уезжает."""

    class FakeVM:
        total = 64 * 2**30
        available = 16 * 2**30
        # psutil.used на Windows = total - free — ДРУГОЕ число: соблазн
        used = 48 * 2**30

    class FakePsutil:
        @staticmethod
        def virtual_memory():
            return FakeVM()

    import types
    fake_psutil = types.ModuleType("psutil")
    fake_psutil.virtual_memory = FakePsutil.virtual_memory
    monkeypatch.setitem(sys.modules, "psutil", fake_psutil)

    class FakeResp:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(url, timeout=None):
        assert "user:pass" not in url          # в ЗАПРОС уходит как есть
        return FakeResp()

    monkeypatch.setattr(creator_gate.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(config, "BRAIN_URL",
                        "http://user:pass@127.0.0.1:8082")
    out = creator_gate._cmd_status()
    assert "RAM: 48.0 / 64.0 ГБ (75.0%)" in out   # 64-16=48 и 48/64 — одно
    assert "user:pass" not in out                  # в ЧАТ — не уезжает


def test_git_honest_when_not_a_repo(gate_home, monkeypatch):
    """Аудит 295: не репозиторий — не «дерево чистое», а правда."""

    class FakeRun:
        def __init__(self):
            self.returncode = 128
            self.stdout = ""
            self.stderr = "fatal: not a git repository"

    monkeypatch.setattr("subprocess.run", lambda cmd, **kw: FakeRun())
    out = creator_gate._cmd_status()
    assert "не репозиторий" in out and "чистое" not in out


def test_unknown_command_named_and_negative_ts(gate_home):
    """Аудит 302/303: нераспознанная команда — с указанием ЧЕГО именно;
    намерение из будущего — снято, не вечное ожидание."""
    hit, out = creator_gate.check(WORD + " танцы")
    assert hit and "танцы" in out and "статус" in out   # и подсказка жива
    pend = Path(config.DATA_DIR) / "gate_rotate.json"
    pend.parent.mkdir(parents=True, exist_ok=True)
    pend.write_text(json.dumps({"v": 1, "nonce": "x", "box": "eA==",
                                "mac": "y", "ts": time.time() + 9999}),
                    encoding="utf-8")
    hit, out = creator_gate.check(WORD + " подтверждаю")
    assert hit and "БУДУЩЕМ" in out
    assert not pend.exists()                     # намерение снято


def test_gate_log_written_without_secrets(gate_home, monkeypatch):
    """Аудит 289: события калитки — в logs/gate_log.jsonl; само слово и
    payload туда не попадают никогда (журнал читается и без слова)."""
    monkeypatch.setattr(creator_gate, "_cmd_status", lambda: "ОСМОТР")
    creator_gate.check(WORD + " статус")
    log = Path(config.LOGS_DIR) / "gate_log.jsonl"
    assert log.is_file()
    raw = log.read_text(encoding="utf-8")
    assert WORD not in raw
    rec = json.loads(raw.splitlines()[-1])
    assert rec["event"] == "hit" and rec["cmd"] == "статус"


def test_permissions_live_behind_the_gate(gate_home, monkeypatch):
    """Аудит 284: моторика, самовнедрение и слежение — ЗА словом.
    Без слова — указатель; со словом — резолюция; страж при этом
    файлы мозгу не отдаёт (см. test_permissions_files_immutable)."""
    from core import agent as agent_mod

    class FakeBrain:
        calls = 0

        def ask_json(self, *a, **kw):
            self.calls += 1
            return {"answer": "мозг"}

    class FakeMemory:
        def recall(self, *a, **kw):
            return []

    a = agent_mod.Agent(brain=FakeBrain(), memory=FakeMemory())

    r = a.handle("включи моторику")
    assert "кнопка 91" in r.text and "калитк" in r.text
    assert FakeBrain.calls == 0 and not motor.enabled()

    r = a.handle(WORD + " включи моторику")
    assert motor.enabled() is True
    # честная резолюция, как у кнопки 91
    rec = json.loads(Path(config.HANDS_ENABLED_FILE).read_text(
        encoding="utf-8"))
    assert rec.get("resolution")
    motor.set_enabled(False)

    r = a.handle("разреши внедрять себя")
    assert "калитк" in r.text
    r = a.handle(WORD + " разреши внедрять себя")
    from core import repair
    assert repair.self_write_resolution() is not None
    repair.forbid_self_write()

    r = a.handle(WORD + " следи за экраном")
    assert r.tool_used == "creator_gate"


def test_permissions_files_immutable(home):
    """Аудит 284 (страж): файлы резолюций мозг больше не пишет —
    «разреши внедрять себя» нельзя получить пустым write_file."""
    for rel in ("data/self_write.json", "data/hands_enabled.json",
                "data/screen_watch.json"):
        v = guard.check_path(rel, mode="write")
        assert not v.allowed(), rel
        assert v.rule == "path.immutable"


# ================================================================
# МОЗГ: потолки, стрим, фоллбэк, журнал (306–331)
# ================================================================

class _SSEServer(ThreadingHTTPServer):
    """Подставной сервер с НАСТОЯЩИМ SSE — для настенных часов, ошибок
    и finish_reason (фейк-сервер тестов отвечает plain JSON)."""

    def __init__(self, chunks, error=None, finish="stop", drip=0.0):
        super().__init__(("127.0.0.1", 0), _SSEHandler)
        self.chunks = chunks
        self.error = error
        self.finish = finish
        self.drip = drip

    @property
    def base_url(self):
        return "http://%s:%d" % self.server_address[:2]


class _SSEHandler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        srv = self.server
        # тело читаем ДО ответа: нечитанный POST рвёт соединение раньше
        # ответа, и клиент видит пустоту вместо своих же дельт
        length = int(self.headers.get("Content-Length", 0))
        self.rfile.read(length)
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        if srv.error is not None:
            self.wfile.write(b'data: {"error": "%s"}\n\n'
                             % srv.error.encode())
            return
        for c in srv.chunks:
            piece = json.dumps({"choices": [{"delta": {"content": c}}]},
                               ensure_ascii=False)
            self.wfile.write(("data: %s\n\n" % piece).encode())
            if srv.drip:
                time.sleep(srv.drip)
        last = json.dumps({"choices": [{"delta": {}, "finish_reason":
                                        srv.finish}]})
        self.wfile.write(("data: %s\n\n" % last).encode())
        self.wfile.write(b"data: [DONE]\n\n")


@pytest.fixture()
def sse(request):
    srv = _SSEServer(*getattr(request, "param", ({},)))
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield srv
    srv.shutdown()


def test_stream_wall_clock_beats_dripping_server(monkeypatch):
    """Аудит 315: сервер, капающий дельтой, больше не держит воркер
    бесконечно — настенные часы останавливают генерацию."""
    from core import brain as brain_mod
    srv = _SSEServer(["а", "б", "в"], drip=0.4)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        client = brain_mod.BrainClient(brain_url=srv.base_url)
        monkeypatch.setattr(config, "BRAIN_TIMEOUT_SEC", 0.5)
        with pytest.raises(brain_mod.BrainError) as ei:
            client.ask_json("вопрос", on_text=lambda s: None)
        assert "настенных часов" in str(ei.value)
    finally:
        srv.shutdown()


def test_stream_error_is_not_silence():
    """Аудит 326: {"error": …} в SSE — честный BrainError, а не пустой
    ответ, выдающий себя за «мозг промолчал»."""
    from core import brain as brain_mod
    srv = _SSEServer(["а"], error="модель не загружена")
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        client = brain_mod.BrainClient(brain_url=srv.base_url)
        with pytest.raises(brain_mod.BrainError) as ei:
            client.ask_json("вопрос", on_text=lambda s: None)
        assert "модель не загружена" in str(ei.value)
    finally:
        srv.shutdown()


def test_stream_finish_reason_and_throttle():
    """Аудит 319/327: finish_reason доезжает до ответа (обрезка ≠ кривой
    JSON); on_text зовётся не на каждой дельте — троттлинг эфира."""
    from core import brain as brain_mod
    srv = _SSEServer(['{"answer": "'] + ["дельта-%d " % i
                                           for i in range(40)] + ['"}'],
                     finish="length")
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        client = brain_mod.BrainClient(brain_url=srv.base_url)
        calls = []
        data = client._post_stream(
            "/v1/chat/completions",
            {"messages": [{"role": "user", "content": "вопрос"}]},
            lambda s: calls.append(s))
        # finish_reason ДОЕЗЖАЕТ до ответа (обрезка ≠ кривой JSON)
        fr = data["choices"][0]["message"].get("finish_reason")
        assert fr == "length"
        assert "дельта-0" in data["choices"][0]["message"]["content"]
        # 40 дельт мгновенно → первый эмит + финальный хвост: не 40 раз
        assert len(calls) <= 3
    finally:
        srv.shutdown()


def test_history_capped_inside_client(client, srv, monkeypatch):
    """Аудит 310: история — с потолком ВНУТРИ клиента: бомба 8268 не
    переехала из конфига в ask_json (второй замок после render_messages)."""
    from core import brain as brain_mod
    monkeypatch.setattr(config, "HISTORY_BUDGET_TOKENS", 30)
    srv.reply_content = '{"answer": "ок"}'
    huge = [{"role": "user", "content": "длинный-ход-%d " % i + "х" * 200}
            for i in range(20)] + [{"role": "assistant", "content": "ок"}]
    client.ask_json("вопрос", history=huge)
    sent = srv.calls[-1]["messages"]
    assert 2 < len(sent) <= 5           # система + уцелевший хвост + новый ход


def test_turn_context_capped_with_marker(client, srv):
    """Аудит 311: подвижный контекст — второй неучтённый член: потолок
    с честным маркером, свежий хвост (конец блока) выживает."""
    srv.reply_content = '{"answer": "ок"}'
    ctx = "СТАРЫЙ-ГОЛОВА " + "д" * 5000 + "\nСВЕЖИЙ-ХВОСТ: батарея зелёная"
    client.ask_json("вопрос", turn_context=ctx)
    sent = srv.calls[-1]["messages"][-1]["content"]
    assert len(sent) < 2400
    assert "СВЕЖИЙ-ХВОСТ" in sent          # хвост контекста жив
    assert "обрезано" in sent              # маркер честен


def test_ask_json_zero_max_tokens_has_floor(client, srv):
    """Аудит 316: max_tokens=0 → нижняя граница 1 (фикс M1 доведён до
    ask_json), а не пустота и ретрай."""
    srv.reply_content = '{"answer": "ок"}'
    client.ask_json("вопрос", max_tokens=0)
    assert srv.calls[-1]["max_tokens"] >= 1


def test_strip_think_handles_unclosed_block():
    """Аудит (средние): обрезанный по длине think-блок без хвоста —
    стриппер забирает и его, JSON выживает. Тег берём из самого
    стриппера: якорь не хардкодит теги модели (сборки меняются)."""
    from core import brain as brain_mod
    parts = brain_mod._THINK_RE.pattern.split(".*?")
    open_tag, close_tag = parts[0], parts[1]
    # оборванный блок (обрезка по max_tokens): хвоста нет — до конца
    assert brain_mod._strip_think(
        open_tag + "оборванное думание без хвоста") == ""
    # закрытый блок перед JSON — как прежде, JSON выживает
    assert brain_mod._strip_think(
        open_tag + "думание" + close_tag + ' {"answer": "жив"}') \
        == '{"answer": "жив"}'


def test_mood_all_or_nothing(home, monkeypatch):
    """Аудит (средние): битый top_p роняет характер ЦЕЛИКОМ — докстринг
    «полумеры опаснее дефолта» стал правдой кода."""
    from core import brain as brain_mod
    doctrine = Path(config.DATA_DIR) / "creator_doctrine.json"
    monkeypatch.setattr(config, "DOCTRINE_FILE", doctrine)
    doctrine.parent.mkdir(parents=True, exist_ok=True)
    doctrine.write_text(json.dumps(
        {"mood": {"temperature": 0.6, "top_p": 9.9}}), encoding="utf-8")
    assert brain_mod.mood_params() == {}
    doctrine.write_text(json.dumps(
        {"mood": {"temperature": 0.6, "top_p": 0.8}}), encoding="utf-8")
    assert brain_mod.mood_params() == {"temperature": 0.6, "top_p": 0.8}


def test_extract_content_multimodal_and_types():
    """Аудит (средние): content=null → «», список частей → склеенный
    текст, мусор — честный BrainError (не «мозг недоступен»)."""
    from core import brain as brain_mod
    assert brain_mod._extract_content(
        {"choices": [{"message": {"content": None}}]}) == ""
    assert brain_mod._extract_content(
        {"choices": [{"message": {"content": [
            {"type": "text", "text": "при"},
            "вет"]}}]}) == "привет"
    with pytest.raises(brain_mod.BrainError):
        brain_mod._extract_content(
            {"choices": [{"message": {"content": 42}}]})


def test_log_brain_call_survives_nonstring_answer():
    """Аудит (средние): не-строчный answer не убивает строку журнала —
    самая ценная улика не теряется молча."""
    from core import brain as brain_mod
    brain_mod._log_brain_call("ask_json", "", "", None, 1.0, True,
                              {"answer": ["список", "вместо", "текста"]})
    log = Path(config.BRAIN_LOG_FILE)
    rec = json.loads(log.read_text(encoding="utf-8").splitlines()[-1])
    assert rec["ok"] is True and "список" in rec["answer"]


def test_chat_logged_with_answer(client, srv):
    """Аудит (средние): ответ чат-трока — в журнале («хвост brain» не
    пустует для дневника/мыслей/рефлексии)."""
    from core import brain as brain_mod
    srv.reply_content = "ответ дневника"
    client.chat([{"role": "user", "content": "привет"}])
    log = Path(config.BRAIN_LOG_FILE)
    rec = json.loads(log.read_text(encoding="utf-8").splitlines()[-1])
    assert rec["kind"] == "chat" and rec["answer"] == "ответ дневника"


def test_kill_thinking_inserts_minimal_system():
    """Аудит (средние): список БЕЗ системного сообщения — /no_think
    вставляется минимальной статичной строкой (дневник/мысли не платят
    за невидимое думание)."""
    from core import brain as brain_mod
    payload = {"messages": [{"role": "user", "content": "привет"}]}
    brain_mod._kill_thinking(payload)
    assert payload["messages"][0]["role"] == "system"
    assert payload["messages"][0]["content"].endswith("/no_think")


def test_url_trailing_slash_normalized(client, srv):
    """Аудит (средние): BRAIN_URL с хвостовым «/» не даёт //health."""
    from core import brain as brain_mod
    slashed = brain_mod.BrainClient(brain_url=srv.base_url + "/")
    assert slashed.health() is True


def test_no_pytest_branch_in_production_code():
    """Аудит 329: тестовой ВЕТКИ в боевом коде больше нет (слово в
    комментарии урока — не ветка); скорость батареи — в conftest."""
    src = Path(__file__).resolve().parent.parent.joinpath(
        "core", "brain.py").read_text(encoding="utf-8")
    assert 'os.environ.get("PYTEST_CURRENT_TEST")' not in src
    assert "if PYTEST_CURRENT_TEST" not in src


def test_last_usage_reset_on_error(client, monkeypatch):
    """Аудит (средние): после падения мозга last_usage пуст — штамп
    пустого ответа не показывает чужие токены."""
    from core import brain as brain_mod
    client.last_usage = {"prompt_tokens": 999, "completion_tokens": 999}
    monkeypatch.setattr(client, "url", "http://127.0.0.1:1")
    with pytest.raises(brain_mod.BrainError):
        client.chat([{"role": "user", "content": "ты тут?"}])
    assert client.last_usage == {}


# ================================================================
# РУКИ: резолюция, клавиши, сверка, страж, экзамен (332–357)
# ================================================================

def test_enabled_requires_honest_resolution(home):
    """Аудит 332: пустой файл и мусор НЕ включают моторику — только
    честная JSON-резолюция (как пишет кнопка 91 и калитка)."""
    f = Path(config.HANDS_ENABLED_FILE)
    f.parent.mkdir(parents=True, exist_ok=True)
    assert motor.enabled() is False
    f.write_text("", encoding="utf-8")
    assert motor.enabled() is False            # пустой файл — не резолюция
    f.write_text("мусор", encoding="utf-8")
    assert motor.enabled() is False
    f.write_text("{}", encoding="utf-8")
    assert motor.enabled() is True             # валидный словарь — резолюция
    f.write_text(json.dumps({"resolution": "кнопка 91"}),
                 encoding="utf-8")
    assert motor.enabled() is True
    assert "выключена" in motor.set_enabled(False)
    assert motor.enabled() is False


def test_latin_button_is_click_not_hotkey():
    """Аудит 333: «нажми Send/OK/Save» — КЛИК по кнопке английского
    интерфейса, а не «сочетание не в whitelist»; «enter» — клавиша;
    «ctrl c» — сочетание."""
    assert motor.parse_task("нажми Send")["verb"] == "click"
    assert motor.parse_task("нажми Save")["target"] == "Save"
    assert motor.parse_task("нажми enter") == {"verb": "hotkey",
                                               "combo": "enter"}
    assert motor.parse_task("нажми ctrl c") == {"verb": "hotkey",
                                                "combo": "ctrl+c"}


def test_type_keeps_exclamation_mark():
    """Аудит (р4 №20): «напечатай Привет!» печатает «Привет!» — «!» это
    данные, не интонация."""
    assert motor.parse_task("напечатай Привет!")["text"] == "Привет!"
    assert motor.parse_task("напечатай Стоп.")["text"] == "Стоп."
    # у клика пунктуация цели нормализуется сверкой — там режем
    assert motor.parse_task("нажми Пуск!")["target"] == "Пуск"


def test_scale_point_refuses_incomplete_geometry():
    """Аудит 334/335: неполные размеры — честный отказ (ValueError), а
    не «страховка» кадровыми координатами и не ZeroDivisionError."""
    for real, sent in ((None, (100, 50)), ((1920, 1080), None),
                       ((1920, 1080), (0, 50)), ((1920, 1080), (100, 0)),
                       ((0, 1080), (100, 50)), ((1920, 0), (100, 50)),
                       ((1920, 1080), (100,)), ("", "")):
        with pytest.raises(ValueError):
            motor.scale_point(10, 10, real, sent)
    # полная геометрия — как прежде
    assert motor.scale_point(50, 25, (2000, 1000), (1000, 500)) == (100, 50)


def test_find_element_word_boundaries_and_ambiguity():
    """Аудит 336: «ус» больше не матчит «пуск» (границы слов);
    «Пуск» понимает «кнопку Пуска» (начала слов); «Сохранить» и
    «Сохранить как» — честный вопрос, а не тихий первый."""
    d = {"elements": [
        {"text": "пуск", "bbox": [0, 0, 10, 10], "confidence": 0.9},
    ]}
    assert motor.find_element(d, "ус") is None
    assert motor.find_element(d, "нажми кнопку Пуска")["text"] == "пуск"
    # «пуск» НЕ кликает «Запуск приложения» — начало слова, не середина
    d2 = {"elements": [
        {"text": "Запуск приложения", "bbox": [0, 0, 10, 10],
         "confidence": 0.9},
    ]}
    assert motor.find_element(d2, "пуск") is None
    d3 = {"elements": [
        {"text": "Пуск", "bbox": [0, 0, 10, 10], "confidence": 0.9},
        {"text": "Пуск меню", "bbox": [20, 0, 40, 10],
         "confidence": 0.9},
    ]}
    with pytest.raises(motor.AmbiguousTarget) as ei:
        motor.find_element(d3, "пуска")          # «кнопку Пуска» — кому?
    assert "Пуск меню" in ei.value.candidates
    # точное совпадение — по-прежнему без вопросов
    assert motor.find_element(d3, "Пуск меню")["text"] == "Пуск меню"


def test_guard_action_unknown_is_deny_and_scroll_explicit():
    """Аудит 339: страж моторики не fail-open — неизвестное действие
    ОТКАЗ; scroll — явная ветка с проверкой направления; клик без
    размеров экрана — отказ, не выдуманные границы."""
    v = motor.guard_action("format", ("c:",), None)
    assert not v.allowed() and "неизвестное" in v.reason
    v = motor.guard_action("scroll", ("left",), None)
    assert not v.allowed()
    v = motor.guard_action("scroll", ("down",), None)
    assert v.allowed()
    v = motor.guard_action("click", (10, 10), None)
    assert not v.allowed() and "размеров" in v.reason


def test_looking_marks_stay_in_verb_position(home, monkeypatch):
    """Аудит (средние): «нажми кнопку Прочитай» и «напечатай текст про
    камеру» — задания РУК; «включи камеру» и «руки, посмотри на экран»
    — к глазам (предметные метки — в первых двух словах, глагольные —
    префикс)."""
    monkeypatch.setattr("core.motor._do_click",
                        lambda t, target, m: ["КЛИК-ШОВ"])
    monkeypatch.setattr("core.motor._do_paste",
                        lambda t, text, m: ["ПЕЧАТЬ-ШОВ"])
    out = motor.run("нажми кнопку Прочитай")
    assert "КЛИК-ШОВ" in out and "не смотрят" not in out
    out = motor.run("напечатай текст про камеру")
    assert "ПЕЧАТЬ-ШОВ" in out and "не смотрят" not in out
    assert "не смотрят" in motor.run("включи камеру")
    assert "не смотрят" in motor.run("руки, посмотри на экран")
    assert "не смотрят" in motor.run("сделай скриншот")


def test_run_logs_outcome_and_dry_click_ok(home, monkeypatch):
    """Аудит (средние): журнал рук отвечает «кликнула ли» (ok — по
    строкам ответа); сухой клик — ok без моторики."""
    from core import eyes as eyes_mod
    monkeypatch.setattr(eyes_mod, "_VISION_ERROR", "")
    monkeypatch.setattr(eyes_mod, "health", lambda: True)
    monkeypatch.setattr(eyes_mod, "describe_with_sizes",
                        lambda: ({"elements": [
                            {"text": "Пуск", "bbox": [10, 10, 110, 60],
                             "confidence": 0.95}]},
                            (1920, 1080), (960, 540)))
    motor.run("нажми Пуск")
    log = Path(config.HANDS_LOG_FILE)
    rec = json.loads(log.read_text(encoding="utf-8").splitlines()[-1])
    assert rec["verb"] == "click" and rec["ok"] is True
    assert rec["mode"] == "dry"


def test_simple_action_logs_length_not_text(home, monkeypatch):
    """Аудит (средние): журнал рук хранит ДЛИНУ печати, а не сам текст —
    печать Создателя не лежит в читаемой мозгом папке."""
    monkeypatch.setattr(motor, "_execute", lambda name, args: "шов")
    monkeypatch.setattr(motor, "_pixel_check_after", lambda: [])
    motor._do_simple("напечатай секрет-привет", "type",
                     ("секрет-привет",), "печать", False)
    log = Path(config.HANDS_LOG_FILE)
    rec = json.loads(log.read_text(encoding="utf-8").splitlines()[-1])
    assert rec["args"] == [13]      # len("секрет-привет")
    # сама ПЕЧАТЬ не лежит в args (аудит: [len], как в _do_paste);
    # task — команда Создателя, её журнал хранит всегда (закон лога)
    assert not any(isinstance(a, str) and "секрет" in a
                   for a in rec["args"])


def test_multiline_latin_goes_through_buffer(home, monkeypatch):
    """Аудит (средние): многострочная латиница — через буфер и ctrl+v
    (pyautogui.write не умеет переводы строк)."""
    called = {}
    monkeypatch.setattr(motor, "_do_paste",
                        lambda t, text, m: called.setdefault("paste", text)
                        or ["шов"])
    motor.run("напечатай hello\nworld")
    assert called.get("paste") == "hello\nworld"


def test_exam_respects_confidence_threshold(home, monkeypatch):
    """Аудит 337: экзамен подчиняется §10.3 — неуверенный Пуск не
    экзаменуется; провал — в журнале рук (экзамен без следа не
    уезжает)."""
    from core import eyes as eyes_mod
    monkeypatch.setattr(eyes_mod, "_VISION_ERROR", "")
    monkeypatch.setattr(eyes_mod, "health", lambda: True)
    monkeypatch.setattr(eyes_mod, "describe_with_sizes",
                        lambda: ({"elements": [
                            {"text": "Пуск", "bbox": [10, 10, 110, 60],
                             "confidence": 0.42}]},
                            (1920, 1080), (960, 540)))
    monkeypatch.setattr(motor, "enabled", lambda: True)
    out = motor.exam()
    assert "неуверенно" in out and "0.42" in out
    log = Path(config.HANDS_LOG_FILE)
    rec = json.loads(log.read_text(encoding="utf-8").splitlines()[-1])
    assert rec["exam"] is True and rec["ok"] is False


def test_exam_survives_bboxless_start(home, monkeypatch):
    """Аудит 338: Пуск без бокса — честный отказ (не KeyError сквозь
    мёртвый [0,0,0,0]-фальшбэк), след — в журнале."""
    from core import eyes as eyes_mod
    monkeypatch.setattr(eyes_mod, "_VISION_ERROR", "")
    monkeypatch.setattr(eyes_mod, "health", lambda: True)
    monkeypatch.setattr(eyes_mod, "describe_with_sizes",
                        lambda: ({"elements": [
                            {"text": "Пуск", "confidence": 0.9}]},
                            (1920, 1080), (960, 540)))
    out = motor.exam()
    assert "не нашли Пуск" in out        # безбоксовый — не кандидат


def test_eyes_seams_survive_rename(home, monkeypatch):
    """Аудит (средние): приватные швы соседа (глаз) через getattr —
    пропажа _VISION_ERROR не роняет руки (getattr-умолчание), пропажа
    _screenshot_b64 — честный RuntimeError с именем шва, не AttributeError."""
    from core import eyes as eyes_mod
    monkeypatch.delattr(eyes_mod, "_VISION_ERROR", raising=False)
    monkeypatch.setattr(eyes_mod, "health", lambda: True)
    # _VISION_ERROR пропал — руки не падают: говорят с живыми глазами
    assert motor._eyes_or_honest() is eyes_mod
    # инструмент снимка пропал — честный отказ с причиной
    monkeypatch.delattr(eyes_mod, "_screenshot_b64", raising=False)
    with pytest.raises(RuntimeError) as ei:
        motor._screenshot()
    assert "снимка" in str(ei.value)


def test_paste_saves_and_restores_buffer(home, monkeypatch):
    """Аудит (средние): печать кириллицы — билет туда-обратно: буфер
    Создателя сохранён ДО, сверен ПОСЛЕ записи, возвращен ПОСЛЕ
    вставки; подмена при записи — отказ без вставки."""
    from core import hands as hands_mod
    state = {"buf": "старый буфер Создателя"}
    monkeypatch.setattr(hands_mod, "clipboard_save_raw",
                        lambda: state["buf"])
    monkeypatch.setattr(hands_mod, "clipboard_write",
                        lambda text: (state.__setitem__("buf", text)
                                      or "В буфере: %d символов."
                                      % len(text)))
    monkeypatch.setattr(hands_mod, "clipboard_restore",
                        lambda text: (state.__setitem__("buf", text)
                                      or "вернула"))
    monkeypatch.setattr(motor, "_execute",
                        lambda name, args: "вставила")
    monkeypatch.setattr(motor, "_pixel_check_after", lambda: [])
    lines = motor._do_paste("напечатай Привет", "Привет", True)
    assert "вставила" in lines[1]
    assert state["buf"] == "старый буфер Создателя"   # возвращён

    # подмена: запись сказала одно, чтение — другое → отказ
    def bad_write(text):
        state["buf"] = "СОВСЕМ ДРУГОЕ"
        return "В буфере."

    monkeypatch.setattr(hands_mod, "clipboard_write", bad_write)
    lines = motor._do_paste("напечатай Привет", "Привет", True)
    assert any("подменил" in l for l in lines)
