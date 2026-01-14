<#
.SYNOPSIS
    Starts the mm-ibkr-gateway FastAPI server using Poetry's venv directly.

.DESCRIPTION
    Launches uvicorn with the FastAPI application, binding to the configured LAN IP.
    Uses Poetry's managed virtual environment directly without relying on Poetry CLI.

.PARAMETER Force
    Start regardless of time window (for testing).

.EXAMPLE
    .\start-api.ps1
    .\start-api.ps1 -Force
#>

[CmdletBinding()]
param(
    [switch]$Force
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = (Get-Item $ScriptDir).Parent.Parent.FullName

# Source common functions
. (Join-Path $ScriptDir "utils\common.ps1")

Write-Host "`n=== Starting mm-ibkr-gateway API ===" -ForegroundColor Cyan

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
$apiPort = if ($env:API_PORT) { $env:API_PORT } else { "8000" }
$existingProcess = Get-NetTCPConnection -LocalPort $apiPort -State Listen -ErrorAction SilentlyContinue
if ($existingProcess) {
    Write-Host "API is already running on port $apiPort" -ForegroundColor Green
    exit 0
}

# Check storage path
$storagePath = $env:DATA_STORAGE_DIR
if ($storagePath -and -not (Test-Path $storagePath)) {
    Write-Host "ERROR: Storage path not accessible: $storagePath" -ForegroundColor Red
    exit 1
}

# Determine bind host
$bindHost = if ($env:API_BIND_HOST) { $env:API_BIND_HOST } else { "127.0.0.1" }

# Prepare log file
$logDir = $env:LOG_DIR
if ($logDir) {
    if ([System.IO.Path]::GetExtension($logDir)) {
        $logDir = Split-Path $logDir -Parent
    }
} else {
    $logDir = Join-Path $RepoRoot "logs"
}
if (-not (Test-Path $logDir)) {
    New-Item -ItemType Directory -Path $logDir -Force | Out-Null
}
$apiLogFile = Join-Path $logDir "api.log"

Write-Host "Binding to: ${bindHost}:${apiPort}" -ForegroundColor Gray
Write-Host "Log file: $apiLogFile" -ForegroundColor Gray

Push-Location $RepoRoot

try {
    # Prefer venv created by configure (DATA_STORAGE_DIR\venv); if not found fall back to Poetry cache
    $usePoetryRunFallback = $false
    $pythonExe = $null

    $storageVenv = if ($env:DATA_STORAGE_DIR) { Join-Path $env:DATA_STORAGE_DIR "venv" } else { $null }
    if ($storageVenv -and (Test-Path (Join-Path $storageVenv "Scripts\python.exe"))) {
        $venvPath = $storageVenv
        $pythonExe = Join-Path $venvPath "Scripts\python.exe"
        Write-Host "Using venv from DATA_STORAGE_DIR: $venvPath" -ForegroundColor Gray
    } else {
        # Find Poetry's venv directly (no Poetry CLI needed)
        # Try multiple possible Poetry cache locations
        $possiblePaths = @(
            "$env:APPDATA\pypoetry\Cache\virtualenvs",
            "$env:LOCALAPPDATA\pypoetry\Cache\virtualenvs",
            "$env:USERPROFILE\AppData\Local\pypoetry\Cache\virtualenvs",
            "$env:USERPROFILE\AppData\Roaming\pypoetry\Cache\virtualenvs"
        )
        
        $poetryVenvBase = $null
        foreach ($path in $possiblePaths) {
            if (Test-Path $path) {
                $poetryVenvBase = $path
                break
            }
        }
    
    if (-not $poetryVenvBase) {
        # No cached venv; check if Poetry is installed and attempt 'poetry run' as a fallback
        $poetryCmd = Get-Command poetry -ErrorAction SilentlyContinue
        if ($poetryCmd) {
            Write-Host "No Poetry venv found, but Poetry is available; will attempt 'poetry run uvicorn' fallback" -ForegroundColor Yellow
            $usePoetryRunFallback = $true
        } else {
            Write-Host "ERROR: Poetry virtual environment cache not found" -ForegroundColor Red
            Write-Host "Checked paths:" -ForegroundColor Yellow
            foreach ($path in $possiblePaths) {
                Write-Host "  - $path" -ForegroundColor Yellow
            }
            Write-Host "Run 'poetry install' from the repo root to create the environment" -ForegroundColor Yellow
            exit 1
        }
    }
    
    $venvDirs = @(Get-ChildItem $poetryVenvBase -Directory -ErrorAction SilentlyContinue | 
                  Where-Object { $_.Name -like "mm-ibkr-gateway*" } | 
                  Sort-Object LastWriteTime -Descending)
    
    if (-not $venvDirs) {
        Write-Host "ERROR: No Poetry virtual environment found for mm-ibkr-gateway" -ForegroundColor Red
        Write-Host "Expected in: $poetryVenvBase" -ForegroundColor Yellow
        Write-Host "Run 'poetry install' from the repo root" -ForegroundColor Yellow
        exit 1
    }
    
    $venvPath = $venvDirs[0].FullName
    $pythonExe = "$venvPath\Scripts\python.exe"
    
    if (-not (Test-Path $pythonExe)) {
        Write-Host "ERROR: Python not found in venv: $pythonExe" -ForegroundColor Red
        exit 1
    }
    
    Write-Host "Using venv: $venvPath" -ForegroundColor Gray
    }

    # Start the API in background using Start-Process
    Write-Host "Starting uvicorn..." -ForegroundColor Gray
    
    if ($usePoetryRunFallback) {
        # Start via poetry run uvicorn
        $process = Start-Process -FilePath "poetry" `
            -ArgumentList @("-m", "api.uvicorn_runner", "--host", $bindHost, "--port", $apiPort, "--log-level", "info") `
            -WorkingDirectory $RepoRoot `
            -NoNewWindow `
            -RedirectStandardOutput $apiLogFile `
            -PassThru
    } else {
        $process = Start-Process -FilePath $pythonExe `
            -ArgumentList @("-m", "api.uvicorn_runner", "--host", $bindHost, "--port", $apiPort, "--log-level", "info") `
            -WorkingDirectory $RepoRoot `
            -NoNewWindow `
            -RedirectStandardOutput $apiLogFile `
            -PassThru
    }
    
    # Store PID for later reference
    $pidDir = if ($logDir) { $logDir } else { $env:TEMP }
    $pidFile = Join-Path $pidDir "api.pid"
    try {
        Set-Content -Path $pidFile -Value $process.Id -Force -ErrorAction Stop
    } catch {
        Write-Host "WARNING: Could not write PID file to ${pidFile}: $_" -ForegroundColor Yellow

        # Fallback: attempt to write PID to %TEMP% if ProgramData/log dir isn't writable
        $fallbackPidFile = Join-Path $env:TEMP "api.pid"
        try {
            Set-Content -Path $fallbackPidFile -Value $process.Id -Force -ErrorAction Stop
            Write-Host "Wrote PID file to TEMP fallback: $fallbackPidFile" -ForegroundColor Yellow
            $pidFile = $fallbackPidFile
        } catch {
            Write-Host "ERROR: Could not write PID file to TEMP fallback (${fallbackPidFile}): $_" -ForegroundColor Red
        }
    }
    
    Write-Host "API server started (PID: $($process.Id))" -ForegroundColor Green
    
    # Wait and verify it's running
    $timeout = 20
    $interval = 2
    $waited = 0
    $listening = $null
    while ($waited -lt $timeout) {
        $listening = Get-NetTCPConnection -LocalPort $apiPort -State Listen -ErrorAction SilentlyContinue
        if ($listening) { break }
        Start-Sleep -Seconds $interval
        $waited += $interval
    }
    
    if ($listening) {
        Write-Host "API is listening on ${bindHost}:${apiPort}" -ForegroundColor Green
        
        # Test health endpoint
        try {
            $healthUrl = "http://${bindHost}:${apiPort}/health"
            $response = Invoke-RestMethod -Uri $healthUrl -TimeoutSec 5
            Write-Host "Health check: $($response.status)" -ForegroundColor Green
        } catch {
            Write-Host "Health check pending (server still starting)" -ForegroundColor Yellow
        }
    } else {
        Write-Host "WARNING: API started but not yet listening on port $apiPort after ${timeout}s" -ForegroundColor Yellow
        Write-Host "Check logs: $apiLogFile" -ForegroundColor Gray
    }
    
} catch {
    Write-Host "ERROR: Failed to start API: $_" -ForegroundColor Red
    exit 1
} finally {
    Pop-Location
}

# Log startup
$logEntry = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') - API started on ${bindHost}:${apiPort}"
Add-Content -Path (Join-Path $logDir "api_startup.log") -Value $logEntry -ErrorAction SilentlyContinue

Write-Host "`nAPI startup complete" -ForegroundColor Green
