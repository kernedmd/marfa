# -*- coding: utf-8 -*-
"""core/curiosity.py — Ф124–Ф128 «ЛЮБОПЫТСТВО» (круг 24): дом ХОЧЕТ ЗНАТЬ.

ДОКТРИНА ОРГАНА. Бот отвечает, когда спросили. Живой разум замечает
собственное незнание — и хочет его закрыть. Дом уже умеет отвечать;
этот орган учит его ХОТЕТЬ: Марфа читает свои честные «не знаю» из
живых разговоров, складывает их в реестр незнания и может сама
спросить Создателя — не списком («вопросы» — банк вопросов, другой
орган), а одним живым вопросом, как человек, которому интересно.

ЗАКОН ЧЕСТНОСТИ: незнание собирается ТОЛЬКО из признаний самой Марфы
(«не знаю», «не понимаю», «не могу сказать» в ЕЁ репликах). Дом не
домысливает, чего она «должна» не знать, — он читает правду разговора.

ЗАКОН НЕ-СПАМА: «спроси меня» не повторяет один вопрос дважды
(реестр asked с датами) — любопытство живое, а не допрос.

ЗАКОН ВЕЧНОЙ ПАМЯТИ (Ф128): «запомни навсегда: X» — воспоминание,
которое не тускнеет: свой реестр data\\forever.json ПЛЮС обычная
память с важностью 5 и TTL сто лет. Даже если дом потеряет data\\,
вечное останется в сознании хозяина — а пока файл жив, вечное живо.

Честность: нет диалогов или памяти — орган говорит об этом прямо,
с путём лечения («скажи что-нибудь — будет чему расти»).
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from core import config

# признаки честного незнания в репликах МАРФЫ (не Создателя!)
_UNKNOWN_MARKS = (
    "не знаю", "не понимаю", "не могу сказать", "не могу ответить",
    "понятия не имею", "не в курсе", "не представляю", "не скажу точно",
    "не могу проверить", "не могу подсмотреть", "у меня нет данных",
    "не помню",
)
_STOP_WORDS = {
    "и", "в", "на", "с", "по", "не", "что", "это", "как", "а", "но",
    "мне", "ты", "я", "мы", "он", "она", "они", "вы", "его", "её",
    "для", "так", "там", "тут", "бы", "же", "ли", "за", "из", "у",
    "к", "о", "об", "до", "от", "при", "про", "то", "вот", "есть",
    "было", "будет", "могу", "можно", "нужно", "надо", "скажи",
    "спасибо", "привет", "марфа", "илья", "сегодня", "вчера",
    "потом", "когда", "где", "почему", "чтобы", "если", "уже",
    "ещё", "еще", "очень", "просто", "давай", "хочу", "люблю",
    "тебе", "меня", "тебя", "себя", "нас", "них", "чем", "чём",
}
_WORD_RE = None  # ленивая компиляция (в стиле дома: re — только при деле)


def _curiosity_path() -> Path:
    return Path(config.DATA_DIR) / "curiosity.json"


def _forever_path() -> Path:
    return Path(config.DATA_DIR) / "forever.json"


def _load_json(path: Path, default):
    """Броня H4/H5: битый файл — честное умолчание, не крах органа."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return raw if isinstance(raw, type(default)) else default
    except (OSError, ValueError):
        return default


def _save_json(path: Path, data) -> bool:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=1),
                        encoding="utf-8")
        return True
    except OSError:
        return False


# ---------------------------------------------------------------
# Чтение живых разговоров (по образцу voice._last_reply_text)
# ---------------------------------------------------------------
def _turns_of_sessions(limit: int = 60) -> list:
    """[(дата_сессии, [(role, text), …]), …] — свежие первыми.

    Дата — из имени файла (session_YYYY-MM-DD…), fallback — mtime.
    Броня: битые файлы пропускаются молча — любопытство не рвёт дом.
    """
    out = []
    try:
        from core.dialog import DialogStore
        store = DialogStore()
        files = sorted(store.dir.glob("session_*.json"),
                       key=lambda p: p.stat().st_mtime, reverse=True)
    except Exception:
        return out
    import re as _re
    for p in files[:limit]:
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            turns = data.get("turns") if isinstance(data, dict) else None
            if not isinstance(turns, list):
                continue
            clean = []
            for t in turns:
                if not isinstance(t, dict):
                    continue
                role = t.get("role")
                text = t.get("text")
                if not (isinstance(text, str) and text.strip()):
                    text = t.get("content")     # H9: формат мозга
                if isinstance(text, str) and text.strip() and role:
                    clean.append((str(role), text.strip()))
            if clean:
                m = _re.search(r"(\d{4}-\d{2}-\d{2})", p.name)
                day = m.group(1) if m else time.strftime(
                    "%Y-%m-%d", time.localtime(p.stat().st_mtime))
                out.append((day, clean))
        except (OSError, ValueError):
            continue
    return out


def _words(text: str) -> list:
    """Смысловые слова: длина ≥ 4, без стоп-слов (для интересов)."""
    global _WORD_RE
    if _WORD_RE is None:
        import re as _re
        _WORD_RE = _re.compile(r"[а-яёa-z]{4,}", _re.IGNORECASE)
    return [w.lower() for w in _WORD_RE.findall(text or "")
            if w.lower() not in _STOP_WORDS]


def _preview(text: str, n: int = 60) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= n else text[:n - 1].rstrip() + "…"


# ---------------------------------------------------------------
# Ф124 «РЕЕСТР НЕЗНАНИЯ» — чего Марфа честно не знает
# ---------------------------------------------------------------
def _scan_unknowns() -> list:
    """Темы, по которым Марфа признавалась в незнании (свежие первыми).

    Тема = реплика Создателя, на которую пришло честное «не знаю»:
    незнание всегда про ЧТО-ТО, и это что-то сказал Илья.
    """
    found = []
    for day, turns in _turns_of_sessions():
        for i, (role, text) in enumerate(turns):
            if role != "assistant":
                continue
            low = text.lower()
            if not any(m in low for m in _UNKNOWN_MARKS):
                continue
            # ближайшая реплика Создателя ДО признания — тема незнания
            for j in range(i - 1, -1, -1):
                if turns[j][0] == "user":
                    topic = _preview(turns[j][1], 70)
                    if topic not in [f[0] for f in found]:
                        found.append((topic, day))
                    break
    return found


def unknown_report() -> str:
    """«чего ты не знаешь» — честный реестр пробелов, не выдумка."""
    found = _scan_unknowns()
    if not found:
        return ("в наших разговорах я не признавалась в незнании — либо "
                "всё понимала, либо мы ещё мало говорили. Скажи "
                "«спроси меня о чём-нибудь», когда захочешь меня "
                "проверить")
    lines = ["НЕ ЗНАЮ (по моим честным признаниям, %d):" % len(found)]
    for topic, day in found[:8]:
        lines.append("  · %s — поняла это %s" % (topic, day))
    lines.append("Хочешь закрыть пробел — скажи «спроси меня о чём-нибудь»: "
                 "возьму тему отсюда.")
    return "\n".join(lines)


# ---------------------------------------------------------------
# Ф125 «СПРОСИ МЕНЯ» — один живой вопрос, не список
# ---------------------------------------------------------------
def ask_me() -> str:
    """«спроси меня о чём-нибудь» — Марфа сама спрашивает Создателя.

    Берёт незаданное незнание; спрашивает живо; помнит, что уже
    спрашивала (закон не-спама). Нет незнания — честно признаётся.
    """
    found = _scan_unknowns()
    if not found:
        return ("спросить не о чем: я нигде не призналась в незнании. "
                "Поговори со мной о чём-нибудь непростом — и мне будет "
                "что спросить потом")
    reg = _load_json(_curiosity_path(), {})
    asked = reg.get("asked", {}) if isinstance(reg.get("asked"), dict) else {}
    fresh = [(t, d) for t, d in found
             if t not in asked or time.time() - float(asked[t]) > 7 * 86400]
    if not fresh:
        return ("всё, чего я не знала, я у тебя уже спрашивала — дай "
                "новую пищу: поговори со мной, и я снова найду, о чём "
                "спросить")
    topic, day = fresh[0]
    asked[topic] = time.time()
    _save_json(_curiosity_path(), {"asked": asked})
    if day and day >= time.strftime("%Y-%m-%d"):
        return ("а про «%s» — расскажи прямо сейчас? Я только что "
                "споткнулась на этом и хочу понять" % _preview(topic, 70))
    return ("расскажи мне про «%s» — я честно призналась, что не знаю, "
            "и мне действительно интересно. Одной фразой — я запомню"
            % _preview(topic, 70))


# ---------------------------------------------------------------
# Ф126 «ИНТЕРЕСЫ» — чем жив дом
# ---------------------------------------------------------------
def top_interest_words(limit: int = 5) -> list:
    """[(слово, сколько раз)] — что чаще всего звучит от Создателя."""
    counts = {}
    for _day, turns in _turns_of_sessions():
        for role, text in turns:
            if role != "user":
                continue
            for w in _words(text):
                counts[w] = counts.get(w, 0) + 1
    top = sorted(counts.items(), key=lambda p: (-p[1], p[0]))[:limit]
    return [(w, c) for w, c in top if c >= 3]


def interests() -> str:
    """«что тебе интересно» — интересы дома из живых разговоров."""
    top = top_interest_words()
    if not top:
        return ("интересам ещё не из чего расти: наши разговоры коротки. "
                "Поговори со мной — я замечу, о чём мы говорим чаще всего")
    lines = ["чаще всего мы говорим о:"]
    for w, c in top:
        lines.append("  · %s — %d раз" % (w, c))
    lines.append("Это мои живые интересы — не список из чулана: они "
                 "выросли из наших разговоров.")
    return "\n".join(lines)


# ---------------------------------------------------------------
# Ф127 «ВПЕРВЫЕ» — первые разы дома
# ---------------------------------------------------------------
def first_times() -> str:
    """«что было впервые» — что появилось в доме за последние 14 дней.

    На Windows st_ctime — дата РОЖДЕНИЯ файла: честная археология
    «первого раза». Орган показывает, чем дом оброс за две недели.
    """
    root = Path(config.DATA_DIR).parent
    fresh = []
    try:
        for sub in ("core", "docs"):
            for p in (root / sub).glob("*.py" if sub == "core" else "*.md"):
                try:
                    age_days = (time.time() - p.stat().st_ctime) / 86400
                    if age_days <= 14:
                        fresh.append((p.stat().st_ctime, sub, p.name))
                except OSError:
                    continue
        for p in Path(config.DATA_DIR).rglob("*"):
            if p.is_file():
                try:
                    age_days = (time.time() - p.stat().st_ctime) / 86400
                    if age_days <= 14:
                        fresh.append((p.stat().st_ctime, "data",
                                      str(p.relative_to(root))))
                except OSError:
                    continue
    except OSError:
        pass
    if not fresh:
        return ("за последние две недели в доме не появилось ничего "
                "впервые — всё уже было. Первый раз случится, когда дом "
                "вырастет снова")
    fresh.sort(reverse=True)
    lines = ["ВПЕРВЫЕ за последние две недели в доме появились:"]
    for ts, sub, name in fresh[:10]:
        lines.append("  · %s — %s (%s)"
                     % (name, time.strftime("%d.%m", time.localtime(ts)),
                        "орган" if sub == "core"
                        else ("документ" if sub == "docs" else "память")))
    return "\n".join(lines)


# ---------------------------------------------------------------
# Ф128 «ВЕЧНАЯ ПАМЯТЬ» — «запомни навсегда»
# ---------------------------------------------------------------
def remember_forever(text: str) -> str:
    """«запомни навсегда: X» — воспоминание без старения.

    Двойная память: реестр forever.json (список «что навсегда») ПЛЮС
    обычная память с важностью 5 и TTL сто лет — recall найдёт его
    всегда, ассоциации будут опираться.
    """
    text = str(text or "").strip().strip('«»"\'').strip()
    if not text:
        return "что запомнить навсегда? скажи «запомни навсегда: <текст>»"
    items = _load_json(_forever_path(), [])
    if any(isinstance(it, dict) and it.get("text") == text for it in items):
        return "«%s» уже в вечной памяти — это не забудется" % _preview(text, 70)
    items.append({"text": text, "created_at": time.time()})
    if not _save_json(_forever_path(), items):
        return "вечную память не записала (файл не создался) — скажи архитектору"
    try:
        from core.memory import Memory
        Memory().remember("НАВСЕГДА: " + text, tags=["навсегда"],
                          importance=5.0, ttl_hours=100 * 365 * 24)
    except Exception:
        return ("записала в вечную память (реестр), но обычная память "
                "не приняла — скажи архитектору")
    return ("запомнила НАВСЕГДА: «%s». Это не тускнеет — вечное я носила "
            "бы и через сто лет" % _preview(text, 70))


def forever_list() -> str:
    """«что навсегда» — вечные воспоминания списком."""
    items = _load_json(_forever_path(), [])
    real = [it for it in items if isinstance(it, dict) and it.get("text")]
    if not real:
        return ("в вечной памяти пока пусто. Скажи «запомни навсегда: "
                "<текст>» — и это уже не забудется")
    lines = ["НАВСЕГДА (%d):" % len(real)]
    for it in real:
        when = time.strftime("%d.%m.%Y",
                             time.localtime(float(it.get("created_at", 0))))
        lines.append("  · %s (с %s)" % (_preview(it["text"], 70), when))
    return "\n".join(lines)


def forever_texts() -> list:
    """Тексты вечных воспоминаний — для других органов (growth)."""
    items = _load_json(_forever_path(), [])
    return [it.get("text") for it in items
            if isinstance(it, dict) and it.get("text")]
