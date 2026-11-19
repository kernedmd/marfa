# ============================================================
# 04_install_qlora.ps1 — Шаг 4: venv C:\Marfa\venv + QLoRA-стек (ТЗ 3.8, ADR-004)
# Pascal-режим GTX 1060: torch CUDA (CC 6.1), bitsandbytes NF4 (LLM.int8 ЗАПРЕЩЁН),
# peft + trl + transformers + accelerate. Студент: Qwen2.5-3B-Instruct (~6 ГБ, 2 шарда, ADR-009).
# Проверка: импорт стека, torch.cuda.is_available() = True, имя GPU = GTX 1060.
# Урок 12.11.2026 (ручной режим): pip при провале pypi.org сам повторяет через
# зеркало tuna; torch при провале download.pytorch.org — колёса cu118 с aliyun;
# студент при провале HF — hf-mirror.com. Ручная подсказка печатается при провале.
# ============================================================
. "$PSScriptRoot\_common.ps1"
$step = "04_qlora"
trap {
    $m = $_.Exception.Message
    $ln = ""
    try { if ($_.InvocationInfo) { $ln = " (строка $($_.InvocationInfo.ScriptLineNumber))" } } catch {}
    Write-StepLog -Step "04_qlora" -Message "КРИТ: непредвиденная ошибка: $m$ln"
    Write-Host "!!! [04_qlora] КРИТ: $m$ln" -ForegroundColor Red
    exit 1
}


if (Test-Marker $step) { Write-Step "шаг $step уже сделан (маркер) — пропуск"; exit 0 }
Write-StepLog -Step $step -Message "начало шага"
# --- Предусловие: базовый Python из шага 01 (свой в python311\ или адоптированный) ---
if (-not (Test-Path $script:PythonExe)) {
    Fail -Step $step -Why "python.exe не найден ($script:PythonExe) — выполните шаг 01; шаг 01 сам подключит уже установленный Python 3.11.x"
}
# Урок 12.11.2026 (коммит 26): зонд через Invoke-ExeProbe — не через 2>&1 (EAP=Stop).
$pvProbe = Invoke-ExeProbe -FilePath $script:PythonExe -Arguments "--version" -TimeoutSec 20
$pv = "$($pvProbe.Output)".Trim()
Write-StepLog -Step $step -Message "базовый python: $($script:PythonExe) ($pv)"


# --- venv внутри дома ---
if (-not (Test-Path $script:VenvPython)) {
    Write-Step "создание venv (python311 -> venv\)"
    $r = Invoke-Logged -Step $step -FilePath $script:PythonExe -Arguments "-m venv `"$script:HomeDir\venv`"" -TimeoutSec 600
    if ($r -ne 0) { Fail -Step $step -Why "venv не создался" }
}

$vp = $script:VenvPython

# --- pip до актуального ---
Invoke-PipInstall -Step $step -Python $vp -Arguments "-m pip install --upgrade pip --quiet" -TimeoutSec 300 | Out-Null

# --- torch: CUDA-сборка под Pascal (CC 6.1). cu118 поддерживает GTX 1060. ---
Write-Step "torch CUDA 11.8 (Pascal CC 6.1) — большой пакет, ждём"
$r = Invoke-PipInstall -Step $step -Python $vp -TimeoutSec 0 `
     -Arguments "-m pip install torch --index-url https://download.pytorch.org/whl/cu118 --quiet" `
     -FallbackArguments "-m pip install torch==2.0.1+cu118 -f https://mirrors.aliyun.com/pytorch-wheels/cu118/ --quiet"
if ($r -ne 0) { Fail -Step $step -Why "torch cu118 не установился" }

# --- QLoRA-стек ---
Write-Step "QLoRA-стек: bitsandbytes peft trl transformers accelerate"
$r = Invoke-PipInstall -Step $step -Python $vp `
     -Arguments "-m pip install bitsandbytes peft trl transformers accelerate --quiet" -TimeoutSec 0
if ($r -ne 0) { Fail -Step $step -Why "QLoRA-стек не установился" }

# --- рантайм дома: веб-панель, монитор, тесты ---
Write-Step "рантайм: psutil flask requests + pytest"
$r = Invoke-PipInstall -Step $step -Python $vp `
     -Arguments "-m pip install psutil flask requests pytest --quiet" -TimeoutSec 600
if ($r -ne 0) { Fail -Step $step -Why "рантайм-пакеты не установились" }

# --- Студент: Qwen2.5-3B-Instruct (~6 ГБ: ДВА шарда + index.json) в models\ ---
# Урок 12.11.2026 (коммит 25): `python -m huggingface_hub.commands.huggingface_cli`
# умирал за секунду — в huggingface_hub 1.x модуль commands удалён (а в 0.34 CLI уже
# переименован в `hf`). Сеть была ни при чём. Свой загрузчик scripts\download_student.py
# (чистый stdlib: urllib + Range-докачка + таймауты + SHA-256 шардов) не зависит от
# версии библиотеки. В снимке НЕТ единого model.safetensors — модель лежит двумя
# шардами model-0000X-of-00002.safetensors + model.safetensors.index.json (без index
# transformers модель не грузит). Запуск живой (&), не через Invoke-Logged: пользователь
# видит прогресс в консоли; зависание исключено таймаутами внутри загрузчика.
$studentDir = Join-Path $script:ModelsDir "Qwen2.5-3B-Instruct"
$dlScript = Join-Path $PSScriptRoot "download_student.py"
if (-not (Test-Path (Join-Path $studentDir "config.json"))) {
    Write-Step "студент Qwen2.5-3B-Instruct (~6 ГБ, 2 шарда) в models\Qwen2.5-3B-Instruct"
    Write-Step "источник 1: huggingface.co — прогресс ниже; обрывы докачиваются сами"
    & $vp -u $dlScript $studentDir
    $r = $LASTEXITCODE
    if ($r -ne 0) {
        Write-Step "HF не дотянулся (код $r) — повтор через зеркало hf-mirror.com"
        Write-StepLog -Step $step -Message "студент: повтор с HF_ENDPOINT=https://hf-mirror.com"
        $env:HF_ENDPOINT = "https://hf-mirror.com"
        & $vp -u $dlScript $studentDir
        $r = $LASTEXITCODE
        Remove-Item Env:HF_ENDPOINT -ErrorAction SilentlyContinue
    }
    if ($r -ne 0) {
        Fail -Step $step -Why "студент не скачался с обоих источников — ручной путь: скачать со страницы https://huggingface.co/Qwen/Qwen2.5-3B-Instruct/tree/main файлы config.json, generation_config.json, model-00001-of-00002.safetensors, model-00002-of-00002.safetensors, model.safetensors.index.json, tokenizer.json, tokenizer_config.json, vocab.json, merges.txt в models\Qwen2.5-3B-Instruct\ и перезапустить шаг"
    }
} else {
    Write-Step "студент уже на месте"
}
# Проверка целостности (SHA-256 шардов, JSON конфигов) — и для скачанного, и для ручного.
# Через Invoke-Logged: вывод и код возврата в журнале шага.
$rChk = Invoke-Logged -Step $step -FilePath $vp `
         -Arguments "`"$dlScript`" --check-only `"$studentDir`"" -TimeoutSec 900
if ($rChk -ne 0) {
    Fail -Step $step -Why "студент не прошёл проверку целостности — докачайте недостающее или битое (список печатает download_student.py в журнале выше), затем перезапустите шаг"
}
Write-StepLog -Step $step -Message "студент проверен: SHA-256 шардов и конфиги OK"

# --- Проверка стека: импорт + CUDA + имя GPU ---
# Урок 12.11.2026 (коммит 26): bitsandbytes/torch пишут предупреждения в stderr —
# `2>&1` при EAP=Stop ронял бы шаг терминающей ошибкой; зонд через Invoke-ExeProbe
# (таймаут 300 с — зависший импорт больше не вешает шаг навсегда).
Write-Step "проверка стека (импорт, CUDA, GPU)..."
$check = "import torch, bitsandbytes, peft, trl, transformers, accelerate; " +
         "assert torch.cuda.is_available(), 'CUDA недоступна'; " +
         "print('GPU:', torch.cuda.get_device_name(0)); " +
         "print('CC:', torch.cuda.get_device_capability(0))"
$cProbe = Invoke-ExeProbe -FilePath $vp -Arguments "-c `"$check`"" -TimeoutSec 300
$out = @("$($cProbe.Output)" -split "`r?`n" | Where-Object { "$_".Trim() -ne "" })
$out | ForEach-Object { Write-StepLog -Step $step -Message "$_" }
if ($cProbe.TimedOut) { Fail -Step $step -Why "проверка стека не уложилась в 300 с (зависший импорт?) — детали в журнале выше" }
if ($cProbe.Code -ne 0) { Fail -Step $step -Why "стек не импортируется / CUDA недоступна (проверьте драйвер NVIDIA) — детали в журнале выше" }
$gpuLine = ($out | Where-Object { "$_" -match "^GPU:" }) -join ""
if ("$gpuLine" -notmatch "1060") {
    Write-Host "!!! предупреждение: ожидали GTX 1060, увидели: $gpuLine (продолжаем — VRAM 6 ГБ проверит verify)" -ForegroundColor Yellow
}

Set-Marker -Step $step -Note "venv + QLoRA-стек + студент готовы"
exit 0


