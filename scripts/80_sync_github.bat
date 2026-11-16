@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
title МАРФА — синхронизация дома с GitHub (одна кнопка)
cd /d C:\Marfa

echo ============================================================
echo  МАРФА — синхронизация Z440 ^<-^> GitHub ^<-^> Архитектор
echo  Петля: docs\SYNC_PROTOCOL_v1.md
echo ============================================================

:: ---------- 0. Страховка .gitignore (крупное и секреты не в git) ----------
call :ensure_gitignore

:: ---------- 0b. Инвентаризация размеров: что пойдёт в git, что в доме ----------
if exist scripts\inventory_audit.py (
  echo [0] Инвентаризация дома ^(inventory_audit.py^):
  if exist venv\Scripts\python.exe (
    venv\Scripts\python.exe scripts\inventory_audit.py
  ) else (
    python scripts\inventory_audit.py 2>nul
  )
  echo.
)

:: ---------- 1. Импорт bundle от архитектора, если он положен в incoming\ ----------
if exist incoming\*.bundle (
  set /a N=0
  for /f "delims=" %%b in ('dir /b /o-d incoming\*.bundle') do (
    echo [1] Импорт архитекторного bundle: incoming\%%b
    git fetch "incoming\%%b" main
    if errorlevel 1 ( echo [!] fetch не удался — bundle битый? & goto :fail )
    git merge FETCH_HEAD --no-edit -m "merge: архитектор %%b" 2>nul
    if errorlevel 1 (
      git merge --abort 2>nul
      git merge FETCH_HEAD --no-edit --allow-unrelated-histories -m "merge: архитектор %%b (несвязанные истории)" 2>nul
    )
    if errorlevel 1 (
      echo [!] Конфликт слияния с архитектором. Разбери вручную: git status
      goto :fail
    )
    set /a N+=1
  )
  echo [1] Импортировано bundle: !N!
) else (
  echo [1] Входящих bundle нет (incoming\ пуст) — работаем с локальным состоянием
)

:: ---------- 2. Взять в коммит всё, кроме игнорируемого ----------
git add -A

:: ---------- 3. Страховка от крупных файлов (>50 МБ) ----------
powershell -NoProfile -Command "git diff --cached --name-only | ForEach-Object { if ((Test-Path $_) -and ((Get-Item $_).Length -gt 50MB)) { git reset -q HEAD -- $_; Write-Host ('[!] Убран из коммита (крупнее 50 МБ): ' + $_) } }"

:: ---------- 4. Коммит, если есть изменения ----------
git diff --cached --quiet
if errorlevel 1 (
  git commit -m "Синхронизация дома %date% %time%"
  echo [2] Коммит создан
) else (
  echo [2] Новых изменений нет
)

:: ---------- 5. Пуш в GitHub ----------
echo [3] Пуш в github.com/kernedmd/marfa ...
git push origin main
if errorlevel 1 (
  echo [!] Пуш не прошёл. Авторизация: docs\GITHUB_PUSH.md (SSH-ключ или разовый PAT).
  echo     Токен в чат не переносится никогда (СТРАЖ Ф105).
  goto :fail
)

:: ---------- 6. Свежий bundle для архитектора ----------
if not exist outgoing mkdir outgoing
for /f %%t in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd-HHmm"') do set STAMP=%%t
git bundle create "outgoing\marfa-%STAMP%.bundle" main >nul
echo [4] Bundle готов: outgoing\marfa-%STAMP%.bundle

echo ============================================================
echo  ГОТОВО. Последние коммиты:
git log --oneline -3
echo.
echo  Положи outgoing\marfa-%STAMP%.bundle в чат архитектору —
echo  он заберёт его на станцию, прогонит тесты и вернёт правки.
echo ============================================================
goto :eof

:ensure_gitignore
if not exist .gitignore type nul > .gitignore
for %%e in ("models/" "downloads/" "*.gguf" "*.safetensors" "venv/" "python311/" "tools/" "data/" "logs/" ".env" ".env.*" "__pycache__/" "*.pyc" ".pytest_cache/" "incoming/" "outgoing/" "*.bundle" "llama.cpp/" "node_modules/" "marfa/") do (
  findstr /x /c:%%e .gitignore >nul 2>&1 || echo %%~e>>.gitignore
)
goto :eof

:fail
echo ============================================================
echo  ОСТАНОВКА ПО ОШИБКЕ. Логи: logs\ ; протокол: docs\SYNC_PROTOCOL_v1.md
echo ============================================================
exit /b 1
