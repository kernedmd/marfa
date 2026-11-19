# ============================================================
# 02_install_llamacpp.ps1 — Шаг 2: llama.cpp x64 (официальный prebuilt GitHub Releases)
# Xeon E5-1680 v3 поддерживает AVX2 (ТЗ Раздел 9). Распаковка в C:\Marfa\llama.cpp.
# Проверка: llama-server.exe --version отвечает (с таймаутом — шаг не может зависнуть).
# Урок 12.11.2026 (1): zip или уже распакованная папка из downloads\ подхватываются
#   без скачивания.
# Урок 12.11.2026 (2): три запуска подряд «молчали» в журнале: скрипт вис на запуске
#   llama-server --version — Windows показывала диалог (vcruntime140.dll не найден /
#   SmartScreen), процесс не отвечал, а stderr в журнал не попадал. Теперь:
#   vc_redist проверяется ДО любого запуска llama-server, exe разблокируется
#   (Unblock-File), проверка версии с таймаутом 30 с, каждый этап — в журнал,
#   любая ошибка — в журнал (trap).
# ============================================================
. "$PSScriptRoot\_common.ps1"
$step = "02_llamacpp"

trap {
    $m = $_.Exception.Message
    $ln = ""
    try { if ($_.InvocationInfo) { $ln = " (строка $($_.InvocationInfo.ScriptLineNumber))" } } catch {}
    Write-StepLog -Step "02_llamacpp" -Message "КРИТ: непредвиденная ошибка: $m$ln"
    Write-Host "!!! [02_llamacpp] КРИТ: $m$ln" -ForegroundColor Red
    exit 1
}

if (Test-Marker $step) { Write-Step "шаг $step уже сделан (маркер) — пропуск"; exit 0 }
Write-StepLog -Step $step -Message "начало шага"

$tag = "неизвестный"
$llamaDir = Join-Path $script:HomeDir "llama.cpp"

# --- MSVC Redistributable: проверяем ВСЕГДА и ДО любого запуска llama-server ---
# (диалог «vcruntime140.dll не найден» вешал шаг навсегда — урок 12.11.2026)
$vcKey = "HKLM:\SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64"
if (Test-Path $vcKey) {
    Write-StepLog -Step $step -Message "MSVC Redistributable x64: уже установлен"
} else {
    Write-Step "MSVC Redistributable x64 не найден — установка"
    Write-StepLog -Step $step -Message "MSVC Redistributable x64 не найден — установка (без него llama-server виснет на диалоге vcruntime140.dll)"
    $vcExe = Join-Path $script:DownloadsDir "vc_redist.x64.exe"
    $got = Get-RemoteFile -Step $step -OutFile $vcExe -SoftFail -Urls @(
        "https://aka.ms/vs/17/release/vc_redist.x64.exe"
    )
    if ($got) {
        # Урок 12.11.2026 (коммит 24): Start-MarfaProcess — ExitCode Start-Process на
        # PS 5.1 ненадёжен; 3010 = успех, требуется перезагрузка (не провал)
        $vr = Start-MarfaProcess -FilePath $vcExe -Arguments "/install /quiet /norestart" -TimeoutSec 1800
        $vcCode = $vr.Code
        if ($vcCode -isnot [int]) { $vcCode = -1 }
        Write-StepLog -Step $step -Message "vc_redist вернул $vcCode"
        Write-Step "vc_redist вернул $vcCode (3010 = успех, нужна перезагрузка)"
    } else {
        Write-StepLog -Step $step -Message "vc_redist не скачался (сеть) — продолжаем; если llama-server затем зависнет, закройте диалог и поставьте vc_redist.x64.exe вручную"
    }
}

if (Test-Path $script:LlamaServerExe) {
    Write-Step "llama-server.exe уже на месте"
    Write-StepLog -Step $step -Message "llama-server.exe уже на месте"
} else {
    # --- Снимаем запущенный llama-server: он блокирует распаковку ---
    $busy = @(Get-Process -Name "llama-server" -ErrorAction SilentlyContinue)
    if ($busy.Count -gt 0) {
        Write-StepLog -Step $step -Message "остановка работающего llama-server ($($busy.Count) шт.) — блокировал распаковку"
        $busy | Stop-Process -Force -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 1
    }

    # --- Уже распакованная вручную папка в downloads\ (zip удалён, exe остался)? ---
    $unpacked = @(Get-ChildItem $script:DownloadsDir -Directory -Filter "llama-*" -ErrorAction SilentlyContinue |
                  Where-Object { Test-Path (Join-Path $_.FullName "llama-server.exe") } |
                  Sort-Object Name -Descending)
    if ($unpacked.Count -gt 0) {
        New-Item -ItemType Directory -Path $llamaDir -Force | Out-Null
        Write-Step "найдена распакованная папка $($unpacked[0].Name) — копируем в llama.cpp\"
        Write-StepLog -Step $step -Message "копируем из $($unpacked[0].FullName)"
        Copy-Item (Join-Path $unpacked[0].FullName "*") $llamaDir -Force
        if ($unpacked[0].Name -match "^(llama-[a-z0-9.]+)") { $tag = $Matches[1] }
        Get-ChildItem $llamaDir -Filter *.exe -ErrorAction SilentlyContinue | Unblock-File -ErrorAction SilentlyContinue
    }
}

if (-not (Test-Path $script:LlamaServerExe)) {
    # --- Локальный zip из downloads\ (ручное скачивание — штатный путь)? ---
    $zip = $null
    $cached = @(Get-ChildItem $script:DownloadsDir -Filter "llama-*.zip" -ErrorAction SilentlyContinue |
                Where-Object { $_.Name -match "bin-win-(avx2|cpu)-x64\.zip$" -and $_.Length -gt 1MB } |
                Sort-Object Name -Descending)
    $avx = $cached | Where-Object { $_.Name -match "avx2" } | Select-Object -First 1
    if ($avx) { $zip = $avx.FullName }
    elseif ($cached.Count -gt 0) { $zip = $cached[0].FullName }

    if ($zip) {
        $zipName = Split-Path -Leaf $zip
        if ($zipName -match "^(llama-[a-z0-9.]+?)-bin-win") { $tag = $Matches[1] } else { $tag = "локальный zip" }
        Write-Step "в downloads\ уже лежит $zipName — скачивание пропущено"
        Write-StepLog -Step $step -Message "используем локальный zip: $zipName"
    } else {
        # --- Поиск последнего официального релиза llama.cpp ---
        Write-Step "запрос последнего релиза llama.cpp"
        try {
            $rel = Invoke-RestMethod -Uri "https://api.github.com/repos/ggml-org/llama.cpp/releases/latest" `
                                     -Headers @{ "User-Agent" = "marfa-installer" }
        } catch {
            Write-Host ""
            Write-Host "РУЧНОЙ ПУТЬ: откройте https://github.com/ggml-org/llama.cpp/releases/latest" -ForegroundColor Yellow
            Write-Host "  скачайте оттуда llama-<версия>-bin-win-cpu-x64.zip (или -avx2-) в $script:DownloadsDir" -ForegroundColor Yellow
            Write-Host "  и перезапустите шаг — zip подхватится без GitHub API" -ForegroundColor Yellow
            Fail -Step $step -Why "GitHub API недоступен: $_"
        }
        $tag = $rel.tag_name
        Write-Step "релиз: $tag"
        Write-StepLog -Step $step -Message "релиз llama.cpp: $tag"

        # ТЗ требует AVX2 (Xeon E5-1680 v3 умеет). Имя ассета в новых релизах: bin-win-cpu-x64,
        # в старых — bin-win-avx2-x64. Берём avx2, если есть; иначе cpu-x64 (текущий CPU-билд).
        $assets = @($rel.assets | ForEach-Object { $_.name })
        $asset = $assets | Where-Object { $_ -match "bin-win-avx2-x64\.zip$" } | Select-Object -First 1
        if (-not $asset) { $asset = $assets | Where-Object { $_ -match "bin-win-cpu-x64\.zip$" } | Select-Object -First 1 }
        if (-not $asset) { Fail -Step $step -Why "в релизе $tag нет win-avx2/win-cpu x64 zip" }

        $zip = Join-Path $script:DownloadsDir $asset
        $url = "https://github.com/ggml-org/llama.cpp/releases/download/$tag/$asset"
        Write-Step "скачивание $asset (~23 МБ)"
        Get-RemoteFile -Step $step -OutFile $zip -Urls @($url) | Out-Null
    }

    # --- Распаковка в дом ---
    New-Item -ItemType Directory -Path $llamaDir -Force | Out-Null
    Unblock-File -Path $zip -ErrorAction SilentlyContinue
    Write-Step "распаковка в llama.cpp\"
    Write-StepLog -Step $step -Message "распаковка начата: $(Split-Path -Leaf $zip) -> llama.cpp\"
    $extracted = $false
    # tar.exe (bsdtar, встроен в Windows 10 1803+) — заметно быстрее Expand-Archive
    try {
        & tar.exe -xf "$zip" -C "$llamaDir"
        if ($LASTEXITCODE -eq 0) { $extracted = $true }
    } catch {}
    if (-not $extracted) {
        try {
            Expand-Archive -Path $zip -DestinationPath $llamaDir -Force
            $extracted = $true
        } catch {
            Fail -Step $step -Why "zip не распаковывается ($($_.Exception.Message)) — файл битый, удалите его из downloads\ и скачайте заново"
        }
    }
    Write-StepLog -Step $step -Message "распаковка завершена"
    Get-ChildItem $llamaDir -Filter *.exe -ErrorAction SilentlyContinue | Unblock-File -ErrorAction SilentlyContinue

    # В некоторых сборках внутри архива вложенная папка — поднимаем на уровень
    $nested = @(Get-ChildItem $llamaDir -Directory -ErrorAction SilentlyContinue |
                Where-Object { Test-Path (Join-Path $_.FullName "llama-server.exe") })
    if (-not (Test-Path $script:LlamaServerExe) -and $nested.Count -gt 0) {
        Write-StepLog -Step $step -Message "вложенная папка $($nested[0].Name) — поднимаем файлы на уровень llama.cpp\"
        Copy-Item (Join-Path $nested[0].FullName "*") $llamaDir -Force
        Get-ChildItem $llamaDir -Filter *.exe -ErrorAction SilentlyContinue | Unblock-File -ErrorAction SilentlyContinue
    }
}

# --- Проверка: llama-server отвечает (с таймаутом 30 с — шаг не зависнет) ---
if (-not (Test-Path $script:LlamaServerExe)) { Fail -Step $step -Why "llama-server.exe не появился" }
Write-StepLog -Step $step -Message "проверка: llama-server --version (таймаут 30 с)"
$probe = Invoke-ExeProbe -FilePath $script:LlamaServerExe -Arguments "--version" -TimeoutSec 30
if ($probe.TimedOut) {
    Fail -Step $step -Why "llama-server --version не ответил за 30 с (шаг прерван, чтобы не висеть). Чаще всего: на экране висит диалог «vcruntime140.dll не найден» или SmartScreen — закройте его и перезапустите шаг (vc_redist ставится автоматически)"
}
$v = ($probe.Output -split "`r?`n" | Where-Object { "$_".Trim() -ne "" } | Select-Object -First 1)
if (-not $v) { Fail -Step $step -Why "llama-server --version не дал вывода (код $($probe.Code)) — проверьте MSVC Redistributable и антивирус" }
Write-StepLog -Step $step -Message "llama-server: $($v.Trim())"

Set-Marker -Step $step -Note "llama.cpp $tag в llama.cpp\"
exit 0


