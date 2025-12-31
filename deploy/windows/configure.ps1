<#
.SYNOPSIS
    Interactive configuration script for mm-ibkr-gateway Windows deployment.

.DESCRIPTION
    Collects required settings and generates .env file for the execution node.
    Creates directory structure for logs and the audit database.

.PARAMETER NonInteractive
    Skip prompts and use environment variables or defaults.

.EXAMPLE
    .\configure.ps1
#>

[CmdletBinding()]
param(
    [switch]$NonInteractive
)

$ErrorActionPreference = "Stop"

# Script paths
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = (Get-Item $ScriptDir).Parent.Parent.FullName
$EnvFile = Join-Path $RepoRoot ".env"
$SecretsDir = Join-Path $RepoRoot "secrets"

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "  mm-ibkr-gateway Configuration Wizard" -ForegroundColor Cyan
Write-Host "========================================`n" -ForegroundColor Cyan

# Helper function to prompt with default
function Read-HostWithDefault {
    param(
        [string]$Prompt,
        [string]$Default,
        [switch]$Required,
        [switch]$Secret
    )
    
    $displayDefault = if ($Default) { " [$Default]" } else { "" }
    $fullPrompt = "$Prompt$displayDefault"
    
    if ($Secret) {
        $secureValue = Read-Host -Prompt $fullPrompt -AsSecureString
        $value = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
            [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureValue)
        )
    } else {
        $value = Read-Host -Prompt $fullPrompt
    }
    
    if ([string]::IsNullOrWhiteSpace($value)) {
        if ($Required -and [string]::IsNullOrWhiteSpace($Default)) {
            Write-Host "This value is required." -ForegroundColor Red
            return Read-HostWithDefault -Prompt $Prompt -Default $Default -Required:$Required -Secret:$Secret
        }
        return $Default
    }
    return $value
}

# Detect LAN IP
function Get-LanIP {
    $lanIP = Get-NetIPAddress -AddressFamily IPv4 | 
        Where-Object { 
            $_.InterfaceAlias -notmatch "Loopback" -and 
            $_.IPAddress -notmatch "^169\." -and
            $_.IPAddress -notmatch "^127\." -and
            $_.PrefixOrigin -ne "WellKnown"
        } | 
        Select-Object -First 1 -ExpandProperty IPAddress
    return $lanIP
}

# Detect IBKR Gateway installation
function Find-IBKRGateway {
    $possiblePaths = @(
        "$env:USERPROFILE\Jts\ibgateway\*",
        "C:\Jts\ibgateway\*",
        "${env:ProgramFiles}\Jts\ibgateway\*",
        "${env:ProgramFiles(x86)}\Jts\ibgateway\*"
    )
    
    foreach ($pattern in $possiblePaths) {
        $found = Get-Item $pattern -ErrorAction SilentlyContinue | 
            Sort-Object Name -Descending | 
            Select-Object -First 1
        if ($found) {
            return $found.FullName
        }
    }
    return $null
}

# Step 1: Repository Path
Write-Host "Step 1: Repository Path" -ForegroundColor Yellow
Write-Host "Detected: $RepoRoot"
$confirmRepo = Read-HostWithDefault -Prompt "Use this path? (Y/n)" -Default "Y"
if ($confirmRepo -eq "n" -or $confirmRepo -eq "N") {
    $RepoRoot = Read-HostWithDefault -Prompt "Enter repository path" -Required
    $EnvFile = Join-Path $RepoRoot ".env"
    $SecretsDir = Join-Path $RepoRoot "secrets"
}
Write-Host ""

# Step 2: Network Configuration
Write-Host "Step 2: Network Configuration" -ForegroundColor Yellow
$detectedIP = Get-LanIP
Write-Host "Detected LAN IP: $detectedIP"

$LanIP = Read-HostWithDefault -Prompt "Laptop LAN IP (API will bind to this)" -Default $detectedIP -Required
$PiIP = Read-HostWithDefault -Prompt "Raspberry Pi IP (allowed to connect)" -Required
$ApiPort = Read-HostWithDefault -Prompt "API Port" -Default "8000"
Write-Host ""

# Step 3: Storage Path
Write-Host "Step 3: Storage Configuration" -ForegroundColor Yellow
Write-Host "Choose where to store logs and audit data (local disk or synced folder)." -ForegroundColor Gray
$storageType = Read-HostWithDefault -Prompt "Storage type (local/gdrive)" -Default "local"
$storageType = $storageType.Trim().ToLower()
$storageLabel = if ($storageType -like "g*") { "Google Drive" } else { "Local" }

if ($storageType -like "g*") {
    $StorageBasePath = Read-HostWithDefault -Prompt "Google Drive base path for logs/audit" -Required

    # Validate drive for synced storage
    if (-not (Test-Path (Split-Path $StorageBasePath -Qualifier))) {
        Write-Host "WARNING: Drive $(Split-Path $StorageBasePath -Qualifier) not found. Is the sync drive mounted?" -ForegroundColor Yellow
        $proceed = Read-HostWithDefault -Prompt "Continue anyway? (y/N)" -Default "N"
        if ($proceed -ne "y" -and $proceed -ne "Y") {
            Write-Host "Aborted. Please mount the drive and retry." -ForegroundColor Red
            exit 1
        }
    }
} else {
    $defaultLocalPath = "C:\ProgramData\mm-ibkr-gateway\storage"
    $StorageBasePath = Read-HostWithDefault -Prompt "Local base path for logs/audit" -Default $defaultLocalPath -Required
}
Write-Host ""

# Step 4: IBKR Gateway Configuration
Write-Host "Step 4: IBKR Gateway Configuration" -ForegroundColor Yellow
$detectedGateway = Find-IBKRGateway
if ($detectedGateway) {
    Write-Host "Detected IBKR Gateway: $detectedGateway"
}
$GatewayPath = Read-HostWithDefault -Prompt "IBKR Gateway installation path" -Default $detectedGateway -Required
$PaperPort = Read-HostWithDefault -Prompt "Paper trading port" -Default "4002"
Write-Host ""

# Step 5: IBKR Credentials
Write-Host "Step 5: IBKR Credentials" -ForegroundColor Yellow
Write-Host "These credentials are for IBKR Gateway auto-login (paper trading)." -ForegroundColor Gray
Write-Host "WARNING: Credentials will be stored in jts.ini (plaintext - IBKR limitation)" -ForegroundColor Yellow
Write-Host ""

$configureCredentials = Read-HostWithDefault -Prompt "Configure IBKR credentials now? (Y/n)" -Default "Y"
if ($configureCredentials -eq "Y" -or $configureCredentials -eq "y") {
    $IBKRUsername = Read-HostWithDefault -Prompt "IBKR Paper Username" -Required
    $IBKRPassword = Read-HostWithDefault -Prompt "IBKR Paper Password" -Required -Secret
} else {
    $IBKRUsername = ""
    $IBKRPassword = ""
    Write-Host "Skipped. Run setup-ibkr-autologin.ps1 later to configure." -ForegroundColor Gray
}
Write-Host ""

# Step 6: Time Window Configuration
Write-Host "Step 6: Time Window Configuration" -ForegroundColor Yellow
Write-Host "Services will only run during this window on specified days."
$RunWindowStart = Read-HostWithDefault -Prompt "Start time (HH:MM, 24-hour)" -Default "04:00"
$RunWindowEnd = Read-HostWithDefault -Prompt "End time (HH:MM, 24-hour)" -Default "20:00"
$RunWindowDays = Read-HostWithDefault -Prompt "Active days (comma-separated)" -Default "Mon,Tue,Wed,Thu,Fri"
$RunWindowTimezone = Read-HostWithDefault -Prompt "Timezone" -Default "America/Toronto"
Write-Host ""

# Step 7: Safety Confirmation
Write-Host "Step 7: Safety Settings" -ForegroundColor Yellow
Write-Host "SAFETY: Orders are DISABLED by default. Paper trading mode only." -ForegroundColor Green
Write-Host "To enable orders later, set ORDERS_ENABLED=true and create the arm file."
$TradingMode = "paper"
$OrdersEnabled = "false"
Write-Host ""

# Create directories
Write-Host "Creating directories..." -ForegroundColor Cyan

# Storage directories
$LogDir = Join-Path $StorageBasePath "logs"
$AuditDbPath = Join-Path $StorageBasePath "audit.db"
$ArmFilePath = Join-Path $StorageBasePath "arm_orders_confirmed.txt"

if (-not (Test-Path $StorageBasePath)) {
    New-Item -ItemType Directory -Path $StorageBasePath -Force | Out-Null
    Write-Host "  Created: $StorageBasePath"
}
if (-not (Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
    Write-Host "  Created: $LogDir"
}

# Secrets directory
if (-not (Test-Path $SecretsDir)) {
    New-Item -ItemType Directory -Path $SecretsDir -Force | Out-Null
    Write-Host "  Created: $SecretsDir"
}

# ProgramData directory for state
$StateDir = "C:\ProgramData\mm-ibkr-gateway"
if (-not (Test-Path $StateDir)) {
    New-Item -ItemType Directory -Path $StateDir -Force | Out-Null
    Write-Host "  Created: $StateDir"
}

# Generate .env file
Write-Host "`nGenerating .env file..." -ForegroundColor Cyan

$envContent = @"
# =============================================================================
# mm-ibkr-gateway Configuration
# Generated by configure.ps1 on $(Get-Date -Format "yyyy-MM-dd HH:mm:ss")
# =============================================================================

# =============================================================================
# SAFETY SETTINGS (DO NOT CHANGE UNLESS YOU UNDERSTAND THE IMPLICATIONS)
# =============================================================================

# Trading mode: paper = simulated, live = REAL MONEY
TRADING_MODE=$TradingMode

# Order placement: false = disabled, true = ENABLED
ORDERS_ENABLED=$OrdersEnabled

# Arm file path (must exist to place orders when ORDERS_ENABLED=true)
ARM_ORDERS_FILE=$ArmFilePath

# Live trading override (required for live trading with orders enabled)
LIVE_TRADING_OVERRIDE_FILE=

# =============================================================================
# NETWORK SETTINGS
# =============================================================================

# API server bind address (LAN IP for Pi access)
API_BIND_HOST=$LanIP

# API server port
API_PORT=$ApiPort

# Pi IP address (for firewall rules)
PI_IP=$PiIP

# =============================================================================
# IBKR CONNECTION SETTINGS
# =============================================================================

# IBKR Gateway host (always localhost for local gateway)
IBKR_GATEWAY_HOST=127.0.0.1

# Paper Trading Connection
PAPER_GATEWAY_PORT=$PaperPort
PAPER_CLIENT_ID=1

# Live Trading Connection (not used in this deployment)
LIVE_GATEWAY_PORT=4001
LIVE_CLIENT_ID=777

# =============================================================================
# TIME WINDOW SETTINGS
# =============================================================================

# Services run only during this window
RUN_WINDOW_START=$RunWindowStart
RUN_WINDOW_END=$RunWindowEnd
RUN_WINDOW_DAYS=$RunWindowDays
RUN_WINDOW_TIMEZONE=$RunWindowTimezone

# =============================================================================
# PATH SETTINGS
# =============================================================================

# Storage base path (local or synced folder)
GDRIVE_BASE_PATH=$StorageBasePath

# Audit database (SQLite)
AUDIT_DB_PATH=$AuditDbPath

# Log file directory
LOG_FILE_PATH=$LogDir

# IBKR Gateway installation path
IBKR_GATEWAY_PATH=$GatewayPath

# =============================================================================
# LOGGING SETTINGS
# =============================================================================

LOG_LEVEL=INFO
LOG_FORMAT=json

# =============================================================================
# API SETTINGS
# =============================================================================

# API key (generated by generate-api-key.ps1)
# API_KEY=

# Request timeout in seconds
API_REQUEST_TIMEOUT=30.0
"@

# Backup existing .env if present
if (Test-Path $EnvFile) {
    $backupPath = "$EnvFile.backup.$(Get-Date -Format 'yyyyMMdd_HHmmss')"
    Copy-Item $EnvFile $backupPath
    Write-Host "  Backed up existing .env to: $backupPath" -ForegroundColor Gray
}

Set-Content -Path $EnvFile -Value $envContent -Encoding UTF8
Write-Host "  Created: $EnvFile" -ForegroundColor Green

# Store IBKR credentials for autologin setup
if ($IBKRUsername -and $IBKRPassword) {
    $credFile = Join-Path $SecretsDir "ibkr_credentials.json"
    $credContent = @{
        username = $IBKRUsername
        password = $IBKRPassword
        timestamp = (Get-Date -Format "o")
    } | ConvertTo-Json
    Set-Content -Path $credFile -Value $credContent -Encoding UTF8
    Write-Host "  Stored credentials for autologin setup: $credFile" -ForegroundColor Gray
    Write-Host "  Run setup-ibkr-autologin.ps1 to configure IBKR Gateway." -ForegroundColor Gray
}

# Summary
Write-Host "`n========================================" -ForegroundColor Green
Write-Host "  Configuration Complete!" -ForegroundColor Green
Write-Host "========================================`n" -ForegroundColor Green

Write-Host "Summary:" -ForegroundColor Cyan
Write-Host "  Repository:      $RepoRoot"
Write-Host "  API Endpoint:    http://${LanIP}:${ApiPort}"
Write-Host "  Pi IP:           $PiIP"
Write-Host "  Storage Path:    $StorageBasePath ($storageLabel)"
Write-Host "  Trading Mode:    $TradingMode"
Write-Host "  Orders Enabled:  $OrdersEnabled"
Write-Host "  Run Window:      $RunWindowDays $RunWindowStart - $RunWindowEnd ($RunWindowTimezone)"

Write-Host "`nNext Steps:" -ForegroundColor Yellow
Write-Host "  1. Run: .\setup-ibkr-autologin.ps1  (configure gateway auto-login)"
Write-Host "  2. Run: .\generate-api-key.ps1     (create API key)"
Write-Host "  3. Run: .\setup-firewall.ps1       (requires admin)"
Write-Host "  4. Run: .\setup-tasks.ps1          (requires admin)"
Write-Host "  5. Run: .\verify.ps1               (validate deployment)"
Write-Host ""
