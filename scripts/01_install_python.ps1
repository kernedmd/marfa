# ============================================================
# 01_install_python.ps1 — Шаг 1: Python 3.11 (python.org, тихая установка)
# Цель: C:\Marfa\python311. Ничего в Program Files и системные пути (ТЗ Раздел 9).
# Проверка: python --version = 3.11.x, pip жив, venv создаётся.
# Урок 12.11.2026 (1): сеть не пустила python.org — источники python.org -> huaweicloud
#   -> npmmirror; ручной файл из downloads\ подхватывается (Get-RemoteFile).
# Урок 12.11.2026 (2): инсталлятор вернул 0, а python.exe не появился. Причина: Python
#   3.11.9 УЖЕ установлен на машине — тихий режим тогда выходит 0 за 2-3 секунды,
#   НИЧЕГО не ставя (TargetDir игнорируется), а интерактивный режим показывает окно
#   обслуживания «Modify/Repair/Remove» (код 1602 = окно закрыли). Решение: скрипт сам
#   находит работающий Python 3.11.x (реестр + py-лаунчер + типовые папки) и подключает его — путь
#   пишется в data\python_path.txt, его подхватывают все остальные шаги через _common.
#   Диагностика пишется и в журнал шага, а не только на экран.
# ============================================================
. "$PSScriptRoot\_common.ps1"
$step = "01_python"

trap {
    $m = $_.Exception.Message
    $ln = ""
    try { if ($_.InvocationInfo) { $ln = " (строка $($_.InvocationInfo.ScriptLineNumber))" } } catch {}
    Write-StepLog -Step "01_python" -Message "КРИТ: непредвиденная ошибка: $m$ln"
    Write-Host "!!! [01_python] КРИТ: $m$ln" -ForegroundColor Red
    exit 1
}

if (Test-Marker $step) { Write-Step "шаг $step уже сделан (маркер) — пропуск"; exit 0 }
Write-StepLog -Step $step -Message "начало шага"

# --- Санитария окружения: PYTHONHOME/PYTHONPATH от чужих установок (Anaconda и пр.)
# --- отравляют -m pip и venv у адоптированного Python (урок 12.11.2026) ---
foreach ($ev in @("PYTHONHOME", "PYTHONPATH", "PYTHONEXECUTABLE")) {
    if (Test-Path "Env:$ev") {
        $evv = [Environment]::GetEnvironmentVariable($ev)
        Write-StepLog -Step $step -Message "санитария: убираю $ev='$evv' (мешает pip/venv)"
        Remove-Item "Env:$ev" -ErrorAction SilentlyContinue
    }
}

function Show-LogTail {
    # Последние строки журнала шага — на экран (6.6): причина провала видна в чате,
    # а не только в logs\install_01_python.log
    $log = Join-Path $script:LogsDir "install_$step.log"
    Write-Host "  последние строки журнала ($log):" -ForegroundColor Yellow
    $tail = Get-Content $log -Tail 10 -ErrorAction SilentlyContinue
    foreach ($line in $tail) { Write-Host "    $line" -ForegroundColor DarkYellow }
}

function Show-PyDiagnostics {
    # Почему python.exe не появился: папка цели, типовое место, журнал инсталлятора.
    # Всё дублируется в журнал шага (6.6) — консоль могла быть уже закрыта.
    param([Parameter(Mandatory)][string]$Target, [Parameter(Mandatory)][string]$PyLog)
    Write-StepLog -Step $step -Message "диагностика: ---"
    if (Test-Path $Target) {
        $items = @(Get-ChildItem $Target -ErrorAction SilentlyContinue | Select-Object -First 10)
        if ($items.Count -gt 0) {
            $names = ($items | ForEach-Object { $_.Name }) -join ", "
            Write-Host "  в $Target лежит: $names" -ForegroundColor Yellow
            Write-StepLog -Step $step -Message "диагностика: в $Target лежит: $names"
        } else {
            Write-Host "  папка $Target пуста — инсталлятор туда ничего не писал" -ForegroundColor Yellow
            Write-StepLog -Step $step -Message "диагностика: папка $Target пуста"
        }
    } else {
        Write-Host "  папки $Target нет вообще" -ForegroundColor Yellow
        Write-StepLog -Step $step -Message "диагностика: папки $Target нет"
    }
    $def = Join-Path $env:LOCALAPPDATA "Programs\Python\Python311\python.exe"
    if (Test-Path $def) {
        Write-Host "  python найден в типовом месте: $def" -ForegroundColor Yellow
        Write-Host "  TargetDir не применился — шаг подключит эту копию сам (адоптация)" -ForegroundColor Yellow
        Write-StepLog -Step $step -Message "диагностика: python найден в типовом месте: $def"
    }
    if (Test-Path $PyLog) {
        Write-Host "  последние строки журнала инсталлятора ($PyLog):" -ForegroundColor Yellow
        $tail = Get-Content $PyLog -Tail 12 -ErrorAction SilentlyContinue
        foreach ($line in $tail) {
            Write-Host "    $line" -ForegroundColor DarkYellow
            Write-StepLog -Step $step -Message "инсталлятор: $line"
        }
    } else {
        Write-Host "  журнал $PyLog не создан — установщик даже не запустился" -ForegroundColor Yellow
        Write-StepLog -Step $step -Message "диагностика: журнал инсталлятора не создан"
    }
}

$target = Join-Path $script:HomeDir "python311"

if (Test-Path $script:PythonExe) {
    # Урок 12.11.2026 (коммит 26): зонд через Invoke-ExeProbe — не через 2>&1 (EAP=Stop).
    $vProbe = Invoke-ExeProbe -FilePath $script:PythonExe -Arguments "--version" -TimeoutSec 20
    $v = "$($vProbe.Output)".Trim()
    Write-Step "python311 уже на месте: $v"
} else {
    $pyver = "3.11.9"   # последний релиз 3.11 с полным инсталлятором
    $installer = Join-Path $script:DownloadsDir "python-$pyver-amd64.exe"
    # SHA-256 официального python-3.11.9-amd64.exe (26 216 840 байт, python.org/ftp)
    $pySha = "5ee42c4eee1e6b4464bb23722f90b45303f79442df63083f05322f1785f5fdde"
    Get-RemoteFile -Step $step -OutFile $installer -Sha256 $pySha -Urls @(
        "https://www.python.org/ftp/python/$pyver/python-$pyver-amd64.exe",
        "https://mirrors.huaweicloud.com/python/$pyver/python-$pyver-amd64.exe",
        "https://registry.npmmirror.com/-/binary/python/$pyver/python-$pyver-amd64.exe"
    ) | Out-Null

    # --- Адоптация ДО установки: если 3.11.9 уже стоит на машине, тихий режим ---
    # --- бесполезен (выходит 0 за секунды, ничего не ставя) — ищем и подключаем. ---
    $adopt = Find-WorkingPython311
    if ($adopt) {
        Write-StepLog -Step $step -Message "адоптация: найден работающий Python 3.11.x: $adopt — установка не нужна"
        Write-Step "найден уже установленный Python 3.11.x: $adopt"
        Write-Host "  почему: при уже стоящей 3.11.9 тихий инсталлятор выходит 0 за секунды и ничего не ставит" -ForegroundColor Yellow
        Write-Host "  подключаем эту копию; venv и все пакеты останутся внутри C:\Marfa (2.3)" -ForegroundColor Yellow
        Set-Content -Path (Join-Path $script:DataDir "python_path.txt") -Value $adopt -Encoding UTF8
        Write-StepLog -Step $step -Message "путь сохранён: data\python_path.txt"
        $script:PythonExe = $adopt
    } else {
        $pyLog  = Join-Path $script:LogsDir  "python_install.log"
        Unblock-File -Path $installer -ErrorAction SilentlyContinue
        # Кавычки собираем сами; $args НЕ используем — автоматическая переменная PS (урок 12.11.2026).
        $q = [char]34
        $instArgs = "/quiet InstallAllUsers=0 PrependPath=0 Include_test=0 AssociateFiles=0 Shortcuts=0 " +
                    "TargetDir=$q$target$q /log $q$pyLog$q"
        Write-Step "тихая установка в $target (журнал: logs\python_install.log)"
        Write-StepLog -Step $step -Message "аргументы: $instArgs"
        # Урок 12.11.2026 (коммит 24): Start-MarfaProcess вместо Start-Process —
        # у -Wait -PassThru на PS 5.1 ExitCode может быть $null («инсталлятор вернул 0»
        # при реальном отказе). CreateNoWindow влияет только на консольные окна:
        # GUI инсталлятора показывается как раньше.
        $rInst = Start-MarfaProcess -FilePath $installer -Arguments $instArgs -TimeoutSec 1800
        $code = $rInst.Code
        if ($code -isnot [int]) { $code = -1 }
        Write-StepLog -Step $step -Message "инсталлятор вернул $code"
        if ($code -eq 1602) { Write-StepLog -Step $step -Message "1602 = установка отменена пользователем (окно закрыто)" }
        # 3010 = успех, требуется перезагрузка — не провал

        if (-not (Test-Path (Join-Path $target "python.exe"))) {
            Write-StepLog -Step $step -Message "python.exe нет в python311\ (код $code) — ищем уже установленный Python 3.11"
            Show-PyDiagnostics -Target $target -PyLog $pyLog
            $adopt = Find-WorkingPython311
            if ($adopt) {
                Write-StepLog -Step $step -Message "адоптация: найден работающий Python 3.11.x: $adopt"
                Write-Step "подключаем уже установленный Python 3.11.x: $adopt"
                Set-Content -Path (Join-Path $script:DataDir "python_path.txt") -Value $adopt -Encoding UTF8
                Write-StepLog -Step $step -Message "путь сохранён: data\python_path.txt"
                $script:PythonExe = $adopt
            } else {
                Write-Step "тихая установка не сработала, других Python 3.11 нет — открываю инсталлятор вручную"
                Write-Host "  В окне инсталлятора: 'Customize installation' -> Optional Features Next ->" -ForegroundColor Yellow
                Write-Host "  Advanced Options: путь установки должен быть $target -> Install" -ForegroundColor Yellow
                Write-StepLog -Step $step -Message "повтор: интерактивная установка"
                $rInst2 = Start-MarfaProcess -FilePath $installer -Arguments "/install TargetDir=$q$target$q /log $q$pyLog$q" -TimeoutSec 3600
                $code2 = $rInst2.Code
                if ($code2 -isnot [int]) { $code2 = -1 }
                Write-StepLog -Step $step -Message "интерактивная установка вернула $code2"
                if (-not (Test-Path (Join-Path $target "python.exe"))) {
                    Show-PyDiagnostics -Target $target -PyLog $pyLog
                    Fail -Step $step -Why "python.exe не появился в python311\ даже после интерактивной установки — журнал: logs\python_install.log"
                }
            }
        } else {
            Write-StepLog -Step $step -Message "python.exe на месте в $target"
        }
    }
}

# --- Проверка 1: версия ---
if (-not (Test-Path $script:PythonExe)) { Fail -Step $step -Why "python.exe не появился в python311\" }
# Урок 12.11.2026 (коммит 26): зонд через Invoke-ExeProbe — не через 2>&1 (EAP=Stop).
$verProbe = Invoke-ExeProbe -FilePath $script:PythonExe -Arguments "--version" -TimeoutSec 20
$ver = "$($verProbe.Output)".Trim()
if ($ver -notmatch "3\.11\.\d+") { Fail -Step $step -Why "ожидали Python 3.11.x, получили: $ver" }
Write-StepLog -Step $step -Message "версия: $ver"

# --- Проверка 2: pip жив; нет — чиним без сети через ensurepip (урок 12.11.2026) ---
$r = Invoke-Logged -Step $step -FilePath $script:PythonExe -Arguments "-m pip --version" -TimeoutSec 120
if ($r -ne 0) {
    Write-Step "pip не отвечает — пробую починить ensurepip (встроен в Python, сеть не нужна)"
    Write-StepLog -Step $step -Message "pip не отвечает (код $r) — ensurepip --upgrade --default-pip"
    $rEns = Invoke-Logged -Step $step -FilePath $script:PythonExe -Arguments "-m ensurepip --upgrade --default-pip" -TimeoutSec 300
    $r = Invoke-Logged -Step $step -FilePath $script:PythonExe -Arguments "-m pip --version" -TimeoutSec 120
    if ($r -eq 0) {
        Write-Step "pip восстановлен (ensurepip)"
        Write-StepLog -Step $step -Message "pip восстановлен через ensurepip (код ensurepip: $rEns)"
    } else {
        Show-LogTail
        Fail -Step $step -Why "pip не работает даже после ensurepip — переустановите Python двойным кликом (python-3.11.9-amd64.exe уже в downloads\, кнопка 'Install Now'), затем снова 00_install_all.bat; причина — в журнале выше и в logs\install_01_python.log"
    }
}

# --- Проверка 3: venv создаётся ---
$checkVenv = Join-Path $env:TEMP "marfa_venv_check"
if (Test-Path $checkVenv) { Remove-Item $checkVenv -Recurse -Force }
$r = Invoke-Logged -Step $step -FilePath $script:PythonExe -Arguments "-m venv `"$checkVenv`"" -TimeoutSec 300
if ($r -ne 0 -or -not (Test-Path (Join-Path $checkVenv "Scripts\python.exe"))) {
    Show-LogTail
    Fail -Step $step -Why "venv не создаётся — причина в журнале выше; чаще всего помогает переустановка Python ('Install Now')"
}
Remove-Item $checkVenv -Recurse -Force -ErrorAction SilentlyContinue

$note = "Python $ver"
if (Test-Path (Join-Path $script:DataDir "python_path.txt")) {
    $note += " (адоптирован: путь в data\python_path.txt)"
} else {
    $note += " в python311\"
}
Set-Marker -Step $step -Note $note
exit 0


