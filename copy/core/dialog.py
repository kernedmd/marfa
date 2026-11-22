# -*- coding: utf-8 -*-
"""core/dialog.py — №10 «Длинные разговоры» + №11 «История чата» (роадмап-30).

Память диалога на стороне дома: Марфа помнит разговор не только пока
страница открыта, но и после F5 и после перезапуска панели — сессии
лежат в data/dialog/session_<id>.json.

Дисциплина контекста (доктрина §4, Ф53, ADR-005):
- в мозг уходит не вся история, а сжатая: последние ходы дословно
  в бюджете HISTORY_BUDGET_TOKENS (1000), более старые — одной
  строкой-выжимкой «Ранее в разговоре»;
- ЯДРО системного промпта остаётся первым и неизменным — история
  вставляется ПОСЛЕ него, префиксный KV-кэш (№7) не страдает;
- выжимка офлайн (первое предложение хода) — без LLM: гейт качества
  (доктрина §5) запрещает больному мозгу переписывать разговор.

Имена сессий — только [A-Za-z0-9_-] до 64 знаков: никаких побегов
из data/dialog/ (урок калитки хвоста, №26).
"""
from __future__ import annotations

import datetime as dt
import json
import re
import time
from pathlib import Path
from typing import Optional

from core import config

_SESSION_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_KEEP_DAYS = 7          # сколько дней живут неактивные сессии на диске
_MAX_TURNS = 500        # потолок файла сессии — защита от бесконечного роста


def _safe_session(session_id: str) -> str:
    """Валидное имя сессии или ValueError. Побег из папки невозможен."""
    sid = (session_id or "").strip()
    if not _SESSION_RE.match(sid):
        raise ValueError("имя сессии: только буквы/цифры/_/- , до 64 знаков")
    return sid


def _first_sentence(text: str, max_chars: int = 100) -> str:
    """Первая законченная фраза — честная офлайн-выжимка (как Ф53)."""
    text = re.sub(r"\s+", " ", (text or "").strip())
    m = re.search(r"^(.+?[.!?…])\s", text)
    sent = m.group(1) if m else text
    return sent[:max_chars].rstrip() + ("…" if len(sent) > max_chars else "")


def _cap_words(text: str, budget_tokens: int) -> str:
    """Жёсткий потолок по токенам, режем только по границе слов."""
    limit = budget_tokens * config.CHARS_PER_TOKEN_EST
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0]
    return cut.rstrip(" ,;:") + "…"


class DialogStore:
    """Сессии диалогов на диске. Один вызов — один файл, всё атомарно."""

    def __init__(self, data_dir: Optional[Path] = None) -> None:
        self.dir = Path(data_dir) if data_dir else config.DATA_DIR / "dialog"
        self.dir.mkdir(parents=True, exist_ok=True)

    # ---------- пути ----------

    def _path(self, session_id: str) -> Path:
        return self.dir / ("session_%s.json" % _safe_session(session_id))

    # ---------- чтение/запись ----------

    def turns(self, session_id: str) -> list[dict]:
        """Ходы сессии. Нет файла/битый JSON — пусто, дом не падает.
        Плохое имя сессии — ValueError (калитка, не глотаем)."""
        path = self._path(session_id)   # валидация имени — до молчаливого try
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            turns = data.get("turns", []) if isinstance(data, dict) else []
            return [t for t in turns
                    if isinstance(t, dict) and t.get("role") in ("user", "assistant")]
        except (OSError, ValueError):
            return []

    def append(self, session_id: str, role: str, text: str) -> dict:
        """Дописать ход. Роль — только user/assistant (не выдумываем системных)."""
        if role not in ("user", "assistant"):
            raise ValueError("роль хода: user или assistant")
        text = (text or "").strip()
        if not text:
            raise ValueError("пустой ход не записывается")
        path = self._path(session_id)
        turns = self.turns(session_id)
        turn = {"role": role, "text": text[:8000],
                "ts": dt.datetime.now().strftime("%d.%m %H:%M")}
        turns.append(turn)
        if len(turns) > _MAX_TURNS:               # потолок: свежее важнее
            turns = turns[-_MAX_TURNS:]
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"session": _safe_session(session_id),
                                   "turns": turns},
                                  ensure_ascii=False, indent=1),
                       encoding="utf-8")
        tmp.replace(path)                          # атомарно: цельный или старый
        return turn

    def sessions(self) -> list[str]:
        """Все сессии (для дневника и чистки)."""
        return sorted(p.stem[len("session_"):] for p in self.dir.glob("session_*.json"))

    def prune(self, keep_days: int = _KEEP_DAYS,
              now: Optional[float] = None) -> list[str]:
        """Удалить сессии, молчащие дольше keep_days. Возвращает имена."""
        now = now if now is not None else time.time()
        gone = []
        for p in self.dir.glob("session_*.json"):
            try:
                if now - p.stat().st_mtime > keep_days * 86400:
                    p.unlink()
                    gone.append(p.stem[len("session_"):])
            except OSError:
                pass
        return gone

    # ---------- выдача в мозг ----------

    @staticmethod
    def render_messages(turns: list[dict],
                        budget: int = config.HISTORY_BUDGET_TOKENS) -> list[dict]:
        """История ходов -> сообщения для мозга, не длиннее бюджета токенов.

        Гарантии Ф53: новейший ход всегда дословно; старое за пределами
        бюджета — одной выжимкой в начале (без LLM, гейт §5 уважен).
        """
        clean = [t for t in turns if t.get("role") in ("user", "assistant")
                 and (t.get("text") or "").strip()]
        if not clean:
            return []

        # 1) дословный хвост: с новейшего, пока влезает (треть — запас под выжимку)
        tail: list[dict] = []
        used = 0
        reserve = budget // 3
        for t in reversed(clean):
            need = config.token_estimate(t["text"]) + 2
            if tail and used + need > budget - reserve:
                break
            if not tail and need > budget:
                # крайний случай: даже новейший ход длиннее всего бюджета —
                # честная выжимка фразы, не пустота и не обрубок посередине слова
                return [{"role": t["role"],
                         "content": _cap_words(_first_sentence(t["text"]), budget)}]
            tail.insert(0, {"role": t["role"], "content": t["text"]})
            used += need

        # 2) более старые ходы — одной строкой-выжимкой
        older = clean[:len(clean) - len(tail)]
        out: list[dict] = []
        if older:
            lines = []
            for t in older[-12:]:                   # глубже 12 ходов не тянем
                line = "- %s: %s" % (t["role"], _first_sentence(t["text"]))
                if config.token_estimate("\n".join(lines + [line])) > reserve:
                    break
                lines.append(line)
            if lines:
                out.append({"role": "user",
                            "content": "(Ранее в разговоре, кратко:)\n"
                                       + "\n".join(lines)})
        return out + tail
