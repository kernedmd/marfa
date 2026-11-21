# ============================================================
# run_tests.ps1 — прогон тестов дома, v2 (краткий итог на экран,
# полный протокол — в logs\tests_last.txt).
# Урок 21.11: окно закрывалось сразу после прогона — Создатель не
# успевал прочитать ошибки. Теперь итог остаётся на экране (пауза
# в bat-обёртке), а протокол цел, даже если окно всё же закрылось.
# ============================================================
. "$PSScriptRoot\_common.ps1"

# Питон пишет в трубу по-русски, а не кракозябрами локальной кодировки.
$env:PYTHONIOENCODING = "utf-8"

# Тесты живут во временном доме — настоящий дом не трогаем.
$env:MARFA_HOME = Join-Path $env:TEMP "marfa_dev"

$logFile = Join-Path $script:LogsDir "tests_last.txt"

$py = $script:VenvPython
if (-not (Test-Path $py)) { $py = $script:PythonExe }
if (-not (Test-Path $py)) {
    Write-Host "Нет venv и нет python311 — запусти 00_install_all.bat" -ForegroundColor Red
    exit 1
}

Set-Content -Path $logFile -Encoding UTF8 -Value @(
    "МАРФА — прогон тестов " + (Get-Date -Format "yyyy-MM-dd HH:mm"),
    "Дом: " + $script:HomeDir,
    "Python: " + $py,
    "============================================================"
)

Write-Host ("Протокол прогона: " + $logFile)
Write-Host ""

Push-Location $script:HomeDir
# Через cmd: stderr (например, «No module named pytest») вливается в
# общий поток и попадает в протокол, а не роняет ps1 (EAP=Stop в _common).
$cmd = $py + " -m pytest tests/ -v 2>&1"
cmd /c $cmd | ForEach-Object { Write-Host $_; $_ } | Out-File -FilePath $logFile -Append -Encoding UTF8
$code = $LASTEXITCODE
Pop-Location

Write-Host ""
Write-Host "=== последние строки протокола (полный — в файле выше) ==="
Get-Content -Path $logFile -Tail 12 | ForEach-Object { Write-Host $_ }
exit $code
