@echo off
chcp 65001 >nul
title МАРФА — чистка дома

rem ============================================================
rem  Чистка_Дома.bat — мусор и наследие v9.3 уезжают в _trash\ДАТА\
rem  Ничего не удаляется насовсем. Протокол: docs\SYNC_PROTOCOL_v1.md
rem ============================================================

cd /d C:\Marfa
if exist venv\Scripts\python.exe (
  venv\Scripts\python.exe scripts\clean_home.py
) else (
  python scripts\clean_home.py
)
echo.
pause
