<#
.SYNOPSIS
    Health check script for mm-ibkr-gateway services.

.DESCRIPTION
    Checks health of IBKR Gateway and API server.
    Returns structured output and exit codes.

.PARAMETER Json
    Output results as JSON.

.EXAMPLE
    .\healthcheck.ps1
    .\healthcheck.ps1 -Json
#>

[CmdletBinding()]
param(
    [switch]$Json
)

$ErrorActionPreference = "Continue"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = (Get-Item $ScriptDir).Parent.Parent.FullName

# Source common functions
. (Join-Path $ScriptDir "lib\common.ps1")

# Load environment
Import-EnvFile -EnvFilePath (Join-Path $RepoRoot ".env")

# Configuration
$gatewayPort = if ($env:PAPER_GATEWAY_PORT) { [int]$env:PAPER_GATEWAY_PORT } else { 4002 }
$apiPort = if ($env:API_PORT) { [int]$env:API_PORT } else { 8000 }
$apiHost = if ($env:API_BIND_HOST) { $env:API_BIND_HOST } else { "127.0.0.1" }

# Results object
$results = @{
    timestamp = (Get-Date -Format "o")
    inRunWindow = $false
    gateway = @{
        processRunning = $false
        portListening = $false
        healthy = $false
    }
    api = @{
        portListening = $false
        healthEndpoint = $null
        healthy = $false
    }
    overallStatus = "unknown"
    exitCode = 2
}

# Check run window
$results.inRunWindow = Test-RunWindow

# Check IBKR Gateway
$gatewayProcess = Get-Process -Name "ibgateway" -ErrorAction SilentlyContinue
$results.gateway.processRunning = [bool]$gatewayProcess

$gatewayListening = Get-NetTCPConnection -LocalPort $gatewayPort -State Listen -ErrorAction SilentlyContinue
$results.gateway.portListening = [bool]$gatewayListening

$results.gateway.healthy = $results.gateway.processRunning -and $results.gateway.portListening

# Check API
$apiListening = Get-NetTCPConnection -LocalPort $apiPort -State Listen -ErrorAction SilentlyContinue
$results.api.portListening = [bool]$apiListening

if ($apiListening) {
    try {
        $healthUrl = "http://${apiHost}:${apiPort}/health"
        $response = Invoke-RestMethod -Uri $healthUrl -TimeoutSec 10 -ErrorAction Stop
        $results.api.healthEndpoint = $response
        $results.api.healthy = ($response.status -eq "ok" -or $response.status -eq "degraded")
    } catch {
        $results.api.healthEndpoint = @{ error = $_.Exception.Message }
        $results.api.healthy = $false
    }
}

# Determine overall status
if ($results.gateway.healthy -and $results.api.healthy) {
    $results.overallStatus = "healthy"
    $results.exitCode = 0
} elseif ($results.gateway.healthy -or $results.api.healthy) {
    $results.overallStatus = "degraded"
    $results.exitCode = 1
} else {
    $results.overallStatus = "down"
    $results.exitCode = 2
}

# Output
if ($Json) {
    $results | ConvertTo-Json -Depth 10
} else {
    Write-Host "`n=== mm-ibkr-gateway Health Check ===" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Timestamp: $($results.timestamp)"
    Write-Host "In Run Window: $($results.inRunWindow)"
    Write-Host ""
    
    # Gateway status
    $gwColor = if ($results.gateway.healthy) { "Green" } elseif ($results.gateway.processRunning) { "Yellow" } else { "Red" }
    Write-Host "IBKR Gateway:" -ForegroundColor $gwColor
    Write-Host "  Process Running: $($results.gateway.processRunning)"
    Write-Host "  Port $gatewayPort Listening: $($results.gateway.portListening)"
    Write-Host "  Healthy: $($results.gateway.healthy)"
    Write-Host ""
    
    # API status
    $apiColor = if ($results.api.healthy) { "Green" } elseif ($results.api.portListening) { "Yellow" } else { "Red" }
    Write-Host "API Server:" -ForegroundColor $apiColor
    Write-Host "  Port $apiPort Listening: $($results.api.portListening)"
    if ($results.api.healthEndpoint) {
        Write-Host "  Health Endpoint: $($results.api.healthEndpoint.status)"
        if ($results.api.healthEndpoint.ibkr_connected) {
            Write-Host "  IBKR Connected: $($results.api.healthEndpoint.ibkr_connected)"
        }
    }
    Write-Host "  Healthy: $($results.api.healthy)"
    Write-Host ""
    
    # Overall
    $overallColor = switch ($results.overallStatus) {
        "healthy" { "Green" }
        "degraded" { "Yellow" }
        default { "Red" }
    }
    Write-Host "Overall Status: $($results.overallStatus.ToUpper())" -ForegroundColor $overallColor
    Write-Host ""
}

exit $results.exitCode
