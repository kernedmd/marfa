# -*- coding: utf-8 -*-
"""core/history.py — Ф53 «СЖАТИЕ ИСТОРИИ» (ТЗ 3.2, 0.3).

Сжатая история в промпте не более 1000 токенов (ADR-005).
Два уровня сжатия:
  1) офлайн-выжимка (эвристика «первое предложение») — работает всегда, без сети;
  2) суммаризация 30B — когда мозг жив (один вызов, дешевле полного контекста).
Гарантия: render() всегда <= budget, последние ходы — дословно.
"""
from __future__ import annotations

import datetime as dt
import re
from typing import Optional

from core import config


def _first_sentence(text: str, max_chars: int = 120) -> str:
    """Первая законченная фраза — минимальная честная выжимка.

    M6 аудита: точка в КОНЦЕ строки («Привет.») — тоже конец фразы:
    раньше требовался пробел после знака, и однопредложенческий текст
    не резался вовсе (в dialog.py — тот же фикс)."""
    text = re.sub(r"\s+", " ", text.strip())
    m = re.search(r"^(.+?[.!?…])(?:\s|$)", text)
    sent = m.group(1) if m else text
    return sent[:max_chars].rstrip() + ("…" if len(sent) > max_chars else "")


class HistoryCompressor:
    """Хранит ходы диалога; render() отдаёт сжатую историю в лимит бюджета."""

    def __init__(self, brain=None, budget: int = config.HISTORY_BUDGET_TOKENS,
                 keep_recent: int = 4) -> None:
        self.brain = brain            # BrainClient или None
        self.budget = budget          # 1000 (0.3)
        self.keep_recent = keep_recent  # сколько последних ходов держать дословно
        self.turns: list[dict] = []   # {role, text, ts}
        self.last_summary: str = ""   # сводка старых ходов (кэш между render, H3)
        self._sum_cache_key: tuple = ()   # отпечаток ходов, из которых собрана сводка
        self.last_stats: dict = {}

    # ---------- накопление ----------
    def add_turn(self, role: str, text: str) -> None:
        # как dialog.append: системную роль в историю не пишем — она
        # не должна попадать ни в промпт, ни в офлайн-выжимку
        if role not in ("user", "assistant"):
            raise ValueError("роль хода: user или assistant")
        text = (text or "").strip()
        if text:
            self.turns.append({"role": role, "text": text,
                               "ts": dt.datetime.now().strftime("%d.%m %H:%M")})

    # ---------- сжатие ----------
    def _offline_summary(self, old_turns: list[dict]) -> str:
        if not old_turns:
            return ""
        lines = ["- " + t["role"] + ": " + _first_sentence(t["text"]) for t in old_turns]
        return "Ранее в диалоге:\n" + "\n".join(lines)

    def _brain_summary(self, old_turns: list[dict]) -> Optional[str]:
        """Сводка старых ходов силами 30B. Мозг спит/умер — возвращаем None (ADR-002 не нарушаем)."""
        if self.brain is None or not old_turns:
            return None
        dialog = "\n".join(f"{t['role']}: {t['text']}" for t in old_turns)
        try:
            summary = self.brain.chat(
                [{"role": "system",
                  "content": ("Сожми диалог в короткую выжимку фактов и решений "
                              "(до 300 токенов, списком, без воды и без вводных слов).")},
                 {"role": "user", "content": dialog}],
                gen_tokens=300, temperature=0.2,
            )
            return "Ранее в диалоге (сводка):\n" + summary.strip()
        except Exception:
            return None  # любая причина — уходим в офлайн-выжимку

    # ---------- выдача ----------
    def render(self, prefer_brain: bool = True) -> str:
        """Собрать историю <= budget. Новейшие ходы — дословно (резерв под хвост),
        всё более старое — сводкой. Гарантия: newest turn никогда не выбрасывается
        (если один ход не влезает целиком — отдаём его выжимку)."""
        if not self.turns:
            self.last_stats = {"tokens": 0, "kept_verbatim": 0, "summarized": 0, "dropped": 0}
            return ""

        # 1) Дословный хвост: новейшие ходы первыми, пока не исчерпаем
        #    (бюджет минус гарантированная треть под сводку).
        summary_min = self.budget // 3
        tail_lines: list[str] = []
        tail_tok = 0
        tail_src = 0
        for t in reversed(self.turns):
            line = f"{t['role']}: {t['text']}"
            need = config.token_estimate(line) + 1
            if tail_tok + need > self.budget - summary_min and tail_lines:
                break
            tail_lines.insert(0, line)   # chronological порядок в итоге
            tail_tok += need
            tail_src += 1
        # Крайний случай: новейший ход сам длиннее ВСЕГО бюджета — его
        # выжимка (гарантия docstring: newest никогда не выбрасывается).
        # K6 аудита: прежняя ветка `if not tail_lines` была МЁРТВОЙ — цикл
        # всегда добавлял первый ход (`and tail_lines` пропускал перебор),
        # огромный ход попадал в tail, а _fit отрезал его до голого
        # заголовка «Последние ходы:» — пользователь видел пустую историю
        if tail_tok > self.budget and len(tail_lines) == 1:
            newest = self.turns[-1]
            line = f"{newest['role']}: {_first_sentence(newest['text'])}"
            tail_lines = [line]
            tail_tok = config.token_estimate(line) + 1

        # 2) Сводка более старых ходов на остаток бюджета.
        #    H3 аудита: сводка кэшируется по отпечатку старых ходов —
        #    два render подряд не дёргают мозг дважды (сам вызов _brain_summary
        #    дорогой: это второй поход к 30B на каждое сообщение)
        old = self.turns[:-tail_src]
        summary_budget = self.budget - tail_tok
        summary = None
        if prefer_brain:
            key = tuple((t["role"], t["text"]) for t in old)
            if key and key == self._sum_cache_key and self.last_summary:
                summary = self.last_summary          # кэш жив — мозг спит
            else:
                summary = self._brain_summary(old)
                if summary:
                    self._sum_cache_key, self.last_summary = key, summary
        if summary is None:
            summary = self._offline_summary(old)
        summary = self._fit(summary, summary_budget)

        parts = ([summary, "Последние ходы:"] + tail_lines) if summary \
                else ["Последние ходы:"] + tail_lines
        text = "\n".join(p for p in parts if p)
        text = self._fit(text, self.budget)

        # M7 аудита: dropped считается ПОСЛЕ обрезки — сколько ходов
        # реально представлено в тексте, а не «сколько было в списках»
        kept_tail = sum(1 for ln in tail_lines if ln in text)
        dropped = len(self.turns) - len(old) - kept_tail
        self.last_stats = {
            "tokens": config.token_estimate(text),
            "kept_verbatim": kept_tail,
            "summarized": len(old),
            "dropped": max(0, dropped),
        }
        return text

    @staticmethod
    def _fit(text: str, budget: int) -> str:
        """Обрезка по бюджету ТОЛЬКО по границам строк — никогда не режем слово посередине."""
        if config.token_estimate(text) <= budget:
            return text
        lines = text.splitlines()
        out: list[str] = []
        used = 0
        for line in lines:
            need = config.token_estimate(line) + 1
            if used + need > budget:
                break
            out.append(line)
            used += need
        return "\n".join(out)
