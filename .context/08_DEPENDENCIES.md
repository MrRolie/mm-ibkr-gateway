# 08_DEPENDENCIES.md: External Integrations & Libraries

## Direct External Dependencies

### IBKR Integration

#### ib_insync (>=0.9.17, <1.0)

**Purpose**: Python wrapper for Interactive Brokers API

**Key Classes**:
- `ib_insync.IB`: Main client
- `ib_insync.Contract`: Security contract
- `ib_insync.Order`: Order object
- `ib_insync.Ticker`: Market data ticker

**Usage in Project**:
```python
from ib_insync import IB, Contract, Order

# In ibkr_core/client.py
self.ib = IB()
await self.ib.connectAsync(host, port, clientId)

# In ibkr_core/contracts.py
contract = ib_insync.Contract(symbol="AAPL", securityType="STK", exchange="SMART")
contract = self.ib.qualifyContracts(contract)[0]

# In ibkr_core/orders.py
order = ib_insync.Order(action="BUY", totalQuantity=100, orderType="MKT")
oid = self.ib.placeOrder(contract, order)
```

**Connection Settings**:
- **Host**: Configurable via `IBKR_GATEWAY_HOST` (default: `localhost`)
- **Port**: `4002` (paper), `4001` (live) - configurable
- **Client ID**: Unique per connection
- **Auto-reconnect**: ib_insync handles reconnection logic

**Rate Limits**:
- Market data: Unlimited (subject to IBKR subscriptions)
- Order operations: 50/second (soft limit, enforced by broker)
- Account queries: Unlimited
- Contract resolution: 100/second (recommended)

**Error Handling**:
```python
try:
    contract = self.ib.qualifyContracts(contract)[0]
except (ib_insync.ContractError, ib_insync.ConnectionError) as e:
    raise ContractResolutionError(str(e)) from e
```

---

### FastAPI (>=0.104.0, <1.0)

**Purpose**: REST API framework

**Key Components**:
- `FastAPI` app instance
- `@app.get()`, `@app.post()` decorators
- `Depends()` for dependency injection
- Built-in OpenAPI documentation at `/docs`

**Usage**:
```python
from fastapi import FastAPI, Depends
from api.dependencies import get_ibkr_client

app = FastAPI(
    title="IBKR Gateway API",
    description="Market data and order management",
    version="0.1.0"
)

@app.get("/health")
async def health():
    return {"status": "healthy"}

@app.post("/api/orders/place")
async def place_order(
    request: OrderSpecRequest,
    client: IBKRClient = Depends(get_ibkr_client)
):
    return await client.place_order(...)
```

**Documentation**: Available at `/docs` (Swagger UI) and `/redoc` (ReDoc)

---

### Uvicorn (>=0.30, <1.0)

**Purpose**: ASGI server for FastAPI

**Usage**:
```bash
# Via CLI
poetry run ibkr-gateway start-api --host 0.0.0.0 --port 8000

# Direct invocation
uvicorn api.server:app --host 0.0.0.0 --port 8000 --workers 4
```

**Configuration**:
- `--workers`: Number of worker processes (default 1)
- `--reload`: Auto-reload on code change (development only)
- `--log-level`: debug, info, warning, error

---

### Pydantic (>=2.0, <3.0)

**Purpose**: Data validation and serialization

**Key Features**:
- Field validation (type checking, constraints)
- JSON serialization/deserialization
- OpenAPI schema generation
- Custom validators

**Usage**:
```python
from pydantic import BaseModel, Field, field_validator

class OrderSpec(BaseModel):
    symbol: str = Field(..., min_length=1)
    quantity: int = Field(..., ge=1)
    
    @field_validator("symbol")
    @classmethod
    def validate_symbol(cls, v):
        return v.upper()

# Validation on instantiation
spec = OrderSpec(symbol="aapl", quantity=100)
# spec.symbol is now "AAPL"

# JSON serialization
json_data = spec.model_dump_json()
```

---

### MCP SDK (>=1.2, <2.0)

**Purpose**: Model Context Protocol server for Claude integration

**Key Classes**:
- `FastMCP`: Server class
- `Tool`: Decorator for tool definitions

**Usage**:
```python
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("ibkr-gateway")

@mcp.tool()
async def get_quote(symbol: str, security_type: str) -> str:
    """Get market quote for a symbol."""
    # Tool implementation
    return json.dumps(quote)

# Run server
mcp.run(transport="stdio")  # Or HTTP
```

**Connection**:
- Connects to IBKR REST API at `http://localhost:8000`
- 8 tools exposed: quote, historical data, account status, P&L, orders

---

## Development Dependencies

### pytest (^7.4)

**Purpose**: Testing framework

**Plugins**:
- `pytest-asyncio`: Async test support
- `pytest-cov`: Code coverage reporting

**Usage**:
```bash
poetry run pytest tests/ -v
poetry run pytest tests/ --cov=ibkr_core
```

---

### Black (^23.12)

**Purpose**: Code formatter

**Configuration** (in `pyproject.toml`):
```toml
[tool.black]
line-length = 100
target-version = ["py310"]
```

**Usage**:
```bash
poetry run black ibkr_core/ api/
```

---

### isort (^5.13)

**Purpose**: Import organization

**Configuration** (in `pyproject.toml`):
```toml
[tool.isort]
profile = "black"
line_length = 100
```

**Usage**:
```bash
poetry run isort ibkr_core/ api/
```

---

### mypy (^1.7)

**Purpose**: Static type checker

**Configuration** (in `pyproject.toml`):
```toml
[tool.mypy]
python_version = "3.10"
disallow_untyped_defs = false
warn_return_any = true
```

**Usage**:
```bash
poetry run mypy ibkr_core/ api/
```

---

## Network & System Dependencies

### localhost:4002 (IBKR Gateway/TWS)

**Required For**: All market data and order operations

**Not a Dependency Package**: External application that must be running

**How to Get**:
1. Download IBKR Gateway from https://www.ibkr.com/trading/platforms/gateway
2. Or use TWS (Trader Workstation)
3. Enable API in settings (Configure → API → Settings)
4. Ensure paper trading account enabled

**Network Port**: 4002 (paper) or 4001 (live)

**Connection Timeout**: 30 seconds (configurable)

**Retry Logic**: Exponential backoff, automatic reconnection

---

## Optional Dependencies

### python-dotenv (>=1.0, <2.0)

**Purpose**: Load environment variables from `.env` file

**Usage**:
```python
from dotenv import load_dotenv
load_dotenv(".env")

# Now os.environ contains keys from .env
trading_mode = os.environ.get("TRADING_MODE", "paper")
```

---

### loguru (>=0.7, <1.0)

**Purpose**: Enhanced logging with better formatting

**Usage**:
```python
from loguru import logger

logger.add("data/logs/app.log", rotation="500 MB")
logger.info("Order placed", symbol="AAPL")
```

**Configuration**: In `ibkr_core/logging_config.py`

---

### rich (>=13.7, <15.0)

**Purpose**: Pretty console output (CLI)

**Usage**:
```python
from rich.table import Table
from rich.console import Console

console = Console()
table = Table(title="Positions")
table.add_column("Symbol")
table.add_column("Quantity")
console.print(table)
```

---

### typer (>=0.9.0, <1.0)

**Purpose**: CLI framework (used for `ibkr-gateway` commands)

**Usage**:
```python
from typer import Typer

app = Typer()

@app.command()
def healthcheck():
    """Check IBKR Gateway connection."""
    print("Healthy!")

if __name__ == "__main__":
    app()
```

---

### anyio (>=4.5, <5.0)

**Purpose**: Async I/O abstraction layer

**Why Needed**: ib_insync requires asyncio; anyio provides portability

---

### python-json-logger (>=4.0.0, <5.0.0)

**Purpose**: Structured JSON logging for production

**Usage**:
```python
from pythonjsonlogger import jsonlogger
import logging

logger = logging.getLogger()
handler = logging.StreamHandler()
formatter = jsonlogger.JsonFormatter()
handler.setFormatter(formatter)
logger.addHandler(handler)

# Output: {"timestamp": "...", "level": "INFO", "message": "..."}
```

---

## Dependency Tree

```
mm-ibkr-gateway (root)
├── ib-insync (IBKR connector)
│   └── (installed separately from PyPI)
├── fastapi (REST API)
│   ├── pydantic (validation)
│   └── starlette (ASGI framework)
├── uvicorn (ASGI server)
├── mcp (Claude MCP)
├── python-dotenv (env loading)
├── loguru (logging)
├── typer (CLI)
│   └── rich (formatting)
├── aiohttp (async HTTP)
├── httpx (async HTTP client)
├── nest-asyncio (async utilities)
├── anyio (async abstraction)
└── [Dev dependencies]
    ├── pytest (testing)
    ├── pytest-asyncio
    ├── pytest-cov
    ├── black (formatting)
    ├── isort (imports)
    ├── mypy (type checking)
    ├── flake8 (linting)
    ├── bandit (security)
    ├── safety (dependency audit)
    └── pre-commit (git hooks)
```

---

## Compatibility & Version Constraints

| Library | Constraint | Reason |
|---------|-----------|--------|
| ib-insync | >=0.9.17, <1.0 | API stable in 0.9.x; major version TBD |
| FastAPI | >=0.104.0, <1.0 | Recent features, no breaking changes expected |
| Uvicorn | >=0.30, <1.0 | ASGI 3.0 support, stable |
| Pydantic | >=2.0, <3.0 | V2 required for new validator syntax |
| Python | >=3.10 | Type hints, async/await, walrus operator |
| MCP | >=1.2, <2.0 | Recent version with FastMCP |

---

## External API Rate Limits

### IBKR API (via ib_insync)

**Market Data Requests**:
- **Unlimited** (subject to subscriptions)
- Typical: <100ms per quote

**Order Operations**:
- Soft limit: 50 orders/second
- Hard limit enforced by broker

**Account Queries**:
- Unlimited
- Cached locally for 60 seconds

**Contract Resolution**:
- Recommended: 100/second
- Caches results in-memory

### Implementation (Automatic)

ib_insync handles rate limiting internally. No explicit throttling needed in our code.

---

## Network Topology

```
Client/Claude
    ↓
[MCP Tools Server] ←→ [REST API] ←→ [ibkr_core] ←→ [IBKR Gateway]
localhost:8000      localhost:8000  (in-process)  localhost:4002
```

**Data Flow**:
1. Claude queries MCP tool
2. MCP tool calls HTTP client
3. HTTP client POST/GET to REST API
4. REST API calls `ibkr_core` functions
5. `ibkr_core` uses ib_insync to call IBKR Gateway
6. Response flows back up the stack

---

## Security Considerations

### Credentials Handling

- **API Key** (if used): Environment variable, not in code
- **IBKR Account**: Credentials managed by IBKR Gateway (not in our app)
- **Override File**: File-based confirmation for live trading (not credential)

### Network Security

- **IBKR Gateway**: Assume same machine (localhost:4002)
- **REST API**: No authentication by default (add via `API_KEY` env var)
- **MCP**: Communication via stdio or TCP (depends on deployment)

### Secret Management

```bash
# Bad: Secrets in code
API_KEY = "sk_live_123456"

# Good: Secrets in environment
API_KEY = os.environ.get("API_KEY")

# Good: .env file (gitignored)
# .env
API_KEY=sk_live_123456

# .gitignore
.env
```

---

## Troubleshooting Dependencies

### IBKR Gateway Connection Failed

```bash
# Check if Gateway is running
lsof -i :4002

# Verify API enabled
# Settings → Configure → API → Settings
# Ensure "Enable API" is checked

# Test connection
poetry run ibkr-gateway healthcheck
```

### Missing Package

```bash
# Reinstall dependencies
poetry install

# Update to latest compatible versions
poetry update

# Check installed versions
poetry show

# Check specific package
poetry show ib-insync
```

### Type Checking Failures

```bash
# Check with mypy
poetry run mypy ibkr_core/

# Common issues:
# - Missing type hints
# - Incompatible types
# - Untyped library imports

# Add type stubs if needed
poetry add types-requests  # For requests library stubs
```

---

## Summary

- **Core**: ib_insync (IBKR), FastAPI (REST), Uvicorn (ASGI server)
- **Data**: Pydantic (validation), python-json-logger (JSON logs)
- **Async**: asyncio, anyio, nest-asyncio
- **CLI**: typer, rich
- **Testing**: pytest, pytest-asyncio, pytest-cov
- **Quality**: black, isort, mypy, flake8, bandit
- **External**: IBKR Gateway on localhost:4002 (required)
