@echo off
chcp 65001 >nul
title МАРФА — старт дома

rem ============================================================
rem  Старт_Марфа.bat — кнопка Создателя: поднять весь дом.
rem  Движок: start_marfa.py (№22) — команды живут в start_marfa.json
rem  (мозг 8082, глаза 8083, панель 5001), движок ждёт глаза, пишет
rem  журнал logs\startup.log. Повторный запуск безопасен: живых
rem  слуг не трогает. Поменял модель или квант — правь json.
rem ============================================================

cd /d C:\Marfa
if exist venv\Scripts\python.exe (
  venv\Scripts\python.exe start_marfa.py
) else (
  python start_marfa.py
)

rem как в старой кнопке: после старта открыть чат Марфы
start "" http://127.0.0.1:5001/chat
echo.
pause
