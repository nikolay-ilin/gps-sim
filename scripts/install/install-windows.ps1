# Установка gps-sim в venv на Windows и подсказки по ярлыку.
# Запуск из PowerShell в корне репозитория: .\scripts\install\install-windows.ps1
# Политика выполнения при необходимости: Set-ExecutionPolicy -Scope CurrentUser RemoteSigned

$ErrorActionPreference = "Stop"
$Repo = if ($env:REPO_ROOT) { $env:REPO_ROOT } else {
    (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
}
Set-Location $Repo
Write-Host "Каталог проекта: $Repo"

$py = Get-Command py -ErrorAction SilentlyContinue
$python = if ($py) { "py" } else { "python" }

if (-not (Get-Command $python -ErrorAction SilentlyContinue)) {
    Write-Error "Установите Python 3 с python.org и отметьте «Add to PATH»."
}

if (-not (Test-Path ".venv")) {
    & $python -m venv .venv
}
$pip = Join-Path $Repo ".venv\Scripts\pip.exe"
& $pip install -U pip
& $pip install -e ".[dev,ui]"

$exeUi = Join-Path $Repo ".venv\Scripts\gps-sim-ui.exe"
Write-Host ""
Write-Host "Установка завершена."
Write-Host "Консоль: .\.venv\Scripts\Activate.ps1 затем gps-sim, gps-sim-run, gps-sim-ui"
Write-Host "Путь к UI: $exeUi"
Write-Host ""
Write-Host "Ярлык: правый щелчок по gps-sim-ui.exe в .venv\Scripts → отправить на рабочий стол,"
Write-Host "или скопируйте docs\templates\gps-sim-ui-windows-shortcut.vbs.template,"
Write-Host "подставьте пути к exe и каталогу проекта и выполните: cscript //nologo <файл>.vbs"
