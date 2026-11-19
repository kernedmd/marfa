# -*- coding: utf-8 -*-
r"""download_student.py — закачка студента Qwen2.5-3B-Instruct в models (шаг 04).

Урок 12.11.2026 (коммит 25): шаг 04 звал `python -m huggingface_hub.commands.huggingface_cli`,
а в новых версиях huggingface_hub (1.x) модуль commands удалён — обе попытки
(huggingface.co и hf-mirror.com) умирали за секунду («No module named ...»),
и конвейер рапортовал «HF недоступны», хотя сеть была ни при чём.

Решение: свой загрузчик на чистом stdlib — прямые GET на
<endpoint>/Qwen/Qwen2.5-3B-Instruct/resolve/<снимок>/<файл> (urllib, таймаут 30с,
докачка через Range, до 4 попыток на файл), жёсткая проверка SHA-256 обоих
шардов safetensors и JSON-конфигов. Не зависит ни от версии huggingface_hub,
ни от CLI: CLI в 0.34+ переименован, а в 1.x удалён — полагаться на него нельзя.

Важно про состав файлов: в снимке aa8e7253 ЕСТЬ ли единого model.safetensors —
модель лежит двумя шардами model-0000X-of-00002.safetensors + index.json
(без index transformers модель из папки не грузит). Старая подсказка с
«model.safetensors» была ошибочна; такой файл-мусор удаляется при закачке.

Запуск:
  python download_student.py <папка>                 # скачать недостающее
  python download_student.py <папка> --only f1,f2    # только эти файлы
  python download_student.py <папка> --check-only    # только проверка целостности
Источник: переменная HF_ENDPOINT (по умолчанию https://huggingface.co,
шаг 04 при провале повторяет с https://hf-mirror.com).
Коды выхода: 0 — всё ОК; 1 — проверка не прошла; 2 — не скачалось; 3 — плохие аргументы.
"""
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.request

REPO_ID = "Qwen/Qwen2.5-3B-Instruct"
# Снимок закреплён (правило ТЗ: точные версии); SHA-256 шардов неизменны для него.
SNAPSHOT = "aa8e72537993ba99e69dfaafa59ed015b17504d1"

# (имя, фактический размер в снимке) — из API huggingface.co от 12.11.2026
FILES = [
    ("config.json", 661),
    ("generation_config.json", 242),
    ("model-00001-of-00002.safetensors", 3968658944),
    ("model-00002-of-00002.safetensors", 2203268048),
    ("model.safetensors.index.json", 35581),
    ("tokenizer.json", 7031645),
    ("tokenizer_config.json", 7305),
    ("vocab.json", 2776833),
    ("merges.txt", 1671839),
]

# SHA-256 LFS-объектов шардов (tree API, снимок aa8e7253) — проверка жёсткая.
EXPECTED_SHA256 = {
    "model-00001-of-00002.safetensors":
        "67347b23fb4165b652eb6611f5e1f2a06dfcddba8e909df1b2b0b1857bee06c2",
    "model-00002-of-00002.safetensors":
        "a40d941d0e7e0b966ad8b62bb6d6b7c88cce1299197b599d9d0a4ce59aabfc1d",
}

# Нижние границы размера (ловим HTML-заглушки прокси и обрывы). Верх не проверяем:
# мелкие текстовые файлы могут законно отличаться в новой ревизии, а шарды
# защищены SHA-256.
MIN_SIZE = {
    "config.json": 400,
    "generation_config.json": 100,
    "model-00001-of-00002.safetensors": 3900000000,
    "model-00002-of-00002.safetensors": 2100000000,
    "model.safetensors.index.json": 10000,
    "tokenizer.json": 6000000,
    "tokenizer_config.json": 3000,
    "vocab.json": 2000000,
    "merges.txt": 1000000,
}


def endpoint():
    return (os.environ.get("HF_ENDPOINT") or "https://huggingface.co").rstrip("/")


def url_for(fname):
    return "%s/%s/resolve/%s/%s" % (endpoint(), REPO_ID, SNAPSHOT, fname)


def sha256_file(path, report_every_gb=1):
    h = hashlib.sha256()
    done = 0
    with open(path, "rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
            done += len(chunk)
            if report_every_gb and done % (report_every_gb * 1024 * 1024 * 1024) < 1024 * 1024:
                print("  sha256... %.0f ГБ" % (done / 1e9), flush=True)
    return h.hexdigest()


def verify_one(dest_dir, fname):
    """True/False + причина в консоли. Жёстко: sha256 шардов, JSON у конфигов."""
    path = os.path.join(dest_dir, fname)
    if not os.path.exists(path):
        print("ПРОВЕРКА: %s — файла нет" % fname, flush=True)
        return False
    size = os.path.getsize(path)
    if size < MIN_SIZE.get(fname, 1):
        print("ПРОВЕРКА: %s — размер %d байт меньше нижней границы %d (обрыв или заглушка)" %
              (fname, size, MIN_SIZE.get(fname, 1)), flush=True)
        return False
    if fname in EXPECTED_SHA256:
        print("ПРОВЕРКА: %s — считаю SHA-256 (%.2f ГБ, это минуты)..." % (fname, size / 1e9), flush=True)
        real = sha256_file(path)
        if real.lower() != EXPECTED_SHA256[fname]:
            print("ПРОВЕРКА: %s — SHA-256 НЕ совпал (получили %s)" % (fname, real), flush=True)
            return False
    if fname == "config.json":
        try:
            cfg = json.load(open(path, "r", encoding="utf-8"))
            if cfg.get("model_type") != "qwen2":
                print("ПРОВЕРКА: config.json — model_type=%r, ожидали 'qwen2'" % cfg.get("model_type"), flush=True)
                return False
        except Exception as e:
            print("ПРОВЕРКА: config.json — не парсится: %s" % e, flush=True)
            return False
    if fname == "model.safetensors.index.json":
        try:
            idx = json.load(open(path, "r", encoding="utf-8"))
            if "weight_map" not in idx:
                print("ПРОВЕРКА: index.json — нет weight_map", flush=True)
                return False
        except Exception as e:
            print("ПРОВЕРКА: index.json — не парсится: %s" % e, flush=True)
            return False
    if fname == "tokenizer_config.json":
        try:
            json.load(open(path, "r", encoding="utf-8"))
        except Exception as e:
            print("ПРОВЕРКА: tokenizer_config.json — не парсится: %s" % e, flush=True)
            return False
    print("ПРОВЕРКА: %s — ОК (%s)" % (fname, "%.2f ГБ" % (size / 1e9) if size > 1e9 else "%d байт" % size), flush=True)
    return True


def verify_all(dest_dir, names=None):
    ok = True
    for n, _ in FILES:
        if names is not None and n not in names:
            continue
        if not verify_one(dest_dir, n):
            ok = False
    return ok


def download_file(dest_dir, fname, tries=4):
    """Скачивание с докачкой (Range) и до tries попыток. Таймауты по сети 30с —
    зависание исключено: каждый read живёт не дольше timeout."""
    target = os.path.join(dest_dir, fname)
    partial = target + ".part"
    if os.path.exists(target) and verify_one(dest_dir, fname):
        return True
    url = url_for(fname)
    for attempt in range(1, tries + 1):
        try:
            have = os.path.getsize(partial) if os.path.exists(partial) else 0
            req = urllib.request.Request(url)
            req.add_header("User-Agent", "marfa-student-downloader/1.0 (+local install)")
            if have:
                req.add_header("Range", "bytes=%d-" % have)
            resp = urllib.request.urlopen(req, timeout=30)
            code = resp.getcode()
            if have and code == 206:
                mode = "ab"; done = have          # докачка принята
            else:
                if have:
                    print("  сервер не поддержал докачку (код %s) — начинаю с нуля" % code, flush=True)
                mode = "wb"; done = 0             # либо 200 целиком, либо с нуля
            total_hdr = resp.headers.get("Content-Length")
            total = int(total_hdr) + done if total_hdr else None
            t0 = time.time()
            lastprint = done
            with open(partial, mode) as f:
                while True:
                    chunk = resp.read(1024 * 1024)
                    if not chunk:
                        break
                    f.write(chunk)
                    done += len(chunk)
                    if done - lastprint >= 256 * 1024 * 1024:
                        speed = (done - (have if mode == "ab" else 0)) / max(time.time() - t0, 0.001) / 1048576.0
                        tail = ("%.2f/%.2f ГБ" % (done / 1e9, total / 1e9)) if total else "%.2f ГБ" % (done / 1e9)
                        print("  %s: %s (%.1f МБ/с)" % (fname, tail, speed), flush=True)
                        lastprint = done
            resp.close()
            if os.path.exists(target):
                os.remove(target)
            os.replace(partial, target)
            if verify_one(dest_dir, fname):
                return True
            print("  попытка %d/%d: файл скачался, но проверку не прошёл — перекачка" % (attempt, tries), flush=True)
        except urllib.error.HTTPError as e:
            if e.code == 416 and os.path.exists(partial):
                # докачка не нужна — кусок уже полный
                os.replace(partial, target)
                if verify_one(dest_dir, fname):
                    return True
            print("  попытка %d/%d не удалась: HTTP %s %s" % (attempt, tries, e.code, e.reason), flush=True)
        except Exception as e:
            print("  попытка %d/%d не удалась: %s" % (attempt, tries, e), flush=True)
        time.sleep(3)
    return False


def main():
    argv = list(sys.argv[1:])
    check_only = "--check-only" in argv
    if check_only:
        argv.remove("--check-only")
    only = None
    if "--only" in argv:
        i = argv.index("--only")
        if i + 1 >= len(argv):
            print("--only требует список файлов через запятую")
            sys.exit(3)
        only = [s.strip() for s in argv[i + 1].split(",") if s.strip()]
        for n in only:
            if n not in dict(FILES):
                print("неизвестный файл: %s (доступны: %s)" % (n, ", ".join(n2 for n2, _ in FILES)))
                sys.exit(3)
        del argv[i:i + 2]
    if len(argv) != 1:
        print("запуск: python download_student.py <папка> [--only f1,f2] [--check-only]")
        sys.exit(3)
    dest = argv[0]
    os.makedirs(dest, exist_ok=True)
    print("источник: %s | снимок: %s | папка: %s" % (endpoint(), SNAPSHOT, dest), flush=True)

    if check_only:
        print("режим проверки без скачивания", flush=True)
        sys.exit(0 if verify_all(dest, names=only) else 1)

    # Мусор от старой подсказки: единого model.safetensors в снимке нет — есть 2 шарда.
    legacy = os.path.join(dest, "model.safetensors")
    if os.path.exists(legacy):
        print("удаляю устаревший model.safetensors (%.2f ГБ) — вместо него два шарда + index.json" %
              (os.path.getsize(legacy) / 1e9), flush=True)
        os.remove(legacy)

    fail = False
    for n, _ in FILES:
        if only is not None and n not in only:
            continue
        if not download_file(dest, n):
            print("НЕ СКАЧАЛСЯ: %s — источник %s" % (n, endpoint()), flush=True)
            fail = True
    if fail:
        sys.exit(2)
    # проверяем ровно то, что просили скачать (--only) или весь набор (полная закачка)
    if not verify_all(dest, names=only):
        sys.exit(1)
    print("СТУДЕНТ ГОТОВ: %s (2 шарда + конфиги, SHA-256 шардов сверены)" % dest, flush=True)
    sys.exit(0)


if __name__ == "__main__":
    main()
