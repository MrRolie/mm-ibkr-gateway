---
name: ib-gateway-deployer
description: Deploy and orchestrate the Interactive Brokers (IB) Gateway via Docker Compose. Use this when the user needs to spin up or tear down the IB Gateway to provide connectivity for mm-ibkr-mcp or other trading systems.
---

# IB Gateway Deployer

This skill orchestrates the Interactive Brokers (IB) Gateway container deployment. The core deployer logic lives in the `mm-ibkr-gateway` repository.

## Pre-requisites

Ensure you are operating in the `mm-ibkr-gateway` repository root (or switch to it): `/home/mm-mike/ai_system/projects/mm-ibkr-gateway`.

## Deployment Workflow

Do not use raw `docker-compose` commands. Use the provided deployer utility.

1. **Check Environment**:
   ```bash
   uv run python scripts/deployer.py check
   ```

2. **Setup Credentials**:
   ```bash
   uv run python scripts/deployer.py setup
   ```
   *Note: If credentials are missing, this command will interactively ask the user for their TWS_USERID and TWS_PASSWORD. Use your interactive tool prompt capabilities to collect input if the script requires it.*

3. **Start the Gateway**:
   ```bash
   uv run python scripts/deployer.py up
   ```

4. **Verify Status**:
   ```bash
   uv run python scripts/deployer.py status
   ```

5. **Stop the Gateway**:
   ```bash
   uv run python scripts/deployer.py down
   ```

## Networking
- Paper Trading Port: `4002`
- Live Trading Port: `4001`
- Connections from `mm-ibkr-mcp` should target `127.0.0.1:4001` or `127.0.0.1:4002`.
