# -*- coding: utf-8 -*-
"""core/brain.py — МОЗГ ДОМА (ТЗ 3.2, ADR-002): клиент 8082, строгий JSON, фоллбэк.

Восстановлен 2026-11-18 по контракту tests/test_brain.py (канон v9.3):
- chat(): обычный трек, генерация не выше бюджета 768 (0.3);
- ask_json(): строгий JSON, при браке — повтор с укором, regex-спасение ЗАПРЕЩЕНО;
- фоллбэк №37: провайдер с available()/ask() подставляется снаружи (GigaChat);
- usage_tokens(): честный расход из сырого ответа сервера.

СКОРОСТЬ v1 (22.11, доклад Создателя «ответ через две минуты — это очень
долго»): у чат-ответа — СВОЙ бюджет первого захода (BRAIN_ANSWER_TOKENS,
320): краткий ответ на CPU стоит ~40 с, а не две минуты. Обрезанный
JSON — не приговор: повтор уходит с полным бюджетом (обрезка — одна
из причин брака, лечится местом, а не укором). Стрим: ask_json(on_text)
печатает ответ в эфир ЖИВЬЁМ — чат видит рождение текста по мере
генерации, а не после последнего токена.
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.request
from pathlib import Path
from typing import Callable, Optional

from core import config, loghygiene


class BrainError(Exception):
    """Мозг не ответил или ответил не-JSON. Наверх уходит как честная ошибка."""


def _log_brain_call(kind: str, raw_full: str, stripped: str,
                    usage, secs: float, ok: bool,
                    decision=None) -> None:
    """ЖУРНАЛ МОЗГОВОГО ТРАФИКА (23.11, ночь): logs/brain_log.jsonl,
    одна строка на КАЖДУЮ генерацию — токены, секунды, ДУМАНИЕ (сколько
    символов срезано think-блоками), ответ ЦЕЛИКОМ, действие.

    Урок живого лога: Создатель спросил «что она сгенерировала на
    179 токенов — там может быть нормальный ответ, который не дошёл?» —
    а дому нечем было ответить: brain-лога не существовало, обещание
    «хвост brain» из анти-эхо указывало в пустоту. Теперь вопрос
    проверяем: «хвост brain ui_action» покажет, что было в answer,
    а think_chars отличит невидимое думание от пропавшего ответа.

    Ф81 «ЧЕСТНАЯ ПУСТОТА» (день-12, живой лог Создателя: «мозг
    вернулся с пустым ответом дважды — 21 ток и пусто»): журнал
    записывает СЫРУЮ УЛИКУ — что именно прислал мозг, когда ответ
    пуст или это не-json. Прежде слово «пустой ответ» говорило,
    ЧТО случилось, но не КАК: null? пустая строка? русский ключ
    «ответ»? без улики лечение — телепатия. Теперь note несёт
    повод, raw — вещдок: «хвост brain пустой ответ» показывает
    правду целиком.

    Файл не записался — разговор живёт дальше: журнал — правда для
    архива, не орган дыхания. note — человеческая метка повода
    («пустой ответ», «не-json»), чтобы фильтр хвоста находил строку
    словами, а не по пунктуации."""
    try:
        ptok = ctok = 0
        if isinstance(usage, dict):
            try:
                ctok = int(usage.get("completion_tokens") or 0)
            except (TypeError, ValueError):
                ctok = 0
            try:
                ptok = int(usage.get("prompt_tokens") or 0)
            except (TypeError, ValueError):
                ptok = 0
        answer = None
        action = None
        if isinstance(decision, dict):
            a = decision.get("answer")
            answer = (a if isinstance(a, str) else str(a))[:4000] if a is not None else None
            act = decision.get("action")
            if isinstance(act, dict):
                action = json.dumps(act, ensure_ascii=False)[:1000]
        note = ""
        if ok and isinstance(decision, dict) and not (decision.get("answer") or "").strip() \
                and not isinstance(decision.get("action"), dict):
            note = "пустой ответ"
        if not ok:
            note = "не-json"
        rec = {
            "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
            "kind": kind,
            "secs": round(float(secs), 1),
            "prompt_tokens": ptok,
            "completion_tokens": ctok,
            "think_chars": max(0, len(raw_full or "") - len(stripped or "")),
            "ok": bool(ok),
            "note": note,
            "answer": answer,
            "action": action,
        }
        # Ф81: улика — только по поводу (пусто/не-json): честный ответ
        # и так лежит в answer целиком, дублировать его сырой копией —
        # платить журнал вдвое за каждое слово разговора
        if note:
            rec["raw"] = (stripped or "")[:600]
        p = Path(config.BRAIN_LOG_FILE)
        # Ф96 (круг 17): журнал — копилка, пишет через ЕДИНУЮ дверь
        # ротации (loghygiene.append_line): живёт месяцами — диск не
        # бесконечен; закон 8 МБ × 3 архива, страж-хеш-цепь exempt
        loghygiene.append_line(p, json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        pass   # журнал — не орган дыхания; разговор живёт дальше


def _extract_content(data) -> str:
    """H6 аудита: сервер вернул 200 с телом без choices ("error", пустой
    список) — это BrainError с честным диагнозом, а не KeyError.
    «Мозг недоступен» и «мозг ответил криво» — разные болезни, разное
    лечение: вторая лечится ретраем, первая — доктором."""
    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as e:
        raise BrainError("мозг вернул ответ без choices (%s): %s"
                         % (type(e).__name__, str(data)[:200]))


# ---------------------------------------------------------------
# №9 «Темперамент из доктрины»: настроение Марфы читается из
# data/creator_doctrine.json (поле mood), а не зашито в код.
# Создатель может сделать её живее (temperature выше) или строже
# (ниже) правкой одного файла — без правки кода дома.
# Нет файла / нет поля / брак — характер по умолчанию: 0.3.
# ---------------------------------------------------------------
DEFAULT_TEMPERATURE = 0.7
# Фикс сэмплинга Qwen3 БЕЗ мышления (мастер-ТЗ §15, таблица
# разработчиков): temp 0.7, top_p 0.8. Старый дом жил на 0.3 — это
# температура С мышлением; без него ответы сохнут и повторяются
# («Как я могу вам помочь?» из живого лога 23.11 — симптом этого).
# Характер из доктрины Создателя перекрывает дефолт — воля важнее.
DEFAULT_TOP_P = 0.8

# Qwen3 умеет «думать вслух» блоками <think>…</think> ДО ответа.
# Грамматика json_object обычно не пускает их в генерацию, но не все
# сборки сервера держат грамматику: пустой think-блок перед JSON —
# самый дешёвый способ угробить парс и заплатить минутой ретрая.
# Стриппер — страховка, не режим.
_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)


def _strip_think(raw: str) -> str:
    """Убрать think-блоки Qwen3 — JSON остаётся чистым."""
    return _THINK_RE.sub("", raw or "").strip()


def is_refusal(err_text: str) -> bool:
    """Соединение ОТКЛОНЕНО — сервер мозга не слушает порт.

    WinError 10061 на машине Создателя (живой лог 23.11, день-8:
    «мозг недоступен» после §15-рестарта), errno 111 «Connection
    refused» в песочнице — одна болезнь: сервер выключен, грузится
    или его команду старта отвергла сборка. Таймаут («timed out») —
    ДРУГАЯ болезнь: медленное честное думание, ему дозвон противопоказан.
    """
    t = (err_text or "").lower()
    return ("10061" in t or "connection refused" in t
            or "connectionrefusederror" in t
            or "actively refused" in t)


def _urlopen(req, timeout: float):
    """urlopen с честным дозвоном: отказ соединения — не приговор.

    Мозг на CPU поднимается десятками секунд — панель, спросившая
    раньше, чем порт ожил, не имеет права ронять ход первым же
    «нет ответа»: дозваниваемся снова с паузой (закон дома
    BRAIN_CONNECT_RETRIES × BRAIN_CONNECT_BACKOFF_SEC). Эфиру
    говорится честно, ЧТО происходит (stage вне хода — тихий no-op:
    голосовой трек и тесты не шумят). Всё, что НЕ отказ соединения
    (таймаут, HTTP-ошибка, кривой ответ), — без дозвона: у каждой
    болезни своё лечение (урок H6: «недоступен» и «кривой» — разные).
    """
    attempts = max(1, int(config.BRAIN_CONNECT_RETRIES))
    backoff = max(0.0, float(config.BRAIN_CONNECT_BACKOFF_SEC))
    # Батарея не спит 45 с ради симуляции погрузки (дом-паттерн «тест в
    # тесте» PYTEST_CURRENT_TEST — прецедент weekly_audit): ретраи в
    # тестах честные, паузы — нулевые
    if os.environ.get("PYTEST_CURRENT_TEST"):
        backoff = 0.0
    for i in range(attempts):
        try:
            return urllib.request.urlopen(req, timeout=timeout)
        except Exception as e:
            if i >= attempts - 1 or not is_refusal(str(e)):
                raise
            try:
                from core import progress
                progress.stage(
                    "мозг не отвечает на порту (грузится?) — дозваниваюсь,"
                    " попытка %d из %d…" % (i + 2, attempts))
            except Exception:
                pass          # эфир молчит — дозвон живёт
            if backoff:
                time.sleep(backoff)
    raise BrainError("мозг не дозвонился за %d попыток" % attempts)


# МЯГКИЙ ПЕРЕКЛЮЧАТЕЛЬ QWEN3 (двойное мышление, 23.11): «/no_think» в
# системном промпте — модель сама закрывает thinking-блок пустым и
# печатает только ответ. Работает на ЛЮБОЙ сборке сервера (в отличие
# от chat_template_kwargs, которому нужен --jinja): мягкий переключатель
# зашит в саму модель. Докупка статичная — KV-кэш цел.
_NO_THINK = " /no_think"


def _kill_thinking(payload: dict) -> None:
    """Выключить thinking Qwen3 — закон дома (BRAIN_THINKING=False).

    Урок живой переписки 23.11: «Привет! Марфа» стоил 273 токена —
    из них ~10 видимых. Остальное — невидимые thinking-блоки при
    2-6 ток/с на CPU: 80% времени хода Создатель ждал МЫСЛИ, которые
    никогда не показывались и в чат не попадали. Двойная страховка:
    (1) chat_template_kwargs — на серверах с --jinja выключает
    thinking в шаблоне; старые сборки поле молча игнорируют;
    (2) «/no_think» в системном промпте — мягкий переключатель
    самой модели, работает везде (докупка статичная — KV-кэш цел).

    Живёт НА УРОВНЕ МОДУЛЯ, а не методом класса: стрим, чат и
    ask_json зовут её одинаково (урок первой ревизии: метод класса
    из _post_stream звался голым именем — NameError на каждом
    стрим-ходе, то есть на КАЖДОМ ответе чата).
    """
    if config.BRAIN_THINKING:
        return                          # мышление включено волей дома
    payload["chat_template_kwargs"] = {"enable_thinking": False}
    sys_msgs = payload.get("messages") or []
    if sys_msgs and isinstance(sys_msgs[0], dict) \
            and sys_msgs[0].get("role") == "system":
        content = sys_msgs[0].get("content")
        if isinstance(content, str) and not content.rstrip().endswith("/no_think"):
            sys_msgs[0]["content"] = content.rstrip() + _NO_THINK


def mood_params() -> dict:
    """Темперамент из доктрины Создателя. Валидно — берём, брак — молча дефолт.

    Формат в creator_doctrine.json:
        {"doctrine": "...", "mood": {"temperature": 0.6, "top_p": 0.8}}
    Границы здравого смысла: temperature 0.05..2.0, top_p 0.05..1.0 —
    всё, что вне, считаем опечаткой и игнорируем ЦЕЛИКОМ (полумеры
    из битого файла опаснее дефолта).
    """
    try:
        raw = Path(config.DOCTRINE_FILE).read_text(encoding="utf-8")
        mood = (json.loads(raw) or {}).get("mood")
        if not isinstance(mood, dict):
            return {}
        t = float(mood.get("temperature", DEFAULT_TEMPERATURE))
        if not (0.05 <= t <= 2.0):
            return {}
        out = {"temperature": t}
        if "top_p" in mood:
            p = float(mood["top_p"])
            if 0.05 <= p <= 1.0:
                out["top_p"] = p
        return out
    except Exception:   # нет файла, битый JSON, не те типы — дефолт
        return {}


class BrainClient:
    def __init__(self, brain_url: str = "") -> None:
        # brain_url: переопределение для тестов (фальшивый сервер);
        # пустая строка -> адрес из закона дома (core/config.py).
        self.url = brain_url or config.BRAIN_URL
        self.fallback = None  # провайдер фоллбэка (№37): available() + ask(prompt)
        # последний честный расход (usage ответа) — для штампа «N ток»
        self.last_usage: dict = {}
        # Ф81 (день-12): сырой ответ последней генерации ПОСЛЕ think-стриппера —
        # улика для агента. Пустой ответ — это класс болезней (null, "",
        # чужой ключ «ответ»), и укол обязан знать, КАКАЯ случилась,
        # а не бить наугад общим «ответь по существу» (живой лог 24.11:
        # дважды пусто на «почему или проверка?» — 21 ток сгорел зря)
        self.last_raw: str = ""

    # ---------- транспорт ----------

    def _post(self, path: str, payload: dict) -> dict:
        """POST JSON к llama-server. Любая поломка -> BrainError.

        Таймаут — из закона дома (BRAIN_TIMEOUT_SEC, 300 с): Pascal-мозг
        честно думает минутами, обрывать его на 120-й секунде — ложь
        (урок переписки 22.11: «изучи себя» обрывалось ровно так).
        """
        req = urllib.request.Request(
            self.url + path,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with _urlopen(req, timeout=config.BRAIN_TIMEOUT_SEC) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except BrainError:
            raise
        except Exception as e:
            raise BrainError(str(e))

    # ---------- доступность ----------

    def health(self) -> bool:
        try:
            with urllib.request.urlopen(self.url + "/health", timeout=5) as r:
                return r.status == 200
        except Exception:
            return False

    # ---------- стрим (СКОРОСТЬ v1): ответ печатается живьём ----------

    def _post_stream(self, path: str, payload: dict,
                     on_text: Callable[[str], None]) -> dict:
        """POST со стримом SSE: дельты текста летят в on_text ПО МЕРЕ
        генерации — чат показывает рождение ответа, не тишину.

        Возвращает тот же словарь, что _post (content собран из дельт).
        Сервер проигнорировал "stream" и ответил обычным JSON — читаем
        целиком и зовём on_text один раз: превью всё равно состоится,
        пусть и разом (фоллбэк-честность, фейк-сервер тестов живёт так).
        Поломка on_text НЕ рвёт запрос: превью — косметика, мышление —
        работа (закон эфира).
        """
        body = dict(payload)
        body["stream"] = True
        body["stream_options"] = {"include_usage": True}
        _kill_thinking(body)
        req = urllib.request.Request(
            self.url + path,
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with _urlopen(req, timeout=config.BRAIN_TIMEOUT_SEC) as resp:
                chunks: list = []
                usage: dict = {}
                sse = False
                raw_lines: list = []
                for line in resp:
                    raw_lines.append(line)
                    text_line = line.decode("utf-8", errors="replace").strip()
                    if not text_line.startswith("data:"):
                        continue
                    sse = True
                    data_str = text_line[5:].strip()
                    if data_str == "[DONE]":
                        continue
                    try:
                        obj = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(obj.get("usage"), dict) and obj["usage"]:
                        usage = obj["usage"]
                    try:
                        delta = obj["choices"][0].get("delta") or {}
                    except (IndexError, KeyError, TypeError, AttributeError):
                        continue
                    piece = delta.get("content") or ""
                    if piece:
                        chunks.append(piece)
                        try:
                            on_text("".join(chunks))
                        except Exception:
                            pass      # превью сломалось — ответ живёт
                if not sse:
                    data = json.loads(
                        b"".join(raw_lines).decode("utf-8", errors="replace"))
                    content = _extract_content(data)
                    try:
                        on_text(content)
                    except Exception:
                        pass
                    return data
                return {"choices": [{"message": {
                            "role": "assistant",
                            "content": "".join(chunks)}}],
                        "usage": usage}
        except BrainError:
            raise
        except Exception as e:
            raise BrainError(str(e))

    # ---------- обычный чат ----------

    def chat(self, messages: list, gen_tokens: Optional[int] = None,
             temperature: Optional[float] = None,
             top_p: Optional[float] = None) -> str:
        """Чат без JSON-дисциплины. max_tokens не выше бюджета генерации (0.3).

        Температура: явный аргумент > настроение из доктрины (№9) > 0.3.
        top_p (фикс сэмплинга Qwen3, живой язык): явный аргумент >
        настроение из доктрины > параметр не шлётся вовсе.
        """
        cap = config.GENERATION_BUDGET_TOKENS
        # M1 аудита: gen_tokens=0/-1 не превращается в max_tokens=0
        # (сервер вернул бы пустоту или ошибку) — нижняя граница 1
        mt = cap if gen_tokens is None else max(1, min(int(gen_tokens), cap))
        mood = mood_params()
        temp = (float(temperature) if temperature is not None
                else mood.get("temperature", DEFAULT_TEMPERATURE))
        payload = {"messages": messages, "temperature": temp, "max_tokens": mt}
        top_p_val = (float(top_p) if top_p is not None
                     else mood.get("top_p", DEFAULT_TOP_P))
        if top_p_val is not None:
            payload["top_p"] = top_p_val
        _kill_thinking(payload)
        t0 = time.time()
        data = self._post("/v1/chat/completions", payload)
        raw_full = _extract_content(data)
        stripped = _strip_think(raw_full)
        self.last_raw = stripped          # Ф81: улика последней генерации
        usage = data.get("usage")
        if isinstance(usage, dict):
            self.last_usage = {
                "prompt_tokens": int(usage.get("prompt_tokens") or 0),
                "completion_tokens": int(usage.get("completion_tokens") or 0),
            }
        _log_brain_call("chat", raw_full, stripped, usage,
                        time.time() - t0, True, None)
        return stripped

    # ---------- строгий JSON (ADR-002) ----------

    def ask_json(self, user_text: str, system_extra: str = "", retries: int = 2,
                 history: Optional[list] = None,
                 max_tokens: Optional[int] = None,
                 on_text: Optional[Callable[[str], None]] = None,
                 turn_context: str = "") -> dict:
        """Спросить мозг и получить dict. Брак -> повтор с укором -> фоллбэк/ошибка.

        ADR-002: JSON, завёрнутый в посторонний текст, НЕ спасается регулярками —
        только честный повтор. Выдумывать ответ вместо мозга запрещено.
        №10: history — прошлые ходы [{role, content}], вставляются ПОСЛЕ
        системного промпта и ДО нового сообщения: префиксный KV-кэш цел,
        разговор не рвётся.

        Ф77 «СТАБИЛЬНЫЙ ПРЕФИКС» (день-11, живой лог: промпт 7419 ток,
        ответы 90-200 с): system_extra — только СТАТИКА (ядро+манифест+
        законы+доктрина); состояние дома и RAG ездят в turn_context —
        служебным блоком ВНУТРИ сообщения Создателя. Системный префикс
        не меняется от хода к ходу (часы состояния раньше рвали его
        КАЖДЫЙ ход — мозг пересчитывал все ~7400 ток заново),
        llama-server переиспользует KV-кэш: префилл хода падает до
        хвоста. Ф80 «закон инструмента» — в преамбуле: разговор о
        мыслях и правилах — текстом, инструмент — по явной просьбе.

        СКОРОСТЬ v1: max_tokens — бюджет ПЕРВОГО захода (чат Марфы живёт
        на BRAIN_ANSWER_TOKENS: краткость — часть закона дома); повторы
        уходят с полным бюджетом — обрезанный JSON лечится местом.
        on_text — стрим-превью: текст летит в эфир по мере генерации.
        """
        messages = [
            {"role": "system", "content": (
                # «Ассистент» — слово-паразит живого лога 23.11: на нём
                # 30B скатывался в «Я не имею личных мыслей или эмоций»,
                # прямое противоречие органам чувств/сна/мыслей дома.
                # Марфа — организм, и преамбула говорит именно так.
                # Ф80 (день-11): «баланс: ОК» и «почини что?» на
                # философские вопросы — мозг хватался за инструменты
                # без аргументов и сжигал ход; закон в преамбуле.
                "Ты — Марфа, домашний ИИ-организм в доме Создателя. "
                "Ты должна отвечать пользователю строго в формате JSON: "
                "{\"answer\": \"твой текст\"} или "
                "{\"action\": {\"tool\": \"...\", \"args\": {...}}}. "
                "Не пиши ничего вне JSON. "
                # Ф82 (день-12, живой лог: «почему или проверка?» — 21 ток
                # и дважды пустой answer): закон ключа — в преамбуле, до
                # того как мозг решил назвать поле по-русски или оставить
                # пустым. Каждое слово здесь статично и оплачено KV-кэшем
                # один раз за сессию — диета не страдает
                "Ключ ответа — только \"answer\", латиницей; значение — "
                "непустой текст (пустая строка и null — не ответ). "
                "Если пользователь просто здоровается, "
                "поздоровайся в ответ внутри JSON. "
                "Разговор о мыслях, правилах и вопросах — отвечай ТЕКСТОМ "
                "({\"answer\"}); инструмент — только когда Создатель ЯВНО "
                "просит сделать действие, и только с настоящими "
                "аргументами.\n" + system_extra)},
        ]
        for t in (history or []):   # только user/assistant, мусор — мимо
            if not (isinstance(t, dict) and t.get("role") in ("user", "assistant")):
                continue
            content = t.get("content")
            if not (isinstance(content, str) and content.strip()):
                # H9 (раунд 2): DialogStore.turns отдаёт text — это тоже
                # валидная история, а не «мусор мимо»
                content = t.get("text")
            if isinstance(content, str) and content.strip():
                messages.append({"role": t["role"], "content": content})
        # Ф77: подвижный контекст хода (состояние+RAG) — служебным
        # блоком перед словами Создателя: до статичного префикса ему
        # нет дела, а чтение — живое, каждым ходом
        user_msg = user_text
        ctx = (turn_context or "").strip()
        if ctx:
            user_msg = (ctx + "\n— конец служебного контекста —\n\n"
                        + user_text)
        messages.append({"role": "user", "content": user_msg})
        attempts = max(1, retries)
        mood = mood_params()   # №9: характер — из доктрины Создателя
        first_cap = (config.GENERATION_BUDGET_TOKENS if max_tokens is None
                     else min(int(max_tokens), config.GENERATION_BUDGET_TOKENS))
        for i in range(attempts):
            payload = {
                "messages": messages,
                "temperature": mood.get("temperature", DEFAULT_TEMPERATURE),
                "max_tokens": (first_cap if i == 0
                               else config.GENERATION_BUDGET_TOKENS),
                "response_format": {"type": "json_object"},
            }
            # фикс сэмплинга Qwen3 без мышления (§15): top_p 0.8 —
            # характер доктрины может перекрыть своим
            payload["top_p"] = mood.get("top_p", DEFAULT_TOP_P)
            _kill_thinking(payload)
            t0 = time.time()
            if on_text is not None:
                data = self._post_stream("/v1/chat/completions", payload, on_text)
            else:
                data = self._post("/v1/chat/completions", payload)
            raw_full = _extract_content(data)
            raw = _strip_think(raw_full)
            self.last_raw = raw            # Ф81: улика — до разбора и ретрая
            usage = data.get("usage")
            if isinstance(usage, dict):
                self.last_usage = {
                    "prompt_tokens": int(usage.get("prompt_tokens") or 0),
                    "completion_tokens": int(usage.get("completion_tokens") or 0),
                }
            try:
                out = json.loads(raw)
                if isinstance(out, dict):
                    _log_brain_call("ask_json", raw_full, raw, usage,
                                    time.time() - t0, True, out)
                    return out
            except (json.JSONDecodeError, TypeError):
                pass
            # брак: укор и повтор тем же разговором; журнал уже записал
            # попытку с меткой «не-json» — «хвост brain не-json» покажет
            _log_brain_call("ask_json", raw_full, raw, usage,
                            time.time() - t0, False, None)
            messages = messages + [
                {"role": "assistant", "content": raw},
                {"role": "user", "content": (
                    "Твой прошлый ответ не был валидным JSON. "
                    "Ответь ещё раз строго валидным JSON, без текста вокруг.")},
            ]
        # все попытки дали брак: фоллбэк №37, если он есть и жив
        fb = getattr(self, "fallback", None)
        if fb is not None and fb.available():
            return {"answer": fb.ask(user_text), "source": "fallback"}
        raise BrainError("мозг не дал валидный JSON за " + str(attempts) + " попыток")

    # ---------- usage ----------

    @staticmethod
    def usage_tokens(raw: dict) -> int:
        """Честный расход токенов из сырого ответа llama-server."""
        usage = (raw or {}).get("usage") or {}
        try:
            return int(usage.get("completion_tokens", 0))
        except (TypeError, ValueError):
            return 0
