# Linux Local Deployment

Production deployment for IBKR Gateway with Docker, using IBC for auto-login and 2FA handling.

## Quick Start

```bash
cd deploy/linux
cp .env.example .env
# Edit .env with your IBKR credentials
./scripts/start.sh
```

Wait for 2FA approval on your mobile, then verify:

```bash
curl http://localhost:8000/health
```

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    Linux Host                                    │
│                                                                 │
│  ┌─────────────────────┐     ┌─────────────────────┐           │
│  │  IB Gateway Docker  │     │  mm-ibkr-gateway    │           │
│  │  (IBC + Xvfb+socat) │◄────│  FastAPI :8000      │           │
│  │  Live: 4003→4001    │     └─────────────────────┘           │
│  │  Paper: 4004→4002   │                                       │
│  │  VNC: 5900          │                                       │
│  └─────────────────────┘                                        │
│           │                                                     │
│           ▼                                                     │
│  ┌─────────────────────────────────────────┐                    │
│  │         Docker Network: ibkr-network    │                    │
│  └─────────────────────────────────────────┘                    │
└─────────────────────────────────────────────────────────────────┘
```

## Components

| Component | Image | Version |
|-----------|-------|---------|
| IB Gateway | `ghcr.io/gnzsnz/ib-gateway:stable` | 10.37.1o |
| IBC | Included in image | 3.23.0 |
| FastAPI | Built from project Dockerfile | Python 3.11 |

## File Structure

```
deploy/linux/
├── docker-compose.yml        # Combined stack (gateway + api)
├── .env.example              # Environment template
├── config/
│   ├── config.json           # API runtime config
│   └── tws_settings/         # IB Gateway settings (persistent)
├── data/                     # API data (audit db, logs)
├── scripts/
│   ├── start.sh              # Start stack
│   ├── stop.sh               # Stop stack
│   ├── status.sh             # Health check
│   └── logs.sh               # Tail logs
└── README.md
```

## Configuration

### Environment Variables (.env)

| Variable | Description |
|----------|-------------|
| `TWS_USERID` | IBKR username |
| `TWS_PASSWORD` | IBKR password |
| `TRADING_MODE` | `live`, `paper`, or `both` |
| `TIME_ZONE` | Timezone (e.g., `America/New_York`) |
| `VNC_PASSWORD` | Password for VNC access |

### Key Settings

| Setting | Value | Purpose |
|---------|-------|---------|
| `AUTO_RESTART_TIME` | `11:45 PM` | Daily restart without re-auth |
| `TWOFA_TIMEOUT_ACTION` | `restart` | Auto-retry 2FA on timeout |
| `RELOGIN_AFTER_TWOFA_TIMEOUT` | `yes` | Re-initiate login if 2FA expires |
| `EXISTING_SESSION_DETECTED_ACTION` | `primary` | Handle session conflicts |

## Scripts

```bash
./scripts/start.sh    # Start the stack
./scripts/stop.sh     # Stop the stack
./scripts/status.sh   # Show health status
./scripts/logs.sh     # Tail all logs
./scripts/logs.sh ib-gateway  # Tail specific service
```

## 2FA Flow

```
1. IBC starts Gateway → Auto-fills credentials → Clicks Login
        ↓
2. IBKR sends push notification to Mobile App
        ↓
3a. Approve within 3 min → Login succeeds
        ↓
   Gateway runs until 11:45 PM restart

   ─────────── OR ───────────

3b. Timeout → IBC auto-restarts login
        ↓
   New push sent → Repeat until approved
```

## Maintenance

| Event | Action | Notes |
|-------|--------|-------|
| Daily 11:45 PM | Auto-restart | No re-auth needed |
| Sunday 01:00+ ET | Weekly expiry | Must approve 2FA once |
| Container crash | Auto-restart | `restart: always` policy |

## VNC Access

Connect to `localhost:5900` with any VNC client (RealVNC, TigerVNC, etc.) to view the IB Gateway UI. Useful for:
- First-time setup verification
- Debugging login issues
- Checking auto-restart settings

## Ports

| Port | Service | Description |
|------|---------|-------------|
| 4001 | Live API | IBKR live trading |
| 4002 | Paper API | IBKR paper trading |
| 8000 | REST API | mm-ibkr-gateway FastAPI |
| 5900 | VNC | IB Gateway UI access |

All ports bound to `127.0.0.1` (localhost only).

## Troubleshooting

### API not connecting to Gateway

Check the health status:
```bash
./scripts/status.sh
```

Verify `config/config.json` has correct `ibkr_gateway_host`:
```bash
grep ibkr_gateway_host config/config.json
# Should show: "ibkr_gateway_host": "ib-gateway"
```

### Gateway not starting

Check logs:
```bash
./scripts/logs.sh ib-gateway
```

### Permission errors on data/

```bash
chmod 777 deploy/linux/data
```

## Security

1. **Credentials**: Stored in `.env` (gitignored)
2. **Ports**: Localhost only - not exposed to network
3. **VNC**: Password protected
4. **API**: Orders disabled by default in `control.json`

## References

- [IBC User Guide](https://github.com/IbcAlpha/IBC/blob/master/userguide.md)
- [ib-gateway-docker](https://github.com/gnzsnz/ib-gateway-docker)
- [IB Gateway Downloads](https://www.interactivebrokers.com/en/trading/ibgateway-stable.php)