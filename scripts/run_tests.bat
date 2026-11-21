@echo off
rem MARFA: PS1-step wrapper (TZ Section 9). UTF-8 console.
rem v2 (21.11): окно не закрывается после прогона — итог и ошибки
rem остаются на экране; полный протокол каждого прогона пишется
rem в logs\tests_last.txt. Урок: Создатель не успевал прочитать
rem ошибки — окно схлопывалось вместе с ними.
rem BTN_VER RT.2
setlocal
set "SCRIPT_DIR=%~dp0"
chcp 65001 >nul

rem Урок 13:37: кнопка руками + файл в bundle. Новый bat со старым
rem ps1 честно предупреждает, что протокола не будет, а не молчит.
findstr /C:"tests_last" "%SCRIPT_DIR%run_tests.ps1" >nul 2>&1
if errorlevel 1 (
  echo [i] Новый run_tests.ps1 ещё не приехал из bundle — прогон будет,
  echo     но без протокола в файле. Нажми 80_sync_github.bat один раз
  echo     или дождись планировщика — потом кнопка станет полной.
  echo.
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%run_tests.ps1" %*
set "EC=%ERRORLEVEL%"
echo.
echo ============================================================
if %EC%==0 (
  echo  ТЕСТЫ ПРОШЛИ. Дом здоров.
) else (
  echo  ЕСТЬ ПАДЕНИЯ ^(код %EC%^) — это не катастрофа, это сигнал.
  echo  Открой протокол и пришли архитектору последние строки.
)
echo  Полный протокол прогона: C:\Marfa\logs\tests_last.txt
echo ============================================================
echo.
echo  Нажми любую клавишу, чтобы закрыть окно.
pause >nul
endlocal & exit /b %EC%
