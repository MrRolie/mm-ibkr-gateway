<#
.SYNOPSIS
    Starts IBKR Gateway for paper trading.

.DESCRIPTION
    Launches IBKR Gateway with auto-login configuration.
    Checks time window before starting unless -Force is specified.

.PARAMETER Force
    Start regardless of time window (for testing).

.EXAMPLE
    .\start-gateway.ps1
    .\start-gateway.ps1 -Force
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

Write-Host "`n=== Starting IBKR Gateway ===" -ForegroundColor Cyan

# Load environment
Load-EnvFile -EnvFilePath (Join-Path $RepoRoot ".env")

# Check time window unless forced
if (-not $Force) {
    $inWindow = Test-RunWindow
    if (-not $inWindow) {
        Write-Host "Outside run window. Use -Force to override." -ForegroundColor Yellow
        Write-Host "Current time: $(Get-Date -Format 'HH:mm')"
        Write-Host "Run window: $env:RUN_WINDOW_START - $env:RUN_WINDOW_END ($env:RUN_WINDOW_DAYS)"
        exit 0
    }
}

# Check if already running
$gatewayProcess = Get-Process -Name "ibgateway" -ErrorAction SilentlyContinue
if ($gatewayProcess) {
    Write-Host "IBKR Gateway is already running (PID: $($gatewayProcess.Id))" -ForegroundColor Green
    exit 0
}

# Validate gateway path
$gatewayPath = $env:IBKR_GATEWAY_PATH
if (-not $gatewayPath -or -not (Test-Path $gatewayPath)) {
    Write-Host "ERROR: IBKR Gateway path not found: $gatewayPath" -ForegroundColor Red
    Write-Host "Run configure.ps1 to set IBKR_GATEWAY_PATH" -ForegroundColor Yellow
    exit 1
}

# Find ibgateway executable
$gatewayExe = Join-Path $gatewayPath "ibgateway.exe"
if (-not (Test-Path $gatewayExe)) {
    # Try to find it in subdirectories
    $gatewayExe = Get-ChildItem -Path $gatewayPath -Recurse -Filter "ibgateway.exe" -ErrorAction SilentlyContinue | 
                  Select-Object -First 1 -ExpandProperty FullName
    if (-not $gatewayExe) {
        Write-Host "ERROR: ibgateway.exe not found in $gatewayPath" -ForegroundColor Red
        exit 1
    }
}

Write-Host "Starting: $gatewayExe" -ForegroundColor Gray

# Check Google Drive is accessible (fail-safe)
$gdrivePath = $env:GDRIVE_BASE_PATH
if ($gdrivePath -and -not (Test-Path $gdrivePath)) {
    Write-Host "ERROR: Google Drive path not accessible: $gdrivePath" -ForegroundColor Red
    Write-Host "Is Google Drive mounted? Will not start gateway without log/audit storage." -ForegroundColor Yellow
    exit 1
}

# Start gateway process
try {
    $process = Start-Process -FilePath $gatewayExe -PassThru
    Write-Host "IBKR Gateway started (PID: $($process.Id))" -ForegroundColor Green
    
    # Log startup
    $logFile = Join-Path $env:LOG_FILE_PATH "gateway_startup.log"
    $logEntry = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') - Gateway started (PID: $($process.Id))"
    Add-Content -Path $logFile -Value $logEntry -ErrorAction SilentlyContinue
    
    # Wait a moment and verify it's running
    Start-Sleep -Seconds 5
    $running = Get-Process -Name "ibgateway" -ErrorAction SilentlyContinue
    if ($running) {
        Write-Host "Gateway process verified running" -ForegroundColor Green
        
        # Wait for port to be available
        $port = if ($env:TRADING_MODE -eq "live") { $env:LIVE_GATEWAY_PORT } else { $env:PAPER_GATEWAY_PORT }
        $port = if ($port) { $port } else { "4002" }
        
        Write-Host "Waiting for port $port to be available..." -ForegroundColor Gray
        $maxWait = 60  # seconds
        $waited = 0
        while ($waited -lt $maxWait) {
            $listening = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
            if ($listening) {
                Write-Host "Gateway is listening on port $port" -ForegroundColor Green
                exit 0
            }
            Start-Sleep -Seconds 2
            $waited += 2
        }
        
        Write-Host "WARNING: Gateway started but port $port not listening after ${maxWait}s" -ForegroundColor Yellow
        Write-Host "Check IBKR Gateway UI for login status" -ForegroundColor Yellow
    } else {
        Write-Host "WARNING: Gateway process exited unexpectedly" -ForegroundColor Yellow
        exit 1
    }
} catch {
    Write-Host "ERROR: Failed to start gateway: $_" -ForegroundColor Red
    exit 1
}
