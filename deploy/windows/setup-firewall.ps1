<#
.SYNOPSIS
    Configures Windows Firewall rules for mm-ibkr-gateway.

.DESCRIPTION
    Creates inbound rules to:
    - Allow API port access from configured clients (allowed_ips in config.json)
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
. (Join-Path $ScriptDir "utils\common.ps1")

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
$config = Import-GatewayConfig
if (-not $config) {
    $configPath = Get-GatewayConfigPath
    Write-Host "ERROR: config.json not found at $configPath. Run configure.ps1 first." -ForegroundColor Red
    exit 1
}
$apiPort = [int](Get-GatewayConfigValue $config "api_port" 8000)
$bindHost = Get-GatewayConfigValue $config "api_bind_host" $null
$allowedEnv = Get-GatewayConfigValue $config "allowed_ips" "127.0.0.1"

Write-Host "Configuration:" -ForegroundColor Gray
Write-Host "  API Port: $apiPort"
Write-Host "  Bind Host: $bindHost"
Write-Host "  ALLOWED_IPS: $allowedEnv"
if ($AdditionalIPs) {
    Write-Host "  Additional IPs: $AdditionalIPs"
}
Write-Host ""

# Build list of allowed IPs
$allowedIPs = @()
# Add default loopback
$allowedIPs += "127.0.0.1"
# Add configured allowed IPs
$allowedIPs += $allowedEnv -split ","
# Add bindHost if it's specific
if ($bindHost -and $bindHost -ne "0.0.0.0") {
    $allowedIPs += $bindHost
}
if ($AdditionalIPs) {
    $allowedIPs += $AdditionalIPs -split ","
}
$allowedIPs = $allowedIPs | ForEach-Object { $_.Trim() } | Where-Object { $_ -ne "" } | Select-Object -Unique

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
Write-Host "To test locally:" -ForegroundColor Gray
Write-Host "  curl http://127.0.0.1:${apiPort}/health" -ForegroundColor White
Write-Host ""
Write-Host "To verify rules:" -ForegroundColor Gray
Write-Host "  Get-NetFirewallRule -DisplayName 'mm-ibkr-gateway*' | Format-List" -ForegroundColor White
