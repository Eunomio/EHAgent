[CmdletBinding()]
param(
    [switch]$SkipFrontend
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$venvPython = Join-Path $projectRoot '.venv\Scripts\python.exe'
$condaPython = Join-Path $projectRoot '.venv\python.exe'
$condaExe = 'E:\Coding\Anaconda3\Scripts\conda.exe'
$uvExe = 'E:\Coding\Anaconda3\Scripts\uv.exe'

if (-not (Test-Path -LiteralPath $venvPython) -and -not (Test-Path -LiteralPath $condaPython)) {
    if (Test-Path -LiteralPath $uvExe) {
        $env:UV_CACHE_DIR = Join-Path $projectRoot '.uv-cache'
        $env:UV_PYTHON_INSTALL_DIR = Join-Path $projectRoot '.python'
        & $uvExe venv (Join-Path $projectRoot '.venv') --python 3.11
        if ($LASTEXITCODE -ne 0) { throw "uv failed to create the virtual environment (exit $LASTEXITCODE)." }
    }
    elseif (Test-Path -LiteralPath $condaExe) {
        & $condaExe create --prefix (Join-Path $projectRoot '.venv') python=3.11 pip -y
        if ($LASTEXITCODE -ne 0) { throw "conda failed to create the virtual environment (exit $LASTEXITCODE)." }
    }
    else {
        throw 'Python 3.11 environment is missing and neither uv nor conda was found.'
    }
}

if (-not (Test-Path -LiteralPath $venvPython)) {
    $venvPython = $condaPython
}

if (-not (Test-Path -LiteralPath (Join-Path $projectRoot '.env'))) {
    Copy-Item -LiteralPath (Join-Path $projectRoot '.env.example') -Destination (Join-Path $projectRoot '.env')
    Write-Warning 'Created .env from the example. Replace the engineering API key before use.'
}

& $venvPython -m pip install -r (Join-Path $projectRoot 'requirements-dev.txt')
if ($LASTEXITCODE -ne 0) { throw "Python dependency installation failed (exit $LASTEXITCODE)." }
& $venvPython -m alembic -c (Join-Path $projectRoot 'alembic.ini') upgrade head
if ($LASTEXITCODE -ne 0) { throw "Database migration failed (exit $LASTEXITCODE)." }

if (-not $SkipFrontend) {
    & npm.cmd --prefix (Join-Path $projectRoot 'frontend') ci
    if ($LASTEXITCODE -ne 0) { throw "Frontend dependency installation failed (exit $LASTEXITCODE)." }
    & npm.cmd --prefix (Join-Path $projectRoot 'frontend') run build
    if ($LASTEXITCODE -ne 0) { throw "Frontend build failed (exit $LASTEXITCODE)." }
}

Write-Output 'EHAgent development environment is ready.'
