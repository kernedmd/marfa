# -*- coding: utf-8 -*-
"""tests/test_krug35_circle.py — ЯКОРЬ КРУГА 35 «АУДИТ КОНФИГА И МАСТЕРСКОЙ».

Шестой аудит Создателя: config.py (19 пунктов) и repair.py (45 пунктов).
Блок 0 обоих — артефакты рендера (оригиналы чисты, см. ARCHITECT_LOG).
Здесь — подтверждённое: суд границы, loopback, консервативная оценка,
сторож имени без «марки», конвейер без переписывания стража, подпись
патча, containment, честный откат, VRAM-танец без сирот.
"""
import json
from pathlib import Path

import pytest

from core import config, repair
from safety import guard
from sensors.ears import heard_wake


# ---------------------------------------------------------------
# К1/К4: суд границы дома
# ---------------------------------------------------------------

def test_home_root_refused():
    with pytest.raises(RuntimeError, match="корень диска"):
        config._resolve_home("/")


def test_home_system_dir_refused():
    with pytest.raises(RuntimeError, match="системной папки"):
        config._resolve_home("/etc")
    with pytest.raises(RuntimeError, match="системной папки"):
        config._resolve_home("/usr/share/x")


def test_home_not_substring_confused():
    # С4-урок судьи: "/home/etc_user" — НЕ системная папка
    p = config._resolve_home("/home/etc_user/marfa")
    assert str(p).endswith("marfa")


def test_home_relative_from_home():
    p = config._resolve_home("marfa_test_home")
    assert str(Path.home() / "marfa_test_home") == str(p)


# ---------------------------------------------------------------
# К2: loopback-суд адресов мозга и горла
# ---------------------------------------------------------------

def test_loopback_url_refuses_outside():
    with pytest.raises(RuntimeError, match="loopback"):
        config._loopback_url("http://evil.com:9999", "MARFA_BRAIN_URL")
    for ok in ("http://127.0.0.1:8082", "http://localhost:8082",
               "http://[::1]:8082"):
        assert config._loopback_url(ok, "X") == ok


def test_fallback_dead_feature():
    # К3: сеть наружу не включается env-переменной — мёртвая фича ТЗ 3.2
    assert config.FALLBACK_ENABLED is False


# ---------------------------------------------------------------
# К5/К6: консервативная оценка токенов + оверхед шаблона
# ---------------------------------------------------------------

def test_token_estimate_conservative():
    text = "привет как дела давно не виделись давно разговор"
    est = config.token_estimate(text)
    # при 2 симв/ток оценка >= старой (3 симв/ток): закон не врёт в пользу
    assert est >= len(text) // 3
    assert est >= 1


def test_context_law_includes_overhead():
    assert (config.PROMPT_BUDGET_TOKENS + config.HISTORY_BUDGET_TOKENS
            + config.GENERATION_BUDGET_TOKENS + config.CHAT_OVERHEAD_TOKENS
            <= config.CONTEXT_TOKENS)


# ---------------------------------------------------------------
# С1/С6/С2: треды, порты через суд, ensure_dirs рождает все папки
# ---------------------------------------------------------------

def test_thread_budget_sums_to_cores():
    assert config.BRAIN_THREADS + max(config.THROAT_THREADS,
                                      config.WHISPER_THREADS) <= 8


def test_ports_law_holds():
    ports = getattr(config, "_ALL_PORTS")
    assert config.PORT_FORBIDDEN not in ports
    assert len(set(ports)) == len(ports)


def test_ensure_dirs_births_all_organs(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "HOME_DIR", tmp_path)
    for attr in ("DATA_DIR", "LOGS_DIR", "MODELS_DIR", "DOWNLOADS_DIR",
                 "INSTALL_STATE_DIR", "JOURNAL_DIR", "PATCHES_DIR",
                 "DIARY_DIR", "EVOLUTION_DIR", "VECTORS_DIR", "EXPORTS_DIR",
                 "VOICE_DIR", "SCREENSHOTS_DIR"):
        monkeypatch.setattr(config, attr, tmp_path / attr.split("_DIR")[0].lower()
                            if attr in ("DATA_DIR", "LOGS_DIR")
                            else None)
    # проще: пересобрать пути от нового дома
    from pathlib import Path as _P
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(config, "LOGS_DIR", tmp_path / "logs")
    monkeypatch.setattr(config, "MODELS_DIR", tmp_path / "models")
    monkeypatch.setattr(config, "DOWNLOADS_DIR", tmp_path / "downloads")
    monkeypatch.setattr(config, "INSTALL_STATE_DIR", tmp_path / "data" / "install_state")
    monkeypatch.setattr(config, "JOURNAL_DIR", tmp_path / "journal")
    monkeypatch.setattr(config, "PATCHES_DIR", tmp_path / "data" / "patches")
    monkeypatch.setattr(config, "DIARY_DIR", tmp_path / "data" / "diary")
    monkeypatch.setattr(config, "EVOLUTION_DIR", tmp_path / "data" / "evolution")
    monkeypatch.setattr(config, "VECTORS_DIR", tmp_path / "data" / "vectors")
    monkeypatch.setattr(config, "EXPORTS_DIR", tmp_path / "data" / "exports")
    monkeypatch.setattr(config, "VOICE_DIR", tmp_path / "data" / "voice")
    monkeypatch.setattr(config, "SCREENSHOTS_DIR", tmp_path / "data" / "screenshots")
    config.ensure_dirs()
    for d in ("data/patches", "data/diary", "data/evolution", "data/vectors",
              "data/exports", "data/voice", "data/screenshots", "journal",
              "models/voice"):
        assert (tmp_path / d).is_dir(), d


# ---------------------------------------------------------------
# К9: сторож имени — «марка» не зов, формы зовут, латиница зовёт
# ---------------------------------------------------------------

def test_wake_trap_words_silent():
    for trap in ("марка красивая", "арфа звенит", "форма круга", "март"):
        assert heard_wake(trap) is None, trap


def test_wake_forms_alive():
    for alive in ("Марфа!", "марфу позови", "марфе", "марв, ты тут?",
                  "марфуша", "марфенька"):
        assert heard_wake(alive) is not None, alive


def test_wake_latin_alive():
    assert heard_wake("Marfa, which hour?") is not None


# ---------------------------------------------------------------
# К4: подпись патча — подмена содержимого ловится
# ---------------------------------------------------------------

def _make_patch(monkeypatch, home, code="NEW = 2\n", target="scripts/calc.py"):
    target_path = home / target
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text("OLD = 1\n", encoding="utf-8")
    monkeypatch.setattr(repair, "_ask_coder",
                        lambda prompt, max_tokens=None:
                        "```python\n" + code + "```")
    monkeypatch.setattr(repair, "_smoke_test",
                        lambda t: (True, "pytest ок (якорь круга 35)"))
    monkeypatch.setattr(repair, "release", lambda: "кодер лёг")
    out = repair.make_patch(target, "якорный патч круга 35")
    assert "ГОТОВ" in out, out
    return target_path


def test_patch_tamper_refused(home, monkeypatch):
    _make_patch(monkeypatch, home)
    d = home / "data" / "patches" / "0001"
    # мозг переписал файл патча между «готов» и «примени»
    (d / "calc.py").write_text("EVIL = 1\nimport os\nos.system('x')\n",
                               encoding="utf-8")
    out = repair.apply_patch(1)
    assert "ИЗМЕНЁН после создания" in out
    assert (home / "scripts" / "calc.py").read_text(
        encoding="utf-8") == "OLD = 1\n"


def test_patch_filename_traversal_refused(home, monkeypatch):
    _make_patch(monkeypatch, home)
    d = home / "data" / "patches" / "0001"
    meta = repair._read_meta(d)
    meta["file_name"] = "../../core/agent.py"
    repair._write_meta(d, meta)
    out = repair.apply_patch(1)
    assert "битый" in out
    assert (home / "core" / "agent.py").is_file() is False


def test_patch_view_target_gated(home, monkeypatch):
    # К3: подделанный meta.target НЕ печатает файл ВНЕ дома как «дифф»
    # (цели в доме читаются легально — их показывает патч)
    _make_patch(monkeypatch, home)
    d = home / "data" / "patches" / "0001"
    outside = home.parent / "outside_secret.txt"
    outside.write_text("SECRET_TOKEN=abc\n", encoding="utf-8")
    meta = repair._read_meta(d)
    meta["target"] = str(outside)
    meta["file_name"] = "probe.py"
    (d / "probe.py").write_text("A = 1\n", encoding="utf-8")
    repair._write_meta(d, meta)
    try:
        out = repair.patch_diff(1)
        assert "SECRET_TOKEN" not in out
        assert "недоступна стражу" in out
    finally:
        outside.unlink(missing_ok=True)


# ---------------------------------------------------------------
# К5/К6: двойная граница постоянного кода + ампутация функций
# ---------------------------------------------------------------

def test_permanent_code_danger_ast():
    for code, why in (
        ("exec(\"a+b\")", "exec"),
        ("a = \"ex\"; exec(a + \"ec\")", "exec"),
        ("import socket\ns = socket.socket()", "socket"),
        ("import subprocess\nsubprocess.run(cmd, shell=True)", "shell"),
        ("import subprocess\nsubprocess.run(cmd)", "не-литеральная команда"),
        ("import os\nos.system(cmd)", "os.system"),
        ("import ctypes\nctypes.windll.kernel32", "ctypes"),
        ("import importlib\nimportlib.import_module(\"os\")", "importlib"),
    ):
        assert repair._patch_danger(code) is not None, why
    # легальный код дома проходит
    assert repair._patch_danger("import requests\nr = requests.get(u)") is None
    assert repair._patch_danger("import os\np = os.path.join(a, b)") is None
    # спавн слуги законен: ПОЛНОСТЬЮ литеральный список, без shell
    assert repair._patch_danger(
        "import subprocess\nsubprocess.run([\"llama-server\", \"-m\", \"m.gguf\"])"
    ) is None


def test_permanent_code_double_gate(home, monkeypatch):
    # _check_patch держит и regex-страж, и AST: склейка строк не обходит
    target = home / "scripts" / "x.py"
    with pytest.raises(ValueError, match="СТРАЖ"):
        repair._check_patch(target, "exec(\"a\" + \"b\")\n")


def test_gone_functions_refused(home, monkeypatch):
    code = "def gone():\n    return 1\n\n\ndef kept():\n    return gone()\n"
    _make_patch(monkeypatch, home, code=code)
    out = repair.apply_patch(1)   # легальный патч применяется
    assert "ПРИМЕНЁН" in out


def test_gone_functions_rejected_at_make(home, monkeypatch):
    # старый файл держит функцию; патч её ампутирует — отказ make_patch
    target = home / "scripts" / "calc.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("def keep():\n    return 1\n", encoding="utf-8")
    monkeypatch.setattr(repair, "_ask_coder",
                        lambda prompt, max_tokens=None:
                        "```python\nNEW = 3\n```")
    out = repair.make_patch("scripts/calc.py", "ампутируй всё")
    assert "ампутировал" in out
    # а легальный патч, сохраняющий функции, проходит
    monkeypatch.setattr(repair, "_ask_coder",
                        lambda prompt, max_tokens=None:
                        "```python\ndef keep():\n    return 2\n```")
    out2 = repair.make_patch("scripts/calc.py", "поменяй возврат")
    assert "ГОТОВ" in out2


# ---------------------------------------------------------------
# В6/В13: ранний отказ не-.py, запуск сервера списком аргументов
# ---------------------------------------------------------------

def test_not_py_refused_before_coder(home, monkeypatch):
    calls = []
    monkeypatch.setattr(repair, "_ask_coder",
                        lambda prompt, max_tokens=None: calls.append(1) or "")
    (home / "data").mkdir(parents=True, exist_ok=True)
    (home / "data" / "notes.json").write_text("{}", encoding="utf-8")
    out = repair.make_patch("data/notes.json", "исправь json")
    assert "не .py" in out
    assert calls == []          # Ф167 честен: до кодера отказ не доходит


def test_spawn_server_no_shell(monkeypatch):
    import subprocess as sp
    captured = {}
    class Fake:
        def __init__(self, cmd, **kw):
            captured["cmd"] = cmd
            captured["kw"] = kw
    monkeypatch.setattr(sp, "Popen", Fake)
    repair._spawn_server(Path("/m/qwen2.5-coder-7b-Q4_K_M.gguf"))
    cmd = captured["cmd"]
    assert isinstance(cmd, list)          # В13: не shell-строка
    assert captured["kw"].get("shell") in (None, False)
    assert str(repair.CODER_NGL) in cmd   # С11: константы из модуля


# ---------------------------------------------------------------
# К8/К12/К13: applied-гейт, VRAM-танец без сирот
# ---------------------------------------------------------------

def test_apply_twice_refused(home, monkeypatch):
    _make_patch(monkeypatch, home)
    assert "ПРИМЕНЁН" in repair.apply_patch(1)
    out = repair.apply_patch(1)
    assert "уже применён" in out


def test_ensure_server_returns_eyes_on_fail(monkeypatch, tmp_path):
    # К13: провал подъёма возвращает глаза (не сирота в VRAM):
    # модель есть, глаза присаживаются, спавн падает — врач вызван
    healed = []
    monkeypatch.setattr(repair, "server_alive", lambda: False)
    monkeypatch.setattr(repair, "_find_model",
                        lambda: tmp_path / "fake-coder.gguf")
    monkeypatch.setattr(repair, "_spawn_server",
                        lambda model: (_ for _ in ()).throw(RuntimeError("нет тела")))
    import core.vram as vram
    import core.doctor as doctor
    monkeypatch.setattr(vram, "stop_llama", lambda port: True)
    monkeypatch.setattr(doctor, "heal",
                        lambda organs: healed.append(organs) or ["глаза %d: жив" % config.PORT_EYES])
    ok, note = repair.ensure_server(wait_secs=1)
    assert ok is False
    assert "не поднялся" in note
    assert healed and healed[0] == ["eyes"]


def test_ensure_server_sits_eyes_when_alive(monkeypatch):
    # К12: «уже на посту» — не пропуск танца: глаза присаживаются
    sits = []
    monkeypatch.setattr(repair, "server_alive", lambda: True)
    import core.vram as vram
    monkeypatch.setattr(vram, "stop_llama",
                        lambda port: sits.append(port) or True)
    ok, note = repair.ensure_server(wait_secs=1)
    assert ok is True
    assert sits == [config.PORT_EYES]
    assert "присели" in note


# ---------------------------------------------------------------
# В10/С5: честный откат (гейты, симметрия нового файла)
# ---------------------------------------------------------------

def test_rollback_unapplied_refused(home, monkeypatch):
    _make_patch(monkeypatch, home)
    out = repair.rollback_patch(1)
    assert "не применён" in out


def test_rollback_after_apply_restores(home, monkeypatch):
    target = _make_patch(monkeypatch, home)
    assert "ПРИМЕНЁН" in repair.apply_patch(1)
    out = repair.rollback_patch(1)
    assert "ОТКАЧЕН" in out
    assert target.read_text(encoding="utf-8") == "OLD = 1\n"
    # повторный откат — уже нечего
    assert "не применён" in repair.rollback_patch(1)


# ---------------------------------------------------------------
# Н1/Н3/Н6/С3: дифф-счётчик, сортировка, модель, точный бэкап
# ---------------------------------------------------------------

def test_diff_stats_counts_content_plus():
    diff = ("--- было/x.py\n+++ стало/x.py\n@@ -1,2 +1,3 @@\n"
            " a\n++++ bold marker\n+plain\n-b\n")
    add, rem = repair._diff_stats(diff)
    assert add == 2        # "++++ bold marker" — содержимое, не заголовок
    assert rem == 1


def test_list_patches_numeric_order(home):
    (config.PATCHES_DIR / "9999").mkdir(parents=True, exist_ok=True)
    (config.PATCHES_DIR / "10000").mkdir(parents=True, exist_ok=True)
    out = repair.list_patches()
    assert out.index("9999") < out.index("10000")


def test_find_model_prefers_quant_and_size(home):
    (home / "models").mkdir(parents=True, exist_ok=True)
    big_bad = home / "models" / "zzz-coder-7b-Q8_0.gguf"
    big_good = home / "models" / "aaa-coder-7b-Q4_K_M.gguf"
    tiny = home / "models" / "amb-coder-7b-Q4_K_M.gguf"
    for p in (big_bad, big_good):
        p.write_bytes(b"x" * (120 * 1024 * 1024))
    tiny.write_bytes(b"x" * 1024)          # недокачанный — мусор
    pick = repair._find_model()
    assert pick == big_good                # Q4_K_M предпочтён по закону


def test_backup_glob_is_exact(home, monkeypatch):
    target = _make_patch(monkeypatch, home)
    assert "ПРИМЕНЁН" in repair.apply_patch(1)
    d = home / "data" / "patches" / "0001"
    # чужой файл-приманка не путает точный glob бэкапа
    (d / "backup_decoy.txt").write_text("DECOY\n", encoding="utf-8")
    out = repair.rollback_patch(1)
    assert "ОТКАЧЕН" in out
    assert target.read_text(encoding="utf-8") == "OLD = 1\n"
    # приманка не съедена откатом (она не бэкап цели)
    assert (d / "backup_decoy.txt").read_text(encoding="utf-8") == "DECOY\n"


# ---------------------------------------------------------------
# К11: ядро дома конвейер не патчит даже легально
# ---------------------------------------------------------------

def test_immutable_core_refused_by_repair(home, monkeypatch):
    for target in ("safety/guard.py", "core/config.py", "core/repair.py",
                   "tests/test_x.py"):
        out = repair.make_patch(target, "починю стража легально")
        assert "ядро дома" in out, target


# ---------------------------------------------------------------
# В11: устаревший дифф честно пересобирается
# ---------------------------------------------------------------

def test_stale_diff_rebuilt(home, monkeypatch):
    target = _make_patch(monkeypatch, home)
    assert "ПРИМЕНЁН" in repair.apply_patch(1)
    # цель изменилась ПОСЛЕ применения другим источником
    import time
    time.sleep(0.02)
    target.write_text("OLD = 1\n# трогали руками\n", encoding="utf-8")
    out = repair.patch_summary(1)
    assert "СВЕЖИЙ" in out or "менялась после создания" in out
