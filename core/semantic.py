# -*- coding: utf-8 -*-
"""core/semantic.py — Ф52 «СМЫСЛОВАЯ ПАМЯТЬ» (день-9, 24.11): фронт 5,
сухим режимом — по образцу рук (орган готов, слуга по кнопке).

«вспомни по смыслу <о чём>» ищет в душе дома СМЫСЛ, а не слова:
bge-m3 (слуга 8087, Ф51) превращает и запрос, и куски души в векторы,
косинус говорит «насколько похоже». «про отпуск» находит и «мы уезжали
к морю» — косинус слов (память v1) так не умеет; органы не заменяются,
а расширяются: дословный поиск («что я говорил») остаётся при своих.

Индексируемая душа: правила дома (№40), дневники (data/diary/), память
(data/memory/). Куски — по абзацам (≤600 симв). Векторный кэш
data/vectors/index.json: sha256 куска — ключ; текст не менялся — вектор
не пересчитывается (инкрементальность, №17 триажа в маленьком виде).

ЧЕСТНОСТЬ СУХОГО РЕЖИМА: слуга спит (не поднята кнопка 93) — орган
говорит правду и зовёт кнопку, а не притворяется поиском; дословные
органы предлагаются как живая альтернатива. Пустой индекс — «не читала
душу» с командой индексации.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path

from core import config

CHUNK_CHARS = 600            # кусок души: абзац до 600 симв
TOP_K = 3                    # сколько воспоминаний по смыслу
MIN_SIMILARITY = 0.35        # ниже — не воспоминание, а совпадение шума


def _index_file() -> Path:
    return Path(config.VECTORS_DIR) / "index.json"


def _sha(text: str) -> str:
    return hashlib.sha256(str(text).encode("utf-8")).hexdigest()[:16]


def _chunks_of(text: str) -> list:
    """Абзацы по-человечески: пустая строка — граница; длинный абзац —
    режем по предложениям, не по буквам середины слова."""
    out = []
    for para in re.split(r"\n\s*\n", str(text or "")):
        para = para.strip()
        if not para or len(para) < 20:
            continue
        while len(para) > CHUNK_CHARS:
            cut = para.rfind(". ", 0, CHUNK_CHARS)
            if cut < CHUNK_CHARS // 2:
                cut = para.rfind(" ", 0, CHUNK_CHARS)
            if cut < CHUNK_CHARS // 2:
                cut = CHUNK_CHARS
            out.append(para[:cut + 1].strip())
            para = para[cut + 1:].strip()
        if para:
            out.append(para)
    return out[:200]   # потолок на источник: душа, не склад


def _sources() -> list:
    """Что индексируем: (путь, метка источника). Пути ленивые."""
    d = Path(config.DATA_DIR)
    out = []
    rules_file = Path(config.RULES_FILE)
    if rules_file.is_file():
        out.append((rules_file, "правило"))
    for p in sorted((d / "diary").glob("*.md")):
        out.append((p, "дневник %s" % p.stem[5:] if p.stem[:5] == "2026-"
                    else "дневник %s" % p.stem))
    mem = d / "memory" / "memory.md"
    if mem.is_file():
        out.append((mem, "память"))
    return out


def _load_index() -> dict:
    try:
        rec = json.loads(_index_file().read_text(encoding="utf-8"))
        if isinstance(rec, dict) and isinstance(rec.get("vectors"), dict):
            return rec
    except (OSError, ValueError):
        pass
    return {"chunks": [], "vectors": {}}


def _save_index(rec: dict) -> None:
    try:
        _index_file().parent.mkdir(parents=True, exist_ok=True)
        _index_file().write_text(
            json.dumps(rec, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass  # индекс не записался — поиск по старому всё равно честен


def reindex() -> str:
    """«переиндексируй смыслы» — пересобрать индекс души. Слуга нужен:
    новые куски векторизует он (старые берутся из кэша)."""
    from core import embedder
    rec = _load_index()
    old_vectors = rec["vectors"]
    chunks: list = []
    new_texts: list = []
    for path, label in _sources():
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        if path.name == "rules.json":
            try:
                data = json.loads(text)
                items = data.get("rules", []) if isinstance(data, dict) else []
                for r in items:
                    if isinstance(r, dict) and r.get("text"):
                        chunks.append({"sha": _sha(r["text"]),
                                       "source": label,
                                       "ref": "№%s" % r.get("n", "?"),
                                       "text": str(r["text"]),
                                       "origin": path.name})
                        if _sha(r["text"]) not in old_vectors:
                            new_texts.append(str(r["text"]))
            except ValueError:
                continue
        else:
            for piece in _chunks_of(text):
                sha = _sha(piece)
                chunks.append({"sha": sha, "source": label,
                               "ref": path.name, "text": piece,
                               "origin": str(path.relative_to(config.DATA_DIR))
                               if str(path).startswith(str(config.DATA_DIR))
                               else path.name})
                if sha not in old_vectors:
                    new_texts.append(piece)
    if new_texts:
        try:
            vectors = embedder.embed(new_texts)
        except embedder.EmbedderAsleep as e:
            return ("слуга-эмбеддер спит — новые куски не векторизовать. "
                    "Кнопка scripts\\93_embedder.bat поднимет его, потом "
                    "скажи «переиндексируй смыслы» ещё раз. (%s)" % e)
        for piece, vec in zip(new_texts, vectors):
            old_vectors[_sha(piece)] = [round(float(x), 6) for x in vec]
    # чистка: векторы кусков, которых больше нет в душе
    live = {c["sha"] for c in chunks}
    rec = {"chunks": chunks,
           "vectors": {k: v for k, v in old_vectors.items() if k in live}}
    _save_index(rec)
    return ("смыслы индексированы: %d кусков души, %d новых векторов "
            "(кэш бережёт старые). Поиск — «вспомни по смыслу <о чём>»"
            % (len(chunks), len(new_texts)))


def _cosine(a: list, b: list) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if not na or not nb:
        return 0.0
    return dot / (na * nb)


def search(query: str, top_k: int = TOP_K) -> list:
    """Топ воспоминаний по смыслу: [{source, ref, text, sim}...].
    Вызывает слугу (один embed запроса); спит — EmbedderAsleep."""
    from core import embedder
    rec = _load_index()
    chunks = [c for c in rec["chunks"]
              if c.get("sha") in rec["vectors"]]
    if not chunks:
        return []
    vec = embedder.embed([query])[0]
    scored = []
    for c in chunks:
        sim = _cosine(vec, rec["vectors"][c["sha"]])
        if sim >= MIN_SIMILARITY:
            scored.append({"source": c.get("source", "?"),
                           "ref": c.get("ref", "?"),
                           "text": c.get("text", ""),
                           "sim": sim})
    scored.sort(key=lambda r: r["sim"], reverse=True)
    return scored[:top_k]


def render(query: str) -> str:
    """«вспомни по смыслу X» — честный ответ со всеми отказами."""
    from core import embedder
    q = str(query or "").strip()
    if not q:
        return "о чём вспомнить по смыслу? скажи «вспомни по смыслу отпуск»"
    rec = _load_index()
    if not rec["chunks"]:
        return ("смысловая память ещё не читала душу — скажи "
                "«переиндексируй смыслы» (нужен слуга-эмбеддер, кнопка 93)")
    if not embedder.alive():
        return ("слуга-эмбеддер спит (порт %d) — по смыслу искать нечем, "
                "врать векторами не буду. Разбудить: кнопка "
                "scripts\\93_embedder.bat. Пока живут дословные органы: "
                "«что я говорил про <слово>» и «вспомни <фразу>»"
                % config.PORT_EMBEDDER)
    try:
        found = search(q)
    except embedder.EmbedderAsleep:
        return ("слуга-эмбеддер спит (порт %d) — по смыслу искать нечем, "
                "врать векторами не буду. Разбудить: кнопка "
                "scripts\\93_embedder.bat. Пока живут дословные органы: "
                "«что я говорил про <слово>» и «вспомни <фразу>»"
                % config.PORT_EMBEDDER)
    if not found:
        return ("по смыслу «%s» в душе не нашлось (порог похожести %.2f). "
                "Может, другими словами? Дословно ищет «что я говорил "
                "про <слово>»" % (q, MIN_SIMILARITY))
    lines = ["ПО СМЫСЛУ «%s»:" % q]
    for r in found:
        lines.append("  · %s (%s) — похожесть %d%%:"
                     % (r["source"], r["ref"], round(r["sim"] * 100)))
        lines.append("      %s" % r["text"][:220])
    return "\n".join(lines)
