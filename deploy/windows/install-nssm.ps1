<#
Requires: Run as Administrator

Purpose: Download and install NSSM (Non-Sucking Service Manager) and add it to PATH.
#>

param(
    [string]$InstallPath = "C:\\Program Files\\NSSM"
)

$ErrorActionPreference = 'Stop'

Write-Host '=== NSSM Installation ===' -ForegroundColor Cyan
Write-Host ''

# Check if NSSM already installed
$nssmExe = Get-Command nssm -ErrorAction SilentlyContinue
if ($nssmExe) {
    Write-Host ('NSSM already installed at: {0}' -f $nssmExe.Source) -ForegroundColor Green
    try { & nssm version } catch {}
    exit 0
}

# Configuration
$NssmVersion = '2.24'
$NssmUrl = "https://nssm.cc/release/nssm-$NssmVersion.zip"
$TempDir = Join-Path $env:TEMP 'nssm-install'
$ZipFile = Join-Path $TempDir 'nssm.zip'

Write-Host ("Installing NSSM {0}..." -f $NssmVersion) -ForegroundColor Yellow
Write-Host ("Download URL: {0}" -f $NssmUrl)
Write-Host ("Install Path: {0}" -f $InstallPath)
Write-Host ''

# Create temp directory
if (Test-Path $TempDir) { Remove-Item -Recurse -Force $TempDir }
New-Item -ItemType Directory -Path $TempDir | Out-Null

# Download NSSM
Write-Host 'Downloading NSSM...' -NoNewline
try {
    Invoke-WebRequest -Uri $NssmUrl -OutFile $ZipFile -UseBasicParsing
    Write-Host ' OK' -ForegroundColor Green
} catch {
    Write-Host ' FAIL' -ForegroundColor Red
    Write-Host ("Error: Failed to download NSSM: {0}" -f $_) -ForegroundColor Red
    exit 1
}

# Extract archive
Write-Host 'Extracting archive...' -NoNewline
try {
    Expand-Archive -Path $ZipFile -DestinationPath $TempDir -Force
    Write-Host ' OK' -ForegroundColor Green
} catch {
    Write-Host ' FAIL' -ForegroundColor Red
    Write-Host ("Error: Failed to extract NSSM: {0}" -f $_) -ForegroundColor Red
    exit 1
}

# Determine architecture
$Arch = if ([Environment]::Is64BitOperatingSystem) { 'win64' } else { 'win32' }
$NssmExePath = Join-Path (Join-Path $TempDir "nssm-$NssmVersion") (Join-Path $Arch 'nssm.exe')

if (-not (Test-Path $NssmExePath)) {
    Write-Host ("Error: NSSM executable not found at expected path: {0}" -f $NssmExePath) -ForegroundColor Red
    exit 1
}

# Create install directory
Write-Host 'Creating install directory...' -NoNewline
if (-not (Test-Path $InstallPath)) {
    New-Item -ItemType Directory -Path $InstallPath -Force | Out-Null
}
Write-Host ' OK' -ForegroundColor Green

# Copy NSSM to install location
Write-Host 'Installing NSSM...' -NoNewline
$DestExe = Join-Path $InstallPath 'nssm.exe'
Copy-Item -Path $NssmExePath -Destination $DestExe -Force
Write-Host ' OK' -ForegroundColor Green

# Add to PATH if not already present
Write-Host 'Updating system PATH...' -NoNewline
$CurrentMachinePath = [Environment]::GetEnvironmentVariable('Path', 'Machine')
if ($null -eq $CurrentMachinePath) { $CurrentMachinePath = '' }
if ($CurrentMachinePath -notlike ("*{0}*" -f $InstallPath)) {
    $NewPath = if ([string]::IsNullOrWhiteSpace($CurrentMachinePath)) { $InstallPath } else { "$CurrentMachinePath;$InstallPath" }
    try {
        [Environment]::SetEnvironmentVariable('Path', $NewPath, 'Machine')
    } catch {
        Write-Host ' (could not update Machine PATH, continuing)' -ForegroundColor Yellow
    }
    # Update current session PATH so nssm is immediately available
    $env:Path = if ([string]::IsNullOrWhiteSpace($env:Path)) { $InstallPath } else { "$env:Path;$InstallPath" }
    Write-Host ' OK' -ForegroundColor Green
} else {
    Write-Host ' (already in PATH)' -ForegroundColor Gray
}

# Cleanup temp files
Write-Host 'Cleaning up...' -NoNewline
Remove-Item -Recurse -Force $TempDir
Write-Host ' OK' -ForegroundColor Green

# Verify installation
Write-Host ''
Write-Host '=== Verification ===' -ForegroundColor Cyan
Write-Host ("NSSM Location: {0}" -f $DestExe)
try { & $DestExe version } catch {}

Write-Host ''
Write-Host 'NSSM installation complete!' -ForegroundColor Green
Write-Host ''
Write-Host 'Next steps:' -ForegroundColor Yellow
Write-Host '  1. Run install-service.ps1 to create the signal listener service'
Write-Host '  2. Run setup-firewall.ps1 to configure network access'
Write-Host ''
