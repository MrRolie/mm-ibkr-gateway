# 02_ARCHITECTURE.md: System Design & Boundaries

## High-Level Overview

```
┌─────────────────────────────────────────────────────────────┐
│                     IBKR Gateway System                      │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌─────────────┐   ┌─────────────┐   ┌──────────────┐      │
│  │   REST API  │   │  Direct API  │   │  MCP Server  │      │
│  │ (FastAPI)   │   │  (Python)    │   │  (Claude)    │      │
│  └──────┬──────┘   └──────┬──────┘   └──────┬───────┘      │
│         │                  │                  │               │
│         └──────────────────┼──────────────────┘               │
│                            │                                  │
│                    ┌───────▼────────┐                        │
│                    │  ibkr_core API  │                       │
│                    │  (Business      │                       │
│                    │   Logic)        │                       │
│                    └───────┬────────┘                        │
│                            │                                  │
│          ┌─────────────────┼─────────────────┐               │
│          │                 │                 │               │
│     ┌────▼────┐    ┌──────▼────┐   ┌──────▼──────┐          │
│     │ Contracts│    │ Market     │   │ Orders &    │         │
│     │ & Cache  │    │ Data       │   │ Account     │         │
│     └──────────┘    └────────────┘   └────────────┘         │
│          │                 │                 │               │
│          └─────────────────┼─────────────────┘               │
│                            │                                  │
│                    ┌───────▼────────┐                        │
│                    │  IBKR Executor  │                       │
│                    │  (Dedicated     │                       │
│                    │   Thread)       │                       │
│                    └───────┬────────┘                        │
│                            │                                  │
│                    ┌───────▼────────┐                        │
│                    │ ib_insync      │                        │
│                    │ (IBKR SDK)     │                        │
│                    └───────┬────────┘                        │
│                            │                                  │
│                    ┌───────▼────────┐                        │
│                    │ IBKR Gateway   │                        │
│                    │ on port 4002   │                        │
│                    │ (Paper/Live)   │                        │
│                    └────────────────┘                        │
│                                                               │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ Persistence: SQLite audit.db (correlation IDs,      │   │
│  │             order lifecycle, fills)                 │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

---

## Module Structure

### `ibkr_core/` – Core Domain Logic

**Responsibility**: Market data, account management, order lifecycle. No HTTP, no MCP.

| Module | Purpose | Key Functions |
|--------|---------|---------------|
| `client.py` | Main client facade | `create_client()`, connect/disconnect |
| `contracts.py` | Contract resolution & caching | `resolve_contract()`, contract cache |
| `market_data.py` | Quotes & historical bars | `get_quote()`, `get_bars()` |
| `account.py` | Account summary, positions, P&L | `get_account_summary()`, `get_positions()`, `get_pnl()` |
| `orders.py` | Order placement, cancellation, status | `preview_order()`, `place_order()`, `get_order_status()`, `cancel_order()` |
| `persistence.py` | SQLite audit & order history | `log_order_action()`, `query_order_history()` |
| `config.py` | Configuration loading & validation | `get_config()`, safety gates |
| `logging_config.py` | Structured logging, correlation IDs | `get_correlation_id()`, JSON logging |
| `metrics.py` | Observability counters | `record_trade()`, `get_metrics()` |
| `cli.py` | CLI commands | `demo()`, `healthcheck()`, `start_api()` |
| `demo.py` | Interactive demo script | User-facing 5-min walkthrough |
| `healthcheck.py` | Health check logic | Connection test, server time |
| `simulation.py` | Paper trading simulator | Order simulation, fills |

**Invariant**: All async operations run in IBKR executor thread. No blocking calls in main event loop.

---

### `api/` – REST API Layer

**Responsibility**: HTTP endpoints, request validation, response formatting. No business logic.

| Module | Purpose |
|--------|---------|
| `server.py` | FastAPI app, route definitions, lifespan |
| `models.py` | Pydantic request/response models |
| `errors.py` | Error codes, exception mapping |
| `auth.py` | API key validation |
| `middleware.py` | Correlation ID injection, request logging |
| `dependencies.py` | FastAPI dependency injection (client, context, executor) |

**Endpoints**:

| Path | Method | Purpose |
|------|--------|---------|
| `/health` | GET | System health check |
| `/api/market/quote` | GET | Market quote for symbol |
| `/api/market/historical` | GET | Historical bars |
| `/api/account/summary` | GET | Account status |
| `/api/account/positions` | GET | Current positions |
| `/api/account/pnl` | GET | P&L by timeframe |
| `/api/orders/preview` | POST | Preview order (no placement) |
| `/api/orders/place` | POST | Place order (gated by TRADING_MODE, ORDERS_ENABLED) |
| `/api/orders/{orderId}/status` | GET | Order status |
| `/api/orders/{orderId}/cancel` | POST | Cancel order (gated) |

**Request validation**:
- Pydantic models enforce schema before business logic
- 400 Bad Request for invalid input
- 401 Unauthorized for missing API key
- 422 Unprocessable Entity for validation failure

**Error handling**:
- HTTP status code maps to error code
- Response body includes error code, message, details
- See `api/errors.py` for full code set

---

### `mcp_server/` – Claude MCP Tool Server

**Responsibility**: Expose 8 tools via MCP protocol. Thin wrapper over REST API.

| Tool | Purpose | Maps to API |
|------|---------|-----------|
| `get_quote` | Get current market quote | GET `/api/market/quote` |
| `get_historical_data` | Get historical OHLCV bars | GET `/api/market/historical` |
| `get_account_status` | Get account summary & positions | GET `/api/account/{summary,positions}` |
| `get_pnl` | Get P&L by symbol or total | GET `/api/account/pnl` |
| `preview_order` | Preview order without placement | POST `/api/orders/preview` |
| `place_order` | Place live order (gated) | POST `/api/orders/place` |
| `get_order_status` | Get order status | GET `/api/orders/{orderId}/status` |
| `cancel_order` | Cancel order (gated) | POST `/api/orders/{orderId}/cancel` |

**Design**:
- `main.py`: FastMCP server, tool definitions
- `http_client.py`: HTTP client to REST API
- `config.py`: MCP-specific config
- `errors.py`: Error handling, response mapping

**Invariant**: MCP tools are **stateless**. Each tool call makes fresh HTTP request.

---

## Data Flow

### Quote Retrieval

```
User Request (symbol)
        ↓
api/server.py::get_quote_endpoint()
        ↓
ibkr_core/client.py::get_quote()
        ↓
ibkr_core/contracts.py::resolve_contract() [cache hit/miss]
        ↓
IBKR Executor → ib_insync → IBKR Gateway
        ↓
Quote snapshot (bid/ask/last/volume/timestamp)
        ↓
Pydantic model validation (api/models.py)
        ↓
HTTP 200 + JSON response
```

### Order Placement

```
User Request (OrderSpec)
        ↓
api/server.py::place_order_endpoint()
        ↓
auth check + Pydantic validation
        ↓
ibkr_core/client.py::place_order()
        ↓
config.validate() [TRADING_MODE, ORDERS_ENABLED, override file]
        ↓
ibkr_core/orders.py::place_order_internal()
        ↓
If ORDERS_ENABLED=false:
  Return OrderResult(status=SIMULATED)
Else (ORDERS_ENABLED=true + TRADING_MODE=live):
  IBKR Executor → ib_insync → IBKR Gateway → Broker
        ↓
ibkr_core/persistence.py::log_order_action()
        ↓
SQLite audit.db: Insert (orderId, action, timestamp, spec, status, config_snapshot)
        ↓
HTTP 200 + OrderResult (status=ACCEPTED or FILLED)
```

**Safety gates**:
1. `config.trading_mode == "paper"` → simulate
2. `config.orders_enabled == False` → simulate
3. `config.trading_mode == "live" and config.orders_enabled == True`:
   - Check override file exists
   - Log warning

---

## Concurrency & Threading

### IBKR Executor Thread

All IBKR operations (ib_insync calls) run in a dedicated thread:

```python
# In ibkr_core/client.py
self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="IBKR")
# All ib_insync operations run via:
await loop.run_in_executor(self.executor, ib_insync_call, *args)
```

**Why**: ib_insync requires a persistent event loop. Single-threaded executor avoids "no event loop in current thread" errors.

### API Request Concurrency

FastAPI handles multiple concurrent requests via Uvicorn workers. Each request:
- Gets its own correlation ID (UUID)
- Shares the single IBKR client (thread-safe via executor)
- Logs with correlation ID for tracing

---

## Configuration & Secrets

### Config Files

- **`.env`** (gitignored): Runtime configuration
- **`.env.example`** (tracked): Template with defaults

### Config Loading

```python
# ibkr_core/config.py
config = get_config()  # Singleton
# Reads from .env, validates, gates on safety checks
```

### Safety Checks at Startup

```python
config.validate()  # In ibkr_core/client.py::__init__()
# Raises InvalidConfigError if:
# - TRADING_MODE not in ("paper", "live")
# - TRADING_MODE=live + ORDERS_ENABLED=true but override file missing
```

**Invariant**: Order placement checks config at runtime, not just startup.

---

## Persistence Layer

### SQLite Schema

**Table: `audit_log`**

```sql
CREATE TABLE audit_log (
    id INTEGER PRIMARY KEY,
    correlation_id TEXT,
    timestamp TEXT NOT NULL,
    event_type TEXT NOT NULL,
    event_data TEXT (JSON),
    user_context TEXT,
    account_id TEXT,
    UNIQUE(correlation_id, event_type, timestamp)
);
```

- **event_type**: `ORDER_PLACED`, `ORDER_FILLED`, `ORDER_CANCELLED`, etc.
- **event_data**: Full OrderDetail as JSON
- **Unique constraint**: Idempotent writes (same input → no duplicate row)

**Table: `order_history`**

```sql
CREATE TABLE order_history (
    order_id INTEGER PRIMARY KEY,
    symbol TEXT,
    action TEXT,
    quantity REAL,
    order_type TEXT,
    status TEXT,
    filled REAL,
    avg_fill_price REAL,
    commission REAL,
    placed_at TEXT,
    updated_at TEXT,
    config_snapshot TEXT (JSON)
);
```

**Invariant**: Append-only. Never update or delete rows. History is immutable.

---

## Entry Points

### CLI

```bash
ibkr-gateway healthcheck        # → ibkr_core/cli.py::healthcheck()
ibkr-gateway demo               # → ibkr_core/demo.py::main()
ibkr-gateway start-api          # → uvicorn api.server:app
```

### REST API

```bash
uvicorn api.server:app --host 0.0.0.0 --port 8000
```

Lifespan events in `api.dependencies.py`:
- `lifespan_context()`: Creates client on startup, closes on shutdown
- `get_client_manager()`: Returns shared client instance

### MCP Server

```bash
python -m mcp_server.main
```

Connects to REST API at `http://localhost:8000` (configurable).

### Direct Python

```python
from ibkr_core.client import create_client

async def main():
    client = await create_client()
    quote = await client.get_quote(SymbolSpec(symbol="AAPL", securityType="STK"))
    await client.close()

asyncio.run(main())
```

---

## Error Handling Strategy

### Hierarchy

```
Exception
├── IBKRException (base)
│   ├── ConnectionError (IBKR Gateway unreachable)
│   ├── ContractResolutionError (Symbol not found)
│   ├── MarketDataError (Quote fetch failed)
│   ├── OrderError (Order placement failed)
│   │   ├── TradingDisabledError (ORDERS_ENABLED=false)
│   │   ├── OrderValidationError (Invalid quantity, etc.)
│   │   └── OrderRejectedError (Broker rejected)
│   └── AccountError (Account fetch failed)
└── APIError (HTTP layer)
    ├── 400 BadRequest (invalid input)
    ├── 401 Unauthorized (bad API key)
    ├── 422 UnprocessableEntity (validation failed)
    ├── 503 ServiceUnavailable (IBKR unreachable)
    └── 500 InternalServerError (unexpected)
```

### Error Propagation

```
ibkr_core/ (raises IBKRException)
    ↓
api/server.py (catches, maps to APIError)
    ↓
HTTP 4xx/5xx response
    ↓
Client sees APIError response with code + message
```

---

## Testing Strategy

### Test Organization

| Directory | Purpose |
|-----------|---------|
| `tests/test_models.py` | Pydantic model validation |
| `tests/test_config.py` | Configuration & safety gates |
| `tests/test_contracts.py` | Contract resolution |
| `tests/test_market_data.py` | Quote/bar fetching |
| `tests/test_account_*.py` | Account operations |
| `tests/test_orders*.py` | Order lifecycle (place, cancel, status) |
| `tests/test_api_*.py` | REST API endpoints |
| `tests/test_mcp_*.py` | MCP tools |
| `tests/test_persistence*.py` | Audit log persistence |
| `tests/test_simulation*.py` | Paper trading simulation |

### Mocking Strategy

- **Real IBKR calls**: Marked with `@pytest.mark.integration`
- **Mocked IBKR calls**: Use `MagicMock` to simulate responses
- **No external I/O**: Tests run with `TRADING_MODE=paper`, `ORDERS_ENABLED=false`

**Run without integrations**:
```bash
pytest tests/ -m "not integration"
```

---

## Observability

### Logging

- **Level**: Configurable via `LOG_LEVEL` env var
- **Format**: JSON (python-json-logger) for production
- **Correlation ID**: All logs tagged with UUID for tracing
- **Structured**: Fields like `symbol`, `orderId`, `account_id` included

### Metrics

- **File**: `ibkr_core/metrics.py`
- **Data**: Trade counts, fill rates, latencies
- **Endpoint**: `/api/metrics` (future)

### Audit Log

- **File**: `data/audit.db`
- **Queries**: See `persistence.py::query_audit_log()`

---

## Dependencies (See 08_DEPENDENCIES.md for Full List)

- **ib_insync**: IBKR API wrapper
- **FastAPI**: REST framework
- **Uvicorn**: ASGI server
- **Pydantic**: Data validation
- **MCP SDK**: Claude integration

---

## Backward Compatibility

### Contract Changes

When adding a new field to an API response:
1. Make it **optional** (`Optional[type]`)
2. Provide sensible default in Pydantic model
3. Update audit log schema if persisting
4. Document in `03_DATA_CONTRACTS.md`

### Order Lifecycle Changes

Order status values are **append-only**. Never remove or rename:
- `SUBMITTED`, `ACCEPTED`, `FILLED`, `CANCELLED`, `REJECTED` are permanent

---

## Summary

- **Three interfaces** (API, MCP, direct Python) share single `ibkr_core` logic
- **Dedicated IBKR executor thread** prevents event loop conflicts
- **Safety gates** prevent accidental live trading
- **Append-only audit log** ensures immutability
- **Pydantic models** enforce schema at API boundary
- **Error hierarchy** maps domain exceptions → HTTP codes
