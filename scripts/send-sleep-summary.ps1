param([string]$Backend = "http://127.0.0.1:8000")
$payload = Get-Content -Raw (Join-Path $PSScriptRoot "sample-sleep-summary.json")
Invoke-RestMethod -Method Post -Uri "$Backend/api/v1/ingest/sleep-summaries" -ContentType "application/json" -Body $payload

