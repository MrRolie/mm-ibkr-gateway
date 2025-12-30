<#
.SYNOPSIS
    Stops the mm-ibkr-gateway FastAPI server.

.DESCRIPTION
    Terminates the uvicorn/python process serving the API.

.PARAMETER Force
    Force kill if graceful shutdown fails.

.EXAMPLE
    .\stop-api.ps1
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

Write-Host "`n=== Stopping mm-ibkr-gateway API ===" -ForegroundColor Cyan

# Load environment
Load-EnvFile -EnvFilePath (Join-Path $RepoRoot ".env")

# Get API port
$apiPort = if ($env:API_PORT) { [int]$env:API_PORT } else { 8000 }

# Find process by stored PID
$pidFile = Join-Path "C:\ProgramData\mm-ibkr-gateway" "api.pid"
$storedPid = $null
if (Test-Path $pidFile) {
    $storedPid = [int](Get-Content $pidFile -ErrorAction SilentlyContinue)
}

# Find processes listening on the API port
$listeners = Get-NetTCPConnection -LocalPort $apiPort -State Listen -ErrorAction SilentlyContinue

if (-not $listeners -and -not $storedPid) {
    Write-Host "API is not running on port $apiPort" -ForegroundColor Yellow
    exit 0
}

# Collect PIDs to terminate
$pidsToKill = @()

if ($storedPid) {
    $proc = Get-Process -Id $storedPid -ErrorAction SilentlyContinue
    if ($proc) {
        $pidsToKill += $storedPid
    }
}

if ($listeners) {
    foreach ($listener in $listeners) {
        if ($listener.OwningProcess -notin $pidsToKill) {
            $pidsToKill += $listener.OwningProcess
        }
    }
}

# Also find any python/uvicorn processes that might be related
$pythonProcesses = Get-Process -Name "python", "python3", "pythonw" -ErrorAction SilentlyContinue | 
    Where-Object { 
        $cmdLine = (Get-CimInstance Win32_Process -Filter "ProcessId = $($_.Id)" -ErrorAction SilentlyContinue).CommandLine
        $cmdLine -match "uvicorn" -or $cmdLine -match "api\.server"
    }

foreach ($proc in $pythonProcesses) {
    if ($proc.Id -notin $pidsToKill) {
        $pidsToKill += $proc.Id
    }
}

if ($pidsToKill.Count -eq 0) {
    Write-Host "No API processes found to stop" -ForegroundColor Yellow
    exit 0
}

Write-Host "Found $($pidsToKill.Count) process(es) to stop" -ForegroundColor Gray

foreach ($pid in $pidsToKill) {
    try {
        $process = Get-Process -Id $pid -ErrorAction SilentlyContinue
        if ($process) {
            Write-Host "Stopping process $pid ($($process.ProcessName))..." -ForegroundColor Gray
            
            # Try graceful termination
            Stop-Process -Id $pid -ErrorAction SilentlyContinue
            
            # Wait for exit
            $waitCount = 0
            while ((Get-Process -Id $pid -ErrorAction SilentlyContinue) -and $waitCount -lt 10) {
                Start-Sleep -Milliseconds 500
                $waitCount++
            }
            
            # Force if still running and -Force specified
            $stillRunning = Get-Process -Id $pid -ErrorAction SilentlyContinue
            if ($stillRunning) {
                if ($Force) {
                    Write-Host "Force killing process $pid..." -ForegroundColor Yellow
                    Stop-Process -Id $pid -Force
                } else {
                    Write-Host "Process $pid still running. Use -Force to kill." -ForegroundColor Yellow
                }
            } else {
                Write-Host "Process $pid stopped" -ForegroundColor Green
            }
        }
    } catch {
        Write-Host "Error stopping process $pid : $_" -ForegroundColor Yellow
    }
}

# Clean up PID file
if (Test-Path $pidFile) {
    Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
}

# Verify stopped
Start-Sleep -Seconds 1
$stillListening = Get-NetTCPConnection -LocalPort $apiPort -State Listen -ErrorAction SilentlyContinue
if ($stillListening) {
    Write-Host "WARNING: Something still listening on port $apiPort" -ForegroundColor Yellow
} else {
    Write-Host "API server stopped successfully" -ForegroundColor Green
}

# Log shutdown
$logDir = $env:LOG_FILE_PATH
if ($logDir) {
    $logEntry = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') - API stopped"
    Add-Content -Path (Join-Path $logDir "api_startup.log") -Value $logEntry -ErrorAction SilentlyContinue
}
