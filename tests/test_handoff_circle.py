# -*- coding: utf-8 -*-
r"""tests/test_handoff_circle.py — круг 18 «РУКОПОЖАТИЕ БЕРЕГОВ» (Ф106–Ф108).

Урок бандла-1930 (24.11.2026, вечер): финальный bundle круга-17 уехал к
Создателю с единственным ref HEAD — ветки main внутри не было. Кнопка 80
дома зовёт «git fetch <bundle> main» (v3.4), живой bundle падал
«fatal: couldn't find remote ref main», и кнопка называла его битым:
«[x] fetch не удался — bundle битый?». Создатель застрял с кольцом 17 —
проблема вернулась тем же файлом («вот какая проблема», бандл прислан
обратно побайтово тем же, что уехал).

Круг закрывает ОБЕ стороны рукопожатия:
  Ф106 «ДВУХСТУПЕНЧАТЫЙ ВХОД» — кнопка 80 v3.5: сначала каноническая
        ветка main, при её отсутствии в bundle — HEAD. Дом принимает
        ЛЮБОЙ честный bundle архитектора; «битым» отныне называется
        только действительно битый;
  Ф107 «СТРАЖ ВЫПУСКА» — server_sync.py v1.5: bundle без refs/heads/main
        не покидает станцию никогда: брак ловится на месте выпуска
        (list-heads после сборки, файл удаляется), а не на берегу
        Создателя посреди остановленной кнопки;
  Ф108 «ЗОЛОТОЙ ЯКОРЬ РУКОПОЖАТИЯ» — бандл, собранный станцией,
        принимается свежим домом ТОЧНЫМ паттерном кнопки
        («git fetch <bundle> main») — рукопожатие проверено тестом
        от берега до берега, а не обещано текстом протокола.

Нумерация: Ф101–Ф105 заняты планами БЭКЛОГА (и живым стражем токенов —
Ф105 в creator_gate.py), новая нумерация идёт с Ф106 (правило БЭКЛОГА).
"""
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BAT = ROOT / "scripts" / "80_sync_github.bat"
SYNC = ROOT / "scripts" / "server_sync.py"


# ---------------------------------------------------------------- инструменты

def _git(repo, *args):
    """git в чужой папке с собственной личностью — станция не настраивает
    чужой global-конфиг (закон: батарея не мусорит в окружение)."""
    env = dict(os.environ,
               GIT_AUTHOR_NAME="тест", GIT_AUTHOR_EMAIL="t@t",
               GIT_COMMITTER_NAME="тест", GIT_COMMITTER_EMAIL="t@t")
    r = subprocess.run(["git", "-C", str(repo)] + list(args),
                       capture_output=True, text=True, env=env, timeout=60)
    return r.returncode, r.stdout + r.stderr


def _repo(path, name="дом"):
    """Свежий репозиторий с одним коммитом на ветке main."""
    path.mkdir(parents=True, exist_ok=True)
    assert _git(path, "init", "-b", "main")[0] == 0
    (path / "f.txt").write_text(name, encoding="utf-8")
    _git(path, "add", "-A")
    assert _git(path, "commit", "-m", name)[0] == 0
    return path


def _head_of(repo, ref="HEAD"):
    code, out = _git(repo, "rev-parse", ref)
    return out.strip() if code == 0 else ""


# ------------------------------------------------------------ урок (болезнь)

def test_disease_reproduced(tmp_path):
    """Болезнь пришита к истории: bundle с одним HEAD дом-паттерном не читается.

    Это не проверка кода — это ПАМЯТЬ: «git fetch <bundle> main» на HEAD-only
    bundle падает «couldn't find remote ref main». Пока git ведёт себя так,
    фолбэк Ф106 — не роскошь, а единственная дорога домой для такого бандла.
    """
    arh = _repo(tmp_path / "arh", "архитектор")
    (arh / "f.txt").write_text("круг17", encoding="utf-8")
    _git(arh, "commit", "-am", "круг 17")
    bad = tmp_path / "head-only.bundle"
    assert _git(arh, "bundle", "create", str(bad), "HEAD")[0] == 0

    dom = _repo(tmp_path / "dom")
    code, out = _git(dom, "fetch", str(bad), "main")   # паттерн кнопки 80
    assert code != 0, "HEAD-only bundle вдруг принимается по main — урок устарел"
    assert "couldn't find remote ref" in out


# ------------------------------------------------------------------- Ф106

def test_button_two_step_fetch_source():
    """Ф106 по исходнику: двухступенчатый вход в :import_bundle — main, затем HEAD.

    Якорь по исходнику грубее поведенческого, но ловит тихий обход: вынуть
    фолбэк из кнопки незаметно нельзя (урок круга 17 — закон одной двери).
    """
    t = BAT.read_text(encoding="utf-8")
    assert "rem BTN_VER 3.5" in t                     # версия поднята
    sub = t[t.index(":import_bundle"):]
    # первая ступень — каноническая ветка
    assert "git fetch %1 main" in sub
    # вторая ступень — фолбэк на HEAD, ПОСЛЕ main, и до слияний
    assert "git fetch %1 HEAD" in sub
    assert sub.index("git fetch %1 main") < sub.index("git fetch %1 HEAD")
    assert sub.index("git fetch %1 HEAD") < sub.index("git merge-base")
    # честный сбой остаётся честным: битым назван только брак ОБЕИХ ступеней
    assert sub.count("bundle битый") == 1


def test_button_fallback_rescues_head_only(tmp_path):
    """Ф106 поведением: HEAD-only bundle принимается домом через фолбэк.

    Последовательность — как в кнопке: main упал -> HEAD принят -> FETCH_HEAD
    указывает на коммит архитектора. Дом не застревает с кольцом 17.
    """
    arh = _repo(tmp_path / "arh", "архитектор")
    (arh / "f.txt").write_text("круг17", encoding="utf-8")
    _git(arh, "commit", "-am", "круг 17")
    bad = tmp_path / "head-only.bundle"
    assert _git(arh, "bundle", "create", str(bad), "HEAD")[0] == 0

    dom = _repo(tmp_path / "dom")
    # ступень 1 — падает, как вечером 24.11
    assert _git(dom, "fetch", str(bad), "main")[0] != 0
    # ступень 2 — фолбэк кнопки v3.5
    assert _git(dom, "fetch", str(bad), "HEAD")[0] == 0
    assert _head_of(dom, "FETCH_HEAD") == _head_of(arh)


def test_button_fallback_keeps_canonical_main(tmp_path):
    """Ф106: bundle с веткой main идёт по первой ступени — фолбэк не нужен.

    Канон не сместился: main остаётся главным входом, HEAD — запасная дверь.
    """
    arh = _repo(tmp_path / "arh", "архитектор")
    good = tmp_path / "main.bundle"
    assert _git(arh, "bundle", "create", str(good), "main")[0] == 0

    dom = _repo(tmp_path / "dom")
    assert _git(dom, "fetch", str(good), "main")[0] == 0
    assert _head_of(dom, "FETCH_HEAD") == _head_of(arh)


# ------------------------------------------------------------------- Ф107

def test_export_guard_source():
    """Ф107 по исходнику: страж выпуска вшит в export_bundle.

    Тихо вырезать страж нельзя: list-heads после сборки, требование
    refs/heads/main, брак удаляется с места выпуска, причина — вслух.
    """
    src = SYNC.read_text(encoding="utf-8")
    sub = src[src.index("def export_bundle"):]
    assert 'git("bundle", "create", out, "main")' in sub   # сборка только по main
    assert 'git("bundle", "list-heads", out)' in sub        # проверка после сборки
    assert '"refs/heads/main" not in heads' in sub          # критерий брака
    assert "os.remove(out)" in sub                          # брак не покидает станцию
    assert "ручная сборка по HEAD запрещена" in sub         # причина — вслух


def test_export_bundle_rejects_head_only(tmp_path, monkeypatch, capsys):
    """Ф107 поведением: саботаж сборки по HEAD — брак отловлен и удалён.

    Вечер 24.11 повторить нельзя: даже если сборка уйдёт по HEAD, страж
    увидит отсутствие ветки и не выпустит файл.
    """
    sys.path.insert(0, str(ROOT / "scripts"))
    import server_sync as ss

    station = _repo(tmp_path / "station", "станция")
    monkeypatch.setattr(ss, "ROOT", station)
    monkeypatch.setattr(ss, "DOWNLOAD", tmp_path / "download")

    real_git = ss.git

    def sabotaged_git(*args, **kw):
        if args[:2] == ("bundle", "create"):
            args = args[:-1] + ("HEAD",)   # саботаж: как руками вечером 24.11
        return real_git(*args, **kw)

    monkeypatch.setattr(ss, "git", sabotaged_git)
    out = ss.export_bundle()
    assert out is None, "страж выпустил бандл без refs/heads/main"
    assert not list((tmp_path / "download").glob("*.bundle")), \
        "брак остался лежать на месте выпуска"
    assert "БРАК" in capsys.readouterr().out, "причина брака не сказана вслух"


# ------------------------------------------------------------------- Ф108

def test_golden_handshake_end_to_end(tmp_path, monkeypatch):
    """Ф108 — золотой якорь: бандл станции принимается домом паттерном кнопки.

    Рукопожатие от берега до берега: export_bundle собрал -> list-heads
    несёт refs/heads/main -> «git fetch <bundle> main» в СВЕЖЕМ доме прошёл.
    Это та самая цепочка, которая порвалась 24.11 — теперь она тест.
    """
    sys.path.insert(0, str(ROOT / "scripts"))
    import server_sync as ss

    station = _repo(tmp_path / "station", "станция")
    (station / "circle.txt").write_text("круг 18", encoding="utf-8")
    _git(station, "add", "-A")
    _git(station, "commit", "-m", "круг 18")
    monkeypatch.setattr(ss, "ROOT", station)
    monkeypatch.setattr(ss, "DOWNLOAD", tmp_path / "download")

    out = ss.export_bundle()
    assert out and Path(out).is_file(), "станция не собрала бандл"

    # берег Создателя: свежий дом, точный паттерн кнопки 80 (v3.5, ступень 1)
    dom = _repo(tmp_path / "dom")
    code, out_fetch = _git(dom, "fetch", str(out), "main")
    assert code == 0, "кнопка 80 не смогла бы принять бандл станции: " + out_fetch
    assert _head_of(dom, "FETCH_HEAD") == _head_of(station)


def test_protocol_names_the_rule():
    """Протокол синхронизации называет закон: bundle несёт refs/heads/main.

    Книга не имеет права молчать о законе, по которому живут берега
    (урок круга 17: исключение без причины — забытость, с причиной — закон).
    """
    doc = (ROOT / "docs" / "SYNC_PROTOCOL_v1.md").read_text(encoding="utf-8")
    assert "refs/heads/main" in doc
    assert "двухступенчат" in doc.lower() or "двухступенчатый" in doc
