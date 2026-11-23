# -*- coding: utf-8 -*-
"""core/embedder.py — Ф51 «СЛУГА-ЭМБЕДДЕР» (день-9, 24.11): bge-m3
превращает текст в ВЕКТОР СМЫСЛА — фронт 5 (семантическая память).

СЛУГА ПО ВЫЗОВУ по образцу кодера (8085) и whisper-моста (8086):
порт 8087, поднимает кнопка 93 (или орган сам скажет, что слуга спит —
и как разбудить). Живёт на CPU (-t 4, -ngl 0): VRAM принадлежит глазам
(принцип хозяина ресурса), а эмбеддинг маленькой модели CPU по силам —
запрос летит секундами.

Что даёт: «вспомни по смыслу» (Ф52) ищет не слова, а СМЫСЛ — «про
отпуск» найдёт и «мы уезжали к морю». Косинус слов (память v1) так не
умеет: это другой орган, другие органы не заменяются — расширяются.

API: llama-server --embedding отдаёт /v1/embeddings (OpenAI-совместимо);
старые сборки знают /embedding — пробуем оба, честно сообщаем, что
поняла сборка.
"""
from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path
from typing import Optional

from core import config

EMBED_THREADS = 4            # мозг на 8 ядрах не должен голодать
START_WAIT_SECS = 60         # маленькая модель поднимается быстро


class EmbedderAsleep(RuntimeError):
    """Слуга спит — орган честно откажет, а не притворится."""


def find_model() -> Optional[Path]:
    """bge-m3 в чулане (АРСЕНАЛ: bge-m3-Q8_0.gguf). Имя/квант могли
    поменять — ищем по шаблону; нет — None, честно."""
    for pat in ("*bge-m3*.gguf", "*bge*m3*.gguf", "*bge*.gguf"):
        cands = sorted(config.MODELS_DIR.glob(pat))
        if cands:
            return cands[0]
    return None


def find_server() -> Optional[Path]:
    """Бинарник llama-server из сборки дома — тот же, что служит мозгу
    и глазам (в режиме --embedding он служит эмбеддингам)."""
    for base in (config.HOME_DIR / "llama.cpp", config.HOME_DIR):
        p = base / "llama-server.exe"
        if p.is_file():
            return p
    return None


def alive() -> bool:
    """Жив ли слуга: любой HTTP-ответ с порта — жив (как у whisper-моста:
    нам достаточно, что порт служит)."""
    import requests
    try:
        requests.get(config.EMBEDDER_URL, timeout=2)
        return True
    except Exception:
        return False


def _spawn(server: Path, model: Path) -> str:
    """Поднять слугу в своей консоли. Флаги без кавычек-мусора, значение
    простые: закон дня-8 (неизвестный флаг убивает сервер) не нарушен —
    берём только флаги семейства llama-server."""
    cmd = ('"%s" -m "%s" --embedding --pooling mean -ngl 0 -t %d '
           '--host 127.0.0.1 --port %d'
           % (server, model, EMBED_THREADS, config.PORT_EMBEDDER))
    subprocess.Popen(cmd, shell=True, cwd=str(config.HOME_DIR),
                     creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0))
    return cmd


def ensure_server(wait_secs: Optional[float] = None) -> tuple:
    """Поднять слугу: (жив ли, честная сводка). Образец — whisper-мост."""
    if alive():
        return True, "слуга-эмбеддер уже на порту %d" % config.PORT_EMBEDDER
    server = find_server()
    model = find_model()
    if not server:
        return False, ("не нашла llama-server.exe в сборке дома — "
                       "слуге нечем служить")
    if not model:
        return False, ("не нашла bge-m3 в чулане (models/) — спроси "
                       "архитектора, куда легла модель")
    _spawn(server, model)
    deadline = time.time() + (wait_secs if wait_secs is not None
                              else START_WAIT_SECS)
    while time.time() < deadline:
        if alive():
            return True, ("слуга-эмбеддер поднялся на порту %d (CPU, "
                          "%d потоков — глазам VRAM не трогаем)"
                          % (config.PORT_EMBEDDER, EMBED_THREADS))
        time.sleep(2.0)
    return False, ("слуга не ожил за %d с — посмотри его консоль "
                   "(модель не та? сборка не знает --embedding?)"
                   % START_WAIT_SECS)


def lay_to_rest() -> str:
    """Уложить слугу (кнопка 93, второй выбор): семантика — по вызову."""
    from core.vram import stop_llama
    if stop_llama(config.PORT_EMBEDDER, server_name="llama-server"):
        return "слуга-эмбеддер уложен — порт %d свободен" % config.PORT_EMBEDDER
    if not alive():
        return "слуга и так спал — порт %d тих" % config.PORT_EMBEDDER
    return "не смогла уложить слугу — скажи архитектору"


def embed(texts: list) -> list:
    """Векторы смысла для списка текстов (батчем). Слуга спит —
    EmbedderAsleep (честный отказ, орган не врёт векторами из головы).

    Путь /v1/embeddings (OpenAI-совместимый); старая сборка не знает
    его — пробуем /embedding по одному тексту. Пустой список — пустой
    ответ (не ошибка: «нечего векторизовать» — законная ситуация)."""
    import requests
    clean = [str(t or "").strip() for t in texts
             if str(t or "").strip()]
    if not clean:
        return []
    if not alive():
        raise EmbedderAsleep("слуга-эмбеддер спит на порту %d"
                             % config.PORT_EMBEDDER)
    try:
        r = requests.post(config.EMBEDDER_URL + "/v1/embeddings",
                          json={"input": clean},
                          timeout=config.EMBEDDER_TIMEOUT_SEC)
        if r.status_code == 200:
            data = (r.json() or {}).get("data") or []
            out = [d.get("embedding") for d in data
                   if isinstance(d, dict)]
            if len(out) == len(clean) and all(out):
                return out
        # фоллбэк: старый путь /embedding — по одному
        out = []
        for t in clean:
            r = requests.post(config.EMBEDDER_URL + "/embedding",
                              json={"content": t},
                              timeout=config.EMBEDDER_TIMEOUT_SEC)
            if r.status_code != 200:
                raise EmbedderAsleep("слуга ответил кодом %d на /embedding"
                                     % r.status_code)
            v = (r.json() or {}).get("embedding")
            if not isinstance(v, list):
                raise EmbedderAsleep("слуга вернул не вектор")
            out.append(v)
        return out
    except EmbedderAsleep:
        raise
    except Exception as e:
        raise EmbedderAsleep("слуга не ответил: %s" % e)
