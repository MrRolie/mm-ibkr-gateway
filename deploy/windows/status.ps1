<#
.SYNOPSIS
    Shows current status of mm-ibkr-gateway services.

.DESCRIPTION
    Displays detailed status information including processes, ports,
    scheduled tasks, and configuration.

.EXAMPLE
    .\status.ps1
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

Write-Host ("`n" + ("=" * 60)) -ForegroundColor Cyan
Write-Host "  mm-ibkr-gateway Status" -ForegroundColor Cyan
Write-Host ("=" * 60) -ForegroundColor Cyan
Write-Host ""

# Time and window status
$now = Get-Date
$inWindow = Test-RunWindow
$windowColor = if ($inWindow) { "Green" } else { "Yellow" }

Write-Host "TIME & SCHEDULE" -ForegroundColor White
Write-Host "  Current Time:    $($now.ToString('yyyy-MM-dd HH:mm:ss'))"
Write-Host "  In Run Window:   " -NoNewline
Write-Host "$inWindow" -ForegroundColor $windowColor
Write-Host "  Window Hours:    $env:RUN_WINDOW_START - $env:RUN_WINDOW_END"
Write-Host "  Window Days:     $env:RUN_WINDOW_DAYS"

if (-not $inWindow) {
    $nextStart = Get-NextWindowStart
    if ($nextStart) {
        Write-Host "  Next Window:     $($nextStart.ToString('yyyy-MM-dd HH:mm'))"
    }
}
Write-Host ""

# NSSM Services status
Write-Host "NSSM SERVICES" -ForegroundColor White

$apiService = Get-Service -Name "mm-ibkr-api" -ErrorAction SilentlyContinue
if ($apiService) {
    $statusColor = if ($apiService.Status -eq "Running") { "Green" } else { "Red" }
    Write-Host "  mm-ibkr-api:     " -NoNewline
    Write-Host "$($apiService.Status)" -ForegroundColor $statusColor
    if ($apiService.Status -eq "Running") {
        # Find the Python process
        $pythonProcesses = Get-Process -Name "python", "python3" -ErrorAction SilentlyContinue
        $apiProcess = $pythonProcesses | Where-Object {
            $cmdLine = (Get-CimInstance Win32_Process -Filter "ProcessId = $($_.Id)" -ErrorAction SilentlyContinue).CommandLine
            $cmdLine -match "uvicorn|api\.server"
        } | Select-Object -First 1
        if ($apiProcess) {
            Write-Host "                   PID: $($apiProcess.Id)" -ForegroundColor Gray
        }
    }
} else {
    Write-Host "  mm-ibkr-api:     " -NoNewline
    Write-Host "NOT INSTALLED" -ForegroundColor Yellow
}

$gatewayService = Get-Service -Name "mm-ibkr-gateway" -ErrorAction SilentlyContinue
if ($gatewayService) {
    $statusColor = if ($gatewayService.Status -eq "Running") { "Green" } else { "Red" }
    Write-Host "  mm-ibkr-gateway: " -NoNewline
    Write-Host "$($gatewayService.Status)" -ForegroundColor $statusColor
    if ($gatewayService.Status -eq "Running") {
        $gatewayProcess = Get-Process -Name "ibgateway" -ErrorAction SilentlyContinue
        if ($gatewayProcess) {
            Write-Host "                   PID: $($gatewayProcess.Id)" -ForegroundColor Gray
        }
    }
} else {
    Write-Host "  mm-ibkr-gateway: " -NoNewline
    Write-Host "NOT INSTALLED" -ForegroundColor Yellow
}
Write-Host ""

# Port status
Write-Host "NETWORK" -ForegroundColor White
$gatewayListening = Get-NetTCPConnection -LocalPort $gatewayPort -State Listen -ErrorAction SilentlyContinue
$apiListening = Get-NetTCPConnection -LocalPort $apiPort -State Listen -ErrorAction SilentlyContinue

$gwPortColor = if ($gatewayListening) { "Green" } else { "Red" }
$apiPortColor = if ($apiListening) { "Green" } else { "Red" }

Write-Host "  Gateway Port:    $gatewayPort " -NoNewline
Write-Host $(if ($gatewayListening) { "[LISTENING]" } else { "[NOT LISTENING]" }) -ForegroundColor $gwPortColor

Write-Host "  API Port:        $apiPort " -NoNewline
Write-Host $(if ($apiListening) { "[LISTENING]" } else { "[NOT LISTENING]" }) -ForegroundColor $apiPortColor

Write-Host "  API Bind Host:   $apiHost"
Write-Host "  Allowed IPs:     $env:ALLOWED_IPS"
Write-Host ""

# Health check
if ($apiListening) {
    Write-Host "HEALTH CHECK" -ForegroundColor White
    try {
        $healthUrl = "http://${apiHost}:${apiPort}/health"
        $response = Invoke-RestMethod -Uri $healthUrl -TimeoutSec 5 -ErrorAction Stop
        $statusColor = if ($response.status -eq "ok") { "Green" } elseif ($response.status -eq "degraded") { "Yellow" } else { "Red" }
        Write-Host "  API Status:      " -NoNewline
        Write-Host "$($response.status)" -ForegroundColor $statusColor
        Write-Host "  IBKR Connected:  $($response.ibkr_connected)"
        Write-Host "  Trading Mode:    $($response.trading_mode)"
        Write-Host "  Orders Enabled:  $($response.orders_enabled)"
    } catch {
        Write-Host "  API Status:      " -NoNewline
        Write-Host "ERROR - $($_.Exception.Message)" -ForegroundColor Red
    }
    Write-Host ""
}

# Configuration
Write-Host "CONFIGURATION" -ForegroundColor White
Write-Host "  Trading Mode:    $env:TRADING_MODE"
Write-Host "  Orders Enabled:  $env:ORDERS_ENABLED"
Write-Host "  Storage Path:    $env:DATA_STORAGE_DIR"

# Check storage path accessibility
if ($env:DATA_STORAGE_DIR) {
    if (Test-Path $env:DATA_STORAGE_DIR) {
        Write-Host "  Drive Status:    " -NoNewline
        Write-Host "Accessible" -ForegroundColor Green
    } else {
        Write-Host "  Drive Status:    " -NoNewline
        Write-Host "NOT ACCESSIBLE" -ForegroundColor Red
    }
}
Write-Host ""

# mm-control status
Write-Host "MM-CONTROL" -ForegroundColor White
$guardFile = "C:\ProgramData\mm-control\TRADING_DISABLED"
if (Test-Path $guardFile) {
    Write-Host "  Trading Status:  " -NoNewline
    Write-Host "DISABLED" -ForegroundColor Red
    $guardContent = Get-Content $guardFile -Raw
    if ($guardContent) {
        Write-Host "  Guard Reason:    $($guardContent.Split('|')[2].Trim())" -ForegroundColor Gray
    }
} else {
    Write-Host "  Trading Status:  " -NoNewline
    Write-Host "ENABLED" -ForegroundColor Green
}

$togglesFile = "C:\ProgramData\mm-control\toggles.json"
if (Test-Path $togglesFile) {
    try {
        $toggles = Get-Content $togglesFile | ConvertFrom-Json
        Write-Host "  Toggle Store:    Present" -ForegroundColor Gray
        if ($toggles.expires_at) {
            Write-Host "  TTL Expiry:      $($toggles.expires_at)" -ForegroundColor Yellow
        }
    } catch {
        Write-Host "  Toggle Store:    Error reading" -ForegroundColor Yellow
    }
}
Write-Host ""



Write-Host ("=" * 60) -ForegroundColor Cyan
Write-Host ""
