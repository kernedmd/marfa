# -*- coding: utf-8 -*-
"""core/config.py — ЕДИНЫЙ ИСТОЧНИК КОНСТАНТ ДОМА МАРФА (ТЗ 0.1, 0.3-0.5, Раздел 8).

Закон дома. Любой модуль берёт числа отсюда, а не выдумывает свои.
Аудит RAM: docs/RAM_AUDIT.md. Монитор Ф97 тревожит на 85% и критит на 92%
от ФАКТИЧЕСКОГО объёма RAM.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

# ---------------------------------------------------------------
# ДОМ (ТЗ 2.3): всё живёт только внутри C:\Marfa.
# Переопределение для разработки/тестов вне Z440: переменная MARFA_HOME.
# ---------------------------------------------------------------
HOME_DIR: Path = Path(os.environ.get("MARFA_HOME") or (
    r"C:\Marfa" if sys.platform == "win32"
    else os.path.join(tempfile.gettempdir(), "marfa_dev")
)).resolve()

CORE_DIR = HOME_DIR / "core"
DATA_DIR = HOME_DIR / "data"
LOGS_DIR = HOME_DIR / "logs"
MODELS_DIR = HOME_DIR / "models"
DOWNLOADS_DIR = HOME_DIR / "downloads"
INSTALL_STATE_DIR = DATA_DIR / "install_state"

# Файлы дома
DOCTRINE_FILE = DATA_DIR / "creator_doctrine.json"   # нерушимо, у Ильи (ТЗ Раздел 7)
GENOME_FILE = DATA_DIR / "context_genome.json"       # геном контекста (ТЗ 3.6)
LAST_QUANT_FILE = DATA_DIR / "last_quant.txt"        # Ф101: прежний квант для рестарта
QUEUE_FILE = DATA_DIR / "queue.json"                 # Ф74: очередь задач
GUARD_LOG_FILE = LOGS_DIR / "guard_log.jsonl"        # hash-chain лог СТРАЖА (ТЗ 3.7)
MONITOR_STATUS_FILE = DATA_DIR / "monitor_status.json"   # Ф97: статус для web
MONITOR_LOG_FILE = LOGS_DIR / "monitor_log.jsonl"        # Ф97: история событий

# ---------------------------------------------------------------
# 0.1 БЮДЖЕТ RAM (64 ГБ, план 44 ГБ) — ЗАКОН.
# ---------------------------------------------------------------
RAM_TOTAL_GB = 64
RAM_BUDGET_GB = 44
RAM_PLAN_GB = {
    "brain_weights_q4km": 19.0,   # 30B Q4_K_M: веса (файл 18.63) с учётом --mlock
    "kv_cache_4096": 2.0,         # KV-кэш при контексте 4096
    "windows_python_agent": 5.0,  # Windows + Python + агент
    "qlora_night": 8.0,           # студент + буферы ночью (30B не выгружается)
    "reserve": 10.0,              # браузер Ильи, бэкапы, распаковка моделей
}
assert abs(sum(RAM_PLAN_GB.values()) - RAM_BUDGET_GB) < 1e-9, "План RAM должен сходиться в 44 ГБ"

# Пороги монитора Ф97 — проценты от ФАКТИЧЕСКОГО объёма
MONITOR_WARN_PCT = 85
MONITOR_CRIT_PCT = 92

# ---------------------------------------------------------------
# 0.3 КОНТЕКСТ 4096 — больше нельзя (закон доктрины, ADR-005).
# Интерпретация бюджета: 3072 — весь промпт (система+состояние+RAG,
# внутри него сжатая история не более 1000 — Ф53), 768 — генерация.
# 3072 + 768 = 3840 <= 4096, запас 256 токенов.
# ---------------------------------------------------------------
CONTEXT_TOKENS = 4096
PROMPT_BUDGET_TOKENS = 3072
HISTORY_BUDGET_TOKENS = 1000     # Ф53: сжатая история внутри промпта
GENERATION_BUDGET_TOKENS = 768
assert PROMPT_BUDGET_TOKENS + GENERATION_BUDGET_TOKENS <= CONTEXT_TOKENS

# Грубая оценка токенов офлайн (без tokenizer'а): усреднённо ~3 символа/токен
# для смеси русского и кода. Точная цифра приходит из usage ответа llama-server.
CHARS_PER_TOKEN_EST = 3

# ---------------------------------------------------------------
# УШИ (Г-уши, Этап 1): сторож имени — vosk small, всегда на CPU.
# Доктрина «хозяина ресурса»: дешёвый вечно-включённый детектор имени;
# тяжёлая расшифровка — whisper-turbo, включается ПОСЛЕ слова «Марфа».
# ---------------------------------------------------------------
EARS_MODEL_DIR = MODELS_DIR / "vosk-model-small-ru-0.22"
EARS_WAKE_WORDS = ("марфа",)   # точные слова-триггеры
EARS_WAKE_MAX_DIST = 1         # допуск Левенштейна: «марва», «марфу»...
EARS_SAMPLE_RATE = 16000       # моно int16 — родной формат vosk
EARS_LOG_FILE = LOGS_DIR / "ears_log.jsonl"   # правило 6.6: логи — истина
EARS_STATUS_FILE = DATA_DIR / "ears_status.json"  # служба ушей: сердцебиение
EARS_RETRY_SECS = 60           # служба: пауза между попытками (микрофон воткнут позже — ухо проснётся)

# ---------------------------------------------------------------
# ПОРТЫ (ТЗ 2.1, 2.2; правило 6.4: порт 5000 НЕ ТРОГАТЬ)
# ---------------------------------------------------------------
PORT_BRAIN = 8082          # llama-server (30B на CPU)
PORT_EYES = 8083           # llama-server (Qwen2.5-VL, CUDA) — сенсор зрения
PORT_HANDS = 8084          # llama-server (UI-TARS) — СЛУГА ПО ВЫЗОВУ, ТЗ_Руки_v1
PORT_WEB = 5001            # локальная панель Марфы
PORT_FORBIDDEN = 5000      # занят чем-то важным — не используем
BRAIN_URL = os.environ.get("MARFA_BRAIN_URL") or f"http://127.0.0.1:{PORT_BRAIN}"
HANDS_URL = f"http://127.0.0.1:{PORT_HANDS}"

# ---------------------------------------------------------------
# МОЗГ И КВАНТЫ (ТЗ 2.1, Раздел 8)
# ---------------------------------------------------------------
BRAIN_MODEL_NAME = "Qwen3-30B-A3B"      # MoE: 3.3B активных из 30.5B
BRAIN_CTX_TOKENS = CONTEXT_TOKENS
BRAIN_FLAGS = ["--mlock", "-ngl", "0"]  # 0.5 и 2.2: GPU только для QLoRA
# Таймаут клиента мозга (22.11, урок переписки: «изучи себя» → timed out).
# 120 с оказалось ложью для Pascal: 768 токенов генерации при ~6 ток/с
# под нагрузкой — уже 128 с. Честное ожидание для Q4 на DDR4 — 5 минут.
BRAIN_TIMEOUT_SEC = 300
DEFAULT_QUANT = "Q4_K_M"
MODEL_QUANTS_GB = {
    "Q4_K_M": 18.63,   # по умолчанию: 8-16 ток/с на DDR4
    "Q6_K": 25.10,     # опция на 64 ГБ: 6-12 ток/с (решает Илья)
}
GGUF_FILES = {
    "Q4_K_M": "Qwen3-30B-A3B-Q4_K_M.gguf",
    "Q6_K": "Qwen3-30B-A3B-Q6_K.gguf",
}
GGUF_BASE_URL = "https://huggingface.co/Qwen/Qwen3-30B-A3B-GGUF/resolve/main"
GGUF_FALLBACK_URLS = {
    "Q4_K_M": "https://huggingface.co/unsloth/Qwen3-30B-A3B-GGUF/resolve/main/Qwen3-30B-A3B-Q4_K_M.gguf",
    "Q6_K": "https://huggingface.co/unsloth/Qwen3-30B-A3B-GGUF/resolve/main/Qwen3-30B-A3B-Q6_K.gguf",
}

# Студент (ТЗ 2.2, ADR-009)
STUDENT_MODEL_ID = "Qwen/Qwen2.5-3B-Instruct"   # плотной 3B у семейства Qwen3 нет
STUDENT_GB_EST = 7.0

# ---------------------------------------------------------------
# 0.4 QLORA — только ночью (окно 04:30-06:30), днём GPU свободна
# ---------------------------------------------------------------
QLORA_WINDOW = ("04:30", "06:30")
QLORA_NF4 = True           # ADR-004: Pascal CC 6.1, LLM.int8 запрещён
QLORA_DEADLINE = "06:30"   # дедлайн в колбэке

# ---------------------------------------------------------------
# СТРАЖ (ТЗ 3.7, ADR-003)
# ---------------------------------------------------------------
GUARD_LEVELS = ("LOW", "MEDIUM", "HIGH", "CRITICAL", "BANNED")
CANARIES_FILE = DATA_DIR / "canaries.json"

# ---------------------------------------------------------------
# АВТОНОМНОСТЬ (ТЗ 3.9, Ф71/Ф74/Ф75)
# ---------------------------------------------------------------
PLAN_HOUR = 8              # план дня в 08:00
MAX_FEATURES_PER_WEEK = 5  # не более 3-5 фишек в неделю (Раздел 5)

# ---------------------------------------------------------------
# СТРЕМЛЕНИЕ (Круг Д): расписание, вопросы, библиотекарь, служба
# ---------------------------------------------------------------
QUESTIONS_FILE = DATA_DIR / "questions.json"          # банк вопросов Илье
SCHEDULE_STATE_FILE = DATA_DIR / "schedule_state.json"  # Ф75: что уже отработало
LIBRARIAN_STATE_FILE = DATA_DIR / "librarian_state.json"  # что прочитано
EVOLUTION_DIR = DATA_DIR / "evolution"                # журнал уроков
DIARY_DIR = DATA_DIR / "diary"                        # №8: вечерние дневники
DRIVE_STATUS_FILE = DATA_DIR / "drive_status.json"    # служба стремления: сердце
DRIVE_INTERVAL_SECS = 60      # такт службы: раз в минуту (Ф74)
DOCTOR_STATE_FILE = DATA_DIR / "doctor_state.json"    # №21: память автодоктора

# ---------------------------------------------------------------
# ЖИВОЙ ЯЗЫК (гейт §5 — вердикт батареи 21.11.2026: факты 13/13,
# честность 2/2, речь чистая в двух прогонах Q4_K_M).
# Резолюция Создателя — data/live_voice.json, пишет кнопка 89:
# воля Создателя живёт в data/ (в git не попадает), не в коде.
# Сэмплинг — фикс Qwen3 из вердикта: temp 0.7 / top-p 0.8.
# ---------------------------------------------------------------
LIVE_VOICE_FILE = DATA_DIR / "live_voice.json"
LIVE_VOICE_TEMPERATURE = 0.7
LIVE_VOICE_TOP_P = 0.8
LIVE_VOICE_MAX_TOKENS = 768      # бюджет генерации (0.3): рассказ — не трактат
LIVE_VOICE_TEXT_CAP = 1500       # символ: рассказ длиннее — честно обрезаем

# ---------------------------------------------------------------
# РУКИ (ТЗ_Руки_v1): моторная кора — СЛУГА ПО ВЫЗОВУ, порт 8084.
# VRAM-арифметика: глаза 3.0 + руки 5.4 = 8.4 ГБ > 6 ГБ — вместе не
# живут; пока задачи рук нет, модель спит на диске. Резолюция Создателя
# на моторику (реальные клики) — data/hands_enabled.json (кнопка 91);
# без неё — сухой режим: план действий без движения мыши.
# ---------------------------------------------------------------
HANDS_MODEL = MODELS_DIR / "UI-TARS-7B-DPO.Q4_K_M.gguf"
HANDS_MMPROJ = MODELS_DIR / "UI-TARS-7B-DPO.mmproj-f16.gguf"
HANDS_CTX_TOKENS = 4096        # контекст моторной коры
HANDS_TIMEOUT_SEC = 300        # один вопрос рукам (7B на GTX 1060)
HANDS_START_WAIT_SECS = 180    # подъём Q4 с NVMe — десятки секунд
HANDS_MAX_STEPS = 8            # бюджет шагов на задачу (анти-вечный-цикл)
HANDS_TASK_BUDGET_SEC = 600    # секунд на задачу целиком (ТЗ 6: зависла — отказ)
HANDS_TYPE_LIMIT = 120         # символов печати за одно действие (№20)
HANDS_ENABLED_FILE = DATA_DIR / "hands_enabled.json"   # резолюция Создателя
HANDS_LOG_FILE = LOGS_DIR / "hands_log.jsonl"          # правило 6.6: логи — истина
HANDS_HOTKEY_WHITELIST = (     # №19: список — код, не мнение модели
    "esc", "enter", "tab", "alt+tab", "up", "down", "left", "right",
    "ctrl+c", "ctrl+v", "ctrl+a", "space", "backspace",
)
HANDS_DIALECT_FILE = DATA_DIR / "hands_dialect.json"  # измеряет экзамен Р-0

# ---------------------------------------------------------------
# САМОЛЕЧЕНИЕ (ТЗ_Самолечение_v1, 22.11): КОДЕР — пятый слуга-разум,
# qwen2.5-coder-7b-instruct из чулана (проснулась по слову Создателя
# «пусть Марфа сама себя чинит»). СЛУГА ПО ВЫЗОВУ, порт 8085: пока
# патча нет — спит на диске. VRAM: кодер ~4.7 + глаза 3.0 > 6 ГБ —
# тот же танец, что у рук: глаза присели, кодер поднялся, написал
# патч, лёг, глаза вернулись. Патч ложится ТОЛЬКО в песочницу
# data\patches\ — применение за Создателем («примени патч №»),
# с бэкапом и откатом.
# ---------------------------------------------------------------
PORT_CODER = 8085            # llama-server (qwen2.5-coder-7b) — СЛУГА ПО ВЫЗОВУ
CODER_URL = f"http://127.0.0.1:{PORT_CODER}"
CODER_CTX_TOKENS = 8192      # коду нужен простор: файл + требование + ответ
CODER_TIMEOUT_SEC = 300      # один вопрос кодеру (7B на GTX 1060)
CODER_START_WAIT_SECS = 180  # подъём с NVMe — десятки секунд
CODER_MAX_TOKENS = 4096      # ответ: файл целиком до ~250 строк
CODER_MAX_FILE_LINES = 250   # v1: файлы больше — архитектору, не кодеру
PATCHES_DIR = DATA_DIR / "patches"          # ПЕСОЧНИЦА патчей (не core\)
REPAIR_LOG_FILE = LOGS_DIR / "repair_log.jsonl"   # правило 6.6: логи — истина

# ---------------------------------------------------------------
# Fallback GigaChat (ТЗ 3.2): включается только когда 30B упала
# ---------------------------------------------------------------
FALLBACK_ENABLED = os.environ.get("MARFA_FALLBACK", "0") == "1"


def ensure_dirs() -> None:
    """Создать каркас папок дома (идемпотентно)."""
    for d in (DATA_DIR, LOGS_DIR, MODELS_DIR, DOWNLOADS_DIR, INSTALL_STATE_DIR):
        d.mkdir(parents=True, exist_ok=True)


def token_estimate(text: str) -> int:
    """Офлайн-оценка токенов. Для точной цифры используйте usage от llama-server."""
    return max(1, (len(text) + CHARS_PER_TOKEN_EST - 1) // CHARS_PER_TOKEN_EST)
