@echo off
chcp 65001 >nul
title МАРФА — ремонт мозга (одна кнопка, v1.0)
rem BTN_VER 1.0

rem ============================================================
rem  92_brain_fix.bat — чинит команду мозга и поднимает мозг.
rem  Причина рождения: день-8 (23.11) — терапия §15 вписала в
rem  start_marfa.json хвост с кавычками
rem  (--chat-template-kwargs "{\"enable_thinking\": false}"),
rem  кавычки съедаются разбором argv, сервер получает невалидный
rem  JSON и умирает на старте. Живой мозг маскировал бомбу до
rem  первого Стоп-Старт: чат ответил «мозг недоступен
rem  (WinError 10061)». Кнопка снимает ядовитый хвост (путь
rem  модели Создателя сохраняется) и поднимает мозг, если он
rem  не жив. Мышление выключено НА КЛИЕНТЕ (brain.py шлёт
rem  chat_template_kwargs + «/no_think» каждому запросу) —
rem  серверу для этого ничего не нужно.
rem  Идемпотентна: здоровая команда не трогается, живой мозг
rem  не перезапускается. Тяжёлая логика — в
rem  scripts\fix_brain_cmd.py (тесты tests\test_fix_brain_cmd.py).
rem ============================================================

setlocal
set "SCRIPT_DIR=%~dp0"
set "MARFA_ROOT=%SCRIPT_DIR%.."

if not exist "%MARFA_ROOT%\venv\Scripts\python.exe" (
  echo [ОШИБКА] Не найден venv Марфы: %MARFA_ROOT%\venv\Scripts\python.exe
  echo          Сначала поставь Python кнопкой 01_install_python.bat
  pause
  exit /b 1
)

"%MARFA_ROOT%\venv\Scripts\python.exe" "%MARFA_ROOT%\scripts\fix_brain_cmd.py" --start %*
set "EC=%ERRORLEVEL%"

rem Окно не закроется само: пользователь должен успеть прочитать результат
pause
endlocal & exit /b %EC%
