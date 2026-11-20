# ============================================================
# verify.ps1 — СВОДНЫЙ АУДИТ ДОМА (ТЗ Раздел 9, шаг 5).
# Версии компонентов, модели и размеры, свободная RAM (план 44 из 64 — 0.1),
# VRAM 6 ГБ, порты 8082/5001 свободны (5000 не трогаем — 6.4), .env не в индексе git (2.4),
# selftest офлайн-тестов (правило 6.6).
# ============================================================
. "$PSScriptRoot\_common.ps1"
$step = "05_verify"
trap {
    $m = $_.Exception.Message
    $ln = ""
    try { if ($_.InvocationInfo) { $ln = " (строка $($_.InvocationInfo.ScriptLineNumber))" } } catch {}
    Write-StepLog -Step "05_verify" -Message "КРИТ: непредвиденная ошибка: $m$ln"
    Write-Host "!!! [05_verify] КРИТ: $m$ln" -ForegroundColor Red
    exit 1
}

$failures = @()

function Check {
    param([string]$Name, [bool]$Ok, [string]$Detail = "")
    if ($Ok) { Write-Host "  [ОК]  $Name $Detail" -ForegroundColor Green }
    else     { Write-Host "  [ПРОВАЛ] $Name $Detail" -ForegroundColor Red; $script:failures += "$Name $Detail" }
    Write-StepLog -Step $step -Message "$(if ($Ok) {'[ОК]'} else {'[ПРОВАЛ]'}) $Name $Detail"
}

Write-Host ""
Write-Host "АУДИТ ДОМА: $script:HomeDir"
Write-Host "----------------------------------------------"

# --- 1. Компоненты ---
# Урок 12.11.2026 (коммит 26): ЗДЕСЬ упал сам аудит — llama-server.exe печатает баннер
# версии в stderr (весь лог llama.cpp идёт в stderr), и `& exe --version 2>&1` при
# ErrorActionPreference=Stop (_common.ps1) превращает первую строку stderr нативной
# команды в терминающую NativeCommandError (грабли PS 5.1; они же описаны в
# _common.ps1 у Invoke-ExeProbe, пункт «б»). Все нативные зонды ниже — через
# Invoke-ExeProbe: System.Diagnostics.Process, никакого 2>&1, таймаут обязателен.
$pyVer = "нет"
if (Test-Path $script:PythonExe) {
    $pyProbe = Invoke-ExeProbe -FilePath $script:PythonExe -Arguments "--version" -TimeoutSec 20
    $pyVer = ("$($pyProbe.Output)" -split "`r?`n" | Where-Object { "$_".Trim() -ne "" } | Select-Object -First 1)
    if ("$pyVer".Trim() -eq "") { $pyVer = "нет" }
}
Check -Name "Python 3.11" -Ok ($pyVer -match "3\.11\.\d+") -Detail "($pyVer)"

$llamaVer = "нет"
if (Test-Path $script:LlamaServerExe) {
    $llProbe = Invoke-ExeProbe -FilePath $script:LlamaServerExe -Arguments "--version" -TimeoutSec 30
    $llamaVer = ("$($llProbe.Output)" -split "`r?`n" | Where-Object { "$_".Trim() -ne "" } | Select-Object -First 1)
    if ("$llamaVer".Trim() -eq "") { $llamaVer = "нет" }
}
# Сломанный exe (нет vcruntime140.dll) покажет диалог — Invoke-ExeProbe убьёт его по
# таймауту 30 с и вернёт пустой вывод > «нет» > честный ПРОВАЛ вместо вечного висения.
Check -Name "llama-server" -Ok ("$($llProbe.Output)" -match "version") -Detail "($llamaVer)"

$venvOk = Test-Path $script:VenvPython
Check -Name "venv" -Ok $venvOk

if ($venvOk) {
    # Холодный импорт torch на машине бывает долгим — таймаут 180 с.
    $tProbe = Invoke-ExeProbe -FilePath $script:VenvPython -Arguments '-c "import torch; print(torch.__version__, torch.cuda.is_available())"' -TimeoutSec 180
    $tLines = @("$($tProbe.Output)" -split "`r?`n" | Where-Object { "$_".Trim() -ne "" })
    $torchInfo = if ($tLines.Count -gt 0) { "$($tLines[$tLines.Count - 1])" } else { "нет вывода" }
    $cudaOk = ("$torchInfo" -match "True$|True ") -and (-not $tProbe.TimedOut)
    Check -Name "torch + CUDA" -Ok $cudaOk -Detail "($torchInfo)"
}

# --- 2. Модели ---
# Урок 13.11.2026 (коммит 27): размер сверяем в тех же ГБ, что и при скачивании
# (1 ГБ = 10^9 байт). Прежнее деление на 1GB (2^30) показывало ГиБ: файл мозга
# «17.28» на деле 18.56 ГБ и в порядке — но цифра сбивала с толку. Мозг Q4_K_M
# вне допуска = провал аудита (битый мозг не поднимет смоук); опциональный Q6_K
# вне допуска = жёлтое [--] предупреждение (докачает 03b), НЕ провал: опция не
# должна блокировать дом (Раздел 8).
foreach ($q in @(@{N="Q4_K_M"; GB=18.63; Opt=$false}, @{N="Q6_K"; GB=25.10; Opt=$true})) {
    $f = Join-Path $script:ModelsDir "Qwen3-30B-A3B-$($q.N).gguf"
    if (Test-Path $f) {
        $gb = [math]::Round((Get-Item $f).Length / 1000000000, 2)
        $low = [math]::Round($q.GB * 0.90, 2)
        $high = [math]::Round($q.GB * 1.10, 2)
        if ($gb -ge $low -and $gb -le $high) {
            Check -Name "модель $($q.N)" -Ok $true -Detail "($gb ГБ из ~$($q.GB) — в допуске)"
        } elseif ($q.Opt) {
            Write-Host "  [--]   модель $($q.N): $gb ГБ из ~$($q.GB) — вне допуска $low-$high (недокачана?). Не влияет на работу: 03b_download_model_q6k.bat докачает с места обрыва, либо удалите файл, чтобы не путал светофор" -ForegroundColor Yellow
            Write-StepLog -Step $step -Message "[--] модель $($q.N): $gb ГБ вне допуска $low-$high (опция — не провал)"
        } else {
            Check -Name "модель $($q.N)" -Ok $false -Detail "($gb ГБ из ~$($q.GB), допуск $low-$high — недокачан: перезапустите шаг 03a, докачка продолжится с места обрыва)"
        }
    } elseif (-not $q.Opt) {
        Check -Name "модель $($q.N)" -Ok $false -Detail "(файла нет — конвейер сломан)"
    } else {
        Write-Host "  [--]   модель $($q.N): опция, не скачана (Раздел 8)" -ForegroundColor DarkGray
    }
}
$student = Join-Path $script:ModelsDir "Qwen2.5-3B-Instruct\config.json"
Check -Name "студент Qwen2.5-3B-Instruct" -Ok (Test-Path $student)

# --- 3. RAM: план 44 из 64 ---
$total = Get-TotalRamGB
$free = Get-FreeRamGB
Check -Name "RAM всего 64 ГБ" -Ok ($total -ge 60) -Detail "(факт: $total ГБ)"
Check -Name "RAM свободно > 40 ГБ" -Ok ($free -ge 40) -Detail "(свободно: $free ГБ)"

# --- 4. VRAM 6 ГБ ---
$vramInfo = "нет nvidia-smi"
$nvCmd = Get-Command nvidia-smi.exe -ErrorAction SilentlyContinue
if ($nvCmd) {
    $nProbe = Invoke-ExeProbe -FilePath $nvCmd.Source -Arguments "--query-gpu=memory.total,name --format=csv,noheader" -TimeoutSec 20
    $nLines = @("$($nProbe.Output)" -split "`r?`n" | Where-Object { "$_".Trim() -ne "" })
    if ($nLines.Count -gt 0) {
        $vramInfo = "$($nLines[0])$(if ($nProbe.TimedOut) { ' (таймаут)' })"
    }
}
$vramOk = "$vramInfo" -match "6144|6143|614[0-9]" # 6 ГБ в MiB
Check -Name "VRAM 6 ГБ (GTX 1060)" -Ok $vramOk -Detail "($vramInfo)"

# --- 5. Порты: 8082 и 5001 СВОБОДНЫ, 5000 не используем ---
Check -Name "порт 8082 свободен" -Ok (Test-PortFree -Port 8082)
Check -Name "порт 5001 свободен" -Ok (Test-PortFree -Port 5001)

# --- 6. .env не в индексе git (правило 0.2 / Раздел 2.4) ---
# Урок 12.11.2026 (коммит 26): git может быть не установлен вовсе (05_install_git —
# отдельный шаг) и папка дома может не быть репозиторием. Прежние вызовы
# `git ... 2>&1`/`2>$null` при EAP=Stop были бы следующей миной: git ls-files
# --error-unmatch в ХОРОШЕМ случае (.env не трекается) печатает «fatal: pathspec .env
# did not match any files» именно в stderr — терминающая ошибка. Проверка стала
# мягкой: нет git / нет репозитория = пропуск с пометкой, не провал аудита.
$gitCmd = Get-Command git.exe -ErrorAction SilentlyContinue
if (-not $gitCmd) {
    Check -Name ".env не в git" -Ok $true -Detail "(git не установлен — проверка пропущена; шаг 05_install_git ставит его в tools\git)"
} else {
    Push-Location $script:HomeDir
    try {
        $envExists = Test-Path (Join-Path $script:HomeDir ".env")
        $gProbe = Invoke-ExeProbe -FilePath $gitCmd.Source -Arguments "ls-files --error-unmatch .env" -TimeoutSec 15
        $tracked = (-not $gProbe.TimedOut) -and ($gProbe.Code -eq 0)
        if ("$($gProbe.Output)" -match "not a git repository") {
            Check -Name ".env не в git" -Ok $true -Detail "(папка не git-репозиторий — секретам некуда утекать)"
        } else {
            $detail = "(файла .env нет)"
            if ($envExists) { $detail = "(файл есть, в git не попадает)" }
            if ($tracked)  { $detail = "(файл есть И он в индексе — секрет утекёт!)" }
            Check -Name ".env не в git" -Ok (-not $tracked) -Detail $detail
        }
    } finally { Pop-Location }
}

# --- 7. Selftest: компиляция всех наших .py тем python.exe, что и тесты ---
# Урок 13.11.2026 (коммит 28): web/app.py держал «\» внутри выражения f-string —
# такой синтаксис разрешили только в Python 3.12 (PEP 701). Песочница разработчика
# (3.12) молчала и 125 тестов были зелёными, а на 3.11 машины файл падал SyntaxError
# ещё при импорте — pytest отдавал «1 error during collection» без причины на ладони.
# compileall за секунды собирает ВСЕ наши .py тем самым интерпретатором, что и тесты:
# несовместимость с версией машины всплывает СРАЗУ, с именем файла и строкой.
if ($venvOk) {
    Write-Host "  selftest: компиляция всех .py (python venv, офлайн)..."
    $pyDirs = @("core","sensors","safety","web","tests","scripts","evolution","growth") |
        Where-Object { Test-Path (Join-Path $script:HomeDir $_) }
    Push-Location $script:HomeDir
    $cProbe = Invoke-ExeProbe -FilePath $script:VenvPython -Arguments "-m compileall -q $($pyDirs -join ' ')" -TimeoutSec 120
    Pop-Location
    $cLines = @("$($cProbe.Output)" -split "`r?`n" | Where-Object { "$_".Trim() -ne "" })
    foreach ($l in $cLines) { Write-StepLog -Step $step -Message "compileall: $l" }
    $compileOk = (($cProbe.Code -eq 0) -and (-not $cProbe.TimedOut))
    foreach ($l in $cLines) { Write-Host "    $l" }
    if (-not $compileOk) {
        Write-Host "  РАЗБОР: SyntaxError = код не собирается версией Python машины (частая причина — конструкции 3.12 в f-string: «\» в выражении или те же кавычки). Правьте файл из вывода выше." -ForegroundColor Yellow
    }
    Check -Name "selftest compile (.py)" -Ok $compileOk
}

# --- 8. Selftest: офлайн-тесты ядра (мок-мозг, JSON-память) ---
# Урок 12.11.2026 (коммит 26): pytest при сбоях пишет в stderr — `2>&1` при EAP=Stop
# ронял бы шаг; запуск через Invoke-ExeProbe, таймаут 600 с.
# Урок 13.11.2026 (коммит 27): при провале хвост 3 строк обрезал причину («1 error
# during collection» без трассировки). Теперь: полный вывод pytest — в журнал шага
# (6.6), на консоль при провале — хвост 15 строк, затем автоматическая диагностика
# venv (scripts\diag_venv.py: каждый нужный пакет импортируется отдельно, печатается
# версия или ошибка) и подсказка точечного повтора.
if ($venvOk -and (Test-Path (Join-Path $script:HomeDir "tests"))) {
    Write-Host "  selftest: pytest (офлайн)..."
    Push-Location $script:HomeDir
    $env:MARFA_HOME = Join-Path $env:TEMP "marfa_selftest"
    $pProbe = Invoke-ExeProbe -FilePath $script:VenvPython -Arguments "-m pytest tests/ -q" -TimeoutSec 600
    $pLines = @("$($pProbe.Output)" -split "`r?`n" | Where-Object { "$_".Trim() -ne "" })
    foreach ($l in $pLines) { Write-StepLog -Step $step -Message "pytest: $l" }   # полный вывод — в журнал (6.6)
    $selftestOk = (($pProbe.Code -eq 0) -and (-not $pProbe.TimedOut))
    $tailCount = if ($selftestOk) { 3 } else { 15 }
    foreach ($l in @($pLines | Select-Object -Last $tailCount)) { Write-Host "    $l" }
    if (-not $selftestOk) {
        Write-Host ""
        Write-Host "  РАЗБОР: причина — в хвосте выше (ищите SyntaxError / ModuleNotFoundError / ImportError)." -ForegroundColor Yellow
        Write-Host "  Диагностика venv по одному пакету:" -ForegroundColor Yellow
        $dProbe = Invoke-ExeProbe -FilePath $script:VenvPython -Arguments "`"$script:HomeDir\scripts\diag_venv.py`"" -TimeoutSec 120
        $dLines = @("$($dProbe.Output)" -split "`r?`n" | Where-Object { "$_".Trim() -ne "" })
        foreach ($l in $dLines) { Write-Host "    $l" }
        foreach ($l in $dLines) { Write-StepLog -Step $step -Message "diag_venv: $l" }
        Write-Host "  Точечный повтор одного файла: venv\Scripts\python.exe -m pytest tests\test_monitor_web.py -q" -ForegroundColor Yellow
        Write-Host "  Полный вывод: logs\install_05_verify.log" -ForegroundColor Yellow
    }
    Check -Name "selftest pytest" -Ok $selftestOk -Detail "$(if ($selftestOk) { '' } else { '(хвост вывода выше — пришлите его целиком)' })"
    Remove-Item Env:MARFA_HOME -ErrorAction SilentlyContinue
    Pop-Location
}

Write-Host "----------------------------------------------"
if ($failures.Count -gt 0) {
    Write-Host "АУДИТ ПРОВАЛЕН: $($failures.Count) пунктов:" -ForegroundColor Red
    $failures | ForEach-Object { Write-Host "   - $_" -ForegroundColor Red }
    exit 1
}
Write-Host "АУДИТ ЧИСТ: дом в порядке (план 44 из 64 ГБ, порты свободны, секреты не утекают)" -ForegroundColor Green
exit 0


