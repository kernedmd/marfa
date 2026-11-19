@echo off
chcp 65001 >nul
title Обновить Марфу из GitHub и проверить тестами
cd /d C:\Marfa
venv\Scripts\python.exe sync_and_test.py
echo.
pause
