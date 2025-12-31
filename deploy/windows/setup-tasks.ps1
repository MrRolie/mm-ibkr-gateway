<#
.SYNOPSIS
    Creates Windows Task Scheduler tasks for mm-ibkr-gateway.

.DESCRIPTION
    Sets up scheduled tasks for:
    - Start/stop IBKR Gateway (weekday 04:00 / 20:01)
    - Start/stop API server (weekday 04:02 / 20:00)
    - Watchdog (every 2 minutes)
    - Boot reconciliation

.PARAMETER Force
    Remove and recreate existing tasks.

.PARAMETER TaskUser
    User account to run tasks under. Defaults to current user.

.EXAMPLE
    .\setup-tasks.ps1
    .\setup-tasks.ps1 -Force
#>

[CmdletBinding()]
param(
    [switch]$Force,
    [string]$TaskUser
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = (Get-Item $ScriptDir).Parent.Parent.FullName

# Source common functions
. (Join-Path $ScriptDir "lib\common.ps1")

Write-Host "`n=== Task Scheduler Setup ===" -ForegroundColor Cyan

# Check admin rights
if (-not (Test-IsAdmin)) {
    Write-Host "ERROR: This script requires administrator privileges." -ForegroundColor Red
    Write-Host "Please run PowerShell as Administrator and try again." -ForegroundColor Yellow
    exit 1
}

# Load environment
Import-EnvFile -EnvFilePath (Join-Path $RepoRoot ".env")

# Determine task user
if (-not $TaskUser) {
    $TaskUser = "$env:USERDOMAIN\$env:USERNAME"
}
Write-Host "Tasks will run as: $TaskUser" -ForegroundColor Gray

# Get password for running tasks when not logged in
Write-Host "`nFor tasks to run when you're not logged in, enter your Windows password:" -ForegroundColor Yellow
$securePassword = Read-Host "Password (press Enter to skip - tasks will only run when logged in)" -AsSecureString

$passwordProvided = $securePassword.Length -gt 0
if (-not $passwordProvided) {
    Write-Host "WARNING: Tasks will only run when user is logged in." -ForegroundColor Yellow
}

# Parse schedule configuration
$startTime = if ($env:RUN_WINDOW_START) { $env:RUN_WINDOW_START } else { "04:00" }
$endTime = if ($env:RUN_WINDOW_END) { $env:RUN_WINDOW_END } else { "20:00" }
$runDays = if ($env:RUN_WINDOW_DAYS) { $env:RUN_WINDOW_DAYS } else { "Mon,Tue,Wed,Thu,Fri" }
$stopTasksEnabled = $false
if ($env:STOP_TASKS_ENABLED) {
    [bool]::TryParse($env:STOP_TASKS_ENABLED, [ref]$stopTasksEnabled) | Out-Null
}
$gatewayStartTaskEnabled = $false
if ($env:START_GATEWAY_TASK_ENABLED) {
    [bool]::TryParse($env:START_GATEWAY_TASK_ENABLED, [ref]$gatewayStartTaskEnabled) | Out-Null
}

# Convert day abbreviations to Task Scheduler format (MON,TUE,WED,THU,FRI,SAT,SUN)
$dayMap = @{
    "Mon" = "MON"
    "Tue" = "TUE"
    "Wed" = "WED"
    "Thu" = "THU"
    "Fri" = "FRI"
    "Sat" = "SAT"
    "Sun" = "SUN"
}
$scheduleDays = ($runDays -split "," | ForEach-Object { $dayMap[$_.Trim()] }) -join ","

# Calculate stop times (API stops first, then gateway)
$endHour = [int]($endTime.Split(":")[0])
$endMinute = [int]($endTime.Split(":")[1])
$gatewayStopTime = "{0:D2}:{1:D2}" -f $endHour, ($endMinute + 1)

# Calculate start times (gateway first, then API)
$startHour = [int]($startTime.Split(":")[0])
$startMinute = [int]($startTime.Split(":")[1])
$apiStartTime = "{0:D2}:{1:D2}" -f $startHour, ($startMinute + 2)

Write-Host "`nSchedule Configuration:" -ForegroundColor Gray
Write-Host "  Days: $scheduleDays"
if ($gatewayStartTaskEnabled) {
    Write-Host "  Gateway Start: $startTime"
} else {
    Write-Host "  Gateway Start: DISABLED (START_GATEWAY_TASK_ENABLED=false)" -ForegroundColor Yellow
}
Write-Host "  API Start: $apiStartTime"
if ($stopTasksEnabled) {
    Write-Host "  API Stop: $endTime"
    Write-Host "  Gateway Stop: $gatewayStopTime"
} else {
    Write-Host "  Stop tasks: DISABLED (set STOP_TASKS_ENABLED=true to create stop tasks)" -ForegroundColor Yellow
}
Write-Host ""

# Task folder
$taskFolder = "\mm-ibkr-gateway"

# Ensure task folder exists in Task Scheduler
$taskFolderPath = "C:\Windows\System32\Tasks\mm-ibkr-gateway"
if (-not (Test-Path $taskFolderPath)) {
    try {
        New-Item -ItemType Directory -Path $taskFolderPath -Force | Out-Null
        Write-Host "Created task folder: $taskFolder" -ForegroundColor Gray
    } catch {
        Write-Host "WARNING: Could not create task folder: $_" -ForegroundColor Yellow
    }
}

# Helper function to create a task
function New-IBKRScheduledTask {
    param(
        [string]$TaskName,
        [string]$Description,
        [string]$ScriptPath,
        [string]$Trigger,  # "DAILY", "ONSTART", "MINUTE"
        [string]$Time,     # For DAILY triggers
        [int]$Interval,    # For MINUTE triggers
        [string]$Days      # For DAILY triggers
    )
    
    $fullTaskName = "$taskFolder\$TaskName"
    
    # Remove existing task if -Force (suppress all output/errors)
    if ($Force) {
        Start-Process -FilePath "schtasks" -ArgumentList "/delete", "/tn", $fullTaskName, "/f" -WindowStyle Hidden -Wait 2>$null
    }
    
    # Check if task exists by querying and checking exit code
    $checkProcess = Start-Process -FilePath "schtasks" -ArgumentList "/query", "/tn", $fullTaskName -WindowStyle Hidden -Wait -PassThru 2>$null
    $existing = $checkProcess.ExitCode -eq 0
    
    if ($existing -and -not $Force) {
        Write-Host "  Task already exists: $TaskName (use -Force to recreate)" -ForegroundColor Yellow
        return
    }
    
    # Build schtasks command - note: /tr needs escaped quotes for XML
    $taskCommand = "powershell.exe -ExecutionPolicy Bypass -NoProfile -File \`"$ScriptPath\`""
    $schtasksArgs = @(
        "/create",
        "/tn", $fullTaskName,
        "/tr", $taskCommand,
        "/ru", $TaskUser,
        "/rl", "HIGHEST"
    )
    
    switch ($Trigger) {
        "DAILY" {
            $schtasksArgs += @("/sc", "WEEKLY", "/d", $Days, "/st", $Time)
        }
        "ONSTART" {
            $schtasksArgs += @("/sc", "ONSTART", "/delay", "0001:00")  # 1 minute delay
        }
        "MINUTE" {
            $schtasksArgs += @("/sc", "MINUTE", "/mo", $Interval)
        }
    }
    
    if ($passwordProvided) {
        $password = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
            [Runtime.InteropServices.Marshal]::SecureStringToBSTR($securePassword)
        )
        $schtasksArgs += @("/rp", $password)
    }
    
    try {
        $result = & schtasks $schtasksArgs 2>&1
        if ($LASTEXITCODE -eq 0) {
            Write-Host "  Created: $TaskName" -ForegroundColor Green
        } else {
            Write-Host "  Failed: $TaskName - $result" -ForegroundColor Red
        }
    } catch {
        Write-Host "  Error creating task $TaskName : $_" -ForegroundColor Red
    }
}

Write-Host "Creating scheduled tasks..." -ForegroundColor Cyan

# 1. Gateway START
if ($gatewayStartTaskEnabled) {
    New-IBKRScheduledTask `
        -TaskName "IBKR-Gateway-START" `
        -Description "Start IBKR Gateway at market open" `
        -ScriptPath (Join-Path $ScriptDir "start-gateway.ps1") `
        -Trigger "DAILY" `
        -Time $startTime `
        -Days $scheduleDays
} else {
    Write-Host "Skipping Gateway start task (START_GATEWAY_TASK_ENABLED=false)" -ForegroundColor Yellow
}

# 2. API START
New-IBKRScheduledTask `
    -TaskName "IBKR-API-START" `
    -Description "Start mm-ibkr-gateway API server" `
    -ScriptPath (Join-Path $ScriptDir "start-api.ps1") `
    -Trigger "DAILY" `
    -Time $apiStartTime `
    -Days $scheduleDays

# 3. API STOP
if ($stopTasksEnabled) {
    New-IBKRScheduledTask `
        -TaskName "IBKR-API-STOP" `
        -Description "Stop mm-ibkr-gateway API server" `
        -ScriptPath (Join-Path $ScriptDir "stop-api.ps1") `
        -Trigger "DAILY" `
        -Time $endTime `
        -Days $scheduleDays
} else {
    Write-Host "Skipping API stop task (STOP_TASKS_ENABLED=false)" -ForegroundColor Yellow
}

# 4. Gateway STOP
if ($stopTasksEnabled) {
    New-IBKRScheduledTask `
        -TaskName "IBKR-Gateway-STOP" `
        -Description "Stop IBKR Gateway after market close" `
        -ScriptPath (Join-Path $ScriptDir "stop-gateway.ps1") `
        -Trigger "DAILY" `
        -Time $gatewayStopTime `
        -Days $scheduleDays
} else {
    Write-Host "Skipping Gateway stop task (STOP_TASKS_ENABLED=false)" -ForegroundColor Yellow
}

# 5. Watchdog
New-IBKRScheduledTask `
    -TaskName "IBKR-Watchdog" `
    -Description "Health check and auto-restart services" `
    -ScriptPath (Join-Path $ScriptDir "watchdog.ps1") `
    -Trigger "MINUTE" `
    -Interval 2

# 6. Boot Reconcile
New-IBKRScheduledTask `
    -TaskName "IBKR-Boot-Reconcile" `
    -Description "Ensure correct state after system boot" `
    -ScriptPath (Join-Path $ScriptDir "boot-reconcile.ps1") `
    -Trigger "ONSTART"

Write-Host "`n=== Task Setup Complete ===" -ForegroundColor Green
Write-Host ""
Write-Host "To view tasks: Task Scheduler > $taskFolder" -ForegroundColor Gray
Write-Host "To list tasks: schtasks /query /tn `"\mm-ibkr-gateway\*`"" -ForegroundColor Gray
Write-Host ""

# Show scheduled tasks
Write-Host "Registered Tasks:" -ForegroundColor Cyan
if (Get-Command Get-ScheduledTask -ErrorAction SilentlyContinue) {
    Get-ScheduledTask -TaskPath "\mm-ibkr-gateway\" | Get-ScheduledTaskInfo | Select-Object TaskName, NextRunTime, LastTaskResult | Format-Table -AutoSize
} else {
    # Fallback for older systems (might fail if wildcard not supported)
    schtasks /query /fo TABLE /tn "\mm-ibkr-gateway\*" 2>$null | Select-Object -Skip 1
}
