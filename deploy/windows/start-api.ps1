<#
.SYNOPSIS
    Starts the mm-ibkr-gateway FastAPI server.

.DESCRIPTION
    Launches uvicorn with the FastAPI application, binding to the configured LAN IP.
    Checks time window before starting unless -Force is specified.

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

# Check Google Drive is accessible (fail-safe)
$gdrivePath = $env:GDRIVE_BASE_PATH
if ($gdrivePath -and -not (Test-Path $gdrivePath)) {
    Write-Host "ERROR: Google Drive path not accessible: $gdrivePath" -ForegroundColor Red
    Write-Host "Is Google Drive mounted? Will not start API without log/audit storage." -ForegroundColor Yellow
    exit 1
}

# Validate IBKR Gateway is running (for paper trading)
$gatewayPort = if ($env:PAPER_GATEWAY_PORT) { $env:PAPER_GATEWAY_PORT } else { "4002" }
$gatewayListening = Get-NetTCPConnection -LocalPort $gatewayPort -State Listen -ErrorAction SilentlyContinue
if (-not $gatewayListening) {
    Write-Host "WARNING: IBKR Gateway not listening on port $gatewayPort" -ForegroundColor Yellow
    Write-Host "API will start but may not be able to connect to IBKR" -ForegroundColor Yellow
}

# Determine bind host
$bindHost = if ($env:API_BIND_HOST) { $env:API_BIND_HOST } else { "127.0.0.1" }

# Check for API key
if (-not $env:API_KEY) {
    Write-Host "WARNING: API_KEY not set. Authentication is DISABLED." -ForegroundColor Yellow
    Write-Host "Run generate-api-key.ps1 to create a key." -ForegroundColor Yellow
}

# Prepare log file
$logDir = $env:LOG_FILE_PATH
if (-not $logDir) {
    $logDir = Join-Path $RepoRoot "logs"
}
if (-not (Test-Path $logDir)) {
    New-Item -ItemType Directory -Path $logDir -Force | Out-Null
}
$apiLogFile = Join-Path $logDir "api.log"

Write-Host "Binding to: ${bindHost}:${apiPort}" -ForegroundColor Gray
Write-Host "Log file: $apiLogFile" -ForegroundColor Gray

# Change to repo directory
Push-Location $RepoRoot

try {
    # Check if poetry is available
    $poetryPath = Get-Command poetry -ErrorAction SilentlyContinue
    if (-not $poetryPath) {
        Write-Host "ERROR: Poetry not found in PATH" -ForegroundColor Red
        Write-Host "Install poetry: pip install poetry" -ForegroundColor Yellow
        exit 1
    }
    
    # Build the uvicorn command
    $uvicornArgs = @(
        "run",
        "uvicorn",
        "api.server:app",
        "--host", $bindHost,
        "--port", $apiPort,
        "--log-level", "info"
    )
    
    Write-Host "Starting: poetry $($uvicornArgs -join ' ')" -ForegroundColor Gray
    
    # Start as background process with output redirection
    $processInfo = New-Object System.Diagnostics.ProcessStartInfo
    $processInfo.FileName = "poetry"
    $processInfo.Arguments = $uvicornArgs -join " "
    $processInfo.WorkingDirectory = $RepoRoot
    $processInfo.UseShellExecute = $false
    $processInfo.RedirectStandardOutput = $true
    $processInfo.RedirectStandardError = $true
    $processInfo.CreateNoWindow = $true
    
    # Copy environment variables
    foreach ($key in [Environment]::GetEnvironmentVariables([EnvironmentVariableTarget]::Process).Keys) {
        $processInfo.Environment[$key] = [Environment]::GetEnvironmentVariable($key)
    }
    
    $process = New-Object System.Diagnostics.Process
    $process.StartInfo = $processInfo
    
    # Set up async output handling to log file
    $outputHandler = {
        if (-not [String]::IsNullOrEmpty($EventArgs.Data)) {
            $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
            "$timestamp $($EventArgs.Data)" | Out-File -FilePath $Event.MessageData -Append -Encoding UTF8
        }
    }
    
    $outEvent = Register-ObjectEvent -InputObject $process -EventName OutputDataReceived -Action $outputHandler -MessageData $apiLogFile
    $errEvent = Register-ObjectEvent -InputObject $process -EventName ErrorDataReceived -Action $outputHandler -MessageData $apiLogFile
    
    $process.Start() | Out-Null
    $process.BeginOutputReadLine()
    $process.BeginErrorReadLine()
    
    # Store PID for later reference
    $pidFile = Join-Path "C:\ProgramData\mm-ibkr-gateway" "api.pid"
    Set-Content -Path $pidFile -Value $process.Id
    
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
    
    # Cleanup event handlers
    if ($outEvent) { Unregister-Event -SourceIdentifier $outEvent.Name -ErrorAction SilentlyContinue }
    if ($errEvent) { Unregister-Event -SourceIdentifier $errEvent.Name -ErrorAction SilentlyContinue }
}

# Log startup
$logEntry = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') - API started on ${bindHost}:${apiPort}"
Add-Content -Path (Join-Path $logDir "api_startup.log") -Value $logEntry -ErrorAction SilentlyContinue
