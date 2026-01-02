<#
.SYNOPSIS
    Simple API connectivity test (fetch account summary and report first account).

.DESCRIPTION
    Calls the /account/summary endpoint on the local mm-ibkr-gateway API.
    Prints the first accountId returned and exits 0 on success, 1 on failure.

.EXAMPLE
    .\test-api.ps1
#>

[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = (Get-Item $ScriptDir).Parent.Parent.FullName

# Source common functions
. (Join-Path $ScriptDir "utils\common.ps1")

# Load environment
Import-EnvFile -EnvFilePath (Join-Path $RepoRoot ".env")

$apiHost = if ($env:API_BIND_HOST) { $env:API_BIND_HOST } else { "127.0.0.1" }
$apiPort = if ($env:API_PORT) { $env:API_PORT } else { 8000 }
$apiKey  = $env:API_KEY
$url     = "http://${apiHost}:${apiPort}/account/summary"

Write-Host "`n=== Testing mm-ibkr-gateway API ===" -ForegroundColor Cyan
Write-Host "URL: $url" -ForegroundColor Gray
Write-Host "API Key Set: $(if ($apiKey) { 'Yes' } else { 'No' })" -ForegroundColor Gray

# Prepare headers
$headers = @{}
if ($apiKey) {
    $headers["X-API-Key"] = $apiKey
} else {
    Write-Host "WARNING: API_KEY not set; calling without auth header." -ForegroundColor Yellow
}

try {
    $resp = Invoke-RestMethod -Uri $url -Headers $headers -TimeoutSec 10
    $accountId = $null
    if ($resp.accountId) { $accountId = $resp.accountId }
    elseif ($resp.account_id) { $accountId = $resp.account_id }
    elseif ($resp.accounts -and $resp.accounts.Count -gt 0) { $accountId = $resp.accounts[0] }

    if ($accountId) {
        Write-Host "Account summary retrieved." -ForegroundColor Green
        Write-Host "AccountId: $accountId"
        exit 0
    } else {
        Write-Host "ERROR: Account summary call succeeded but no accountId found in response." -ForegroundColor Red
        Write-Host ($resp | ConvertTo-Json -Depth 5)
        exit 1
    }
} catch {
    Write-Host "ERROR: API test failed" -ForegroundColor Red
    Write-Host "Message: $($_.Exception.Message)" -ForegroundColor Red
    if ($_.Exception.Response) {
        Write-Host "Status Code: $($_.Exception.Response.StatusCode)" -ForegroundColor Red
        try {
            $errorBody = $_.Exception.Response.Content.ReadAsString()
            Write-Host "Response Body: $errorBody" -ForegroundColor Red
        } catch { }
    }
    exit 1
}
