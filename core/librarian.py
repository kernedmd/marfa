# -*- coding: utf-8 -*-
"""core/librarian.py — БИБЛИОТЕКАРЬ v0 (Круг Д): Марфа читает дом.

Стремление расти начинается с любопытства: раз в час библиотекарь
берёт ОДИН ещё не прочитанный файл дома (docs/*.md, README) и кладёт
его в память кусочками с тегом «библиотека».

Честность (гейт §5): в память попадают СЛОВА Создателя и архитектора
из файлов дома — дословно, без пересказа больным мозгом. Никакого
интернета: «ничего вне дома» (доктрина §9). LLM-пересказы прочитанного
— после вердикта батареи.

Механика:
- состояние data/librarian_state.json: {файл: {mtime, chunks}};
- изменился файл — перечитывается (дедуп памяти обновит записи);
- выжимка памяти (№7) тег «библиотека» не трогает: книги не сжимают.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Optional

from core import config

CHUNK_CHARS = 900          # кусок ~900 символов:recall ловит, контекст не рвёт
MAX_CHUNKS_PER_FILE = 40   # потолок: гигантский файл не затопит память
TTL_HOURS = 24 * 365       # библиотека живёт год


def library_files(home: Optional[Path] = None) -> list[Path]:
    """Полка дома: docs/*.md и README у корня. Порядок стабильный."""
    home = Path(home) if home else config.HOME_DIR
    out: list[Path] = []
    docs = home / "docs"
    if docs.is_dir():
        out += sorted(p for p in docs.glob("*.md") if p.is_file())
    out += sorted(p for p in home.glob("README*.md") if p.is_file())
    return out


def chunk_text(text: str, chunk_chars: int = CHUNK_CHARS) -> list[str]:
    """Резать по абзацам (пустым строкам), склеивая до chunk_chars."""
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks: list[str] = []
    buf = ""
    for p in paragraphs:
        if buf and len(buf) + len(p) + 2 > chunk_chars:
            chunks.append(buf)
            buf = p
        else:
            buf = (buf + "\n\n" + p) if buf else p
        if len(chunks) >= MAX_CHUNKS_PER_FILE:
            break
    if buf and len(chunks) < MAX_CHUNKS_PER_FILE:
        chunks.append(buf)
    # одиночный абзац длиннее куска — режем по строкам
    final: list[str] = []
    for c in chunks:
        while len(c) > chunk_chars * 2 and len(final) < MAX_CHUNKS_PER_FILE:
            final.append(c[:chunk_chars * 2])
            c = c[chunk_chars * 2:]
        # H8 аудита: лимит — потолок для ВСЕХ кусков, хвост не добавляет 41-й
        if len(final) < MAX_CHUNKS_PER_FILE:
            final.append(c)
    return [c for c in final if c.strip()]


class Librarian:
    def __init__(self, state_path: Optional[Path] = None,
                 home: Optional[Path] = None) -> None:
        self.state_path = Path(state_path) if state_path else config.LIBRARIAN_STATE_FILE
        self.home = Path(home) if home else config.HOME_DIR

    # ---------- состояние ----------

    def _load(self) -> dict:
        try:
            data = json.loads(self.state_path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and isinstance(data.get("files"), dict):
                return data
        except (OSError, ValueError):
            pass
        return {"files": {}}

    def _save(self, data: dict) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.state_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1),
                       encoding="utf-8")
        tmp.replace(self.state_path)

    def _pending(self) -> list[tuple[Path, float]]:
        """Непрочитанное/изменившееся: [(путь, mtime)]."""
        state = self._load()
        out = []
        for p in library_files(self.home):
            try:
                mtime = p.stat().st_mtime
            except OSError:
                continue
            rel = p.relative_to(self.home).as_posix()
            known = state["files"].get(rel)
            if not isinstance(known, dict) or known.get("mtime") != mtime:
                out.append((p, mtime))
        return out

    def read_one(self) -> Optional[dict]:
        """Прочитать ОДИН файл с полки (дёшево, раз в час). None — всё читано."""
        pending = self._pending()
        if not pending:
            return None
        path, mtime = pending[0]
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return None                     # нечитаемое — не повод падать
        rel = path.relative_to(self.home).as_posix()
        tag = path.stem.lower()[:40]

        from core.memory import Memory
        mem = Memory()
        chunks = chunk_text(text)
        stored = 0
        for c in chunks:
            try:
                mem.remember(c, tags=["библиотека", tag], importance=2.5,
                             ttl_hours=TTL_HOURS)
                stored += 1
            except Exception:
                pass                        # память спотыкается — читаем дальше

        # H9 аудита: все куски упали — файл НЕ помечаем прочитанным,
        # повтор через час; молча терять полку нельзя
        if chunks and stored == 0:
            return {"file": rel, "chunks": len(chunks), "stored": 0, "ok": False}

        state = self._load()
        state["files"][rel] = {"mtime": mtime, "chunks": len(chunks)}
        self._save(state)
        # пустой файл (M5): помечаем, чтобы полка шла дальше, — но честно
        # отчитываемся нулём кусков
        return {"file": rel, "chunks": len(chunks), "stored": stored, "ok": True}


def tick() -> str:
    """Точка входа расписания Ф75 (раз в час)."""
    report = Librarian().read_one()
    if not report:
        return "полка прочитана — тишина"
    if not report.get("ok", True):
        return ("память не приняла %s — не пометила прочитанным, "
                "повторю через час" % report["file"])
    if not report["chunks"]:
        return "прочитано %s: файл пустой — двигаюсь дальше" % report["file"]
    return "прочитано %s: %d кусков" % (report["file"], report["chunks"])
