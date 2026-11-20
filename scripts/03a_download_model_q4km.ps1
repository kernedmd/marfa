# ============================================================
# 03a_download_model_q4km.ps1 — Шаг 3a: мозг Qwen3-30B-A3B Q4_K_M (18.63 ГБ)
# Официальный GGUF (Qwen/Qwen3-30B-A3B-GGUF). Источники по порядку:
# Hugging Face -> ModelScope -> unsloth. Докачка при обрыве (curl -C -).
# Урок 12.11.2026: уже скачанный полный файл (размер в допуске) заново не качается.
# Проверка: размер в допуске, SHA-256 записан в лог.
# ============================================================
. "$PSScriptRoot\_common.ps1"
$step = "03a_model_q4km"
trap {
    $m = $_.Exception.Message
    $ln = ""
    try { if ($_.InvocationInfo) { $ln = " (строка $($_.InvocationInfo.ScriptLineNumber))" } } catch {}
    Write-StepLog -Step "03a_model_q4km" -Message "КРИТ: непредвиденная ошибка: $m$ln"
    Write-Host "!!! [03a_model_q4km] КРИТ: $m$ln" -ForegroundColor Red
    exit 1
}

$quant = "Q4_K_M"
$expectedGB = 18.63

if (Test-Marker $step) { Write-Step "шаг $step уже сделан (маркер) — пропуск"; exit 0 }
Write-StepLog -Step $step -Message "начало шага"

$file = Join-Path $script:ModelsDir "Qwen3-30B-A3B-$quant.gguf"
$repoFile = "Qwen3-30B-A3B-$quant.gguf"
Get-RemoteFile -Step $step -OutFile $file -ExpectedGB $expectedGB -Urls @(
    "https://huggingface.co/Qwen/Qwen3-30B-A3B-GGUF/resolve/main/$repoFile",
    "https://modelscope.cn/models/Qwen/Qwen3-30B-A3B-GGUF/resolve/master/$repoFile",
    "https://huggingface.co/unsloth/Qwen3-30B-A3B-GGUF/resolve/main/$repoFile"
) | Out-Null

# --- SHA-256 в лог (правило 6.6) — считаем долго, честно пишем прогресс ---
Write-Step "SHA-256 (может занять несколько минут)..."
$hash = (Get-FileHash -Path $file -Algorithm SHA256).Hash
Write-StepLog -Step $step -Message "SHA256 $quant = $hash"
Write-Step "SHA-256: $hash"

$sizeGB = [math]::Round((Get-Item $file).Length / 1GB, 2)
Set-Marker -Step $step -Note "$quant $sizeGB ГБ OK"
exit 0


