# -*- coding: utf-8 -*-
"""core/units.py — КОНВЕРТЕР ВЕЛИЧИН (Ф25, 23.11): «переведи 5 км в мили».

Длина, вес, данные и температура — всё, что спрашивается на ходу и не
нуждает мозг (у него нет справочника — закон фактов: дом не выдумывает
коэффициенты). Единицы понимаются в обе стороны, «кг в км» — честный
отказ с подсказкой семейств. Запятая в дроби («5,5 кг») — по-русски.
"""
from __future__ import annotations

import re

# семейства: базовая единица и множители
LENGTH = {                       # база — метр
    "мм": 0.001, "миллиметр": 0.001, "сантиметр": 0.01, "см": 0.01,
    "дм": 0.1, "м": 1, "метр": 1, "метров": 1, "км": 1000,
    "километр": 1000, "дюйм": 0.0254, "фут": 0.3048, "ярд": 0.9144,
    "миля": 1609.344, "мили": 1609.344,
}
WEIGHT = {                       # база — килограмм
    "мг": 1e-6, "г": 0.001, "грамм": 0.001, "кг": 1, "килограмм": 1,
    "кило": 1, "т": 1000, "тонна": 1000, "фунт": 0.45359237,
    "унция": 0.0283495,
}
DATA = {                         # база — байт
    "б": 1, "байт": 1, "кб": 1024, "мб": 1024 ** 2,
    "гб": 1024 ** 3, "тб": 1024 ** 4,
}
TEMP = {"c": "c", "с": "c", "цельсий": "c", "f": "f", "фаренгейт": "f",
        "к": "k", "k": "k", "кельвин": "k"}

FAMILIES = (("длину", LENGTH), ("вес", WEIGHT), ("данные", DATA))


def _norm(unit: str) -> str:
    return str(unit or "").strip().lower().rstrip(".")


def convert(value: float, src: str, dst: str) -> str:
    """Перевести значение; единицы — любые из семей; ошибки честные."""
    src_n, dst_n = _norm(src), _norm(dst)
    # температура — свой род: формулы, не множители
    if src_n in TEMP or dst_n in TEMP:
        return _temp(value, src_n, dst_n)
    for fam_name, table in FAMILIES:
        if src_n in table and dst_n in table:
            out = value * table[src_n] / table[dst_n]
            return "%s %s = %s %s" % (_fmt_in(value), src_n,
                                      _fmt_out(out), dst_n)
    if any(src_n in t for _, t in FAMILIES) or src_n in TEMP:
        return ("не поняла вторую единицу; %s переводится в: %s"
                % (src_n, ", ".join(_peers(src_n))))
    return ("не знаю таких единиц; умею длину (мм…миля), вес (мг…тонна), "
            "данные (б…тб) и температуру (c/f/k): «переведи 5 км в мили»")


def _peers(unit: str) -> list:
    for _, table in FAMILIES:
        if unit in table:
            return [k for k in table if k != unit][:12]
    return []


def _temp(value: float, src_n: str, dst_n: str) -> str:
    if src_n not in TEMP or dst_n not in TEMP:
        return ("температура переводится только в температуру: "
                "«переведи 20 c в f»")
    c = value if src_n == "c" else ((value - 32) / 1.8 if src_n == "f"
                                    else value - 273.15)
    out = c if dst_n == "c" else (c * 1.8 + 32 if dst_n == "f"
                                  else c + 273.15)
    src_l = {"c": "°C", "f": "°F", "k": "K"}[TEMP[src_n]]
    dst_l = {"c": "°C", "f": "°F", "k": "K"}[TEMP[dst_n]]
    return "%s %s = %s %s" % (_fmt_in(value), src_l, _fmt_out(out), dst_l)


def _fmt_in(v: float) -> str:
    s = ("%g" % v)
    return s.replace(".", ",")


def _fmt_out(v: float) -> str:
    if abs(v) >= 1000:
        s = ("%.2f" % v).rstrip("0").rstrip(".")
    elif abs(v) >= 1:
        s = ("%.4f" % v).rstrip("0").rstrip(".")
    else:
        s = ("%.6g" % v)
    return s.replace(".", ",")


def parse(text: str) -> str:
    """«переведи 5 км в мили» / «переведи 20 c в f» / «переведи 5,5 кг в г»."""
    m = re.match(
        r"^переведи\s+(-?\d+(?:[.,]\d+)?)\s+([а-яёa-z]+)\s+в\s+([а-яёa-z]+)$",
        str(text or "").strip().lower().rstrip("?.!"))
    if not m:
        return ("не поняла; скажи «переведи 5 км в мили», "
                "«переведи 72 кг в фунты» или «переведи 20 c в f»")
    value = float(m.group(1).replace(",", "."))
    return convert(value, m.group(2), m.group(3))
