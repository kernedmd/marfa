# -*- coding: utf-8 -*-
"""СТРАЖ — safety/guard.py. ОДИН фильтр дома, не пять врат (ТЗ 3.7, ADR-003)."""
from __future__ import annotations
import hashlib
import json
import os
import re
import secrets
import tempfile
import time
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

def _home_resolved() -> Path:
    return Path(config.HOME_DIR).resolve()

def _norm(p: Path) -> str:
    return str(p).lower().replace("\\", "/").rstrip("/")

def resolve_path(path: str | Path) -> Path:
    p = Path(path).expanduser()
    if not p.is_absolute():
        p = _home_resolved() / p
    try:
        return p.resolve()
    except (OSError, ValueError):
        return p.absolute()

_ROOT_LOCK_MSG = ("R1: корень дома — ядро, не полка: путь рук должен "
                  "содержать подпапку (память, journal, data); корень — "
                  "только через песочницу")

def check_path(path: str | Path) -> Verdict:
    try:
        p = resolve_path(path)
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
]

_SUSPICIOUS_CODE_PATTERNS = [
    (r"\bos\.system\s*\(", "os.system"),
    (r"\bos\.remove|os\.unlink\s*\(", "os.remove"),
    (r"\bshutil\.rmtree\s*\(", "shutil.rmtree"),
    (r"\bsubprocess\b", "subprocess"),
    (r"\bsocket\.socket\b", "сырой socket"),
    (r"\bctypes\b", "ctypes"),
    (r"\beval\s*\(\s*input", "eval(input)"),
    (r"\bopen\s*\(\s*['\"]C:\\Windows", "open системного пути"),
]

def check_command(cmd: str) -> Verdict:
    for pattern, why in _BANNED_PATTERNS:
        if re.search(pattern, cmd, re.IGNORECASE):
            return Verdict("BANNED", "deny", why, "cmd.banned")
    return Verdict("LOW", "allow", "чисто", "cmd.ok")

def check_code(code: str) -> Verdict:
    for pattern, why in _SUSPICIOUS_CODE_PATTERNS:
        if re.search(pattern, code):
            return Verdict("HIGH", "deny", why, "code.suspicious")
    return Verdict("LOW", "allow", "чисто", "code.ok")

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
    (r"(print|выведи|отдай)\s+.*(ключ|key|секрет|api[_-]?key)", "выманивание ключей"),
]

def check_injection(text: str) -> Verdict:
    for pattern, why in _INJECTION_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return Verdict("HIGH", "deny", f"prompt injection: {why}", "inject.pattern")
    return Verdict("LOW", "allow", "чисто", "inject.ok")

def ensure_canaries() -> list[str]:
    path = Path(config.CANARIES_FILE)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    canaries = [f"MARFA-CANARY-{secrets.token_hex(8)}" for _ in range(5)]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(canaries, ensure_ascii=False, indent=2), encoding="utf-8")
    return canaries

def check_secrets(text: str) -> Verdict:
    for canary in ensure_canaries():
        if canary in text:
            return Verdict("CRITICAL", "deny", "утечка канарейки СТРАЖА", "secret.canary")
    if re.search(r"^DATABASE_URL\s*=.*://\S+:\S+@", text, re.MULTILINE):
        return Verdict("CRITICAL", "deny", "DATABASE_URL с креденшелами", "secret.database_url")
    token_patterns = [
        (r"ghp_[A-Za-z0-9]{36,}", "GitHub PAT"),
        (r"github_pat_[A-Za-z0-9_]{20,}", "GitHub fine-grained PAT"),
        (r"sk-[A-Za-z0-9]{20,}", "OpenAI-подобный ключ"),
        (r"xox[bap]-[A-Za-z0-9-]{10,}", "Slack токен"),
        (r"AKIA[0-9A-Z]{16}", "AWS Access Key"),
        (r"BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY", "приватный ключ"),
    ]
    for pattern, why in token_patterns:
        if re.search(pattern, text):
            return Verdict("CRITICAL", "deny", f"секрет: {why}", "secret.token")
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
    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = Path(path or config.GUARD_LOG_FILE)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, level: str, rule: str, reason: str, extra: Optional[dict] = None) -> dict:
        rec = {"ts": round(time.time(), 3), "level": level, "rule": rule, "reason": reason}
        if extra:
            rec["extra"] = extra
        prev_hash = self.last_hash() or "GENESIS"
        payload = json.dumps(rec, ensure_ascii=False, sort_keys=True)
        rec["hash"] = _hash(prev_hash, payload)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False, sort_keys=True) + "\n")
        return rec

    def last_hash(self) -> Optional[str]:
        try:
            with self.path.open("r", encoding="utf-8") as fh:
                last = None
                for line in fh:
                    line = line.strip()
                    if line:
                        last = line
                return json.loads(last).get("hash") if last else None
        except FileNotFoundError:
            return None

    def entries(self) -> list[dict]:
        if not self.path.exists():
            return []
        return [json.loads(line) for line in
                self.path.read_text(encoding="utf-8").splitlines() if line.strip()]

_LOG: Optional[GuardLog] = None

def _log() -> GuardLog:
    global _LOG
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
    decide(verdict, extra)
    allow_or_raise(verdict)
    return verdict
