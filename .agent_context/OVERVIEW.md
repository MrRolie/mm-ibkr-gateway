# IBKR Gateway - Agent Onboarding

## What is this project?

This is a **Python gateway service** for Interactive Brokers (IBKR) that provides:

- REST API for trading operations
- MCP (Model Context Protocol) server for LLM integration
- CLI for manual trading operations

## Key Safety Features

**This system is SAFE BY DEFAULT:**

- Orders are DISABLED until explicitly enabled (`ORDERS_ENABLED=true`)
- Paper trading mode is the default (`TRADING_MODE=paper`)
- Live trading requires explicit override file

## Quick Start

```bash
# Install dependencies
poetry install

# Run tests
poetry run pytest

# Start API server (requires IBKR Gateway running)
poetry run python -m api.server

# Use CLI
poetry run python -m ibkr_core.cli quote AAPL
```

## Project Structure

```text
mm-ibkr-gateway/
├── api/                    # FastAPI REST API
│   ├── server.py          # Main API application
│   ├── models.py          # Pydantic request/response models
│   ├── middleware.py      # Correlation ID middleware
│   └── dependencies.py    # FastAPI dependencies
├── ibkr_core/             # Core IBKR functionality
│   ├── client.py          # IBKRClient wrapper around ib_insync
│   ├── config.py          # Configuration from environment
│   ├── models.py          # Domain models (OrderSpec, SymbolSpec, etc.)
│   ├── orders.py          # Order operations (preview, place, cancel)
│   ├── market_data.py     # Quote and historical data
│   ├── account.py         # Account info (summary, positions, PnL)
│   ├── persistence.py     # SQLite audit database
│   ├── metrics.py         # In-memory metrics collection
│   ├── simulation.py      # Simulated client for testing
│   └── cli.py             # Command-line interface
├── mcp_server/            # MCP server for LLM integration
│   └── server.py          # MCP tools implementation
├── scripts/               # Utility scripts
│   ├── query_audit_log.py
│   └── export_order_history.py
├── tests/                 # Test suite (500+ tests)
├── .context/              # Project planning docs
└── .agent_context/        # This folder - agent onboarding
```

## Configuration

All configuration via environment variables (see `.env.example`):

| Variable | Default | Description |
| ---------- | --------- | ------------- |
| `TRADING_MODE` | `paper` | `paper` or `live` |
| `ORDERS_ENABLED` | `false` | Enable order placement |
| `IBKR_MODE` | - | `simulation` for testing without gateway |
| `API_PORT` | `8000` | REST API port |
| `AUDIT_DB_PATH` | `./data/audit.db` | SQLite audit database |

## Key Concepts

### Trading Modes

- **paper**: Connects to paper trading gateway (port 4002)
- **live**: Connects to live trading gateway (port 4001) - requires override file
- **simulation**: In-memory simulated client, no gateway needed

### Order Flow

1. Create `OrderSpec` with instrument, side, quantity, order type
2. `preview_order()` - Get estimated execution details
3. `place_order()` - Submit to IBKR (if `ORDERS_ENABLED=true`)
4. `cancel_order()` - Cancel open orders

### Correlation IDs

Every API request gets a UUID correlation ID that propagates through all logs and audit records for traceability.

## Important Files to Read First

1. [ibkr_core/config.py](../ibkr_core/config.py) - Configuration system
2. [ibkr_core/client.py](../ibkr_core/client.py) - IBKR connection wrapper
3. [ibkr_core/models.py](../ibkr_core/models.py) - Domain models
4. [api/server.py](../api/server.py) - REST API endpoints
