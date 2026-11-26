# -*- coding: utf-8 -*-
r"""tests/test_quiet_loop_circle.py — круг 21 «ТИХАЯ ПЕТЛЯ» (Ф115–Ф117).

Урок приёма krug19 (живой лог дома 24.11 10:16, отчёт Создателя
«Бандл пока не отправляю — есть такая сложность с предыдущим»):
fetch из бандла прошёл (1710 объектов, main -> FETCH_HEAD), но git
gc --auto, которого зовут сами fetch и merge, не смог удалить старый
pack-файл — его держал другой процесс (ручной прогон сошёлся с
автопрогоном планировщика /auto, каждые 2 часа, на одном .git) — и
спросил «Unlink of file ... Should I try again? (y/n)». Вопрос
интерактивный; кнопка отвечать не может; Создатель жал «y» — файл
держали всё это время — петля зависла навсегда. Вторая живая болезнь
петли за один день: круг 19 лечил краш на смене тела, круг 21 лечит
вечное ожидание на вопросе.

Два закона круга 21 (кнопка 80 v3.7, протокол v1.11):
  Ф115 «ТИХИЙ GIT» — петля не имеет права зависнуть на вопросе, на
        который у неё нет ответа: авто-gc выключен (git config
        gc.auto 0 — причина удалена, а не обработана; история дома —
        3,8 МБ кода, чистка — дело архитектора на станции), терминальные
        вопросы запрещены (GIT_TERMINAL_PROMPT=0: пуш честно падает
        с сообщением, бандл собирается всё равно);
  Ф116 «СТРАЖ ОДНОЙ ПЕТЛИ» — второй прогон не стартует, пока жив
        первый: lock-файл %TEMP%\marfa_sync.pid с PID; живой владелец —
        честное сообщение и выход (мёртвый lock — окно закрыли
        крестиком — забирается сам); powershell не сказал PID — страж
        спит, петля едет как раньше (честная деградация);
  Ф117 «ЗОЛОТОЙ ЯКОРЬ ТИХОЙ ПЕТЛИ» — законы пришиты к исходнику и
        истории: переход v3.6 -> v3.7 испытан по закону круга 19
        (fc /b видит различие — объявление без операций; замороженная
        зона идентична прошлой версии), болезнь названа в теле кнопки
        и в протоколе, вынуть тихо нельзя.

Нумерация: Ф112–Ф114 — круг 20; круг 21 идёт с Ф115 (правило БЭКЛОГА).
"""
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BAT = ROOT / "scripts" / "80_sync_github.bat"
GITIGNORE = ROOT / ".gitignore"
PROTOCOL = ROOT / "docs" / "SYNC_PROTOCOL_v1.md"

# Последнее тело v3.6 в истории: коммит книг круга-20 (266d294). Золотой
# якорь перехода приколочен к конкретной паре версий (как sha256
# запускника в круге 19): HEAD растёт с каждым кругом, а переход
# v3.6 -> v3.7 — факт истории, он не переоткрывается заново.
KRUG20_BOOKS_COMMIT = "266d294"
# Последнее тело v3.7 в истории: коммит книг круга-21 (28162d0) —
# продление круга 22: рабочая копия уже несёт v3.8, и переход
# v3.6 -> v3.7 сверяется по ДВУМ телам из истории, а новый переход
# v3.7 -> v3.8 якорится в своём круге (test_root_lock_circle.py)
KRUG21_BOOKS_COMMIT = "28162d0"


def _text() -> str:
    return BAT.read_text(encoding="utf-8").replace("\r\n", "\n")


# ------------------------------------------------------------------- Ф115

def test_auto_gc_disabled_by_law():
    """Причина удалена: git config gc.auto 0 в :ensure_repo кнопки.

    «Should I try again?» приходит из gc (repack не может удалить
    старый pack). Нет авто-gc — нет вопроса: требование исполняется
    удалением причины, а не обработкой следствия (урок круга 19
    работает и здесь). Идемпотентно: каждый прогон ставит одно и то же.
    """
    t = _text()
    sub = t[t.index(":ensure_repo"):t.index("\n:ensure_gitignore")]
    assert "git config gc.auto 0" in sub, "авто-gc не выключен — вопрос может вернуться"


def test_terminal_prompts_disabled():
    """GIT_TERMINAL_PROMPT=0 стоит в теле ДО любого git-вызова петли.

    Терминальные вопросы (кредиты пуша) — тот же класс болезни:
    интерактивный вопрос в неинтерактивной петле. Пуш честно падает
    с сообщением, бандл собирается всё равно.
    """
    t = _text()
    assert 'set "GIT_TERMINAL_PROMPT=0"' in t
    # до первого РЕАЛЬНОГО git-вызова петли (rem-комментарии не в счёт):
    # первая исполнимая команда основного потока — замер толщины истории
    run = t.index("\n:run")
    first_git = t.index("git count-objects", run)
    assert t.index('set "GIT_TERMINAL_PROMPT=0"') < first_git, \
        "тихий режим должен включаться до первого git-вызова"


def test_button_remembers_the_hang():
    """Болезнь пришита к исходнику: кнопка несёт улику зависания 24.11.

    «Should I try again?», время живого лога и имя круга — в теле
    кнопки; тихо вырезать память нельзя (якорь по исходнику, по
    образцу круга 19).
    """
    t = _text()
    assert "Should I try again" in t
    assert "24.11 10:16" in t
    assert "ТИХАЯ ПЕТЛЯ" in t


def test_protocol_names_quiet_loop_law():
    """Протокол называет оба закона круга 21 — книга не молчит.

    Урок круга 17: исключение без причины — забытость, с причиной и
    якорем — закон. Тихий git и страж одной петли описаны в протоколе,
    включая разморозку («n» на вопросе — gc пропустит удаление).
    Продление круга 22: заголовок книги вырос до v1.12 (закон
    «приём обновляет файлы, не процессы»), законы круга 21 — в ней.
    Продление круга 28: заголовок вырос до v1.13 (закон «голос
    упавшего шага»), законы кругов 21 и 22 — в ней.
    """
    doc = PROTOCOL.read_text(encoding="utf-8")
    assert "ПРОТОКОЛ СИНХРОНИЗАЦИИ v1.13" in doc
    assert "ТИХИЙ GIT" in doc and "ОДНА ПЕТЛЯ" in doc
    assert "gc.auto 0" in doc
    assert "Should I try again" in doc
    assert "marfa_sync.pid" in doc
    assert "n" in doc and "идемпотентен" in doc  # разморозка названа


# ------------------------------------------------------------------- Ф116

def test_guard_locks_and_checks_owner():
    """Страж одной петли: lock с PID, проверка жизни владельца, честный выход.

    Второй прогон (ручной поверх /auto) не дерётся с первым за .git:
    живой PID cmd — сообщение с номером и выход; мёртвый — lock
    забирается, петля едет. Захват lock — до баннера и до шагов петли.
    """
    t = _text()
    guard = t[t.index(":: ---------- 0e."):t.index("\n:no_lock")]
    assert 'set "SYNC_LOCK=%TEMP%\\marfa_sync.pid"' in guard
    assert 'for /f %%p in (\'powershell -NoProfile -Command' in guard \
        and "ParentProcessId" in guard      # PID свой — через родителя powershell
    assert 'tasklist /FI "PID eq %LOCKPID%"' in guard \
        and 'findstr /i "cmd.exe"' in guard  # живость = процесс cmd с тем PID
    assert "Прогон уже идёт" in guard and "один дом — одна петля" in guard
    # честный выход: /auto молчит, ручной — пауза, чтобы прочитать
    assert "if not defined MARFA_SYNC_AUTO pause" in guard
    # страж стоит до баннера петли и до первого шага
    assert t.index(":: ---------- 0e.") < t.index("МАРФА — синхронизация Z440")


def test_guard_never_touches_foreign_lock():
    """Чужой lock свят: ветка «прогон уже идёт» выходит БЕЗ удаления.

    Урок круга 20 (неприкосновенность контента) в петле: снимать lock
    имеет право только владелец (LOCKED ставится ПОСЛЕ записи своего
    PID); спящий страж (powershell не сказал PID) lock не пишет и не
    снимает. Снятие — в конце успеха и в :fail, всегда под «if defined
    LOCKED».
    """
    t = _text()
    guard = t[t.index(":: ---------- 0e."):t.index("\n:no_lock")]
    busy = guard[guard.index("Прогон уже идёт"):]
    assert "del /q" not in busy, "ветка «уже идёт» не смеет трогать чужой lock"
    # LOCKED=1 ставится только в :lock_take — после записи своего PID
    assert guard.index(':lock_take') < guard.index('set "LOCKED=1"')
    # снятие — только владельцем, на обоих путях выхода
    assert t.count('if defined LOCKED del /q "%SYNC_LOCK%"') == 2
    before_eos = t[t.index("if defined LOCKED del /q"):t.index("goto :eof")]
    assert "if not defined MARFA_SYNC_AUTO pause" in before_eos
    # спящий страж не пишет lock (MYPID пуст — запись мимо)
    assert 'if not defined MYPID (' in guard


def test_guard_survives_crashed_owner():
    """Мёртвый lock забирается: tasklist не нашёл cmd — :lock_take.

    Окно закрыли крестиком — lock остался с мёртвым PID; следующий
    прогон видит «PID не жив» и перезаписывает lock своим. Самолечение,
    без ручной чистки.
    """
    t = _text()
    guard = t[t.index(":: ---------- 0e."):t.index("\n:no_lock")]
    # лестница: не нашёл процесс (errorlevel 1) -> забираю lock
    assert 'if errorlevel 1 goto :lock_take' in guard
    assert '>\"%SYNC_LOCK%\" echo %MYPID%' in guard


# ------------------------------------------------------------------- Ф117

def test_transition_v3_6_to_v3_7_by_fc_from_history():
    """ГЛАВНЫЙ ЯКОРЬ: переход v3.6 -> v3.7 испытан по закону круга 19.

    Оба тела берутся из git-истории (продление круга 22: рабочая
    копия уже несёт v3.8 — переход v3.6 -> v3.7 врос в историю и
    сверяется по паре коммитов: книги круга-20 — последнее тело
    v3.6, книги круга-21 — последнее тело v3.7). fc /b эквивалент:
    байты различаются -> errorlevel 1 -> смена ОБЪЯВЛЯЕТСЯ, петля
    доезжает на старом теле (Ф109 жив).
    Замороженная зона (запускник) идентична байт-в-байт — переход не
    трогает запускник ни при каких версиях (Ф110 жив).
    """
    # новое тело из истории: книги круга-21 — последнее тело v3.7
    tree = subprocess.run(
        ["git", "-C", str(ROOT), "show",
         KRUG21_BOOKS_COMMIT + ":scripts/80_sync_github.bat"],
        capture_output=True, text=True, encoding="utf-8").stdout.replace("\r\n", "\n")
    # старое тело из истории: книги круга-20 — последнее тело v3.6
    old = subprocess.run(
        ["git", "-C", str(ROOT), "show",
         KRUG20_BOOKS_COMMIT + ":scripts/80_sync_github.bat"],
        capture_output=True, text=True, encoding="utf-8").stdout.replace("\r\n", "\n")
    assert "rem ТЕЛО КНОПКИ 3.6" in old, "история должна нести тело v3.6 (книги круга-20)"
    assert "rem ТЕЛО КНОПКИ 3.7" in tree, "история должна нести тело v3.7 (книги круга-21)"
    # fc /b: тела различаются -> объявление (не молчание и не операция)
    assert old != tree, "тела обязаны различаться — иначе перехода нет"
    # замороженная зона идентична: родитель на cmd /c читает exit /b
    # на прежнем смещении при ЛЮБОМ новом теле (Ф110)
    def frozen(s):
        end = s.index("\nexit /b %ERRORLEVEL%\n") + len("\nexit /b %ERRORLEVEL%\n")
        return s[:end]
    assert frozen(old) == frozen(tree), \
        "замороженная зона менялась между v3.6 и v3.7 — закон Ф110 нарушен"


def test_pamyat_out_of_git():
    """Остатки самоделок pamять\\ не поедут в git (инвентаризация 10:16).

    Живой лог дома показал: pamять — 4 файла, 530 Б, «В GIT» — остатки
    эпохи до journal\\lessons.json (уроки живут в journal/, это воля
    Создателя и она версионируется; самоделки — рантайм). Закон в
    .gitignore станции; с merge'ом доедет до дома и шаг 4 (git add -A)
    перестанет их видеть.
    """
    gi = GITIGNORE.read_text(encoding="utf-8")
    # строки-ПРАВИЛА (не комментарии): самоделки — в игноре, журнал — нет
    rules = [ln.strip() for ln in gi.splitlines()
             if ln.strip() and not ln.lstrip().startswith("#")]
    assert "pamять/" in rules, "остатки самоделок должны быть в игноре"
    # journal/ в игноре быть НЕ должно — уроки версионируются (круг 20)
    assert "journal/" not in rules, "журнал уроков версионируется — игнор запрещён"


def test_freeze_and_ghost_survive_krug21():
    """Круг 21 не разбудил призраков круга 19 (продление законов).

    Старый маркер «rem BTN_VER 3.5» — по-прежнему ровно один и в
    замороженной шапке; новый страж не добавил строк старого формата;
    3z не тронут (запрет операций над собой жив).
    """
    t = _text()
    hits = [ln for ln in t.split("\n") if "rem BTN_VER" in ln]
    assert hits == ["rem BTN_VER 3.5"]
    sub = t[t.index(":: ---------- 3z."):t.index("\n:no_selfupdate")]
    for banned in ("copy /y", "cmd /c", "exit /b", "set /a"):
        assert banned not in sub, "в 3z вернулась операция над собой: " + banned
