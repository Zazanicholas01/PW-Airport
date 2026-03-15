$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$repoRoot = Split-Path -Parent $PSScriptRoot
$pythonExe = "python"

$env:PYTHONPATH = $repoRoot

cmd /c "python -m pip show uvicorn >nul 2>nul"
if ($LASTEXITCODE -ne 0) {
    Write-Host "[dashboard-dev] installing requirements into user site-packages"
    & $pythonExe -m pip install --user -r (Join-Path $repoRoot "requirements.txt")
}

Write-Host "[dashboard-dev] starting static dashboard shell on http://127.0.0.1:8000"
& $pythonExe -m uvicorn src.web.dashboard_app:app --host 127.0.0.1 --port 8000
