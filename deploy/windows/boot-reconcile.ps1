<#
.SYNOPSIS
    Boot reconciliation script for mm-ibkr-gateway.

.DESCRIPTION
    Runs at system startup to ensure services are in the correct state
    based on the current time and run window configuration.

.EXAMPLE
    .\boot-reconcile.ps1
#>

[CmdletBinding()]
param()

$ErrorActionPreference = "Continue"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = (Get-Item $ScriptDir).Parent.Parent.FullName

# Source common functions
. (Join-Path $ScriptDir "lib\common.ps1")

# Load environment
Import-EnvFile -EnvFilePath (Join-Path $RepoRoot ".env")

Write-Log "Boot reconciliation started" "INFO"

# Wait for network and Google Drive to be ready
$maxWait = 120  # 2 minutes
$waited = 0
$gdrivePath = $env:GDRIVE_BASE_PATH

while ($gdrivePath -and -not (Test-Path $gdrivePath) -and $waited -lt $maxWait) {
    Write-Log "Waiting for Google Drive ($waited s)..." "INFO"
    Start-Sleep -Seconds 10
    $waited += 10
}

if ($gdrivePath -and -not (Test-Path $gdrivePath)) {
    Write-Log "WARN: Google Drive not available after ${maxWait}s. Proceeding anyway." "WARN"
}

# Check if within run window
$inWindow = Test-RunWindow

if ($inWindow) {
    Write-Log "Within run window - ensuring services are started" "INFO"
    
    # Start Gateway
    $gatewayPort = if ($env:PAPER_GATEWAY_PORT) { [int]$env:PAPER_GATEWAY_PORT } else { 4002 }
    $gatewayListening = Get-NetTCPConnection -LocalPort $gatewayPort -State Listen -ErrorAction SilentlyContinue
    
    if (-not $gatewayListening) {
        Write-Log "Starting Gateway..." "INFO"
        & (Join-Path $ScriptDir "start-gateway.ps1") -Force
        Start-Sleep -Seconds 15
    }
    
    # Start API
    $apiPort = if ($env:API_PORT) { [int]$env:API_PORT } else { 8000 }
    $apiListening = Get-NetTCPConnection -LocalPort $apiPort -State Listen -ErrorAction SilentlyContinue
    
    if (-not $apiListening) {
        Write-Log "Starting API..." "INFO"
        & (Join-Path $ScriptDir "start-api.ps1") -Force
    }
    
    Write-Log "Boot reconciliation complete - services started" "INFO"
} else {
    Write-Log "Outside run window - ensuring services are stopped" "INFO"
    
    # Stop any running services
    & (Join-Path $ScriptDir "stop-api.ps1")
    & (Join-Path $ScriptDir "stop-gateway.ps1")
    
    # Show next window start
    $nextStart = Get-NextWindowStart
    if ($nextStart) {
        Write-Log "Next run window starts: $($nextStart.ToString('yyyy-MM-dd HH:mm'))" "INFO"
    }
    
    Write-Log "Boot reconciliation complete - services stopped" "INFO"
}
