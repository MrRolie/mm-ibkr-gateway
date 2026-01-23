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
$config = Import-GatewayConfig
$apiPort = [int](Get-GatewayConfigValue $config "api_port" 8000)
$apiHost = Get-GatewayConfigValue $config "api_bind_host" "127.0.0.1"
$allowedIps = Get-GatewayConfigValue $config "allowed_ips" "127.0.0.1"
$paperPort = [int](Get-GatewayConfigValue $config "paper_gateway_port" 4002)
$livePort = [int](Get-GatewayConfigValue $config "live_gateway_port" 4001)
$runWindowStart = Get-GatewayConfigValue $config "run_window_start" "04:00"
$runWindowEnd = Get-GatewayConfigValue $config "run_window_end" "20:00"
$runWindowDays = Get-GatewayConfigValue $config "run_window_days" "Mon,Tue,Wed,Thu,Fri"
$runWindowTimezone = Get-GatewayConfigValue $config "run_window_timezone" "America/Toronto"
$dataStorageDir = Get-GatewayConfigValue $config "data_storage_dir" $null

$controlBaseDir = Get-GatewayConfigValue $config "mm_control_base_dir" "C:\ProgramData\mm-control"
$controlFile = Join-Path $controlBaseDir "control.json"
$tradingMode = "paper"
$ordersEnabled = $null
$dryRun = $null
$overrideFile = $null
if (Test-Path $controlFile) {
    try {
        $controlState = Get-Content -Path $controlFile -Raw | ConvertFrom-Json
        if ($controlState.trading_mode) { $tradingMode = $controlState.trading_mode }
        $ordersEnabled = $controlState.orders_enabled
        $dryRun = $controlState.dry_run
        $overrideFile = $controlState.live_trading_override_file
    } catch {
        $tradingMode = "paper"
    }
}

$gatewayPort = if ($tradingMode -eq "live") { $livePort } else { $paperPort }

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
Write-Host "  Window Hours:    $runWindowStart - $runWindowEnd"
Write-Host "  Window Days:     $runWindowDays"
Write-Host "  Window TZ:       $runWindowTimezone"

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
Write-Host "  Allowed IPs:     $allowedIps"
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
$configPath = Get-GatewayConfigPath
Write-Host "  config.json:     $configPath"
Write-Host "  Control File:    $controlFile"
Write-Host "  Trading Mode:    $tradingMode"
if ($null -ne $ordersEnabled) {
    Write-Host "  Orders Enabled:  $ordersEnabled"
}
if ($null -ne $dryRun) {
    Write-Host "  Dry Run:         $dryRun"
}
if ($overrideFile) {
    Write-Host "  Override File:   $overrideFile"
}
Write-Host "  Storage Path:    $dataStorageDir"

# Check storage path accessibility
if ($dataStorageDir) {
    if (Test-Path $dataStorageDir) {
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
$guardFile = Join-Path $controlBaseDir "TRADING_DISABLED"
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

if (Test-Path $controlFile) {
    Write-Host "  Control File:    Present" -ForegroundColor Gray
} else {
    Write-Host "  Control File:    Missing" -ForegroundColor Yellow
}
Write-Host ""



Write-Host ("=" * 60) -ForegroundColor Cyan
Write-Host ""
