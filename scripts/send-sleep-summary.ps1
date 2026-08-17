param(
    [string]$Backend = "http://127.0.0.1:8000",
    [string]$Token = ""
)
$payload = Get-Content -Raw (Join-Path $PSScriptRoot "sample-sleep-summary.json")
$headers = @{}
if ($Token) { $headers["X-EH-Sleep-Token"] = $Token }
Invoke-RestMethod -Method Post -Uri "$Backend/api/v1/ingest/sleep-reports" -Headers $headers -ContentType "application/json" -Body $payload
