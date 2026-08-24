$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $repoRoot
$env:PYTHONUTF8 = "1"

Write-Host "标注页面：http://127.0.0.1:8010"
Write-Host "按 Ctrl+C 停止"
& .\.venv\Scripts\python.exe -m annotation_tool.app --host 127.0.0.1 --port 8010
