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
import threading
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


def _turn_text(t: dict) -> str:
    """H9 аудита (раунд 2): ход хранится как text (DialogStore) или
    content (формат мозга) — контракт не зависит от случайного выбора
    ключа вызывающим: одна опечатка больше не опустошает историю молча."""
    v = t.get("text")
    if not (isinstance(v, str) and v.strip()):
        v = t.get("content")
    return v if isinstance(v, str) else ""


# Ф160 «ГОЛОС СОЗДАТЕЛЯ» (круг 26): метка источника в истории для мозга.
# Мост ушей пишет ходы голосом с meta.voice=True — рендер помечает их
# «[голосом]», чтобы мозг ЗНАЛ, что было сказано вслух, а что печатью
# (живой лог дня-15: «Я сказал это в микрофон?» — мозг цитировал
# печатный вопрос как произнесённый). Мозг не видит meta — видит текст.
_VOICE_MARK = "[голосом] "


def _turn_view(t: dict) -> str:
    """Текст хода глазами мозга: голосовые реплики Создателя — с
    меткой источника. Ответы Марфы не помечаются: канал ответа не
    меняет их смысла, а токены дороги."""
    text = _turn_text(t)
    if (t.get("role") == "user" and isinstance(t.get("meta"), dict)
            and t.get("meta").get("voice")):
        return _VOICE_MARK + text
    return text


def _first_sentence(text: str, max_chars: int = 100) -> str:
    """Первая законченная фраза — честная офлайн-выжимка (как Ф53).

    M6 аудита: точка в конце строки — тоже конец фразы (без требования
    пробела после знака), синхронизировано с history.py и memory._sentence."""
    text = re.sub(r"\s+", " ", (text or "").strip())
    m = re.search(r"^(.+?[.!?…])(?:\s|$)", text)
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
    """Сессии диалогов на диске. Один вызов — один файл, всё атомарно.

    M10 аудита (раунд 2): append под замком — два потока (web-хендлер +
    CLI) пишут одну сессию одновременно без тихой потери хода: раньше
    оба читали одинаковый список и последний replace затирал первого."""

    def __init__(self, data_dir: Optional[Path] = None) -> None:
        self.dir = Path(data_dir) if data_dir else config.DATA_DIR / "dialog"
        self.dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

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

    # ---------- Ф160 «ГОЛОС СОЗДАТЕЛЯ» (круг 26): одна история ----------

    def newest_other_session(self, exclude: str) -> Optional[str]:
        """Самая живая сессия, КРОМЕ exclude (по mtime файла). У Создателя
        может быть несколько окон панели — голосу важна самая свежая."""
        best: Optional[str] = None
        best_mt = -1.0
        try:
            for p in self.dir.glob("session_*.json"):
                sid = p.stem[len("session_"):]
                if sid == exclude:
                    continue
                mt = p.stat().st_mtime
                if mt > best_mt:
                    best_mt, best = mt, sid
        except OSError:
            return None
        return best

    def unified_turns(self, session_id: str,
                      merge_limit: int = 12) -> list[dict]:
        """Ходы сессии + ходы ГОЛОСОМ (или наоборот) — один разговор.

        Живой лог дня-15 вскрыл раскол мозга: ходы панели жили в своей
        сессии, ходы моста ушей — в voice; каждый мозговой ход видел
        ПОЛОВИНУ разговора. Эхо-сверка не видела соседнюю сессию, вопросы
        «что я говорил в микрофон» уходили мозгу, которому нечего цитировать.
        Теперь: панельная сессия получает хвост голосовой (и наоборот),
        хронология — по штампам ходов, метки «[голосом]» ставит рендер.
        Потолок merge_limit: голосовой хвост — приправа, не меню (бюджет
        истории 1000 токенов — Ф53).
        """
        mine = self.turns(session_id)
        try:
            if session_id == config.VOICE_SESSION:
                other = self.newest_other_session(exclude=config.VOICE_SESSION)
            else:
                other = config.VOICE_SESSION
        except Exception:
            other = None
        extra = self.turns(other)[-merge_limit:] if other else []
        if not extra:
            return mine

        def _ts(t: dict) -> float:
            # год — от сегодняшнего (декабрьский след в январе переносится);
            # битый штамп — 0.0: без штампа ход честно считается старым
            try:
                ts = dt.datetime.strptime(str(t.get("ts", "")), "%d.%m %H:%M")
            except ValueError:
                return 0.0
            now = dt.datetime.now()
            ts = ts.replace(year=now.year)
            if ts > now + dt.timedelta(days=1):
                ts = ts.replace(year=now.year - 1)
            return ts.timestamp()

        merged = sorted(mine + extra, key=_ts)
        return merged

    def append(self, session_id: str, role: str, text: str,
               meta: Optional[dict] = None) -> dict:
        """Дописать ход. Роль — только user/assistant (не выдумываем системных).

        meta — штамп хода (эфир, 22.11): сколько думала (secs) и кто
        отвечал (src). В файл ложатся только простые значения — никакой
        вложенной мути от будущих callers; старые файлы без meta читаются
        как раньше (F5 не сотрёт время и не сломает историю).
        """
        if role not in ("user", "assistant"):
            raise ValueError("роль хода: user или assistant")
        text = (text or "").strip()
        if not text:
            raise ValueError("пустой ход не записывается")
        path = self._path(session_id)
        with self._lock:                      # M10: чтение+запись — одна транзакция
            turns = self.turns(session_id)
            turn = {"role": role, "text": text[:8000],
                    "ts": dt.datetime.now().strftime("%d.%m %H:%M")}
            if meta:
                clean = {}
                for k, v in meta.items():
                    if isinstance(v, (int, float, str, bool)) and len(clean) < 8:
                        clean[str(k)[:32]] = v
                if clean:
                    turn["meta"] = clean
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

    def last_user_activity(self) -> Optional[dt.datetime]:
        """Когда Создатель говорил с домом ПОСЛЕДНИЙ РАЗ (любая сессия).

        Ф3/Ф4 (23.11): приветствие и дайджест «что нового» должны знать,
        сколько мы не виделись — из первых рук (файлы диалога), а не из
        выдумки мозга. Штамп хода «dd.mm HH:MM» без года: год выводим
        сами (декабрь→январь честно переносится), битые штампы — мимо.
        Нет ходов — None: «мы ещё не разговаривали», не «минуту назад».
        """
        best: Optional[dt.datetime] = None
        try:
            files = list(self.dir.glob("session_*.json"))
        except OSError:
            return None
        now = dt.datetime.now()
        for p in files:
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                turns = data.get("turns", []) if isinstance(data, dict) else []
            except (OSError, ValueError):
                continue
            for t in turns:
                if not (isinstance(t, dict) and t.get("role") == "user"):
                    continue
                try:
                    ts = dt.datetime.strptime(str(t.get("ts", "")),
                                              "%d.%m %H:%M")
                except ValueError:
                    continue
                ts = ts.replace(year=now.year)
                if ts > now + dt.timedelta(days=1):
                    ts = ts.replace(year=now.year - 1)   # декабрьский след в январе
                if best is None or ts > best:
                    best = ts
        return best

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
    def _turn_day(t: dict) -> Optional[dt.date]:
        """День хода по штампу «dd.mm HH:MM» (год — от сегодняшнего,
        декабрьский след в январе переносится). Битый штамп — None:
        такой ход честно считается «свежим» (консервативно — лучше
        лишняя строка дословно, чем потерянный день)."""
        try:
            ts = dt.datetime.strptime(str(t.get("ts", "")), "%d.%m %H:%M")
        except ValueError:
            return None
        now = dt.datetime.now()
        ts = ts.replace(year=now.year)
        if ts > now + dt.timedelta(days=1):
            ts = ts.replace(year=now.year - 1)
        return ts.date()

    @staticmethod
    def render_messages(turns: list[dict],
                        budget: int = config.HISTORY_BUDGET_TOKENS) -> list[dict]:
        """История ходов -> сообщения для мозга, не длиннее бюджета токенов.

        Гарантии Ф53: новейший ход всегда дословно; старое за пределами
        бюджета — одной выжимкой в начале (без LLM, гейт §5 уважен).
        H9: ходы принимаются и в формате DialogStore (text), и в формате
        мозга (content) — контракт устойчив к выбору вызывающего.

        Ф79 «СВЕЖЕЕ УТРО» (день-11, живой лог Создателя: «чат накопился
        за несколько дней и токены убивают Марфу»): сессия, живущая
        днями, тащила хвост вчерашних разговоров в дословном хвосте —
        каждый день переговаривать заново то, что уже прожито. Теперь
        граница — день ПОСЛЕДНЕГО хода: сегодня едет дословно (в
        бюджете), прошлые дни сворачиваются в выжимку «Ранее, прошлые
        дни». Память не теряется: полный архив остаётся в файле
        сессии, экспорте (Ф55) и памяти дома — диета касается только
        контекста хода.
        """
        clean = [t for t in turns if t.get("role") in ("user", "assistant")
                 and _turn_text(t).strip()]
        if not clean:
            return []

        # Ф79: свежесть = день последнего хода сессии (не календарное
        # «сегодня» — рендер старой сессии честно показывает её вечер)
        last_day = DialogStore._turn_day(clean[-1])
        fresh_from = len(clean)
        for i in range(len(clean) - 1, -1, -1):
            day = DialogStore._turn_day(clean[i])
            if day is not None and last_day is not None and day != last_day:
                break
            fresh_from = i

        # 1) дословный хвост: со свежего, пока влезает (треть — запас под выжимку)
        fresh = clean[fresh_from:]
        tail: list[dict] = []
        used = 0
        reserve = budget // 3
        for t in reversed(fresh):
            need = config.token_estimate(_turn_view(t)) + 2
            if tail and used + need > budget - reserve:
                break
            if not tail and need > budget:
                # крайний случай: даже новейший ход длиннее всего бюджета —
                # честная выжимка фразы, не пустота и не обрубок посередине слова
                return [{"role": t["role"],
                         "content": _cap_words(_first_sentence(_turn_view(t)), budget)}]
            tail.insert(0, {"role": t["role"], "content": _turn_view(t)})
            used += need

        # 2) прошлые дни + то из сегодня, что не влезло, — выжимкой.
        #    День-граница (Ф79) сворачивает ПРОШЛЫЕ дни всегда; переполнение
        #    свежего дня сворачивается как раньше (Ф53) — штампа нет или
        #    день один, выжимка честно зовётся «ранее в разговоре»
        older = clean[:fresh_from] + fresh[:len(fresh) - len(tail)]
        had_past_days = fresh_from > 0
        out: list[dict] = []
        if older:
            lines = []
            for t in older[-12:]:                   # глубже 12 ходов не тянем
                line = "- %s: %s" % (t["role"], _first_sentence(_turn_view(t)))
                if config.token_estimate("\n".join(lines + [line])) > reserve:
                    break
                lines.append(line)
            if lines:
                header = ("(Ранее, прошлые дни — кратко:)\n" if had_past_days
                          else "(Ранее в разговоре, кратко:)\n")
                out.append({"role": "user", "content": header + "\n".join(lines)})
        return out + tail
