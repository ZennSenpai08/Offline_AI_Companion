param([string]$Python = '')
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$environmentPath = Join-Path $projectRoot '.venv'
$environmentPython = Join-Path $environmentPath 'Scripts/python.exe'
if (!(Test-Path -LiteralPath $environmentPython)) {
    if ($Python) {
        & $Python -c "import sys,struct; assert (3,10) <= sys.version_info[:2] < (3,15) and struct.calcsize('P') == 8, 'Requires Python 3.10-3.14 x64; 3.12 recommended'"
        if ($LASTEXITCODE -ne 0) { throw 'Selected Python is unavailable or unsupported.' }
        & $Python -m venv $environmentPath
    } else {
        & py -3.12 -m venv $environmentPath
    }
    if ($LASTEXITCODE -ne 0) { throw 'Install Python 3.12 x64, or pass -Python with a supported interpreter path.' }
}
& $environmentPython -m pip install --only-binary=:all: -r (Join-Path $projectRoot 'requirements.txt')
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed. Check network access or install from a trusted local wheelhouse.' }
& $environmentPython -m pip check
if ($LASTEXITCODE -ne 0) { throw 'Dependency consistency check failed.' }
& $environmentPython -c "from PySide6 import QtCore, QtGui, QtWidgets; import psutil; print('Qt', QtCore.qVersion(), 'ready')"
if ($LASTEXITCODE -ne 0) { throw 'Qt import failed. See docs/phase-2-validation.md.' }
Write-Host 'Setup complete. From the project directory run: .\.venv\Scripts\python.exe -m app'
