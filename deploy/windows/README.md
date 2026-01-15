# Windows Execution Node Deployment Guide

## Overview

This guide deploys the **mm-ibkr-gateway** as a production execution node on a Windows x86_64 laptop. The node runs:

- **IBKR Gateway** (paper trading, auto-login, Windows service)
- **FastAPI REST API** (LAN-bound, API key protected, Windows service)
- **NSSM service management** (auto-start on boot, auto-restart on failure)
- **Time-windowed operation** (API enforces window internally, returns 503 outside hours)
- **mm-control integration** (centralized trading control via guard file + toggle store)

A client on the same LAN connects to this node to execute trades.

---

## Architecture

```text
┌─────────────────────────────────────────────────────────────────┐
│                    Windows Laptop (Execution Node)              │
│                                                                 │
│  ┌─────────────────┐     ┌─────────────────┐                    │
│  │  IBKR Gateway   │◄────│  FastAPI REST   │◄──── LAN (Pi)      │
│  │  (port 4002)    │     │  (port 8000)    │                    │
│  │  NSSM Service   │     │  NSSM Service   │                    │
│  └─────────────────┘     └─────────────────┘                    │
│           │                       │                             │
│           ▼                       ▼                             │
│  ┌─────────────────────────────────────────┐                    │
│  │         Storage (ProgramData)           │                    │
│  │  - audit.db (SQLite)                    │                    │
│  │  - logs/                                │                    │
│  └─────────────────────────────────────────┘                    │
│                                                                 │
│  ┌─────────────────────────────────────────┐                    │
│  │         mm-control                      │                    │
│  │  - TRADING_DISABLED (guard file)        │                    │
│  │  - toggles.json (with TTL)              │                    │
│  │  - control.log (audit)                  │                    │
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
- Administrator access (for NSSM service installation and Firewall)
- Static LAN IP configured on the laptop

### Network Requirements

- Laptop and client on same LAN subnet
- Laptop has static IP (e.g., 192.168.1.100)
- Client IP known (e.g., 192.168.1.50)

---

## Safety Model

This deployment preserves ALL existing safety mechanisms:

| Safety Layer | Default | Description |
| -------------- | --------- | ------------- |
| `TRADING_MODE` | `paper` | Paper trading only (port 4002) |
| `ORDERS_ENABLED` | `false` | Orders blocked by default |
| Override File | Not present | Required for live+orders |
| Firewall | Allowed IPs only | LAN-restricted access |
| API Key | Required | Authentication enforced |
| Time Window | Weekdays 4-8 | Services only run during market hours |

**To enable order placement:**

1. Set `ORDERS_ENABLED=true` in `.env`
2. Create the arm file: `arm_orders_confirmed.txt` in the configured path

**Live trading is NOT enabled by this deployment.** Additional steps (documented separately) are required.

---

## Quick Start

### 1. Run Configuration Script

Open PowerShell and run:

```powershell
cd "C:\Users\mikae\Coding Projects\mm-ibkr-gateway\deploy\windows"
.\configure.ps1
```

This interactive script will:

- Detect your LAN IP
- Ask for allowed client IPs, storage path, IBKR credentials, time window, and mm-control settings
- Create a Python virtual environment and install required packages
- Generate `.env` file with all settings and create required directories

### 2. Set Up IBKR Gateway Auto-Login with IBAutomater

```powershell
.\setup-ibkr-autologin.ps1
```

This script:
- Configures `jts.ini` with credentials for automatic paper trading login
- Sets up IBAutomater Java agent for UI automation and auto-restart
- Copies `IBAutomater.jar` to state directory
- Updates `ibgateway.vmoptions` to enable the Java agent
- **Must run before installing Gateway service**

### 3. Create Firewall Rules (Admin Required)

```powershell
# Run as Administrator
.\setup-firewall.ps1
```

Opens firewall rules for API port (8000) and IBKR Gateway port (4002/4001).

### 4. Install NSSM Service Manager (Admin Required)

```powershell
# Run as Administrator
.\install-nssm.ps1
```

Downloads and installs NSSM (Non-Sucking Service Manager) for Windows service management.

### 5. Install NSSM Services (Admin Required)

```powershell
# Run as Administrator
.\install-api-service.ps1
.\install-gateway-service.ps1
```

Creates `mm-ibkr-api` and `mm-ibkr-gateway` Windows services with:
- Auto-start on boot
- Auto-restart on failure (5s delay)
- Log rotation at 10MB
- Environment variables loaded from `.env`

**Note:** Services will be in Stopped state after installation.

### 6. Generate API Key

```powershell
.\generate-api-key.ps1
```

Generates a secure API key. Copy the output to your client configuration.

### 7. Start Services

```powershell
Start-Service -Name mm-ibkr-api
Start-Service -Name mm-ibkr-gateway

# Verify both are running
Get-Service -Name mm-ibkr-api, mm-ibkr-gateway
```

Or services will auto-start on next system boot.

### 8. Verify Deployment

```powershell
.\verify.ps1
```

Runs all health checks and reports status. Check logs if any tests fail.

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
| `ALLOWED_IPS` | `127.0.0.1` | Comma-separated list of allowed remote IPs/CIDR for inbound API connections |

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
| `DATA_STORAGE_DIR` | (configured) | Base storage directory (ProgramData recommended) |
| `AUDIT_DB_PATH` | `{BASE}/audit.db` | Audit database location |
| `LOG_DIR` | `{BASE}/logs/` | Log directory |
| `IBKR_GATEWAY_PATH` | (configured) | IBKR Gateway install path |

---

## Scripts Reference

### Primary Scripts

| Script | Purpose | Admin Required |
| -------- | --------- | ------------- |
| `configure.ps1` | Interactive setup wizard | No |
| `install-nssm.ps1` | Install NSSM service manager | Yes |
| `install-api-service.ps1` | Install API as Windows service | Yes |
| `install-gateway-service.ps1` | Install Gateway as Windows service | Yes |
| `setup-firewall.ps1` | Create firewall rules | Yes |
| `setup-ibkr-autologin.ps1` | Configure IBKR auto-login | No |
| `generate-api-key.ps1` | Generate secure API key | No |
| `verify.ps1` | Validate deployment | No |

### Operational Scripts

| Script | Purpose |
| -------- | --------- |
| `status.ps1` | Show NSSM services and API health status |
| `healthcheck.ps1` | Manual API health check |

### Service Management Commands

```powershell
# Start services
Start-Service -Name mm-ibkr-api
Start-Service -Name mm-ibkr-gateway

# Stop services
Stop-Service -Name mm-ibkr-api
Stop-Service -Name mm-ibkr-gateway

# Restart services
Restart-Service -Name mm-ibkr-api
Restart-Service -Name mm-ibkr-gateway

# Check service status
Get-Service -Name mm-ibkr-api, mm-ibkr-gateway

# View service logs
Get-Content "C:\ProgramData\mm-ibkr-gateway\storage\logs\api-stdout.log" -Tail 50
Get-Content "C:\ProgramData\mm-ibkr-gateway\storage\logs\gateway-stdout.log" -Tail 50
```

---

## NSSM Service Management

Both API and Gateway run as Windows services managed by NSSM (Non-Sucking Service Manager):

| Service | Auto-Start | Auto-Restart | Window Enforcement |
| ------- | ---------- | ------------ | -------------------|
| `mm-ibkr-api` | Yes (on boot) | Yes (5s delay) | Internal (API returns 503 outside window) |
| `mm-ibkr-gateway` | Yes (on boot) | Yes (5s delay) | None (runs 24/7, IB handles daily restart) |

### Service Features

- **Auto-start on boot:** Services start automatically when Windows boots (no user login required)
- **Auto-restart on failure:** NSSM restarts services within 5 seconds if they crash
- **Log rotation:** Logs rotate automatically at 10MB
- **Environment variables:** `.env` file loaded into service environment
- **Window management:** API enforces `RUN_WINDOW_*` internally via middleware

### Time Window Behavior

**Previous approach (Task Scheduler + Watchdog):**
- External watchdog polled every 2 minutes
- Stopped API process outside window
- Scheduled tasks started/stopped services

**Current approach (NSSM + API internal enforcement):**
- Services run 24/7, managed by NSSM
- API middleware checks time window on each request
- Returns HTTP 503 Service Unavailable outside window
- No external polling or process management needed

---

## mm-control Integration

The deployment integrates with [mm-control](https://github.com/your-org/mm-control) for centralized trading control:

### Disable Trading

```powershell
# Disable immediately (requires confirmation)
cd C:\Users\mikae\Coding Projects\mm-control\scripts
.\disable-trading.ps1 -Reason "Market volatility"

# Disable with 30-minute TTL auto-revert
.\disable-trading.ps1 -Reason "Testing deployment" -TTL 30

# Skip confirmation (automation)
.\disable-trading.ps1 -Reason "Automated circuit breaker" -Force
```

### Enable Trading

```powershell
# Enable (requires confirmation)
.\enable-trading.ps1 -Reason "Normal conditions restored"

# Skip confirmation
.\enable-trading.ps1 -Reason "TTL expired" -Force
```

### Check Trading Status

```powershell
# Via API endpoint
Invoke-RestMethod -Uri "http://localhost:8000/control/status"

# Via guard file
Test-Path "C:\ProgramData\mm-control\TRADING_DISABLED"

# Via toggles file
Get-Content "C:\ProgramData\mm-control\toggles.json" | ConvertFrom-Json
```

### How It Works

1. **Guard File:** Presence of `C:\ProgramData\mm-control\TRADING_DISABLED` blocks all trading
2. **Toggle Store:** `C:\ProgramData\mm-control\toggles.json` provides structured state with TTL
3. **API Middleware:** Checks `is_trading_disabled()` before processing orders (returns HTTP 403)
4. **TTL Monitor:** Background thread in API auto-enables trading when TTL expires
5. **Audit Log:** All actions logged to `C:\ProgramData\mm-control\control.log`
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
   schtasks /run /tn "\mm-tasks\IBKR-API-START"
   
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
Get-Content "$env:DATA_STORAGE_DIR\logs\api.log" -Tail 100
```

### API Startup & PID file

- `start-api.ps1` launches the server using `python -m api.uvicorn_runner`.
  - `api.uvicorn_runner` ensures `sys.stdout`/`sys.stderr` are present (prevents uvicorn/formatter errors when stdio is redirected), and runs `api.boot:app` so an asyncio event loop exists before importing third-party libs that may call `asyncio.get_event_loop()` at import time.
- PID file behavior:
  - Primary: writes PID to `LOG_DIR\api.pid` (typically under `%DATA_STORAGE_DIR%/logs`).
  - Fallback: if the ProgramData storage/log directory is not writable, the script writes the PID to `%TEMP%\api.pid` and logs a warning indicating the fallback location.
- Recommendation: ensure the service account or the Task Scheduler account has write permissions to `%DATA_STORAGE_DIR%` and its `logs` subdirectory so PID files and logs are persisted in ProgramData.

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

1. Copy to a client securely (not via email/chat). For local testing you can use mm-trading on the same machine.
2. Rotate periodically using `generate-api-key.ps1`
3. File is excluded from git via `.gitignore`

### Firewall

The firewall rule restricts API access to:

- Allowed IPs (configured during setup)
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

### 2. Copy API Key to client

The API key is in `secrets/api_key.txt`. Copy it to any client that will call the API (for example, mm-trading on the same machine):

```bash
# On client (or local shell)
export IBKR_API_KEY="<paste-key-here>"
```

### 3. Verify client connectivity

Local test (same machine):

```bash
curl -H "X-API-Key: $IBKR_API_KEY" http://127.0.0.1:8000/health
```

Remote client test (replace `<laptop-ip>` with this machine IP):

```bash
curl -H "X-API-Key: $IBKR_API_KEY" http://<laptop-ip>:8000/health
```

### 4. Enable Orders (When Ready)

When ready to enable order placement:

```powershell
# Edit .env
$env:ORDERS_ENABLED = "true"

# Create arm file
New-Item -Path "$env:DATA_STORAGE_DIR\arm_orders_confirmed.txt" -ItemType File
```

### 5. Monitor First Full Day

Watch the first full trading day:

```powershell
# In one terminal
Get-Content "$env:DATA_STORAGE_DIR\logs\api.log" -Wait

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
  2. Ensure mm-control guard file is NOT present (check: `C:\ProgramData\mm-control\TRADING_DISABLED`).
  3. Restart the API.
- To switch to live trading:
  1. Set `TRADING_MODE=live` in `.env`.
  2. Set `ORDERS_ENABLED=true` only if you intend to place live orders.
  3. Create a live trading override file at `LIVE_TRADING_OVERRIDE_FILE` (physical guard for live mode).
  4. Ensure mm-control guard file is NOT present (check: `C:\ProgramData\mm-control\TRADING_DISABLED`).
  5. Ensure firewall rules, credentials, and IBKR live ports/IDs (`LIVE_GATEWAY_PORT`, `LIVE_CLIENT_ID`) are correct.
  6. Restart Gateway and API. Verify via `.\status.ps1` and health check that `trading_mode` reports `live` before placing any orders.

---

## Version History

| Version | Date | Changes |
| --------- | ------ | --------- |
| 1.0.0 | 2024-12-30 | Initial deployment guide |
