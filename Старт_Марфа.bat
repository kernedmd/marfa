@echo off
chcp 65001 >nul
title Запуск Марфы
echo [MARFA] Запускаю Мозг, Глаза и Панель...
start "Мозг (8082)" /min cmd /c "C:\Marfa\llama.cpp\llama-server.exe -m C:\Marfa\models\Qwen3-30B-A3B-Q4_K_M.gguf --host 127.0.0.1 --port 8082 -ngl 0 --temp 0.3"
start "Глаза (8083)" /min cmd /c "C:\Marfa\llama.cpp\llama-server.exe -m C:\Marfa\models\vlm\Qwen2.5-VL-3B-Instruct-Q4_K_M.gguf --mmproj C:\Marfa\models\vlm\mmproj-Qwen2.5-VL-3B-Instruct-Q8_0.gguf -ngl 99 -c 8192 -t 2 --temp 0.1"
start "Панель (5001)" /min cmd /c "cd /d C:\Marfa && venv\Scripts\python.exe -m flask --app web.app run --host 127.0.0.1 --port 5001"
timeout /t 30 /nobreak >nul
start http://127.0.0.1:5001/chat
exit