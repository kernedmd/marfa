@echo off
chcp 65001 >nul
title МАРФА — синхронизация дома с GitHub (одна кнопка, v3.5)
rem BTN_VER 3.5

rem ============================================================
rem  v3.5 (24.11.2026): двухступенчатый приём bundle — main, при
rem  отсутствии ветки в bundle пробуем HEAD. Урок бандла-1930:
rem  финальный bundle круга-17 был собран по HEAD, «git fetch
rem  <bundle> main» падал «couldn't find remote ref main», и кнопка
rem  называла живой bundle битым — Создатель застрял с кольцом 17.
rem  v3.4 (20.11.2026): режим /auto для планировщика — задача
rem  «Марфа-синхронизация» (региструется start_marfa.py
rem  --в-планировщик) сама зовёт эту кнопку каждые 2 часа: без
rem  пауз, аргумент /auto переживает оба рестарта кнопки.
rem  Требование Создателя: «всё, что мы делаем, запускается автоматом».
rem  v3.3 (20.11.2026): incoming не копится + кнопка неуязвима к окну.
rem  Урок прогона 04:17: в одном окне cmd переменная запуска жила
rem  между нажатиями — кнопка шла прямо из дерева, который слияние
rem  мог переписать на ходу, а самообновление 3z стопорилось. Теперь
rem  кнопка опознаёт себя по пути (%~f0), счётчик перезапусков
rem  обнуляется на каждом нажатии, а вросшие/принятые bundles
rem  удаляются из incoming\ — папка не копится.
rem  v3.2 (20.11.2026): один прогон до конца + ноль ручного труда.
rem  Требование Создателя: «уже требую автоматизацию». Если слияние
rem  принесло НОВУЮ версию этой кнопки — прогон перезапускается ею
rem  сам (шаг 3z): второе нажатие не нужно, замена файла руками не
rem  нужна никогда. Тяжёлые bundles эпохи жирной истории (>100 МБ)
rem  из outgoing\ кнопка удаляет сама. v3.1 (20.11.2026): автолечение
rem  Урок третьего прогона: в первый снимок дома попали тяжёлые
rem  сборки llama (llama-cuda ~700 МБ в истории git) — пуш в GitHub
rem  падает (curl 55 + лимит 100 МБ), а bundle не пролезает в чат.
rem  Лечение автоматом: если история репозитория толще 100 МБ —
rem  пересборка (старая уезжает в .git_old\, ничего не удаляется),
rem  свежий снимок + усыновление станции, GitHub обновляется
rem  с заменой (push --force — частный репозиторий, хозяин один).
rem  v3.0 (19.11.2026, ночь): всё автоматом — усыновление.
rem  Урок второго прогона: дом, GitHub и станция — три НЕСВЯЗАННЫЕ
rem  истории, каждый общий файл = конфликт «оба добавили», а
rem  «-X theirs» такие конфликты НЕ решает (проверено в песочнице).
rem  Лечение: разовое усыновление — merge --no-commit, дерево
rem  архитектора принимается целиком (checkout FETCH_HEAD -- .),
rem  уникальные файлы дома остаются, коммит сшивает истории.
rem  Дальше все слияния идут по общей базе — конфликтов add/add
rem  больше не бывает. Ручного труда: положить bundle в incoming\
rem  и нажать кнопку.
rem  Протокол: docs\SYNC_PROTOCOL_v1.md (v1.9, разделы 2, 3, 6 и 8)
rem ============================================================

:: ---------- 0a. Временная копия: кнопка сможет обновить себя в петле ----------
rem Самодиагностика ПО ПУТИ, без переменной окружения: переменная жила
rem между нажатиями в одном окне cmd — второй запуск шёл прямо из дерева,
rem который слияние переписывало на ходу, а 3z в том же окне не срабатывал.
if /i "%~f0"=="%TEMP%\marfa_sync_run.bat" goto :run
del /q "%TEMP%\marfa_sync_run.bat" >nul 2>&1
copy /y "%~f0" "%TEMP%\marfa_sync_run.bat" >nul 2>&1
if not exist "%TEMP%\marfa_sync_run.bat" goto :run
echo [0] Работаю с временной копии — репозиторий может обновить кнопку сам
set "MARFA_SYNC_TURNS=1"
rem /auto (планировщик) передаётся дальше — пауз не будет и в потомках
cmd /c ""%TEMP%\marfa_sync_run.bat" %*"
exit /b %ERRORLEVEL%

:run
cd /d C:\Marfa
title МАРФА — синхронизация дома с GitHub (одна кнопка, v3.7)
rem ТЕЛО КНОПКИ 3.7
rem ------------------------------------------------------------
rem  v3.7 (24.11.2026, круг 21 «ТИХАЯ ПЕТЛЯ»): приём krug19 завис
rem  НАВСЕГДА — git gc --auto (его зовут сами fetch и merge) спросил
rem  «Should I try again?» про залоченный pack-файл (лог дома
rem  24.11 10:16: ручной прогон сошёлся с автопрогоном планировщика
rem  на одном .git) — вопрос интерактивный, кнопка отвечать не может.
rem  Два закона круга 21: (1) ТИХИЙ GIT — авто-gc выключен, терминальные
rem  вопросы запрещены: петля не может зависнуть на вопросе, на который
rem  у неё нет ответа; (2) ОДНА ПЕТЛЯ — страж с lock-файлом: второй
rem  прогон (ручной поверх /auto) не стартует, пока жив первый.
rem  v3.6 (24.11.2026, круг 19 «СМЕНА ТЕЛА БЕЗ ПАДЕНИЯ»): первый
rem  живой прогон самообновления упал на смене тела — старый шаг 3z
rem  перезаписал РАБОТАЮЩУЮ временную копию и позвал рестарт; cmd.exe
rem  читает батник по смещению байтов, тело под процессом сменилось,
rem  и парсер упал в середину строки нового тела («was unexpected at
rem  this time», лог дома 24.11 09:32; прогон №2 доехал до ГОТОВО
rem  только со второго нажатия). Закон круга 19: работающий файл не
rem  трогаем НИКОГДА — 3z сверяет тела побайтно, объявляет смену и
rem  доезжает петлю на старом теле; новое вступает в силу со
rem  следующего запуска (планировщик /auto — каждые 2 часа).
rem  Запускник (строки до :run) заморожен байт-точно: родитель,
rem  ждущий на cmd /c, читает exit /b на прежнем смещении при любом
rem  новом теле. Живая версия — этой строкой и заголовком окна;
rem  старый маркер версии остался в замороженной шапке один раз и
rem  навсегда: новые строки того формата разбудили бы призрака
rem  перезаписи в старых кнопках, живших поиском по нему.
rem ------------------------------------------------------------
if /i "%~1"=="/auto" set "MARFA_SYNC_AUTO=1"

rem ТИХИЙ GIT (закон круга 21): петля не имеет права зависнуть на
rem вопросе, на который у неё нет ответа. Терминальные вопросы git
rem (кредиты) запрещены — пуш честно падает с сообщением, бандл
rem собирается всё равно. А «Should I try again?» про залоченный
rem pack — от gc --auto: причина удалена ниже (gc.auto=0 в :ensure_repo).
set "GIT_TERMINAL_PROMPT=0"

:: ---------- 0e. Страж одной петли: один дом — одна петля (закон круга 21) ----------
rem Урок 24.11 10:16: два прогона на одном .git держат pack-файлы друг
rem друга — gc не может удалить старый pack и спрашивает «Should I try
rem again?» бесконечно. Закон: второй прогон не стартует, пока жив
rem первый. Lock с PID: мёртвый (окно закрыли крестиком) — lock
rem забирается, петля едет; powershell не сказал PID — страж спит,
rem петля едет как раньше (честная деградация, рассказать архитектору).
set "SYNC_LOCK=%TEMP%\marfa_sync.pid"
set "MYPID="
for /f %%p in ('powershell -NoProfile -Command "(Get-CimInstance Win32_Process -Filter ('ProcessId={0}' -f $PID)).ParentProcessId"') do set "MYPID=%%p"
if not defined MYPID (
  echo [i] Страж петли спит ^(не вижу свой PID^) — работаю без него, расскажи архитектору
  goto :no_lock
)
if not exist "%SYNC_LOCK%" goto :lock_take
set /p LOCKPID=<"%SYNC_LOCK%"
tasklist /FI "PID eq %LOCKPID%" 2>nul | findstr /i "cmd.exe" >nul 2>&1
if errorlevel 1 goto :lock_take
echo [!] Прогон уже идёт ^(PID %LOCKPID%^) — второй не стартует:
echo     один дом — одна петля одновременно ^(закон круга 21^).
echo     Дождись ГОТОВО в первом окне или закрой его и нажми кнопку снова.
if not defined MARFA_SYNC_AUTO pause
exit /b 0
:lock_take
>"%SYNC_LOCK%" echo %MYPID%
set "LOCKED=1"
:no_lock

echo ============================================================
echo  МАРФА — синхронизация Z440 ^<-^> GitHub ^<-^> Архитектор
echo  Петля: docs\SYNC_PROTOCOL_v1.md (v1.11, разделы 2 и 8)
echo ============================================================

:: ---------- 0b-0. Толщина истории: тяжёлым сборкам в git не место ----------
set "SURGERY=0"
set "GSIZE=0"
for /f "tokens=2" %%s in ('git count-objects -v 2^>nul ^| findstr /C:"size:"') do set /a GSIZE+=%%s
for /f "tokens=2" %%s in ('git count-objects -v 2^>nul ^| findstr /C:"size-pack:"') do set /a GSIZE+=%%s
if %GSIZE% GTR 102400 call :surgery
if errorlevel 1 goto :fail

:: ---------- 0b. Репозиторий дома: создать при первом запуске ----------
call :ensure_repo
call :ensure_gitignore

:: ---------- 0c. Инвентаризация размеров: что пойдёт в git ----------
if exist scripts\inventory_audit.py (
  echo [0] Инвентаризация дома ^(inventory_audit.py^):
  if exist venv\Scripts\python.exe (
    venv\Scripts\python.exe scripts\inventory_audit.py
  ) else (
    python scripts\inventory_audit.py 2>nul
  )
  echo.
)

:: ---------- 0d. Первый коммит, если git только что родился ----------
git rev-parse --verify -q HEAD >nul 2>&1
if errorlevel 1 (
  git add -A
  git commit -q -m "дом: снимок до объединения с архитектором (первый запуск)"
  echo [1] Создан первый коммит дома — текущее состояние без рантайма
) else (
  echo [1] Репозиторий дома жив — продолжаю
)

:: ---------- 2. GitHub: забрать свою историю ----------
echo [2] GitHub: забираю историю github.com/kernedmd/marfa ...
if "%SURGERY%"=="1" (
  echo     история пересобрана — GitHub обновлю с заменой ^(push --force^) на шаге [6]
  goto :skip_gh
)
call :clean_tree
git fetch origin main >nul 2>&1
if errorlevel 1 (
  echo     GitHub недоступен или нет прав — резервная копия не обновлена, петля жива
) else (
  git merge-base --is-ancestor FETCH_HEAD HEAD >nul 2>&1
  if not errorlevel 1 (
    echo     история GitHub уже вросла в дом
  ) else (
    git merge FETCH_HEAD --no-edit -X ours --allow-unrelated-histories -m "github: объединение истории" >nul 2>&1
    if errorlevel 1 (
      echo     [!] история GitHub не влита ^(конфликт^) — продолжаю без неё; покажи архитектору
    ) else (
      echo     история GitHub влита в дом
    )
  )
)
:skip_gh


:: ---------- 3. Bundle от архитектора ----------
call :clean_tree
set "IMPORTED=0"
if exist incoming\*.bundle (
  for /f "delims=" %%b in ('dir /b /o-d incoming\*.bundle') do (
    echo [3] Приём bundle архитектора: incoming\%%b
    call :import_bundle "incoming\%%b"
    if errorlevel 1 goto :fail
    set "IMPORTED=1"
  )
) else (
  echo [3] Входящих bundle нет — синхронизирую локальное состояние
)

:: ---------- 3z. Смена тела: объявление, а не операция (закон круга 19) ----------
rem Работающий файл не трогаем НИКОГДА: cmd.exe читает батник по
rem смещению байтов, и перезапись под ногами роняет парсер в середину
rem строки нового тела («was unexpected at this time», лог дома
rem 24.11 09:32 — первый живой прогон самообновления). Слияние уже
rem положило новое тело в scripts\; тела сверяются побайтно (fc /b),
rem смена объявляется вслух, петля доезжает до ГОТОВО на старом теле —
rem второе нажатие не нужно: планировщик /auto поднимет новое тело
rem следующим запуском (каждые 2 часа).
if not "%IMPORTED%"=="1" goto :no_selfupdate
fc /b "%~f0" "scripts\80_sync_github.bat" >nul 2>&1
if errorlevel 2 goto :no_selfupdate
if not errorlevel 1 goto :no_selfupdate
echo [3z] Смена тела кнопки: слияние принесло новое — прогон доезжаю
echo      до ГОТОВО на старом теле, петля не рвётся; новое тело вступит
echo      в силу со следующего запуска ^(авто каждые 2 часа^).
:no_selfupdate

:: ---------- 3b. Чистка дома: наследие v9.3 уезжает в _trash ----------
if exist scripts\clean_home.py (
  echo [4] Чистка дома ^(мусор ^> _trash, раздел 8 протокола^):
  if exist venv\Scripts\python.exe (
    venv\Scripts\python.exe scripts\clean_home.py --yes
  ) else (
    python scripts\clean_home.py --yes 2>nul
  )
  echo.
) else if "%IMPORTED%"=="1" (
  echo [x] Bundle принят, но код архитектора не доехал ^(scripts\clean_home.py нет^) —
  echo     слияние не состоялось. Сообщи архитектору и пришли вывод целиком.
  goto :fail
) else (
  echo [4] Кода архитектора в доме ещё нет ^(bundle не подкладывался^) — чистка пропущена
)

:: ---------- 4. Взять в коммит всё, кроме игнорируемого ----------
rem тяжёлые сборки llama.cpp, приехавшие в старые снимки, выводим из git
rem (на диске остаются; впредь их держит .gitignore)
git rm -r -q --cached llama-cuda llama-vulkan 2>nul && echo     llama-cuda, llama-vulkan выведены из git ^(на диске остались^)
git add -A

rem страховка от крупных файлов (>50 МБ)
powershell -NoProfile -Command "git diff --cached --name-only | ForEach-Object { if ((Test-Path $_) -and ((Get-Item $_).Length -gt 50MB)) { git reset -q HEAD -- $_; Write-Host ('[!] Убран из коммита (крупнее 50 МБ): ' + $_) } }"

git diff --cached --quiet
if errorlevel 1 (
  git commit -q -m "Синхронизация дома %date% %time%"
  echo [5] Коммит создан
) else (
  echo [5] Новых изменений нет
)

:: ---------- 5. Пуш в GitHub (провал не останавливает петлю) ----------
echo [6] Пуш в github.com/kernedmd/marfa ...
if "%SURGERY%"=="1" (
  git push --force origin main
) else (
  git push origin main
)
if errorlevel 1 (
  echo [!] Пуш не прошёл — резервная копия GitHub не обновлена, но петля жива:
  echo     ответный bundle для архитектора будет собран ниже всё равно.
  echo     Окно входа GitHub — норма: войди как kernedmd, запомнится.
  echo     Авторизация один раз: docs\GITHUB_PUSH.md ^(SSH-ключ или PAT^);
  echo     токен в чат не переносится никогда ^(СТРАЖ Ф105^).
)

:: ---------- 6. Свежий bundle для архитектора ----------
if not exist outgoing mkdir outgoing
rem тяжёлые огрызки эпохи жирной истории кнопка убирает сама
for %%f in (outgoing\*.bundle) do if %%~zf GTR 104857600 (
  echo     [!] убираю тяжёлый мусор старой истории: outgoing\%%~nxf ^(%%~zf байт^)
  del /q "outgoing\%%~nxf"
)
for /f %%t in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd-HHmm"') do set STAMP=%%t
git bundle create "outgoing\marfa-%STAMP%.bundle" main >nul
echo [7] Bundle готов: outgoing\marfa-%STAMP%.bundle

echo ============================================================
echo  ГОТОВО. Последние коммиты:
git log --oneline -3
echo.
echo  Положи outgoing\marfa-%STAMP%.bundle в чат архитектору —
echo  он заберёт его на станцию, прогонит тесты и вернёт правки.
echo  ^(_тяжёлые старые bundle из outgoing уже убраны автоматом_^)
echo ============================================================
if defined LOCKED del /q "%SYNC_LOCK%" >nul 2>&1
if not defined MARFA_SYNC_AUTO pause
goto :eof

:surgery
echo [1s] История репозитория потяжелела до ~%GSIZE% КБ — в ней застряли
echo     тяжёлые сборки llama из первого снимка. Пересобираю историю (один раз):
echo     старая уедет в .git_old\, файлы на диске не трогаются.
set "SURGERY=1"
for /f %%d in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd-HHmmss"') do set OLDD=%%d
if not exist .git_old mkdir .git_old
powershell -NoProfile -Command "Move-Item -LiteralPath .git -Destination .git_old\%OLDD%" >nul 2>&1
if exist .git (
  echo [x] не смог убрать старую историю — покажи архитектору этот вывод
  exit /b 1
)
echo     старая история: .git_old\%OLDD% ^(тяжёлая, можно удалить через неделю^)
exit /b 0

:import_bundle
rem v3.5 (24.11.2026): урок бандла-1930 — архитектор собрал bundle с одним
rem ref HEAD (без ветки main), git fetch <bundle> main падал "couldn't find
rem remote ref main" и кнопка называла живой bundle битым. Лечение: двухсту-
rem пеньчатый вход — сначала каноническая ветка main, при её отсутствии в
rem bundle пробуем HEAD. Любой честный bundle архитектора дом принимает.
git fetch %1 main
if errorlevel 1 (
  echo     ветки main в bundle нет — пробую HEAD ^(архитектор мог собрать по HEAD^)
  git fetch %1 HEAD
  if errorlevel 1 ( echo [x] fetch не удался — bundle битый? & exit /b 1 )
  echo     HEAD принят — история архитектора в bundle без ветки, это нормально
)
git merge-base --is-ancestor FETCH_HEAD HEAD >nul 2>&1
if not errorlevel 1 (
  echo     история архитектора уже вросла в дом
  del /q %1 >nul 2>&1
  echo     [i] %~nx1 убран из incoming — уже в истории дома
  exit /b 0
)
git merge-base HEAD FETCH_HEAD >nul 2>&1
if errorlevel 1 (
  rem несвязанные истории: разовое УСЫНОВЛЕНИЕ — дерево архитектора
  rem целиком, уникальные файлы дома остаются; конфликтов не бывает
  echo     истории не связаны — усыновление ^(автомат, один раз^):
  git merge --no-commit --allow-unrelated-histories FETCH_HEAD >nul 2>&1
  git checkout FETCH_HEAD -- .
  git add -A
  git commit -q -m "приём: архитектор %~nx1 (усыновление, автомат)"
  if errorlevel 1 (
    git merge --abort >nul 2>&1
    echo [x] усыновление не удалось — покажи архитектору вывод git status
    exit /b 1
  )
  echo     усыновление выполнено: версии архитектора приняты, твоё уникальное цело
  del /q %1 >nul 2>&1
  exit /b 0
)
git merge FETCH_HEAD --no-edit -X theirs -m "приём: архитектор %~nx1"
if errorlevel 1 (
  rem конфликт при общей истории: архитектор сильнее (протокол) — авторазрешение
  git checkout --theirs -- . 2>nul
  git add -A
  git commit -q --no-edit -m "приём: архитектор %~nx1 (авторазрешение)"
  if errorlevel 1 (
    git merge --abort >nul 2>&1
    echo [x] конфликт не решается автоматом — покажи архитектору вывод git status
    exit /b 1
  )
)
del /q %1 >nul 2>&1
exit /b 0

:clean_tree
rem фантомные правки (переносы строк) и реальная грязь — в коммит ДО
rem слияния: иначе merge отказывается работать поверх них
git add -A
git diff --cached --quiet
if errorlevel 1 git commit -q -m "локальные правки перед слиянием (авто)"
exit /b 0

:ensure_repo
if not exist .git (
  echo [0] Git-репозитория дома нет — создаю, один раз:
  git init -b main
  if errorlevel 1 exit /b 1
  git config user.name "Создатель Марфы"
  git config user.email "creator@marfa.local"
)
git remote get-url origin >nul 2>&1
if errorlevel 1 git remote add origin https://github.com/kernedmd/marfa.git
rem ТИХИЙ GIT (закон круга 21, урок 24.11 10:16): git gc --auto, который
rem зовут сами fetch и merge, спросил «Should I try again?» про
rem залоченный pack и повесил петлю навсегда. Причина удалена:
rem авто-gc выключен; история дома — 3,8 МБ кода, чистка — дело
rem архитектора на станции, не петли.
git config gc.auto 0
exit /b 0

:ensure_gitignore
if not exist .gitignore type nul > .gitignore
for %%e in ("models/" "downloads/" "*.gguf" "*.safetensors" "venv/" "python311/" "tools/" "data/" "logs/" ".env" ".env.*" "__pycache__/" "*.pyc" ".pytest_cache/" "incoming/" "outgoing/" "*.bundle" "_trash/" "llama.cpp/" "llama-cuda/" "llama-vulkan/" ".git_old/" "node_modules/" "marfa/") do (
  findstr /x /c:%%e .gitignore >nul 2>&1 || echo %%~e>>.gitignore
)
exit /b 0

:fail
echo ============================================================
echo  ОСТАНОВКА ПО ОШИБКЕ. Протокол: docs\SYNC_PROTOCOL_v1.md
echo ============================================================
if defined LOCKED del /q "%SYNC_LOCK%" >nul 2>&1
if not defined MARFA_SYNC_AUTO pause
exit /b 1
