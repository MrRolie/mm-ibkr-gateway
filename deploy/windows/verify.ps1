<#
.SYNOPSIS
    Validates mm-ibkr-gateway deployment.

.DESCRIPTION
    Comprehensive verification of all deployment components:
    - Environment configuration
    - Directory structure
    - Firewall rules
    - Scheduled tasks
    - Service connectivity

.EXAMPLE
    .\verify.ps1
#>

[CmdletBinding()]
param()

$ErrorActionPreference = "Continue"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = (Get-Item $ScriptDir).Parent.Parent.FullName

# Source common functions
. (Join-Path $ScriptDir "lib\common.ps1")

# Load environment
Import-EnvFile -EnvFilePath (Join-Path $RepoRoot ".env")

$passCount = 0
$warnCount = 0
$failCount = 0

function Write-Check {
    param(
        [string]$Name,
        [string]$Status,  # "PASS", "WARN", "FAIL"
        [string]$Details
    )
    
    $color = switch ($Status) {
        "PASS" { "Green" }
        "WARN" { "Yellow" }
        "FAIL" { "Red" }
        default { "Gray" }
    }
    
    $symbol = switch ($Status) {
        "PASS" { "[✓]" }
        "WARN" { "[!]" }
        "FAIL" { "[✗]" }
        default { "[ ]" }
    }
    
    Write-Host "  $symbol " -ForegroundColor $color -NoNewline
    Write-Host "$Name" -NoNewline
    if ($Details) {
        Write-Host " - $Details" -ForegroundColor Gray
    } else {
        Write-Host ""
    }
    
    switch ($Status) {
        "PASS" { $script:passCount++ }
        "WARN" { $script:warnCount++ }
        "FAIL" { $script:failCount++ }
    }
}

Write-Host "`n" + "="*60 -ForegroundColor Cyan
Write-Host "  mm-ibkr-gateway Deployment Verification" -ForegroundColor Cyan
Write-Host "="*60 -ForegroundColor Cyan
Write-Host ""

# ============================================================================
# Configuration Checks
# ============================================================================
Write-Host "CONFIGURATION" -ForegroundColor White

# .env file
$envFile = Join-Path $RepoRoot ".env"
if (Test-Path $envFile) {
    Write-Check ".env file exists" "PASS"
} else {
    Write-Check ".env file exists" "FAIL" "Run configure.ps1"
}

# Required variables
$requiredVars = @("API_BIND_HOST", "API_PORT", "PI_IP", "GDRIVE_BASE_PATH", "IBKR_GATEWAY_PATH")
foreach ($var in $requiredVars) {
    $value = [Environment]::GetEnvironmentVariable($var)
    if ($value) {
        Write-Check "$var configured" "PASS" $value.Substring(0, [Math]::Min(30, $value.Length))
    } else {
        Write-Check "$var configured" "FAIL" "Not set"
    }
}

# API Key
if ($env:API_KEY) {
    Write-Check "API_KEY configured" "PASS" "$($env:API_KEY.Substring(0,8))..."
} else {
    Write-Check "API_KEY configured" "WARN" "Auth disabled - run generate-api-key.ps1"
}

Write-Host ""

# ============================================================================
# Directory Checks
# ============================================================================
Write-Host "DIRECTORIES" -ForegroundColor White

# Google Drive
if ($env:GDRIVE_BASE_PATH) {
    if (Test-Path $env:GDRIVE_BASE_PATH) {
        Write-Check "Google Drive accessible" "PASS" $env:GDRIVE_BASE_PATH
    } else {
        Write-Check "Google Drive accessible" "FAIL" "Path not found: $env:GDRIVE_BASE_PATH"
    }
}

# Log directory
if ($env:LOG_FILE_PATH) {
    if (Test-Path $env:LOG_FILE_PATH) {
        Write-Check "Log directory exists" "PASS" $env:LOG_FILE_PATH
    } else {
        Write-Check "Log directory exists" "WARN" "Will be created on first run"
    }
}

# Secrets directory
$secretsDir = Join-Path $RepoRoot "secrets"
if (Test-Path $secretsDir) {
    Write-Check "Secrets directory exists" "PASS"
} else {
    Write-Check "Secrets directory exists" "WARN" "Will be created by generate-api-key.ps1"
}

# State directory
$stateDir = "C:\ProgramData\mm-ibkr-gateway"
if (Test-Path $stateDir) {
    Write-Check "State directory exists" "PASS" $stateDir
} else {
    Write-Check "State directory exists" "WARN" "Will be created on first run"
}

Write-Host ""

# ============================================================================
# IBKR Gateway Checks
# ============================================================================
Write-Host "IBKR GATEWAY" -ForegroundColor White

# Gateway installation
if ($env:IBKR_GATEWAY_PATH) {
    if (Test-Path $env:IBKR_GATEWAY_PATH) {
        Write-Check "Gateway installation found" "PASS" $env:IBKR_GATEWAY_PATH
        
        # Check for ibgateway.exe
        $exePath = Get-ChildItem -Path $env:IBKR_GATEWAY_PATH -Recurse -Filter "ibgateway.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($exePath) {
            Write-Check "ibgateway.exe found" "PASS"
        } else {
            Write-Check "ibgateway.exe found" "FAIL" "Not found in gateway path"
        }
    } else {
        Write-Check "Gateway installation found" "FAIL" "Path not found"
    }
} else {
    Write-Check "Gateway installation found" "FAIL" "IBKR_GATEWAY_PATH not set"
}

# jts.ini
$jtsIni = "$env:USERPROFILE\Jts\jts.ini"
if (Test-Path $jtsIni) {
    Write-Check "jts.ini configured" "PASS"
} else {
    Write-Check "jts.ini configured" "WARN" "Run setup-ibkr-autologin.ps1"
}

Write-Host ""

# ============================================================================
# Firewall Checks
# ============================================================================
Write-Host "FIREWALL" -ForegroundColor White

$firewallRules = Get-NetFirewallRule -DisplayName "mm-ibkr-gateway*" -ErrorAction SilentlyContinue
if ($firewallRules) {
    Write-Check "Firewall rules exist" "PASS" "$($firewallRules.Count) rules"
    
    # Check for Pi IP rule
    $allowRules = $firewallRules | Where-Object { $_.Action -eq "Allow" }
    if ($allowRules) {
        Write-Check "Allow rules configured" "PASS"
    } else {
        Write-Check "Allow rules configured" "WARN" "No allow rules found"
    }
    
    $blockRules = $firewallRules | Where-Object { $_.Action -eq "Block" }
    if ($blockRules) {
        Write-Check "Block rule configured" "PASS"
    } else {
        Write-Check "Block rule configured" "WARN" "No block rule found"
    }
} else {
    Write-Check "Firewall rules exist" "FAIL" "Run setup-firewall.ps1 as admin"
}

Write-Host ""

# ============================================================================
# Scheduled Tasks Checks
# ============================================================================
Write-Host "SCHEDULED TASKS" -ForegroundColor White

$expectedTasks = @(
    "IBKR-Gateway-START",
    "IBKR-API-START",
    "IBKR-API-STOP",
    "IBKR-Gateway-STOP",
    "IBKR-Watchdog",
    "IBKR-Boot-Reconcile"
)

$taskOutput = schtasks /query /fo CSV /tn "\mm-ibkr-gateway\*" 2>$null
if ($taskOutput) {
    $tasks = $taskOutput | ConvertFrom-Csv
    $taskNames = $tasks | ForEach-Object { $_.TaskName -replace "\\mm-ibkr-gateway\\", "" }
    
    foreach ($expectedTask in $expectedTasks) {
        if ($expectedTask -in $taskNames) {
            $task = $tasks | Where-Object { $_.TaskName -match $expectedTask }
            Write-Check $expectedTask "PASS" $task.Status
        } else {
            Write-Check $expectedTask "FAIL" "Not found"
        }
    }
} else {
    Write-Check "Scheduled tasks" "FAIL" "No tasks found - run setup-tasks.ps1 as admin"
}

Write-Host ""

# ============================================================================
# Service Checks
# ============================================================================
Write-Host "SERVICES" -ForegroundColor White

# Gateway process
$gatewayProcess = Get-Process -Name "ibgateway" -ErrorAction SilentlyContinue
if ($gatewayProcess) {
    Write-Check "Gateway process running" "PASS" "PID: $($gatewayProcess.Id)"
} else {
    $inWindow = Test-RunWindow
    if ($inWindow) {
        Write-Check "Gateway process running" "WARN" "Not running (within run window)"
    } else {
        Write-Check "Gateway process running" "PASS" "Not running (outside run window)"
    }
}

# Gateway port
$gatewayPort = if ($env:PAPER_GATEWAY_PORT) { [int]$env:PAPER_GATEWAY_PORT } else { 4002 }
$gatewayListening = Get-NetTCPConnection -LocalPort $gatewayPort -State Listen -ErrorAction SilentlyContinue
if ($gatewayListening) {
    Write-Check "Gateway port $gatewayPort listening" "PASS"
} else {
    if ($gatewayProcess) {
        Write-Check "Gateway port $gatewayPort listening" "WARN" "Process running but port not listening"
    } else {
        Write-Check "Gateway port $gatewayPort listening" "PASS" "Not listening (gateway not running)"
    }
}

# API port
$apiPort = if ($env:API_PORT) { [int]$env:API_PORT } else { 8000 }
$apiListening = Get-NetTCPConnection -LocalPort $apiPort -State Listen -ErrorAction SilentlyContinue
if ($apiListening) {
    Write-Check "API port $apiPort listening" "PASS"
    
    # Health check
    $apiHost = if ($env:API_BIND_HOST) { $env:API_BIND_HOST } else { "127.0.0.1" }
    try {
        $healthUrl = "http://${apiHost}:${apiPort}/health"
        $response = Invoke-RestMethod -Uri $healthUrl -TimeoutSec 5 -ErrorAction Stop
        if ($response.status -eq "ok") {
            Write-Check "API health check" "PASS" "status: ok"
        } elseif ($response.status -eq "degraded") {
            Write-Check "API health check" "WARN" "status: degraded (IBKR may not be connected)"
        } else {
            Write-Check "API health check" "WARN" "status: $($response.status)"
        }
    } catch {
        Write-Check "API health check" "FAIL" $_.Exception.Message
    }
} else {
    $inWindow = Test-RunWindow
    if ($inWindow) {
        Write-Check "API port $apiPort listening" "WARN" "Not listening (within run window)"
    } else {
        Write-Check "API port $apiPort listening" "PASS" "Not listening (outside run window)"
    }
}

Write-Host ""

# ============================================================================
# Schedule Info
# ============================================================================
Write-Host "SCHEDULE" -ForegroundColor White

$inWindow = Test-RunWindow
if ($inWindow) {
    Write-Host "  Currently: " -NoNewline
    Write-Host "WITHIN RUN WINDOW" -ForegroundColor Green
    $nextEnd = Get-NextWindowEnd
    if ($nextEnd) {
        Write-Host "  Window ends: $($nextEnd.ToString('yyyy-MM-dd HH:mm'))"
    }
} else {
    Write-Host "  Currently: " -NoNewline
    Write-Host "OUTSIDE RUN WINDOW" -ForegroundColor Yellow
    $nextStart = Get-NextWindowStart
    if ($nextStart) {
        Write-Host "  Next window: $($nextStart.ToString('yyyy-MM-dd HH:mm'))"
    }
}

Write-Host ""

# ============================================================================
# Summary
# ============================================================================
Write-Host "="*60 -ForegroundColor Cyan
Write-Host ""

$totalChecks = $passCount + $warnCount + $failCount
Write-Host "SUMMARY: " -NoNewline
Write-Host "$passCount passed" -ForegroundColor Green -NoNewline
Write-Host ", " -NoNewline
Write-Host "$warnCount warnings" -ForegroundColor Yellow -NoNewline
Write-Host ", " -NoNewline
Write-Host "$failCount failed" -ForegroundColor Red -NoNewline
Write-Host " (total: $totalChecks)"
Write-Host ""

if ($failCount -gt 0) {
    Write-Host "Action Required:" -ForegroundColor Red
    Write-Host "  Fix failed checks before deploying to production."
    Write-Host ""
    exit 1
} elseif ($warnCount -gt 0) {
    Write-Host "Deployment Status:" -ForegroundColor Yellow
    Write-Host "  Deployment functional but review warnings above."
    Write-Host ""
    exit 0
} else {
    Write-Host "Deployment Status:" -ForegroundColor Green
    Write-Host "  All checks passed! Deployment is ready."
    Write-Host ""
    exit 0
}
