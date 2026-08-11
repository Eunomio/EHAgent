[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$response = Invoke-RestMethod -Method Get -Uri 'http://127.0.0.1:8000/api/v1/health'
$response | ConvertTo-Json -Depth 5

if ($response.status -ne 'ok') {
    throw 'EHAgent health check did not return ok.'
}
