# ============================================================
# 03b_download_model_q6k.ps1 — Шаг 3b: опция Q6_K (25.10 ГБ) — Раздел 8 ТЗ.
# Скачивается ТОЛЬКО по решению Ильи после недели логов Q4_K_M (правило 6).
# Запуск отдельно: scripts\03b_download_model_q6k.bat (в конвейер 00 НЕ входит).
# Источники по порядку: Hugging Face -> ModelScope -> unsloth; докачка при обрыве.
# ============================================================
. "$PSScriptRoot\_common.ps1"
$step = "03b_model_q6k"
trap {
    $m = $_.Exception.Message
    $ln = ""
    try { if ($_.InvocationInfo) { $ln = " (строка $($_.InvocationInfo.ScriptLineNumber))" } } catch {}
    Write-StepLog -Step "03b_model_q6k" -Message "КРИТ: непредвиденная ошибка: $m$ln"
    Write-Host "!!! [03b_model_q6k] КРИТ: $m$ln" -ForegroundColor Red
    exit 1
}

$quant = "Q6_K"
$expectedGB = 25.10

if (Test-Marker $step) { Write-Step "шаг $step уже сделан (маркер) — пропуск"; exit 0 }
Write-StepLog -Step $step -Message "начало шага"

# Диск: Q6_K требует ещё ~25 ГБ сверх Q4_K_M
$drive = Get-PSDrive -Name ((Resolve-Path $script:HomeDir).Drive.Name)
$freeGB = [math]::Round($drive.Free / 1GB, 1)
if ($freeGB -lt 30) { Fail -Step $step -Why "свободно ${freeGB} ГБ, для Q6_K нужно >= 30" }

$file = Join-Path $script:ModelsDir "Qwen3-30B-A3B-$quant.gguf"
$repoFile = "Qwen3-30B-A3B-$quant.gguf"
Get-RemoteFile -Step $step -OutFile $file -ExpectedGB $expectedGB -Urls @(
    "https://huggingface.co/Qwen/Qwen3-30B-A3B-GGUF/resolve/main/$repoFile",
    "https://modelscope.cn/models/Qwen/Qwen3-30B-A3B-GGUF/resolve/master/$repoFile",
    "https://huggingface.co/unsloth/Qwen3-30B-A3B-GGUF/resolve/main/$repoFile"
) | Out-Null

Write-Step "SHA-256 (несколько минут)..."
$hash = (Get-FileHash -Path $file -Algorithm SHA256).Hash
Write-StepLog -Step $step -Message "SHA256 $quant = $hash"

$sizeGB = [math]::Round((Get-Item $file).Length / 1GB, 2)
Set-Marker -Step $step -Note "$quant $sizeGB ГБ OK"
exit 0


