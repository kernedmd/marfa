# -*- coding: utf-8 -*-
r"""tests/test_selfcare.py — АПТЕЧКА ДОМА: Марфа ставит модули сама.

Живой прогон станции (22.11): Создатель спросил «ПОчему ты сам не
установишь?», потом руками запустил ГОЛЫЙ pip — тот ответил
«Requirement already satisfied … python311» (системный Python!) —
а cv2 в venv дома так и не появился.

Якоря:
- pip аптечки — всегда СВОЙ интерпретатор (sys.executable -m pip),
  никогда голый `pip` из PATH;
- whitelist: только модули, заявленные в requirements.txt — текст
  Создателя или мозга не может расширить список установки;
- истина установки — ИМПОРТ после pip, а не код возврата;
- уже стоящий модуль не будит pip вообще.

Швы: selfcare.module_version / selfcare._run_pip — реальный pip
в тестах не живёт.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import selfcare  # noqa: E402

REP_OK = {"ok": True, "already": False, "version": "4.10.0",
          "secs": 23.4, "import_name": "cv2", "pkg": "opencv-python",
          "rc": 0, "tail": "", "why": None}

REP_FAIL = {"ok": False, "already": False, "version": None,
            "secs": 12.0, "import_name": "cv2", "pkg": "opencv-python",
            "rc": 1, "tail": "network is unreachable", "why": None}


# ---------- pip своего интерпретатора, не чужой ----------

def test_pip_command_never_bare_pip():
    """Урок живого прогона: голый pip на Windows — это pip ИЗ PATH,
    системного Python («Requirement already satisfied … python311»).
    Аптечка зовёт pip ТОЛЬКО через интерпретатор самого дома."""
    cmd = selfcare.pip_command("cv2")
    assert cmd[0] == sys.executable          # свой python, не PATH
    assert cmd[1:4] == ["-m", "pip", "install"]
    assert cmd[-1] == "opencv-python"        # cv2 прячется за пакетом
    assert "pip.exe" not in " ".join(cmd) and not cmd[0].endswith("\\pip")


def test_pip_command_no_shell_no_url():
    """Список аргументов без shell-строки: ни URL, ни --index-url —
    только имя пакета из whitelist."""
    cmd = selfcare.pip_command("PIL")
    assert cmd[-1] == "pillow"
    for tok in cmd:
        assert "http" not in tok and "--index-url" not in tok


def test_manual_command_names_own_interpreter():
    """Команда для Создателя — с путём к интерпретатору ДОМА в кавычках:
    копируй-вставляй — и попадёт в venv, не в системный Python."""
    s = selfcare.manual_command("cv2")
    assert sys.executable in s and "opencv-python" in s
    assert s.startswith('"') and '" -m pip install' in s


# ---------- whitelist: только своё ----------

def test_whitelist_is_requirements_subset():
    """Аптечка ставит ТОЛЬКО пакеты, заявленные в requirements.txt —
    иначе «поставь <что-нибудь>» станет дырой в дом."""
    req = Path(__file__).resolve().parents[1] / "requirements.txt"
    text = req.read_text(encoding="utf-8")
    for pkg in selfcare.KNOWN_MODULES.values():
        assert pkg in text, "аптечка ставит незаявленное: " + pkg


def test_ensure_unknown_module_refused(monkeypatch):
    """Незнакомый модуль — отказ без единого вызова pip: whitelist
    читает код, а не текст задания."""
    calls = []
    monkeypatch.setattr(selfcare, "module_version", lambda name: None)
    monkeypatch.setattr(selfcare, "_run_pip",
                        lambda cmd, timeout: calls.append(cmd) or (0, ""))
    rep = selfcare.ensure_module("torch_superhack")
    assert rep["ok"] is False and rep["why"] == "not_whitelisted"
    assert calls == []
    assert "не знаком" in selfcare.render_report(rep)


def test_ensure_already_present_no_pip(monkeypatch):
    """Модуль уже стоит — pip не дёргается вовсе (идемпотентность)."""
    calls = []
    monkeypatch.setattr(selfcare, "module_version", lambda name: "4.10")
    monkeypatch.setattr(selfcare, "_run_pip",
                        lambda cmd, timeout: calls.append(cmd) or (0, ""))
    rep = selfcare.ensure_module("cv2")
    assert rep["ok"] is True and rep["already"] is True
    assert rep["version"] == "4.10"
    assert calls == []


# ---------- установка: успех, вранье pip, честный отказ ----------

def test_ensure_install_success(monkeypatch):
    """Нет модуля → pip своего venv → импорт подтвердил → отчёт с секундами."""
    state = {"ver": None}
    monkeypatch.setattr(selfcare, "module_version",
                        lambda name: state["ver"])
    seen = []

    def fake_pip(cmd, timeout):
        seen.append(cmd)
        state["ver"] = "4.10.0"           # pip сработал — модуль появился
        return 0, "Successfully installed opencv-python"

    monkeypatch.setattr(selfcare, "_run_pip", fake_pip)
    rep = selfcare.ensure_module("cv2")
    assert rep["ok"] is True and rep["already"] is False
    assert rep["version"] == "4.10.0" and rep["pkg"] == "opencv-python"
    assert rep["secs"] >= 0.0
    assert len(seen) == 1 and seen[0][0] == sys.executable


def test_ensure_pip_exit_zero_but_no_import_is_failure(monkeypatch):
    """pip соврал « successfully», а импорта нет — значит, НЕТ: истина
    установки — импорт, а не код возврата."""
    monkeypatch.setattr(selfcare, "module_version", lambda name: None)
    monkeypatch.setattr(selfcare, "_run_pip",
                        lambda cmd, timeout: (0, "Successfully installed"))
    rep = selfcare.ensure_module("cv2")
    assert rep["ok"] is False
    assert "не смогла" in selfcare.render_report(rep)


def test_ensure_install_failure_honest(monkeypatch):
    """Сеть спит — честный отказ с хвостом ошибки и командой для рук."""
    monkeypatch.setattr(selfcare, "module_version", lambda name: None)
    monkeypatch.setattr(selfcare, "_run_pip",
                        lambda cmd, timeout: (1, "network is unreachable"))
    rep = selfcare.ensure_module("cv2")
    assert rep["ok"] is False and rep["rc"] == 1
    s = selfcare.render_report(rep)
    assert "не смогла" in s and "network is unreachable" in s
    assert "-m pip install opencv-python" in s   # что делать руками


def test_render_report_success_names_secs():
    """Успех докладывается секундами и версией — Создатель видит,
    сколько заняло самолечение, не открывая консоль."""
    assert "поставила сама" in selfcare.render_report(REP_OK)
    assert "23" in selfcare.render_report(REP_OK)
    assert "4.10.0" in selfcare.render_report(REP_OK)
