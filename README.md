# mm-ibkr-gateway (Deployer)

This repository is an **agent-focused deployment utility** for the Interactive Brokers (IB) Gateway. 

The core IBKR trading and MCP logic has been migrated to `mm-ibkr-mcp`. This repository is now strictly dedicated to reliably deploying and managing the IB Gateway container, allowing `mm-ibkr-mcp` (or any other application) to connect to it via `localhost` (ports 4001/4002).

## Features
- **Docker Compose Setup**: Uses a standard community image (`ghcr.io/gnzsnz/ib-gateway`) for the Interactive Brokers Gateway.
- **Agent-Friendly Utilities**: Provides a Python CLI tool (`scripts/deployer.py`) that returns structured JSON output, making it extremely easy for coding agents to manage the gateway lifecycle without manual shell scripting.
- **Minimal User Steps**: Users only need to supply their credentials when prompted during the initial setup; everything else is automated.

## Quickstart

1. Install dependencies via `uv`:
   ```bash
   uv sync
   ```

2. Setup credentials (if `.env` is missing, you will be prompted):
   ```bash
   uv run python scripts/deployer.py setup
   ```

3. Start the Gateway:
   ```bash
   uv run python scripts/deployer.py up
   ```

4. Check Status:
   ```bash
   uv run python scripts/deployer.py status
   ```

5. Stop the Gateway:
   ```bash
   uv run python scripts/deployer.py down
   ```

## Integration with `mm-ibkr-mcp`
Once deployed via this repository, the Gateway will automatically expose its API ports. `mm-ibkr-mcp` can connect to the deployed gateway using:
- **Host:** `localhost` or `127.0.0.1`
- **Paper Trading Port:** `4002`
- **Live Trading Port:** `4001`