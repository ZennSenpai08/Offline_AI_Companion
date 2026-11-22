param([switch]$Offscreen, [switch]$Benchmark, [switch]$Audio)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectRoot '.venv/Scripts/python.exe'
if (!(Test-Path -LiteralPath $pythonPath)) { throw 'Run scripts/setup.ps1 first.' }
$previousPlatform = $env:QT_QPA_PLATFORM
Push-Location $projectRoot
try {
    if ($Offscreen) { $env:QT_QPA_PLATFORM = 'offscreen' }
    else { $env:QT_QPA_PLATFORM = 'windows' }
    & $pythonPath -c "from PySide6 import QtCore, QtWidgets; import psutil; print('Qt', QtCore.qVersion())"
    if ($LASTEXITCODE -ne 0) { throw 'Qt is required. Skipped GUI tests are not a Phase 2 pass.' }
    & $pythonPath -m pip check
    if ($LASTEXITCODE -ne 0) { throw 'Dependency consistency check failed.' }
    if ($Audio) {
        & $pythonPath scripts/check_audio.py
        if ($LASTEXITCODE -ne 0) { throw 'Phase 4 native dependencies, model or audio input enumeration failed.' }
    }
    & $pythonPath -m unittest discover -s tests -v
    if ($LASTEXITCODE -ne 0) { throw 'Tests failed.' }
    & $pythonPath -m compileall -q app tests scripts
    if ($LASTEXITCODE -ne 0) { throw 'Compilation failed.' }
    if ($Benchmark) {
        if ($Offscreen) { throw 'Native performance measurements require a visible Windows desktop, not offscreen.' }
        & $pythonPath -m app --data-dir .runtime/phase4-validation --benchmark-seconds 60 --report .runtime/phase4-benchmark.json --snapshot .runtime/phase4-placeholder.png
        if ($LASTEXITCODE -ne 0) { throw 'Application benchmark failed.' }
    }
} finally {
    $env:QT_QPA_PLATFORM = $previousPlatform
    Pop-Location
}
