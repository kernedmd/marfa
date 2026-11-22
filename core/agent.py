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
"""
from __future__ import annotations

import ast
import json
import operator as _op
import re
import time
from pathlib import Path
from typing import Optional

from core import config, creator_gate, diary, eyes, hands, identity, progress
from core.brain import BrainClient
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
    "- Моё тело: мозг Qwen3-30B (думаю и говорю), глаза Qwen2.5-VL (вижу экран "
    "по команде «посмотри» и «что ты видишь»; веб-камера — «посмотри на меня»), "
    "уши vosk (сторож имени: слышу, когда меня зовут), руки — моторная кора "
    "на координатах глаз (единое зрение: глаза читают экран и дают боксы, "
    "руки кликают по центру под стражем, если Создатель включил моторику). "
    "Голоса пока нет — отвечаю текстом. Подробный честный отчёт о себе — "
    "команда «изучи себя».\n"
    "- Язык дома — русский. Отвечаю по-русски, без языковой каши.\n"
    "- Честность важнее уверенности: не знаю — говорю «не знаю». Цифры или ничего."
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
    """Ответ дома: текст, откуда пришло (python/brain/fallback), каким инструментом."""

    def __init__(self, text: str, source: str = "python",
                 tool_used: Optional[str] = None) -> None:
        self.text = text
        self.source = source
        self.tool_used = tool_used


# ---------------------------------------------------------------
# Безопасная арифметика: AST, только числа и операции
# ---------------------------------------------------------------
_OPS = {
    ast.Add: _op.add, ast.Sub: _op.sub, ast.Mult: _op.mul, ast.Div: _op.truediv,
    ast.Mod: _op.mod, ast.Pow: _op.pow, ast.FloorDiv: _op.floordiv,
    ast.USub: _op.neg, ast.UAdd: _op.pos,
}


def _safe_math(expr: str):
    """Вычислить арифметическое выражение. Не арифметика → None (идём к мозгу)."""
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError:
        return None

    def ev(node):
        if isinstance(node, ast.Expression):
            return ev(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
            return _OPS[type(node.op)](ev(node.left), ev(node.right))
        if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
            return _OPS[type(node.op)](ev(node.operand))
        raise ValueError("не арифметика")

    try:
        return ev(tree)
    except Exception:
        return None


def _fmt_num(x) -> str:
    if isinstance(x, float) and x.is_integer():
        return str(int(x))
    return str(x)


def _house_state() -> str:
    """Лёгкое состояние дома для промпта (тяжёлый осмотр — marfa_status.py).
    Г-2.1: сюда же — глаза. Мозг читает этот текст в каждом сообщении
    и ЗНАЕТ, что у дома есть зрение и как им пользоваться.
    22.11 (ночь): сюда же — камера. Урок живого прогона: на «а сейчас?»
    мозг ответил про камеру ПО ПАМЯТИ («всё ещё недоступна») уже после
    установки opencv. Свежий факт в состоянии дома — мозгу не нужно
    выдумывать."""
    eyes_note = (
        "глаза: сенсор зрения " + str(config.PORT_EYES) + " жив, команда «посмотри» — опишу экран"
        if eyes.health_cached()
        else "глаза: сенсор %d не запущен (зрения сейчас нет)" % config.PORT_EYES)
    # v2: уши называют ПРИЧИНУ — «микрофон не найден», «модель ушей нет»,
    # «служба не запущена» — а не отговорку «молчит или микрофона нет»
    ears_note = "уши: " + identity.ears_diagnosis()
    # камера: факт из живого процесса (кэш), не воспоминание мозга
    cam_note = ("камера: модуль есть — «посмотри в камеру»; живой тест — "
                "«проверь камеру»" if eyes.camera_module_ok()
                else "камера: нет модуля opencv (venv\\Scripts\\pip install "
                "opencv-python); после установки — «проверь камеру»")
    from core.uptime import started_hhmm
    return (
        "Состояние дома: мозг " + config.BRAIN_MODEL_NAME + " на " + config.BRAIN_URL +
        ", панель " + str(config.PORT_WEB) +
        ", контекст " + str(config.CONTEXT_TOKENS) +
        ", квант " + config.DEFAULT_QUANT +
        ", RAM-бюджет " + str(config.RAM_BUDGET_GB) + " ГБ; " + eyes_note +
        "; " + cam_note +
        "; " + ears_note +
        "; я не сплю с " + started_hhmm()
    )


class Agent:
    """Диспетчер: быстрые команды — 0 сек на Python, остальное — мозг 30B."""

    def __init__(self, brain=None, memory=None, doctrine=None) -> None:
        self.brain = brain or BrainClient()
        self.memory = memory or Memory()
        self.doctrine = doctrine if doctrine is not None else load_doctrine()

    # ---------- быстрые команды (мозг молчит) ----------

    def _fast(self, text: str) -> Optional[Reply]:
        t = text.strip()
        low = t.lower()

        if low in ("время", "который час", "сколько времени"):
            return Reply("Сейчас " + time.strftime("%H:%M:%S") +
                         ", " + time.strftime("%d.%m.%Y"), "python", "time")

        if low == "статус" or low.startswith("статус дома"):
            return Reply(_house_state(), "python", "status")

        if low.startswith("скобки"):
            target = t[len("скобки"):].strip() or t
            return Reply(hands.check_brackets(target), "python", "check_brackets")

        if low.startswith("вычисли"):
            expr = t[len("вычисли"):].strip()
            val = _safe_math(expr)
            if val is not None:
                return Reply(_fmt_num(val), "python", "calc")
            # не арифметика → прозрачно падаем в мозговой трек

        if low.startswith("помни"):
            payload = t[len("помни"):].strip()
            if payload:
                self.memory.remember(payload)
                return Reply("запомнила: " + payload, "python", "remember")

        if low.startswith("вспомни"):
            query = t[len("вспомни"):].strip()
            if query:
                found = self.memory.recall(query, top_k=3)
                if found:
                    lines = "\n".join("- " + r["text"] for r in found)
                    return Reply("Вот что помню:\n" + lines, "python", "recall")
                return Reply("пока ничего не вспомнила по этому", "python", "recall")

        # №8: вечерний дневник. Гейт §5 (вердикт батареи 21.11.2026):
        # есть резолюция Создателя — Марфа пишет «Живой рассказ» сама,
        # по механическим фактам и с фиксом сэмплинга Qwen3.
        if low in ("подведи день", "подвести день", "дневник"):
            try:
                text = diary.Diary().build_day(
                    brain=self.brain if hasattr(self.brain, "chat") else None)
            except Exception as e:
                return Reply("дневник не собрался: " + str(e), "python", "diary")
            return Reply("Вот дневник за сегодня:\n\n" + text, "python", "diary")

        # Гейт §5, рефлексия: Марфа читает свои дневники и думает.
        # Без резолюции честно говорит, чем включается.
        if low in ("поразмышляй", "размышляй", "о чём думаешь", "о чем думаешь"):
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
        if low in ("сохрани себя", "бэкап", "backup"):
            from core import backup as _backup
            try:
                report = _backup.create_backup()
            except Exception as e:
                return Reply("бэкап не собрался: " + str(e),
                             "python", "backup")
            return Reply(_backup.render(report), "python", "backup")

        # №25 uptime: сколько панель не спит (мозг старше — его часы
        # в его консоли, тут честно про моё бодрствование)
        if low in ("сколько ты не спала", "ты не спала", "uptime"):
            from core.uptime import uptime_text
            return Reply(uptime_text(), "python", "uptime")

        # №21 доктор: осмотр дома текстом — без мозга и без лечения.
        # Лечение — у кнопки 84 (с подтверждением) и автодоктора
        # (слуга, мёртвый два осмотра подряд, поднимается сам).
        if low in ("доктор", "осмотри дом", "осмотр"):
            from core import doctor as _doctor
            return Reply(_doctor.render(_doctor.check_all()),
                         "python", "doctor")

        # Круг Д: библиотекарь — Марфа читает дом (механика, без LLM)
        if low in ("почитай", "прочитай", "что почитать"):
            from core.librarian import Librarian
            report = Librarian().read_one()
            if not report:
                return Reply("вся полка прочитана — нового ничего нет",
                             "python", "librarian")
            return Reply("Прочитала %s — %d кусков легло в память. "
                         "Спроси — расскажу." % (report["file"], report["chunks"]),
                         "python", "librarian")

        # Круг Д: инициатива — Марфа сама хочет знать
        if low in ("вопросы", "что хотела спросить", "что хотела спросить?"):
            from core.questions import QuestionBank
            items = QuestionBank().open_items()
            if not items:
                return Reply("пока всё понятно — открытых вопросов нет",
                             "python", "questions")
            lines = ["%d. %s" % (i + 1, it["text"]) for i, it in enumerate(items)]
            return Reply("Хотела спросить:\n" + "\n".join(lines)
                         + "\n\n(ответь: «ответ <номер>: ...»)",
                         "python", "questions")

        m = re.match(r"^ответ\s+(\d+)\s*[:.,-]?\s+(.+)$", t.strip())
        if m:
            from core.questions import QuestionBank
            n, text = int(m.group(1)), m.group(2).strip()
            bank = QuestionBank()
            items = bank.open_items()
            if not (1 <= n <= len(items)):
                return Reply("вопроса №%d нет — скажи «вопросы», посмотрю "
                             "список заново" % n, "python", "questions")
            item = bank.answer(items[n - 1]["id"], text)
            if item is None:
                return Reply("не записалось — вопрос уже закрыт?", "python", "questions")
            if self.memory is not None:
                try:
                    self.memory.remember(
                        "Илья ответил на «%s»: %s" % (item["text"], text),
                        tags=["ответ"], importance=3.5)
                except Exception:
                    pass
            return Reply("Запомнила: «%s» → %s" % (item["text"], text),
                         "python", "questions")

        # Г-2.4, камера (22.11): веб-камера — второй источник зрения.
        # ВАЖНО: ветка ДО экранной — «посмотри в камеру» начинается
        # с «посмотри », и экранная ветка съела бы его. «Онлайн-знакомство».
        if (low in ("посмотри в камеру", "включи камеру", "что в камере",
                    "кто в камере", "глянь в камеру", "покажи камеру")
                or low.startswith("посмотри на меня")
                or low.startswith("посмотри на нас")):
            return Reply(eyes.describe_camera_text(), "python", "camera")

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
        if (low in ("что на экране", "опиши экран") or low == "посмотри"
                or low.startswith("посмотри ") or low.startswith("посмотри,")
                or low.startswith("что ты видишь") or low.startswith("что видишь")):
            return Reply(eyes.describe_text(), "python", "eyes")

        # Круг Р v2 (22.11, «единое зрение»): руки — исполнитель
        # координат ГЛАЗ, своей модели у них нет, сервер зрения они
        # не занимают (мастер-ТЗ §4: хозяин VRAM — глаза). Глагол
        # («нажми X» / «напечатай Y») разбирают сами руки — поэтому
        # задание уходит им ЦЕЛИКОМ; мозг молчит, каждое действие
        # всё равно идёт через СТРАЖА, моторика — только по резолюции
        # Создателя (кнопка 91), без неё — сухой режим.
        for _prefix in ("руки", "кликни", "нажми", "напечатай", "прокрути"):
            if low.startswith(_prefix):
                from core import motor
                if "экзамен" in low:
                    return Reply(motor.exam(), "python", "hands_exam")
                return Reply(motor.run(t), "python", "hands")

        # САМОЛЕЧЕНИЕ v1 (ТЗ_Самолечение_v1, 22.11): кодер-слуга пишет
        # патчи в ПЕСОЧНИЦУ data\patches — применение за Создателем.
        # «Марфа сама себя лечит»: мозг (или Создатель) ставит требование,
        # кодер-7B печатает код, страж проверяет, Создатель применяет.
        if low in ("патчи", "список патчей"):
            from core import repair
            return Reply(repair.list_patches(), "python", "patches")
        m = re.match(r"^примени\s+патч\s+(\d+)$", low)
        if m:
            from core import repair
            return Reply(repair.apply_patch(int(m.group(1))),
                         "python", "patch_apply")
        m = re.match(r"^откати\s+патч\s+(\d+)$", low)
        if m:
            from core import repair
            return Reply(repair.rollback_patch(int(m.group(1))),
                         "python", "patch_rollback")
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
        if low in ("изучи себя", "расскажи о себе", "кто ты", "что ты такое",
                   "что ты умеешь", "что умеешь", "твои возможности"):
            return Reply(identity.capabilities_report(memory=self.memory),
                         "python", "self_inspect")

        return None

    # ---------- системный контекст мозгового трека ----------

    def _system_extra(self, user_text: str) -> str:
        """Системный контекст мозгового трека.

        Порядок — дисциплина промпта (доктрина §4): ЯДРО ЛИЧНОСТИ первым
        и неизменным (префиксный KV-кэш, №51), затем МАНИФЕСТ возможностей
        (тоже статичный — имена инструментов и команд, Г-2.3), затем
        доктрина Создателя, состояние дома и RAG-воспоминания.
        """
        parts = [IDENTITY, identity.manifest(), self.doctrine, _house_state()]
        if self.memory is not None:
            try:
                found = self.memory.recall(user_text, top_k=3)
            except Exception:
                found = []
            if found:
                rag = "\n".join("- " + r["text"] for r in found)
                parts.append("Воспоминания (RAG):\n" + rag)
        return "\n\n".join(parts)

    # ---------- действия мозга через РУКИ (надзор СТРАЖА) ----------

    def _act(self, action: dict) -> Reply:
        tool = str(action.get("tool", ""))
        args = action.get("args") or {}
        try:
            if tool == "write_file":
                return Reply(hands.write_file(args.get("path", ""),
                                              args.get("content", "")),
                             "brain", "write_file")
            if tool == "read_file":
                return Reply(hands.read_file(args.get("path", "")),
                             "brain", "read_file")
            if tool == "run_python":
                return Reply(hands.run_python(args.get("code", "")),
                             "brain", "run_python")
            if tool == "browser_search":
                return Reply(hands.browser_search(args.get("query", "")),
                             "brain", "browser_search")
            if tool == "check_brackets":
                return Reply(hands.check_brackets(args.get("text", "")),
                             "brain", "check_brackets")
            if tool == "ui_action":
                # Доктрина ТЗ_Руки_v2: мозг не жмёт кнопки — он ДОВЕРЯЕТ
                # задание рукам. Координаты мозг никогда не называет: их
                # дают глаза дескриптором, руки берут центр бокса,
                # страж проверяет.
                from core import motor
                return Reply(motor.run(str(args.get("task", ""))),
                             "brain", "ui_action")
            if tool == "code_patch":
                # Доктрина ТЗ_Самолечение_v1: мозг не чинит файлы сам —
                # он ДОВЕРЯЕТ требование кодеру-слуге. Патч ложится в
                # песочницу; применяет Создатель («примени патч №») —
                # «уже починила» можно говорить только после него.
                from core import repair
                return Reply(repair.make_patch(str(args.get("path", "")),
                                               str(args.get("requirement", ""))),
                             "brain", "code_patch")
            _lesson("неизвестный-инструмент", "мозг позвал «%s»" % tool)
            return Reply("неизвестный инструмент: " + tool +
                         ". Мои инструменты (только эти имена): " +
                         identity.tool_names() +
                         " — позови существующий", "brain", tool or None)
        except PermissionError as e:
            _lesson("страж-отказ", "%s: %s" % (tool, e))
            return Reply("СТРАЖ отказал: " + str(e), "brain", tool or None)

    # ---------- главная точка ----------

    def handle(self, user_text: str, reply_to=None,
               history: Optional[list] = None) -> Reply:
        """Главная точка дома. №10: history — прошлые ходы разговора
        (DialogStore.render_messages), мозг видит диалог целиком."""
        hit, gate_reply = creator_gate.check(user_text)   # калитка Создателя
        if hit:
            return Reply(gate_reply, "python", "creator_gate")
        fast = self._fast(user_text)
        if fast is not None:
            return fast
        # эфир: быстрые команды мгновенны, а вот мозговой трек — долгий;
        # чат обязан видеть, ЧТО происходит, пока он идёт (не молчать)
        progress.stage("собираю контекст: доктрина, воспоминания, состояние дома…")
        system_extra = self._system_extra(user_text)
        progress.stage("мозг думает — большая модель на CPU, это может занять минуту и больше…")
        try:
            decision = self.brain.ask_json(
                user_text, system_extra=system_extra,
                history=history)
        except Exception as e:
            _lesson("мозг-недоступен", str(e))
            # Урок переписки 22.11: голое «timed out» Создатель читает как
            # поломку. Чаще это медленный Pascal-мозг, честно думающий
            # над длинным ответом, — говорим это человеческим языком.
            note = ""
            if "timed out" in str(e).lower():
                note = (" — думал дольше %d сек и не успел. Это не поломка: "
                        "мозг честно работает, просто медленно. Спроси "
                        "покороче или повтори через минуту"
                        % config.BRAIN_TIMEOUT_SEC)
            return Reply("мозг недоступен: " + str(e) + note, "fallback", None)
        if isinstance(decision, dict) and isinstance(decision.get("action"), dict):
            return self._act(decision["action"])
        if isinstance(decision, dict):
            return Reply(str(decision.get("answer", "Нет ответа")), "brain", None)
        return Reply(str(decision), "brain", None)
