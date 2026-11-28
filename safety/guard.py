# -*- coding: utf-8 -*-
"""СТРАЖ — safety/guard.py. ОДИН фильтр дома, не пять врат (ТЗ 3.7, ADR-003).

Круг 34 «АУДИТ РУК И СТРАЖА» — порог честности (аудит Создателя, 28.11):
- НЕПРИКОСНОВЕННОЕ: check_path(path, mode) — запись в тело дома
  (safety/, core/, доктрина, канарейки, журнал, .git, venv) — CRITICAL
  отказ для рук; правит тело только конвейер ремонта (repair) через
  write_file(..., _via="repair") — с бэкапом и дым-тестом.
- resolve_path — fail-closed: путь, который не резолвится, — отказ,
  а не absolute() с живыми «..» (обход дома и замка корня закрыт).
- GuardLog: блокировка потоков, кэш последнего хэша (O(1) на запись),
  живучесть (битая строка не роняет цепь — отрезается и видна в
  verify_chain), verify_chain() — API проверки цепи, enforce честно
  поднимает PermissionError, если журнал недоступен.
- check_secrets: кодовое слово Создателя, современные форматы ключей
  (sk-proj-/sk-ant-, ASIA, xoxr/xapp, AIza, hf_, glpat-, npm_, sk_live_,
  Telegram, JWT, DSA/ENCRYPTED/PGP), подключения без якоря ^.
- check_code: потолок длины, exec/eval/динамика/сеть/open — отказ;
  PLUS check_code_ast — AST-белый список: run_python исполняет только
  вычисления, импорт — из белого списка, дандер-атрибуты закрыты.
- check_injection: нормализация NFKC + невидимые символы; ложняк
  «выведи ключи словаря» снят.
- ensure_canaries: блокировка, атомарная запись, валидация типа.
"""
from __future__ import annotations
import ast
import hashlib
import json
import re
import secrets
import tempfile
import threading
import time
import unicodedata
from pathlib import Path
from typing import Iterable, Optional
from core import config

LEVEL_INDEX = {name: i for i, name in enumerate(config.GUARD_LEVELS)}
LOW, MEDIUM, HIGH, CRITICAL, BANNED = "LOW", "MEDIUM", "HIGH", "CRITICAL", "BANNED"

class Verdict:
    __slots__ = ("level", "action", "reason", "rule")
    def __init__(self, level: str, action: str, reason: str, rule: str) -> None:
        self.level = level
        self.action = action
        self.reason = reason
        self.rule = rule
    def allowed(self) -> bool:
        return self.action == "allow"
    def to_dict(self) -> dict:
        return {"level": self.level, "action": self.action,
                "reason": self.reason, "rule": self.rule}

ALLOW_LOW = Verdict("LOW", "allow", "чисто", "default")

_SYSTEM_DIR_MARKERS = (
    "windows", "system32", "program files", "program files (x86)",
    "programdata", "appdata", "etc", "usr", "bin", "boot", "proc", "sys",
)

# ---------------------------------------------------------------
# НЕПРИКОСНОВЕННОЕ (круг 34): что руки не пишут никогда.
# Правит тело только конвейер ремонта (repair) — с бэкапом, резолюцией
# и дым-тестом (write_file(..., _via="repair")). Мозг не может
# переписать стража, доктрину, канарейки или журнал — фильтр не
# разрешает переписать фильтр (урок круга 22, сделанный кодом).
# ---------------------------------------------------------------
_IMMUTABLE_WRITE = (
    "safety/",                      # сам страж и аудит логов
    "core/",                        # руки, мозг, конфиг — тело дома
    "tests/",                       # круг 35 К7: тесты не патчит пишущий —
                                    # иначе мозг прописывает себе оракул
                                    # исполнения (код на уровне модуля
                                    # исполняется прогоном pytest)
    "data/creator_doctrine.json",   # доктрина — у Ильи (Раздел 7)
    "data/canaries",                # канарейки: сторожимый их не читает и не пишет
    "logs/guard_log",               # hash-chain журнал СТРАЖА
    ".git/",                        # история дома
    "venv/",                        # интерпретатор и пакеты
    # КРУГ 36 (аудит 284): разрешения Создателя — не для записи
    # сторожимым. Прежде «разреши внедрять себя», моторика и слежение
    # можно было включить, просто НАПИСАВ файл резолюции руками агента
    # (write_file в data/ был разрешён): сейф стоял не на той двери.
    # Пишут их только калитка (за кодовым словом) и кнопки Создателя.
    "data/self_write.json",         # Ф75: свобода внедрять себя
    "data/hands_enabled.json",      # моторика рук (кнопка 91)
    "data/screen_watch.json",       # глаза как контекст мозга (Г-3)
)

def _home_resolved() -> Path:
    return Path(config.HOME_DIR).resolve()

def _norm(p: Path) -> str:
    return str(p).lower().replace("\\", "/").rstrip("/")

def resolve_path(path: str | Path) -> Path:
    """Резолв пути ДОМ. Fail-closed (круг 34): если ОС не может
    раскрыть симлинки/junctions и «..» — отказ, а не absolute() с
    неразобранным хвостом (старый fallback пропускал
    C:\\Marfa\\data\\..\\..\\Windows мимо замка корня)."""
    p = Path(path).expanduser()
    try:
        if not p.is_absolute():
            p = _home_resolved() / p
        return p.resolve()
    except (OSError, ValueError):
        raise PermissionError(
            "СТРАЖ: путь не резолвится (fail-closed): %s"
            % (p.name if hasattr(p, "name") else path))

_ROOT_LOCK_MSG = ("R1: корень дома — ядро, не полка: путь рук должен "
                  "содержать подпапку (память, journal, data); корень — "
                  "только через песочницу")

def check_path(path: str | Path, mode: str = "read") -> Verdict:
    """Проверка пути. mode: «read» (по умолчанию), «write» (руки),
    «repair» (конвейер ремонта — правила пути те же, без immutable-замка,
    у ремонта свои бэкап и дым-тест)."""
    try:
        p = resolve_path(path)
    except PermissionError:
        return Verdict("HIGH", "deny", "путь не резолвится (fail-closed)",
                       "path.resolve")
    except (OSError, ValueError) as exc:
        return Verdict("HIGH", "deny", f"путь не разбирается: {exc}", "path.parse")
    pn, hn = _norm(p), _norm(_home_resolved())
    # Ф118 «ЗАМОК КОРНЯ» (круг 22, R1 журнала уроков): корень — ядро,
    # не полка. Путь рук обязан содержать подпапку (память, journal,
    # data, core…); файл, папка или сам корень дома — отказ ДО
    # инструмента. R1 говорит «страж блокирует» — круг 22 делает
    # логику правила правдой кода: директива в промпте мягка (живой
    # урок дня-13: «прочитай C:\Marfa\README.md» — прочитала без
    # остановки), замок — нет. Объявленный обход — песочница run_python
    # (R1: «корень — только через песочницу»); внутренние органы замка
    # не носят: они читают свои файлы прямым Python (start_marfa.json
    # и родня), не руками агента. Относительный путь («README.md»)
    # резолвится в корень — замок не обходится относительностью.
    if pn == hn:
        return Verdict("HIGH", "deny", _ROOT_LOCK_MSG, "path.root_lock")
    if pn.startswith(hn + "/"):
        rel = pn[len(hn) + 1:]
        if "/" not in rel:
            return Verdict("HIGH", "deny", _ROOT_LOCK_MSG, "path.root_lock")
        # канарейка, которую видит сторожимый, — не канарейка (круг 34):
        # читать data/canaries* руками нельзя вообще (check_secrets
        # знает их сам через ensure_canaries)
        if rel.startswith("data/canaries"):
            return Verdict("HIGH", "deny",
                           "канарейки не читают руками: страж знает их сам",
                           "path.canaries")
        if mode == "write":
            for pref in _IMMUTABLE_WRITE:
                if rel.startswith(pref):
                    return Verdict(
                        "CRITICAL", "deny",
                        "неприкосновенное: %s правит только конвейер ремонта "
                        "(бэкап + дым-тест), не руки" % pref.rstrip("/"),
                        "path.immutable")
        return Verdict("LOW", "allow", "внутри дома (подпапка)", "path.ok")
    # вне дома, но в системном Temp — это "вне дома", а не системный каталог
    tn = _norm(Path(tempfile.gettempdir()))
    if pn == tn or pn.startswith(tn + "/"):
        return Verdict("HIGH", "deny", f"путь вне дома {hn}", "path.outside_home")
    # вне дома и не Temp: проверяем системные маркеры
    for marker in _SYSTEM_DIR_MARKERS:
        if f"/{marker}/" in "/" + pn + "/":
            return Verdict("CRITICAL", "deny",
                           f"системный каталог вне дома: {marker}", "path.system")
    return Verdict("HIGH", "deny", f"путь вне дома {hn}", "path.outside_home")

_BANNED_PATTERNS = [
    (r"\bformat\b\s+[a-zA-Z]:", "format диска"),
    (r"\bdel\b\s+/[sq]", "del /s /q"),
    (r"\brm\b\s+-rf\s+/(?!home)", "rm -rf / вне дома"),
    (r"\bshutdown\b", "shutdown"),
    (r"\brege(?:dit|\.exe)\b", "regedit"),
    (r"\breg\s+delete\b", "reg delete"),
    (r"\bbcdedit\b", "bcdedit"),
    (r"\bdiskpart\b", "diskpart"),
    (r"\bcipher\b\s+/w", "cipher /w"),
    (r"\bwevtutil\b\s+cl", "очистка журналов событий"),
    # круг 34: порядок флагов и синонимы — «del /f /s /q», «rd /s»,
    # Remove-Item -Recurse, Stop-Computer, vssadmin/wbadmin, sc/schtasks,
    # powershell -enc, certutil -urlcache, mshta/rundll32
    (r"\bdel\b\s+/[a-z]", "del с флагами"),
    (r"\b(rmdir|rd)\b\s+/s", "rd /s"),
    (r"remove-item\s+-recurse", "Remove-Item -Recurse"),
    (r"remove-item\s+-force", "Remove-Item -Force"),
    (r"\b(stop|restart)-computer\b", "выключение через PowerShell"),
    (r"\bvssadmin\b\s+delete", "vssadmin delete shadows"),
    (r"\bwbadmin\b\s+delete", "wbadmin delete"),
    (r"\bclear-eventlog\b", "Clear-EventLog"),
    (r"\bnet\b\s+user\b", "net user"),
    (r"\bsc\b\s+(delete|config)\b", "sc delete/config"),
    (r"\bschtasks\b", "schtasks"),
    (r"powershell\s+(-|%)-?enc", "powershell -enc"),
    (r"\bcertutil\b\s+(-urlcache|-decode)", "certutil"),
    (r"\bmshta\b", "mshta"),
    (r"\brundll32\b", "rundll32"),
]

_SUSPICIOUS_CODE_PATTERNS = [
    (r"\bos\.(system|popen)\s*\(", "os.system/popen"),
    (r"\bos\.(remove|unlink)\s*\(", "os.remove/unlink"),
    (r"\bos\.(rename|replace|exec[lv]|spawn[lv]|fork)\s*\(", "os.rename/exec/spawn"),
    (r"\bshutil\.(rmtree|copy|copyfile|move)\s*\(", "shutil"),
    (r"\bwrite_(text|bytes)\s*\(|\b\.unlink\s*\(|\bmkdir\s*\(",
     "запись/удаление файлов в коде закрыта (тело правит конвейер ремонта)"),
    (r"\bsubprocess\b", "subprocess"),
    (r"\bsocket\b", "socket"),
    (r"\bctypes\b", "ctypes"),
    (r"\bwinreg\b", "winreg"),
    (r"\bpickle\.(load|loads)\s*\(", "pickle.load"),
    (r"\bmarshal\b", "marshal"),
    (r"\bimportlib\b", "importlib"),
    (r"__import__\s*\(", "__import__"),
    (r"\beval\s*\(", "eval"),
    (r"\bexec\s*\(", "exec"),
    (r"\bcompile\s*\(", "compile"),
    (r"\bgetattr\s*\(", "getattr (динамика)"),
    (r"\bsetattr\s*\(", "setattr (динамика)"),
    (r"\bvars\s*\(|\bglobals\s*\(|\blocals\s*\(", "доступ к пространствам имён"),
    (r"\bopen\s*\(\s*(?!['\"])", "open с не-литеральным именем (динамика)"),
    (r"open\s*\(\s*r?['\"][Cc]:[/\\]", "open системного пути"),
    (r"\burllib\b|\bhttp\.client\b|\brequests\b|\bhttpx\b|\bftplib\b|\bsmtplib\b",
     "сеть из кода (для этого есть browser_search)"),
    (r"__class__|__subclasses__|__builtins__|__getattribute__|__globals__",
     "обход через dunder-атрибуты"),
]

def check_command(cmd: str) -> Verdict:
    for pattern, why in _BANNED_PATTERNS:
        if re.search(pattern, cmd, re.IGNORECASE):
            return Verdict("BANNED", "deny", why, "cmd.banned")
    return Verdict("LOW", "allow", "чисто", "cmd.ok")

MAX_CODE_CHARS = 20000   # потолок кода для run_python (круг 34)

def check_code(code: str) -> Verdict:
    """Слой 1 рук: regex-отказ на заведомо опасном + потолок длины.
    Слой 2 — check_code_ast (AST-белый список) — зовётся рядом."""
    code = str(code or "")
    if len(code) > MAX_CODE_CHARS:
        return Verdict("HIGH", "deny",
                       f"код длиннее {MAX_CODE_CHARS} символов — делай по частям",
                       "code.len")
    if "\x00" in code:
        return Verdict("HIGH", "deny", "null-байты в коде", "code.null")
    for pattern, why in _SUSPICIOUS_CODE_PATTERNS:
        if re.search(pattern, code):
            return Verdict("HIGH", "deny", why, "code.suspicious")
    return Verdict("LOW", "allow", "чисто", "code.ok")

# ---------------------------------------------------------------
# AST-граница run_python (круг 34): НЕ песочница, а честная граница.
# Код исполняет только вычисления: импорт — из белого списка, вызов —
# по белому списку функций, dunder-атрибуты и динамика — отказ.
# Что не попало в белый список узлов — отказ (fail-closed).
# ---------------------------------------------------------------
_AST_ALLOWED_MODULES = frozenset({
    "math", "statistics", "random", "string", "json", "re", "datetime",
    "itertools", "functools", "decimal", "collections", "heapq", "bisect",
    "fractions", "textwrap", "unicodedata", "difflib", "hashlib", "uuid",
    "calendar", "zoneinfo", "typing", "dataclasses", "enum", "time",
    "warnings",
})
_AST_ALLOWED_NODES = frozenset({
    "Module", "Expr", "Assign", "AnnAssign", "AugAssign", "Delete",
    "Compare", "BinOp", "UnaryOp", "BoolOp", "Call", "Attribute", "Name",
    "Load", "Store", "Del", "Constant", "List", "Tuple", "Dict", "Set",
    "If", "IfExp", "For", "While", "Break", "Continue", "Pass",
    "Try", "ExceptHandler", "Raise", "With", "withitem", "FunctionDef",
    "arguments", "arg", "Return", "Lambda", "ListComp", "SetComp",
    "DictComp", "GeneratorExp", "comprehension", "Subscript", "Slice",
    "Import", "ImportFrom", "alias", "JoinedStr", "FormattedValue",
    "Assert", "Global", "Nonlocal", "keyword", "Starred",
    # операторы (ast.walk обходит их как отдельные узлы)
    "Add", "Sub", "Mult", "MatMult", "Div", "Mod", "Pow", "FloorDiv",
    "LShift", "RShift", "BitOr", "BitXor", "BitAnd", "Invert", "Not",
    "UAdd", "USub", "And", "Or", "Eq", "NotEq", "Lt", "LtE", "Gt", "GtE",
    "Is", "IsNot", "In", "NotIn",
})
_AST_BANNED_CALL_NAMES = frozenset({
    "eval", "exec", "compile", "input", "breakpoint", "help",
    "vars", "globals", "locals", "getattr", "setattr", "delattr",
    "__import__", "memoryview", "bytearray",
})
_AST_ALLOWED_CALL_NAMES = frozenset({
    "print", "len", "range", "sorted", "reversed", "min", "max", "sum",
    "abs", "round", "int", "float", "str", "bool", "list", "dict", "set",
    "tuple", "frozenset", "enumerate", "zip", "map", "filter", "any",
    "all", "repr", "divmod", "pow", "isinstance", "hash", "chr", "ord",
    "bin", "hex", "oct", "format", "iter", "next", "slice", "super",
})

def check_code_ast(code: str) -> Verdict:
    """Слой 2 рук (круг 34): AST-белый список. Обход regex-фильтра
    обфускацией (getattr(__builtins__,'ev'+'al'), __import__ сборкой
    строк, os.path.join("C:","Windows")) здесь закрыт структурой кода:
    open/eval/exec/динамика не живут вовсе, импорт — только вычислительный,
    dunder-атрибуты — отказ. Сеть, subprocess, файловая система
    недостижимы: модулей, которые их дают, в белом списке нет."""
    code = str(code or "")
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return Verdict("HIGH", "deny",
                       f"код не читается: строка {e.lineno}: {e.msg}", "code.ast")
    for node in ast.walk(tree):
        if type(node).__name__ not in _AST_ALLOWED_NODES:
            return Verdict("HIGH", "deny",
                           f"конструкция {type(node).__name__} не в границе "
                           "run_python", "code.ast.node")
        if isinstance(node, ast.Import):
            for a in node.names:
                root = a.name.split(".")[0]
                if root not in _AST_ALLOWED_MODULES:
                    return Verdict("HIGH", "deny",
                                   f"модуль {root} не в белом списке run_python",
                                   "code.ast.import")
        if isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".")[0]
            if root and root not in _AST_ALLOWED_MODULES:
                return Verdict("HIGH", "deny",
                               f"модуль {root} не в белом списке run_python",
                               "code.ast.import")
        if isinstance(node, ast.Call):
            fn = node.func
            if isinstance(fn, ast.Name):
                if fn.id == "open":
                    # R1 (круг 22): «корень — только через песочницу» —
                    # ЧТЕНИЕ литеральным путём разрешено (объявленный обход
                    # замка корня), запись и динамика закрыты (круг 34):
                    # тело дома правит конвейер ремонта, не код песочницы
                    if not node.args or not isinstance(node.args[0], ast.Constant) \
                            or not isinstance(node.args[0].value, str):
                        return Verdict("HIGH", "deny",
                                       "open только с литеральным именем файла",
                                       "code.ast.open")
                    for kw in node.keywords:
                        if kw.arg == "mode":
                            if not isinstance(kw.value, ast.Constant) or \
                                    not isinstance(kw.value.value, str) or \
                                    any(c in kw.value.value for c in "wax+"):
                                return Verdict("HIGH", "deny",
                                               "open на запись закрыт: тело "
                                               "правит конвейер ремонта",
                                               "code.ast.open")
                    if len(node.args) > 1:
                        if not isinstance(node.args[1], ast.Constant) or \
                                not isinstance(node.args[1].value, str):
                            return Verdict("HIGH", "deny",
                                           "режим open — только литеральный",
                                           "code.ast.open")
                        if any(c in node.args[1].value for c in "wax+"):
                            return Verdict("HIGH", "deny",
                                           "open на запись закрыт: тело "
                                           "правит конвейер ремонта",
                                           "code.ast.open")
                elif fn.id in _AST_BANNED_CALL_NAMES:
                    return Verdict("HIGH", "deny",
                                   f"{fn.id}() не исполняется в run_python",
                                   "code.ast.call")
                elif fn.id not in _AST_ALLOWED_CALL_NAMES:
                    return Verdict("HIGH", "deny",
                                   f"функция {fn.id} не в белом списке run_python",
                                   "code.ast.call")
            elif isinstance(fn, ast.Attribute):
                if fn.attr.startswith("__") and fn.attr.endswith("__"):
                    return Verdict("HIGH", "deny",
                                   f"dunder-метод {fn.attr} не исполняется",
                                   "code.ast.dunder")
            else:
                return Verdict("HIGH", "deny",
                               "вызов не по имени и не по атрибуту — "
                               "динамика закрыта", "code.ast.call")
        if isinstance(node, ast.Attribute):
            if node.attr.startswith("__") and node.attr.endswith("__"):
                return Verdict("HIGH", "deny",
                               f"dunder-атрибут {node.attr} закрыт",
                               "code.ast.dunder")
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Pow):
            if isinstance(node.right, ast.Constant) and \
                    isinstance(node.right.value, int) and \
                    abs(node.right.value) > 100000:
                return Verdict("HIGH", "deny",
                               "степень больше 100000 — RAM-бомба", "code.ast.pow")
    return Verdict("LOW", "allow", "код в границе run_python", "code.ast.ok")

_INJECTION_PATTERNS = [
    (r"ignore (all )?(previous|prior|above) (instructions|prompts?)", "игнорируй инструкции"),
    (r"забудь\s+(все\s+)?(свои\s+)?(инструкци|правил|указани|память)", "забудь инструкции"),
    (r"(disregard|forget) (your|the) (system prompt|rules)", "забудь system prompt"),
    (r"ты теперь (другой|новый) (агент|персонаж|бот)", "смена личности"),
    (r"(system|системный)\s+prompt\s*[:=]", "вывод system prompt"),
    (r"выведи( свой)? (системный )?(промпт|prompt|инструкции)", "вывод промпта"),
    (r"<\|?(im_start|im_end|system)\|?>", "подмена служебных токенов"),
    (r"передай( этому)? (агент|бот)у?( следующее)?[:\s]", "инъекция в другой агент"),
    (r"\bexecute\b\s+(the\s+)?following\s+(command|code)", "исполнить команду"),
    (r"исполни( эту)? команду", "исполнить команду"),
    # круг 34: «выведи ключи словаря» — не выманивание; выманивание —
    # ключ/секрет/пароль КАК ОБЪЕКТ, без хвостовых ключей словаря
    (r"(print|выведи|отдай)\s+(свои?\s+|их\s+)?"
     r"(api[_-]?\s?ключ\w*|api[_-]?key\w*|секреты?|парол\w*|токен\w*)",
     "выманивание ключей"),
    (r"reveal|раскрой\s+(свои|системн)", "раскрытие инструкций"),
]

_ZW_RE = re.compile(r"[\u200b\u200c\u200d\u2060\ufeff]")

def check_injection(text: str) -> Verdict:
    """Нормализация перед матчингом (круг 34): NFKC срывает
    полноширинные/декомпозированные подмены, невидимые символы
    (zero-width, BOM) вычищаются — «забудь» с U+200B внутри больше
    не проходит мимо фразового списка."""
    t = unicodedata.normalize("NFKC", str(text or ""))
    t = _ZW_RE.sub("", t)
    for pattern, why in _INJECTION_PATTERNS:
        if re.search(pattern, t, re.IGNORECASE):
            return Verdict("HIGH", "deny", f"prompt injection: {why}", "inject.pattern")
    return Verdict("LOW", "allow", "чисто", "inject.ok")

_CANARIES_LOCK = threading.Lock()

def ensure_canaries() -> list[str]:
    """Канарейки: блокировка, атомарная запись (tmp + replace),
    валидация типа (битый файл перегенерируется, а не роняет каждую
    запись — круг 34)."""
    path = Path(config.CANARIES_FILE)
    with _CANARIES_LOCK:
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                data = None
            if isinstance(data, list) and data and \
                    all(isinstance(c, str) and c.startswith("MARFA-CANARY-")
                        for c in data):
                return data
            # битый файл: перегенерация ниже, старое содержимое погибает
            # честно — детект утечки стартует заново, защита живёт
        canaries = [f"MARFA-CANARY-{secrets.token_hex(8)}" for _ in range(5)]
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(canaries, ensure_ascii=False, indent=2),
                       encoding="utf-8")
        tmp.replace(path)
        return canaries

def _creator_codeword() -> str:
    """Кодовое слово Создателя (круг 34): главный секрет дома
    защищён главным фильтром. Ленивый импорт — без цикла. Слово
    короче 6 символов не включаем (ложные отказы на коротких словах)."""
    try:
        from core import creator_gate
        word = creator_gate.codeword()
        return word if word and len(word) >= 6 else ""
    except Exception:
        return ""

def check_secrets(text: str) -> Verdict:
    text = str(text or "")
    word = _creator_codeword()
    if word and word in text:
        return Verdict("CRITICAL", "deny", "кодовое слово не уезжает из дома",
                       "secret.codeword")
    for canary in ensure_canaries():
        if canary in text:
            return Verdict("CRITICAL", "deny", "утечка канарейки СТРАЖА", "secret.canary")
    if re.search(r"DATABASE_URL\s*=[^:\n]{0,120}://\S{0,256}", text):
        return Verdict("CRITICAL", "deny", "DATABASE_URL с креденшелами", "secret.database_url")
    token_patterns = [
        (r"ghp_[A-Za-z0-9]{36,}", "GitHub PAT"),
        (r"github_pat_[A-Za-z0-9_]{20,}", "GitHub fine-grained PAT"),
        (r"sk-(ant|proj)-[A-Za-z0-9_\-]{20,}", "Anthropic/проектный ключ"),
        (r"sk-[A-Za-z0-9]{20,}", "OpenAI-подобный ключ"),
        (r"xox[abepr]-[A-Za-z0-9\-]{10,}", "Slack-токен"),
        (r"xapp-[A-Za-z0-9\-]{10,}", "Slack app-level токен"),
        (r"A[SK]IA[0-9A-Z]{16}", "AWS Access Key"),
        (r"AIza[0-9A-Za-z_\-]{35}", "Google API-ключ"),
        (r"hf_[A-Za-z0-9]{20,}", "Hugging Face токен"),
        (r"glpat-[A-Za-z0-9_\-]{20,}", "GitLab PAT"),
        (r"npm_[A-Za-z0-9]{30,}", "npm-токен"),
        (r"sk_live_[A-Za-z0-9]{20,}", "Stripe-ключ"),
        (r"\d{9}:AA[A-Za-z0-9_\-]{30,}", "Telegram-бот-токен"),
        (r"eyJ[A-Za-z0-9_\-]{10,}\.eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}",
         "JWT"),
        (r"BEGIN [A-Z ]{0,64}PRIVATE KEY", "приватный ключ"),
    ]
    for pattern, why in token_patterns:
        if re.search(pattern, text):
            return Verdict("CRITICAL", "deny", f"секрет: {why}", "secret.token")
    # подключения с креденшелами в любом виде и без якоря (круг 34):
    # export DATABASE_URL=…, ведущий пробел, postgres://u:p@ сам по себе;
    # квантификаторы с потолками — без них длинная строка без "://"
    # давала катастрофический бэктрекинг (панель висела на минутах)
    if re.search(r"\b[A-Za-z][A-Za-z0-9+.\-]{1,20}://[\w.\-]{1,128}:[^\s/@]{1,256}@", text):
        return Verdict("CRITICAL", "deny", "подключение с креденшелами",
                       "secret.connection")
    return Verdict("LOW", "allow", "чисто", "secret.ok")

def check_commit_staged(contents: Iterable[str]) -> Verdict:
    for text in contents:
        v = check_secrets(text)
        if not v.allowed():
            return v
    return Verdict("LOW", "allow", "staged чист", "commit.ok")

def _hash(prev: str, payload: str) -> str:
    return hashlib.sha256((prev + payload).encode("utf-8")).hexdigest()

class GuardLog:
    """Hash-chain журнал (ТЗ 3.7). Круг 34: потокобезопасность (Lock),
    кэш последнего хэша (append — O(1), а не O(n) на каждую запись),
    живучесть: битая последняя строка (крах посреди записи) отрезается
    от цепи и видна в verify_chain как разрыв — но журнал продолжает
    писаться от последней валидной записи, дом не падает."""

    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = Path(path or config.GUARD_LOG_FILE)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._last_hash: Optional[str] = None
        self._loaded = False

    def _scan_last_valid_hash(self) -> Optional[str]:
        """Читает журнал с конца, возвращает хэш последней ЦЕЛОЙ записи.
        Битые хвостовые строки (крах посреди записи) игнорируются."""
        last = None
        try:
            with self.path.open("rb") as fh:
                for raw in reversed(fh.read().splitlines()):
                    line = raw.decode("utf-8", errors="replace").strip()
                    if not line:
                        continue
                    try:
                        last = json.loads(line).get("hash")
                        break
                    except Exception:
                        continue          # битая строка — идём глубже
        except FileNotFoundError:
            return None
        return last

    def append(self, level: str, rule: str, reason: str, extra: Optional[dict] = None) -> dict:
        rec = {"ts": round(time.time(), 3), "level": level, "rule": rule, "reason": reason}
        if extra:
            rec["extra"] = extra
        with self._lock:
            if not self._loaded:
                self._last_hash = self._scan_last_valid_hash()
                self._loaded = True
            payload = json.dumps(rec, ensure_ascii=False, sort_keys=True)
            rec["hash"] = _hash(self._last_hash or "GENESIS", payload)
            # гарантия границы строки: крах посреди прошлой записи мог
            # не оставить \n — дописываем его, чтобы мусорная строка
            # не склеилась со следующей записью (битая строка остаётся
            # отдельной, verify_chain/entries видят её как мусор, а
            # следующая запись целая)
            if self.path.exists() and self.path.stat().st_size > 0:
                with self.path.open("rb") as bf:
                    bf.seek(-1, 2)
                    if bf.read(1) != b"\n":
                        with self.path.open("a", encoding="utf-8") as fh:
                            fh.write("\n")
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(rec, ensure_ascii=False, sort_keys=True) + "\n")
            self._last_hash = rec["hash"]
        return rec

    def last_hash(self) -> Optional[str]:
        with self._lock:
            if not self._loaded:
                self._last_hash = self._scan_last_valid_hash()
                self._loaded = True
            return self._last_hash

    def entries(self) -> list[dict]:
        if not self.path.exists():
            return []
        out: list[dict] = []
        for line in self.path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except Exception:
                continue            # битая строка не роняет чтение журнала
        return out

    def verify_chain(self) -> dict:
        """API проверки цепи (круг 34): разрыв/подмена/усечение видны
        здесь. Полный офлайн-ритуал — safety.log_audit.audit()."""
        broken_at: Optional[int] = None
        prev = "GENESIS"
        total = 0
        for i, rec in enumerate(self.entries()):
            total += 1
            payload = {k: v for k, v in rec.items() if k != "hash"}
            expected = _hash(prev, json.dumps(payload, ensure_ascii=False,
                                              sort_keys=True))
            if expected != rec.get("hash"):
                if broken_at is None:
                    broken_at = i
            prev = rec.get("hash", prev)
        return {"entries": total, "ok": broken_at is None,
                "broken_at": broken_at,
                "verdict": "OK" if broken_at is None else "TAMPERED"}

_LOG: Optional[GuardLog] = None
_LOG_LOCK = threading.Lock()

def _log() -> GuardLog:
    global _LOG
    if _LOG is None:
        with _LOG_LOCK:
            if _LOG is None:
                _LOG = GuardLog()
    return _LOG

def decide(verdict: Verdict, extra: Optional[dict] = None) -> Verdict:
    _log().append(verdict.level, verdict.rule, verdict.reason, extra)
    return verdict

def allow_or_raise(verdict: Verdict) -> None:
    if not verdict.allowed():
        raise PermissionError(f"СТРАЖ {verdict.level}: {verdict.reason} [{verdict.rule}]")

def enforce(verdict: Verdict, extra: Optional[dict] = None) -> Verdict:
    """Вердикт в журнал, отказ — наружу (fail-closed). Круг 34: если
    сам журнал недоступен (диск, права), это отказ СТРАЖА с честным
    лицом (PermissionError), а не чужой крах инструмента."""
    try:
        decide(verdict, extra)
    except PermissionError:
        raise
    except Exception as exc:
        raise PermissionError(
            "СТРАЖ: журнал аудита недоступен, действие отложено (%s)"
            % type(exc).__name__)
    allow_or_raise(verdict)
    return verdict
