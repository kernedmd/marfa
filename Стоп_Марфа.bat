@echo off
chcp 65001 >nul
title MARFA Stopper

rem ============================================================
rem  Стоп_Марфа.bat - остановка дома C:\Marfa (MASTER_TZ, Раздел 25)
rem  Гасит Мозг (8082) и Глаза (8083) через llama-server.exe,
rem  и веб-панель (Flask) через python.exe.
rem ============================================================

echo [MARFA] останавливаю Мозг и Глаза (llama-server.exe)...
taskkill /IM llama-server.exe /F >nul 2>&1
if errorlevel 1 (echo [MARFA] llama-server.exe не запущен) else (echo [MARFA] llama-server.exe остановлен)

echo [MARFA] останавливаю веб-панель (python.exe)...
taskkill /IM python.exe /F >nul 2>&1
if errorlevel 1 (echo [MARFA] python.exe не запущен) else (echo [MARFA] python.exe остановлен)

echo [MARFA] дом остановлен.
timeout /t 3 /nobreak >nul
exit /b 0
