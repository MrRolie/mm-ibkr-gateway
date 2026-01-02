# 06_TESTING.md: Test Organization & Strategies

## Test Overview

- **Total tests**: 635 (all passing as of last run)
- **Framework**: pytest
- **Async support**: pytest-asyncio
- **Coverage**: Target 80%+ for core modules (`ibkr_core/`, `api/`)
- **Runtime**: ~30 seconds for full suite

---

## Test Markers & Organization

### Standard Markers

```python
# In pyproject.toml
[tool.pytest.ini_options]
markers = [
    "integration: tests requiring live IBKR Gateway connection",
    "slow: tests taking > 1 second",
]
```

### Running Tests

```bash
# All tests
poetry run pytest tests/ -v

# Exclude integrations (unit tests only, ~20 sec)
poetry run pytest tests/ -v -m "not integration"

# Only integrations (requires IBKR Gateway running)
poetry run pytest tests/ -v -m "integration"

# Only slow tests
poetry run pytest tests/ -v -m "slow"

# Single test file
poetry run pytest tests/test_config.py -v

# Single test function
poetry run pytest tests/test_config.py::TestTradingMode::test_valid_paper_mode -v

# With coverage
poetry run pytest tests/ --cov=ibkr_core --cov=api --cov-report=html
```

---

## Test Structure by Module

### `tests/test_models.py` (150+ tests)

**Scope**: Pydantic model validation

**Tests**:

- `TestSymbolSpec`: Symbol validation (security type, currency, etc.)
- `TestQuote`: Quote model parsing and edge cases
- `TestBar`: Historical bar validation
- `TestPosition`: Position calculation (unrealizedPnL, percentPnL)
- `TestAccountSummary`: Account field validation
- `TestOrderResult`: Order status and fill tracking
- `TestOrderDetail`: Full order lifecycle model

**Key Invariants Tested**:

- Negative prices rejected
- Order quantities >= 1
- Security types in allowed set
- Serialization round-trip (model → JSON → model)

---

### `tests/test_config.py` (35+ tests)

**Scope**: Configuration loading, validation, safety gates

**Tests**:

- `TestConfigDefaults`: Default values loaded correctly
- `TestTradingMode`: `TRADING_MODE` validation (paper, live, typos)
- `TestOrdersEnabled`: `ORDERS_ENABLED` boolean parsing
- `TestLiveTradingOverride`: Override file requirement for live mode
- `TestTradingDisabledError`: Error raised when placing orders while disabled
- `TestInvalidConfiguration`: Port validation, invalid values

**Key Safety Tests**:

- ✅ `test_live_mode_with_orders_enabled_requires_override`: Override file must exist
- ✅ `test_invalid_trading_mode`: Raises error on typo
- ✅ `test_check_trading_enabled_raises_when_disabled`: Prevents order placement in paper mode

**How to Run**:

```bash
poetry run pytest tests/test_config.py -v
```

---

### `tests/test_contracts.py` (20+ tests)

**Scope**: Contract resolution and caching

**Tests**:

- `TestResolveContract`: Basic resolution (symbol → IBKR contract)
- `TestContractCache`: Cache hit/miss behavior
- `TestCacheExpiration`: Stale cache handling
- `TestResolutionErrors`: Delisted/invalid symbols

**Key Invariants Tested**:

- Same symbol always returns same contract (in-memory cache)
- Cache respects exchange/currency (cache key)
- Deleted symbols result in appropriate errors

---

### `tests/test_market_data.py` (30+ tests)

**Scope**: Quote and historical bar fetching

**Tests**:

- `TestGetQuote`: Live quote retrieval
- `TestGetBars`: Historical bar fetching (1 min, 1 day, etc.)
- `TestMarketDataErrors`: Connection failures, invalid symbols
- `TestQuoteParsing`: Bid/ask/last price normalization

**Marked as**: `@pytest.mark.integration` (requires IBKR)

**How to Test (with IBKR running)**:

```bash
poetry run pytest tests/test_market_data.py -v -m integration
```

---

### `tests/test_account_*.py` (100+ tests)

**Scope**: Account operations (summary, positions, P&L)

**Tests**:

- `test_account_summary.py`: `get_account_summary()` validation
- `test_account_positions.py`: `get_positions()`, position calculations
- `test_account_pnl.py`: `get_pnl()`, P&L aggregation, timeframe handling

**Key Invariants Tested**:

- `netLiquidation = cash + sum(position.marketValue)`
- `unrealizedPnL = sum(position.unrealizedPnL)`
- Positions keyed by symbol (no duplicates)

**Example Test**:

```python
def test_get_account_summary_cash_non_negative():
    """Cash balance must be >= 0."""
    summary = get_account_summary()
    assert summary.cash >= 0
```

---

### `tests/test_orders*.py` (150+ tests)

**Scope**: Order lifecycle (preview, place, cancel, status)

**Files**:

- `test_orders_validation.py`: Input validation
- `test_orders_advanced.py`: Complex orders (bracket, trailing stop)
- `test_orders_integration.py`: Full workflow (place → fill → cancel)
- `test_orders_safety.py`: Safety gate enforcement

**Key Safety Tests**:

- ✅ `test_order_placement_raises_when_disabled`: `ORDERS_ENABLED=false` → simulated
- ✅ `test_deterministic_order_id`: Same order always gets same ID
- ✅ `test_negative_quantity_rejected`: Quantity validation
- ✅ `test_limit_order_requires_limit_price`: Price validation

**Example Test**:

```python
def test_place_order_returns_simulated_in_paper_mode():
    """Orders are simulated when TRADING_MODE=paper."""
    result = place_order(
        symbol_spec=SymbolSpec(symbol="AAPL", securityType="STK"),
        action="BUY",
        quantity=100,
        order_type="MKT"
    )
    assert result.status == "SIMULATED"  # Never "ACCEPTED" or "FILLED"
```

---

### `tests/test_api_*.py` (80+ tests)

**Scope**: REST API endpoints

**Files**:

- `test_api_health.py`: Health check endpoint
- `test_api_market_data.py`: `/api/market/quote`, `/api/market/historical`
- `test_api_account.py`: Account endpoints
- `test_api_orders.py`: Order endpoints

**Mocking Strategy**: Use `@mock.patch` to simulate IBKR responses without live connection.

**Example Test**:

```python
@mock.patch("ibkr_core.client.get_quote")
def test_api_quote_endpoint_returns_200(mock_get_quote):
    mock_get_quote.return_value = Quote(symbol="AAPL", bid=150.0, ask=150.1, ...)
    
    response = client.get("/api/market/quote?symbol=AAPL&securityType=STK")
    assert response.status_code == 200
    assert response.json()["symbol"] == "AAPL"
```

---

### `tests/test_mcp_*.py` (30+ tests)

**Scope**: MCP tool server

**Files**:

- `test_mcp_tools.py`: Tool definitions and responses
- `test_mcp_errors.py`: Error mapping (domain → MCP)

**Key Tests**:

- Tool parameters validated
- Response format correct (JSON-RPC)
- Errors mapped to MCP error codes

---

### `tests/test_persistence_audit.py` (30+ tests)

**Scope**: SQLite audit log

**Tests**:

- `TestAuditLogInsertion`: Rows inserted correctly
- `TestAuditLogQuerying`: Query functions work
- `TestIdempotency`: Duplicate inserts rejected by unique constraint
- `TestSchema`: Table structure correct

**Key Invariant Tested**:

```python
def test_unique_constraint_prevents_duplicates():
    """Unique(correlation_id, event_type, timestamp) prevents duplicates."""
    # Same correlation_id + event_type + timestamp → second insert fails
    log_order_action(order1, config)
    with pytest.raises(sqlite3.IntegrityError):
        log_order_action(order1, config)  # Duplicate
```

---

### `tests/test_simulation*.py` (50+ tests)

**Scope**: Paper trading simulation

**Files**:

- `test_simulation_client.py`: Simulated order placement
- `test_simulation_orders.py`: Order fill logic
- `test_simulation_integration.py`: Full workflow in paper mode

**Key Tests**:

- Simulated orders return immediately
- Fill price matches market quote (or limit if better)
- Quantities tracked correctly

---

## Running Tests in CI/CD

### GitHub Actions (`.github/workflows/ci.yml`)

```yaml
name: CI
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.10'
      - run: poetry install
      - run: poetry run pytest tests/ -v -m "not integration" --cov
      - uses: codecov/codecov-action@v3
```

### Local Pre-Commit Hook

```bash
# Create .git/hooks/pre-commit
#!/bin/bash
poetry run pytest tests/ -m "not integration" -q
if [ $? -ne 0 ]; then
    echo "Tests failed. Commit aborted."
    exit 1
fi
```

---

## Test Determinism

### Requirement: Tests Must Be Deterministic

All unit tests must produce identical results on repeated runs, regardless of:

- System time
- File system state
- Previous test runs

### Implementation

1. **Mock external calls**:

   ```python
   @mock.patch("ibkr_core.client.ibkr_get_quote")
   def test_quote(mock_quote):
       mock_quote.return_value = Quote(...)  # Hardcoded
   ```

2. **Use fixed timestamps**:

   ```python
   @mock.patch("datetime.now")
   def test_order_timestamp(mock_now):
       mock_now.return_value = datetime(2025, 1, 1, 12, 0, 0)
   ```

3. **Seed random generators**:

   ```python
   def test_with_seed():
       random.seed(42)
       # Test uses deterministic randomness
   ```

4. **Clean database state**:

   ```python
   @pytest.fixture
   def clean_db():
       # Drop and recreate audit_log table
       init_db(":memory:")  # Use in-memory DB for tests
       yield
       # Cleanup
   ```

---

## Critical Invariant Tests

These tests **must always pass**:

| Test | File | Ensures |
|------|------|---------|
| `test_trading_mode_validation` | `test_config.py` | Config validates at startup |
| `test_override_file_required` | `test_config.py` | Live trading gated |
| `test_orders_disabled_by_default` | `test_config.py` | Safe default |
| `test_order_placement_raises_when_disabled` | `test_orders_safety.py` | Can't bypass gates |
| `test_deterministic_order_id` | `test_orders_advanced.py` | Order idempotency |
| `test_position_pnl_calculation` | `test_account_positions.py` | P&L accuracy |
| `test_unique_constraint_prevents_duplicates` | `test_persistence_audit.py` | Audit trail integrity |
| `test_decimal_precision_preserved` | `test_models.py` | No float rounding errors |

---

## Debugging Failed Tests

### Verbose Output

```bash
# Show all print() statements and logs
poetry run pytest tests/test_orders.py::test_place_order -v -s

# Full traceback on error
poetry run pytest tests/test_orders.py -v --tb=long
```

### Debugging with PDB

```python
def test_order_placement():
    import pdb; pdb.set_trace()  # Breakpoint
    place_order(spec)
```

```bash
poetry run pytest tests/test_orders.py::test_order_placement -v -s
# Drops into debugger
```

### Running Single Test

```bash
poetry run pytest tests/test_orders.py::TestOrderValidation::test_negative_quantity_rejected -v
```

---

## Code Coverage

### Check Coverage

```bash
poetry run pytest tests/ --cov=ibkr_core --cov=api --cov-report=html
open htmlcov/index.html
```

### Coverage Goals

- `ibkr_core/`: 80%+
- `api/`: 75%+
- `mcp_server/`: 60%+ (thin wrapper layer)
- Global: 70%+

### Exclude from Coverage

```python
# Don't count demo code
# Add to pyproject.toml:
[tool.coverage.run]
omit = ["*/demo.py", "*/cli.py"]  # CLI code is integration-tested manually
```

---

## Summary

- **635 tests** covering models, config, contracts, market data, accounts, orders, API, MCP, persistence, simulation
- **All unit tests** mock external dependencies (no real IBKR calls)
- **Integration tests** marked and runnable only with IBKR Gateway
- **Critical invariants** have dedicated tests that must never fail
- **Deterministic**: Identical results on repeated runs
- **Fast**: Full suite runs in ~30 seconds
