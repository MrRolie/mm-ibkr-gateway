<#
.SYNOPSIS
    Configures Windows Firewall rules for mm-ibkr-gateway.

.DESCRIPTION
    Creates inbound rules to:
    - Allow API port access from Pi IP
    - Allow API port access from localhost
    - Block API port from all other sources

.PARAMETER Force
    Remove and recreate existing rules.

.PARAMETER AdditionalIPs
    Comma-separated list of additional IPs to allow.

.EXAMPLE
    .\setup-firewall.ps1
    .\setup-firewall.ps1 -AdditionalIPs "192.168.1.51,192.168.1.52"
#>

[CmdletBinding()]
param(
    [switch]$Force,
    [string]$AdditionalIPs
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = (Get-Item $ScriptDir).Parent.Parent.FullName

# Source common functions
. (Join-Path $ScriptDir "lib\common.ps1")

Write-Host "`n=== Windows Firewall Setup ===" -ForegroundColor Cyan

# Check admin rights
if (-not (Test-IsAdmin)) {
    Write-Host "ERROR: This script requires administrator privileges." -ForegroundColor Red
    Write-Host "Please run PowerShell as Administrator and try again." -ForegroundColor Yellow
    exit 1
}

# Load environment
Import-EnvFile -EnvFilePath (Join-Path $RepoRoot ".env")

# Get configuration
$apiPort = if ($env:API_PORT) { [int]$env:API_PORT } else { 8000 }
$piIP = $env:PI_IP
$bindHost = $env:API_BIND_HOST

if (-not $piIP) {
    Write-Host "ERROR: PI_IP not configured. Run configure.ps1 first." -ForegroundColor Red
    exit 1
}

Write-Host "Configuration:" -ForegroundColor Gray
Write-Host "  API Port: $apiPort"
Write-Host "  Pi IP: $piIP"
Write-Host "  Bind Host: $bindHost"
if ($AdditionalIPs) {
    Write-Host "  Additional IPs: $AdditionalIPs"
}
Write-Host ""

# Build list of allowed IPs
$allowedIPs = @("127.0.0.1", $piIP)
if ($bindHost -and $bindHost -ne "0.0.0.0") {
    $allowedIPs += $bindHost
}
if ($AdditionalIPs) {
    $allowedIPs += $AdditionalIPs -split ","
}
$allowedIPs = $allowedIPs | Select-Object -Unique

Write-Host "Allowed IPs: $($allowedIPs -join ', ')" -ForegroundColor Gray
Write-Host ""

# Rule names
$ruleName = "mm-ibkr-gateway API"
$ruleNameBlock = "mm-ibkr-gateway API Block"

# Remove existing rules if -Force
if ($Force) {
    Write-Host "Removing existing rules..." -ForegroundColor Gray
    Get-NetFirewallRule -DisplayName "$ruleName*" -ErrorAction SilentlyContinue | Remove-NetFirewallRule
    Get-NetFirewallRule -DisplayName "$ruleNameBlock*" -ErrorAction SilentlyContinue | Remove-NetFirewallRule
}

# Check if rules exist
$existingRules = Get-NetFirewallRule -DisplayName "$ruleName*" -ErrorAction SilentlyContinue
if ($existingRules -and -not $Force) {
    Write-Host "Firewall rules already exist. Use -Force to recreate." -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Existing rules:" -ForegroundColor Gray
    $existingRules | Format-Table DisplayName, Enabled, Direction, Action -AutoSize
    exit 0
}

Write-Host "Creating firewall rules..." -ForegroundColor Cyan

# Create allow rules for each IP
foreach ($ip in $allowedIPs) {
    $displayName = "$ruleName - Allow $ip"
    
    try {
        New-NetFirewallRule `
            -DisplayName $displayName `
            -Description "Allow mm-ibkr-gateway API access from $ip" `
            -Direction Inbound `
            -Protocol TCP `
            -LocalPort $apiPort `
            -RemoteAddress $ip `
            -Action Allow `
            -Profile Any `
            -Enabled True | Out-Null
        
        Write-Host "  Created: $displayName" -ForegroundColor Green
    } catch {
        Write-Host "  Error creating rule for $ip : $_" -ForegroundColor Red
    }
}

# Create block rule for all other traffic to API port
try {
    New-NetFirewallRule `
        -DisplayName "$ruleNameBlock - Block All Other" `
        -Description "Block all other access to mm-ibkr-gateway API port" `
        -Direction Inbound `
        -Protocol TCP `
        -LocalPort $apiPort `
        -Action Block `
        -Profile Any `
        -Enabled True | Out-Null
    
    Write-Host "  Created: Block rule for port $apiPort" -ForegroundColor Green
} catch {
    Write-Host "  Error creating block rule: $_" -ForegroundColor Red
}

Write-Host "`n=== Firewall Setup Complete ===" -ForegroundColor Green
Write-Host ""

# Show final rules
Write-Host "Active Firewall Rules:" -ForegroundColor Cyan
Get-NetFirewallRule -DisplayName "mm-ibkr-gateway*" | 
    Format-Table DisplayName, Enabled, Direction, Action -AutoSize

Write-Host ""
Write-Host "To test from Pi:" -ForegroundColor Gray
Write-Host "  curl http://${bindHost}:${apiPort}/health" -ForegroundColor White
Write-Host ""
Write-Host "To verify rules:" -ForegroundColor Gray
Write-Host "  Get-NetFirewallRule -DisplayName 'mm-ibkr-gateway*' | Format-List" -ForegroundColor White
