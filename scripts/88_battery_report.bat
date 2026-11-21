@echo off
chcp 65001 >nul
title МАРФА — сводка батареи мозга (v1.0)
rem BTN_VER 88.1

rem ============================================================
rem  Сводка батареи ОДНОЙ кнопкой: собирает все прогоны
rem  logs\brain_battery_*.json в один человекочитаемый
rem  logs\battery_report.txt. Новую батарею НЕ гоняет —
rem  только сводку по уже сделанным прогонам. Секунды, не
rem  минуты. Это кнопка-выручалка: если шаг [3] кнопки 87
rem  не нашёл файла или прогон был вчера — жми сюда.
rem ============================================================

cd /d C:\Marfa
set "PY=python"
if exist venv\Scripts\python.exe set "PY=venv\Scripts\python.exe"

echo ============================================================
echo  МАРФА — СВОДКА БАТАРЕИ МОЗГА
echo  Прогоны не гоняю, собираю готовое. Занимает секунды.
echo ============================================================

if not exist scripts\battery_report.py (
  echo [x] Файла scripts\battery_report.py в доме ещё нет.
  echo     Он приезжает из bundle: нажми 80_sync_github.bat один раз
  echo     или дождись планировщика — он ходит раз в 2 часа.
  echo     Потом нажми сюда снова.
  pause
  exit /b 1
)

%PY% scripts\battery_report.py
if errorlevel 1 (
  echo.
  echo [x] Сводка не собралась: прогонов батареи в logs\ нет
  echo     или все логи битые. Сначала 87_brain_battery.bat.
  pause
  exit /b 1
)

echo.
echo ============================================================
echo  ГОТОВО. Один файл:
echo      C:\Marfa\logs\battery_report.txt
echo  Положи его в чат архитектору целиком.
echo ============================================================
pause
