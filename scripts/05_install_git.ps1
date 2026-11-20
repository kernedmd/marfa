# ============================================================
# 05_install_git.ps1 — необязательный шаг: Git для пуша в GitHub (правило 0.2)
# Дом работает и без git. Ставим портативный MinGit в C:\Marfa\tools\git —
# ничего в Program Files и системных путях (ТЗ 2.3). В конвейер 00 НЕ входит.
# Запуск отдельно: scripts\05_install_git.bat
# Урок 12.11.2026: «'git' не является внутренней или внешней командой» на чистой машине.
# ============================================================
. "$PSScriptRoot\_common.ps1"
$step = "05_git"
trap {
    $m = $_.Exception.Message
    $ln = ""
    try { if ($_.InvocationInfo) { $ln = " (строка $($_.InvocationInfo.ScriptLineNumber))" } } catch {}
    Write-StepLog -Step "05_git" -Message "КРИТ: непредвиденная ошибка: $m$ln"
    Write-Host "!!! [05_git] КРИТ: $m$ln" -ForegroundColor Red
    exit 1
}


if (Test-Marker $step) { Write-Step "шаг $step уже сделан (маркер) — пропуск"; exit 0 }
Write-StepLog -Step $step -Message "начало шага"

$gitExe = Join-Path $script:HomeDir "tools\git\cmd\git.exe"

if (Test-Path $gitExe) {
    Write-Step "git уже на месте: $gitExe"
} else {
    # --- Уже скачанный вручную MinGit в downloads\? ---
    $zip = $null
    $cached = @(Get-ChildItem $script:DownloadsDir -Filter "MinGit-*.zip" -ErrorAction SilentlyContinue |
                Where-Object { $_.Length -gt 1MB } | Sort-Object Name -Descending)
    if ($cached.Count -gt 0) {
        $zip = $cached[0].FullName
        Write-Step "в downloads\ уже лежит $($cached[0].Name) — скачивание пропущено"
        Write-StepLog -Step $step -Message "используем локальный zip: $($cached[0].Name)"
    } else {
        # --- Последний релиз из редиректа releases/latest (без GitHub API и его лимитов) ---
        $tag = $null
        try {
            $resp = Invoke-WebRequest -Uri "https://github.com/git-for-windows/git/releases/latest" `
                                      -UseBasicParsing -MaximumRedirection 5 -ErrorAction Stop
            if ($resp.BaseResponse.ResponseUri.AbsoluteUri -match "/tag/(v[0-9][0-9a-zA-Z.]*[0-9a-zA-Z])") {
                $tag = $Matches[1]
            }
        } catch {
            Write-Step "последний релиз не определился ($($_.Exception.Message)) — беру запасной"
        }
        if (-not $tag) { $tag = "v2.56.1.windows.1" }
        Write-Step "релиз git: $tag"
        Write-StepLog -Step $step -Message "релиз git: $tag"

        # Имя ассета менялось между релизами: MinGit-2.56.1-64-bit.zip (новое) или
        # MinGit-2.56.1.windows.1-64-bit.zip (старое). Перебираем; SoftFail — не роняет шаг.
        $base = (($tag -replace "^v", "") -replace "\.windows\.\d+$", "")
        $cands = @("MinGit-$base-64-bit.zip", "MinGit-$($tag.TrimStart('v'))-64-bit.zip") | Select-Object -Unique

        foreach ($cand in $cands) {
            $try = Join-Path $script:DownloadsDir $cand
            $url = "https://github.com/git-for-windows/git/releases/download/$tag/$cand"
            Write-Step "пробуем $cand"
            if (Get-RemoteFile -Step $step -OutFile $try -SoftFail -Urls @($url)) {
                $zip = $try
                break
            }
        }
        if (-not $zip) {
            Fail -Step $step -Why "ни один MinGit-ассет не скачался — скачайте вручную (источник напечатан выше) в $script:DownloadsDir"
        }
    }

    # --- Распаковка в дом ---
    $gitDir = Join-Path $script:HomeDir "tools\git"
    New-Item -ItemType Directory -Path $gitDir -Force | Out-Null
    Write-Step "распаковка в tools\git\"
    try {
        Expand-Archive -Path $zip -DestinationPath $gitDir -Force
    } catch {
        Fail -Step $step -Why "zip не распаковывается ($($_.Exception.Message)) — файл битый, удалите из downloads\ и повторите шаг"
    }
}

# --- Проверка ---
if (-not (Test-Path $gitExe)) { Fail -Step $step -Why "git.exe не появился в tools\git\cmd\" }
# Урок 12.11.2026 (коммит 26): зонд через Invoke-ExeProbe — не через 2>&1 (EAP=Stop).
$gProbe = Invoke-ExeProbe -FilePath $gitExe -Arguments "--version" -TimeoutSec 20
$v = "$($gProbe.Output)".Trim()
if (-not $v) { Fail -Step $step -Why "git --version не отвечает" }
Write-StepLog -Step $step -Message "git: $v"
Set-Marker -Step $step -Note "$v в tools\git\"

Write-Host ""
Write-Host "Как поднять git-репозиторий в C:\Marfa и запушить (один раз):" -ForegroundColor Cyan
Write-Host "  cd /d C:\Marfa" -ForegroundColor Cyan
Write-Host "  set PATH=C:\Marfa\tools\git\cmd;%PATH%" -ForegroundColor Cyan
Write-Host "  git init -b main" -ForegroundColor Cyan
Write-Host "  git fetch marfa.bundle main:bundle-main" -ForegroundColor Cyan
Write-Host "  git reset --hard bundle-main" -ForegroundColor Cyan
Write-Host "     :: обновит скрипты до последней версии; data\models\downloads\logs не тронет — они в .gitignore" -ForegroundColor DarkCyan
Write-Host "  git remote add origin https://github.com/kernedmd/marfa.git" -ForegroundColor Cyan
Write-Host "  git push -u origin main" -ForegroundColor Cyan
Write-Host "     :: спросит Username (ваш логин GitHub) и Password (вставьте PAT, см. ИНСТРУКЦИЯ_ПУШ_В_GITHUB.md)" -ForegroundColor DarkCyan
exit 0


