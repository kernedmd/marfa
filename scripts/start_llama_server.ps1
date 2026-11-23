# ============================================================
# start_llama_server.ps1 — запуск мозга (порт 8082) — ТЗ Раздел 8/9.
# Без аргумента — Q4_K_M; аргумент Q6_K — опция Раздела 8 (решает Илья
# по недельным логам).
# Флаги закона: контекст 8192 (0.3, терапия §15), сэмплинг 0.7/0.8 без
# мышления, -ngl 0 — GPU только для QLoRA (2.2). Мышление выкл НА КЛИЕНТЕ
# (core/brain.py: chat_template_kwargs в каждом запросе + «/no_think» —
# работает на любой сборке сервера). День-8 (23.11): кавычки
# --chat-template-kwargs в команде старта ломали сервер в первый же
# рестарт (WinError 10061 в чате Создателя) — команда старта мозга
# НЕ СОДЕРЖИТ КАВЫЧЕК, это закон.
# Пишет data\last_quant.txt — прежний квант для рестарта (задел Ф101
# «СМОТРЯЩИЙ»).
# ============================================================
. "$PSScriptRoot\_common.ps1"

$quant = "Q4_K_M"
if ($args.Count -ge 1 -and "$($args[0])".ToUpper() -in @("Q4_K_M", "Q6_K")) {
    $quant = "$($args[0])".ToUpper()
}

$model = Join-Path $script:ModelsDir "Qwen3-30B-A3B-$quant.gguf"
if (-not (Test-Path $model)) {
    Write-Host "нет модели ${quant}: $model" -ForegroundColor Red
    exit 1
}
if (-not (Test-PortFree -Port 8082)) {
    Write-Host "порт 8082 занят — мозг уже запущен (перезапуск вручную: остановите процесс llama-server)" -ForegroundColor Yellow
    exit 1
}

# Прежний квант — для сторожа Ф101 (рестарт с тем же квантом)
$quant | Set-Content -Path (Join-Path $script:DataDir "last_quant.txt") -Encoding ASCII

Write-Host "МОЗГ: Qwen3-30B-A3B $quant ($([math]::Round((Get-Item $model).Length/1GB,2)) ГБ)"
Write-Host "Порт 8082, контекст 8192, мышление выкл на клиенте, -ngl 0 (GPU только для QLoRA). Стоп: Ctrl+C"
Write-Host "----------------------------------------------"
& $script:LlamaServerExe `
    -m $model `
    --port 8082 --host 127.0.0.1 `
    -c 8192 --temp 0.7 --top-p 0.8 --top-k 20 --repeat-penalty 1.0 `
    -ngl 0
exit $LASTEXITCODE
