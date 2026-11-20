@echo off
chcp 65001 >nul
title МАРФА — ремонт модели ушей (одна кнопка, v1.0)
rem BTN_VER 1.0

rem ============================================================
rem  85_fix_ears.bat — чинит раскладку модели ушей одним кликом.
rem  Причина рождения: первый живой прогон ушей на Z440
rem  (20.11.2026) — тест упал, vosk молчал по-английски
rem  «Folder does not contain model files». Архив с сайта
rem  alphacephei содержит внутри ещё одну папку с тем же
rem  именем, а «Извлечь всё» в Проводнике подкладывает
rem  destination с именем архива — модель ложится двойным
rem  матрёшком: models\vosk-...\vosk-...\am\final.mdl.
rem  Кнопка поднимет вложенную папку, распакует zip, если
rem  он не распакован, или честно скажет, что скачать.
rem  Идемпотентна: сколько угодно нажатий, вреда нет.
rem  Тяжёлая логика — в scripts\fix_ears_model.py (тесты
rem  tests\test_fix_ears.py). Протокол: Ф-ушки, Этап 1.
rem ============================================================

setlocal
set "SCRIPT_DIR=%~dp0"
set "MARFA_ROOT=%SCRIPT_DIR%.."

if not exist "%MARFA_ROOT%\venv\Scripts\python.exe" (
  echo [ОШИБКА] Не найден venv Марфы: %MARFA_ROOT%\venv\Scripts\python.exe
  echo          Сначала поставь Python кнопкой 01_install_python.bat
  pause
  exit /b 1
)

"%MARFA_ROOT%\venv\Scripts\python.exe" "%MARFA_ROOT%\scripts\fix_ears_model.py" %*
set "EC=%ERRORLEVEL%"

rem Окно не закроется само: пользователь должен успеть прочитать результат
pause
endlocal & exit /b %EC%
