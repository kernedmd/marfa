# -*- coding: utf-8 -*-
"""МОСТ УШЕЙ — ВЕБ-ФРОНТ (23.11): /api/voice для страницы чата.

Орган моста (sensors/ear_bridge.py) проверен своими 37 якорями; здесь
проверяется ПРОВОДКА к Создателю: голосовые ходы приходят в чат живьём
(опрос раз в 4 с с последним seq), ответы Марфы — безопасным HTML с
сервера (№12: панель не доверяет ни мозгу, ни журналу), busy-флаг
показывает «расшифровываю и думаю» вместо минуты молчания.

Закон №10 р3 — главный якорь файла: УПАВШИЙ МОСТ НЕ РОНЯЕТ СТРАНИЦУ.
Журнала нет, статуса нет, файл битый — /api/voice отвечает честным
пустым приростом, чат жив.
"""
import datetime as dt
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core import config  # noqa: E402
from web.app import app  # noqa: E402


@pytest.fixture()
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("MARFA_HOME", str(tmp_path))
    monkeypatch.setattr(config, "HOME_DIR", tmp_path)
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(config, "LOGS_DIR", tmp_path / "logs")
    monkeypatch.setattr(config, "VOICE_DIR", tmp_path / "data" / "voice")
    monkeypatch.setattr(config, "VOICE_LOG_FILE",
                        tmp_path / "data" / "voice" / "voice_log.jsonl")
    monkeypatch.setattr(config, "VOICE_STATUS_FILE",
                        tmp_path / "data" / "voice" / "status.json")
    config.ensure_dirs()
    (tmp_path / "data" / "voice").mkdir(parents=True, exist_ok=True)
    yield tmp_path


@pytest.fixture()
def client(home, monkeypatch):
    app.config["TESTING"] = True
    return app.test_client()


def _journal(home, records) -> None:
    """Накатать журнал голоса: список dict → jsonl (с seq по порядку)."""
    p = Path(config.VOICE_LOG_FILE)
    lines = []
    for i, rec in enumerate(records, 1):
        rec = dict(rec)
        rec["seq"] = i
        rec.setdefault("ts", dt.datetime.now().isoformat(timespec="seconds"))
        lines.append(json.dumps(rec, ensure_ascii=False))
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _status(home, busy: bool, age_sec: int = 0) -> None:
    ts = dt.datetime.now() - dt.timedelta(seconds=age_sec)
    Path(config.VOICE_STATUS_FILE).write_text(json.dumps({
        "ts": ts.isoformat(timespec="seconds"),
        "sensor": "ear_bridge", "state": "ok", "busy": busy,
    }, ensure_ascii=False), encoding="utf-8")


# ---------- полный обмен: фраза, ответ, штампы, безопасный HTML ----------

def test_exchange_full(client, home):
    _journal(home, [{
        "event": "exchange", "phrase": "Марфа, который час",
        "answer": "Сейчас **14:20** — время живых часов дома №38.",
        "secs": 12.5, "src": "brain", "tok": 84, "ptok": 3512,
    }])
    r = client.get("/api/voice")
    assert r.status_code == 200
    d = r.get_json()
    assert d["seq"] == 1 and len(d["turns"]) == 1
    t = d["turns"][0]
    assert t["event"] == "exchange"
    assert t["phrase"] == "Марфа, который час"
    assert t["answer"].startswith("Сейчас")
    # №12: ответ — ГОТОВЫЙ безопасный HTML с сервера; фраза остаётся
    # текстом (панель покажет textContent)
    assert "<b>14:20</b>" in t["html"]
    assert t["src_label"] == "мозг"            # штамп «кто отвечал»
    assert t["tok"] == 84 and t["ptok"] == 3512


def test_exchange_html_is_escape_safe(client, home):
    # журнал — недоверенный источник, как и мозг: сырой HTML экранируется
    _journal(home, [{
        "event": "exchange", "phrase": "Марфа, привет",
        "answer": "<script>alert('x')</script>Привет, Илья",
        "secs": 3.0, "src": "python",
    }])
    d = client.get("/api/voice").get_json()
    html = d["turns"][0]["html"]
    assert "Привет, Илья" in html
    assert "<script>" not in html          # живого тега нет
    assert "&lt;script&gt;" in html        # стал видимым текстом (№12)


def test_src_label_only_with_secs(client, home):
    # без секунд штампа нет — старые записи читаются как раньше
    _journal(home, [{"event": "exchange", "phrase": "Марфа!",
                     "answer": "Слушаю."}])
    d = client.get("/api/voice").get_json()
    assert d["turns"][0]["src_label"] == ""


# ---------- прирост по seq: страница помнит последнее показанное ----------

def test_after_returns_only_fresh(client, home):
    _journal(home, [
        {"event": "skip", "phrase": "марка красивая", "why": "имени нет"},
        {"event": "exchange", "phrase": "Марфа, время", "answer": "14:20",
         "secs": 2.0, "src": "brain"},
        {"event": "error", "stage": "whisper", "error": "слуга не встал"},
    ])
    d = client.get("/api/voice?after=1").get_json()
    assert d["seq"] == 3
    assert [t["event"] for t in d["turns"]] == ["exchange", "error"]
    # без after сервер отдаёт всё (seq > -1) — старые ходы НЕ заваливают
    # чат потому, что ФРОНТ первого опроса их отбрасывает и берёт лишь
    # текущий seq (chat.html: voiceSeq === null ? [] : turns)
    d0 = client.get("/api/voice").get_json()
    assert d0["seq"] == 3 and len(d0["turns"]) == 3


def test_skip_and_error_come_through(client, home):
    # сноски и ошибки — тоже голосовая правда, чат их видит честно
    _journal(home, [
        {"event": "skip", "phrase": "марка красивая", "why": "имени в фразе нет"},
        {"event": "error", "stage": "whisper", "error": "404: старая сборка"},
    ])
    d = client.get("/api/voice?after=0").get_json()
    skip, err = d["turns"]
    assert skip["why"] == "имени в фразе нет"
    assert "404" in err["error"]
    # сноска — не ответ Марфы: HTML ей не положен
    assert "html" not in skip and "html" not in err


# ---------- busy-флаг: «расшифровываю и думаю», не минута молчания ----------

def test_busy_fresh_true_stale_false(client, home):
    _status(home, busy=True)
    assert client.get("/api/voice").get_json()["busy"] is True
    _status(home, busy=True, age_sec=600)      # протухло — не врём «думаю»
    assert client.get("/api/voice").get_json()["busy"] is False
    _status(home, busy=False)
    assert client.get("/api/voice").get_json()["busy"] is False


# ---------- закон №10 р3: упавший мост не роняет страницу ----------

def test_bridge_down_honest_empty(client, home):
    # ни журнала, ни статуса — служба не поднималась: честный пустой
    # прирост, страница жива
    d = client.get("/api/voice").get_json()
    assert d["seq"] == 0 and d["turns"] == [] and d["busy"] is False


def test_broken_journal_lines_skipped(client, home):
    # битые строки журнала молча мимо — журнал не должен ронять страницу
    p = Path(config.VOICE_LOG_FILE)
    p.write_text("не json вообще\n{сломанный\n\n"
                 + json.dumps({"event": "exchange", "seq": 7,
                               "phrase": "Марфа, статус",
                               "answer": "все системы в норме",
                               "secs": 4.0, "src": "brain"},
                              ensure_ascii=False) + "\n",
                 encoding="utf-8")
    d = client.get("/api/voice").get_json()
    assert d["seq"] == 7
    assert len(d["turns"]) == 1
    assert d["turns"][0]["phrase"] == "Марфа, статус"
