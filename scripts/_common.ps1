# ============================================================
# _common.ps1 — общие функции установочного комплекта (ТЗ Раздел 9)
# Дом Марфа: всё живёт только внутри C:\Marfa (ТЗ 2.3).
# Правило конвейера (по духу 6.7): провал шага останавливает всё,
# повторный запуск пропускает сделанное по маркерам data\install_state\*.done.
# ============================================================
$ErrorActionPreference = "Stop"

# Дом = папка над scripts\. Скрипты живут в репозитории, дом может быть копией на Z440.
$script:HomeDir = Split-Path -Parent $PSScriptRoot
$script:DataDir = Join-Path $script:HomeDir "data"
$script:LogsDir = Join-Path $script:HomeDir "logs"
$script:ModelsDir = Join-Path $script:HomeDir "models"
$script:DownloadsDir = Join-Path $script:HomeDir "downloads"
$script:StateDir = Join-Path $script:DataDir "install_state"
$script:PythonExe = Join-Path $script:HomeDir "python311\python.exe"
# Урок 12.11.2026: если на машине уже стоял Python 3.11.x, шаг 01 подключает его
# и пишет путь в data\python_path.txt (тихий инсталлятор при уже установленной
# версии молча выходит 0, ничего не ставя). Все шаги используют этот путь.
$pyOverrideFile = Join-Path $script:DataDir "python_path.txt"
if (Test-Path $pyOverrideFile) {
    $pyOverride = (Get-Content $pyOverrideFile -TotalCount 1 -ErrorAction SilentlyContinue)
    if ($pyOverride) {
        $pyOverride = $pyOverride.Trim()
        if (($pyOverride -ne "") -and (Test-Path $pyOverride)) { $script:PythonExe = $pyOverride }
    }
}
$script:VenvPython = Join-Path $script:HomeDir "venv\Scripts\python.exe"
$script:LlamaServerExe = Join-Path $script:HomeDir "llama.cpp\llama-server.exe"

foreach ($d in @($script:DataDir, $script:LogsDir, $script:ModelsDir,
                 $script:DownloadsDir, $script:StateDir)) {
    if (-not (Test-Path $d)) { New-Item -ItemType Directory -Path $d -Force | Out-Null }
}

function Get-Home { return $script:HomeDir }

function Test-Marker {
    param([Parameter(Mandatory)][string]$Step)
    return Test-Path (Join-Path $script:StateDir "$Step.done")
}

function Set-Marker {
    param([Parameter(Mandatory)][string]$Step, [string]$Note = "")
    $path = Join-Path $script:StateDir "$Step.done"
    "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $Note" | Set-Content -Path $path -Encoding UTF8
    Write-Step "МАРКЕР: $Step.done $Note"
}

function Write-Step {
    param([Parameter(Mandatory)][string]$Message)
    Write-Host "[$(Get-Date -Format 'HH:mm:ss')] $Message"
}

function Write-StepLog {
    # Журнал шага — источник правды (правило 6.6): logs\install_<step>.log
    param([Parameter(Mandatory)][string]$Step, [Parameter(Mandatory)][string]$Message)
    $log = Join-Path $script:LogsDir "install_$Step.log"
    "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] $Message" | Add-Content -Path $log -Encoding UTF8
}

function Fail {
    # Провал шага: пишет лог и завершает шаг кодом 1 — конвейер 00 останавливается.
    param([Parameter(Mandatory)][string]$Step, [Parameter(Mandatory)][string]$Why)
    Write-StepLog -Step $Step -Message "ПРОВАЛ: $Why"
    Write-Host "!!! [$Step] ПРОВАЛ: $Why" -ForegroundColor Red
    exit 1
}

function Start-MarfaProcess {
    # Низкоуровневый запуск через System.Diagnostics.Process — НЕ Start-Process.
    # Урок 12.11.2026 (коммит 24): на Windows PowerShell 5.1 объект от Start-Process
    # -PassThru теряет хэндл процесса после ожидания — ExitCode = $null навсегда, даже
    # после повторного параметless WaitForExit() (живой pip 24.0 признавался мёртвым:
    # «код завершения не получен ()»). По документации .NET (Process.ExitCode) хэндл
    # нужно получить ДО завершения процесса: здесь хэндл принадлежит нашему объекту с
    # момента Start() и кэшируется сразу ($null = $p.Handle) — код возврата читается
    # всегда. Потоки вывода читаются асинхронно ДО ожидания (иначе deadlock на
    # заполненном буфере пайпа), таймаут прерывает зависший exe (урок 12.11.2026:
    # диалог vcruntime140.dll вешал шаг навсегда).
    # Возврат: @{ TimedOut; Code; Output; Error }.
    param(
        [Parameter(Mandatory)][string]$FilePath,
        [string]$Arguments = "",             # пусто — exe без аргументов (зонд)
        [Parameter(Mandatory)][int]$TimeoutSec
    )
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $FilePath
    $psi.Arguments = $Arguments          # строка целиком: кавычки расставлены вызывающим
    $psi.UseShellExecute = $false        # перенаправление работает только при false
    $psi.CreateNoWindow = $true          # pip/venv не мигают чёрными окнами
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $p = New-Object System.Diagnostics.Process
    $p.StartInfo = $psi
    try {
        if (-not $p.Start()) {
            return @{ TimedOut = $false; Code = $null; Output = ""; Error = "Process.Start вернул false" }
        }
    } catch {
        return @{ TimedOut = $false; Code = $null; Output = ""; Error = $_.Exception.Message }
    }
    $null = $p.Handle                    # кэш хэндла, пока процесс жив — ключ к ExitCode
    $outTask = $p.StandardOutput.ReadToEndAsync()
    $errTask = $p.StandardError.ReadToEndAsync()
    $timedOut = (-not $p.WaitForExit($TimeoutSec * 1000))
    if ($timedOut) { try { $p.Kill() } catch {} }
    $null = $p.WaitForExit()             # финализация кода возврата (требование .NET)
    $out = ""; $err = ""
    try { if ($outTask.Wait(5000)) { $out = "$($outTask.Result)" } } catch {}
    try { if ($errTask.Wait(5000)) { $err = "$($errTask.Result)" } } catch {}
    $code = $null
    try { $code = $p.ExitCode } catch {}
    $p.Close()
    return @{ TimedOut = $timedOut; Code = $code; Output = $out; Error = $err }
}

function Invoke-Logged {
    # Запуск внешней команды с телеметрией в лог шага. Провал наружного кода = провал шага.
    # Таймаут обязателен для всех путей: TimeoutSec 0 («большая установка») -> 14400с
    # (4 ч хватает и torch 2.4 ГБ, и студенту 7 ГБ; зависший процесс больше не вешает
    # конвейер навсегда). Вывод процесса (stdout+stderr) дописывается в журнал шага.
    param(
        [Parameter(Mandatory)][string]$Step,
        [Parameter(Mandatory)][string]$FilePath,
        [string]$Arguments = "",
        [int]$TimeoutSec = 0
    )
    Write-StepLog -Step $Step -Message "ЗАПУСК: $FilePath $Arguments"
    if ($TimeoutSec -le 0) { $TimeoutSec = 14400 }
    $r = Start-MarfaProcess -FilePath $FilePath -Arguments $Arguments -TimeoutSec $TimeoutSec
    $outText = "$($r.Output)".TrimEnd()
    $errText = "$($r.Error)".TrimEnd()
    if ($outText -ne "") { Add-Content -Path (Join-Path $script:LogsDir "install_$Step.log") -Value $outText -Encoding UTF8 }
    if ($errText -ne "") { Add-Content -Path (Join-Path $script:LogsDir "install_$Step.log") -Value $errText -Encoding UTF8 }
    if ($r.TimedOut) {
        Fail -Step $Step -Why "таймаут ${TimeoutSec}с: $FilePath $Arguments"
    }
    $ec = $r.Code
    if ($ec -isnot [int]) {
        Write-StepLog -Step $Step -Message "код завершения не получен ($ec) — считаем провалом; вывод процесса в строках журнала выше"
        return -1
    }
    return $ec
}

function Invoke-ExeProbe {
    # Запуск exe с таймаутом и захватом вывода (через Start-MarfaProcess). Зачем:
    # (а) сломанный exe (нет vcruntime140.dll, SmartScreen) может показать диалог и
    # висеть вечно — таймаут прерывает (урок 12.11.2026, три молчаливых запуска шага 02);
    # (б) вывод не через 2>&1 — при ErrorActionPreference=Stop перенаправленный stderr
    # нативной команды не превращается в терминающую ошибку (грабли PowerShell 5.1);
    # (в) ExitCode читается честно: у Start-Process -PassThru на PS 5.1 код возврата
    # терялся ($null) — живой pip 24.0 признавался мёртвым (урок 12.11.2026).
    param(
        [Parameter(Mandatory)][string]$FilePath,
        [string]$Arguments = "",
        [int]$TimeoutSec = 30
    )
    $r = Start-MarfaProcess -FilePath $FilePath -Arguments $Arguments -TimeoutSec $TimeoutSec
    $output = "$($r.Output)".TrimEnd()
    $errText = "$($r.Error)".TrimEnd()
    if ($errText -ne "") {
        if ($output -eq "") { $output = $errText } else { $output = "$output`r`n$errText" }
    }
    if ($r.TimedOut) { return @{ TimedOut = $true; Code = -1; Output = $output } }
    $code = $r.Code
    if ($code -isnot [int]) { $code = -1 }   # старт не удался (нет exe и т.п.) — не выдаём за таймаут
    return @{ TimedOut = $false; Code = $code; Output = $output }
}

function Test-PortFree {
    # Проверка, что порт СВОБОДЕН (для 8082/5001 перед стартом; 5000 не трогаем — 6.4)
    param([Parameter(Mandatory)][int]$Port)
    $busy = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue
    return ($null -eq $busy)
}

function Get-FreeRamGB {
    $os = Get-CimInstance Win32_OperatingSystem
    return [math]::Round($os.FreePhysicalMemory * 1KB / 1GB, 1)
}

function Get-TotalRamGB {
    $os = Get-CimInstance Win32_OperatingSystem
    return [math]::Round($os.TotalVisibleMemorySize * 1KB / 1GB, 1)
}

function Test-FileSha256 {
    # Строгое сравнение SHA-256 (регистр не важен).
    param([Parameter(Mandatory)][string]$Path, [Parameter(Mandatory)][string]$Sha256)
    if (-not (Test-Path $Path)) { return $false }
    return ((Get-FileHash -Path $Path -Algorithm SHA256).Hash -ieq $Sha256)
}

function Rename-Bad {
    # Битый/лишний файл уводим в *.bad-<метка>, чтобы не мешал новой загрузке с нуля.
    param([Parameter(Mandatory)][string]$Step, [Parameter(Mandatory)][string]$Path)
    if (Test-Path $Path) {
        $bad = "$Path.bad-$(Get-Date -Format 'yyyyMMdd-HHmmss')"
        Move-Item -Path $Path -Destination $bad -Force
        Write-StepLog -Step $Step -Message "подозрительный файл убран в $bad"
        Write-Step "подозрительный файл убран в $(Split-Path -Leaf $bad)"
    }
}

function Find-WorkingPython311 {
    # Единый поиск работающего Python 3.11.x (урок 12.11.2026: 3.11.9 уже стоит на
    # машине — тихий инсталлятор выходит 0 за секунды, ничего не ставя). Порядок:
    # реестр (HKCU/HKLM/WOW6432Node) -> py-лаунчер -> типовые папки -> дом.
    # Каждый кандидат проверяется Invoke-ExeProbe (таймаут 15 с) — сломанный exe
    # не повесит шаг системным диалогом. Возвращает путь к python.exe или $null.
    $cands = @()
    foreach ($rk in @(
            "HKCU:\Software\Python\PythonCore\3.11\InstallPath",
            "HKLM:\Software\Python\PythonCore\3.11\InstallPath",
            "HKLM:\Software\WOW6432Node\Python\PythonCore\3.11\InstallPath")) {
        try {
            $ip = Get-ItemProperty -Path $rk -ErrorAction Stop
            $v = $ip."(default)"
            if ($v) {
                $v = "$v".TrimEnd('\')
                $cands += (Join-Path $v "python.exe")
            }
        } catch {}
    }
    try {
        $pyc = (Get-Command py.exe -ErrorAction Stop).Source
        $probe = Invoke-ExeProbe -FilePath $pyc -Arguments '-3.11 -c "import sys; print(sys.executable)"' -TimeoutSec 15
        if (-not $probe.TimedOut -and $probe.Code -eq 0) {
            $p = ("$($probe.Output)" -split "`r?`n" | Where-Object { "$_".Trim() -ne "" } | Select-Object -First 1)
            if ($p) { $cands += ("$p".Trim()) }
        }
    } catch {}
    if ($env:LOCALAPPDATA) { $cands += (Join-Path $env:LOCALAPPDATA "Programs\Python\Python311\python.exe") }
    $cands += "C:\Program Files\Python311\python.exe"
    $cands += "C:\Program Files (x86)\Python311\python.exe"
    $cands += (Join-Path $script:HomeDir "python311\python.exe")
    foreach ($c in ($cands | Where-Object { $_ } | Select-Object -Unique)) {
        if (-not (Test-Path $c)) { continue }
        $probe = Invoke-ExeProbe -FilePath $c -Arguments "--version" -TimeoutSec 15
        if ($probe.TimedOut) { continue }
        if ("$($probe.Output)" -match "Python 3\.11\.") { return $c }
    }
    return $null
}

function Invoke-PipInstall {
    # pip с запасным источником (урок 12.11.2026: сетевые блокировки — штатная ситуация).
    # 1-я попытка — как задано; при провале: FallbackArguments, если заданы
    # (torch -> колёса cu118 с зеркала aliyun), иначе те же пакеты через зеркало tuna.
    # Возврат: код последней попытки.
    param(
        [Parameter(Mandatory)][string]$Step,
        [Parameter(Mandatory)][string]$Python,
        [Parameter(Mandatory)][string]$Arguments,
        [string]$FallbackArguments = "",
        [int]$TimeoutSec = 0
    )
    $r = Invoke-Logged -Step $Step -FilePath $Python -Arguments $Arguments -TimeoutSec $TimeoutSec
    if ($r -eq 0) { return 0 }
    if ($FallbackArguments -ne "") {
        Write-Step "pip не дотянулся (код $r) — повтор через запасной источник"
        Write-StepLog -Step $Step -Message "pip: повтор с запасными аргументами: $FallbackArguments"
        return (Invoke-Logged -Step $Step -FilePath $Python -Arguments $FallbackArguments -TimeoutSec $TimeoutSec)
    }
    Write-Step "pip не дотянулся до pypi.org (код $r) — повтор через зеркало tuna"
    Write-StepLog -Step $Step -Message "pip: повтор с зеркалом pypi.tuna.tsinghua.edu.cn"
    return (Invoke-Logged -Step $Step -FilePath $Python -Arguments "$Arguments -i https://pypi.tuna.tsinghua.edu.cn/simple" -TimeoutSec $TimeoutSec)
}

function Show-ManualHint {
    # Урок 12.11.2026 (провал 01_python): провал скачивания обязан давать ручной путь, а не тупик.
    param([Parameter(Mandatory)][string]$Name, [Parameter(Mandatory)][string[]]$Urls,
          [Parameter(Mandatory)][string]$OutFile)
    Write-Host ""
    Write-Host "РУЧНОЙ ПУТЬ (сеть не пустила — это штатная ситуация):" -ForegroundColor Yellow
    Write-Host "  1) скачайте файл любым браузером (источники по порядку):" -ForegroundColor Yellow
    foreach ($u in $Urls) { Write-Host "       $u" -ForegroundColor Yellow }
    Write-Host "  2) положите его сюда, имя должно совпасть:" -ForegroundColor Yellow
    Write-Host "       $OutFile" -ForegroundColor Yellow
    Write-Host "  3) перезапустите шаг — скачивание пропустится, файл проверится по SHA-256/размеру" -ForegroundColor Yellow
    Write-Host ""
}

function Get-RemoteFile {
    # Единый загрузчик комплекта (появился после провала 01_python 12.11.2026).
    # 1) файл уже скачан (в т.ч. вручную в downloads\) и проходит проверку -> используем;
    # 2) цепочка источников: curl -L -C - (докачка при обрыве), --retry,
    #    --ssl-no-revoke (schannel на Windows падает на проверке отзыва сертификата за прокси);
    # 3) после получения: SHA-256 (жёстко) или размер ±10% (GGUF-ревизии);
    # 4) ни один источник не дотянулся -> подсказка ручного скачивания и провал шага (6.7).
    param(
        [Parameter(Mandatory)][string]$Step,
        [Parameter(Mandatory)][string]$OutFile,
        [Parameter(Mandatory)][string[]]$Urls,
        [string]$Sha256 = "",
        [double]$ExpectedGB = 0,
        [switch]$SoftFail
    )
    $name = Split-Path -Leaf $OutFile

    # --- 1) уже скачан? ---
    if (Test-Path $OutFile) {
        $sizeBytes = (Get-Item $OutFile).Length
        if ($Sha256 -ne "") {
            if (Test-FileSha256 -Path $OutFile -Sha256 $Sha256) {
                Write-Step "$name уже на месте — SHA-256 совпал, скачивание не нужно"
                Write-StepLog -Step $Step -Message "$name уже на месте, SHA-256 OK"
                return $true
            }
            Rename-Bad -Step $Step -Path $OutFile
        }
        elseif ($ExpectedGB -gt 0) {
            $sizeGB = [math]::Round($sizeBytes / 1GB, 2)
            if ($sizeGB -ge ($ExpectedGB * 0.90) -and $sizeGB -le ($ExpectedGB * 1.10)) {
                Write-Step "$name уже на месте ($sizeGB ГБ в допуске) — докачка не нужна"
                Write-StepLog -Step $Step -Message "$name уже на месте, $sizeGB ГБ OK"
                return $true
            }
            if ($sizeGB -gt ($ExpectedGB * 1.10)) {
                Rename-Bad -Step $Step -Path $OutFile
            }
            else {
                # меньше нижней границы = недокачанный: оставляем, curl -C - продолжит с места обрыва
                Write-Step "найден недокачанный файл ($sizeGB ГБ) — продолжаем с места обрыва"
            }
        }
        elseif ($sizeBytes -gt 1MB) {
            Write-Step "$name уже на месте ($([math]::Round($sizeBytes / 1MB)) МБ) — скачивание пропущено"
            Write-StepLog -Step $Step -Message "$name уже на месте, $([math]::Round($sizeBytes / 1MB)) МБ"
            return $true
        }
        else { Rename-Bad -Step $Step -Path $OutFile }
    }

    # --- 2) цепочка источников ---
    $i = 0
    foreach ($u in $Urls) {
        $i++
        Write-Step "источник $i/$($Urls.Count): $u"
        Write-StepLog -Step $Step -Message "источник ${i}: $u"
        & curl.exe -L -C - --retry 2 --retry-delay 2 --ssl-no-revoke -# -o "$OutFile" "$u"
        $r = $LASTEXITCODE
        # 33 = файл уже скачан полностью (сервер ответил 416 на запрос диапазона)
        if ($r -eq 0 -or $r -eq 33) {
            Write-StepLog -Step $Step -Message "curl код $r — передача завершена"
            break
        }
        Write-Step "источник не дотянулся (curl код $r) — следующий"
        Write-StepLog -Step $Step -Message "curl код $r — источник пропущен"
    }

    if (-not (Test-Path $OutFile)) {
        Show-ManualHint -Name $name -Urls $Urls -OutFile $OutFile
        if ($SoftFail) { return $false }
        Fail -Step $Step -Why "$name не скачался ни с одного источника"
    }

    # --- 3) проверка полученного ---
    if ($Sha256 -ne "") {
        Write-Step "SHA-256 $name (файл большой — это не зависание)..."
        if (-not (Test-FileSha256 -Path $OutFile -Sha256 $Sha256)) {
            $real = (Get-FileHash -Path $OutFile -Algorithm SHA256).Hash
            Fail -Step $Step -Why "SHA-256 $name не совпал: ожидали $Sha256, получили $real — файл битый или подменён, удалите и повторите шаг"
        }
        Write-StepLog -Step $Step -Message "SHA-256 OK: $Sha256"
        Write-Step "SHA-256 совпал"
    }
    elseif ($ExpectedGB -gt 0) {
        $sizeGB = [math]::Round((Get-Item $OutFile).Length / 1GB, 2)
        $low = $ExpectedGB * 0.90; $high = $ExpectedGB * 1.10
        if ($sizeGB -lt $low -or $sizeGB -gt $high) {
            Fail -Step $Step -Why "размер $sizeGB ГБ вне допуска $low-$high ГБ (ждали ~$ExpectedGB) — файл не докачан: повторите шаг, докачка продолжится; при повторной ошибке удалите файл"
        }
        Write-StepLog -Step $Step -Message "размер OK: $sizeGB ГБ (допуск $low-$high)"
    }
    return $true
}


