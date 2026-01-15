#Requires -Version 5.1
<#
.SYNOPSIS
    Install IBKR Gateway as Windows service using NSSM.

.DESCRIPTION
    Creates a service that auto-starts Gateway on boot, auto-restarts on failure,
    with IBAutomater configured for auto-login.

.PARAMETER Force
    If true, removes existing service before reinstalling.

.EXAMPLE
    .\install-gateway-service.ps1

.EXAMPLE
    .\install-gateway-service.ps1 -Force

.NOTES
    Author: mm-ibkr-gateway deployment refactor
    Date: 2026-01-14
    Requires: NSSM installed (run install-nssm.ps1 first)
    Requires: IBAutomater setup (run setup-ibkr-autologin.ps1 first)
#>

[CmdletBinding()]
param(
    [switch]$Force
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# Constants
$ServiceName = "mm-ibkr-gateway"
$NssmPath = "C:\Program Files\NSSM\nssm.exe"
$RepoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$EnvFile = Join-Path $RepoRoot ".env"

# Validate NSSM is installed
if (-not (Test-Path $NssmPath)) {
    Write-Error "NSSM not found at $NssmPath. Run install-nssm.ps1 first."
    exit 1
}

# Load .env to get paths
if (-not (Test-Path $EnvFile)) {
    Write-Error ".env file not found at $EnvFile. Run configure.ps1 first."
    exit 1
}

# Parse .env for required variables
$envVars = @{}
Get-Content $EnvFile | Where-Object {
    -not ($_.Trim().StartsWith("#")) -and $_.Trim().Length -gt 0 -and $_.Contains("=")
} | ForEach-Object {
    $parts = $_ -split "=", 2
    $key = $parts[0].Trim()
    $value = $parts[1].Trim()
    $envVars[$key] = $value
}

$GatewayPath = $envVars["IBKR_GATEWAY_PATH"]
$LogDir = $envVars["LOG_DIR"]
$DataStorageDir = $envVars["DATA_STORAGE_DIR"]

if (-not $GatewayPath) {
    Write-Error "IBKR_GATEWAY_PATH not found in .env"
    exit 1
}

if (-not $LogDir) {
    $LogDir = Join-Path $DataStorageDir "logs"
}

$GatewayExe = Join-Path $GatewayPath "ibgateway.exe"

# Validate prerequisites
if (-not (Test-Path $GatewayExe)) {
    Write-Error "IBKR Gateway not found at $GatewayExe"
    Write-Host "Ensure IBKR Gateway is installed and IBKR_GATEWAY_PATH is correct in .env"
    exit 1
}

# Ensure log directory exists
if (-not (Test-Path $LogDir)) {
    New-Item -Path $LogDir -ItemType Directory -Force | Out-Null
    Write-Verbose "Created log directory: $LogDir"
}

# Remove existing service if Force specified
if ($Force) {
    Write-Host "Force flag specified - removing existing service if present..."
    $existingService = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
    if ($existingService) {
        Write-Verbose "Stopping service $ServiceName"
        & $NssmPath stop $ServiceName 2>$null
        Start-Sleep -Seconds 2
        
        Write-Verbose "Removing service $ServiceName"
        & $NssmPath remove $ServiceName confirm 2>$null
        Start-Sleep -Seconds 1
    }
}

# Check if service already exists
$existingService = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if ($existingService) {
    Write-Error "Service $ServiceName already exists. Use -Force to reinstall."
    exit 1
}

# Create service
Write-Host "Installing service: $ServiceName"
Write-Verbose "  Gateway: $GatewayExe"
Write-Verbose "  AppDirectory: $GatewayPath"

& $NssmPath install $ServiceName $GatewayExe ""

if ($LASTEXITCODE -ne 0) {
    Write-Error "Failed to install service $ServiceName"
    exit 1
}

# Configure service properties
Write-Host "Configuring service properties..."

& $NssmPath set $ServiceName AppDirectory $GatewayPath
& $NssmPath set $ServiceName AppStdoutCreationDisposition 4  # Append to file
& $NssmPath set $ServiceName AppStderrCreationDisposition 4
& $NssmPath set $ServiceName AppStdout (Join-Path $LogDir "gateway-stdout.log")
& $NssmPath set $ServiceName AppStderr (Join-Path $LogDir "gateway-stderr.log")

# Enable log rotation at 10MB
& $NssmPath set $ServiceName AppRotateFiles 1
& $NssmPath set $ServiceName AppRotateBytes 10485760  # 10MB

# Set start type to auto-start
Write-Verbose "Setting start type to auto-start..."
& $NssmPath set $ServiceName Start SERVICE_AUTO_START

# Configure restart behavior
Write-Verbose "Configuring restart behavior..."
& $NssmPath set $ServiceName AppRestartDelay 5000  # 5 seconds
& $NssmPath set $ServiceName AppExit Default Restart
& $NssmPath set $ServiceName AppThrottle 10000  # 10 seconds throttle

# Load .env into service environment (same as API)
Write-Verbose "Loading environment from .env..."
$envContent = @()
Get-Content $EnvFile | Where-Object {
    -not ($_.Trim().StartsWith("#")) -and $_.Trim().Length -gt 0
} | ForEach-Object {
    $envContent += $_
}
$envString = $envContent -join "`n"
& $NssmPath set $ServiceName AppEnvironmentExtra $envString

# Set service display name and description
Write-Verbose "Setting display name and description..."
$tradingMode = $envVars["TRADING_MODE"]
$displayMode = if ($tradingMode -eq "live") { "LIVE TRADING" } else { "Paper Trading" }
& $NssmPath set $ServiceName DisplayName "MM IBKR Gateway ($displayMode)"
& $NssmPath set $ServiceName Description "Interactive Brokers Gateway with auto-login (IBAutomater). Auto-starts on boot, auto-restarts on failure."

Write-Host ""
Write-Host "Service installed successfully!" -ForegroundColor Green
Write-Host ""
Write-Host "Service Name: $ServiceName"
Write-Host "Executable: $GatewayExe"
Write-Host "Working Directory: $GatewayPath"
Write-Host "Trading Mode: $displayMode" -ForegroundColor $(if ($tradingMode -eq "live") { "Red" } else { "Yellow" })
Write-Host "Logs: $LogDir"
Write-Host ""
Write-Host "To start the service:"
Write-Host "  Start-Service -Name $ServiceName" -ForegroundColor Cyan
Write-Host ""
Write-Host "To check service status:"
Write-Host "  Get-Service -Name $ServiceName" -ForegroundColor Cyan
Write-Host ""
Write-Host "To view logs:"
Write-Host "  Get-Content '$LogDir\gateway-stdout.log' -Tail 50" -ForegroundColor Cyan
Write-Host ""
Write-Host "To stop the service:"
Write-Host "  Stop-Service -Name $ServiceName" -ForegroundColor Cyan
Write-Host ""
