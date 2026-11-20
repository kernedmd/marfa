# ============================================================
# 00_install_all.ps1 — КОНВЕЙЕР УСТАНОВКИ ДОМА (ТЗ Раздел 9).
# Цель: чистая Windows 10/11 x64 на Z440 -> рабочий дом за один прогон.
# Каждый шаг ставит своё, проверяет себя, пишет маркер data\install_state\<шаг>.done.
# Провал шага останавливает конвейер; повторный запуск пропускает сделанное.
# ============================================================
. "$PSScriptRoot\_common.ps1"

$steps = @(
    @{ Script = "01_install_python.ps1";      Title = "Шаг 1: Python 3.11 (если уже стоит на машине — подключится сам)" },
    @{ Script = "02_install_llamacpp.ps1";    Title = "Шаг 2: llama.cpp AVX2 в llama.cpp\" },
    @{ Script = "03a_download_model_q4km.ps1"; Title = "Шаг 3a: мозг Q4_K_M 18.63 ГБ" },
    @{ Script = "04_install_qlora.ps1";       Title = "Шаг 4: venv + QLoRA-стек + студент" },
    @{ Script = "verify.ps1";                 Title = "Шаг 5: сводный аудит дома" },
    @{ Script = "smoke_test.ps1";             Title = "Шаг 6: смоук-тест мозга 8082" }
)

Write-Host "=============================================="
Write-Host "УСТАНОВКА ДОМА МАРФА: $script:HomeDir"
Write-Host "RAM всего: $(Get-TotalRamGB) ГБ, свободно: $(Get-FreeRamGB) ГБ (план 44 из 64 — 0.1)"
Write-Host "Ручной режим: скачанное в downloads\ и models\ подхватится само (светофор: scripts\90_manual_check.bat)"
Write-Host "=============================================="

# Диск: свободно >= 90 ГБ (модели 18.63 + опц. 25.10 + студент ~7 + venv/кэши ~10 + запас)
$drive = Get-PSDrive -Name ((Resolve-Path $script:HomeDir).Drive.Name)
$freeGB = [math]::Round($drive.Free / 1GB, 1)
if ($freeGB -lt 90) {
    Fail -Step "00" -Why "на диске свободно ${freeGB} ГБ, нужно >= 90 (модели + venv + запас)"
}
Write-Step "Диск: свободно ${freeGB} ГБ — допуск пройден"

foreach ($s in $steps) {
    $name = [IO.Path]::GetFileNameWithoutExtension($s.Script)
    Write-Host ""
    Write-Host "----------------------------------------------"
    Write-Host $s.Title
    Write-Host "----------------------------------------------"
    & (Join-Path $PSScriptRoot $s.Script)
    if ($LASTEXITCODE -ne 0) {
        Fail -Step "00" -Why "шаг $name завершился с кодом $LASTEXITCODE — конвейер остановлен (6.7: откат/разбор, не «починю потом»)"
    }
}

Write-Host ""
Write-Host "=============================================="
Write-Host "ДОМ ГОТОВ. Запуск: scripts\start_llama_server.bat (мозг 8082), scripts\start_marfa.bat (web 5001)"
Write-Host "=============================================="
exit 0


