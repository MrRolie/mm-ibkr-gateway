#Requires -Version 5.1
<#
.SYNOPSIS
    Install mm-ibkr-api as Windows service using NSSM.

.DESCRIPTION
    Creates a service that auto-starts API on boot, auto-restarts on failure,
    and loads .env file into service environment.

.PARAMETER Force
    If true, removes existing service before reinstalling.

.EXAMPLE
    .\install-api-service.ps1

.EXAMPLE
    .\install-api-service.ps1 -Force

.NOTES
    Author: mm-ibkr-gateway deployment refactor
    Date: 2026-01-14
    Requires: NSSM installed (run install-nssm.ps1 first)
#>

[CmdletBinding()]
param(
    [switch]$Force
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# Constants
$ServiceName = "mm-ibkr-api"
$NssmPath = "C:\Program Files\NSSM\nssm.exe"
$RepoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$EnvFile = Join-Path $RepoRoot ".env"

# Source common functions
. (Join-Path $PSScriptRoot "utils\common.ps1")

# Validate NSSM is installed
if (-not (Test-Path $NssmPath)) {
    Write-Error "NSSM not found at $NssmPath. Run install-nssm.ps1 first."
    exit 1
}

# Load .env to get secrets (and optional config path override)
if (-not (Test-Path $EnvFile)) {
    Write-Error ".env file not found at $EnvFile. Run configure.ps1 first or create a minimal .env with API_KEY/ADMIN_TOKEN."
    exit 1
}

Import-EnvFile -EnvFilePath $EnvFile

# Load config.json for operational paths
$config = Import-GatewayConfig
if (-not $config) {
    $configPath = Get-GatewayConfigPath
    Write-Error "config.json not found at $configPath. Run configure.ps1 first."
    exit 1
}

$DataStorageDir = Get-GatewayConfigValue $config "data_storage_dir" $null
$LogDir = Get-GatewayConfigValue $config "log_dir" $null

if (-not $DataStorageDir) {
    Write-Error "data_storage_dir not configured in config.json"
    exit 1
}

if (-not $LogDir) {
    $LogDir = Join-Path $DataStorageDir "logs"
}

$PythonExe = Join-Path $DataStorageDir "venv\Scripts\python.exe"

# Validate prerequisites
if (-not (Test-Path $PythonExe)) {
    Write-Error "Python venv not found at $PythonExe. Ensure venv is created under data_storage_dir."
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
        $stopped = Stop-ServiceWithWait -Name $ServiceName -TimeoutSeconds 60 -NssmPath $NssmPath
        if (-not $stopped) {
            Write-Error "Timed out waiting for service $ServiceName to stop. Stop it manually and re-run."
            exit 1
        }
        
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
Write-Verbose "  Python: $PythonExe"
Write-Verbose "  AppDirectory: $RepoRoot"
Write-Verbose "  Command: -m api.uvicorn_runner"

& $NssmPath install $ServiceName $PythonExe "-m api.uvicorn_runner"

if ($LASTEXITCODE -ne 0) {
    Write-Error "Failed to install service $ServiceName"
    exit 1
}

# Configure service properties
Write-Host "Configuring service properties..."

& $NssmPath set $ServiceName AppDirectory $RepoRoot
& $NssmPath set $ServiceName AppStdoutCreationDisposition 4  # Append to file
& $NssmPath set $ServiceName AppStderrCreationDisposition 4
& $NssmPath set $ServiceName AppStdout (Join-Path $LogDir "api-stdout.log")
& $NssmPath set $ServiceName AppStderr (Join-Path $LogDir "api-stderr.log")

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

# Load .env into service environment
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
& $NssmPath set $ServiceName DisplayName "MM IBKR API (FastAPI)"
& $NssmPath set $ServiceName Description "FastAPI REST service for IBKR order execution. Auto-starts on boot, auto-restarts on failure."

Write-Host ""
Write-Host "Service installed successfully!" -ForegroundColor Green
Write-Host ""
Write-Host "Service Name: $ServiceName"
Write-Host "Executable: $PythonExe -m api.uvicorn_runner"
Write-Host "Working Directory: $RepoRoot"
Write-Host "Logs: $LogDir"
Write-Host ""
Write-Host "To start the service:"
Write-Host "  Start-Service -Name $ServiceName" -ForegroundColor Cyan
Write-Host ""
Write-Host "To check service status:"
Write-Host "  Get-Service -Name $ServiceName" -ForegroundColor Cyan
Write-Host ""
Write-Host "To view logs:"
Write-Host "  Get-Content '$LogDir\api-stdout.log' -Tail 50" -ForegroundColor Cyan
Write-Host ""
Write-Host "To stop the service:"
Write-Host "  Stop-Service -Name $ServiceName" -ForegroundColor Cyan
Write-Host ""
