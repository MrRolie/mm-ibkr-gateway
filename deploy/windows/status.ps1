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
. (Join-Path $ScriptDir "lib\common.ps1")

# Load environment
Load-EnvFile -EnvFilePath (Join-Path $RepoRoot ".env")

# Configuration
$gatewayPort = if ($env:PAPER_GATEWAY_PORT) { [int]$env:PAPER_GATEWAY_PORT } else { 4002 }
$apiPort = if ($env:API_PORT) { [int]$env:API_PORT } else { 8000 }
$apiHost = if ($env:API_BIND_HOST) { $env:API_BIND_HOST } else { "127.0.0.1" }

Write-Host "`n" + "="*60 -ForegroundColor Cyan
Write-Host "  mm-ibkr-gateway Status" -ForegroundColor Cyan
Write-Host "="*60 -ForegroundColor Cyan
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

# Process status
Write-Host "PROCESSES" -ForegroundColor White
$gatewayProcess = Get-Process -Name "ibgateway" -ErrorAction SilentlyContinue
if ($gatewayProcess) {
    Write-Host "  IBKR Gateway:    " -NoNewline
    Write-Host "Running (PID: $($gatewayProcess.Id))" -ForegroundColor Green
} else {
    Write-Host "  IBKR Gateway:    " -NoNewline
    Write-Host "Not Running" -ForegroundColor Red
}

$pythonProcesses = Get-Process -Name "python", "python3" -ErrorAction SilentlyContinue
$apiProcess = $pythonProcesses | Where-Object {
    $cmdLine = (Get-CimInstance Win32_Process -Filter "ProcessId = $($_.Id)" -ErrorAction SilentlyContinue).CommandLine
    $cmdLine -match "uvicorn|api\.server"
} | Select-Object -First 1

if ($apiProcess) {
    Write-Host "  API Server:      " -NoNewline
    Write-Host "Running (PID: $($apiProcess.Id))" -ForegroundColor Green
} else {
    Write-Host "  API Server:      " -NoNewline
    Write-Host "Not Running" -ForegroundColor Red
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
Write-Host "  Pi IP (allowed): $env:PI_IP"
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
Write-Host "  Google Drive:    $env:GDRIVE_BASE_PATH"

# Check Google Drive accessibility
if ($env:GDRIVE_BASE_PATH) {
    if (Test-Path $env:GDRIVE_BASE_PATH) {
        Write-Host "  Drive Status:    " -NoNewline
        Write-Host "Accessible" -ForegroundColor Green
    } else {
        Write-Host "  Drive Status:    " -NoNewline
        Write-Host "NOT ACCESSIBLE" -ForegroundColor Red
    }
}

# Check arm file
$armFile = $env:ARM_ORDERS_FILE
if ($armFile) {
    Write-Host "  Arm File:        " -NoNewline
    if (Test-Path $armFile) {
        Write-Host "EXISTS (orders can be placed)" -ForegroundColor Yellow
    } else {
        Write-Host "Not present (orders blocked)" -ForegroundColor Green
    }
}
Write-Host ""

# Scheduled tasks
Write-Host "SCHEDULED TASKS" -ForegroundColor White
$tasks = schtasks /query /fo CSV /tn "\mm-ibkr-gateway\*" 2>$null | ConvertFrom-Csv
if ($tasks) {
    foreach ($task in $tasks) {
        $taskName = $task.TaskName -replace "\\mm-ibkr-gateway\\", ""
        $status = $task.Status
        $statusColor = switch ($status) {
            "Ready" { "Green" }
            "Running" { "Cyan" }
            "Disabled" { "Yellow" }
            default { "Gray" }
        }
        Write-Host "  $taskName : " -NoNewline
        Write-Host $status -ForegroundColor $statusColor
    }
} else {
    Write-Host "  No tasks found. Run setup-tasks.ps1" -ForegroundColor Yellow
}
Write-Host ""

# Restart state
$stateFile = "C:\ProgramData\mm-ibkr-gateway\restart_state.json"
if (Test-Path $stateFile) {
    Write-Host "RESTART STATE" -ForegroundColor White
    $state = Get-Content $stateFile | ConvertFrom-Json
    if ($state.gateway) {
        Write-Host "  Gateway restarts (this hour): $($state.gateway.count)"
        if ($state.gateway.lastRestart) {
            Write-Host "  Gateway last restart: $($state.gateway.lastRestart)"
        }
    }
    if ($state.api) {
        Write-Host "  API restarts (this hour): $($state.api.count)"
        if ($state.api.lastRestart) {
            Write-Host "  API last restart: $($state.api.lastRestart)"
        }
    }
    Write-Host ""
}

Write-Host "="*60 -ForegroundColor Cyan
Write-Host ""
