# -*- coding: utf-8 -*-
r"""tests/test_sync_button.py — статические проверки кнопки 80_sync_github.bat.

Кнопка работает на Z440 (cmd.exe), на станции не запускается — поэтому
проверяем текст файла. Урок первого прогона (19.11.2026, ночь): bundle
скачался, но не влился, а кнопка v2.1 замаскировала сбой и продолжила
пушить. v2.2 не имеет права повторять это — что и фиксируют тесты.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BAT = ROOT / "scripts" / "80_sync_github.bat"


def _text() -> str:
    return BAT.read_text(encoding="utf-8")


def test_button_exists():
    assert BAT.is_file(), "кнопка scripts/80_sync_github.bat пропала"


def test_dirty_tree_committed_before_merges():
    """Грязь коммитится ДО слияний — merge не откажется поверх фантомных правок."""
    t = _text()
    assert ":clean_tree" in t
    assert "локальные правки перед слиянием" in t
    # чистка дерева вызывается и перед GitHub-слиянием, и перед приёмом bundle
    assert t.count("call :clean_tree") >= 2


def test_failures_still_honest():
    """То, что автомат не осилил — честная остановка, а не маскировка."""
    t = _text()
    assert "git merge --abort" in t
    assert t.count("покажи архитектору") >= 2  # усыновление и авторазрешение
    # старый маскирующий фолбэк удалён
    assert "(завершение)" not in t


def test_adoption_for_unrelated_histories():
    """Несвязанные истории — усыновление автоматом (v3.0).

    Урок второго прогона: дом/GitHub/станция — три несвязанные линии,
    каждый общий файл = add/add, который -X theirs не решает.
    """
    t = _text()
    assert "git merge-base HEAD FETCH_HEAD" in t  # связность проверяется ДО слияния
    assert "усыновление" in t
    assert "git merge --no-commit --allow-unrelated-histories FETCH_HEAD" in t
    assert "git checkout FETCH_HEAD -- ." in t   # дерево архитектора целиком


def test_related_conflicts_autoresolved():
    """Конфликт при общей истории — «архитектор сильнее» без ручного труда."""
    t = _text()
    assert "git checkout --theirs -- ." in t
    assert "авторазрешение" in t
    # внутри :import_bundle порядок: «уже вросла» -> усыновление -> авторазрешение
    sub = t[t.index(":import_bundle"):]
    assert sub.index("уже вросла") < sub.index("усыновление") < sub.index("авторазрешение")


def test_sentinel_after_import():
    """После приёма bundle код архитектора обязан доехать — иначе честный сбой."""
    t = _text()
    assert "IMPORTED" in t
    assert "не доехал" in t


def test_push_failure_not_fatal():
    """Провал пуша в GitHub — предупреждение, петля (bundle) продолжается."""
    t = _text()
    assert "Пуш не прошёл" in t
    # после предупреждения о пуше кнопка продолжает собирать bundle
    assert t.index("Пуш не прошёл") < t.index("git bundle create")


def test_heavy_llama_builds_out_of_git():
    """Сборки llama-cuda/llama-vulkan — рантайм: в игноре и выводятся из git."""
    t = _text()
    assert "llama-cuda/" in t and "llama-vulkan/" in t  # .gitignore кнопкой
    assert "git rm -r -q --cached llama-cuda llama-vulkan" in t


def test_self_update_via_temp_copy():
    """Кнопка работает с временной копии — петля может обновить её саму.

    v3.3: самодиагностика ПО ПУТИ (%~f0), а не по переменной окружения —
    переменная жила между нажатиями в одном окне cmd, и второй запуск
    шёл прямо из дерева, который слияние переписывало на ходу.
    Круг 19 (24.11): рестарт остался только в запускнике 0a — шаг 3z
    больше не перезапускается и не перезаписывает работающий файл
    (закон смены тела): первый живой прогон самообновления упал именно
    на перезаписи — cmd читает батник по смещению байтов.
    """
    t = _text()
    assert 'if /i "%~f0"=="%TEMP%\\marfa_sync_run.bat" goto :run' in t
    assert "%TEMP%\\marfa_sync_run.bat" in t
    # рестарт только запускник 0a: 3z объявляет смену тела, но не
    # перезапускается (закон круга 19 — смена тела без падения)
    assert t.count('cmd /c ""%TEMP%\\marfa_sync_run.bat" %*"') == 1


def test_auto_mode_for_scheduler():
    """v3.4: /auto — режим для задачи «Марфа-синхронизация» (каждые 2 часа).

    Планировщик зовёт кнопку без человека: пауз быть не должно, а аргумент
    переживает рестарт запускника (0a). Круг 19: 3z больше не
    перезапускается — новое тело поднимает сам планировщик следующим
    прогоном, и /auto доезжает до конца без повторных входов.
    Круг 21: третья пауза — у стража одной петли (ручной прогон должен
    УСПЕТЬ прочитать «прогон уже идёт» до закрытия окна; /auto молчит).
    """
    t = _text()
    # аргумент разбирается после :run — в потомке, у которого %1 есть
    assert 'if /i "%~1"=="/auto" set "MARFA_SYNC_AUTO=1"' in t
    # все три паузы (страж, успех и :fail) уважают автоматный режим
    assert t.count("if not defined MARFA_SYNC_AUTO pause") == 3
    # голых pause не осталось — планировщик не зависнет в невидимом окне
    bare = [ln for ln in t.splitlines()
            if ln.strip() == "pause"]
    assert not bare


def test_fat_history_surgery():
    """История толще 100 МБ — пересборка автоматом (v3.1).

    Урок третьего прогона: тяжёлые сборки llama застряли в истории
    первого снимка; rm --cached чистит только будущее, пуш падает,
    bundle не пролезает в чат.
    """
    t = _text()
    assert "git count-objects -v" in t            # измерение толщины истории
    assert "GTR 102400" in t                      # порог: 100 МБ
    assert "call :surgery" in t and "\n:surgery" in t
    assert "Move-Item -LiteralPath .git" in t     # старая история -> .git_old\
    assert ".git_old/" in t                       # и в игнор-списке кнопки
    # пересборка не тянет старую историю с GitHub: пуш с заменой
    assert "git push --force origin main" in t
    assert 'if "%SURGERY%"=="1" (' in t           # флаг разведён по шагам
    # ничего не удаляется насовсем — старая история сохранена
    assert "можно удалить через неделю" in t


def test_body_change_is_announcement_krug19():
    """Круг 19 «СМЕНА ТЕЛА БЕЗ ПАДЕНИЯ» (24.11): 3z — объявление, не операция.

    Урок первого живого самообновления (лог дома 24.11 09:32): старый 3z
    перезаписывал РАБОТАЮЩУЮ временную копию и перезапускался ею — cmd
    читает батник по смещению байтов, тело сменилось под ногами, парсер
    упал в середину строки нового тела («was unexpected at this time»).
    Прогон №2 дошёл до ГОТОВО только вторым нажатием. Требование
    Создателя «без второго нажатия» (v3.2) теперь исполняется иначе:
    петлю доезжает СТАРОЕ тело, новое вступает в силу следующим
    запуском (планировщик /auto — каждые 2 часа).
    """
    t = _text()
    assert "rem BTN_VER" in t                     # исторический маркер в шапке
    assert "marfa_sync_run.bat" in t              # запуск через временную копию
    # 3z стоит после приёма bundle и до чистки дома
    assert t.index(":no_selfupdate") > t.index(":import_bundle")
    sub = t[t.index(":: ---------- 3z."):t.index("\n:no_selfupdate")]
    # закон: смена тела — объявление; операций над файлами и рестарта нет
    for banned in ("copy /y", "cmd /c", "exit /b", "set /a"):
        assert banned not in sub, "в 3z вернулась операция над собой: " + banned
    # тела сверяются побайтно: работающее (%~f0) против дерева
    assert 'fc /b "%~f0"' in sub
    assert "Смена тела" in sub


def test_fat_outgoing_bundles_autoremoved():
    """Тяжёлые bundles (>100 МБ) эпохи жирной истории удаляются сами."""
    t = _text()
    assert "104857600" in t                       # порог: 100 МБ
    assert 'del /q "outgoing\\%%~nxf"' in t
    # чистка — до сборки нового bundle
    assert t.index("104857600") < t.index("git bundle create")


def test_ingrown_bundles_autoremoved():
    """Вросшие и принятые bundles убираются из incoming сами (v3.3).

    Урок прогона 04:17: пять отработанных bundles копились в incoming.
    """
    t = _text()
    sub = t[t.index(":import_bundle"):]
    assert sub.count("del /q %1") >= 3          # вросла + усыновление + слияние
    # удаление только после успеха; сбой приёма — файл остаётся для разбора
    assert sub.index("уже вросла") < sub.index("del /q %1")


# ---------------------------------------------- круг 28 «ГОЛОС УПАВШЕГО ШАГА»

def test_fail_names_the_step_krug28():
    """Ф171 ГОЛОС УПАВШЕГО: :fail называет шаг и печатает живую диагностику.

    Урок 27.11: кнопка v3.8 умерла сразу после шапки — git
    count-objects не ответил в C:\\Marfa, findstr вернул ошибку, а
    «if errorlevel 1 goto :fail» после ИЗМЕРЕНИЯ убил петлю без
    единого слова: Создатель увидел «ОСТАНОВКА ПО ОШИБКЕ» и ни
    одной причины. Закон: каждая ступень носит имя (STEP), :fail
    повторяет имя упавшего шага и зовёт git говорить самому —
    версия и ответ count-objects без подавления ошибок.
    """
    t = _text()
    assert t.count('set "STEP=') >= 9           # все ступени + запасной в :fail
    assert "Упал шаг: %STEP%" in t              # :fail повторяет имя
    fail = t[t.index("\n:fail\n"):]
    assert "git --version 2>&1" in fail         # git представляется
    assert "git count-objects -v 2>&1" in fail  # живой диагноз репозитория
    assert ".git: ПАПКИ НЕТ" in fail            # и наличие самого дома git
    assert ".git_old" in fail                   # след хирургии виден сразу


def test_measurement_is_not_a_verdict_krug28():
    """Ф172 ИЗМЕРЕНИЕ — НЕ ПРИГОВОР.

    Смерть блока 0b-0 осталась только у surgery (настоящей работы);
    не измерилось — честное сообщение, петля едет к :ensure_repo.
    Заодно возвращено обещание v3.0 «репозиторий создаётся сам при
    первом запуске», случайно убитое v3.1: без .git count-objects
    молчал, а смерть шла РАНЬШЕ ensure_repo — петля не могла даже
    принять собственное лекарство из incoming.
    """
    t = _text()
    # старый смертельный шаблон удалён: измерение больше не убивает петлю
    assert "if %GSIZE% GTR 102400 call :surgery" not in t
    sub = t[t.index(":: ---------- 0b-0."):t.index(":: ---------- 0b. Репозиторий")]
    # смерть возможна только внутри surgery-ветки, после настоящего вызова
    assert "call :surgery" in sub
    assert sub.index("call :surgery") < sub.index("if errorlevel 1 goto :fail")
    # не измерилось — честное сообщение, а не тишина и не смерть
    assert "не измерилась" in sub


def test_git_introduces_itself_krug28():
    """Ф173 GIT ПРЕДСТАВЛЯЕТСЯ ПЕРВЫМ.

    Урок 27.11: без git в PATH старая кнопка выдавала каскад fatal
    от каждого вызова по очереди. Теперь один честный отказ до
    работы с именем лекарства (кнопка 05), и вызывающий проверяет
    :ensure_repo — отказ больше не глотается.
    """
    t = _text()
    # срез по САМИМ меткам (не по call-строкам и не по комментариям)
    repo = t[t.index("\n:ensure_repo\n"):t.index("\n:ensure_gitignore\n")]
    assert "git --version" in repo
    assert "05_install_git.bat" in repo          # лекарство названо по имени
    # отказ :ensure_repo слышит вызывающий — честная остановка с шагом
    assert "call :ensure_repo\nif errorlevel 1 goto :fail" in t


def test_outgoing_bundle_honest_krug28():
    """Ф174 ЧЕСТНЫЙ ОТВЕТНЫЙ BUNDLE.

    До v3.9 шаг [7] говорил «Bundle готов» поверх провала сборки, и
    финал звал в чат несуществующий файл. Теперь сборка проверяется:
    не собрался — честный [x] и финал без «Положи в чат».
    """
    t = _text()
    assert "BUNDLE_OK" in t
    sub = t[t.index("git bundle create"):]
    assert "НЕ собрался" in sub                  # честный отказ есть
    assert 'if "%BUNDLE_OK%"=="1" (' in t        # финал conditional
    # а путь успеха не тронут: старое приглашение в чат живо
    assert "Положи outgoing\\marfa-%STAMP%.bundle в чат архитектору" in t


def test_commits_under_control_krug28():
    """Ф175 КОММИТ ПОД КОНТРОЛЕМ.

    Коммиты дома (первый снимок и синхронизация) проверяются: не
    создался — честная остановка с именем шага, а не «Коммит
    создан» поверх провала (закон v2.2 «не маскируй сбой» доехал
    до последних двух непроверенных команд кнопки).
    """
    t = _text()
    assert "первый коммит не создался" in t
    assert "коммит синхронизации не создался" in t
    # оба отказа живут внутри своих проверок и ведут в :fail
    assert t.index("первый коммит не создался") < t.index('set "STEP=2:')
    assert t.index("коммит синхронизации не создался") < t.index(":: ---------- 5. Пуш")


def test_launcher_frozen_krug28():
    """Закон круга 19: запускник (до exit /b %ERRORLEVEL%) заморожен.

    Родитель, ждущий на cmd /c, читает exit /b по смещению байтов
    старого тела — запускник не меняется НИКОГДА, какую бы версию
    ни несло тело. Золотой якорь перехода v3.8 -> v3.9: sha256
    замороженной зоны (та же граница, что в круге 21).
    """
    import hashlib
    raw = _text()  # уже нормализовано: \r\n -> \n (блоб git тоже LF)
    end = raw.index("\nexit /b %ERRORLEVEL%\n") + len("\nexit /b %ERRORLEVEL%\n")
    launcher = raw[:end]
    assert hashlib.sha256(launcher.encode("utf-8")).hexdigest() == (
        "fee9bd2263e3e897283d443695858f5c68d7a241352880189e9c7ec644c46782"
    ), "запускник кнопки изменился — закон круга 19 (Ф110) нарушен"
