# ============================================================
# start_marfa.ps1 — запуск web-панели Марфы на 5001 (ТЗ 2.3, правило 6.4: 5000 НЕ трогаем).
# Каркас v9.0: web\app.py уже перенесён Ильёй или собран в этом репозитории.
# ============================================================
. "$PSScriptRoot\_common.ps1"

if (-not (Test-Path $script:VenvPython)) {
    Write-Host "нет venv — сначала 00_install_all.bat (шаг 04)" -ForegroundColor Red
    exit 1
}
if (-not (Test-PortFree -Port 5001)) {
    Write-Host "порт 5001 занят — панель уже запущена" -ForegroundColor Yellow
    exit 1
}

Write-Host "Панель Марфы: http://127.0.0.1:5001 (порт 5000 не трогаем — правило 6.4)"
Push-Location $script:HomeDir
& $script:VenvPython -m web.app
Pop-Location
exit $LASTEXITCODE


