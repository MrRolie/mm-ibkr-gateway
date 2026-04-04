# Agent Directives for `mm-ibkr-gateway`

**DO NOT ATTEMPT TO IMPLEMENT TRADING LOGIC OR MCP SERVERS IN THIS REPOSITORY.**
All core trading logic and MCP capabilities belong in `mm-ibkr-mcp`.

This repository's sole purpose is the **orchestration and deployment** of the Interactive Brokers (IB) Gateway container using Docker Compose.

## How to Interact with this Repository
As an AI coding agent, you should use the provided Python deployment utility rather than raw `docker-compose` commands. The utility is designed to yield easily parsable, structured JSON outputs to help you verify state.

### Using the Deployer Utility
Always use `uv run python scripts/deployer.py <command>` from the root of this repository.

1. **Verify State**:
   Run `uv run python scripts/deployer.py check` to ensure Docker is running and ports are available.

2. **Handle Configuration**:
   Run `uv run python scripts/deployer.py setup`. If the `.env` file does not exist or lacks `TWS_USERID` / `TWS_PASSWORD`, this command will interactively ask the user for them. **You cannot supply these on behalf of the user; prompt the user via the tool if necessary.**

3. **Deploy the Gateway**:
   Run `uv run python scripts/deployer.py up`.
   If successful, it returns `{"status": "started", "container": "ib-gateway"}`.

4. **Verify Deployment**:
   Run `uv run python scripts/deployer.py status` to confirm the container's status via a JSON array.

5. **Stop the Gateway**:
   Run `uv run python scripts/deployer.py down` when a teardown is requested.

## Networking Notes
- The gateway container publishes `4001` (Live) and `4002` (Paper) on the host machine.
- Connections from `mm-ibkr-mcp` should be targeted at `127.0.0.1:4001` or `127.0.0.1:4002`.