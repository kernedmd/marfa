# -*- coding: utf-8 -*-
"""tests/test_start_scripts.py — якоря старт-скриптов (день-8, 23.11).

УРОК ДНЯ-8: кавычки в команде старта мозга переживают три слоя разбора
(JSON → Popen(shell=True) → argv сервера) и доезжают покорёженными —
сервер получает невалидный JSON и умирает на старте, а чат Создателя
отвечает «мозг недоступен (WinError 10061)». Живой мозг маскировал
бомбу до первого Стоп → Старт.

Эти тесты — НЕ регрессия кода, а регрессия ФАЙЛОВ: старт-скрипты
обязаны оставаться лечимыми на уровне байтов. PowerShell-скрипты дома
живут в cp1251 (ANSI на русской Windows) — читаем байтами, кириллицу
не трогаем.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import start_marfa as sm  # noqa: E402

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


# ---------- закон: команда старта мозга НЕ СОДЕРЖИТ КАВЫЧЕК ----------

def test_template_brain_cmd_has_no_quotes():
    """Закон дня-8: кавычки в brain_cmd — бомба с часовым механизмом
    (три слоя разбора съедают их по-разному). Шаблон обязан быть
    чистым: ни одной кавычки, ни одного ядовитого хвоста."""
    cmd = sm.TEMPLATE["brain_cmd"]
    assert '"' not in cmd and "'" not in cmd
    for marker in sm._POISON_MARKERS:
        assert marker not in cmd
    assert "-c 8192" in cmd and "--temp 0.7" in cmd and "--top-p 0.8" in cmd
    assert "--port 8082" in cmd and "-ngl 0" in cmd


def test_repo_config_brain_cmd_clean():
    """start_marfa.json в репо — здоровая команда (станция не разносит
    заразу в дом): без кавычек и без ядовитых хвостов."""
    import json
    cfg = json.loads((Path(sm.CONFIG_FILE)).read_text(encoding="utf-8"))
    cmd = cfg.get("brain_cmd") or ""
    assert cmd and '"' not in cmd
    for marker in sm._POISON_MARKERS:
        assert marker not in cmd


def test_eyes_cmd_still_clean():
    """Глаза не пострадали от терапии — их команда без кавычек и была,
    и остаётся (регрессия на всякий случай: закон один на все слуги)."""
    assert '"' not in sm.TEMPLATE["eyes_cmd"]


# ---------- лечение отравленного конфига ----------

def test_heal_poisoned_brain_cmd():
    """Отравленная команда (кавычки терапии §15) лечится: хвост снят,
    яда нет, основа (модель/порт/контекст) на месте."""
    poisoned = ('llama.cpp\\llama-server.exe -m models\\Qwen3-30B-A3B-'
                'Q4_K_M.gguf --host 127.0.0.1 --port 8082 -ngl 0 -c 8192 '
                '--temp 0.7 --top-p 0.8 --top-k 20 --repeat-penalty 1.0 '
                '--jinja --chat-template-kwargs "{\\"enable_thinking\\":'
                ' false}"')
    cfg = {"brain_cmd": poisoned, "eyes_cmd": "run eyes"}
    assert sm._heal_brain_cmd(cfg) is True
    healed = cfg["brain_cmd"]
    assert '"' not in healed
    for marker in sm._POISON_MARKERS:
        assert marker not in healed
    assert "-c 8192" in healed and "--port 8082" in healed
    assert "Qwen3-30B-A3B" in healed
    assert cfg["eyes_cmd"] == "run eyes"          # чужие поля не тронуты


def test_heal_keeps_custom_model_path():
    """Создатель сменил квант (Q6_K) — лечение переносит ЕГО модель,
    а не подсовывает дефолтную."""
    poisoned = ('llama.cpp\\llama-server.exe -m models\\Qwen3-30B-A3B-'
                'Q6_K.gguf --host 127.0.0.1 --port 8082 -ngl 0 '
                '--jinja --chat-template-kwargs x')
    cfg = {"brain_cmd": poisoned}
    assert sm._heal_brain_cmd(cfg) is True
    assert "Qwen3-30B-A3B-Q6_K.gguf" in cfg["brain_cmd"]
    assert "Q4_K_M" not in cfg["brain_cmd"]


def test_heal_ignores_healthy():
    """Здоровая команда не трогается (идемпотентность: сколько угодно
    нажатий кнопки 92, вреда нет)."""
    healthy = sm.TEMPLATE["brain_cmd"]
    cfg = {"brain_cmd": healthy}
    assert sm._heal_brain_cmd(cfg) is False
    assert cfg["brain_cmd"] == healthy


def test_heal_ignores_empty():
    """Пустая команда — не яд: её лечить нечем, старт честно скажет
    «впиши brain_cmd» (существующий контракт)."""
    assert sm._heal_brain_cmd({"brain_cmd": ""}) is False


def test_ensure_config_heals_file(tmp_path, monkeypatch):
    """Живой конфиг с ядом лечится при чтении: файл перезаписан,
    честное сообщение — на экран, вторая попытка стопа-старта не
    наткнётся на ту же бомбу."""
    import io
    import contextlib
    p = tmp_path / "start_marfa.json"
    p.write_text(json.dumps({
        "brain_cmd": 'exe -m m.gguf --jinja --chat-template-kwargs "\\"x\\""',
        "eyes_cmd": "run eyes"}, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(sm, "_log", lambda line: None)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        cfg = sm.ensure_config(p)
    assert sm._POISON_MARKERS[0] not in cfg["brain_cmd"]
    assert '"' not in cfg["brain_cmd"]
    again = json.loads(p.read_text(encoding="utf-8"))
    assert again == cfg                       # лечение записано в файл
    assert "ВЫЛЕЧЕНА" in buf.getvalue()


# ---------- PowerShell-скрипты: байтовые якоря ----------

def test_common_ps1_math_round_repaired():
    """_common.ps1: [math]::Round починен (терапия §15 перестаралась
    и оставила [m[math] — Get-FreeRamGB/Get-TotalRamGB падали на
    каждом verify/90_manual_check). Читаем байтами: файл в cp1251."""
    data = (SCRIPTS / "_common.ps1").read_bytes()
    assert b"[m[math]" not in data
    assert data.count(b"[math]::Round") == 6
    data.decode("cp1251")                    # кодировка не побита лечением


def test_start_llama_server_ps1_clean():
    """start_llama_server.ps1: ядовитого хвоста нет, законные флаги
    на месте, кавычек-экранирований нет, [math] жив."""
    data = (SCRIPTS / "start_llama_server.ps1").read_bytes()
    assert b'--chat-template-kwargs "' not in data
    assert b'--jinja --chat' not in data
    assert b'\\"' not in data
    assert b"[m[math]" not in data
    for anchor in (b"-c 8192", b"--temp 0.7", b"--top-p 0.8",
                   b"-ngl 0", b"[math]::Round"):
        assert anchor in data
    data.decode("cp1251")


def test_all_ps1_free_of_math_poison():
    """Ни один ps1 дома не несёт [m[math] — повреждение впервые
    пришло «фиксом» терапии и не должно пережить день-8."""
    for p in sorted(SCRIPTS.glob("*.ps1")):
        assert b"[m[math]" not in p.read_bytes(), p.name


# ---------- старт ждёт мозг честно ----------

def test_brain_wait_is_honest():
    """День-8: мозг на старте ЖДЁТСЯ (120 с) — старт без ожидания
    прятал смерть команды за «проверь позже». Ноль — запрещён."""
    brain_entry = [s for s in sm.SERVICES if s[3] == "brain_cmd"][0]
    assert brain_entry[4] == 120
