@echo off
chcp 65001 >nul
title МАРФА — синхронизация с полным логом (диагноз, v1.0)
rem BTN_VER 86.1

rem ============================================================
rem  Диагност кнопки 80: прогоняет синхронизацию и пишет КАЖДУЮ
rem  строку в logs\sync_trace.log. Урок прогона 12:25 (21.11):
rem  кнопка запустилась, но до приёма bundle не дошла — окно
rem  закрылось или застряло молча, а что случилось, никто не
rem  записал. Теперь запись есть всегда: даже если прогон
rem  повиснет, последняя строка лога покажет шаг.
rem  Прогон идёт с /auto — внутри кнопки 80 нет ни одной паузы,
rem  весь поток течёт в лог; финальная пауза — здесь, в окне.
rem  Запуск: двойной клик. Довести до «Прогон завершён», затем
rem  прислать архитектору logs\sync_trace.log из C:\Marfa\logs.
rem  Если окно надолго замерло на одной строке — НЕ закрывать:
rem  лог уже пишется на диск, его и прислать (заодно глянь
rem  панель задач — не спряталось ли окно входа GitHub).
rem ============================================================

cd /d C:\Marfa
if not exist logs mkdir logs

echo ===== прогон %date% %time% ===== > logs\sync_trace.log
scripts\80_sync_github.bat /auto >> logs\sync_trace.log 2>&1
echo ===== прогон завершён, код %ERRORLEVEL% ===== >> logs\sync_trace.log

echo.
echo Прогон завершён. Полный лог: C:\Marfa\logs\sync_trace.log
echo Последние строки прогона:
powershell -NoProfile -Command "Get-Content -Tail 25 -Encoding UTF8 'logs\sync_trace.log'"
echo.
echo Пришли архитектору файл C:\Marfa\logs\sync_trace.log
pause
