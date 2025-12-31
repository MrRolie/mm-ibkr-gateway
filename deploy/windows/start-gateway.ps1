<#
.SYNOPSIS
    Starts IBKR Gateway for paper trading.

.DESCRIPTION
    Launches IBKR Gateway with auto-login configuration.
    Checks time window before starting unless -Force is specified.

.PARAMETER Force
    Start regardless of time window (for testing).

.PARAMETER ShowWindow
    Launch IBKR Gateway with a visible window (default is minimized).

.EXAMPLE
    .\start-gateway.ps1
    .\start-gateway.ps1 -Force
#>

[CmdletBinding()]
param(
    [switch]$Force,
    [switch]$ShowWindow,
    [switch]$NoAgent
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = (Get-Item $ScriptDir).Parent.Parent.FullName
$StateDir = "C:\ProgramData\mm-ibkr-gateway"

# Source common functions
. (Join-Path $ScriptDir "utils\common.ps1")

Write-Host "`n=== Starting IBKR Gateway ===" -ForegroundColor Cyan

# Load environment
Import-EnvFile -EnvFilePath (Join-Path $RepoRoot ".env")

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

# Check storage path is accessible (fail-safe)
$gdrivePath = $env:GDRIVE_BASE_PATH
if ($gdrivePath -and -not (Test-Path $gdrivePath)) {
    Write-Host "ERROR: Storage path not accessible: $gdrivePath" -ForegroundColor Red
    Write-Host "Is the storage path mounted/available? Will not start gateway without log/audit storage." -ForegroundColor Yellow
    exit 1
}

# Start gateway process
# IBKR Gateway looks for jts.ini in %USERPROFILE%\Jts
# Ensure the config directory exists and is set correctly
$jtsConfigDir = "$env:USERPROFILE\Jts"
$userIniPath = "$jtsConfigDir\jts.ini"
if (-not (Test-Path "$jtsConfigDir\jts.ini")) {
    Write-Host "WARNING: jts.ini not found at $jtsConfigDir\jts.ini" -ForegroundColor Yellow
    Write-Host "Run setup-ibkr-autologin.ps1 to configure auto-login" -ForegroundColor Yellow
    Write-Host "Continuing anyway - Gateway will show login prompt..." -ForegroundColor Gray
}

# Keep install jts.ini in sync if it is missing credentials
$installIniPath = Join-Path $gatewayPath "jts.ini"
if (Test-Path $userIniPath) {
    $userIni = Get-Content -Path $userIniPath -Raw
    $installNeedsUpdate = (-not (Test-Path $installIniPath)) -or -not (Select-String -Path $installIniPath -Pattern "PaperLogin=" -SimpleMatch -ErrorAction SilentlyContinue)
    if ($installNeedsUpdate) {
        try {
            Set-Content -Path $installIniPath -Value $userIni -Encoding UTF8
            Write-Host "Synced jts.ini to gateway install path" -ForegroundColor Gray
        } catch {
            Write-Host "WARNING: Could not sync jts.ini to install path: $_" -ForegroundColor Yellow
        }
    }
}

$agentEnabled = $true
if ($env:IB_AUTOMATER_ENABLED) {
    [bool]::TryParse($env:IB_AUTOMATER_ENABLED, [ref]$agentEnabled) | Out-Null
}
if ($NoAgent) { $agentEnabled = $false }

if ($agentEnabled) {
    # Prepare IBAutomater (Java agent) for UI automation + auto-restart handling
    New-Item -ItemType Directory -Path $StateDir -Force | Out-Null
    $jarSource = Join-Path $ScriptDir "ibautomater\IBAutomater.jar"
    $jarTarget = Join-Path $StateDir "IBAutomater.jar"
    $javaAgentConfigPath = Join-Path $StateDir "IBAutomater.json"

    if (-not (Test-Path $jarSource)) {
        Write-Host "ERROR: IBAutomater.jar missing at $jarSource" -ForegroundColor Red
        Write-Host "Re-run setup or copy jar to deploy/windows/ibautomater/IBAutomater.jar" -ForegroundColor Yellow
        exit 1
    }

    Copy-Item $jarSource $jarTarget -Force

    # Load credentials for the Java agent
    $username = $env:IBKR_USERNAME
    $password = $env:IBKR_PASSWORD
    if (-not $username -or -not $password) {
        $credFile = Join-Path $RepoRoot "secrets\ibkr_credentials.json"
        if (Test-Path $credFile) {
            $creds = Get-Content $credFile | ConvertFrom-Json
            if (-not $username) { $username = $creds.username }
            if (-not $password) { $password = $creds.password }
        }
    }
    if (-not $username -or -not $password) {
        Write-Host "ERROR: IBKR credentials missing (set IBKR_USERNAME/IBKR_PASSWORD or secrets\\ibkr_credentials.json)" -ForegroundColor Red
        exit 1
    }

    $tradingMode = if ($env:TRADING_MODE -eq "live") { "live" } else { "paper" }
    $gatewayPort = if ($tradingMode -eq "live") {
        if ($env:LIVE_GATEWAY_PORT) { [int]$env:LIVE_GATEWAY_PORT } else { 4001 }
    } else {
        if ($env:PAPER_GATEWAY_PORT) { [int]$env:PAPER_GATEWAY_PORT } else { 4002 }
    }
    $exportLogs = $false
    $isRestart = $false
    $agentConfigContent = @(
        $username
        $password
        $tradingMode
        $gatewayPort
        $exportLogs
        $isRestart
    ) -join "`n"
    Set-Content -Path $javaAgentConfigPath -Value $agentConfigContent -Encoding UTF8

    # Ensure ibgateway.vmoptions has the javaagent entry
    $vmOptionsPath = Join-Path $gatewayPath "ibgateway.vmoptions"
    $javaAgentLine = "-javaagent:$jarTarget=$javaAgentConfigPath"
    if (Test-Path $vmOptionsPath) {
        $vmLines = Get-Content $vmOptionsPath
        $filtered = $vmLines | Where-Object { $_ -notmatch "IBAutomater\.jar" }
        if (-not ($filtered -contains $javaAgentLine)) {
            $filtered += $javaAgentLine
        }
        Set-Content -Path $vmOptionsPath -Value $filtered -Encoding UTF8
    } else {
        Set-Content -Path $vmOptionsPath -Value @($javaAgentLine) -Encoding UTF8
    }
} else {
    Write-Host "IBAutomater disabled (env IB_AUTOMATER_ENABLED=false or -NoAgent)" -ForegroundColor Yellow
}

try {
    # Launch gateway; default minimized, optionally visible for debugging
    $windowStyle = if ($ShowWindow) { "Normal" } else { "Minimized" }
    # Force jts config directory so gateway reads the user jts.ini we manage
    $jtsArg = "-J-DjtsConfigDir=$jtsConfigDir"

    $process = Start-Process -FilePath $gatewayExe `
        -WorkingDirectory $gatewayPath `
        -WindowStyle $windowStyle `
        -ArgumentList $jtsArg `
        -PassThru
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
