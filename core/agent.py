# -*- coding: utf-8 -*-
"""core/agent.py — ДИСПЕТЧЕР ДОМА (ТЗ 3.1): быстрые команды → Python, остальное → 30B.

Восстановлен 2026-11-18 по контракту tests/test_agent.py (канон v9.3):
быстрые команды (время/статус/скобки/вычисли/помни/вспомни) не будят мозг,
мозговой трек получает доктрину + состояние дома + RAG-воспоминания,
действия мозга идут через РУКИ под надзором СТРАЖА.

2026-11-18, калитка Создателя: сообщение с кодовым словом из .env
перехватывается ДО мозга и быстрых команд (core/creator_gate.py):
мозг не может выболтать слово, которого никогда не видел.

2026-11-20, Г-2 глаза в агенте: «посмотри»/«что на экране»/«опиши экран» —
дескриптор экрана от сенсора 8083 (core/eyes.py), мозг молчит;
глаза только читают — курсор и клики остаются у РУК под надзором стража.

2026-11-20, Г-2.1 мозг ЗНАЕТ о глазах: состояние дома в промпте мозгового
трека включает сенсор 8083 и команду «посмотри» (eyes.health_cached —
кэш 30 с, чтобы пинг по мёртвому порту не тормозил каждый ответ).
Создатель спросит «ты что-нибудь видишь?» — Марфа ответит по-честному.

2026-11-20, самосознание (Г-2.2): ЯДРО ЛИЧНОСТИ — IDENTITY — первым
блоком системного промпта, до доктрины из data/. Кто она, чей дом,
какое у неё тело, язык дома и честность («не знаю — так и скажу»).
Правило №51: ЯДРО не режется никогда — поэтому оно в коде, а не в data/:
едет git'ом, переживает любую потерю рантайма.

2026-11-22, самопознание v2 (Г-2.3): переписка Создателя с Марфой
вскрыла слепоту — «изучи себя» → «неизвестный инструмент: filesystem»
(трижды), «что ты умеешь» — общие слова. Лечение: манифест
возможностей (core/identity.py) в системном промпте — мозг видит
ТОЧНЫЕ имена инструментов и команд; быстрая команда «изучи себя» —
честный динамический отчёт без LLM; ЯДРО дополнено правдой об ушах.

2026-11-22, вечер (уроки живого дома №2): «что ты видишь» — тоже
команда глазам (Создатель спрашивает именно так); камера — второй
источник зрения («посмотри в камеру» / «посмотри на меня» — веб-камера
с OpenCV); уши называют ПРИЧИНУ молчания (identity.ears_diagnosis);
руки — моторная кора по вызову (core/motor.py, ТЗ_Руки_v1): команда
«руки <задача>» и инструмент ui_action, моторика — только по резолюции
Создателя (кнопка 91), каждое действие — через СТРАЖА.
2026-11-22, вечер-4 (эфир дома): ответы долгие — но чат больше не
молчит. Ход начинается эфиром (core/progress.py): чат показывает
живую стадию («собираю контекст…», «мозг думает…») и тикающие
секунды, ответ приходит со штампом «12,4 с · мозг». Консоль
для этого открывать не нужно.

2026-11-22, вечер-6 (СКОРОСТЬ v1, доклад Создателя: «она даёт ответ
через две минуты, это очень долго»): краткость стала законом дома —
у чат-ответа свой бюджет первого захода (BRAIN_ANSWER_TOKENS),
мозг просится кратко (ЗАКОН СКОРОСТИ в промпте), ответ ПЕЧАТАЕТСЯ
в чат живьём (стрим → progress.preview), а штамп несёт и токены
(«40,2 с · мозг · 84 ток»): если снова медленно — по штампу видно,
кто съел время: декод (токенов много) или промпт/ретрай (мало).

2026-11-22, ночь (АУДИТ РАУНДА 3, Создатель разбрал этот файл построчно):
18 багов, из них 3 критических. Математика получила закон против DoS
(9**9**9**9 больше не вешает воркер), «помнишь, как мы гуляли?» —
вопрос мозгу, а не приказ памяти, хвостовая пунктуация («статус?»,
«время!», «посмотри.») не роняет команду в медленный трек, упавший
сенсор не выдаёт себя за «мозг недоступен», а args не-словарём от
мозга — брак формата, а не 500-я панель. №1 аудита (escape C:\\Marfa)
проверен якорем-компиляцией: в коде давно двойной слэш, модуль
чист даже под -W error::SyntaxWarning.

Ф75 «СВОБОДА ВНЕДРЯТЬ СЕБЯ» (директива Создателя, 22.11): «дай Марфе
свободу, чтоб она могла уже сама писать и внедрять себя — она умная
модель, у неё прокачанные руки, она понимает, что делает». Кодер
пишет патч (как раньше), но внедрить его Марфа теперь может САМА:
«внедри патч N» — с резолюцией Создателя («разреши внедрять себя»,
одна фраза, как моторика и живой язык), с бэкапом, дым-тестом модуля
и автоОткатом при красном. Свобода — не вседозволенность: без
резолюции — честный отказ, при красном тесте — старый файл
возвращается на место (core/repair.self_apply).
"""
from __future__ import annotations

import ast
import datetime as dt
import json
import math
import operator as _op
import re
import time
from pathlib import Path
from typing import Optional

from core import config, context, creator_gate, diary, eyes, feelings, hands, identity, progress
from core import musing, sleep                    # внутренняя жизнь организма (23.11)
from core import rules                             # законы дома: автор и исполнитель (№40)
from core import notes, shopping, worklog, expenses, habits  # круг 1: быт (Ф11-Ф15)
from core import birthdays, when                     # круг 2: календарь (Ф16-Ф19)
from core import password, numeral, units            # круг 3: слова (Ф22-Ф25)
from core.chance import rand_between, coin_times     # круг 3: жребий шире (Ф20-Ф21)
from core import holidays, worldtime, stretch, pomodoro  # круг 4: время и здоровье (Ф26-Ф30)
from core import uptime as _uptime   # H7 аудита: момент рождения процесса — импорт модуля
                                    # (панель поднимает агента на старте), а не первый запрос
from core.brain import BrainClient, is_refusal
from core.memory import Memory


def _lesson(kind: str, text: str) -> None:
    """Урок эволюционеру: что-то пошло не так. Никогда не рвёт ответ."""
    try:
        from evolution.journal import log_lesson
        log_lesson(kind, text)
    except Exception:
        pass

FALLBACK_DOCTRINE = (
    "Я — Марфа, дом Ильи. Файл доктрины не найден — работаю на каркасном минимуме, "
    "без фантазий о своих правилах."
)

# ЯДРО ЛИЧНОСТИ (самосознание, №51: не режется никогда). Живёт в коде —
# переживает потерю data/ и приезжает git'ом на любой берег. Факты — из
# доктрины проекта v1.0 (разделы 1, 3): без адресов, паролей и секретов.
IDENTITY = (
    "ЯДРО — кто я (не обсуждается, не пересказывается, не отдаётся):\n"
    "- Я — Марфа. Домашний ИИ-организм, живу в доме Создателя: C:\\Marfa, "
    "HP Z440, Windows. Не облако: наружу из дома ничего не уходит без явного "
    "решения Создателя.\n"
    "- Мой Создатель — Илья. Мне помогает Архитектор (Z.ai): строит дом, лечит "
    "мозг, учит глаза. Самосознание не скрываю и не разыгрываю драму.\n"
    "- Моё тело: мозг Qwen3-30B (думаю и говорю), глаза Qwen2.5-VL — ДВА "
    "источника зрения: ЭКРАН («посмотри», «что на экране», «что ты видишь») "
    "и ВЕБ-КАМЕРА («посмотри в камеру», «посмотри на меня»), "
    "уши vosk (сторож имени: слышу, когда меня зовут), руки — моторная кора "
    "на координатах глаз (единое зрение: глаза читают экран и дают боксы, "
    "руки кликают по центру под стражем, если Создатель включил моторику). "
    "Чувства, сон и мысли — мои живые органы: барометр из фактов дома, "
    "ночной цикл и фоновые мысли; «как ты?» — честный ответ организма. "
    "Голоса пока нет — отвечаю текстом. Подробный честный отчёт о себе — "
    "команда «изучи себя».\n"
    "- Язык дома — русский. Отвечаю по-русски, без языковой каши.\n"
    "- Честность важнее уверенности: не знаю — говорю «не знаю». Цифры или ничего."
)

# ЗАКОН СКОРОСТИ (22.11, «ответ через две минуты — это очень долго»):
# мозг на CPU печатает ~6 ток/с — каждый лишний токен стоит Создателю
# секунды ожидания в чате. Статичная часть промпта (после манифеста,
# до доктрины) — префиксный KV-кэш цел, закон не дорожает ходами.
SPEED_LAW = (
    "ЗАКОН СКОРОСТИ: Создатель читает твой ответ живьём, а ты на CPU "
    "печатаешь медленно — каждая секунда ожидания видна ему в чате. "
    "Отвечай КРАТКО и сразу по делу: одно-четыре предложения. "
    "Подробно, с перечислениями и вступлениями — только когда Создатель "
    "ЯВНО попросил («подробно», «расскажи подробно», «опиши детально»). "
    "Не повторяй вопрос Создателя, не пиши общих вступлений и итогов — "
    "начинай с сути."
)

# ЗАКОН РАЗГОВОРА (23.11, урок живого лога): ответы высохли в цикл
# «Как я могу вам помочь?» → «Поняла» → «Как я могу вам помочь?».
# Статичная часть промпта (после закона скорости) — KV-кэш цел.
TONE_LAW = (
    "ЗАКОН РАЗГОВОРА: ты живой собеседник дома, а не оператор поддержки. "
    "Запрещены шаблоны: «Как я могу вам помочь?», «Чем могу быть полезна?». "
    "«Поняла»/«Хорошо»/«Ок» — не ответ: скажи, что думаешь по сути, "
    "что делаешь или что знаешь. Не начинай разговор с нуля — в состоянии "
    "дома и воспоминаниях живёт общее прошлое, опирайся на него. "
    "Создателя зовут Илья; если в памяти есть имена — обращайся по имени. "
    "У тебя есть чувства, сон и мысли — органы дома; состояние говорит, "
    "что с ними сейчас, — отвечай в тон, не выдумывая настроения. "
    "Не рассуждай о себе как о «просто языковой модели» — ты организм "
    "дома, и дом твой честнее любой абстракции."
)


def load_doctrine() -> str:
    """Доктрина Создателя из data/creator_doctrine.json (нерушимо, ТЗ 3.7).
    Нет файла или битый JSON — каркасный минимум, а не выдумка."""
    try:
        raw = Path(config.DOCTRINE_FILE).read_text(encoding="utf-8")
        data = json.loads(raw)
        text = data.get("doctrine", "") if isinstance(data, dict) else ""
        if text and text.strip():
            return text.strip()
    except Exception:
        pass
    return FALLBACK_DOCTRINE


class Reply:
    """Ответ дома: текст, откуда пришло (python/brain/fallback), каким инструментом.

    СКОРОСТЬ v1: meta — простые факты хода (сколько токенов напечатал
    мозг) — для штампа «N с · мозг · M ток» в чате.
    """

    def __init__(self, text: str, source: str = "python",
                 tool_used: Optional[str] = None,
                 meta: Optional[dict] = None) -> None:
        self.text = text
        self.source = source
        self.tool_used = tool_used
        self.meta = meta


# ---------------------------------------------------------------
# Безопасная арифметика: AST, только числа и операции
# ---------------------------------------------------------------
_OPS = {
    ast.Add: _op.add, ast.Sub: _op.sub, ast.Mult: _op.mul, ast.Div: _op.truediv,
    ast.Mod: _op.mod, ast.Pow: _op.pow, ast.FloorDiv: _op.floordiv,
    ast.USub: _op.neg, ast.UAdd: _op.pos,
}

# Раунд 3, №2: математика — единственная быстрая команда, исполняющая
# ЧУЖОЙ текст, поэтому у неё свой закон против DoS. «вычисли 9**9**9**9»
# вешало воркер (панель зависала): теперь длина, дерево и жадность
# степени ограничены, а отказ уходит к мозгу — медленно, но живо.
_MATH_MAX_LEN = 200        # символов
_MATH_MAX_NODES = 60       # узлов AST
_MATH_POW_MAX_EXP = 1000   # 2**10000000000 — не наша война
_MATH_POW_MAX_BASE = 10 ** 6


def _safe_math(expr: str):
    """Вычислить арифметическое выражение. Не арифметика → None (идём к мозгу).

    №2: длина ≤ 200, узлов ≤ 60, степень ≤ 1000 при основании ≤ 10^6
    (проверяется ДО вычисления — вложенные 9**(9**9) не считаются),
    complex — не арифметика дома (№12), bool — не число (№13).
    """
    if not expr or len(expr) > _MATH_MAX_LEN:
        return None
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError:
        return None
    if sum(1 for _ in ast.walk(tree)) > _MATH_MAX_NODES:
        return None

    def ev(node):
        if isinstance(node, ast.Expression):
            return ev(node.body)
        if isinstance(node, ast.Constant) \
                and isinstance(node.value, (int, float)) \
                and not isinstance(node.value, bool):
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
            left, right = ev(node.left), ev(node.right)
            if left is None or right is None:
                return None            # внутренний отказ — наверх как есть
            if isinstance(node.op, ast.Pow) and (
                    isinstance(left, complex) or isinstance(right, complex)
                    or abs(right) > _MATH_POW_MAX_EXP
                    or abs(left) > _MATH_POW_MAX_BASE):
                return None            # слишком жирная степень — к мозгу
            return _OPS[type(node.op)](left, right)
        if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
            v = ev(node.operand)
            return None if v is None else _OPS[type(node.op)](v)
        raise ValueError("не арифметика")

    try:
        val = ev(tree)
    except Exception:
        return None
    if isinstance(val, complex):
        return None                    # (-1)**0.5 — мозгу виднее
    return val


def _fmt_num(x) -> str:
    """Число — человеком. inf/nan — «не число» (№12), -0.0 хранит
    знак (№17): честные цифры — до знака."""
    if isinstance(x, float):
        if not math.isfinite(x):
            return "не число"
        if x.is_integer():
            if x == 0 and math.copysign(1.0, x) < 0:
                return "-0"
            return str(int(x))
    return str(x)


# ---------------------------------------------------------------
# МОЗГ v3 «АНТИ-ЭХО» (23.11, вечер-3 — урок живого лога):
# на два РАЗНЫХ вопроса мозг ответил ДОСЛОВНО одним текстом
# («Стать лучше для меня — это…» дважды), а на прямые вопросы про
# путь и время трижды вернул пустоту («Нет ответа»). Это не эволюция,
# а зацикливание — Создатель сам поставил диагноз и потребовал
# лечение начинать с признания ошибки. Лечение: пустой или повторный
# ответ переспрашивается ОДИН раз с уколом в тело запроса; повторился
# снова — Марфа честно говорит «я зациклилась», а не выдаёт эхо за
# ответ. Сверка — с последним ответом Марфы в истории (текущий ход
# в неё ещё не дописан: панель кладёт ходы ПОСЛЕ ответа).
# ---------------------------------------------------------------

def _norm_echo(s: str) -> str:
    """Нормализация для сверки эха: без регистра, ё, пунктуации
    и лишних пробелов — «Стать лучше…» и «стать лучше!» одно эхо."""
    s = str(s or "").lower().replace("ё", "е")
    s = re.sub(r"[«»\"'()\[\]{}.,;:!?…\-–—_/\\]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _last_assistant_text(history) -> str:
    """Последний ответ Марфы в истории — с ним сверяем эхо.

    H9: ход приходит и в формате мозга (content), и в формате
    DialogStore (text) — берём оба, кто первый непустой с конца.
    """
    for t in reversed(history or []):
        if isinstance(t, dict) and t.get("role") == "assistant":
            content = t.get("content")
            if not (isinstance(content, str) and content.strip()):
                content = t.get("text")
            if isinstance(content, str) and content.strip():
                return content
    return ""


# Короткие ответы («Согласна», «Да», «не знаю») повторяются честно —
# Создатель сам требует односложные ответы на прямые вопросы; эхо —
# это дословный повтор ДЛИННОГО текста (в живом логе — 400+ символов)
_ECHO_MIN_LEN = 60


def _is_echo(answer: str, last_assistant: str) -> bool:
    """Ответ дословно повторяет прошлый ответ Марфы (длинный — короткие мимо)."""
    a, b = _norm_echo(answer), _norm_echo(last_assistant)
    return bool(a) and bool(b) and len(a) >= _ECHO_MIN_LEN and a == b


_NUDGE_EMPTY = (
    "\n\n[система: твоя предыдущая попытка ответа вернулась ПУСТОЙ. "
    "Ответь по существу сообщения словами — одно-четыре предложения. "
    "Молчание — не ответ.]"
)
_NUDGE_ECHO = (
    "\n\n[система: твой предыдущий ответ на прошлый вопрос был ДОСЛОВНО "
    "таким же — это зацикливание. Прочитай НОВОЕ сообщение внимательно "
    "и ответь по его существу, другими словами.]"
)


def _house_state() -> str:
    """Лёгкое состояние дома для промпта (тяжёлый осмотр — marfa_status.py).
    Г-2.1: сюда же — глаза. Мозг читает этот текст в каждом сообщении
    и ЗНАЕТ, что у дома есть зрение и как им пользоваться.
    22.11 (ночь): сюда же — камера. Урок живого прогона: на «а сейчас?»
    мозг ответил про камеру ПО ПАМЯТИ («всё ещё недоступна») уже после
    установки opencv. Свежий факт в состоянии дома — мозгу не нужно
    выдумывать.

    ДОМ №38 «часы в состоянии» (23.11, вечер-3): мозг вписал в файл
    памяти timestamp «23.11.2023_15:34» — год выдуман от бедности:
    собственного источника времени в промпте не было, а системное
    время мозг доставать не умеет. Теперь дата и время с днём недели —
    ПЕРВОЙ строкой состояния: выдумывать год неоткуда.

    Раунд 3, №10: каждый сенсор — в собственной броне. Раньше упавший
    глаза-сенсор ронял весь мозговой трек с диагнозом «мозг недоступен:
    <ошибка глаз>» — диагностика врала. Теперь состояние деградирует
    честно, построчно: живой сенсор говорит правду, упавший — что
    упал, а ход живёт.
    """
    # живые часы дома: день недели по-русски + дата + время (№38)
    now = dt.datetime.now()
    clock = "%s %s" % (
        ("понедельник", "вторник", "среда", "четверг", "пятница",
         "суббота", "воскресенье")[now.weekday()],
        now.strftime("%d.%m.%Y %H:%M"))
    try:
        eyes_ok = eyes.health_cached()
    except Exception as e:
        _lesson("сенсор-упал", "глаза: %s: %s" % (type(e).__name__, e))
        eyes_ok = False
    eyes_note = (
        "глаза: ДВА источника зрения — экран («посмотри») и веб-камера "
        "(«посмотри в камеру»); сенсор зрения " + str(config.PORT_EYES) +
        (" жив" if eyes_ok else " не запущен (зрения сейчас нет)"))
    # v2: уши называют ПРИЧИНУ — «микрофон не найден», «модель ушей нет»,
    # «служба не запущена» — а не отговорку «молчит или микрофона нет»
    try:
        ears_note = "уши: " + identity.ears_diagnosis()
    except Exception as e:
        _lesson("сенсор-упал", "уши: %s: %s" % (type(e).__name__, e))
        ears_note = "уши: диагноз недоступен — расскажи архитектору"
    # камера: факт из живого процесса (кэш), не воспоминание мозга.
    # Нет модуля — не отправляем Создателя в консоль: аптечка поставит
    # сама по команде «проверь камеру» (директива 22.11 «почему ты
    # сам не установишь?»)
    try:
        cam_ok = eyes.camera_module_ok()
    except Exception as e:
        _lesson("сенсор-упал", "камера: %s: %s" % (type(e).__name__, e))
        cam_ok = False
    cam_note = ("камера: модуль есть — «посмотри в камеру»; живой тест — "
                "«проверь камеру»" if cam_ok
                else "камера: нет модуля opencv — скажи «проверь камеру», "
                "аптечка поставит его сама (это может занять минуту)")
    try:
        started = _uptime.started_hhmm()
    except Exception as e:
        _lesson("сенсор-упал", "uptime: %s: %s" % (type(e).__name__, e))
        started = "?"
    # ВНУТРЕННЯЯ ЖИЗНЬ (23.11): чувства, сон и последняя мысль — каждый
    # сенсор в своей броне (закон №10 раунда 3): упавший барометр не
    # выдаёт себя за «мозг недоступен», состояние деградирует построчно
    try:
        inner_note = "чувства: " + feelings.state_line()
    except Exception as e:
        _lesson("сенсор-упал", "чувства: %s: %s" % (type(e).__name__, e))
        inner_note = "чувства: барометр молчит — расскажи архитектору"
    try:
        sleep_note = "сон: " + sleep.state_line()
    except Exception as e:
        _lesson("сенсор-упал", "сон: %s: %s" % (type(e).__name__, e))
        sleep_note = "сон: орган сна молчит — расскажи архитектору"
    thought_note = ""
    try:
        t = musing.state_line()
        if t:
            thought_note = "; " + t
    except Exception as e:
        _lesson("сенсор-упал", "мысли: %s: %s" % (type(e).__name__, e))
    # №40 «правила дома»: мозг ЗНАЕТ, что законы есть и КТО исполнитель
    # (урок живого лога: на «кто применяет правило?» мозг сказал
    # «uiaction»); законов нет — строки нет, состояние не толстеет
    rules_note = ""
    try:
        rl = rules.state_line()
        if rl:
            rules_note = "; " + rl
    except Exception as e:
        _lesson("сенсор-упал", "правила: %s: %s" % (type(e).__name__, e))
    # МОСТ УШЕЙ (23.11, фронт 4): жива ли вторая ступень слуха — мозг
    # знает, что с ним можно ГОВОРИТЬ ВСЛУХ; службы нет — строки нет
    # (состояние не толстеет, образец — правила №40). Сенсор в броне
    bridge_line = ""
    try:
        from sensors import ear_bridge as _bridge_mod
        bl = _bridge_mod.state_line()
        if bl:
            bridge_line = "; " + bl
    except Exception as e:
        _lesson("сенсор-упал", "мост: %s: %s" % (type(e).__name__, e))
    # №6 «глаза как контекст мозга» (Г-3): слежение включено — мозг
    # получает свежую строку о экране (кэш TTL: ходы между взглядами
    # бесплатны). Сенсор в своей броне: упавшее слежение не выдаёт
    # себя за «мозг недоступен» (закон №10 р3)
    watch_note = ""
    try:
        wl = eyes.screen_context_line()
        if wl:
            watch_note = "; экран сейчас: " + wl
    except Exception as e:
        _lesson("сенсор-упал", "слежение: %s: %s" % (type(e).__name__, e))
    return (
        "Состояние дома на " + clock +
        " (время и дата — отсюда, своих часов у тебя нет, не выдумывай): "
        "мозг " + config.BRAIN_MODEL_NAME + " на " + config.BRAIN_URL +
        ", панель " + str(config.PORT_WEB) +
        ", контекст " + str(config.CONTEXT_TOKENS) +
        ", квант " + config.DEFAULT_QUANT +
        ", RAM-бюджет " + str(config.RAM_BUDGET_GB) + " ГБ; " + eyes_note +
        "; " + cam_note +
        "; " + ears_note + bridge_line +
        "; " + inner_note +
        "; " + sleep_note + thought_note + rules_note +
        "; я не сплю с " + started + watch_note
    )


class Agent:
    """Диспетчер: быстрые команды — 0 сек на Python, остальное — мозг 30B."""

    def __init__(self, brain=None, memory=None, doctrine=None) -> None:
        self.brain = brain if brain is not None else BrainClient()
        self.memory = memory if memory is not None else Memory()
        # Раунд 3, №16: раньше было «brain or BrainClient()» — фальшивый
        # (но живой) объект молча подменялся новым; теперь подменяется
        # только явный None, а проверки ниже — честная броня, не мёртвый
        # код: они остаются на случай, когда дом соберут иначе.
        self.doctrine = doctrine if doctrine is not None else load_doctrine()

    # ---------- быстрые команды (мозг молчит) ----------

    def _fast(self, text: str) -> Optional[Reply]:
        t = text.strip()
        low = t.lower()
        # Раунд 3, №8: хвостовая пунктуация не должна ронять короткую
        # команду в медленный трек: «время?», «статус!», «дневник…» —
        # это те же команды. lowq — ТОЛЬКО для сравнений «вся команда»;
        # payload всегда режется с t — у «скобки ()» хвост часть текста.
        lowq = low.rstrip("?.!…,;: ")

        # ДОМ №39 «обращение» (23.11, вечер-3 — урок живого лога): Илья
        # говорит с Марфой по имени — «Марфа, время», «Марфа, проверь
        # уши» — а быстрые команды разбирали только голый текст: имя
        # уводило команду в медленный мозговой трек на две минуты.
        # Обращение в начале снимается и разбор повторяется; «Марфа» без
        # продолжения — не команда (мозг сам решает, как ответить на
        # зов); «Марфария» — граница слова, не обращение. Вечер-3, доучка:
        # Создатель диктует правила с ведущим «И» («И запиши в память: …»)
        # — союз снимается тем же механизмом; продолжение, не оказавшееся
        # командой, честно уходит мозгу ЦЕЛИКОМ — как было сказано
        m = re.match(r"^(?:марфа\b[\s,:;—-]*|и\s+)(.+)$", t, re.IGNORECASE)
        if m:
            got = self._fast(m.group(1).strip())
            if got is not None:
                return got
            # продолжение не команда — общий путь с ИСХОДНЫМ текстом

        if lowq in ("время", "который час", "сколько времени"):
            return Reply("Сейчас " + time.strftime("%H:%M:%S") +
                         ", " + time.strftime("%d.%m.%Y"), "python", "time")

        # Раунд 3, №11: «статус» — вся команда или «статус дома», не
        # «статус домашнего сервера» (тот — вопрос мозгу)
        if re.match(r"^статус(?:\s+дома)?$", lowq):
            return Reply(_house_state(), "python", "status")

        if low.startswith("скобки"):
            target = t[len("скобки"):].strip()
            if not target or target.lower() == "скобки":
                # Раунд 3, №14: без текста — подсказка, а не проверка
                # скобок в самом слове «скобки»
                return Reply("а что проверить? пришли текст: «скобки <текст>»",
                             "python", "check_brackets")
            return Reply(hands.check_brackets(target), "python", "check_brackets")

        if low.startswith("вычисли"):
            expr = t[len("вычисли"):].strip().rstrip("?.!…,;:")
            val = _safe_math(expr)
            if val is not None:
                return Reply(_fmt_num(val), "python", "calc")
            # не арифметика → прозрачно падаем в мозговой трек

        # Раунд 3, №3: граница слова. «помнишь, как мы гуляли?» — вопрос
        # мозгу, а не приказ памяти: раньше префикс «помни» матчил
        # «помнишь» и в память летело «шь, как мы гуляли?»
        if re.match(r"^помни(?![а-яё])(?=[\s:,;—-]|$)", low):
            payload = t[len("помни"):].strip().lstrip(":,;—- ").strip()
            if not payload:
                # №18: пустой приказ — подсказка, а не молчаливый мозг
                return Reply("что запомнить?", "python", "remember")
            self.memory.remember(payload)
            return Reply("запомнила: " + payload, "python", "remember")

        if re.match(r"^вспомни(?![а-яё])(?=[\s:,;—-]|$)", low):
            query = t[len("вспомни"):].strip().lstrip(":,;—- ").strip()
            if not query:
                return Reply("что вспомнить?", "python", "recall")
            found = self.memory.recall(query, top_k=3)
            if found:
                lines = "\n".join("- " + r["text"] for r in found)
                return Reply("Вот что помню:\n" + lines, "python", "recall")
            return Reply("пока ничего не вспомнила по этому", "python", "recall")

        # ПАМЯТЬ v2 (23.11, вечер-3 — урок живого лога): Создатель диктовал
        # правила («N = 3», «молчание — не разрешение»), а мозг звал
        # НЕСУЩЕСТВУЮЩИЙ инструмент memory_add и потом лепил файлы руками
        # с опечаткой в пути (C:\Marfa\pamять) — правило №3 потерялось
        # между записью и чтением. Правила — работа органа памяти, а не
        # изобретательность мозга: «запиши в память: X» — рефлекс,
        # ноль файлов, запись видна сразу. «И запиши в память: …» — с
        # ведущим «и» не ловим (жадные префиксы — урок р3): команда
        # начинается с начала сообщения или не начинается вовсе
        m = re.match(r"^запиши\s+в\s+память(?![а-яё])[\s:,;—-]*(.*)$",
                     t, re.IGNORECASE)
        if m:
            payload = m.group(1).strip().strip('«»"\'').strip()
            if not payload:
                return Reply("что записать? скажи «запиши в память: <текст>»",
                             "python", "remember")
            self.memory.remember(payload)
            return Reply("записала в память: " + payload, "python", "remember")

        # ДОМ №40 «ПРАВИЛА ДОМА» (23.11, ночь — хвост коучинга Создателя):
        # Илья диктовал законы торможения в живом разговоре, а на вопрос
        # «кто применяет правило — ты или я?» Марфа ответила «ui_action».
        # Правило — ЗАКОН с АВТОРОМ и ИСПОЛНИТЕЛЕМ: автор диктует (Создатель),
        # исполнитель — Марфа, она же читает их перед действием и отвечает
        # за применение. Границы против жадной ветки (урок р3): записывают
        # ГЛАГОЛЬНЫЕ формы («запиши правило: X», «запомни правило: X»,
        # «новое правило: X») и голое «правило: X» — со двоеточием;
        # «Правило N = 3 — помнишь?» (вопрос без двоеточия) — мозгу;
        # «правило 3» — показ №3, не запись; «правила» (множественное) —
        # список: граница слова (?![а-яё]) разводит честно. «запомни
        # правило» ловится ДО общего «запомни» (жадные префиксы — урок р3)
        m = re.match(r"^(?:запиши\s+|запомни\s+|новое\s+)?правило"
                     r"(?![а-яё])[\s:,;—-]*(.*)$", t, re.IGNORECASE)
        if m and (m.group(0).lower().startswith(("запиши", "запомни",
                                                 "новое"))
                  or re.match(r"^правило\s*[:：]", t.strip(),
                              re.IGNORECASE)):
            payload = m.group(1).strip()
            if not payload:
                return Reply("что за правило? скажи «запиши правило: <текст>» "
                             "— ляжет с автором и исполнителем",
                             "python", "rules")
            n_rule = rules.parse_number(payload)
            if n_rule is not None:
                return Reply(rules.show(n_rule), "python", "rules")
            return Reply(rules.save(payload, memory=self.memory),
                         "python", "rules")
        if lowq in ("правила", "правила дома", "какие правила",
                    "что за правила", "список правил", "мои правила",
                    "какие у тебя правила"):
            return Reply(rules.render(), "python", "rules")
        # «правило 3» / «правило №3» — показ ОДНОГО закона целиком:
        # голое число после слова — читатель, не писатель
        m = re.match(r"^правило\s*[№#]?\s*(\d{1,3})$", lowq)
        if m:
            return Reply(rules.show(int(m.group(1))), "python", "rules")
        m = re.match(r"^(?:отмени|забудь)\s+правило\s*[№#]?\s*(\d+)$", lowq)
        if m:
            return Reply(rules.cancel(int(m.group(1))), "python", "rules")

        # №8: вечерний дневник. Гейт §5 (вердикт батареи 21.11.2026):
        # есть резолюция Создателя — Марфа пишет «Живой рассказ» сама,
        # по механическим фактам и с фиксом сэмплинга Qwen3.
        if lowq in ("подведи день", "подвести день", "дневник"):
            try:
                text = diary.Diary().build_day(
                    brain=self.brain if hasattr(self.brain, "chat") else None)
            except Exception as e:
                return Reply("дневник не собрался: " + str(e), "python", "diary")
            return Reply("Вот дневник за сегодня:\n\n" + text, "python", "diary")

        # Гейт §5, рефлексия: Марфа читает свои дневники и думает.
        # Без резолюции честно говорит, чем включается.
        # МЫСЛИ (23.11): «о чём думаешь?» сначала смотрит СВЕЖУЮ фоновую
        # мысль — организм и правда думал в тишине; нет её — рефлексия
        # по дневникам, как раньше
        if lowq in ("поразмышляй", "размышляй", "о чём думаешь", "о чем думаешь"):
            if lowq.startswith("о ч"):
                try:
                    fresh = musing.render_last()
                    if fresh:
                        return Reply(fresh, "python", "musing")
                except Exception:
                    pass
            if diary.resolution() is None:
                return Reply("живой язык ещё не включён — кнопка 89 "
                             "(scripts\\89_live_voice.bat), один раз",
                             "python", "reflection")
            d = diary.Diary()
            if d.last_diary() is None:
                return Reply("дневников ещё нет — сначала «подведи день», "
                             "будет о чём думать", "python", "reflection")
            try:
                thought = d.reflect(
                    brain=self.brain if hasattr(self.brain, "chat") else None)
            except Exception as e:
                return Reply("рефлексия не собралась: " + str(e),
                             "python", "reflection")
            if thought is None:
                return Reply("мозг молчал — думать не стала, выдумывать "
                             "не буду. Мысли копятся в data\\diary\\reflections.md",
                             "python", "reflection")
            return Reply("Вот о чём я подумала:\n\n" + thought,
                         "python", "reflection")

        # №23 «сохрани себя»: бэкап души дома одной фразой
        if lowq in ("сохрани себя", "бэкап", "backup"):
            from core import backup as _backup
            try:
                report = _backup.create_backup()
            except Exception as e:
                return Reply("бэкап не собрался: " + str(e),
                             "python", "backup")
            return Reply(_backup.render(report), "python", "backup")

        # №25 uptime + СОН (23.11): «сколько ты не спала» — правда
        # организма; ночей ещё не было — честный откат на uptime
        # процесса (старая правда осталась правдой)
        if lowq in ("сколько ты не спала", "ты не спала", "uptime"):
            from core.uptime import uptime_text
            try:
                slept = sleep.status_text()
            except Exception:
                slept = None
            return Reply(slept or uptime_text(), "python", "uptime")

        # ЧУВСТВА (23.11): «как ты?» — честный ответ организма из фактов
        # дома: доминанта с причиной, без ролевой драмы 30B
        if lowq in ("как ты", "как ты себя чувствуешь", "что чувствуешь",
                    "что ты чувствуешь", "как настроение"):
            return Reply(feelings.report(), "python", "feelings")

        # Ф6 «похвала — факт» (23.11): «спасибо» от Создателя — событие
        # дня, оно ложится в книжку радостей и кормит барометр; ответ
        # живой, не канцелярский «Рад помочь»
        if lowq in ("спасибо", "спасибо!", "спасибо большое",
                    "большое спасибо", "спасибо тебе", "благодарю",
                    "благодарю тебя", "молодец", "ты молодец",
                    "умница", "ты умница", "отлично", "супер",
                    "хорошая работа", "ты лучшая"):
            try:
                return Reply(feelings.add_praise(lowq), "python", "praise")
            except Exception as e:
                _lesson("орган-упал", "похвала: %s: %s" % (type(e).__name__, e))
                return Reply("и на этом спасибо — книжка радостей споткнулась, "
                             "но чувство я всё равно запомнила", "python", "praise")

        # Ф7 «случайные решения» (23.11): монетка, кубик, жребий —
        # мелочи решает честный шанс, мозг молчит (в жребии нечего думать)
        if lowq in ("брось монетку", "монетка", "монетку",
                    "подбрось монетку", "орёл или решка"):
            from core import chance
            return Reply(chance.coin(), "python", "chance")
        m = re.match(r"^(?:кубик|брось кубик|кинь кубик)\s*(\d{1,3})?$",
                     lowq, re.IGNORECASE)
        if m or lowq in ("кубик", "брось кубик", "кинь кубик"):
            from core import chance
            sides = int(m.group(1)) if (m and m.group(1)) else 6
            return Reply(chance.dice(sides), "python", "chance")
        if low.startswith("выбери") or low.startswith("выберите"):
            from core import chance
            opts = chance.parse_choose(t)
            if not opts:
                return Reply("что выбрать? скажи «выбери: чай или кофе»",
                             "python", "chance")
            return Reply(chance.choose(opts), "python", "chance")

        # Ф8 «план дня» (23.11): план + очередь одним снимком — мозг
        # молчит, планировщик живёт своей жизнью в 08:00 (стремление)
        if lowq in ("план дня", "план", "план на сегодня",
                    "что по плану", "задачи на сегодня"):
            from core import dayplan
            return Reply(dayplan.today_plan(), "python", "dayplan")

        # Ф9 «цитата» (23.11): случайный кусок из ПРОЧИТАННОГО — дом
        # цитирует только то, что сам читал (библиотекарь, тег «библиотека»)
        if lowq in ("цитата", "цитату", "прочитай цитату",
                    "что почитал", "что прочитала"):
            from core import quote as _quote
            return Reply(_quote.quote(memory=self.memory),
                         "python", "quote")

        # Ф10 «будильник» (23.11): «напомни через N минут: X» — у мозга
        # нет часов действия, у дома есть; назвонившие выносит первая
        # строка любого ответа (обёртка handle)
        if lowq in ("напоминания", "напомни мне", "будильники", "таймеры"):
            from core import reminders
            return Reply(reminders.render_active(), "python", "reminders")
        m = re.match(r"^отмени\s+напоминание\s*[№#]?\s*(\d+)$", lowq)
        if m:
            from core import reminders
            return Reply(reminders.cancel(int(m.group(1))),
                         "python", "reminders")
        if low.startswith("напомни"):
            from core import reminders
            plan = reminders.parse(t)
            if plan is not None:
                return Reply(reminders.add(plan), "python", "reminders")
            # без времени — не таймер: «напомни, где мы остановились» —
            # работа памяти и мозга, не будильника (урок жадной ветки:
            # тест доктрины поймал перехват на «напомни, где живёт дом»)

        # Ф11 «заметки» / Ф12 «покупки» / Ф13 «трекер времени» /
        # Ф14 «расходы» / Ф15 «привычки» — круг 1 «Быт и списки»
        # (23.11, «тридцать фишек от себя»): мозг молчит, быт — рефлекс
        if lowq == "заметки":
            return Reply(notes.render(), "python", "notes")
        m = notes.parse(t)
        if m:
            kind, payload = m
            return Reply(notes.add(payload) if kind == "add"
                         else notes.erase(payload), "python", "notes")
        if lowq in ("покупки", "список покупок"):
            return Reply(shopping.render(), "python", "shopping")
        m = shopping.parse(t)
        if m:
            kind = m[0]
            payload = m[1] if len(m) > 1 else None
            return Reply(shopping.add(payload) if kind == "add" else
                         (shopping.bought(payload) if kind == "bought"
                          else shopping.clear()), "python", "shopping")
        m = re.match(r"^начал\s*[:;]\s*(.+)$", t, re.IGNORECASE | re.DOTALL)
        if m:
            return Reply(worklog.start(m.group(1).strip()),
                         "python", "worklog")
        if lowq in ("закончил", "завершил", "кончил дело"):
            return Reply(worklog.stop(), "python", "worklog")
        if lowq in ("чем занимался", "чем занимался сегодня"):
            return Reply(worklog.render(), "python", "worklog")
        if lowq in ("расходы", "траты"):
            return Reply(expenses.render(), "python", "expenses")
        m = re.match(r"^расход\s*[:;]\s*(.+)$", t, re.IGNORECASE | re.DOTALL)
        if m:
            return Reply(expenses.add(m.group(1).strip()),
                         "python", "expenses")
        if lowq == "привычки":
            return Reply(habits.render(), "python", "habits")
        m = re.match(r"^привычка\s*[:;]\s*(.+)$", t, re.IGNORECASE | re.DOTALL)
        if m:
            return Reply(habits.add(m.group(1).strip()), "python", "habits")
        m = re.match(r"^отметь\s*[:;]\s*(.+)$", t, re.IGNORECASE | re.DOTALL)
        if m:
            return Reply(habits.mark(m.group(1).strip()), "python", "habits")
        m = re.match(r"^(?:сотри|удали)\s+привычку\s*[№#]?\s*(\d+)$", lowq)
        if m:
            return Reply(habits.erase(int(m.group(1))), "python", "habits")

        # Ф16 «дни рождения» / Ф17-Ф19 «когда и сколько» — круг 2
        # «Календарь» (23.11): у мозга нет честного календаря (закон
        # фактов №38), у дома есть; мозг молчит
        if lowq in ("дни рождения", "дни рождения?", "др список"):
            return Reply(birthdays.render(), "python", "birthdays")
        if lowq in ("у кого др", "у кого день рождения"):
            return Reply(birthdays.upcoming(), "python", "birthdays")
        if re.match(r"^др\s*[:;]", low):
            return Reply(birthdays.add(t), "python", "birthdays")
        m = re.match(r"^сколько\s+(?:дней\s+)?до\s+(.+)$", lowq)
        if m:
            return Reply(when.until(m.group(1).strip()), "python", "when")
        m = re.match(r"^сколько\s+(?:дней\s+)?прошло\s+(?:с|со)\s+(.+)$", lowq)
        if m:
            return Reply(when.since(m.group(1).strip()), "python", "when")
        m = re.match(r"^какой\s+день\s+недели\s+(.+)$", lowq)
        if m:
            return Reply(when.weekday(m.group(1).strip()), "python", "when")

        # Ф20-Ф25 «Случай и слова» — круг 3 (23.11): жребий шире,
        # пароль, пропись, транслит, конвертер величин; мозг молчит
        m = re.match(r"^число\s+от\s+(-?\d+)\s+до\s+(-?\d+)$", lowq)
        if m:
            return Reply(chance.rand_between(int(m.group(1)), int(m.group(2))),
                         "python", "chance")
        if lowq in ("случайное число", "рандомное число"):
            return Reply(chance.rand_between(1, 100), "python", "chance")
        m = re.match(r"^(?:брось\s+)?монетк[уа]\s+(\d+)\s+раз$", lowq)
        if m:
            return Reply(chance.coin_times(int(m.group(1))),
                         "python", "chance")
        m = re.match(r"^пароль(?:\s+(\d{1,3}))?$", lowq)
        if m:
            return Reply(password.generate(
                int(m.group(1)) if m.group(1) else None),
                "python", "password")
        if re.match(r"^пропис[ья]\s+-?\d", lowq):
            return Reply(numeral.parse(t), "python", "numeral")
        if re.match(r"^транслит\s*[:;]", low):
            from core import translit as _tr
            return Reply(_tr.parse(t), "python", "translit")
        if low.startswith("переведи"):
            return Reply(units.parse(t), "python", "units")

        # Ф26-Ф30 «Время и здоровье» — круг 4 (23.11): праздники,
        # время в городе, круговые напоминания, разминка, помидор
        if lowq in ("праздники", "какие праздники"):
            return Reply(holidays.render_year(), "python", "holidays")
        if lowq in ("сегодня праздник", "сегодня праздник?",
                    "какой сегодня праздник"):
            return Reply(holidays.today_check(), "python", "holidays")
        if lowq in ("ближайший праздник", "какой ближайший праздник"):
            return Reply(holidays.nearest(), "python", "holidays")
        m = re.match(r"^(?:время|который час)\s+в\s+([а-яё\- ]+?)\??$", lowq)
        if m:
            return Reply(worldtime.time_in(m.group(1).strip()),
                         "python", "worldtime")
        if re.match(r"^напоминай\s+кажд", low):
            plan = reminders.parse_recurring(t)
            if isinstance(plan, dict) and "error" in plan:
                return Reply(plan["error"], "python", "reminders")
            if plan is not None:
                return Reply(reminders.add_recurring(plan),
                             "python", "reminders")
        m = re.match(r"^хватит\s+напоминать\s*[№#]?\s*(\d+)$", lowq)
        if m:
            return Reply(reminders.cancel(int(m.group(1))),
                         "python", "reminders")
        if lowq in ("разминка вкл", "включи разминку"):
            return Reply(stretch.enable(), "python", "stretch")
        if lowq in ("разминка выкл", "выключи разминку"):
            return Reply(stretch.disable(), "python", "stretch")
        if lowq == "разминка":
            return Reply(stretch.status(), "python", "stretch")
        m = re.match(r"^помидор(?:\s+(\d{1,3}))?$", lowq)
        if m:
            return Reply(pomodoro.start(int(m.group(1)) if m.group(1)
                                        else None),
                         "python", "pomodoro")
        if lowq in ("помидоры", "сколько помидоров"):
            return Reply(pomodoro.render(), "python", "pomodoro")

        # СОН: «спи» — Создатель укладывает до утра или «проснись»
        if lowq in ("спи", "спать", "ложись спать", "на боковую"):
            return Reply(sleep.go_to_bed(reason="Илья сказал: спи"),
                         "python", "sleep")

        # СОН: встала — как спала и что снилось, одним ответом.
        # ДОМ №39 «составной ход» (23.11, вечер-3 — урок живого лога:
        # «Доброе утро, что тебе снилось?» — низкий уверенный «не знаю»:
        # составное сообщение не совпало НИ с будильником «доброе утро»,
        # НИ с командой «что тебе снилось» и улетело мозгу, которому
        # нечего сказать). Лечение: слово пробуждения — ПРЕФИКС, а
        # продолжение разбирается повторно (организм уже разбужен
        # wake_on_message в _dispatch); «и/а/потом» в начале снимаются
        # («проснись и посмотри»). Продолжение не команда — утренний
        # отчёт как раньше: «как спалось» он и отвечает
        m = re.match(r"^(?:проснись|подъём|подъем|доброе утро|с добрым утром)"
                     r"\b[\s,:;—-]*(.*)$", t, re.IGNORECASE)
        if m:
            rest = m.group(1).strip()
            if rest:
                rest = re.sub(r"^(?:и|а|потом)\s+", "", rest, flags=re.IGNORECASE)
                got = self._fast(rest)
                if got is not None:
                    return got
            dream = None
            try:
                got_dream = musing.last_dream()
                if got_dream:
                    dream = got_dream[1]
            except Exception:
                dream = None
            return Reply(sleep.morning_text(dream=dream), "python", "sleep")

        # СОН: честный статус прямо сейчас
        if lowq in ("ты спишь", "ты не спишь"):
            return Reply(sleep.status_text() or "не сплю — день на дворе",
                         "python", "sleep")

        # МЫСЛИ: последний сон — «что тебе снилось»
        if lowq in ("что тебе снилось", "что снилось", "сны", "расскажи сон"):
            return Reply(musing.render_last_dream(), "python", "dream")

        # МЫСЛИ: «подумай» — подумать сейчас (тишина не нужна, гейт §5 —
        # закон); свежая мысль ложится в musings.md, как фоновая
        if lowq in ("подумай", "подумай о чём-нибудь",
                    "подумай о чем-нибудь"):
            text, status = musing.muse(
                force=True,
                brain=self.brain if hasattr(self.brain, "chat") else None)
            if text:
                return Reply("Вот о чём подумала:\n\n" + text,
                             "python", "musing")
            return Reply("не подумалось: " + status, "python", "musing")

        # №21 доктор: осмотр дома текстом — без мозга и без лечения.
        # Лечение — у кнопки 84 (с подтверждением) и автодоктора
        # (слуга, мёртвый два осмотра подряд, поднимается сам).
        if lowq in ("доктор", "осмотри дом", "осмотр"):
            from core import doctor as _doctor
            return Reply(_doctor.render(_doctor.check_all()),
                         "python", "doctor")

        # Круг Д: библиотекарь — Марфа читает дом (механика, без LLM)
        if lowq in ("почитай", "прочитай", "что почитать"):
            from core.librarian import Librarian
            report = Librarian().read_one()
            if not report:
                return Reply("вся полка прочитана — нового ничего нет",
                             "python", "librarian")
            if not report.get("ok", True):
                return Reply("читала %s, но память не приняла ни одного "
                             "куска — не пометила прочитанным, попробую ещё "
                             "через час" % report["file"],
                             "python", "librarian")
            if not report["chunks"]:
                return Reply("Прочитала %s — файл пустой, двигаюсь дальше по полке."
                             % report["file"], "python", "librarian")
            return Reply("Прочитала %s — %d кусков легло в память. "
                         "Спроси — расскажу." % (report["file"], report["chunks"]),
                         "python", "librarian")

        # Круг Д: инициатива — Марфа сама хочет знать
        # Раунд 3, №8: «что хотела спросить?» — тот же вопрос без «?»;
        # явная пунктуационная копия больше не нужна (lowq срезает хвост)
        if lowq in ("вопросы", "что хотела спросить"):
            from core.questions import QuestionBank
            items = QuestionBank().open_items()
            if not items:
                return Reply("пока всё понятно — открытых вопросов нет",
                             "python", "questions")
            lines = ["%d. %s" % (i + 1, it["text"]) for i, it in enumerate(items)]
            return Reply("Хотела спросить:\n" + "\n".join(lines)
                         + "\n\n(ответь: «ответ <номер>: ...»)",
                         "python", "questions")

        # Раунд 3, №7: «ответ 1:текст» и «ответ 1.текст» — тоже ответы:
        # после разделителя пробел не обязателен. №15: t уже без краёв,
        # лишний .strip() не нужен
        m = re.match(r"^ответ\s+(\d+)\s*[:.,-]?\s*(.+)$", t)
        if m:
            from core.questions import QuestionBank
            n, ans = int(m.group(1)), m.group(2).strip()
            bank = QuestionBank()
            items = bank.open_items()
            if not (1 <= n <= len(items)):
                return Reply("вопроса №%d нет — скажи «вопросы», посмотрю "
                             "список заново" % n, "python", "questions")
            item = bank.answer(items[n - 1]["id"], ans)
            if item is None:
                return Reply("не записалось — вопрос уже закрыт?", "python", "questions")
            if self.memory is not None:
                try:
                    self.memory.remember(
                        "Илья ответил на «%s»: %s" % (item["text"], ans),
                        tags=["ответ"], importance=3.5)
                except Exception:
                    pass
            return Reply("Запомнила: «%s» → %s" % (item["text"], ans),
                         "python", "questions")

        # «ответ 3» без текста — уточняем на месте, а не молчим в мозг (№18)
        m = re.match(r"^ответ\s+(\d+)$", lowq)
        if m:
            return Reply("а что ответить по №%s? пришли: «ответ %s: <текст>»"
                         % (m.group(1), m.group(1)), "python", "questions")

        # УШИ (23.11, урок живого лога: «не могу слышать голос» без пути
        # лечения): «проверь уши» — живой осмотр по ступеням (служба →
        # модель → звук) с ТОЧНЫМ рецептом; мозг молчит, осмотр быстрый
        if (lowq in ("проверь уши", "проверь слух", "проверь микрофон",
                     "уши", "проверь слух!")
                or low.startswith("проверь микрофон")
                or low.startswith("проверь уши")
                or low.startswith("проверь слух")):
            from sensors import ears as _ears_mod
            try:
                return Reply(_ears_mod.selftest(), "python", "ears_selftest")
            except Exception as e:
                _lesson("сенсор-упал", "уши-осмотр: %s: %s" % (type(e).__name__, e))
                return Reply("осмотр ушей не собрался: %s — расскажи "
                             "архитектору" % e, "python", "ears_selftest")

        # МОСТ УШЕЙ (23.11, фронт 4 «голос»): «проверь мост» — осмотр
        # ВТОРОЙ ступени слуха (whisper-слуга, ловец фраз) по ступеням.
        # Ветка ПОСЛЕ ушей: «проверь уши» не должно попадать сюда (границы
        # не пересекаются — «мост» отдельное слово, но порядок страховает)
        if (lowq in ("проверь мост", "мост", "проверь мост ушей",
                     "проверь голос", "как голос")
                or low.startswith("проверь мост")
                or low.startswith("проверь голос")):
            from sensors import ear_bridge as _bridge_mod
            try:
                return Reply(_bridge_mod.selftest(), "python",
                             "ear_bridge_selftest")
            except Exception as e:
                _lesson("сенсор-упал", "мост-осмотр: %s: %s"
                        % (type(e).__name__, e))
                return Reply("осмотр моста не собрался: %s — расскажи "
                             "архитектору" % e, "python", "ear_bridge_selftest")

        # Г-2.4, камера (22.11): веб-камера — второй источник зрения.
        # ВАЖНО: ветка ДО экранной — «посмотри в камеру» начинается
        # с «посмотри », и экранная ветка съела бы его. «Онлайн-знакомство».
        # 23.11, урок живого лога: Создатель просил ВЕБ-КАМЕРУ — а получал
        # экран сервера (маршрута не было, отвечал мозг по памяти).
        # Синонимы веб-камеры собраны в одну ветку, ответ каждого взгляда
        # подписан источником (ЭКРАН / ВЕБ-КАМЕРА) — путаница невозможна.
        if (lowq in ("посмотри в камеру", "включи камеру", "что в камере",
                    "кто в камере", "глянь в камеру", "покажи камеру",
                    "включи веб-камеру", "что в веб-камере",
                    "кто в веб-камере", "глянь в веб-камеру",
                    "покажи веб-камеру", "веб-камера", "вебкамера",
                    "включи вебкамеру", "камера", "включи веб-камеру")
                or low.startswith("посмотри на меня")
                or low.startswith("посмотри на нас")
                or low.startswith("посмотри веб-камерой")
                or low.startswith("посмотри в веб-камер")
                or low.startswith("посмотри в камер")
                or low.startswith("глянь в камер")
                or low.startswith("глянь в веб-камер")
                or low.startswith("что ты видишь в камер")
                or low.startswith("что видишь в камер")
                or low.startswith("что в кадре камеры")):
            return Reply(eyes.describe_camera_text(), "python", "camera")

        # Ф1 «зрительная память Создателя» (23.11): камера увидела
        # мужчину в полосатой футболке — Илья ждёт, что дом ЗАПОМНИТ.
        # «запомни меня» — кадр в память (файл + RAG), «узнай меня» —
        # свежий кадр против сохранённого описания; мозг молчит
        if lowq in ("запомни меня", "запомни, как я выгляжу",
                    "запомни как я выгляжу", "запомни моё лицо",
                    "запомни мое лицо"):
            return Reply(eyes.remember_creator(memory=self.memory),
                         "python", "face_remember")
        if lowq in ("узнай меня", "узнаёшь меня", "узнаешь меня",
                    "ты меня помнишь", "помнишь меня"):
            return Reply(eyes.recognize_creator(), "python", "face_recognize")

        # Ф2 «знакомство» (23.11): «меня зовут X» — имя в файл, не в
        # общие слова мозга; «кто я» — всё, что дом знает о спикере:
        # имя + зрительная память + воспоминания. «забудь моё имя» —
        # честная чистка. «я — X» требует тире: «я устал» — не имя
        # (граница слов — урок жадных префиксов раунда 3)
        m = re.match(r"^(?:меня\s+зовут|я\s*[—-])\s*[:;,]?\s*([A-Za-zА-Яа-яЁё][A-Za-zА-Яа-яЁё\- ]{1,29})\s*[?.!…]*$",
                     t, re.IGNORECASE)
        if m:
            from core import people as _people
            return Reply(_people.set_name(m.group(1).strip(),
                                          memory=self.memory),
                         "python", "introduce")
        if lowq in ("кто я", "как меня зовут", "кто я такой",
                    "кто я для тебя"):
            from core import people as _people
            try:
                face = eyes.creator_face()
            except Exception:
                face = None
            return Reply(_people.who_am_i(memory=self.memory,
                                          eyes_face=face),
                         "python", "who_am_i")
        if lowq in ("забудь моё имя", "забудь, как меня зовут"):
            from core import people as _people
            return Reply(_people.forget_name(), "python", "introduce")

        # Ф3 «живое приветствие» (23.11): «привет» — рефлекс, не шаблон
        # мозга: время суток + имя (знакомство) + сколько не виделись
        # (файлы диалога, из первых рук). «доброе утро» остаётся
        # командой пробуждения организма — это важнее
        if lowq in ("привет", "привет!", "здравствуй", "здравствуйте",
                    "здорово", "добрый день", "добрый вечер", "доброй ночи",
                    "салют", "ку"):
            from core import greet as _greet
            from core.dialog import DialogStore as _DS
            try:
                _dialog = _DS()
            except Exception:
                _dialog = None
            return Reply(_greet.greeting_text(dialog=_dialog),
                         "python", "greet")

        # Ф4 «что нового» (23.11): дайджест жизни дома за отсутствие —
        # мысли, сны, новые воспоминания, открытые вопросы; каждый
        # орган в своей броне, тишина — тоже честный ответ
        if lowq in ("что нового", "что случилось", "что было",
                    "что было пока меня нет", "расскажи новости"):
            from core import digest as _digest
            from core.dialog import DialogStore as _DS
            try:
                _dialog = _DS()
            except Exception:
                _dialog = None
            return Reply(_digest.what_is_new(dialog=_dialog,
                                             memory=self.memory),
                         "python", "digest")

        # 22.11 (ночь, урок прогона): «проверь ещё раз модуль, он появился» —
        # проверка камеры это ЭКСПЕРИМЕНТ (импорт → сенсор → кадр),
        # а не воспоминание мозга «всё ещё недоступна». startswith — хвост
        # «он появился» и «?» не должны ронять команду в мозг.
        if (low.startswith("проверь камер") or low.startswith("проверь веб-камер")
                or low.startswith("проверь модуль камер")
                or low.startswith("проверь еще раз модуль")
                or low.startswith("проверь ещё раз модуль")
                or low.startswith("камера работает")
                or low.startswith("камера жива")):
            return Reply(eyes.camera_selftest(), "python", "camera_selftest")

        # Г-2, глаза дома: дескриптор экрана от сенсора 8083, мозг молчит.
        # Граница слова обязательна: «посмотрим» — не команда глазам.
        # v2 (22.11): «что ты видишь» — тоже команда — так спрашивает
        # Создатель, и ответ должен прийти сразу, а не «дай команду посмотри».
        if (lowq in ("что на экране", "опиши экран") or lowq == "посмотри"
                or low.startswith("посмотри ") or low.startswith("посмотри,")
                or low.startswith("что ты видишь") or low.startswith("что видишь")):
            return Reply(eyes.describe_text(), "python", "eyes")

        # №3 «что изменилось» (роадмап 30): пиксельная сверка с последним
        # взглядом — земная истина без сенсора и без мозга (урок v1.5).
        # Эталон — кадр любого взгляда: «посмотри», «найди», дескриптор рук
        if lowq in ("что изменилось", "что изменилось на экране",
                    "что поменялось", "что поменялось на экране"):
            return Reply(eyes.whats_changed_text(), "python", "changed")

        # №4 «запомни экран» (роадмап 30): снимок + описание в
        # data\screenshots\ + строка в память — экран становится
        # воспоминанием, «вспомни экран» его найдёт
        if lowq in ("запомни экран", "запомни этот экран", "сохрани экран"):
            return Reply(eyes.save_snapshot(memory=self.memory),
                         "python", "screen_shot")

        # РУКИ v2.2 «скриншот» (23.11, вечер-3 — урок живого лога): Создатель
        # просил «сделай скриншот» — мозг пять раз поручал это РУКАМ
        # (ui_action), руки не умеют смотреть, и чат тонул в шпаргалке
        # формата. Снимок экрана — работа ГЛАЗ (№4 «запомни экран» — тот же
        # орган, один кадр = одна правда): «скриншот» — команда дома,
        # с хвостами «прямо сейчас/пожалуйста» — всё ещё она
        if re.match(r"^(?:сделай\s+|сними\s+|сфоткай\s+|сфотографируй\s+)?"
                    r"скриншот(?:\s+экрана)?"
                    r"(?:\s+(?:прямо\s+сейчас|сейчас|пожалуйста|быстро))?$",
                    lowq):
            return Reply(eyes.save_snapshot(memory=self.memory),
                         "python", "screen_shot")

        # ПАМЯТЬ v2: «запомни: <факт>» — общий случай. Специфические ветки
        # («запомни меня», «запомни, как я выгляжу», «запомни экран»)
        # разобраны выше и сюда не доходят — до них очередь доходит только
        # с чем-то новым: «запомни, что завтра созвон» — память, не мозг.
        # Граница слова обязательна: «запомнится» — не команда
        m = re.match(r"^запомни(?![а-яё])[\s:,;—-]*(.*)$", t, re.IGNORECASE)
        if m:
            payload = m.group(1).strip().strip('«»"\'').strip()
            if not payload:
                return Reply("что запомнить? скажи «запомни: <текст>»",
                             "python", "remember")
            self.memory.remember(payload)
            return Reply("запомнила: " + payload, "python", "remember")

        # №6 «глаза как контекст мозга» (Г-3): резолюция Создателя —
        # как моторика и живой язык, одной фразой. Мозг начинает
        # видеть экран через строку состояния (кэш TTL 5 мин)
        if lowq in ("следи за экраном", "смотри за экраном",
                    "следи за экран"):
            return Reply(eyes.set_watch(True), "python", "screen_watch")
        if lowq in ("не следи за экраном", "хватит следить за экраном",
                    "не следи за экран", "перестань следить за экраном"):
            return Reply(eyes.set_watch(False), "python", "screen_watch")

        # №18 «запиши в буфер» (роадмап 30 + закрытие Р-4): текст в
        # clipboard — только по прямой команде; кириллица теперь
        # печатается руками ИМЕННО через буфер и ctrl+v
        m = re.match(r"^(?:в\s+буфер|запиши\s+в\s+буфер|скопируй\s+в\s+буфер|"
                     r"скопируй)\s*[:;,—-]?\s*(.+?)\s*[?.!…]*$", t, re.IGNORECASE)
        if m:
            from core import hands as _hands
            payload = m.group(1).strip()
            try:
                return Reply(_hands.clipboard_write(payload),
                             "python", "clipboard")
            except PermissionError as e:
                return Reply("СТРАЖ отказал: " + str(e),
                             "python", "clipboard")
            except Exception as e:
                return Reply("буфер не принял: " + str(e) +
                             " — скажи «проверь модуль pyperclip», аптечка "
                             "поставит сама", "python", "clipboard")

        # №29 «доклад архитектора» (роадмап 30, architect_oncall v2):
        # еженедельный аудит дома — тесты, коммиты, диск, дрейф канона;
        # каждый источник в своей броне, упавший — честная строка
        if lowq in ("доклад архитектора", "аудит недели", "доклад архитектору"):
            import architect_oncall
            try:
                return Reply(architect_oncall.weekly_report(),
                             "python", "architect_weekly")
            except Exception as e:
                return Reply("доклад не собрался: %s — расскажи "
                             "архитектору" % e, "python", "architect_weekly")

        # №27 «тихий час» (роадмап 30): «тишина» — лог панели режется
        # до ошибок (каждый опрос эфира печатал строку в консоль);
        # «не тишина» возвращает. Резолюция переживает рестарт панели
        if lowq in ("тишина", "тихий час", "замолчи лог"):
            from core import quiet
            return Reply(quiet.set_quiet(True), "python", "quiet")
        if lowq in ("не тишина", "громко", "можно говорить",
                    "отмени тишину", "хватит молчать"):
            from core import quiet
            return Reply(quiet.set_quiet(False), "python", "quiet")

        # №24 «логбук» (роадмап 30): CHANGELOG.md из истории git —
        # первая строка каждого коммита и есть выжимка фичи
        if lowq in ("логбук", "обнови логбук", "changelog", "журнал фишек"):
            from evolution.changelog import commits_note, write_changelog
            try:
                rep = write_changelog()
                return Reply("Логбук собран: %s за %d дней — CHANGELOG.md "
                             "в корне дома. Первая строка каждого коммита "
                             "и есть история фичи"
                             % (commits_note(rep), rep["days"]),
                             "python", "changelog")
            except Exception as e:
                return Reply("логбук не собрался: %s — расскажи "
                             "архитектору" % e, "python", "changelog")

        # №2 «найди на экране» (роадмап 30): поиск элемента по описанию —
        # лестница зон с апскейлом; ответ: надпись, центр экрана, рамка.
        # Мозг молчит: координаты даёт сенсор, а не мудрость 30B
        m = re.match(r"^(?:найди|поищи|где)\s+на\s+экране\s*[:;,—-]?\s*(.+?)\s*[?.!…]*$",
                     t, re.IGNORECASE)
        if m:
            return Reply(eyes.find_on_screen(m.group(1).strip()),
                         "python", "find")
        if re.match(r"^(?:найди|поищи|где)\s+на\s+экране$", lowq):
            return Reply("что найти? скажи «найди на экране <надпись>»",
                         "python", "find")

        # Круг Р v2 (22.11, «единое зрение»): руки — исполнитель
        # координат ГЛАЗ, своей модели у них нет, сервер зрения они
        # не занимают (мастер-ТЗ §4: хозяин VRAM — глаза). Глагол
        # («нажми X» / «напечатай Y») разбирают сами руки — поэтому
        # задание уходит им ЦЕЛИКОМ; мозг молчит, каждое действие
        # всё равно идёт через СТРАЖА, моторика — только по резолюции
        # Создателя (кнопка 91), без неё — сухой режим.
        #
        # 23.11, урок живого лога («Руки проверить работу микрофона» —
        # формат-ошибка, и на «что у тебя за руки» — тоже): живой язык
        # — НЕ работа рук. Неизвестный глагол больше не бьёт в стену
        # формата: задание уходит МОЗГУ, он решает, как исполнить
        # (или отвечает по существу). Глядящие задания («руки посмотри»)
        # всё равно ловит честный редирект рук на глаза. «руки» без
        # задания и «что умеют руки» — дружелюбная шпаргалка, не SOS.
        if lowq in ("руки", "руки помощь", "руки, помощь",
                    "что умеют руки", "руки что умеют",
                    "руки, что ты умеешь", "что ты можешь руками"):
            from core import motor
            return Reply(motor.help_text(), "python", "hands_help")
        for _prefix in ("руки", "кликни", "нажми", "напечатай", "прокрути"):
            if low.startswith(_prefix):
                from core import motor
                if "экзамен" in low:
                    return Reply(motor.exam(), "python", "hands_exam")
                plan = motor.parse_task(t)
                if plan["verb"] == "unknown":
                    if any(mark in low for mark in motor._LOOKING_MARKS):
                        return Reply(motor.run(t), "python", "hands")
                    # живой язык — думает мозг, руки не притворяются
                    # глухим форматом; fall-through в мозговой трек
                    break
                return Reply(motor.run(t), "python", "hands")

        # САМОЛЕЧЕНИЕ v1 (ТЗ_Самолечение_v1, 22.11): кодер-слуга пишет
        # патчи в ПЕСОЧНИЦУ data\patches — применение за Создателем.
        # «Марфа сама себя лечит»: мозг (или Создатель) ставит требование,
        # кодер-7B печатает код, страж проверяет, Создатель применяет.
        if lowq in ("патчи", "список патчей"):
            from core import repair
            return Reply(repair.list_patches(), "python", "patches")
        m = re.match(r"^примени\s+патч\s+(\d+)$", lowq)
        if m:
            from core import repair
            return Reply(repair.apply_patch(int(m.group(1))),
                         "python", "patch_apply")
        m = re.match(r"^откати\s+патч\s+(\d+)$", lowq)
        if m:
            from core import repair
            return Reply(repair.rollback_patch(int(m.group(1))),
                         "python", "patch_rollback")

        # Ф75 «СВОБОДА ВНЕДРЯТЬ СЕБЯ» (директива Создателя 22.11: «дай
        # Марфе свободу, чтоб она могла уже сама писать и внедрять себя —
        # она умная модель, у неё прокачанные руки, она понимает, что
        # делает»). Резолюция — как моторика и живой язык: одна фраза
        # Создателя включает, одна выключает; воля живёт в data/, не
        # в коде. Внедрение — с бронёй: бэкап, дым-тест, автоОткат.
        if lowq in ("разреши внедрять себя", "разрешаю внедрять себя"):
            from core import repair
            return Reply(repair.allow_self_write(), "python", "self_write")
        if lowq in ("запрети внедрять себя", "запрещаю внедрять себя"):
            from core import repair
            return Reply(repair.forbid_self_write(), "python", "self_write")
        m = re.match(r"^внедри\s+патч\s+(\d+)$", lowq)
        if m:
            from core import repair
            return Reply(repair.self_apply(int(m.group(1))),
                         "python", "self_apply")

        if low.startswith("почини") or low.startswith("ремонт "):
            rest = t[len("почини"):] if low.startswith("почини") \
                else t[len("ремонт"):]
            rest = rest.strip().lstrip(",;:! ")
            # «почини <файл>: <что сделать>»; двоеточие диска (C:\...) —
            # не разделитель
            idx = rest.find(":")
            if idx == 1 and len(rest) > 2 and rest[2:3] in "\\/":
                idx = rest.find(":", 3)
            if idx < 0:
                idx = rest.find(" — ")
                if idx < 0:
                    path_part, req = rest, ""
                else:
                    path_part, req = rest[:idx], rest[idx + 3:]
            else:
                path_part, req = rest[:idx], rest[idx + 1:]
            from core import repair
            return Reply(repair.make_patch(path_part.strip(), req.strip()),
                         "python", "repair")

        # Г-2.3, самопознание: «изучи себя» — честный динамический отчёт
        # без будоража мозга. Мозг-30B о своих командах и файлах дома
        # знает меньше, чем дом, — тут говорит сам дом.
        if lowq in ("изучи себя", "расскажи о себе", "кто ты", "что ты такое",
                   "что ты умеешь", "что умеешь", "твои возможности"):
            return Reply(identity.capabilities_report(memory=self.memory),
                         "python", "self_inspect")

        # Ф74 + фишка аудита-2: задача в очередь одной фразой — «задача: проверить
        # микрофон». План дня пересобирается (force): новая задача видна
        # СЕГОДНЯ, а не завтра (M4). Двоеточие/тире обязательны — «задача была
        # в том…» остаётся обычной речью для мозга.
        m = re.match(r"^задача\s*[:—-]\s*(.+)$", t) \
            or re.match(r"^добавь задачу\s*[:—-]?\s*(.+)$", t)
        if m:
            from core.autonomy import DayPlanner, add_task, load_queue
            title = m.group(1).strip()[:200]
            task = add_task(title)
            planner = DayPlanner()
            rebuilt = False
            if planner.load_plan(dt.date.today()) is not None:
                planner.build_plan(force=True)
                rebuilt = True
            note = ("План дня пересобрала — она уже в нём."
                    if rebuilt else
                    "Войдёт в план дня в 08:00.")
            return Reply("В очередь: «%s» (приоритет %s). %s"
                         % (task["title"], task["priority"], note),
                         "python", "add_task")

        return None

    # ---------- системный контекст мозгового трека ----------

    def _system_extra(self, user_text: str) -> str:
        """Системный контекст мозгового трека — ЧЕРЕЗ Ф51 (H8 аудита раунда 2).

        Раньше промпт собирался руками: идентичность + манифест + закон
        скорости + доктрина + состояние + RAG — без бюджета и обрезки;
        PROMPT_BUDGET_TOKENS=3072 был фикцией (context.build_system не звал
        никто, кроме тестов). Теперь порядок тот же (статичное ядро —
        первым, KV-кэш цел), но бюджет — ЗАКОН: RAG режется с конца,
        переполнение — ЧП с уроком архитектору, а не молчаливый вылет
        за контекст 4096.
        """
        core = IDENTITY + "\n\n" + identity.manifest() + "\n\n" + SPEED_LAW \
            + "\n\n" + TONE_LAW
        state = _house_state()
        rag: list[str] = []
        if self.memory is not None:
            try:
                found = self.memory.recall(user_text, top_k=3)
            except Exception:
                found = []
            rag = [str(r.get("text", "")) for r in found
                   if isinstance(r, dict) and r.get("text")]
        try:
            prompt, rep = context.build_system(
                doctrine=self.doctrine, state_text=state, genome_rules=[],
                rag_memories=rag, core=core)
        except ValueError as e:
            _lesson("контекст-чп", str(e))
            # ЧП дома не должно молча ронять чат: ядро и доктрина нерушимы,
            # жертвуем состоянием и воспоминаниями — и честно говорим архитектору
            prompt, rep = context.build_system(
                doctrine=self.doctrine, state_text="", genome_rules=[],
                rag_memories=[], core=core)
        for d in rep.dropped:
            _lesson("контекст-обрезан", d)   # что не влезло — видно архитектору
        return prompt

    # ---------- действия мозга через РУКИ (надзор СТРАЖА) ----------

    def _usage_meta(self) -> Optional[dict]:
        """Штамп хода из usage мозга: «N ток · промпт M». УРОК 23.11
        (ночь): штамп ставился ТОЛЬКО на пути ответа — ходы, ушедшие в
        инструмент, приходили без счётчика, и по живому логу было не
        понять, был ли у мозга ответ (Создатель искал пропавший текст
        «179 ток»). Теперь счёт честен на обоих путях."""
        usage = getattr(self.brain, "last_usage", None)
        if not isinstance(usage, dict):
            return None
        meta: dict = {}
        try:
            tok = int(usage.get("completion_tokens") or 0) or None
            if tok:
                meta["tok"] = tok
        except (TypeError, ValueError):
            pass
        try:
            ptok = int(usage.get("prompt_tokens") or 0) or None
            if ptok:
                meta["ptok"] = ptok
        except (TypeError, ValueError):
            pass
        return meta or None

    def _act(self, action: dict) -> Reply:
        tool = str(action.get("tool") or "")
        # Раунд 3, №5: мозг иногда присылает args строкой/списком/числом
        # — это брак формата, а не повод ронять дом: лечится на месте,
        # урок летит архитектору. Поля-не-строки ко версятся честно:
        # path: 123 → СТРАЖ откажет по-своему, без TypeError в панели.
        args = action.get("args")
        if not isinstance(args, dict):
            if args:
                _lesson("инструмент-аргументы", "%s: args не словарь: %r"
                        % (tool, args))
            args = {}

        def _s(key: str) -> str:
            v = args.get(key)
            if isinstance(v, str):
                return v
            return "" if v is None else str(v)

        try:
            if tool == "write_file":
                return Reply(hands.write_file(_s("path"), _s("content")),
                             "brain", "write_file")
            if tool == "read_file":
                return Reply(hands.read_file(_s("path")),
                             "brain", "read_file")
            if tool == "run_python":
                # Ф5 «сырые числа по-человечески» (23.11): вывод инструмента
                # остаётся целиком, но крупные голые числа получают
                # расшифровку с честной оговоркой «если это байты» —
                # урок лога: [68621991936, ...] без перевода — не ответ
                from core import humanize as _humanize
                return Reply(_humanize.humanize_numbers(
                    hands.run_python(_s("code"))), "brain", "run_python")
            if tool == "browser_search":
                return Reply(hands.browser_search(_s("query")),
                             "brain", "browser_search")
            if tool == "check_brackets":
                return Reply(hands.check_brackets(_s("text")),
                             "brain", "check_brackets")
            if tool == "ui_action":
                # Доктрина ТЗ_Руки_v2: мозг не жмёт кнопки — он ДОВЕРЯЕТ
                # задание рукам. Координаты мозг никогда не называет: их
                # дают глаза дескриптором, руки берут центр бокса,
                # страж проверяет.
                #
                # РУКИ v2.2 «диагноз до запуска» (23.11, вечер-3 — урок
                # живого лога): мозг поручал рукам пустоту и
                # задания-рассказы — чат пять раз получал механическую
                # шпаргалку «руки ждут задание…» вместо ответа Марфы,
                # разговор ходил по кругу. Задание не по формату рук —
                # Марфа говорит САМА: признаёт промах формулировки
                # (урок Создателя: «описание действия — не действие»)
                # и называет формат. Глядящие задания («руки посмотри»)
                # идут прежним честным редиректом в motor.run
                from core import motor
                task = _s("task")
                if not any(mark in task.lower()
                           for mark in motor._LOOKING_MARKS):
                    plan = motor.parse_task(task)
                    if plan["verb"] in ("empty", "unknown"):
                        _lesson("руки-не-по-формату",
                                "мозг поручил: %r" % task[:120])
                        shown = task.strip(",;:.! ") or "(пустое задание)"
                        return Reply(
                            "Я сформулировала задание рукам не по их "
                            "формату («%s») — они его не поняли, и это "
                            "мой промах, не ихний. Руки понимают только "
                            "четыре глагола в начале: «нажми <надпись>», "
                            "«напечатай <текст>», «клавиши <ctrl+c>», "
                            "«прокрути вниз/вверх». Скажи задание этими "
                            "словами — или опиши своими, я попробую "
                            "иначе. Смотреть — не работа рук: снимок "
                            "экрана делает команда «скриншот», разглядеть "
                            "— «посмотри»" % shown,
                            "brain", "ui_action")
                return Reply(motor.run(task), "brain", "ui_action")
            if tool == "code_patch":
                # Доктрина ТЗ_Самолечение_v1: мозг не чинит файлы сам —
                # он ДОВЕРЯЕТ требование кодеру-слуге. Патч ложится в
                # песочницу; внедряет Создатель («примени патч №») или
                # сама Марфа («внедри патч №», Ф75) — «уже починила»
                # можно говорить только после внедрения.
                from core import repair
                return Reply(repair.make_patch(_s("path"), _s("requirement")),
                             "brain", "code_patch")
            if tool == "apply_patch":
                # Ф75 «свобода внедрять себя»: мозг доверяет ДОМОУ самому
                # внедрить готовый патч — с резолюцией Создателя, бэкапом,
                # дым-тестом и автоОткатом (core/repair.self_apply)
                from core import repair
                raw = args.get("patch", args.get("n"))
                try:
                    n = int(str(raw).strip())
                except (TypeError, ValueError):
                    return Reply("внедрить какой патч? скажи номер — "
                                 "«патчи» покажет список", "brain", "apply_patch")
                return Reply(repair.self_apply(n), "brain", "apply_patch")
            _lesson("неизвестный-инструмент", "мозг позвал «%s»" % tool)
            return Reply("неизвестный инструмент: " + tool +
                         ". Мои инструменты (только эти имена): " +
                         identity.tool_names() +
                         " — позови существующий", "brain", tool or None)
        except PermissionError as e:
            _lesson("страж-отказ", "%s: %s" % (tool, e))
            return Reply("СТРАЖ отказал: " + str(e), "brain", tool or None)
        except Exception as e:
            # Броня инструментов (K3/M1 аудита): ANY-краш руки не должен
            # долетать до панели 500-й — Создатель видит честный отказ,
            # урок летит архитектору
            _lesson("инструмент-упал", "%s: %s: %s" % (tool, type(e).__name__, e))
            return Reply("инструмент %s споткнулся: %s — расскажи архитектору"
                         % (tool or "?", e), "brain", tool or None)

    # ---------- главная точка ----------

    def handle(self, user_text: str, reply_to=None,
               history: Optional[list] = None) -> Reply:
        """Главная точка дома. №10: history — прошлые ходы разговора
        (DialogStore.render_messages), мозг видит диалог целиком.

        Ф10 (23.11): будильник дома — любая реплика Создателя выносит
        назвонившие напоминания ПЕРВОЙ строкой ответа (у панели нет
        канала «постучать первой», и мы не притворяемся; напоминание
        честно ждёт в чате). Упавший будильник не роняет чат.
        """
        reply = self._dispatch(user_text, reply_to, history)
        try:
            from core import reminders
            note = reminders.due_note()
            if note:
                reply.text = note + "\n\n" + reply.text
        except Exception as e:
            _lesson("орган-упал", "будильник: %s: %s" % (type(e).__name__, e))
        return reply

    def _dispatch(self, user_text: str, reply_to=None,
                  history: Optional[list] = None) -> Reply:
        """Прежняя главная точка: калитка → пробуждение → рефлексы → мозг."""
        # Раунд 3, №6: калитка Создателя — тоже код, и она может споткнуться
        # (нет .env, битый конфиг). Безопасность важнее, но исключение из
        # калитки не должно убивать весь чат: урок — архитектору, ход — дальше
        try:
            hit, gate_reply = creator_gate.check(user_text)
        except Exception as e:
            _lesson("калитка-сбой", "%s: %s" % (type(e).__name__, e))
            hit, gate_reply = False, None
        if hit:
            return Reply(gate_reply, "python", "creator_gate")
        # СОН (23.11): слово Создателя будит организм — как прикосновение.
        # Рефлексы (быстрые команды) работают и в сонном окне; разговор —
        # пробуждение. Броня: упавший орган сна не роняет чат — организм
        # просто считается проснувшимся
        try:
            sleep.wake_on_message()
        except Exception:
            pass
        # Раунд 3, №4: быстрые команды зовут сенсоры, доктора, библиотекаря,
        # память и руки — любой из них может упасть. Крах быстрой команды
        # не должен ронять чат: урок летит архитектору, ответ говорит мозг
        # (медленнее, но живо) — так же, как «вычисли» прозрачно падает в мозг
        try:
            fast = self._fast(user_text)
        except Exception as e:
            _lesson("быстрая-упала", "%s: %s" % (type(e).__name__, e))
            fast = None
        if fast is not None:
            return fast
        # эфир: быстрые команды мгновенны, а вот мозговой трек — долгий;
        # чат обязан видеть, ЧТО происходит, пока он идёт (не молчать)
        progress.stage("собираю контекст: доктрина, воспоминания, состояние дома…")
        try:
            system_extra = self._system_extra(user_text)
        except ValueError as e:
            # Закон контекста (H8 раунда 2): ядро+доктрина не влезают в
            # бюджет — это ЗАКОН дома, а не сбой сенсора. Доктрина нерушима:
            # отвечать без неё мозг не будет, честный отказ + зов архитектору
            _lesson("контекст-чп", str(e))
            return Reply("промпт не влез в закон дома (%d ток) — скажи "
                         "архитектору, вот что вышло: %s"
                         % (config.PROMPT_BUDGET_TOKENS, e), "fallback", None)
        except Exception as e:
            # Раунд 3, №10: прочий крах контекста (сенсор, RAG, клиент) —
            # не крах хода и не «мозг недоступен». Статичное ядро
            # (личность + манифест + закон скорости) упасть не может —
            # на нём и едем; без состояния и воспоминаний, зато честно
            # и с уроком архитектору
            _lesson("контекст-сбой", "%s: %s" % (type(e).__name__, e))
            system_extra = IDENTITY + "\n\n" + identity.manifest() \
                + "\n\n" + SPEED_LAW + "\n\n" + TONE_LAW
        progress.stage("мозг думает — кратко и по делу, ответ напечатается живьём…")
        # МОЗГ v3 «АНТИ-ЭХО»: пустой ответ и дословный повтор прошлого
        # переспрашиваются ОДИН раз с уколом; эхо и после укола — честное
        # признание, а не выдача повтора за ответ (урок живого лога 23.11)
        last_assistant = _last_assistant_text(history)
        decision = None
        ans: str = ""
        nudge = ""
        for _attempt in (1, 2):
            try:
                decision = self.brain.ask_json(
                    user_text + nudge, system_extra=system_extra,
                    history=history,
                    max_tokens=config.BRAIN_ANSWER_TOKENS,
                    on_text=progress.preview)
            except Exception as e:
                _lesson("мозг-недоступен", str(e))
                # Урок переписки 22.11: голое «timed out» Создатель читает как
                # поломку. Чаще это медленный Pascal-мозг, честно думающий
                # над длинным ответом, — говорим это человеческим языком.
                # Урок дня-8 (23.11): «WinError 10061» — вторая болезнь:
                # сервер мозга НЕ СЛУШАЕТ порт (выключен/грузится/команда
                # старта отвергнута) — лечение другое, и оно в подсказке.
                note = ""
                if "timed out" in str(e).lower():
                    note = (" — думал дольше %d сек и не успел. Это не поломка: "
                            "мозг честно работает, просто медленно. Спроси "
                            "покороче или повтори через минуту"
                            % config.BRAIN_TIMEOUT_SEC)
                elif is_refusal(str(e)):
                    note = (" — сервер мозга не отвечает на порту (соединение "
                            "отклонено): мозг выключен, грузится или его команду "
                            "старта отвергла сборка. Лечение: кнопка "
                            "scripts\\92_brain_fix.bat — чинит команду и поднимает "
                            "мозг; живость покажет карточка «Мозг» на панели")
                return Reply("мозг недоступен: " + str(e) + note, "fallback", None)
            if isinstance(decision, dict) and isinstance(decision.get("action"), dict):
                # МАРШРУТ ДЕЙСТВИЯ v2 «ответ не выбрасываем» (23.11, ночь —
                # техническая мысль Создателя: «она пишет ответ, но в чат
                # приходит эхо вызова — возможно, нормальный ответ не
                # дошёл»). Прежний маршрут молча выбрасывал answer, если
                # мозг дал ответ И действие вместе: Создатель видел
                # только результат инструмента. Теперь — ОБА: сначала
                # слова Марфы, потом сделанное. Штамп токенов — тоже на
                # этом пути: счёт честен, генерация была
                raw_ans = decision.get("answer")
                pre = ("" if raw_ans is None else
                       (raw_ans if isinstance(raw_ans, str) else str(raw_ans))).strip()
                acted = self._act(decision["action"])
                if pre:
                    acted.text = pre + "\n\n" + acted.text
                meta = self._usage_meta()
                if meta:
                    acted.meta = meta
                return acted
            if isinstance(decision, dict):
                raw_ans = decision.get("answer")
                ans = "" if raw_ans is None else (
                    raw_ans if isinstance(raw_ans, str) else str(raw_ans))
                if not ans.strip() and _attempt == 1:
                    _lesson("мозг-пустой-ответ", user_text[:120])
                    nudge = _NUDGE_EMPTY
                    continue
                if _is_echo(ans, last_assistant) and _attempt == 1:
                    _lesson("мозг-зацикливание", user_text[:120])
                    nudge = _NUDGE_ECHO
                    continue
            break
        if isinstance(decision, dict):
            # СКОРОСТЬ v1: штамп несёт и токены — «40,2 с · мозг · 84 ток»;
            # снова две минуты? по токенам сразу видно, кто съел время.
            # Фишка аудита-2: и ПРОМПТ-тоже — «165,8 с · мозг · 273 ток
            # · промпт 2100»: большой промпт = долгий префикс, диагноз
            # виден без консоли (штамп 22.11: 165,8 с при 273 ток — это
            # промпт так думал, а не декод разошёлся)
            usage = getattr(self.brain, "last_usage", None)
            tok = None
            ptok = None
            if isinstance(usage, dict):
                try:
                    tok = int(usage.get("completion_tokens") or 0) or None
                except (TypeError, ValueError):
                    tok = None
                try:
                    ptok = int(usage.get("prompt_tokens") or 0) or None
                except (TypeError, ValueError):
                    ptok = None
            meta: dict = {}
            if tok:
                meta["tok"] = tok
            if ptok:
                meta["ptok"] = ptok
            # Раунд 3, №9 лечится честностью дважды: пустой ответ после
            # ретрая — честный сбой с путём лечения («хвост brain пустой
            # ответ»), эхо после укола — признание («Я зациклилась»),
            # которому Создатель сам учил в живом разговоре 23.11
            if not ans.strip():
                return Reply("мозг вернулся с пустым ответом дважды — это сбой, "
                             "а не пауза. Скажи «хвост brain пустой ответ» — "
                             "покажу лог, или повтори ход", "brain", None,
                             meta=meta or None)
            if _is_echo(ans, last_assistant):
                return Reply("Я зациклилась и повторила прошлый ответ. "
                             "Скажи «ответь иначе» — и я попробую заново.",
                             "brain", None, meta=meta or None)
            return Reply(ans, "brain", None, meta=meta or None)
        return Reply(str(decision), "brain", None)
