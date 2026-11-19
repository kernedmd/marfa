# -*- coding: utf-8 -*-
"""core/memory.py — ПАМЯТЬ МАРФЫ (ТЗ 3.4, ADR-006).

ChromaDB, а если она не поднялась (нет пакета/сбой) — ПРОЗРАЧНЫЙ JSON-фоллбэк.
Агент не обязан знать, на каком бэкенде работает: интерфейс один.

Операции: remember / recall / forget. Сверх ТЗ на каркас: дедуп (тот же текст
обновляет запись, а не плодит копии), TTL (забывается по сроку), связи (граф).
"""
from __future__ import annotations
from typing import Optional
from pathlib import Path
import json
import time
import uuid
import re
import math

from core import config   # FIX 2026-11-18: config.DATA_DIR использовался без импорта


def _clean_metadata(md):
    """Готовит метаданные для ChromaDB add/upsert: убирает None и пустые списки."""
    if not md:
        return None
    out = {}
    for k, v in md.items():
        if v is None:
            continue
        if isinstance(v, (list, tuple)):
            items = [x for x in v if x is not None and isinstance(x, (bool, int, float, str))]
            if not items:
                continue
            t = type(items[0])
            items = [x for x in items if type(x) is t]
            if items:
                out[k] = items
            continue
        if isinstance(v, (bool, int, float, str)):
            out[k] = v
    return out if out else None


def _norm(text: str) -> str:
    """Нормализация для дедупа: нижний регистр, без пунктуации и лишних пробелов."""
    return re.sub(r"\s+", " ", re.sub(r"[^\wа-яё\s]", " ", text.lower(), flags=re.UNICODE)).strip()


def _tokens(text: str) -> set[str]:
    return set(_norm(text).split()) - {"", "и", "в", "на", "с", "по", "the", "a", "of"}


def _cosine_tokens(a: set[str], b: set[str]) -> float:
    """Косинус по мешку токенов — релевантность офлайн-фоллбэка."""
    if not a or not b:
        return 0.0
    inter = len(a & b)
    return inter / math.sqrt(len(a) * len(b))


# ---------------------------------------------------------------
# Бэкенды
# ---------------------------------------------------------------
class JsonBackend:
    """JSON-фоллбэк (ADR-006): один файл data/memory/memory.json. Ноль зависимостей."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text("[]", encoding="utf-8")

    def _load(self) -> list[dict]:
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _save(self, items: list[dict]) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(self.path)  # атомарно: цельный файл или старый

    def add(self, rec: dict) -> None:
        items = self._load()
        items.append(rec)
        self._save(items)

    def all_records(self) -> list[dict]:
        return self._load()

    def update(self, rec_id: str, patch: dict) -> bool:
        items = self._load()
        for rec in items:
            if rec["id"] == rec_id:
                rec.update(patch)
                self._save(items)
                return True
        return False

    def delete(self, rec_id: str) -> bool:
        items = self._load()
        rest = [r for r in items if r["id"] != rec_id]
        if len(rest) == len(items):
            return False
        self._save(rest)
        return True


class ChromaBackend:
    """ChromaDB (основной путь на Z440, где пакет установлен)."""

    def __init__(self, path: Path, collection: str = "marfa") -> None:
        import chromadb  # ленивый импорт: на машине без пакета уходим в фоллбэк

        self.client = chromadb.PersistentClient(path=str(path))
        self.col = self.client.get_or_create_collection(collection)

    def add(self, rec: dict) -> None:
        self.col.add(ids=[rec["id"]], documents=[rec["text"]],
                     metadatas=[_clean_metadata({k: v for k, v in rec.items() if k not in ("id", "text", "links")})])

    def all_records(self) -> list[dict]:
        got = self.col.get()
        out = []
        for i, doc, meta in zip(got["ids"], got["documents"], got["metadatas"]):
            rec = {"id": i, "text": doc, **(meta or {})}
            out.append(rec)
        return out

    def update(self, rec_id: str, patch: dict) -> bool:
        if not any(r["id"] == rec_id for r in self.all_records()):
            return False
        self.col.update(ids=[rec_id], metadatas=[_clean_metadata(patch)])
        return True

    def delete(self, rec_id: str) -> bool:
        self.col.delete(ids=[rec_id])
        return True


# ---------------------------------------------------------------
# Память
# ---------------------------------------------------------------
class Memory:
    """remember/recall/forget. Дедуп: тот же текст → обновление. TTL: expire_at."""

    def __init__(self, data_dir: Optional[Path] = None, ttl_hours: float = 24 * 30) -> None:
        data_dir = Path(data_dir) if data_dir else None
        self.backend = None
        self.fallback: Optional[JsonBackend] = None
        try:
            root = data_dir or Path(config.DATA_DIR)
            self.backend = ChromaBackend(root / "chroma")
        except Exception:  # ImportError или сбой ChromaDB → ADR-006 фоллбэк
            root = data_dir or Path(config.DATA_DIR)
            self.fallback = JsonBackend(root / "memory" / "memory.json")
        self.ttl_hours = ttl_hours

    # ---------- внутреннее ----------
    def _records(self) -> list[dict]:
        return self.backend.all_records() if self.backend else self.fallback.all_records()

    def _now(self) -> float:
        return time.time()

    def _alive(self, rec: dict) -> bool:
        exp = rec.get("expire_at")
        return exp is None or exp > self._now()

    # ---------- API ----------
    def remember(self, text: str, tags: Optional[list[str]] = None,
                 importance: float = 1.0, ttl_hours: Optional[float] = None,
                 links: Optional[list[str]] = None) -> dict:
        """Запомнить. Дедуп: тот же нормализованный текст обновляет существующую запись."""
        text = text.strip()
        if not text:
            raise ValueError("пустой текст помнить нельзя")
        norm = _norm(text)
        now = self._now()
        expire = now + (ttl_hours if ttl_hours is not None else self.ttl_hours) * 3600

        for rec in self._records():
            if rec.get("norm") == norm and self._alive(rec):
                patch = {"text": text, "tags": tags or rec.get("tags", []),
                         "importance": max(importance, float(rec.get("importance", 1))),
                         "expire_at": expire, "updated_at": now, "hits": rec.get("hits", 0)}
                if self.backend:
                    self.backend.update(rec["id"], patch)
                else:
                    self.fallback.update(rec["id"], patch)
                rec.update(patch)
                return rec

        rec = {
            "id": uuid.uuid4().hex[:12],
            "text": text,
            "norm": norm,
            "tags": tags or [],
            "importance": float(importance),
            "created_at": now,
            "updated_at": now,
            "expire_at": expire,
            "hits": 0,
            "links": links or [],
        }
        if self.backend:
            self.backend.add(rec)
        else:
            self.fallback.add(rec)
        return rec

    def recall(self, query: str, top_k: int = 5) -> list[dict]:
        """Вспомнить: релевантность = косинус токенов + вес важности + свежесть."""
        q = _tokens(query)
        scored = []
        for rec in self._records():
            if not self._alive(rec):
                continue
            rel = _cosine_tokens(q, _tokens(rec["text"]))
            age_h = max(0.0, (self._now() - rec.get("created_at", self._now())) / 3600)
            score = rel * (0.5 + 0.5 * min(1.0, float(rec.get("importance", 1)) / 5)) \
                    + 0.05 * math.exp(-age_h / 24)
            if score > 0.01:
                scored.append((score, rec))
        scored.sort(key=lambda p: p[0], reverse=True)
        out = []
        for score, rec in scored[:top_k]:
            rec["score"] = round(score, 4)
            out.append(rec)
        return out

    def forget(self, rec_id: str) -> bool:
        """Забыть по id. Чужой id — False, не исключение."""
        if self.backend:
            known = any(r["id"] == rec_id for r in self._records())
            if not known:
                return False
            return self.backend.delete(rec_id)
        return self.fallback.delete(rec_id)

    def forget_expired(self) -> int:
        """Сборка мусора: удалить просроченные. Возвращает количество."""
        gone = 0
        for rec in self._records():
            if not self._alive(rec):
                self.forget(rec["id"])
                gone += 1
        return gone

    def link(self, id_a: str, id_b: str) -> bool:
        """Граф связей: двусторонняя ссылка между воспоминаниями."""
        known = {r["id"] for r in self._records()}
        if id_a not in known or id_b not in known:
            return False
        for a, b in ((id_a, id_b), (id_b, id_a)):
            rec = next(r for r in self._records() if r["id"] == a)
            links = rec.get("links", [])
            if b not in links:
                patch = {"links": links + [b]}
                if self.backend:
                    self.backend.update(a, patch)
                else:
                    self.fallback.update(a, patch)
        return True
