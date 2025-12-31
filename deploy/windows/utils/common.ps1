<#
.SYNOPSIS
    Common functions for mm-ibkr-gateway Windows deployment scripts.

.DESCRIPTION
    Shared utilities for loading configuration, checking run window,
    and other common operations.
#>

function Import-EnvFile {
    <#
    .SYNOPSIS
        Load environment variables from .env file.
    #>
    param(
        [string]$EnvFilePath
    )
    
    if (Test-Path $EnvFilePath) {
        Get-Content $EnvFilePath | ForEach-Object {
            if ($_ -match "^([^#=]+)=(.*)$") {
                $key = $matches[1].Trim()
                $value = $matches[2].Trim()
                # Remove quotes if present
                $value = $value -replace '^["'']|["'']$', ''
                Set-Item -Path "Env:$key" -Value $value -ErrorAction SilentlyContinue
            }
        }
    }
}

function Test-RunWindow {
    <#
    .SYNOPSIS
        Check if current time is within the configured run window.
    
    .OUTPUTS
        Boolean - True if within run window, False otherwise.
    #>
    
    # Get configuration
    $startTime = if ($env:RUN_WINDOW_START) { $env:RUN_WINDOW_START } else { "04:00" }
    $endTime = if ($env:RUN_WINDOW_END) { $env:RUN_WINDOW_END } else { "20:00" }
    $runDays = if ($env:RUN_WINDOW_DAYS) { $env:RUN_WINDOW_DAYS } else { "Mon,Tue,Wed,Thu,Fri" }
    
    # Parse times
    try {
        $start = [DateTime]::ParseExact($startTime, "HH:mm", $null)
        $end = [DateTime]::ParseExact($endTime, "HH:mm", $null)
    } catch {
        Write-Warning "Invalid time format in RUN_WINDOW_START/END. Using defaults."
        $start = [DateTime]::ParseExact("04:00", "HH:mm", $null)
        $end = [DateTime]::ParseExact("20:00", "HH:mm", $null)
    }
    
    $now = Get-Date
    $currentTime = $now.TimeOfDay
    $startTimeSpan = $start.TimeOfDay
    $endTimeSpan = $end.TimeOfDay
    
    # Check day of week
    $dayAbbreviations = @{
        "Mon" = "Monday"
        "Tue" = "Tuesday"
        "Wed" = "Wednesday"
        "Thu" = "Thursday"
        "Fri" = "Friday"
        "Sat" = "Saturday"
        "Sun" = "Sunday"
    }
    
    $allowedDays = $runDays -split "," | ForEach-Object { 
        $abbrev = $_.Trim()
        if ($dayAbbreviations.ContainsKey($abbrev)) {
            $dayAbbreviations[$abbrev]
        } else {
            $abbrev
        }
    }
    
    $currentDay = $now.DayOfWeek.ToString()
    
    if ($currentDay -notin $allowedDays) {
        return $false
    }
    
    # Check time
    if ($currentTime -ge $startTimeSpan -and $currentTime -lt $endTimeSpan) {
        return $true
    }
    
    return $false
}

function Get-NextWindowStart {
    <#
    .SYNOPSIS
        Get the next scheduled run window start time.
    
    .OUTPUTS
        DateTime - Next window start time.
    #>
    
    $startTime = if ($env:RUN_WINDOW_START) { $env:RUN_WINDOW_START } else { "04:00" }
    $runDays = if ($env:RUN_WINDOW_DAYS) { $env:RUN_WINDOW_DAYS } else { "Mon,Tue,Wed,Thu,Fri" }
    
    $start = [DateTime]::ParseExact($startTime, "HH:mm", $null)
    $now = Get-Date
    
    $dayMap = @{
        "Mon" = [DayOfWeek]::Monday
        "Tue" = [DayOfWeek]::Tuesday
        "Wed" = [DayOfWeek]::Wednesday
        "Thu" = [DayOfWeek]::Thursday
        "Fri" = [DayOfWeek]::Friday
        "Sat" = [DayOfWeek]::Saturday
        "Sun" = [DayOfWeek]::Sunday
    }
    
    $allowedDays = $runDays -split "," | ForEach-Object { $dayMap[$_.Trim()] }
    
    # Check today if we haven't passed the start time
    if ($now.DayOfWeek -in $allowedDays -and $now.TimeOfDay -lt $start.TimeOfDay) {
        return $now.Date.Add($start.TimeOfDay)
    }
    
    # Find next allowed day
    for ($i = 1; $i -le 7; $i++) {
        $checkDate = $now.AddDays($i)
        if ($checkDate.DayOfWeek -in $allowedDays) {
            return $checkDate.Date.Add($start.TimeOfDay)
        }
    }
    
    return $null
}

function Get-NextWindowEnd {
    <#
    .SYNOPSIS
        Get the next scheduled run window end time.
    
    .OUTPUTS
        DateTime - Next window end time.
    #>
    
    $endTime = if ($env:RUN_WINDOW_END) { $env:RUN_WINDOW_END } else { "20:00" }
    $runDays = if ($env:RUN_WINDOW_DAYS) { $env:RUN_WINDOW_DAYS } else { "Mon,Tue,Wed,Thu,Fri" }
    
    $end = [DateTime]::ParseExact($endTime, "HH:mm", $null)
    $now = Get-Date
    
    $dayMap = @{
        "Mon" = [DayOfWeek]::Monday
        "Tue" = [DayOfWeek]::Tuesday
        "Wed" = [DayOfWeek]::Wednesday
        "Thu" = [DayOfWeek]::Thursday
        "Fri" = [DayOfWeek]::Friday
        "Sat" = [DayOfWeek]::Saturday
        "Sun" = [DayOfWeek]::Sunday
    }
    
    $allowedDays = $runDays -split "," | ForEach-Object { $dayMap[$_.Trim()] }
    
    # Check today if we haven't passed the end time
    if ($now.DayOfWeek -in $allowedDays -and $now.TimeOfDay -lt $end.TimeOfDay) {
        return $now.Date.Add($end.TimeOfDay)
    }
    
    # Find next allowed day
    for ($i = 1; $i -le 7; $i++) {
        $checkDate = $now.AddDays($i)
        if ($checkDate.DayOfWeek -in $allowedDays) {
            return $checkDate.Date.Add($end.TimeOfDay)
        }
    }
    
    return $null
}

function Test-IsAdmin {
    <#
    .SYNOPSIS
        Check if running as administrator.
    #>
    $currentPrincipal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
    return $currentPrincipal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Get-RestartState {
    <#
    .SYNOPSIS
        Get restart state for backoff tracking.
    #>
    $stateFile = "C:\ProgramData\mm-ibkr-gateway\restart_state.json"
    
    if (Test-Path $stateFile) {
        try {
            return Get-Content $stateFile | ConvertFrom-Json
        } catch {
            return @{ gateway = @{ count = 0; lastRestart = $null }; api = @{ count = 0; lastRestart = $null } }
        }
    }
    
    return @{ gateway = @{ count = 0; lastRestart = $null }; api = @{ count = 0; lastRestart = $null } }
}

function Save-RestartState {
    <#
    .SYNOPSIS
        Save restart state for backoff tracking.
    #>
    param($State)
    
    $stateDir = "C:\ProgramData\mm-ibkr-gateway"
    if (-not (Test-Path $stateDir)) {
        New-Item -ItemType Directory -Path $stateDir -Force | Out-Null
    }
    
    $stateFile = Join-Path $stateDir "restart_state.json"
    $State | ConvertTo-Json -Depth 10 | Set-Content $stateFile
}

function Test-CanRestart {
    <#
    .SYNOPSIS
        Check if restart is allowed based on backoff rules.
    
    .PARAMETER Service
        Service name: "gateway" or "api"
    
    .PARAMETER MaxPerHour
        Maximum restarts allowed per hour (default: 5)
    
    .OUTPUTS
        Boolean - True if restart is allowed, False if rate limited.
    #>
    param(
        [string]$Service,
        [int]$MaxPerHour = 5
    )
    
    $state = Get-RestartState
    
    if (-not $state.$Service) {
        $state | Add-Member -NotePropertyName $Service -NotePropertyValue @{ count = 0; lastRestart = $null; firstRestartInWindow = $null } -Force
    }
    
    $serviceState = $state.$Service
    $now = Get-Date
    
    # Reset counter if more than an hour since first restart in window
    if ($serviceState.firstRestartInWindow) {
        $firstRestart = [DateTime]::Parse($serviceState.firstRestartInWindow)
        if (($now - $firstRestart).TotalHours -ge 1) {
            $serviceState.count = 0
            $serviceState.firstRestartInWindow = $null
        }
    }
    
    # Check if under limit
    if ($serviceState.count -lt $MaxPerHour) {
        return $true
    }
    
    return $false
}

function Update-RestartCount {
    <#
    .SYNOPSIS
        Increment restart count for a service.
    #>
    param([string]$Service)
    
    $state = Get-RestartState
    
    if (-not $state.$Service) {
        $state | Add-Member -NotePropertyName $Service -NotePropertyValue @{ count = 0; lastRestart = $null; firstRestartInWindow = $null } -Force
    }
    
    $now = Get-Date
    $serviceState = $state.$Service
    
    # Initialize window if needed
    if (-not $serviceState.firstRestartInWindow -or $serviceState.count -eq 0) {
        $serviceState.firstRestartInWindow = $now.ToString("o")
    }
    
    $serviceState.count++
    $serviceState.lastRestart = $now.ToString("o")
    
    $state.$Service = $serviceState
    Save-RestartState -State $state
}

function Write-Log {
    <#
    .SYNOPSIS
        Write a log entry to the watchdog log.
    #>
    param(
        [string]$Message,
        [string]$Level = "INFO"
    )
    
    $logDir = if ($env:LOG_FILE_PATH) { $env:LOG_FILE_PATH } else { "C:\ProgramData\mm-ibkr-gateway\logs" }
    if (-not (Test-Path $logDir)) {
        New-Item -ItemType Directory -Path $logDir -Force | Out-Null
    }
    
    $logFile = Join-Path $logDir "watchdog.log"
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $entry = "[$timestamp] [$Level] $Message"
    
    Add-Content -Path $logFile -Value $entry
    
    # Also write to console with color
    $color = switch ($Level) {
        "ERROR" { "Red" }
        "WARN" { "Yellow" }
        "INFO" { "Gray" }
        default { "White" }
    }
    Write-Host $entry -ForegroundColor $color
}
