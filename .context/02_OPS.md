# 02_OPS.md: Execution & Safety (Setup, Run, Side Effects)

## Purpose

This document is the **operational runbook**. Copy-paste commands to build, run, test, and understand side effects.

---

## The Golden Path (5 minutes)

```bash
# 1. Clone repo
git clone <repo-url>
cd mm-ibkr-gateway

# 2. Install dependencies
poetry install

# 3. Copy environment template
cp .env.example .env
# Edit .env if needed (usually not; defaults are safe)

# 4. Verify IBKR Gateway is running on port 4002
# (TWS or Gateway app must be running, paper mode by default)

# 5. Run healthcheck
poetry run ibkr-gateway healthcheck
# Expected output:
#   ✓ Connected to IBKR Gateway
#   ✓ Server time: 2025-01-30 14:35:00 UTC
#   ✓ System ready

# 6. Run demo (paper mode, no trades)
poetry run ibkr-gateway demo
# Expected output:
#   - AAPL quote (bid/ask/last)
#   - SPY bars (5 days)
#   - Account summary (net liquidation, buying power)
#   - Current positions

# ✅ You're done. System is safe and working.
```

---

## Build & Environment

### Setup (First Time)

```bash
# 1. Install Poetry (Python package manager)
curl -sSL https://install.python-poetry.org | python3 -
export PATH="$HOME/.local/bin:$PATH"

# 2. Clone repo
git clone <repo-url>
cd mm-ibkr-gateway

# 3. Install all dependencies (includes dev dependencies)
poetry install

# 4. Activate virtual environment
poetry shell
# OR use poetry run for individual commands:
poetry run python -m ibkr_core.cli healthcheck
```

### Environment Variables (.env)

```bash
# Copy template
cp .env.example .env

# Edit if needed (optional; defaults are safe):
nano .env  # or open in editor

# Example .env (SAFE DEFAULTS)
TRADING_MODE=paper                          # ✅ Safe default
ORDERS_ENABLED=false                        # ✅ Safe default
IBKR_HOST=127.0.0.1
IBKR_PORT=4002
API_PORT=8000
LOG_LEVEL=INFO
LIVE_TRADING_OVERRIDE_FILE=~/ibkr_override.txt

# ❌ NEVER commit .env to git
# ✅ DO commit .env.example
```

### Check Python Version

```bash
python --version
# Expected: Python 3.10 or higher
# If not installed, install Python 3.10+ from python.org
```

---

## Running the System

### 1. Healthcheck (Verify Connection)

```bash
poetry run ibkr-gateway healthcheck

# Expected output:
# ✓ Connected to IBKR Gateway on 127.0.0.1:4002
# ✓ Server time: 2025-01-30 14:35:22 UTC
# ✓ System ready (paper mode, orders disabled)

# Troubleshooting:
# ❌ "Connection refused" → Start TWS or Gateway app on port 4002
# ❌ "Timeout" → Check firewall, ensure IBKR Gateway is running
```

### 2. Interactive Demo (Paper Mode)

```bash
poetry run ibkr-gateway demo

# Expected output:
# 1. Connection Status
#    ✓ Connected to IBKR Gateway
#    ✓ Paper mode (default)
#
# 2. Market Data
#    AAPL Quote:
#      Bid: 150.25 | Ask: 150.26 | Last: 150.255
#
# 3. Historical Data (SPY, last 5 days)
#    Date        Open    High    Low     Close   Volume
#    2025-01-30  651.0   652.5   649.8   651.5   5000000
#    ...
#
# 4. Account Summary
#    Net Liquidation: $1,000,000.00
#    Buying Power: $2,000,000.00
#    Cash: $500,000.00
#
# 5. Current Positions
#    Symbol  Qty     Avg Cost    Current Value   Unrealized PnL
#    AAPL    100     $150.00     $15,025.50      $25.50

# All safe (no real orders placed)
```

### 3. Start REST API

```bash
poetry run ibkr-gateway start-api

# Expected output:
# INFO:     Application startup complete [PID=12345]
# INFO:     Uvicorn running on http://0.0.0.0:8000
# INFO:     Press CTRL+C to quit

# In another terminal, verify API is responding:
curl http://localhost:8000/health
# Response: {"status": "ok"}

# API documentation:
# http://localhost:8000/docs  (Swagger UI)

# Example API calls (paper mode, safe):
curl http://localhost:8000/api/account/summary
curl "http://localhost:8000/api/market/quote?symbol=AAPL"
curl http://localhost:8000/api/account/positions

# To stop:
# Ctrl+C in the terminal running start-api
```

### 4. Start MCP Server (Claude Integration)

```bash
poetry run ibkr-mcp

# Expected output:
# MCP Server running on stdio
# Ready for Claude to connect

# This tool reads from stdin and writes to stdout
# Used by Claude/LLM integrations
```

---

## Testing

### Unit + Integration Tests (All)

```bash
poetry run pytest tests/ -v

# Expected output:
# tests/unit/test_config.py::test_trading_mode_validation PASSED
# tests/unit/test_contracts.py::test_contract_caching PASSED
# ...
# tests/integration/test_market_data.py::test_get_quote PASSED
# ...
# ===================== 635 passed in 12.34s =====================

# Duration: ~15 seconds (depends on machine)
```

### Skip Slow Tests (Integration)

```bash
poetry run pytest tests/ -v -m "not integration"

# Runs only unit tests (~5 seconds)
# Use this for quick feedback during development
```

### Run Single Test File

```bash
poetry run pytest tests/unit/test_orders.py -v

# Or with keyword filter:
poetry run pytest tests/ -k "test_order_placement" -v
```

### Run Single Test File

```bash
poetry run pytest tests/unit/test_orders.py -v

# Or with keyword filter:
poetry run pytest tests/ -k "test_order_placement" -v
```

### Run with Coverage

```bash
poetry run pytest tests/ --cov=ibkr_core --cov=api --cov-report=html

# Opens coverage report:
open htmlcov/index.html  # macOS
# or
xdg-open htmlcov/index.html  # Linux
```

### Test Markers

```bash
# Run only unit tests (no integration, ~20 seconds)
poetry run pytest tests/ -v -m "not integration"

# Run only integration tests (requires IBKR Gateway)
poetry run pytest tests/ -v -m "integration"

# Run only slow tests
poetry run pytest tests/ -v -m "slow"
```

### Mocking IBKR Gateway (No Real Connection)

Tests use fixtures to mock IBKR:

```python
# In tests/conftest.py:
@pytest.fixture
def mock_ib():
    """Mock ib-insync client"""
    with patch("ibkr_core.client.IB") as mock:
        yield mock
```

All tests use mock by default (paper mode + no real network calls).

---

## Side Effects (System Boundaries)

### Where This Code Talks to the Outside World

| System | Direction | Purpose | Recoverable? |
|--------|-----------|---------|-------------|
| **IBKR Gateway** (port 4002) | OUT | Market data, orders, account status | ✅ Yes (retry) |
| **IBKR Live/Paper** | OUT (via Gateway) | Order execution, real money (if enabled) | ❌ No (trade irreversible) |
| **SQLite (audit.db)** | IN/OUT | Audit trail (append only) | ✅ Yes (re-append) |
| **Filesystem** | IN | Read .env config | ✅ Yes (reload config) |
| **Filesystem** | IN | Read LIVE_TRADING_OVERRIDE_FILE | ✅ Yes (create file) |
| **Filesystem** | OUT | Write logs | ✅ Yes (re-write) |
| **HTTP (REST API)** | IN | Receive requests | ✅ Yes (retry from client) |
| **HTTP (REST API)** | OUT | Send responses | ⚠️ Partial (response may fail after order placed) |
| **stdio (MCP)** | IN/OUT | Claude requests/responses | ✅ Yes (retry from Claude) |

### Critical Side Effects (Non-Recoverable)

**Once an order is placed, it cannot be unplaced:**

1. **Paper Mode**: Simulated (no side effect)
2. **Live Mode**: Real order at IBKR
   - Cannot undo (only cancel)
   - Cannot replay (idempotency prevents duplication)
   - Audit trail is permanent
   - Fills affect real account balance

**Safeguard**: Five safety gates prevent accidental live orders.

### State Management

| State | Persistence | Lifetime | Mutation |
|-------|-------------|----------|----------|
| **Config** | .env | Session | Immutable (validate at startup) |
| **Contract Cache** | Memory | Session | Append-only (no deletes/updates) |
| **Market Quotes** | Memory (temporary) | ~1 second | Overwritten on new quote |
| **Orders** | SQLite audit.db | Forever | Append-only (no deletes/updates) |
| **Account Balance** | IBKR servers | Forever | Updated by trades |

---

## Maintenance & Operations

### Log Files

```bash
# Logs are written to:
# - stdout (console)
# - (Optional) File at LOG_FILE path in .env

# View logs with:
poetry run ibkr-gateway start-api 2>&1 | tee app.log

# Or use tail (real-time):
tail -f app.log
```

### Audit Trail (Database)

```bash
# Access SQLite directly:
sqlite3 data/audit.db

# View orders:
sqlite> SELECT orderId, symbol, action, status, timestamp FROM orders LIMIT 10;

# View audit log:
sqlite> SELECT correlation_id, orderId, action, timestamp FROM audit LIMIT 10;

# Export as CSV:
sqlite> .mode csv
sqlite> .output audit_export.csv
sqlite> SELECT * FROM orders;
```

### Monitoring Checklist

**Daily**:

- [ ] Healthcheck passes
- [ ] No error logs
- [ ] IBKR Gateway connected

**Weekly**:

- [ ] All 635 tests pass
- [ ] Audit trail integrity verified
- [ ] No stale processes

**Monthly**:

- [ ] Review audit trail for anomalies
- [ ] Check disk space (logs, audit.db)
- [ ] Verify backups of audit.db

---

## Emergency Procedures

### Issue: IBKR Gateway Unresponsive

```bash
# 1. Check if IBKR Gateway is running
netstat -an | grep 4002

# 2. Restart IBKR Gateway
# (Open TWS or Gateway app, Settings → API → Enable)

# 3. Re-run healthcheck
poetry run ibkr-gateway healthcheck

# 4. If still fails, check firewall
# (Ensure port 4002 is not blocked)
```

### Issue: API Server Won't Start

```bash
# Check if port 8000 is in use:
lsof -i :8000  # macOS/Linux
netstat -ano | findstr :8000  # Windows

# Kill existing process:
kill -9 <PID>  # macOS/Linux
taskkill /PID <PID> /F  # Windows

# Restart:
poetry run ibkr-gateway start-api
```

### Issue: Tests Fail

```bash
# 1. Check Python version
python --version  # Must be >= 3.10

# 2. Reinstall dependencies
poetry install --no-cache

# 3. Run single failing test with verbose output
poetry run pytest tests/unit/test_config.py::test_X -vvv

# 4. Check for stale *.pyc files
find . -name "*.pyc" -delete

# 5. Clear pytest cache
poetry run pytest --cache-clear tests/

# 6. If all else fails:
poetry env remove $(python -c "import sys; print(sys.version_info[0])")
poetry install
```

### Issue: Order Stuck in "PENDING" Status

```bash
# This should not happen (orders are simulated or filled immediately)
# But if it does:

# 1. Check order status via API:
curl http://localhost:8000/api/orders/<orderId>/status

# 2. Try cancel:
curl -X POST http://localhost:8000/api/orders/<orderId>/cancel

# 3. Check audit trail:
sqlite3 data/audit.db
sqlite> SELECT * FROM orders WHERE orderId = '<orderId>';

# 4. If still stuck, contact IBKR support
```

---

## Code Quality & Git Workflow

### Before Committing

```bash
# 1. Run all tests
poetry run pytest tests/ -v

# 2. Check for lint (optional; no linter configured)
# poetry run black --check .
# poetry run flake8 .

# 3. Verify .context/ is updated if code changes
# (Check 00_INDEX.md, 01_RULES.md, 03_DECISIONS.md)

# 4. Commit
git add .
git commit -m "Add feature X"

# 5. Push
git push
```

### Deployment (Manual)

```bash
# 1. Tag release
git tag -a v0.2.0 -m "Release 0.2.0"
git push --tags

# 2. Deploy to production
# (Copy files, restart service, run tests)

# 3. Monitor logs
tail -f app.log
```

---

## Performance & Scalability

### Current Limits

| Metric | Current | Limit | Action |
|--------|---------|-------|--------|
| **Concurrent Requests** | 1,000s | IBKR limit | Contact IBKR for more |
| **Order Placement Rate** | ~10/sec | IBKR limit | Rate limit, queue orders |
| **Contract Cache Size** | ~10,000 | Memory | OK (fits in 1 GB) |
| **Audit Database Size** | grows ~100 KB/day | Disk | Archive monthly |

### Optimization Tips

```bash
# 1. Use mcp_server for bulk queries (batch API calls)
# 2. Cache quotes locally if possible (don't over-request)
# 3. Archive audit.db monthly to archive/ folder
# 4. Use integration tests sparingly (slow; use mocks)

# Example: Batch quotes
# ❌ Inefficient: 100 API calls
for symbol in symbols:
    quote = get_quote(symbol)

# ✅ Efficient: 1 batch call (if API supports it)
quotes = get_quotes(symbols)
```

---

## Context Maintenance (Why .context/ Matters)

Any change to this system that affects:

- ✅ Runtime behavior (new endpoint, new order type)
- ✅ Database schema (new column, index)
- ✅ Safety rules (new gate, config change)
- ✅ External integrations (new API, new database)
- ✅ Operational procedures (new deployment step)

**MUST UPDATE .context/ FILES:**

1. [00_INDEX.md](.context/00_INDEX.md) - Update repo map or entry points
2. [01_RULES.md](.context/01_RULES.md) - Add new invariants
3. [03_DECISIONS.md](.context/03_DECISIONS.md) - Log decision + rationale
4. Other files as needed

**PR Review Checklist:**

- ✅ Code changed? → .context/ changed?
- ✅ Database schema changed? → 01_RULES.md updated?
- ✅ API endpoint added? → 00_INDEX.md updated?
- ✅ Safety rule added? → 01_RULES.md updated?

**If .context/ is stale, the PR is INCOMPLETE.**

---

## Code Patterns & Style Guide

### Python Style

- **PEP 8**: Core style guide
- **Type hints**: All function signatures must have type hints
- **Docstrings**: Google-style for all public functions/classes
- **Line length**: Max 100 characters (Black formatter)

### Naming Conventions

```python
# Functions: snake_case
def place_order(spec: OrderSpec) -> OrderResult:
    pass

# Constants: UPPER_CASE
DEFAULT_TIMEOUT_SECONDS = 30
TRADING_DISABLED_ERROR = "Orders are disabled"

# Classes: PascalCase
class AccountSummary(BaseModel):
    pass

# Private: _leading_underscore
def _validate_internal(spec: OrderSpec) -> bool:
    pass

# Private attributes: self._leading_underscore
class Client:
    def __init__(self):
        self._executor = ThreadPoolExecutor(max_workers=1)
```

### Error Handling (Required Pattern)

```python
# ✅ REQUIRED: Catch specific exceptions, log with correlation_id, raise
try:
    contract = resolve_contract(symbol)
except ContractResolutionError as e:
    logger.error(f"[{correlation_id}] Contract resolution failed: {e}", 
                 extra={"correlation_id": correlation_id})
    raise

# ❌ FORBIDDEN: Silent pass or bare except
try:
    place_order(spec)
except Exception:
    pass  # NO!
```

### Logging Pattern (Required)

```python
# Always include correlation_id
from loguru import logger

logger.info(
    f"[{correlation_id}] Order placed: {orderId}",
    extra={
        "correlation_id": correlation_id,
        "orderId": orderId,
        "symbol": symbol
    }
)
```

### Async/Executor Pattern (Required)

```python
# ✅ CORRECT: Use executor for blocking IBKR calls
async def get_quote(symbol: str) -> Quote:
    loop = asyncio.get_event_loop()
    contract = await loop.run_in_executor(
        executor,
        resolve_contract_sync,
        symbol
    )
    quote = await loop.run_in_executor(
        executor,
        get_quote_sync,
        contract
    )
    return quote

# ❌ FORBIDDEN: Blocking call in async function
async def get_quote_bad(symbol: str):
    contract = resolve_contract_sync(symbol)  # BLOCKS EVENT LOOP!
    return contract
```

---

## Related Files

- [00_INDEX.md](.context/00_INDEX.md) - System map and entry points
- [01_RULES.md](.context/01_RULES.md) - Non-negotiable invariants
- [03_DECISIONS.md](.context/03_DECISIONS.md) - Why decisions were made
- [05_RUNBOOK.md](.context/05_RUNBOOK.md) - Detailed troubleshooting
- [06_TESTING.md](.context/06_TESTING.md) - Test strategy and fixtures
