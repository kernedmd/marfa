@echo off
rem MARFA: PS1-step wrapper (TZ Section 9). UTF-8 console.
setlocal
set "SCRIPT_DIR=%~dp0"
chcp 65001 >nul
powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%90_manual_check.ps1" %*
set "EC=%ERRORLEVEL%"
rem Окно не закроется само: пользователь должен успеть прочитать результат
pause
endlocal & exit /b %EC%
