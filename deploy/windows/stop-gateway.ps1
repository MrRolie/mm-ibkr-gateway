<#
.SYNOPSIS
    Stops IBKR Gateway gracefully.

.DESCRIPTION
    Terminates IBKR Gateway process. Does not cancel orders or flatten positions.

.PARAMETER Force
    Force kill if graceful shutdown fails.

.EXAMPLE
    .\stop-gateway.ps1
#>

[CmdletBinding()]
param(
    [switch]$Force
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = (Get-Item $ScriptDir).Parent.Parent.FullName

# Source common functions
. (Join-Path $ScriptDir "lib\common.ps1")

Write-Host "`n=== Stopping IBKR Gateway ===" -ForegroundColor Cyan

# Load environment
Import-EnvFile -EnvFilePath (Join-Path $RepoRoot ".env")

# Find gateway process
$gatewayProcesses = Get-Process -Name "ibgateway" -ErrorAction SilentlyContinue

if (-not $gatewayProcesses) {
    Write-Host "IBKR Gateway is not running" -ForegroundColor Yellow
    exit 0
}

foreach ($process in $gatewayProcesses) {
    Write-Host "Stopping gateway process (PID: $($process.Id))..." -ForegroundColor Gray
    
    try {
        # Try graceful shutdown first
        $process.CloseMainWindow() | Out-Null
        
        # Wait for process to exit
        $exited = $process.WaitForExit(10000)  # 10 second timeout
        
        if (-not $exited) {
            if ($Force) {
                Write-Host "Graceful shutdown timed out, forcing termination..." -ForegroundColor Yellow
                $process.Kill()
                $process.WaitForExit(5000)
            } else {
                Write-Host "Graceful shutdown timed out. Use -Force to kill." -ForegroundColor Yellow
            }
        }
    } catch {
        Write-Host "Error stopping process: $_" -ForegroundColor Yellow
        if ($Force) {
            try {
                Stop-Process -Id $process.Id -Force
            } catch {
                Write-Host "Failed to force kill: $_" -ForegroundColor Red
            }
        }
    }
}

# Verify stopped
Start-Sleep -Seconds 2
$remaining = Get-Process -Name "ibgateway" -ErrorAction SilentlyContinue
if ($remaining) {
    Write-Host "WARNING: Some gateway processes still running" -ForegroundColor Yellow
    $remaining | ForEach-Object { Write-Host "  PID: $($_.Id)" }
} else {
    Write-Host "IBKR Gateway stopped successfully" -ForegroundColor Green
    
    # Log shutdown
    $logFile = Join-Path $env:LOG_FILE_PATH "gateway_startup.log"
    $logEntry = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') - Gateway stopped"
    Add-Content -Path $logFile -Value $logEntry -ErrorAction SilentlyContinue
}
