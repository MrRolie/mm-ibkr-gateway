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
. (Join-Path $ScriptDir "utils\common.ps1")

# Load environment
Import-EnvFile -EnvFilePath (Join-Path $RepoRoot ".env")

# Configuration
$gatewayPort = if ($env:PAPER_GATEWAY_PORT) { [int]$env:PAPER_GATEWAY_PORT } else { 4002 }
$apiPort = if ($env:API_PORT) { [int]$env:API_PORT } else { 8000 }
$apiHost = if ($env:API_BIND_HOST) { $env:API_BIND_HOST } else { "127.0.0.1" }
$maxRestartsPerHour = 5

Write-Log "Watchdog started" "INFO"

# Check if within run window
$inWindow = Test-RunWindow

# Check storage path first
$gdrivePath = $env:GDRIVE_BASE_PATH
if ($gdrivePath -and -not (Test-Path $gdrivePath)) {
    Write-Log "CRITICAL: Storage path not accessible at $gdrivePath" "ERROR"
    Write-Log "Will not start services without log/audit storage" "ERROR"
    exit 1
}

# ==============================================================================
# GATEWAY: Monitor 24/7, restart if unhealthy (IB handles daily soft restart)
# ==============================================================================
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
        
        # Start gateway - respect GATEWAY_SHOW_WINDOW setting
        $showWindow = $false
        if ($env:GATEWAY_SHOW_WINDOW) { [bool]::TryParse($env:GATEWAY_SHOW_WINDOW, [ref]$showWindow) | Out-Null }
        
        $gwParams = @{ Force = $true }
        if ($showWindow) { $gwParams["ShowWindow"] = $true }
        & (Join-Path $ScriptDir "start-gateway.ps1") @gwParams
        Update-RestartCount -Service "gateway"
        
        # Wait for gateway to be ready
        Start-Sleep -Seconds 10
    } else {
        Write-Log "CRITICAL: Gateway restart limit reached ($maxRestartsPerHour/hour). Manual intervention required." "ERROR"
    }
}

# ==============================================================================
# API: Enforce run window - stop outside, monitor/restart inside
# ==============================================================================
if (-not $inWindow) {
    Write-Log "Outside run window - enforcing API stopped" "INFO"
    
    # Stop API if running
    $apiListening = Get-NetTCPConnection -LocalPort $apiPort -State Listen -ErrorAction SilentlyContinue
    if ($apiListening) {
        Write-Log "Stopping API (outside run window)" "INFO"
        & (Join-Path $ScriptDir "stop-api.ps1")
    }
    
    Write-Log "Watchdog complete (Gateway: running 24/7, API: stopped outside window)" "INFO"
    exit 0
}

# Inside run window - check API health

$apiListening = Get-NetTCPConnection -LocalPort $apiPort -State Listen -ErrorAction SilentlyContinue
$apiHealthy = $false

if ($apiListening) {
    # Try health endpoint
    try {
        $healthUrl = "http://${apiHost}:${apiPort}/health"
        $response = Invoke-RestMethod -Uri $healthUrl -TimeoutSec 10 -ErrorAction Stop
        if ($response.status -eq "ok" -or $response.status -eq "degraded") {
            # Health endpoint passed, but verify with a real API call
            # Edge case: API can report "ok" but actual endpoints return 500
            try {
                $apiKey = $env:API_KEY
                $headers = @{}
                if ($apiKey) { $headers["X-API-Key"] = $apiKey }
                
                $testUrl = "http://${apiHost}:${apiPort}/account/summary"
                $testResp = Invoke-RestMethod -Uri $testUrl -Headers $headers -TimeoutSec 5 -ErrorAction Stop
                
                # Real endpoint works
                $apiHealthy = $true
                Write-Log "API health check passed: endpoints working" "INFO"
            } catch {
                # Health check passed but actual endpoint failed - restart needed
                Write-Log "API health endpoint ok but endpoints failing: $_" "WARN"
                $apiHealthy = $false
            }
        }
    } catch {
        Write-Log "API health check failed: $_" "WARN"
    }
}

if (-not $apiHealthy) {
    Write-Log "API is not healthy (inside run window)" "WARN"
    
    # Check if gateway is healthy (after potential restart above)
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
