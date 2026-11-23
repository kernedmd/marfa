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
import datetime as dt
import json
import time
import uuid
import re
import math

from core import config   # FIX 2026-11-18: config.DATA_DIR использовался без импорта


def _clean_metadata(md):
    """Готовит метаданные для ChromaDB add/upsert: убирает None и пустые списки.

    Пустая метадата — {} (не None): metadatas=[None] разные версии ChromaDB
    трактуют по-разному (H10 аудита 22.11) — предсказуемость важнее."""
    if not md:
        return {}
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
    return out


def _norm(text: str) -> str:
    """Нормализация для дедупа: нижний регистр, без пунктуации и лишних пробелов."""
    return re.sub(r"\s+", " ", re.sub(r"[^\wа-яё\s]", " ", text.lower(), flags=re.UNICODE)).strip()


def _tokens(text: str) -> set[str]:
    return set(_norm(text).split()) - {"", "и", "в", "на", "с", "по", "the", "a", "of"}


def _sentence(text: str, max_chars: int = 90) -> str:
    """Первая фраза воспоминания — строка выжимки (№7)."""
    text = re.sub(r"\s+", " ", (text or "").strip())
    m = re.search(r"^(.+?[.!?…])(\s|$)", text)
    sent = m.group(1) if m else text
    return sent[:max_chars].rstrip() + ("…" if len(sent) > max_chars else "")


def _cosine_tokens(a: set[str], b: set[str]) -> float:
    """Косинус по мешку токенов — релевантность офлайн-фоллбэка."""
    if not a or not b:
        return 0.0
    inter = len(a & b)
    return inter / math.sqrt(len(a) * len(b))


def _ts(v, default=None) -> Optional[float]:
    """Честный таймстамп из чего угодно (K5 аудита 22.11): число — как есть,
    ISO-строка — в float, мусор/None — default. Одна запись с created_at
    строкой (импорт, ручная правка, будущая миграция) не должна ронять
    recall/compress_old всего дома."""
    if v is None:
        return default
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return dt.datetime.fromisoformat(str(v)).timestamp()
    except ValueError:
        return default


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
        """Битый файл не убивает память (H2 аудита): нечитаемое — [],
        битый JSON откладывается рядом с меткой времени (.broken-<ts>) —
        данные не затираются молча, их можно спасти руками."""
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except OSError:
            return []
        except ValueError:
            aside = self.path.with_name(
                "%s.broken-%d" % (self.path.name, int(time.time())))
            try:
                self.path.replace(aside)
            except OSError:
                pass
            return []
        if not isinstance(data, list):
            return []
        return [r for r in data if isinstance(r, dict)]

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

    def find_by_norm(self, norm: str) -> Optional[dict]:
        """Дедуп без полного перебора чужих путей: точное совпадение norm.
        Старые записи без norm (до v4) — досчитываем на лету (M8 аудита)."""
        for rec in self._load():
            if rec.get("norm") == norm:
                return rec
            if not rec.get("norm") and rec.get("text") \
                    and _norm(rec["text"]) == norm:
                return rec
        return None

    def get_by_ids(self, ids: list[str]) -> list[dict]:
        wanted = set(ids)
        return [r for r in self._load() if r["id"] in wanted]


class ChromaBackend:
    """ChromaDB (основной путь на Z440, где пакет установлен)."""

    def __init__(self, path: Path, collection: str = "marfa") -> None:
        import chromadb  # ленивый импорт: на машине без пакета уходим в фоллбэк

        self.client = chromadb.PersistentClient(path=str(path))
        self.col = self.client.get_or_create_collection(collection)

    @staticmethod
    def _rows_to_records(got) -> list[dict]:
        out = []
        ids = got.get("ids") or []
        docs = got.get("documents") or []
        metas = got.get("metadatas") or []
        for i, doc, meta in zip(ids, docs, metas):
            out.append({"id": i, "text": doc, **(meta or {})})
        return out

    def add(self, rec: dict) -> None:
        # K4 аудита: links больше НЕ выкидывается из метаданных —
        # remember(links=...) молча терял связи, а link() их не находил
        self.col.add(ids=[rec["id"]], documents=[rec["text"]],
                     metadatas=[_clean_metadata({k: v for k, v in rec.items()
                                                 if k not in ("id", "text")})])

    def all_records(self) -> list[dict]:
        return self._rows_to_records(self.col.get())

    def get_by_ids(self, ids: list[str]) -> list[dict]:
        """Точечный запрос — без полного скана коллекции (H1 аудита)."""
        if not ids:
            return []
        return self._rows_to_records(self.col.get(ids=ids))

    def find_by_norm(self, norm: str) -> Optional[dict]:
        """Точный дедуп через where-фильтр по norm — без полного скана
        на каждый remember (H1). Старые записи без norm — досчёт (M8)."""
        recs = self._rows_to_records(self.col.get(where={"norm": norm}))
        if recs:
            return recs[0]
        for rec in self.all_records():
            if not rec.get("norm") and rec.get("text") \
                    and _norm(rec["text"]) == norm:
                return rec
        return None

    def update(self, rec_id: str, patch: dict) -> bool:
        if not self.get_by_ids([rec_id]):
            return False
        # дедуп обновляет и текст записи, не только метаданные
        docs = [patch["text"]] if "text" in patch else None
        self.col.update(ids=[rec_id], documents=docs,
                        metadatas=[_clean_metadata(patch)])
        return True

    def delete(self, rec_id: str) -> bool:
        self.col.delete(ids=[rec_id])
        return True


# ---------------------------------------------------------------
# Память
# ---------------------------------------------------------------
_fallback_lesson_done = False     # M13: урок фоллбэка — раз за процесс, не спамим


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
            # M13 аудита: тихий откат на пустой JSON — потеря дня памяти.
            # Пишем урок один раз за процесс: Создатель и доктор увидят.
            global _fallback_lesson_done
            if not _fallback_lesson_done:
                _fallback_lesson_done = True
                try:
                    from evolution.journal import log_lesson
                    log_lesson("память-фоллбэк",
                               "ChromaDB не поднялась — живу на JSON-фоллбэке; "
                               "если он пуст, а Chroma раньше работала — "
                               "скажи Создателю, свежие данные могли не доехать")
                except Exception:
                    pass
        self.ttl_hours = ttl_hours

    # ---------- внутреннее ----------
    def _records(self) -> list[dict]:
        return self.backend.all_records() if self.backend else self.fallback.all_records()

    def _backend(self):
        """Активный бэкенд (chroma или JSON-фоллбэк)."""
        return self.backend or self.fallback

    def _now(self) -> float:
        return time.time()

    def _alive(self, rec: dict) -> bool:
        # K5 аудита: expire_at может прийти строкой (импорт/ручная правка) —
        # str > float кидал TypeError и ронял recall целиком
        exp = _ts(rec.get("expire_at"))
        return exp is None or exp > self._now()

    def count(self) -> int:
        """Живых (не истёкших) записей. Для самопознания («изучи себя»)
        и статуса: цифра настоящая, из любого бэкенда — chroma или JSON."""
        return sum(1 for rec in self._records() if self._alive(rec))

    def recent(self, since_ts: float, limit: int = 5) -> list[dict]:
        """Живые записи, созданные ПОСЛЕ since_ts (Ф4 «что нового»).

        Свежие — сверху (created_at по убыванию). Битые created_at —
        мимо: дайджест строится из честных дат, а не из мусора."""
        out = []
        for rec in self._records():
            if not self._alive(rec):
                continue
            created = _ts(rec.get("created_at"))
            if created is not None and created > since_ts:
                out.append(rec)
        out.sort(key=lambda r: _ts(r.get("created_at")) or 0.0, reverse=True)
        return out[:limit]

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

        # Дедуп — ТОЧНЫЙ поиск по norm (H1 аудита: без полного скана
        # коллекции на каждый remember; M8: старые записи без norm
        # находятся досчётом внутри find_by_norm)
        dup = self._backend().find_by_norm(norm)
        if dup is not None and self._alive(dup):
            # M2 аудита: tags=[] — честная очистка, а не «оставить как было»
            patch = {"text": text,
                     "tags": tags if tags is not None else (dup.get("tags") or []),
                     "importance": max(importance, float(dup.get("importance", 1))),
                     "expire_at": expire, "updated_at": now, "hits": dup.get("hits", 0)}
            self._backend().update(dup["id"], patch)
            dup.update(patch)
            return dup

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
            # K5 аудита: created_at строкой не роняет recall
            created = _ts(rec.get("created_at"), self._now())
            age_h = max(0.0, (self._now() - created) / 3600)
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
            # H1 аудита: точечный запрос вместо полного скана коллекции
            if not self.backend.get_by_ids([rec_id]):
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

    # ---------- №7: сжатие памяти (механическое, гейт §5 — без LLM) ----------

    def compress_old(self, days: int = 7, min_group: int = 5,
                     now: Optional[float] = None) -> dict:
        """Старые воспоминания — уплотнить в выжимки по дням.

        Честная механика (доктрина §5: до вердикта батареи больной мозг
        не переписывает память): выжимка — первые фразы, ничего не
        выдумывается. Не трогаем: важное (importance >= 4), библиотеку,
        уже готовые выжимки. Группы меньше min_group остаются как есть —
        дробить память на крохи хуже, чем держать.
        """
        now = now if now is not None else self._now()
        horizon = now - days * 86400
        protected = {"выжимка", "библиотека"}
        by_day: dict[str, list[dict]] = {}
        for rec in self._records():
            if not self._alive(rec):
                continue
            if set(rec.get("tags") or []) & protected:
                continue
            if float(rec.get("importance", 1)) >= 4:
                continue
            # K5 аудита: created_at строкой/мусором — не роняет сжатие;
            # битую дату не сжимаем вслепую — пропускаем запись
            created = _ts(rec.get("created_at"))
            if created is None or created > horizon:
                continue
            day = dt.datetime.fromtimestamp(created).strftime("%d.%m.%Y")
            by_day.setdefault(day, []).append(rec)

        stats = {"compressed": 0, "digests": 0, "days": []}
        # дни — по датам, не по строкам («01.02» < «31.01» лексикографически)
        for day, recs in sorted(by_day.items(),
                                key=lambda kv: dt.datetime.strptime(kv[0], "%d.%m.%Y")):
            if len(recs) < min_group:
                continue
            recs = sorted(recs, key=lambda r: -float(r.get("importance", 1)))
            lines = ["- " + _sentence(r["text"]) for r in recs[:15]]
            if len(recs) > 15:
                lines.append("- … и ещё %d короче" % (len(recs) - 15))
            digest = ("Выжимка памяти за %s (%d воспоминаний):\n%s"
                      % (day, len(recs), "\n".join(lines)))
            self.remember(digest, tags=["выжимка"], importance=3,
                          ttl_hours=24 * 90)
            # M4 аудита: считаем только реально забытые — не врём в отчёте
            gone = sum(1 for r in recs if self.forget(r["id"]))
            stats["compressed"] += gone
            stats["digests"] += 1
            stats["days"].append(day)
        return stats

    def link(self, id_a: str, id_b: str) -> bool:
        """Граф связей: двусторонняя ссылка между воспоминаниями.

        M3 аудита: один проход по записям — раньше было три полных скана
        плюс два повторных (на 10 000 записей — заметные секунды)."""
        recs = {r["id"]: r for r in self._records()}
        if id_a not in recs or id_b not in recs:
            return False
        for a, b in ((id_a, id_b), (id_b, id_a)):
            links = recs[a].get("links") or []
            if b not in links:
                self._backend().update(a, {"links": links + [b]})
        return True
