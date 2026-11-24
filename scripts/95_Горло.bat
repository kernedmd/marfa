@echo off
chcp 65001 >nul
title МАРФА — слуга-горло: голос с интонацией (Ф121, v1.0)
rem BTN_VER 95.1

rem ============================================================
rem  СЛУГА-ГЛОТО (круг 23, Ф121): Silero v5_6_ru на порту 8084 —
rem  Марфа получает голос с ЖИВОЙ интонацией вопроса и
rem  восклицания (вердикт Создателя: «v5_6_ru, восклицание —
rem  норм»). Пророчество Ф56 исполнилось: стандартный голос
rem  показался слабым — дом вернулся к TTS по живой проверке.
rem  Слуга живёт на CPU (4 потока, ~0,5 ГБ RAM), VRAM не трогает
rem  (принцип хозяина ресурса — VRAM принадлежит глазам).
rem  Это НЕ резолюция, а инструмент: поднять/уложить можно в
rem  любой момент; горло спит — цепь честно уйдёт в SAPI
rem  (запасной рот), дом не молчит.
rem  [4] — установка ПОСЫЛКИ (torch wheels + модель): дом офлайн,
rem  посылка приезжает по USB (docs\ТЗ_Голос_v2.md, раздел 7).
rem  После подъёма скажи в чате «проверь голос» — проба цепи.
rem ============================================================

cd /d C:\Marfa
set "PY=python"
if exist venv\Scripts\python.exe set "PY=venv\Scripts\python.exe"

echo ============================================================
echo  МАРФА — СЛУГА-ГЛОТО (порт 8084, CPU, silero v5_6_ru)
echo  [1] проверь горло — осмотр без подъёма
echo  [2] поднять слугу (голос с интонацией, ~0,5 ГБ RAM)
echo  [3] уложить слугу (цепь честно уйдёт в SAPI)
echo  [4] установить посылку (torch из incoming\wheels + модель)
echo  [5] выход
echo ============================================================
choice /C 12345 /N /M "Что делаем? [1] осмотр [2] поднять [3] уложить [4] посылка [5] выход: "
if errorlevel 5 goto :done
if errorlevel 4 goto :parcel
if errorlevel 3 goto :lay
if errorlevel 2 goto :raise

:check
echo.
echo ОСМОТР ГОРЛА...
%PY% sensors\throat.py --check
echo.
pause
goto :done

:raise
echo.
echo ПОДНИМАЮ СЛУГУ (модель грузится секунды)...
%PY% -c "from core import throat; ok, note = throat.ensure_server(); print('ЖИВ' if ok else 'НЕ ОЖИЛ'); print(note); print(); print('Дальше в чате: проверь голос  —  проба цепи, потом  скажи вслух …')"
pause
goto :done

:lay
echo.
echo УКЛАДЫВАЮ СЛУГУ...
%PY% -c "from core import throat; print(throat.lay_to_rest())"
pause
goto :done

:parcel
echo.
echo УСТАНОВКА ПОСЫЛКИ (дом офлайн — wheels и модель по USB)...
if not exist incoming\wheels\*.whl (
  echo   нет incoming\wheels\*.whl — положи колёса torch посылкой
  echo   ^(как собрать — docs\ТЗ_Голос_v2.md, раздел 7^)
  goto :parcel_model
)
echo   [1/2] ставлю torch из колёс (^без интернета^)...
%PY% -m pip install --no-index --find-links incoming\wheels torch
:parcel_model
if not exist models\voice\v5_6_ru.pt (
  echo.
  echo   нет models\voice\v5_6_ru.pt — положи модель посылкой:
  echo   ожидается 147 664 410 байт, sha256 04cc9b1d…cbf50b2e
  echo   ^(откуда — docs\ТЗ_Голос_v2.md, раздел 7^)
) else (
  echo   [2/2] модель на месте: models\voice\v5_6_ru.pt
)
echo.
echo ПРОВЕРКА ПОСЛЕ УСТАНОВКИ...
%PY% sensors\throat.py --check
echo.
echo Если всё на месте — выбор [2]: поднять слугу, потом в чате
echo «проверь голос» — услышишь новый голос Марфы.
pause

:done
