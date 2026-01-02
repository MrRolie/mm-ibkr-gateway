<#$
.SYNOPSIS
    Recreates all mm-ibkr-gateway scheduled tasks after env changes.

.DESCRIPTION
    Deletes existing mm-ibkr-gateway Task Scheduler entries and runs setup-tasks.ps1 -Force.
    Use this after updating .env so Task Scheduler picks up the new settings.

.EXAMPLE
    .\update-tasks.ps1
#>

[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = (Get-Item $ScriptDir).Parent.Parent.FullName

Write-Host "`n=== Updating mm-ibkr-gateway Scheduled Tasks ===" -ForegroundColor Cyan

# Delete existing tasks (ignore errors if they don't exist)
$tasks = @(
    "\mm-ibkr-gateway\IBKR-Gateway-START",
    "\mm-ibkr-gateway\IBKR-Gateway-STOP",
    "\mm-ibkr-gateway\IBKR-API-START",
    "\mm-ibkr-gateway\IBKR-API-STOP",
    "\mm-ibkr-gateway\IBKR-Watchdog",
    "\mm-ibkr-gateway\IBKR-Boot-Reconcile"
)

foreach ($task in $tasks) {
    try {
        schtasks /delete /tn $task /f 2>$null | Out-Null
        Write-Host "Removed task: $task" -ForegroundColor Gray
    } catch {
        # ignore
    }
}

# Recreate tasks with current .env settings
Write-Host "Recreating tasks with setup-tasks.ps1 -Force" -ForegroundColor Gray
& (Join-Path $ScriptDir "setup-tasks.ps1") -Force

Write-Host "`n=== Task Update Complete ===" -ForegroundColor Green
