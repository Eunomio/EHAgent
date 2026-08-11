[CmdletBinding()]
param(
    [switch]$SkipFrontend
)

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
    & $venvPython -m ruff check app tests
    if ($LASTEXITCODE -ne 0) { throw "Ruff checks failed (exit $LASTEXITCODE)." }
    & $venvPython -m mypy app
    if ($LASTEXITCODE -ne 0) { throw "Mypy checks failed (exit $LASTEXITCODE)." }
    & $venvPython -m pytest --cov=app --cov-report=term-missing
    if ($LASTEXITCODE -ne 0) { throw "Backend tests failed (exit $LASTEXITCODE)." }

    if (-not $SkipFrontend) {
        & npm.cmd --prefix frontend run test
        if ($LASTEXITCODE -ne 0) { throw "Frontend tests failed (exit $LASTEXITCODE)." }
        & npm.cmd --prefix frontend run build
        if ($LASTEXITCODE -ne 0) { throw "Frontend build failed (exit $LASTEXITCODE)." }
    }
}
finally {
    Pop-Location
}
