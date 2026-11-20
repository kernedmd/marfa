@echo off
rem MARFA: PS1-step wrapper (TZ Section 9). UTF-8 console.
setlocal
set "SCRIPT_DIR=%~dp0"
chcp 65001 >nul
powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%smoke_test.ps1" %*
set "EC=%ERRORLEVEL%"
endlocal & exit /b %EC%
