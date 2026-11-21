@echo off
chcp 65001 >nul
title МАРФА — доктор дома (v1.0)
rem BTN_VER 84.1

rem ============================================================
rem  ДОКТОР ДОМА — осмотр и лечение одной кнопкой (№21).
rem  Осмотр: порты мозг/глаза/панель, сердца ушей и стремления,
rem  venv, веса моделей, .env (не читая значений), диск, канон.
rem  Лечение: мёртвый слуга поднимается той же командой, что и
rem  при старте дома (start_marfa.json) — с подтверждения.
rem  Автодоктор (расписание, раз в 5 минут) делает это сам:
rem  слуга, мёртвый два осмотра подряд, поднимается без вопросов.
rem ============================================================

cd /d C:\Marfa
set "PY=python"
if exist venv\Scripts\python.exe set "PY=venv\Scripts\python.exe"

if not exist scripts\marfa_doctor.py (
  echo [x] Файла scripts\marfa_doctor.py в доме ещё нет.
  echo     Он приезжает из bundle: нажми 80_sync_github.bat один раз
  echo     или дождись планировщика — он ходит раз в 2 часа.
  echo     Потом нажми сюда снова.
  pause
  exit /b 1
)

%PY% scripts\marfa_doctor.py --heal
echo.
pause
