[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$venvPython = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $venvPython)) {
    $venvPython = Join-Path $projectRoot '.venv\python.exe'
}

if (-not (Test-Path -LiteralPath $venvPython)) {
    throw 'Missing .venv. Run scripts\install.ps1 first.'
}

Push-Location $projectRoot
try {
    & $venvPython -m alembic upgrade head
    if ($LASTEXITCODE -ne 0) { throw "Database migration failed (exit $LASTEXITCODE)." }
    & $venvPython -m uvicorn app.main:app --host 127.0.0.1 --port 8000
    if ($LASTEXITCODE -ne 0) { throw "Application server stopped with an error (exit $LASTEXITCODE)." }
}
finally {
    Pop-Location
}
