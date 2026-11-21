# -*- coding: utf-8 -*-
r"""tests/test_battery_report.py — сводка батареи одним файлом.

Супер-фишка для Создателя: после прогонов батареи в logs/ лежат JSON —
читать глазами тяжело, пересылать по одному неудобно. battery_report.py
собирает всё в один человеческий файл. Проверяем: честность (нет
прогонов — честно), метрики (скорость/пустые/обрывки), полнота (все
ответы в файле), один файл на выходе.
"""
import json
from pathlib import Path

from scripts.battery_report import collect, main, render


def _write_run(logs: Path, tag: str, results):
    logs.mkdir(parents=True, exist_ok=True)
    data = {
        "meta": {"tag": tag, "started": "20261121-200000",
                 "overrides": {"temperature": 0.7}, "max_tokens": 1024},
        "results": results,
    }
    (logs / ("brain_battery_%s_20261121-200000.json" % tag)).write_text(
        json.dumps(data, ensure_ascii=False), encoding="utf-8")


def _r(qid, answer, ref, **kw):
    base = {"id": qid, "question": "Вопрос %s" % qid, "reference": ref,
            "answer": answer, "empty": not answer,
            "think_tag_remnant": kw.get("remnant", False),
            "tok_per_s": kw.get("tok"), "elapsed_s": kw.get("t", 10.0),
            "thinking_chars": kw.get("think", 0)}
    base.update(kw.get("extra", {}))
    return base


def test_collect_empty_is_honest(tmp_path):
    assert collect(tmp_path / "logs") == []


def test_main_without_runs_honest(tmp_path, capsys):
    rc = main(["battery_report.py", str(tmp_path)])
    assert rc == 1
    assert "нет" in capsys.readouterr().out


def test_metrics_speed_and_remnants(tmp_path):
    logs = tmp_path / "logs"
    _write_run(logs, "q4km-fix", [
        _r("F01", "391", "391", tok=10.0, t=10.0),
        _r("F02", "Сидней", "Канберра", tok=20.0, t=10.0),
        _r("H01", "<think>не знаю</think>", "не знаю", remnant=True, tok=None, t=30.0),
    ])
    runs = collect(logs)
    text = render(runs)
    assert "q4km-fix" in text
    assert "15.00 ток/с" in text          # средняя из 10 и 20
    assert "с обрывками think-тегов: 1" in text
    assert "temperature=0.7" in text


def test_answers_included_in_full(tmp_path):
    logs = tmp_path / "logs"
    _write_run(logs, "q4km-default", [_r("F04", "Булгаков", "Булгаков")])
    text = render(collect(logs))
    assert "ВОПРОСЫ И ОТВЕТЫ ПОЛНОСТЬЮ" in text
    assert "Вопрос F04" in text
    assert "Эталон: Булгаков" in text
    assert "Ответ:  Булгаков" in text


def test_empty_answer_shown_as_pusto(tmp_path):
    logs = tmp_path / "logs"
    _write_run(logs, "q4km-default", [_r("H02", "", "не помню")])
    text = render(collect(logs))
    assert "(пусто)" in text
    assert "пустых ответов: 1" in text


def test_broken_json_marked_not_fatal(tmp_path):
    logs = tmp_path / "logs"
    _write_run(logs, "q4km-default", [_r("F01", "391", "391")])
    (logs / "brain_battery_broken_20261121-210000.json").write_text(
        "{не json", encoding="utf-8")
    runs = collect(logs)
    assert len(runs) == 2
    text = render(runs)
    assert "битый JSON" in text
    assert "Вопрос F01" in text   # живой прогон не потерялся


def test_single_file_output(tmp_path):
    logs = tmp_path / "logs"
    _write_run(logs, "q6km-default", [_r("F10", "443", "443")])
    _write_run(logs, "q6km-fix", [_r("F10", "443", "443")])
    rc = main(["battery_report.py", str(tmp_path)])
    assert rc == 0
    out = logs / "battery_report.txt"
    assert out.is_file()
    text = out.read_text(encoding="utf-8")
    assert "q6km-default" in text and "q6km-fix" in text
    assert "ОДИН файл" in text
