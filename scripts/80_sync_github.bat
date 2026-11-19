@echo off
chcp 65001 >nul
title МАРФА — синхронизация дома с GitHub (одна кнопка)
cd /d C:\Marfa

echo ============================================================
echo  МАРФА — синхронизация Z440 ^<-^> GitHub ^<-^> Архитектор
echo  Петля: docs\SYNC_PROTOCOL_v1.md (v1.2, раздел 8)
echo ============================================================

:: ---------- 0. Репозиторий дома: создать при первом запуске ----------
call :ensure_repo
call :ensure_gitignore

:: ---------- 0b. Инвентаризация размеров: что пойдёт в git ----------
if exist scripts\inventory_audit.py (
  echo [0] Инвентаризация дома ^(inventory_audit.py^):
  if exist venv\Scripts\python.exe (
    venv\Scripts\python.exe scripts\inventory_audit.py
  ) else (
    python scripts\inventory_audit.py 2>nul
  )
  echo.
)

:: ---------- 0c. Первый коммит, если git только что родился ----------
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
git fetch origin main >nul 2>&1
if not errorlevel 1 (
  git merge-base --is-ancestor FETCH_HEAD HEAD >nul 2>&1
  if errorlevel 1 (
    git merge FETCH_HEAD --no-edit -X ours --allow-unrelated-histories -m "github: объединение истории" >nul 2>&1
    if errorlevel 1 (
      git add -A
      git commit -q --no-edit -m "github: объединение истории (завершение)"
    )
    echo     история GitHub влита в дом
  ) else (
    echo     история GitHub уже вросла в дом
  )
) else (
  echo     GitHub недоступен или нет прав — пуш ниже скажет точнее
)

:: ---------- 3. Bundle от архитектора ----------
if exist incoming\*.bundle (
  for /f "delims=" %%b in ('dir /b /o-d incoming\*.bundle') do (
    echo [3] Приём bundle архитектора: incoming\%%b
    call :import_bundle "incoming\%%b"
    if errorlevel 1 goto :fail
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
) else (
  echo [4] clean_home.py нет — чистка пропущена
)

:: ---------- 4. Взять в коммит всё, кроме игнорируемого ----------
git add -A

:: страховка от крупных файлов (>50 МБ)
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
goto :eof

:import_bundle
git fetch %1 main
if errorlevel 1 ( echo [x] fetch не удался — bundle битый? & exit /b 1 )
git merge FETCH_HEAD --no-edit -X theirs --allow-unrelated-histories -m "приём: архитектор %~nx1" >nul 2>&1
if errorlevel 1 (
  rem add/add без маркеров: версии архитектора уже стоят в дереве — завершаю слияние
  git add -A
  git commit -q --no-edit -m "приём: архитектор %~nx1 (завершение)"
  if errorlevel 1 ( git merge --abort 2>nul & echo [x] Конфликт слияния — разбери вручную: git status & exit /b 1 )
)
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
for %%e in ("models/" "downloads/" "*.gguf" "*.safetensors" "venv/" "python311/" "tools/" "data/" "logs/" ".env" ".env.*" "__pycache__/" "*.pyc" ".pytest_cache/" "incoming/" "outgoing/" "*.bundle" "_trash/" "llama.cpp/" "node_modules/" "marfa/") do (
  findstr /x /c:%%e .gitignore >nul 2>&1 || echo %%~e>>.gitignore
)
exit /b 0

:fail
echo ============================================================
echo  ОСТАНОВКА ПО ОШИБКЕ. Протокол: docs\SYNC_PROTOCOL_v1.md
echo ============================================================
exit /b 1
