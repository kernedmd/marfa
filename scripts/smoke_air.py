# -*- coding: utf-8 -*-
"""Живой smoke эфира: панель с медленным агентом, как на станции.

Проверяет главное: ПОКА /api/chat думает (2 секунды, стадии меняются),
/api/progress отвечает ПАРАЛЛЕЛЬНО и несёт живую стадию и секунды.
Это и есть лекарство от «непонятно, пока не запустишь консоль».
"""
import json
import threading
import time

import requests

from core import progress
from core.agent import Reply
from core.dialog import DialogStore
import web.app as webapp


class SlowAgent:
    """Думает 2 с, стадии меняются — как глаза, потом мозг."""

    def handle(self, text, history=None):
        progress.stage("глаза читают экран: надписи и кнопки…")
        time.sleep(1.0)
        progress.stage("мозг думает — большая модель на CPU…")
        time.sleep(1.0)
        return Reply("Вижу: живой smoke прошёл", source="brain")


def main() -> int:
    webapp.Agent = SlowAgent
    webapp.DIALOGS = DialogStore("/tmp/marfa-smoke-dialog")
    t = threading.Thread(
        target=lambda: webapp.app.run(host="127.0.0.1", port=5017,
                                      debug=False, threaded=True),
        daemon=True)
    t.start()
    time.sleep(1.0)

    base = "http://127.0.0.1:5017"
    ok = True

    # 1) длинный ход в фоне
    result = {}

    def ask():
        r = requests.post(base + "/api/chat", json={
            "text": "посмотри и расскажи", "session": "smoke1"}, timeout=30)
        result["data"] = r.json()

    th = threading.Thread(target=ask)
    th.start()

    # 2) пока думает — эфир живой (3 замера с паузами)
    seen = []
    time.sleep(0.4)
    for _ in range(3):
        p = requests.get(base + "/api/progress?session=smoke1",
                         timeout=5).json()
        seen.append((p["busy"], p["stage"], p["elapsed"], p["mine"]))
        time.sleep(0.6)
    th.join()

    print("живые замеры эфира во время думания:")
    for b, st, el, mine in seen:
        print("  busy=%s mine=%s elapsed=%4.1fs stage=%s" % (b, mine, el, st))
    ok &= all(b for b, _, _, _ in seen)
    ok &= seen[0][2] < seen[-1][2]                     # секунды растут
    ok &= any("читают экран" in s for _, s, _, _ in seen)
    ok &= any("мозг думает" in s for _, s, _, _ in seen)
    ok &= all(m for _, _, _, m in seen)

    d = result["data"]
    print("ответ:", json.dumps({k: d[k] for k in ("reply", "secs", "source",
                                                  "source_label")},
                               ensure_ascii=False))
    ok &= d["source"] == "brain" and d["source_label"] == "мозг"
    ok &= 1.8 <= d["secs"] <= 4.0

    # 3) после ответа эфир свободен, штамп в памяти диалога
    p = requests.get(base + "/api/progress", timeout=5).json()
    ok &= p["busy"] is False
    ok &= p["last"]["secs"] == d["secs"] and p["last"]["source"] == "мозг"
    turns = webapp.DIALOGS.turns("smoke1")
    ok &= turns[1]["meta"]["secs"] == d["secs"]

    # 4) история со штампами (F5)
    hist = requests.get(base + "/api/dialog/smoke1", timeout=5).json()["turns"]
    ok &= hist[1]["secs"] == d["secs"] and hist[1]["src_label"] == "мозг"

    print("\nИТОГ:", "ЭФИР ЖИВ — чат видит думание живьём" if ok else "ПОЛОМА")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
