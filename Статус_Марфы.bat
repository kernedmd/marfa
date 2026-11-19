@echo off
chcp 65001 >nul
title Статус дома Марфа
cd /d C:\Marfa
venv\Scripts\python.exe marfa_status.py
echo.
pause
