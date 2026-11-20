@echo off
chcp 65001 >nul
title МАРФА — синхронизация дома с GitHub (одна кнопка, v3.2)
rem BTN_VER 3.2

rem ============================================================
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
rem  Протокол: docs\SYNC_PROTOCOL_v1.md (v1.7, разделы 2, 3, 6 и 8)
rem ============================================================

:: ---------- 0a. Временная копия: кнопка сможет обновить себя в петле ----------
if defined MARFA_SYNC_RELAUNCH goto :run
del /q "%TEMP%\marfa_sync_run.bat" >nul 2>&1
copy /y "%~f0" "%TEMP%\marfa_sync_run.bat" >nul 2>&1
if not exist "%TEMP%\marfa_sync_run.bat" goto :run
echo [0] Работаю с временной копии — репозиторий может обновить кнопку сам
set "MARFA_SYNC_RELAUNCH=1"
call "%TEMP%\marfa_sync_run.bat" %*
exit /b %ERRORLEVEL%

:run
cd /d C:\Marfa
if not defined MARFA_SYNC_TURNS set "MARFA_SYNC_TURNS=1"

echo ============================================================
echo  МАРФА — синхронизация Z440 ^<-^> GitHub ^<-^> Архитектор
echo  Петля: docs\SYNC_PROTOCOL_v1.md (v1.7, разделы 2 и 8)
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

:: ---------- 3z. Самообновление кнопки: один прогон до конца ----------
rem Если слияние принесло НОВУЮ версию кнопки — перезапускаемся ею
rem сразу, в этом же прогоне (требование Создателя: без второго нажатия).
rem Предохранитель MARFA_SYNC_TURNS=2: максимум один перезапуск за прогон.
if not "%IMPORTED%"=="1" goto :no_selfupdate
if "%MARFA_SYNC_TURNS%"=="2" goto :no_selfupdate
set "RUN_VER=" & set "TREE_VER="
for /f "delims=" %%a in ('findstr /C:"rem BTN_VER" "%TEMP%\marfa_sync_run.bat" 2^>nul') do set "RUN_VER=%%a"
for /f "delims=" %%a in ('findstr /C:"rem BTN_VER" "scripts\80_sync_github.bat" 2^>nul') do set "TREE_VER=%%a"
if not defined RUN_VER goto :no_selfupdate
if not defined TREE_VER goto :no_selfupdate
if "%RUN_VER%"=="%TREE_VER%" goto :no_selfupdate
echo [3z] Слияние принесло новую версию кнопки — перезапускаюсь ею
set /a MARFA_SYNC_TURNS+=1
copy /y "scripts\80_sync_github.bat" "%TEMP%\marfa_sync_run.bat" >nul
call "%TEMP%\marfa_sync_run.bat" %*
exit /b %ERRORLEVEL%
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
pause
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
git fetch %1 main
if errorlevel 1 ( echo [x] fetch не удался — bundle битый? & exit /b 1 )
git merge-base --is-ancestor FETCH_HEAD HEAD >nul 2>&1
if not errorlevel 1 ( echo     история архитектора уже вросла в дом & exit /b 0 )
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
pause
exit /b 1
