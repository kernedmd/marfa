@echo off
chcp 65001 >nul
title МАРФА — синхронизация дома с GitHub (одна кнопка, v2.2)

rem ============================================================
rem  v2.2 (19.11.2026, ночь): честные слияния.
rem  Урок первого прогона: bundle скачался, но НЕ влился — merge
rem  отказался работать поверх фантомно-изменённых файлов
rem  (переносы строк после вливания GitHub), а старая кнопка это
rem  замаскировала. Теперь: грязь коммитится ДО слияния (:clean_tree),
rem  сбой приёма не маскируется, после приёма контроль (clean_home.py),
rem  тяжёлые сборки llama выведены из git, кнопка работает с временной
rem  копии — петля может обновлять её сама.
rem  Протокол: docs\SYNC_PROTOCOL_v1.md (v1.4, разделы 2 и 8)
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

echo ============================================================
echo  МАРФА — синхронизация Z440 ^<-^> GitHub ^<-^> Архитектор
echo  Петля: docs\SYNC_PROTOCOL_v1.md (v1.4, разделы 2 и 8)
echo ============================================================

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
git push origin main
if errorlevel 1 (
  echo [!] Пуш не прошёл — резервная копия GitHub не обновлена, но петля жива:
  echo     ответный bundle для архитектора будет собран ниже всё равно.
  echo     Окно входа GitHub — норма: войди как kernedmd, запомнится.
  echo     Авторизация один раз: docs\GITHUB_PUSH.md ^(SSH-ключ или PAT^);
  echo     токен в чат не переносится никогда ^(СТРАЖ Ф105^).
)

:: ---------- 6. Свежий bundle для архитектора ----------
if not exist outgoing mkdir outgoing
for /f %%t in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd-HHmm"') do set STAMP=%%t
git bundle create "outgoing\marfa-%STAMP%.bundle" main >nul
echo [7] Bundle готов: outgoing\marfa-%STAMP%.bundle

echo ============================================================
echo  ГОТОВО. Последние коммиты:
git log --oneline -3
echo.
echo  Положи outgoing\marfa-%STAMP%.bundle в чат архитектору —
echo  он заберёт его на станцию, прогонит тесты и вернёт правки.
echo ============================================================
pause
goto :eof

:import_bundle
git fetch %1 main
if errorlevel 1 ( echo [x] fetch не удался — bundle битый? & exit /b 1 )
git merge-base --is-ancestor FETCH_HEAD HEAD >nul 2>&1
if not errorlevel 1 ( echo     история архитектора уже вросла в дом & exit /b 0 )
git merge FETCH_HEAD --no-edit -X theirs --allow-unrelated-histories -m "приём: архитектор %~nx1"
if errorlevel 1 (
  git merge --abort >nul 2>&1
  echo [x] Bundle НЕ влился — конфликт слияния. Выполни: git status
  echo     и покажи вывод архитектору. Локальные правки не потеряны.
  exit /b 1
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
for %%e in ("models/" "downloads/" "*.gguf" "*.safetensors" "venv/" "python311/" "tools/" "data/" "logs/" ".env" ".env.*" "__pycache__/" "*.pyc" ".pytest_cache/" "incoming/" "outgoing/" "*.bundle" "_trash/" "llama.cpp/" "llama-cuda/" "llama-vulkan/" "node_modules/" "marfa/") do (
  findstr /x /c:%%e .gitignore >nul 2>&1 || echo %%~e>>.gitignore
)
exit /b 0

:fail
echo ============================================================
echo  ОСТАНОВКА ПО ОШИБКЕ. Протокол: docs\SYNC_PROTOCOL_v1.md
echo ============================================================
pause
exit /b 1
