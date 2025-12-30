<#
.SYNOPSIS
    Watchdog script for mm-ibkr-gateway services.

.DESCRIPTION
    Monitors IBKR Gateway and API health, automatically restarts if needed.
    Runs every 2 minutes via Task Scheduler during the run window.
    Enforces stopped state outside the run window.

.EXAMPLE
    .\watchdog.ps1
#>

[CmdletBinding()]
param()

$ErrorActionPreference = "Continue"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = (Get-Item $ScriptDir).Parent.Parent.FullName

# Source common functions
. (Join-Path $ScriptDir "lib\common.ps1")

# Load environment
Load-EnvFile -EnvFilePath (Join-Path $RepoRoot ".env")

# Configuration
$gatewayPort = if ($env:PAPER_GATEWAY_PORT) { [int]$env:PAPER_GATEWAY_PORT } else { 4002 }
$apiPort = if ($env:API_PORT) { [int]$env:API_PORT } else { 8000 }
$apiHost = if ($env:API_BIND_HOST) { $env:API_BIND_HOST } else { "127.0.0.1" }
$maxRestartsPerHour = 5

Write-Log "Watchdog started" "INFO"

# Check if within run window
$inWindow = Test-RunWindow

if (-not $inWindow) {
    Write-Log "Outside run window - enforcing stopped state" "INFO"
    
    # Stop API if running
    $apiListening = Get-NetTCPConnection -LocalPort $apiPort -State Listen -ErrorAction SilentlyContinue
    if ($apiListening) {
        Write-Log "Stopping API (outside run window)" "INFO"
        & (Join-Path $ScriptDir "stop-api.ps1")
    }
    
    # Stop Gateway if running
    $gatewayRunning = Get-Process -Name "ibgateway" -ErrorAction SilentlyContinue
    if ($gatewayRunning) {
        Write-Log "Stopping Gateway (outside run window)" "INFO"
        & (Join-Path $ScriptDir "stop-gateway.ps1")
    }
    
    Write-Log "Watchdog complete (services stopped - outside window)" "INFO"
    exit 0
}

# We're in the run window - check services

# Check Google Drive first
$gdrivePath = $env:GDRIVE_BASE_PATH
if ($gdrivePath -and -not (Test-Path $gdrivePath)) {
    Write-Log "CRITICAL: Google Drive not accessible at $gdrivePath" "ERROR"
    Write-Log "Will not start services without log/audit storage" "ERROR"
    exit 1
}

# Check IBKR Gateway
$gatewayRunning = Get-Process -Name "ibgateway" -ErrorAction SilentlyContinue
$gatewayListening = Get-NetTCPConnection -LocalPort $gatewayPort -State Listen -ErrorAction SilentlyContinue

$gatewayHealthy = $gatewayRunning -and $gatewayListening

if (-not $gatewayHealthy) {
    Write-Log "Gateway is not healthy (running: $([bool]$gatewayRunning), listening: $([bool]$gatewayListening))" "WARN"
    
    if (Test-CanRestart -Service "gateway" -MaxPerHour $maxRestartsPerHour) {
        Write-Log "Restarting Gateway..." "INFO"
        
        # Stop first if partially running
        if ($gatewayRunning) {
            & (Join-Path $ScriptDir "stop-gateway.ps1") -Force
            Start-Sleep -Seconds 3
        }
        
        # Start gateway
        & (Join-Path $ScriptDir "start-gateway.ps1") -Force
        Update-RestartCount -Service "gateway"
        
        # Wait for gateway to be ready
        Start-Sleep -Seconds 10
    } else {
        Write-Log "CRITICAL: Gateway restart limit reached ($maxRestartsPerHour/hour). Manual intervention required." "ERROR"
    }
}

# Check API
$apiListening = Get-NetTCPConnection -LocalPort $apiPort -State Listen -ErrorAction SilentlyContinue
$apiHealthy = $false

if ($apiListening) {
    # Try health endpoint
    try {
        $healthUrl = "http://${apiHost}:${apiPort}/health"
        $response = Invoke-RestMethod -Uri $healthUrl -TimeoutSec 10 -ErrorAction Stop
        if ($response.status -eq "ok" -or $response.status -eq "degraded") {
            $apiHealthy = $true
            Write-Log "API health check passed: $($response.status)" "INFO"
        }
    } catch {
        Write-Log "API health check failed: $_" "WARN"
    }
}

if (-not $apiHealthy) {
    Write-Log "API is not healthy" "WARN"
    
    # Check if gateway is now healthy (after potential restart above)
    $gatewayListening = Get-NetTCPConnection -LocalPort $gatewayPort -State Listen -ErrorAction SilentlyContinue
    
    if (-not $gatewayListening) {
        Write-Log "Cannot start API - Gateway not ready" "WARN"
    } elseif (Test-CanRestart -Service "api" -MaxPerHour $maxRestartsPerHour) {
        Write-Log "Restarting API..." "INFO"
        
        # Stop first if running
        if ($apiListening) {
            & (Join-Path $ScriptDir "stop-api.ps1") -Force
            Start-Sleep -Seconds 2
        }
        
        # Start API
        & (Join-Path $ScriptDir "start-api.ps1") -Force
        Update-RestartCount -Service "api"
    } else {
        Write-Log "CRITICAL: API restart limit reached ($maxRestartsPerHour/hour). Manual intervention required." "ERROR"
    }
}

# Final status
$gatewayFinal = Get-NetTCPConnection -LocalPort $gatewayPort -State Listen -ErrorAction SilentlyContinue
$apiFinal = Get-NetTCPConnection -LocalPort $apiPort -State Listen -ErrorAction SilentlyContinue

$status = if ($gatewayFinal -and $apiFinal) { "healthy" } 
          elseif ($gatewayFinal -or $apiFinal) { "degraded" } 
          else { "down" }

Write-Log "Watchdog complete - Status: $status (Gateway: $([bool]$gatewayFinal), API: $([bool]$apiFinal))" "INFO"
