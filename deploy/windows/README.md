# Windows Execution Node Deployment Guide

## Overview

This guide deploys the **mm-ibkr-gateway** as a production execution node on a Windows x86_64 laptop. The node runs:

- **IBKR Gateway** (paper trading, auto-login)
- **FastAPI REST API** (LAN-bound, API key protected)
- **Watchdog automation** (health checks, auto-restart)
- **Time-windowed operation** (weekdays 4:00 AM - 8:00 PM by default)

A Raspberry Pi on the same LAN connects to this node to execute trades.

---

## Architecture

```text
┌─────────────────────────────────────────────────────────────────┐
│                    Windows Laptop (Execution Node)              │
│                                                                 │
│  ┌─────────────────┐     ┌─────────────────┐                    │
│  │  IBKR Gateway   │◄────│  FastAPI REST   │◄──── LAN (Pi)      │
│  │  (port 4002)    │     │  (port 8000)    │                    │
│  └─────────────────┘     └─────────────────┘                    │
│           │                       │                             │
│           ▼                       ▼                             │
│  ┌─────────────────────────────────────────┐                    │
│  │         Google Drive Sync Folder        │                    │
│  │  - audit.db (SQLite)                    │                    │
│  │  - logs/                                │                    │
│  └─────────────────────────────────────────┘                    │
│                                                                 │
│  ┌─────────────────────────────────────────┐                    │
│  │         Task Scheduler                  │                    │
│  │  - Start Gateway (04:00 weekdays)       │                    │
│  │  - Start API (04:02 weekdays)           │                    │
│  │  - Stop API (20:00 weekdays)            │                    │
│  │  - Stop Gateway (20:01 weekdays)        │                    │
│  │  - Watchdog (every 2 min during window) │                    │
│  │  - Boot Reconcile (on startup)          │                    │
│  └─────────────────────────────────────────┘                    │
└─────────────────────────────────────────────────────────────────┘
```

---

## Prerequisites

### Required Software

1. **IBKR Gateway** (not TWS) - Download from [Interactive Brokers](https://www.interactivebrokers.com/en/trading/ibgateway-stable.php)
2. **Python 3.11+** with Poetry installed
3. **Google Drive for Desktop** with sync enabled
4. **Git** (for cloning/updating the repo)

### Required Access

- IBKR paper trading account credentials
- Administrator access (for Task Scheduler and Firewall)
- Static LAN IP configured on the laptop

### Network Requirements

- Laptop and Pi on same LAN subnet
- Laptop has static IP (e.g., 192.168.1.100)
- Pi IP known (e.g., 192.168.1.50)

---

## Safety Model

This deployment preserves ALL existing safety mechanisms:

| Safety Layer | Default | Description |
| -------------- | --------- | ------------- |
| `TRADING_MODE` | `paper` | Paper trading only (port 4002) |
| `ORDERS_ENABLED` | `false` | Orders blocked by default |
| Override File | Not present | Required for live+orders |
| Firewall | Pi IP only | LAN-restricted access |
| API Key | Required | Authentication enforced |
| Time Window | Weekdays 4-8 | Services only run during market hours |

**To enable order placement:**

1. Set `ORDERS_ENABLED=true` in `.env`
2. Create the arm file: `arm_orders_confirmed.txt` in the configured path

**Live trading is NOT enabled by this deployment.** Additional steps (documented separately) are required.

---

## Quick Start

### 1. Run Configuration Script

Open PowerShell **as Administrator** and run:

```powershell
cd "C:\Users\mikae\Coding Projects\mm-ibkr-gateway\deploy\windows"
.\configure.ps1
```

This interactive script will:

- Detect your LAN IP
- Ask for Pi IP, Google Drive path, IBKR credentials
- Generate `.env` file with all settings
- Create directories in Google Drive

### 2. Set Up IBKR Gateway Auto-Login

```powershell
.\setup-ibkr-autologin.ps1
```

This configures IBKR Gateway's `jts.ini` for automatic paper login.

### 3. Create Firewall Rules

```powershell
.\setup-firewall.ps1
```

Restricts API port access to Pi IP and localhost only.

### 4. Create Scheduled Tasks

```powershell
.\setup-tasks.ps1
```

Creates all Task Scheduler jobs for automated operation.

### 5. Generate API Key

```powershell
.\generate-api-key.ps1
```

Generates a secure API key and saves to `secrets/api_key.txt`.
**Copy this key to your Pi's configuration.**

### 6. Verify Deployment

```powershell
.\verify.ps1
```

Runs all health checks and displays status.

---

## Configuration Reference

### Environment Variables

Located in repo root `.env` file:

#### Core Settings

| Variable | Default | Description |
| ---------- | --------- | ------------- |
| `TRADING_MODE` | `paper` | `paper` or `live` |
| `ORDERS_ENABLED` | `false` | Enable order placement |
| `API_KEY` | (generated) | API authentication key |

#### Network Settings

| Variable | Default | Description |
| ---------- | --------- | ------------- |
| `API_BIND_HOST` | (auto-detect) | IP to bind API server |
| `API_PORT` | `8000` | API server port |
| `PAPER_GATEWAY_PORT` | `4002` | IBKR Gateway paper port |
| `PI_IP` | (configured) | Allowed client IP |

#### Time Window Settings

| Variable | Default | Description |
| ---------- | --------- | ------------- |
| `RUN_WINDOW_START` | `04:00` | Daily start time (HH:MM) |
| `RUN_WINDOW_END` | `20:00` | Daily end time (HH:MM) |
| `RUN_WINDOW_DAYS` | `Mon,Tue,Wed,Thu,Fri` | Active days |
| `RUN_WINDOW_TIMEZONE` | `America/Toronto` | Timezone for schedule |

#### Path Settings

| Variable | Default | Description |
| ---------- | --------- | ------------- |
| `GDRIVE_BASE_PATH` | (configured) | Google Drive sync folder |
| `AUDIT_DB_PATH` | `{GDRIVE}/audit.db` | Audit database location |
| `LOG_FILE_PATH` | `{GDRIVE}/logs/` | Log file directory |
| `IBKR_GATEWAY_PATH` | (configured) | IBKR Gateway install path |

---

## Scripts Reference

### Primary Scripts

| Script | Purpose | Admin Required |
| -------- | --------- | ------------- |
| `configure.ps1` | Interactive setup wizard | No |
| `setup-tasks.ps1` | Create scheduled tasks | Yes |
| `setup-firewall.ps1` | Create firewall rules | Yes |
| `setup-ibkr-autologin.ps1` | Configure IBKR auto-login | No |
| `generate-api-key.ps1` | Generate secure API key | No |
| `verify.ps1` | Validate deployment | No |

### Operational Scripts

| Script | Purpose |
| -------- | --------- |
| `start-gateway.ps1` | Start IBKR Gateway |
| `stop-gateway.ps1` | Stop IBKR Gateway |
| `start-api.ps1` | Start FastAPI server |
| `stop-api.ps1` | Stop FastAPI server |
| `watchdog.ps1` | Health monitor (runs via Task Scheduler) |
| `healthcheck.ps1` | Manual health check |
| `status.ps1` | Show current status |

---

## Task Scheduler Tasks

Created by `setup-tasks.ps1`:

| Task Name | Trigger | Action |
| --------- | --------- | -------- |
| `IBKR-Gateway-START` | Weekdays 04:00 | Start IBKR Gateway |
| `IBKR-API-START` | Weekdays 04:02 | Start FastAPI server |
| `IBKR-API-STOP` | Weekdays 20:00 | Stop FastAPI server |
| `IBKR-Gateway-STOP` | Weekdays 20:01 | Stop IBKR Gateway |
| `IBKR-Watchdog` | Every 2 min (during window) | Health check + restart |
| `IBKR-Boot-Reconcile` | At system startup | Ensure correct state |

**Task Configuration:**

- Run whether user is logged on or not: **Yes**
- Run with highest privileges: **Yes**
- Stop if running longer than: **1 hour** (except watchdog)

---

## Watchdog Behavior

The watchdog script (`watchdog.ps1`) runs every 2 minutes during the run window:

1. **Check Time Window** - Exit if outside run window
2. **Check IBKR Gateway** - Verify process running and port listening
3. **Check API Health** - Call `/health` endpoint
4. **Auto-Restart Logic:**
   - If API down but Gateway up → Restart API only
   - If Gateway down → Restart Gateway, then API
5. **Backoff Protection:**
   - Max 5 restarts per hour per service
   - Exponential backoff between retries
   - Log critical error if limit exceeded

Outside the run window, watchdog ensures services are **stopped**.

---

## Troubleshooting

### Check Service Status

```powershell
.\status.ps1
```

### View Recent Logs

```powershell
Get-Content "$env:GDRIVE_BASE_PATH\logs\api.log" -Tail 100
```

### Manual Service Control

```powershell
# Start manually (respects time window)
.\start-gateway.ps1
.\start-api.ps1

# Force start (ignores time window - for testing)
.\start-gateway.ps1 -Force
.\start-api.ps1 -Force

# Stop manually
.\stop-api.ps1
.\stop-gateway.ps1
```

### Reset Restart Counters

```powershell
Remove-Item "$env:ProgramData\mm-ibkr-gateway\restart_state.json"
```

### Re-run Setup

```powershell
# Regenerate .env
.\configure.ps1

# Recreate tasks (removes existing first)
.\setup-tasks.ps1 -Force

# Update firewall rules
.\setup-firewall.ps1 -Force
```

---

## Security Considerations

### Credential Storage

IBKR Gateway credentials are stored in `jts.ini` in **plaintext** (IBKR limitation).

**Recommendations:**

1. Use a dedicated IBKR paper account for this deployment
2. Enable Windows EFS encryption on the Jts folder
3. Ensure laptop has full-disk encryption (BitLocker)
4. Never commit `jts.ini` to version control

### API Key

The API key is stored in `secrets/api_key.txt` outside the repo.

**Recommendations:**

1. Copy to Pi securely (not via email/chat)
2. Rotate periodically using `generate-api-key.ps1`
3. File is excluded from git via `.gitignore`

### Firewall

The firewall rule restricts API access to:

- Pi IP (configured during setup)
- Localhost (127.0.0.1)

**To allow additional IPs:**

```powershell
.\setup-firewall.ps1 -AdditionalIPs "192.168.1.51,192.168.1.52"
```

---

## Appendix: Manual Steps After Deployment

After running all setup scripts, complete these manual steps:

### 1. Test IBKR Gateway Login

Run IBKR Gateway manually once to verify auto-login works:

```powershell
& "$env:IBKR_GATEWAY_PATH\ibgateway.exe"
```

### 2. Copy API Key to Pi

The API key is in `secrets/api_key.txt`. Copy it to your Pi's environment:

```bash
# On Pi
export IBKR_API_KEY="<paste-key-here>"
```

### 3. Verify Pi Connectivity

From the Pi, test connectivity:

```bash
curl -H "X-API-Key: $IBKR_API_KEY" http://<laptop-ip>:8000/health
```

### 4. Enable Orders (When Ready)

When ready to enable order placement:

```powershell
# Edit .env
$env:ORDERS_ENABLED = "true"

# Create arm file
New-Item -Path "$env:GDRIVE_BASE_PATH\arm_orders_confirmed.txt" -ItemType File
```

### 5. Monitor First Full Day

Watch the first full trading day:

```powershell
# In one terminal
Get-Content "$env:GDRIVE_BASE_PATH\logs\api.log" -Wait

# In another terminal
.\status.ps1
```

---

## Version History

| Version | Date | Changes |
| --------- | ------ | --------- |
| 1.0.0 | 2024-12-30 | Initial deployment guide |
