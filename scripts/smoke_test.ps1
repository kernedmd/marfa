# ============================================================
# smoke_test.ps1 — СМОУК-ТЕСТ МОЗГА после установки (ТЗ Раздел 9).
# Старт llama-server (порт 8082, контекст 4096, -ngl 0) ->
# фиксированный промпт -> ответ -> ток/с в лог -> сервер стоп.
# ============================================================
. "$PSScriptRoot\_common.ps1"
$step = "06_smoke"
trap {
    $m = $_.Exception.Message
    $ln = ""
    try { if ($_.InvocationInfo) { $ln = " (строка $($_.InvocationInfo.ScriptLineNumber))" } } catch {}
    Write-StepLog -Step "06_smoke" -Message "КРИТ: непредвиденная ошибка: $m$ln"
    Write-Host "!!! [06_smoke] КРИТ: $m$ln" -ForegroundColor Red
    exit 1
}


Write-StepLog -Step $step -Message "начало смоук-теста"
$model = Join-Path $script:ModelsDir "Qwen3-30B-A3B-Q4_K_M.gguf"
if (-not (Test-Path $model)) { Fail -Step $step -Why "нет модели Q4_K_M — сначала шаг 03a" }

# --- Порт 8082 должен быть свободен ---
if (-not (Test-PortFree -Port 8082)) { Fail -Step $step -Why "порт 8082 занят — мозг уже запущен?" }

# --- Старт сервера отдельным процессом ---
Write-Step "старт llama-server (Q4_K_M, контекст 4096, -ngl 0) — загрузка 18.63 ГБ занимает минуты"
$proc = Start-Process -FilePath $script:LlamaServerExe `
    -ArgumentList @("-m", $model, "--port", "8082", "--host", "127.0.0.1", `
                    "-c", "4096", "-ngl", "0") `
    -NoNewWindow -PassThru `
    -RedirectStandardOutput (Join-Path $script:LogsDir "llama_server_smoke.log") `
    -RedirectStandardError (Join-Path $script:LogsDir "llama_server_smoke.err.log")

try {
    # --- Ждём /health до 10 минут ---
    # Урок 12.11.2026 (коммит 26): живость сервера проверяем Get-Process -Id, а не
    # $proc.HasExited — на PS 5.1 объект Start-Process -PassThru теряет хэндл после
    # долгого ожидания (урок коммита 24: ExitCode = $null), HasExited тоже ненадёжен.
    $healthy = $false
    for ($i = 0; $i -lt 120; $i++) {
        Start-Sleep -Seconds 5
        try {
            $h = Invoke-RestMethod -Uri "http://127.0.0.1:8082/health" -TimeoutSec 3
            if ($h.status -eq "ok") { $healthy = $true; break }
        } catch {
            $alive = $true
            try { $alive = ($null -ne (Get-Process -Id $proc.Id -ErrorAction SilentlyContinue)) } catch { $alive = $true }
            if (-not $alive) { Fail -Step $step -Why "llama-server умер при загрузке — см. logs\llama_server_smoke.err.log" }
        }
    }
    if (-not $healthy) { Fail -Step $step -Why "мозг не поднялся за 10 минут" }
    Write-Step "мозг здоров (8082)"

    # --- Фиксированный промпт ---
    $body = @{
        messages = @(
            @{ role = "system"; content = "Ты — Марфа. Отвечай кратко." },
            @{ role = "user";   content = "Какая модель у твоего мозга? Ответь одной строкой." }
        )
        max_tokens = 64
        temperature = 0.2
    } | ConvertTo-Json -Depth 5

    Write-Step "фиксированный промпт..."
    $t0 = Get-Date
    $resp = Invoke-RestMethod -Uri "http://127.0.0.1:8082/v1/chat/completions" -Method Post `
             -ContentType "application/json; charset=utf-8" -Body ([Text.Encoding]::UTF8.GetBytes($body)) -TimeoutSec 300
    $dt = ((Get-Date) - $t0).TotalSeconds

    $answer = $resp.choices[0].message.content
    $tok = $resp.usage.completion_tokens
    $tps = [math]::Round($tok / [math]::Max($dt, 0.001), 1)
    Write-StepLog -Step $step -Message "ответ: $answer"
    Write-StepLog -Step $step -Message "ток/с: $tps (токенов: $tok, сек: $([math]::Round($dt,1)))"
    Write-Host "Ответ: $answer"
    Write-Host ("Скорость: {0} ток/с (ожидание MoE на DDR4: 8-16)" -f $tps) -ForegroundColor Cyan
}
finally {
    # --- Сервер стоп (ТЗ: фиксированный промпт -> ответ -> лог -> стоп) ---
    # Урок 12.11.2026 (коммит 26): не читаем $proc.HasExited (ненадёжен на PS 5.1 —
    # урок коммита 24), стоп по Id; «процесс уже умер» глушится SilentlyContinue,
    # чтобы успешный смоук не разворачивался в КРИТ на строке остановки.
    if ($proc) {
        Write-Step "стоп llama-server"
        try { Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue } catch {}
    }
}

Set-Marker -Step $step -Note "смоук пройден"
exit 0