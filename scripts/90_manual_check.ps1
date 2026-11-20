# ============================================================
# 90_manual_check.ps1 — СВЕТОФОР РУЧНОГО РЕЖИМА («всё руками», урок 12.11.2026).
# Ничего не качает и не ставит: показывает, что уже есть в доме, чего не хватает,
# и для каждой недостающей позиции печатает точную ссылку, имя файла и место.
# Уже скачанное конвейер 00_install_all.bat подхватывает сам (кэш-first).
# Всегда завершается кодом 0 — это проверка, а не шаг конвейера.
# ============================================================
. "$PSScriptRoot\_common.ps1"

$script:nOk = 0
$script:nNo = 0

function Mark-Ok {
    param([string]$T)
    Write-Host "  [ЕСТЬ]   $T" -ForegroundColor Green
    $script:nOk++
}
function Mark-No {
    param([string]$T, [string[]]$H)
    Write-Host "  [НЕТ]    $T" -ForegroundColor Red
    foreach ($h in $H) { Write-Host "         $h" -ForegroundColor Yellow }
    $script:nNo++
}
function Mark-Near {
    # «почти»: файл лежит в downloads\ или недокачан — докачает/распакует конвейер сам
    param([string]$T, [string[]]$H)
    Write-Host "  [ПОЧТИ]  $T" -ForegroundColor Yellow
    foreach ($h in $H) { Write-Host "         $h" -ForegroundColor Yellow }
}
function Mark-Opt {
    param([string]$T)
    Write-Host "  [ОПЦИЯ]  $T" -ForegroundColor DarkGray
}
function Format-Size {
    param([long]$Bytes)
    if ($Bytes -ge 1GB) { return ("{0} ГБ" -f [math]::Round($Bytes / 1GB, 2)) }
    return ("{0} МБ" -f [math]::Round($Bytes / 1MB, 1))
}

Write-Host ""
Write-Host "=============================================================="
Write-Host "РУЧНОЙ РЕЖИМ: светофор дома $script:HomeDir"
Write-Host "ничего не качает; у каждой [НЕТ] — ссылка и куда положить файл"
Write-Host "=============================================================="

# --- 1. Python 3.11 ---
$pyFound = $null
if (Test-Path $script:PythonExe) { $pyFound = $script:PythonExe }
if (-not $pyFound) { $pyFound = Find-WorkingPython311 }
if ($pyFound) {
    # Урок 12.11.2026 (коммит 26): зонды нативных команд — только Invoke-ExeProbe,
    # не через 2>&1: при EAP=Stop stderr роняет скрипт терминающей ошибкой.
    $vProbe = Invoke-ExeProbe -FilePath $pyFound -Arguments "--version" -TimeoutSec 20
    $v = ("$($vProbe.Output)" -split "`r?`n" | Where-Object { "$_".Trim() -ne "" } | Select-Object -First 1)
    $pipProbe = Invoke-ExeProbe -FilePath $pyFound -Arguments "-m pip --version" -TimeoutSec 30
    if (-not $pipProbe.TimedOut -and $pipProbe.Code -eq 0) {
        Mark-Ok "Python: $pyFound ($v), pip жив — шаг 01 подключит сам, переустановка НЕ нужна"
    } else {
        Mark-Near "Python есть ($pyFound), но pip не отвечает" @(
            "шаг 01 теперь чинит pip сам через ensurepip — просто запустите 00_install_all.bat",
            "или вручную прямо сейчас: `"$pyFound`" -m ensurepip --upgrade --default-pip"
        )
    }
} else {
    $inst = Join-Path $script:DownloadsDir "python-3.11.9-amd64.exe"
    if (Test-Path $inst) {
        Mark-No "Python 3.11 не найден, но инсталлятор уже в downloads\" @(
            "запустите двойным кликом: $inst",
            "подойдёт и 'Install Now', и Customize -> путь C:\Marfa\python311",
            "после установки снова запустите этот светофор"
        )
    } else {
        Mark-No "Python 3.11 не найден" @(
            "скачайте: https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe",
            "зеркала: mirrors.huaweicloud.com/python/3.11.9/ или registry.npmmirror.com/-/binary/python/3.11.9/",
            "запустите двойным кликом ('Install Now' достаточно), затем снова этот светофор"
        )
    }
}

# --- 2. MSVC Redistributable (без него llama-server виснет на vcruntime140.dll) ---
$vcKey = "HKLM:\SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64"
if (Test-Path $vcKey) {
    Mark-Ok "MSVC Redistributable x64"
} else {
    Mark-No "MSVC Redistributable x64" @(
        "скачайте: https://aka.ms/vs/17/release/vc_redist.x64.exe",
        "запустите двойным кликом -> Install (перезагрузка не обязательна)"
    )
}

# --- 3. llama.cpp ---
$zip = @(Get-ChildItem $script:DownloadsDir -Filter "llama-*.zip" -ErrorAction SilentlyContinue |
         Where-Object { $_.Name -match "bin-win-(avx2|cpu)-x64\.zip$" -and $_.Length -gt 1MB } |
         Sort-Object Name -Descending)
if (Test-Path $script:LlamaServerExe) {
    Mark-Ok "llama.cpp: llama-server.exe в llama.cpp\"
} elseif ($zip.Count -gt 0) {
    Mark-Near "llama.cpp: zip уже в downloads\ ($($zip[0].Name), $(Format-Size $zip[0].Length))" @(
        "распаковывать вручную не нужно — шаг 02 сделает это сам при запуске 00_install_all.bat"
    )
} else {
    Mark-No "llama.cpp (нет ни llama.cpp\llama-server.exe, ни zip в downloads\)" @(
        "откройте: https://github.com/ggml-org/llama.cpp/releases/latest",
        "скачайте llama-<версия>-bin-win-cpu-x64.zip (или -avx2-x64.zip, ~23 МБ)",
        "положите в: $script:DownloadsDir — имя файла НЕ переименовывать"
    )
}

# --- 4. Мозг Q4_K_M (18.63 ГБ) ---
$f = Join-Path $script:ModelsDir "Qwen3-30B-A3B-Q4_K_M.gguf"
$exp = 18.63
if (Test-Path $f) {
    $gb = [math]::Round((Get-Item $f).Length / 1GB, 2)
    if ($gb -ge ($exp * 0.90) -and $gb -le ($exp * 1.10)) {
        Mark-Ok "мозг Q4_K_M: $gb ГБ (в допуске) — models\Qwen3-30B-A3B-Q4_K_M.gguf"
    } else {
        Mark-Near "мозг Q4_K_M: файл есть, но $gb ГБ из ~$exp — недокачан" @(
            "перезапустите 00_install_all.bat — шаг 03a докачает с места обрыва (curl -C -)",
            "либо скачайте заново браузером и замените файл целиком"
        )
    }
} else {
    Mark-No "мозг Q4_K_M, 18.63 ГБ" @(
        "скачайте браузером (по порядку, кто дотянет):",
        "  1) https://huggingface.co/Qwen/Qwen3-30B-A3B-GGUF/resolve/main/Qwen3-30B-A3B-Q4_K_M.gguf",
        "  2) https://modelscope.cn/models/Qwen/Qwen3-30B-A3B-GGUF/resolve/master/Qwen3-30B-A3B-Q4_K_M.gguf",
        "  3) https://huggingface.co/unsloth/Qwen3-30B-A3B-GGUF/resolve/main/Qwen3-30B-A3B-Q4_K_M.gguf",
        "положите в: $script:ModelsDir — имя файла должно совпасть ТОЧНО"
    )
}

# --- 5. Q6_K (опция) ---
$f6 = Join-Path $script:ModelsDir "Qwen3-30B-A3B-Q6_K.gguf"
if (Test-Path $f6) {
    Mark-Ok "мозг Q6_K: $(Format-Size (Get-Item $f6).Length) (опция)"
} else {
    Mark-Opt "Q6_K 25.10 ГБ — опция, качается только по решению Ильи (Раздел 8)"
}

# --- 6. Студент Qwen2.5-3B-Instruct ---
$st = Join-Path $script:ModelsDir "Qwen2.5-3B-Instruct\config.json"
if (Test-Path $st) {
    Mark-Ok "студент Qwen2.5-3B-Instruct: models\Qwen2.5-3B-Instruct\"
} else {
    Mark-Near "студент Qwen2.5-3B-Instruct (~6 ГБ) — его скачает шаг 04 сам" @(
        "если HF не дотянет, шаг 04 повторит через hf-mirror.com; если и это не пройдёт:",
        "скачайте вручную с https://huggingface.co/Qwen/Qwen2.5-3B-Instruct/tree/main файлы",
        "(ВНИМАНИЕ: единого model.safetensors нет — модель лежит двумя шардами):",
        "  config.json, generation_config.json, model-00001-of-00002.safetensors,",
        "  model-00002-of-00002.safetensors, model.safetensors.index.json,",
        "  tokenizer.json, tokenizer_config.json, vocab.json, merges.txt",
        "положите в: $script:ModelsDir\Qwen2.5-3B-Instruct\",
        "проверка ручных файлов: venv\Scripts\python.exe scripts\download_student.py models\Qwen2.5-3B-Instruct --check-only"
    )
}

# --- 7. venv ---
if (Test-Path $script:VenvPython) {
    Mark-Ok "venv: venv\Scripts\python.exe"
} else {
    Mark-Near "venv — создаст шаг 04 автоматически (pip + torch CUDA + QLoRA-стек)" @(
        "если pip не дотянет pypi.org, он сам повторит через зеркало tuna — вручную ничего не нужно"
    )
}

# --- 8. git (только для пуша в GitHub) ---
$gitExe = Join-Path $script:HomeDir "tools\git\bin\git.exe"
$gitSys = (Get-Command git.exe -ErrorAction SilentlyContinue)
if (Test-Path $gitExe) {
    Mark-Ok "git: tools\git\bin\git.exe"
} elseif ($gitSys) {
    # Урок 12.11.2026 (коммит 26): `git --version 2>&1` — та же мина stderr при EAP=Stop.
    $gvProbe = Invoke-ExeProbe -FilePath $gitSys.Source -Arguments "--version" -TimeoutSec 20
    Mark-Ok "git: системный ($("$($gvProbe.Output)".Trim()))"
} else {
    Mark-Opt "git — нужен только для пуша в GitHub; 05_install_git.bat поставит в tools\git"
}

# --- 9. Что уже лежит в downloads\ (ручные файлы) ---
Write-Host ""
Write-Host "  downloads\ (ручные файлы):" -ForegroundColor Cyan
$files = @(Get-ChildItem $script:DownloadsDir -File -ErrorAction SilentlyContinue |
           Where-Object { $_.Length -gt 1MB } | Sort-Object Name)
if ($files.Count -eq 0) {
    Write-Host "    (пока пусто)" -ForegroundColor DarkGray
}
foreach ($x in $files) {
    Write-Host "    $($x.Name)  ($(Format-Size $x.Length))" -ForegroundColor Gray
}

# --- 10. Железо и порты (информационно) ---
try {
    $drive = Get-PSDrive -Name ((Resolve-Path $script:HomeDir).Drive.Name)
    $freeGB = [math]::Round($drive.Free / 1GB, 1)
    Write-Host ""
    Write-Host "  Железо: RAM всего $(Get-TotalRamGB) ГБ, свободно $(Get-FreeRamGB) ГБ; на диске свободно $freeGB ГБ (нужно >= 90)"
    $p8082 = "ЗАНЯТ (мозг уже запущен?)"; if (Test-PortFree -Port 8082) { $p8082 = "свободен" }
    $p5001 = "ЗАНЯТ (панель уже запущена?)"; if (Test-PortFree -Port 5001) { $p5001 = "свободен" }
    Write-Host "  Порты: 8082 $p8082; 5001 $p5001"
} catch {}

# --- Итог ---
Write-Host ""
Write-Host "=============================================================="
if ($script:nNo -eq 0) {
    Write-Host "ИТОГ: всё критичное на месте ($script:nOk позиций готово). Запускайте:" -ForegroundColor Green
    Write-Host "    scripts\00_install_all.bat" -ForegroundColor Green
    Write-Host "готовые шаги пропустятся по маркерам, остальное доустановится." -ForegroundColor Green
} else {
    Write-Host "ИТОГ: позиций с [НЕТ]: $script:nNo (каждая с жёлтой подсказкой выше)." -ForegroundColor Yellow
    Write-Host "Скачайте их по ссылкам, положите в указанные места, снова запустите светофор:" -ForegroundColor Yellow
    Write-Host "    scripts\90_manual_check.bat" -ForegroundColor Yellow
    Write-Host "Когда [НЕТ] не останется — scripts\00_install_all.bat" -ForegroundColor Yellow
}
Write-Host "=============================================================="
exit 0


