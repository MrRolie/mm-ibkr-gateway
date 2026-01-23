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

# Load config.json
$config = Import-GatewayConfig
$runWindowStart = Get-GatewayConfigValue $config "run_window_start" "04:00"
$runWindowEnd = Get-GatewayConfigValue $config "run_window_end" "20:00"
$runWindowDays = Get-GatewayConfigValue $config "run_window_days" "Mon,Tue,Wed,Thu,Fri"
$runWindowTimezone = Get-GatewayConfigValue $config "run_window_timezone" "America/Toronto"

# For local testing, always use localhost to avoid firewall/binding issues
$apiHost = "127.0.0.1"
$apiPort = [int](Get-GatewayConfigValue $config "api_port" 8000)
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
    # Use Invoke-WebRequest for better error handling
    $response = Invoke-WebRequest -Uri $url -Headers $headers -TimeoutSec 10 -UseBasicParsing
    $resp = $response.Content | ConvertFrom-Json
    
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
        Write-Host $resp
        exit 1
    }
} catch {
    Write-Host "ERROR: API test failed" -ForegroundColor Red
    Write-Host "Message: $($_.Exception.Message)" -ForegroundColor Red
    
    # Try to get status code and response content
    $statusCode = $null
    $errorBody = ""
    
    if ($_.Exception.Response) {
        $statusCode = [int]$_.Exception.Response.StatusCode
        Write-Host "Status Code: $statusCode" -ForegroundColor Red
    }
    
    # Try to read error detail from the exception
    if ($_.ErrorDetails.Message) {
        $errorBody = $_.ErrorDetails.Message
        Write-Host "Response: $errorBody" -ForegroundColor Gray
    }
    
    # Check if this is a window restriction error
    if ($errorBody -like "*outside run window*" -or $errorBody -like "*Service unavailable*") {
        Write-Host "`nAPI is outside run window." -ForegroundColor Yellow
        Write-Host "Run Window: $runWindowStart - $runWindowEnd ($runWindowDays)" -ForegroundColor Gray
        Write-Host "Timezone: $runWindowTimezone" -ForegroundColor Gray
        Write-Host "Current Time: $(Get-Date -Format 'HH:mm zzz')" -ForegroundColor Gray
        Write-Host "`nThis is expected behavior. The API enforces time windows internally." -ForegroundColor Cyan
        Write-Host "To test during off-hours, update run_window_* in config.json and restart the service." -ForegroundColor Cyan
        exit 0  # Exit successfully - this is expected behavior
    }
    
    # Handle specific status codes
    if ($statusCode -eq 503) {
        Write-Host "`nAPI is outside run window." -ForegroundColor Yellow
        Write-Host "Run Window: $runWindowStart - $runWindowEnd ($runWindowDays)" -ForegroundColor Gray
        Write-Host "Current Time: $(Get-Date -Format 'HH:mm')" -ForegroundColor Gray
        Write-Host "`nThis is expected behavior." -ForegroundColor Cyan
        exit 0
    }
    elseif ($statusCode -eq 403) {
        Write-Host "`nTrading is disabled via mm-control." -ForegroundColor Yellow
        Write-Host "Check: C:\ProgramData\mm-control\TRADING_DISABLED" -ForegroundColor Gray
        Write-Host "Enable with: cd C:\Users\mikae\Coding Projects\mm-control\scripts; .\enable-trading.ps1" -ForegroundColor Cyan
    }
    elseif ($statusCode -eq 401) {
        Write-Host "`nAPI key authentication failed." -ForegroundColor Yellow
        Write-Host "Check API_KEY in .env matches the X-API-Key header." -ForegroundColor Gray
    }
    
    if (-not $_.Exception.Response) {
        Write-Host "`nPossible causes:" -ForegroundColor Yellow
        Write-Host "  - API service not running (check: Get-Service -Name mm-ibkr-api)" -ForegroundColor Gray
        Write-Host "  - Gateway not connected to IBKR" -ForegroundColor Gray
        Write-Host "  - Network/firewall blocking connection" -ForegroundColor Gray
    }
    exit 1
}
