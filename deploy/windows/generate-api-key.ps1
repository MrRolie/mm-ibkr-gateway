<#
.SYNOPSIS
    Generates a secure random API key for mm-ibkr-gateway.

.DESCRIPTION
    Creates a cryptographically secure 32-byte key, base64 encoded.
    Stores in secrets/api_key.txt and updates .env file.

.EXAMPLE
    .\generate-api-key.ps1
#>

[CmdletBinding()]
param(
    [switch]$Force
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = (Get-Item $ScriptDir).Parent.Parent.FullName
$SecretsDir = Join-Path $RepoRoot "secrets"
$ApiKeyFile = Join-Path $SecretsDir "api_key.txt"
$EnvFile = Join-Path $RepoRoot ".env"

Write-Host "`n=== API Key Generator ===" -ForegroundColor Cyan

# Check if key exists
if ((Test-Path $ApiKeyFile) -and -not $Force) {
    Write-Host "API key already exists at: $ApiKeyFile" -ForegroundColor Yellow
    $existing = Get-Content $ApiKeyFile -Raw
    Write-Host "Current key: $($existing.Substring(0, 8))..." -ForegroundColor Gray
    $overwrite = Read-Host "Overwrite? (y/N)"
    if ($overwrite -ne "y" -and $overwrite -ne "Y") {
        Write-Host "Keeping existing key." -ForegroundColor Green
        exit 0
    }
}

# Ensure secrets directory exists
if (-not (Test-Path $SecretsDir)) {
    New-Item -ItemType Directory -Path $SecretsDir -Force | Out-Null
}

# Generate secure random key (32 bytes = 256 bits)
$bytes = New-Object byte[] 32
$rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
$rng.GetBytes($bytes)
$apiKey = [Convert]::ToBase64String($bytes)

# Save to file
Set-Content -Path $ApiKeyFile -Value $apiKey -NoNewline -Encoding UTF8
Write-Host "API key saved to: $ApiKeyFile" -ForegroundColor Green

# Update .env file if it exists
if (Test-Path $EnvFile) {
    $envContent = Get-Content $EnvFile -Raw
    
    if ($envContent -match "^API_KEY=") {
        # Replace existing
        $envContent = $envContent -replace "^API_KEY=.*$", "API_KEY=$apiKey"
    } elseif ($envContent -match "^# API_KEY=") {
        # Uncomment and set
        $envContent = $envContent -replace "^# API_KEY=.*$", "API_KEY=$apiKey"
    } else {
        # Append
        $envContent += "`nAPI_KEY=$apiKey"
    }
    
    Set-Content -Path $EnvFile -Value $envContent -Encoding UTF8
    Write-Host "Updated .env file with API key" -ForegroundColor Green
}

# Create .gitignore entry if needed
$gitignore = Join-Path $RepoRoot ".gitignore"
if (Test-Path $gitignore) {
    $gitignoreContent = Get-Content $gitignore -Raw
    if ($gitignoreContent -notmatch "secrets/") {
        Add-Content -Path $gitignore -Value "`n# Secrets`nsecrets/"
        Write-Host "Added secrets/ to .gitignore" -ForegroundColor Gray
    }
}

Write-Host "`n=== IMPORTANT ===" -ForegroundColor Yellow
Write-Host "Copy this API key to your Raspberry Pi configuration:" -ForegroundColor Yellow
Write-Host ""
Write-Host "  $apiKey" -ForegroundColor White
Write-Host ""
Write-Host "On the Pi, set: IBKR_API_KEY=`"$apiKey`"" -ForegroundColor Gray
Write-Host ""
