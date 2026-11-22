# -*- coding: utf-8 -*-
"""tests/test_clipboard.py — №18 роадмапа 30 «запиши в буфер» + Р-4.

Буфер обмена (pyperclip) — только по прямой команде. Контракт:

  - clipboard_write: текст в буфер, лимит 500 символов (буфер — не
    печать, но и не свалка), секреты (канарейки, ключи) мимо —
    буфер живёт в системе дольше чата и вставится куда угодно;
  - нет модуля — RuntimeError с честной причиной (аптечка поставит:
    pyperclip заявлен в requirements.txt);
  - команда агента «в буфер <текст>» / «скопируй <текст>» — мозг
    молчит, отказ стража — честный текст, не 500-я и не мозг;
  - Р-4 ЗАКРЫТ: «руки напечатай <кириллица>» — руки кладут текст в
    буфер и вставляют ctrl+v (whitelist); латиница печатается прямо,
    как раньше; сухой режим честно описывает план;
  - буфер споткнулся — вставки НЕ будет: ctrl+v без нового буфера
    вставил бы ПРОШЛОЕ, это хуже, чем ничего;
  - лимит печати (120) действует и на вставку — закон один.

Швы: hands._pyperclip / motor._execute / motor.enabled / guard-лог.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import agent, config, hands, motor  # noqa: E402
from safety import guard  # noqa: E402


@pytest.fixture()
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("MARFA_HOME", str(tmp_path))
    monkeypatch.setattr(config, "HOME_DIR", tmp_path)
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(config, "LOGS_DIR", tmp_path / "logs")
    monkeypatch.setattr(config, "GUARD_LOG_FILE",
                        tmp_path / "logs" / "guard_log.jsonl")
    monkeypatch.setattr(config, "CANARIES_FILE",
                        tmp_path / "data" / "canaries.json")
    monkeypatch.setattr(guard, "_LOG", None)
    config.ensure_dirs()
    yield tmp_path


class FakeClip:
    def __init__(self):
        self.copied = None

    def copy(self, text):
        self.copied = text


@pytest.fixture()
def clip(monkeypatch):
    fc = FakeClip()
    monkeypatch.setattr(hands, "_pyperclip", lambda: fc)
    return fc


def _agent():
    class FakeBrain:
        calls = 0

        def ask_json(self, *a, **kw):
            self.calls += 1
            return {"answer": "мозг"}

    class FakeMemory:
        def recall(self, *a, **kw):
            return []

    return agent.Agent(brain=FakeBrain(), memory=FakeMemory())


# ---------- clipboard_write ----------

def test_clipboard_write_ok(home, clip):
    r = hands.clipboard_write("привет, Илья")
    assert clip.copied == "привет, Илья"
    assert "12 символов" in r and "ctrl+v" in r
    # подсказка ведёт к настоящей команде: ctrl+v в whitelist рук
    assert "руки клавиши ctrl+v" in r


def test_guard_type_cyrillic_direct_call_still_denied(home):
    """Глубина защиты: прямой вызов type с кириллицей (мимо роутера
    run) — по-прежнему отказ: исполнитель обязан идти путём paste."""
    v = motor.guard_action("type", ("привет",), (1920, 1080))
    assert not v.allowed() and "латиниц" in v.reason


def test_guard_paste_allows_cyrillic(home):
    v = motor.guard_action("paste", ("привет",), (1920, 1080))
    assert v.allowed() and "вставка" in v.reason


def test_clipboard_write_cyrillic_roundtrip(home, clip):
    """Кириллица едет в буфер как есть — юникод, а не кракозябры."""
    text = "Привет! Как дела? Ёлка и щётка."
    hands.clipboard_write(text)
    assert clip.copied == text


def test_clipboard_write_limit(home, clip):
    long = "а" * (config.CLIPBOARD_LIMIT + 1)
    with pytest.raises(PermissionError):
        hands.clipboard_write(long)
    assert clip.copied is None                  # мимо — не положили


def test_clipboard_write_limit_edge_ok(home, clip):
    text = "а" * config.CLIPBOARD_LIMIT
    hands.clipboard_write(text)
    assert clip.copied == text


def test_clipboard_write_secrets_denied(home, clip, monkeypatch):
    canary = guard.ensure_canaries()[0]
    with pytest.raises(PermissionError):
        hands.clipboard_write("мой ключ: " + canary)
    with pytest.raises(PermissionError):
        hands.clipboard_write("токен ghp_" + "A" * 40)
    assert clip.copied is None


def test_clipboard_write_empty_denied(home, clip):
    with pytest.raises(ValueError):
        hands.clipboard_write("   ")
    assert clip.copied is None


def test_clipboard_no_module_honest(home, monkeypatch):
    def boom():
        raise ImportError("No module named 'pyperclip'")

    monkeypatch.setattr(hands, "_pyperclip", boom)
    with pytest.raises(RuntimeError) as ei:
        hands.clipboard_write("текст")
    assert "pyperclip" in str(ei.value)


# ---------- команда агента ----------

def test_agent_clipboard_command(home, clip):
    a = _agent()
    for msg in ("в буфер привет", "запиши в буфер: привет",
                "скопируй привет", "в буфер привет!"):
        r = a.handle(msg)
        assert r.tool_used == "clipboard", msg
        assert r.source == "python", msg
        assert a.brain.calls == 0, msg
    assert clip.copied == "привет"


def test_agent_clipboard_guard_denial_is_text(home, clip):
    """Отказ стража — честный текст в чате, не исключение и не мозг."""
    a = _agent()
    r = a.handle("в буфер " + "а" * (config.CLIPBOARD_LIMIT + 1))
    assert r.tool_used == "clipboard"
    assert "СТРАЖ отказал" in r.text
    assert a.brain.calls == 0


def test_agent_clipboard_crash_honest_not_brain(home, monkeypatch):
    """Буфер упал (нет дисплея/модуля) — честный текст в чате с советом,
    мозг не зря тратится на бытовую поломку."""
    def boom(text):
        raise RuntimeError("нет дисплея")

    monkeypatch.setattr(hands, "clipboard_write", boom)
    a = _agent()
    r = a.handle("в буфер привет")
    assert r.tool_used == "clipboard" and r.source == "python"
    assert "буфер не принял" in r.text and "нет дисплея" in r.text
    assert a.brain.calls == 0


# ---------- Р-4: кириллица руками через буфер ----------

def test_motor_type_cyrillic_dry_plan(home, clip, monkeypatch):
    monkeypatch.setattr(motor, "enabled", lambda: False)
    text = motor.run("напечатай Привет, Илья")
    assert "СУХОЙ РЕЖИМ" in text
    assert "буфер" in text and "ctrl+v" in text
    assert clip.copied is None                  # сухой режим не трогает


def test_motor_type_cyrillic_motor_pastes(home, clip, monkeypatch):
    """Моторика вкл: текст в буфер, потом ctrl+v — именно в этом порядке."""
    monkeypatch.setattr(motor, "enabled", lambda: True)
    order = []

    def fake_execute(name, args):
        order.append((name, args))
        return "нажала ctrl+v"

    monkeypatch.setattr(motor, "_execute", fake_execute)
    orig_copy = clip.copy

    def copy_spy(text):
        order.append(("clipboard", text))
        orig_copy(text)

    clip.copy = copy_spy
    text = motor.run("напечатай Привет, Илья")
    assert clip.copied == "Привет, Илья"
    assert order[0][0] == "clipboard"           # СНАЧАЛА буфер
    assert order[1] == ("hotkey", ("ctrl+v",))  # ПОТОМ вставка
    assert "вставила ctrl+v" in text


def test_motor_type_latin_still_direct(home, clip, monkeypatch):
    """Латиница печатается прямо, как раньше: буфер не трогаем."""
    monkeypatch.setattr(motor, "enabled", lambda: True)
    executed = []

    def fake_execute(name, args):
        executed.append((name, args))
        return "напечатала %d символов" % len(args[0])

    monkeypatch.setattr(motor, "_execute", fake_execute)
    motor.run("напечатай hello world")
    assert executed == [("type", ("hello world",))]
    assert clip.copied is None


def test_motor_paste_respects_type_limit(home, clip, monkeypatch):
    """Закон печати один: вставка длиннее 120 символов — отказ стража."""
    monkeypatch.setattr(motor, "enabled", lambda: True)
    monkeypatch.setattr(motor, "_execute",
                        lambda name, args: "не должен зваться")
    text = motor.run("напечатай " + "привет " * 30)
    assert "СТРАЖ ОТКАЗАЛ" in text
    assert clip.copied is None


def test_motor_paste_clipboard_down_no_ctrlv(home, monkeypatch):
    """Буфер споткнулся — вставки НЕ будет: ctrl+v без нового буфера
    вставил бы ПРОШЛОЕ (урок честности: ничего лучше, чем ничего)."""
    monkeypatch.setattr(motor, "enabled", lambda: True)
    executed = []

    def fake_execute(name, args):
        executed.append((name, args))
        return "не должен зваться"

    monkeypatch.setattr(motor, "_execute", fake_execute)

    def boom(text):
        raise RuntimeError("нет pyperclip")

    monkeypatch.setattr(hands, "clipboard_write", boom)
    text = motor.run("напечатай Привет")
    assert "БУФЕР не принял" in text and "ПРОШЛОЕ" in text
    assert executed == []                        # ctrl+v не жали


def test_motor_paste_hint_mentions_buffer():
    """Подсказка рук честна: кириллица — через буфер."""
    assert "буфер" in motor._HINT and "ctrl+v" in motor._HINT


def test_manifest_promise_updated():
    """Мозг больше не обещает «руки не печатают кириллицу» — теперь
    обещает правду: кириллица через буфер и ctrl+v."""
    from core import identity
    assert "через буфер" in identity.manifest()
    assert "руки не печатают кириллицу" not in identity.manifest()
