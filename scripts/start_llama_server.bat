@echo off
rem MARFA: PS1-step wrapper (TZ Section 9). UTF-8 console.
setlocal
set "SCRIPT_DIR=%~dp0"
chcp 65001 >nul
powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%start_llama_server.ps1" %*
set "EC=%ERRORLEVEL%"
endlocal & exit /b %EC%
 --temp 0.3 --top-p 0.8 --top-k 20 --min-p 0.05 --repeat-penalty 1.1 --repeat-last-n 256 -c 8192 --jinja --chat-template-kwargs {"enable_thinking":false}