# -*- coding: utf-8 -*-
"""КРУГ 17 «ДЕЖУРНЫЙ РЕЖИМ И ГИГИЕНА» (день-13, вечер) — Ф94–Ф96, Ф98, Ф99.

Две дыры, о которых мастер-ТЗ молчало, закрыты по разведке архитектора:

1. ДЕЖУРНЫЙ РЕЖИМ (открытый вопрос №3 из СТАТУСА — третья ступень
   fallback): мозг мёртв — дом НЕ гаснет. Рефлексы не зовут мозг ПО
   ПОСТРОЕНИЮ, но Создатель об этом не знал: сбой говорил «мозг
   недоступен» и лечение, а живучесть дома — молчала. Теперь сбой сам
   несёт витрину (Ф94), а «что ты можешь без мозга» — живой рефлекс
   (Ф95), работающий в том числе при мёртвом мозге (та же таблица
   роутинга, что и в бою).

2. ГИГИЕНА ЖУРНАЛОВ: копилки дома (brain, ears, monitor, repair,
   hands) пишутся каждым ходом и живут месяцами — ТЗ о них молчало,
   а «пульс» читал файл ЦЕЛИКОМ. Теперь один закон для всех писателей
   (Ф96: дверь append_line, 8 МБ × 3 архива), читатели ходят по
   ограниченному множеству (Ф98: ротация среди дня не роняет
   «сегодня»), «гигиена» показывает журналы лицом (Ф99). Страж —
   хеш-цепь (ТЗ 3.7), ротации не подлежит: честное исключение с
   причиной, не забытость.

Нумерация: Ф97 занята монитором RAM (волна 0) — круг честно обходит
занятое число, не перенумеровывая историю.
"""
import datetime as dt
import json
import os
import time
from pathlib import Path

import pytest

from core import config, creator_gate, daypulse, energy, loghygiene
from core.agent import Agent
from core.brain import BrainClient
from core.identity import DUTY_GROUPS, FAST_COMMANDS, duty_names, duty_report, manifest_slim
from core.memory import Memory
from safety import guard
from tests.fake_llama_server import start_fake_brain


@pytest.fixture()
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("MARFA_HOME", str(tmp_path))
    monkeypatch.setattr(config, "HOME_DIR", tmp_path)
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(config, "LOGS_DIR", tmp_path / "logs")
    monkeypatch.setattr(config, "BRAIN_LOG_FILE", tmp_path / "logs" / "brain_log.jsonl")
    monkeypatch.setattr(config, "EARS_LOG_FILE", tmp_path / "logs" / "ears_log.jsonl")
    monkeypatch.setattr(config, "MONITOR_LOG_FILE", tmp_path / "logs" / "monitor_log.jsonl")
    monkeypatch.setattr(config, "REPAIR_LOG_FILE", tmp_path / "logs" / "repair_log.jsonl")
    monkeypatch.setattr(config, "HANDS_LOG_FILE", tmp_path / "logs" / "hands_log.jsonl")
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
    return Agent(brain=BrainClient(brain_url=srv.base_url), memory=mem,
                 doctrine="Тестовая доктрина дежурства")


# ---------- Ф95 «ЧТО ТЫ МОЖЕШЬ БЕЗ МОЗГА» ----------

def test_duty_names_all_real():
    """ЯКОРЬ ПРОТИВ ДРЕЙФА: каждое имя витрины живёт в корпусе
    FAST_COMMANDS. Дежурство не имеет права обещать то, чего дом не
    умеет: команда, переименованная в роутинге, выпадает из корпуса —
    якорь падает и витрину велят пересобрать (урок: источник один)."""
    corpus = " || ".join(FAST_COMMANDS)
    for name in duty_names():
        assert name in corpus, "витрина обещает то, чего нет в манифесте: " + name


def test_duty_report_command_reflex(agent, srv):
    """«Что ты можешь без мозга» — рефлекс: мозг молчит (srv.calls
    пуст), отвечает сама архитектура; граница честная — свободный
    разговор назван ждущим мозга."""
    r = agent.handle("что ты можешь без мозга")
    assert r.source == "python" and r.tool_used == "duty"
    assert not srv.calls, "дежурная витрина не имеет права звать мозг"
    text = r.text.lower()
    assert "рефлекс" in text and "медиан" not in text
    assert "ждут мозга" in text or "ждёт мозга" in text


def test_duty_command_variants(agent, srv):
    """Живые имена вопроса: «дежурный режим» и «что живо без мозга» —
    та же витрина (Создатель говорит по-разному, дом понимает одно)."""
    for q in ("дежурный режим", "что живо без мозга",
              "что работает без мозга"):
        r = agent.handle(q)
        assert r.tool_used == "duty", "вариант «%s» не дошёл до витрины" % q
    assert not srv.calls


def test_duty_names_in_slim_manifest():
    """Диета (Ф76): имена ездят в стройном манифесте — мозг знает
    витрину и может подсказать её Создателю дословно."""
    slim = manifest_slim()
    assert "что ты можешь без мозга" in slim
    assert "гигиена" in slim


def test_duty_report_groups_render():
    """Витрина рисует все группы и заголовок закона — не список имён
    без контекста, а портрет: что живо и что ждёт."""
    text = duty_report()
    for title, _names in DUTY_GROUPS:
        assert title in text, "витрина потеряла группу: " + title
    assert text.startswith("Рефлексы дома")


# ---------- Ф94 «ДЕЖУРНЫЙ ОТВЕТ» ----------

def test_fallback_carries_duty(agent, monkeypatch):
    """Мозг мёртв — сбой несёт не только диагноз и лечение, но и
    ДЕЖУРНУЮ СТРОКУ: рефлексы живы, у Создателя есть путь в доме,
    который не зависит от 30B. Третья ступень fallback — закрытый
    открытый вопрос №3 из СТАТУСА."""
    monkeypatch.setattr(agent.brain, "url", "http://127.0.0.1:1")
    r = agent.handle("длинный вопрос, требующий размышлений")
    assert r.source == "fallback"
    assert "мозг недоступен" in r.text
    assert "Дежурный режим" in r.text
    assert "что ты можешь без мозга" in r.text
    # витрина в сбое — имена без плейсхолдеров: разговорные, не технические
    assert "<" not in r.text.split("Дежурный режим")[1].split("…")[0]


def test_fallback_duty_names_are_real(agent, monkeypatch):
    """Имена дежурной строки сбоя — из той же витрины (источник один);
    якорь против второй вручную склеенной копии списка."""
    monkeypatch.setattr(agent.brain, "url", "http://127.0.0.1:1")
    r = agent.handle("ещё один думающий вопрос")
    line = r.text.split("Дежурный режим")[1].split("…")[0]
    corpus = " || ".join(FAST_COMMANDS)
    for name in [n.strip(", ") for n in line.split("— ")[-1].split(",")]:
        if name:
            assert name in corpus, "сбой обещает несуществующее: " + name


def test_reflexes_alive_while_brain_dead(agent, monkeypatch):
    """ГЛАВНЫЙ ЯКОРЬ КРУГА: при мёртвом мозге рефлексы отвечают —
    «время» живо, «пульс» жив, витрина жива. Дом не гаснет — это
    устройство архитектуры, а не обещание в тексте."""
    monkeypatch.setattr(agent.brain, "url", "http://127.0.0.1:1")
    r1 = agent.handle("время")
    assert r1.source == "python", "время умерло вместе с мозгом"
    r2 = agent.handle("пульс")
    assert r2.source == "python" and r2.tool_used == "pulse"
    r3 = agent.handle("что ты можешь без мозга")
    assert r3.tool_used == "duty"


# ---------- Ф96 «РОТАЦИЯ ЖУРНАЛОВ» ----------

def test_rotation_creates_archives(home, monkeypatch):
    """Порог мал — дверь закрывает переполненный журнал в архив
    путь.1.jsonl; имена архивов узнаваемы для «хвост brain» (rglob
    по части имени находит их без нового закона)."""
    monkeypatch.setattr(config, "LOG_ROTATE_BYTES", 120)
    monkeypatch.setattr(config, "LOG_ROTATE_KEEP", 2)
    p = Path(config.BRAIN_LOG_FILE)
    p.parent.mkdir(parents=True, exist_ok=True)
    for i in range(5):
        loghygiene.append_line(p, '{"i": %d, "pad": "%s"}\n'
                              % (i, "x" * 60))
    assert p.exists()
    arc1 = p.with_name("brain_log.1.jsonl")
    arc2 = p.with_name("brain_log.2.jsonl")
    arc3 = p.with_name("brain_log.3.jsonl")
    assert arc1.exists(), "ротация не закрыла журнал в архив"
    assert arc2.exists(), "второй архив не сдвинулся"
    assert not arc3.exists(), "глубина закона нарушена (keep=2)"


def test_rotation_bounded_and_oldest_gone(home, monkeypatch):
    """Много ротаций — множество ОГРАНИЧЕНО: живёт не больше keep
    архивов, старейший честно уходит (диск не бесконечен — закон,
    а не пожелание)."""
    monkeypatch.setattr(config, "LOG_ROTATE_BYTES", 80)
    monkeypatch.setattr(config, "LOG_ROTATE_KEEP", 2)
    p = Path(config.BRAIN_LOG_FILE)
    p.parent.mkdir(parents=True, exist_ok=True)
    first = '{"marker": "самый старый"}\n'
    loghygiene.append_line(p, first)
    for i in range(12):
        loghygiene.append_line(p, '{"i": %d, "pad": "%s"}\n'
                              % (i, "y" * 60))
    arcs = [q for q in loghygiene.recent_paths(p) if q != p]
    assert len(arcs) <= 2, "архивов больше закона"
    total = "".join(q.read_text(encoding="utf-8") for q in arcs)
    assert "самый старый" not in total, "старейший не ушёл — диск течёт"


def test_rotation_not_below_threshold(home):
    """Маленький журнал не ротируется: лениво (один stat), без порчи —
    честный размер живёт как есть."""
    p = Path(config.BRAIN_LOG_FILE)
    p.parent.mkdir(parents=True, exist_ok=True)
    loghygiene.append_line(p, '{"i": 1}\n')
    assert not p.with_name("brain_log.1.jsonl").exists()


def test_rotation_failure_keeps_write(home, monkeypatch):
    """Гигиена — не орган дыхания: ротация упала (OSError) — запись
    всё равно живёт (разговор дороже архива, как у бэкапа и печати)."""
    p = Path(config.BRAIN_LOG_FILE)
    p.parent.mkdir(parents=True, exist_ok=True)

    def _boom(_path, **_kw):
        raise OSError("нет места")

    monkeypatch.setattr(loghygiene, "rotate_if_big", _boom)
    loghygiene.append_line(p, '{"i": "жива"}\n')
    assert "жива" in p.read_text(encoding="utf-8")


def test_brain_writer_uses_door(home, monkeypatch):
    """Журнал мозга — самая частая копилка дома: якорь требует, чтобы
    она ходила через дверь (запись попала в файл И дверь звалась)."""
    calls = []
    real = loghygiene.append_line

    def spy(path, text):
        calls.append(path)
        real(path, text)

    monkeypatch.setattr(loghygiene, "append_line", spy)
    from core import brain
    brain._log_brain_call("chat", "ответ", "ответ", None, 1.2, True)
    assert calls, "журнал мозга пишет мимо двери ротации"
    assert calls[0] == Path(config.BRAIN_LOG_FILE)


def test_all_journals_through_one_door():
    """ЗАКОН ОДНОЙ ДВЕРИ: все пять копилок (brain, ears, monitor,
    repair, hands) ходят через loghygiene.append_line — якорь по
    исходнику против тихого обхода; страж НЕ ходит (хеш-цепь, ТЗ 3.7):
    исключение с причиной, не забытость."""
    root = Path(__file__).resolve().parents[1]
    for rel in ("core/brain.py", "sensors/ears.py", "sensors/monitor.py",
                "core/repair.py", "core/motor.py"):
        src = (root / rel).read_text(encoding="utf-8")
        assert "loghygiene.append_line" in src, "%s пишет мимо двери" % rel
    guard_src = (root / "safety" / "guard.py").read_text(encoding="utf-8")
    assert "loghygiene" not in guard_src, \
        "страж не ходит через дверь: хеш-цепь (ТЗ 3.7) — целостность важнее размера"


def test_guard_exempt_from_journals():
    """Список журналов закона не содержит стража — исключение
    закреплено структурой, а не комментарием."""
    assert config.GUARD_LOG_FILE not in loghygiene.journal_paths()
    assert len(loghygiene.journal_paths()) == 5


# ---------- Ф98 «ЧИТАТЕЛИ ПРОТИВ РОТАЦИИ» ----------

def _brain_rec(today: bool, secs: float, ctok: int = 5) -> str:
    day = dt.date.today() if today else dt.date.today() - dt.timedelta(days=1)
    return json.dumps({"ts": day.strftime("%Y-%m-%d") + " 08:00:00",
                       "secs": secs, "completion_tokens": ctok,
                       "ok": True, "kind": "chat"},
                      ensure_ascii=False)


def test_daypulse_reads_across_rotation(home):
    """Ротация среди дня: утро ушло в архив, день живёт в текущем —
    «пульс» видит ОБА (сегодня не роняется ценой гигиены)."""
    p = Path(config.BRAIN_LOG_FILE)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.with_name("brain_log.1.jsonl").write_text(
        _brain_rec(True, 10.0) + "\n", encoding="utf-8")
    p.write_text(_brain_rec(True, 20.0) + "\n", encoding="utf-8")
    recs = [r for r in daypulse._read_records()
            if str(r.get("ts", "")).startswith(dt.date.today().isoformat())]
    assert len(recs) == 2, "пульс потерял сегодня при ротации"
    assert sorted(r["secs"] for r in recs) == [10.0, 20.0]


def test_energy_reads_across_rotation(home):
    """Бухгалтерия энергии — тот же закон: генерации утра (архив) и
    дня (текущий) сходятся в один честный счёт."""
    p = Path(config.BRAIN_LOG_FILE)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.with_name("brain_log.2.jsonl").write_text(
        _brain_rec(True, 30.0, ctok=7) + "\n", encoding="utf-8")
    p.write_text(_brain_rec(True, 5.0, ctok=3) + "\n", encoding="utf-8")
    got = energy._brain_today()
    assert got["gen"] == 2 and got["ctok"] == 10


def test_readers_ignore_yesterday_archive(home):
    """Архив с ВЧЕРАШНИМИ строками читается, но в «сегодня» не
    попадает: фильтр дня — после чтения, ротация его не обманывает."""
    p = Path(config.BRAIN_LOG_FILE)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.with_name("brain_log.1.jsonl").write_text(
        _brain_rec(False, 99.0, ctok=99) + "\n", encoding="utf-8")
    p.write_text(_brain_rec(True, 5.0, ctok=3) + "\n", encoding="utf-8")
    got = energy._brain_today()
    assert got["gen"] == 1 and got["ctok"] == 3


def test_tail_picks_current_after_rotation(home):
    """«хвост brain» после ротации показывает ТЕКУЩИЙ файл (новейший
    по mtime) — лечение из чата не ломается гигиеной."""
    root = Path(config.LOGS_DIR)
    old = root / "brain_log.1.jsonl"
    new = root / "brain_log.jsonl"
    old.write_text('{"старая": "улика"}\n', encoding="utf-8")
    new.write_text('{"новая": "улика"}\n', encoding="utf-8")
    now = time.time()
    os.utime(old, (now - 1000, now - 1000))
    os.utime(new, (now, now))
    out = creator_gate._cmd_tail("brain")
    assert "новая" in out and "старая" not in out


# ---------- Ф99 «ГИГИЕНА ДОМА» ----------

def test_hygiene_command_reflex(agent, srv):
    """«гигиена» — рефлекс: мозг молчит, журналы лицом — имена,
    размеры, закон и честное исключение стража."""
    Path(config.BRAIN_LOG_FILE).parent.mkdir(parents=True, exist_ok=True)
    loghygiene.append_line(Path(config.BRAIN_LOG_FILE), '{"i": 1}\n')
    r = agent.handle("гигиена")
    assert r.source == "python" and r.tool_used == "hygiene"
    assert not srv.calls
    assert "brain_log.jsonl" in r.text
    assert "8" in r.text and "МБ" in r.text, "закон (порог) не назван"
    assert "хеш-цепь" in r.text and "страж" in r.text.lower() or \
        "guard" in r.text.lower()


def test_hygiene_command_variant(agent, srv):
    r = agent.handle("гигиена дома")
    assert r.tool_used == "hygiene"
    assert not srv.calls


def test_hygiene_names_all_journals(agent, srv):
    """Осмотр называет все пять копилок поимённо — ни одна не
    спряталась, ни одна не выдумана."""
    r = agent.handle("гигиена")
    for fname in ("brain_log.jsonl", "ears_log.jsonl", "monitor_log.jsonl",
                  "repair_log.jsonl", "hands_log.jsonl"):
        assert fname in r.text, "гигиена потеряла журнал: " + fname


def test_hygiene_render_armored(home, monkeypatch):
    """Орган в броне: журнал-путь упал (OSError) — осмотр честно
    говорит «не смогла», а не падает и не врёт нулями."""
    def _boom():
        raise OSError("диск")

    monkeypatch.setattr(loghygiene, "journal_paths", _boom)
    text = loghygiene.render()
    assert "не смогла" in text
