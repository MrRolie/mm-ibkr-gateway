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
. (Join-Path $ScriptDir "utils\common.ps1")

# Load environment
Import-EnvFile -EnvFilePath (Join-Path $RepoRoot ".env")

$config = Import-GatewayConfig
$configPath = Get-GatewayConfigPath
$dataStorageDir = Get-GatewayConfigValue $config "data_storage_dir" $null
$logDir = Get-GatewayConfigValue $config "log_dir" $null
$gatewayPath = Get-GatewayConfigValue $config "ibkr_gateway_path" $null
$apiPort = [int](Get-GatewayConfigValue $config "api_port" 8000)
$apiHost = Get-GatewayConfigValue $config "api_bind_host" "127.0.0.1"
$paperPort = [int](Get-GatewayConfigValue $config "paper_gateway_port" 4002)
$livePort = [int](Get-GatewayConfigValue $config "live_gateway_port" 4001)
$controlBaseDir = Get-GatewayConfigValue $config "mm_control_base_dir" "C:\ProgramData\mm-control"
$controlFile = Join-Path $controlBaseDir "control.json"
$tradingMode = "paper"
if (Test-Path $controlFile) {
    try {
        $controlState = Get-Content -Path $controlFile -Raw | ConvertFrom-Json
        if ($controlState.trading_mode) { $tradingMode = $controlState.trading_mode }
    } catch {
        $tradingMode = "paper"
    }
}
$gatewayPort = if ($tradingMode -eq "live") { $livePort } else { $paperPort }

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
        "PASS" { "[+]" }
        "WARN" { "[!]" }
        "FAIL" { "[x]" }
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

Write-Host ("\n" + "="*60) -ForegroundColor Cyan
Write-Host "  mm-ibkr-gateway Deployment Verification" -ForegroundColor Cyan
Write-Host ("="*60) -ForegroundColor Cyan
Write-Host ""

# ============================================================================
# Configuration Checks
# ============================================================================
Write-Host "CONFIGURATION" -ForegroundColor White

# config.json
if ($config) {
    Write-Check "config.json exists" "PASS" $configPath
} else {
    Write-Check "config.json exists" "FAIL" "Run configure.ps1 (expected at $configPath)"
}

# .env file (secrets)
$envFile = Join-Path $RepoRoot ".env"
if (Test-Path $envFile) {
    Write-Check ".env file exists" "PASS"
} else {
    Write-Check ".env file exists" "WARN" "Create .env for API_KEY/ADMIN_TOKEN secrets"
}

# Required config keys
$requiredConfigKeys = @("api_bind_host", "api_port", "data_storage_dir", "ibkr_gateway_path")
foreach ($key in $requiredConfigKeys) {
    $value = Get-GatewayConfigValue $config $key $null
    if ($value) {
        $display = $value.ToString()
        Write-Check "$key configured" "PASS" $display.Substring(0, [Math]::Min(30, $display.Length))
    } else {
        Write-Check "$key configured" "FAIL" "Missing in config.json"
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

# Storage path
if ($dataStorageDir) {
    if (Test-Path $dataStorageDir) {
        Write-Check "Storage path accessible" "PASS" $dataStorageDir
    } else {
        Write-Check "Storage path accessible" "FAIL" "Path not found: $dataStorageDir"
    }
}

# Log directory
if ($logDir) {
    if (Test-Path $logDir) {
        Write-Check "Log directory exists" "PASS" $logDir
    } else {
        Write-Check "Log directory exists" "WARN" "Will be created on first run"
    }
} else {
    Write-Check "Log directory configured" "WARN" "log_dir not set; default created on first run"
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

# VENV CHECK
if ($dataStorageDir) {
    $venvPython = Join-Path $dataStorageDir "venv\Scripts\python.exe"
    if (Test-Path $venvPython) {
        Write-Check "Python venv present" "PASS" $venvPython
    } else {
        Write-Check "Python venv present" "WARN" "Run configure.ps1 to create venv"
    }
}

# ============================================================================
# IBKR Gateway Checks
# ============================================================================
Write-Host "IBKR GATEWAY" -ForegroundColor White

# Gateway installation
if ($gatewayPath) {
    if (Test-Path $gatewayPath) {
        Write-Check "Gateway installation found" "PASS" $gatewayPath
        
        # Check for ibgateway.exe
        $exePath = Get-ChildItem -Path $gatewayPath -Recurse -Filter "ibgateway.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($exePath) {
            Write-Check "ibgateway.exe found" "PASS"
        } else {
            Write-Check "ibgateway.exe found" "FAIL" "Not found in gateway path"
        }
    } else {
        Write-Check "Gateway installation found" "FAIL" "Path not found"
    }
} else {
    Write-Check "Gateway installation found" "FAIL" "ibkr_gateway_path not set"
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
    
    # Check for allowed IP allow rule
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
# NSSM Services Checks
# ============================================================================
Write-Host "NSSM SERVICES" -ForegroundColor White

$expectedServices = @("mm-ibkr-api", "mm-ibkr-gateway")

foreach ($serviceName in $expectedServices) {
    $service = Get-Service -Name $serviceName -ErrorAction SilentlyContinue
    if ($service) {
        $statusColor = switch ($service.Status) {
            "Running" { "Green" }
            "Stopped" { "Yellow" }
            default { "Red" }
        }
        Write-Check "$serviceName installed" "PASS" "Status: $($service.Status)"
        
        if ($service.StartType -eq "Automatic") {
            Write-Check "  Auto-start enabled" "PASS"
        } else {
            Write-Check "  Auto-start enabled" "WARN" "StartType: $($service.StartType)"
        }
    } else {
        Write-Check "$serviceName installed" "FAIL" "Run install-$($serviceName -replace 'mm-ibkr-','')-service.ps1"
    }
}

# Check if NSSM is installed
$nssmPath = "C:\Program Files\NSSM\nssm.exe"
if (Test-Path $nssmPath) {
    Write-Check "NSSM installed" "PASS"
} else {
    Write-Check "NSSM installed" "FAIL" "Run install-nssm.ps1"
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
$apiListening = Get-NetTCPConnection -LocalPort $apiPort -State Listen -ErrorAction SilentlyContinue
if ($apiListening) {
    Write-Check "API port $apiPort listening" "PASS"
    
    # Health check
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
Write-Host ("="*60) -ForegroundColor Cyan
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
