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
│  │         Storage Sync Folder (optional)  │                    │
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
3. **Optional: Google Drive for Desktop** (if using synced storage)
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
- Ask for Pi IP, storage path (local or synced), IBKR credentials
- Generate `.env` file with all settings
- Create directories in the chosen storage path

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
| `GDRIVE_BASE_PATH` | (configured) | Storage base path (local or synced folder) |
| `AUDIT_DB_PATH` | `{BASE}/audit.db` | Audit database location |
| `LOG_FILE_PATH` | `{BASE}/logs/` | Log file directory |
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

### Manual Task Creation (Alternative to setup-tasks.ps1)

If the automated script fails or you prefer manual setup:

1. **Open Task Scheduler** (`taskschd.msc` or Start → Task Scheduler)

2. **Create Task Folder:**
   - Right-click "Task Scheduler Library" → New Folder
   - Name: `mm-ibkr-gateway`

3. **Create Each Task:**

   For each task below, right-click the `mm-ibkr-gateway` folder → Create Task:

   #### IBKR-Gateway-START

   - **General Tab:**
     - Name: `IBKR-Gateway-START`
     - Description: `Start IBKR Gateway at market open`
     - User account: Your Windows account
     - ☑ Run whether user is logged on or not
     - ☑ Run with highest privileges
   - **Triggers Tab:**
     - New → Weekly
     - Days: Monday, Tuesday, Wednesday, Thursday, Friday
     - Start time: `04:00:00`
     - ☑ Enabled
   - **Actions Tab:**
     - New → Start a program
     - Program: `powershell.exe`
     - Arguments: `-ExecutionPolicy Bypass -NoProfile -File "C:\Users\mikae\Coding Projects\mm-ibkr-gateway\deploy\windows\start-gateway.ps1"`
   - **Settings Tab:**
     - ☑ Allow task to be run on demand
     - ☐ Stop the task if it runs longer than: 1 hour

   #### IBKR-API-START

   - Same as Gateway-START but:
     - Name: `IBKR-API-START`
     - Description: `Start mm-ibkr-gateway API server`
     - Start time: `04:02:00`
     - Script: `start-api.ps1`

   #### IBKR-API-STOP

   - **General Tab:** Same as above
     - Name: `IBKR-API-STOP`
     - Description: `Stop mm-ibkr-gateway API server`
   - **Triggers Tab:**
     - Weekly, Mon-Fri, `20:00:00`
   - **Actions Tab:**
     - Script: `stop-api.ps1`
   - **Settings Tab:**
     - Stop after: 5 minutes

   #### IBKR-Gateway-STOP

   - Same as API-STOP but:
     - Name: `IBKR-Gateway-STOP`
     - Description: `Stop IBKR Gateway after market close`
     - Start time: `20:01:00`
     - Script: `stop-gateway.ps1`

   #### IBKR-Watchdog

   - **General Tab:** Same as above
     - Name: `IBKR-Watchdog`
     - Description: `Health check and auto-restart services`
   - **Triggers Tab:**
     - New → On a schedule → Daily
     - Recur every: 1 day
     - Advanced: ☑ Repeat task every: `2 minutes`, For a duration of: `Indefinitely`
   - **Actions Tab:**
     - Script: `watchdog.ps1`
   - **Settings Tab:**
     - ☑ If the task is already running: Do not start a new instance

   #### IBKR-Boot-Reconcile

   - **General Tab:** Same as above
     - Name: `IBKR-Boot-Reconcile`
     - Description: `Ensure correct state after system boot`
   - **Triggers Tab:**
     - New → At startup
     - Delay for: `1 minute`
   - **Actions Tab:**
     - Script: `boot-reconcile.ps1`
   - **Settings Tab:**
     - Stop after: 10 minutes

4. **Test Tasks:**

   ```powershell
   # Test start tasks
   schtasks /run /tn "\mm-ibkr-gateway\IBKR-Gateway-START"
   schtasks /run /tn "\mm-ibkr-gateway\IBKR-API-START"
   
   # Check status
   .\status.ps1
   ```

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

### Task Scheduler Script Issues

If `setup-tasks.ps1` fails with "system cannot find the file specified":

1. **Verify the script created the folder:**
   ```powershell
   Test-Path "C:\Windows\System32\Tasks\mm-ibkr-gateway"
   ```

2. **Create the folder manually if needed:**
   ```powershell
   New-Item -ItemType Directory -Path "C:\Windows\System32\Tasks\mm-ibkr-gateway" -Force
   ```

3. **Re-run the setup script:**
   ```powershell
   .\setup-tasks.ps1 -Force
   ```

4. **If still failing, use manual task creation** (see section above)

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

## Auto-restart & IBAutomater (new)

- `start-gateway.ps1` launches IB Gateway with the IBAutomater Java agent for UI automation (login, auto-restart toggle, popup handling). It reads credentials from `secrets/ibkr_credentials.json` or `IBKR_USERNAME/IBKR_PASSWORD`.
- On first run, launch with a visible window to confirm auto-login and that **Configuration → Lock and Exit → Auto restart** is selected:
  ```powershell
  .\start-gateway.ps1 -ShowWindow -Force
  ```
- Daily stop tasks are now optional. Set `STOP_TASKS_ENABLED=true` in `.env` before running `setup-tasks.ps1` if you want daily API/Gateway stop tasks; otherwise they are skipped.

## Enabling Orders (paper) and Switching to Live

- Orders stay blocked by default (`ORDERS_ENABLED=false`). To allow orders in paper:
  1. Set `ORDERS_ENABLED=true` in `.env`.
  2. Ensure the arm file exists at `ARM_ORDERS_FILE` (acts as a physical guard).
  3. Restart the API.
- To switch to live trading:
  1. Set `TRADING_MODE=live` in `.env`.
  2. Set `ORDERS_ENABLED=true` only if you intend to place live orders.
  3. Create a live trading override file at `LIVE_TRADING_OVERRIDE_FILE` (a second guard).
  4. Ensure firewall rules, credentials, and IBKR live ports/IDs (`LIVE_GATEWAY_PORT`, `LIVE_CLIENT_ID`) are correct.
  5. Restart Gateway and API. Verify via `.\status.ps1` and health check that `trading_mode` reports `live` before placing any orders.

---

## Version History

| Version | Date | Changes |
| --------- | ------ | --------- |
| 1.0.0 | 2024-12-30 | Initial deployment guide |
