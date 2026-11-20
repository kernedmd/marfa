# ============================================================
# run_tests.ps1 Ч pytest всего дома (офлайн: мок-мозг, JSON-пам€ть).
# ѕравило 6.1: не внедр€ть фишку без теста. ѕеред каждым коммитом Ч прогон.
# ============================================================
. "$PSScriptRoot\_common.ps1"

if (-not (Test-Path $script:VenvPython)) {
    # “есты могут идти и на python311, если pytest установлен системно в дом
    if (Test-Path $script:PythonExe) {
        $env:MARFA_HOME = Join-Path $env:TEMP "marfa_dev"
        Push-Location $script:HomeDir
        & $script:PythonExe -m pytest tests/ -v
        Pop-Location
        exit $LASTEXITCODE
    }
    Write-Host "нет venv/python311 Ч сначала 00_install_all.bat" -ForegroundColor Red
    exit 1
}

$env:MARFA_HOME = Join-Path $env:TEMP "marfa_dev"
Push-Location $script:HomeDir
& $script:VenvPython -m pytest tests/ -v
Pop-Location
exit $LASTEXITCODE


