# Development Guide

## Setup

```bash
# Clone and install
git clone <repo>
cd mm-ibkr-gateway
poetry install

# Copy environment file
cp .env.example .env

# Run tests (no IBKR Gateway needed)
poetry run pytest
```

## Testing

### Run All Tests
```bash
poetry run pytest
```

### Run Specific Test Files
```bash
# Unit tests for a module
poetry run pytest tests/test_orders.py -v

# All Phase 8 tests
poetry run pytest tests/test_metrics*.py tests/test_persistence*.py tests/test_simulation*.py -v
```

### Test Categories

| Category | Files | Gateway Required |
|----------|-------|------------------|
| Unit tests | `test_*.py` (most) | No |
| Simulation tests | `test_simulation_*.py` | No |
| E2E tests | `test_e2e_api.py` | Yes |

### Running Without IBKR Gateway

Use simulation mode for development:
```bash
export IBKR_MODE=simulation
poetry run pytest
```

Or in code:
```python
from ibkr_core.simulation import SimulatedIBKRClient

client = SimulatedIBKRClient()
client.connect()  # Always succeeds
quote = client.get_quote("AAPL")  # Returns synthetic quote
```

## Code Style

- **Formatter**: Black (line length 100)
- **Linter**: Ruff
- **Type hints**: Required for public APIs

```bash
# Format
poetry run black .

# Lint
poetry run ruff check .
```

## Adding New Features

### 1. New API Endpoint

```python
# In api/server.py
@app.post("/new-endpoint", response_model=ResponseModel)
async def new_endpoint(
    request: RequestModel,
    ctx: RequestContext = Depends(get_request_context),
    client_manager: IBKRClientManager = Depends(get_client_manager),
    _: str = Depends(verify_api_key),
):
    def _operation(client):
        # Your IBKR operation here
        return result

    return await execute_ibkr_operation(client_manager, _operation, ctx)
```

### 2. New Core Function

```python
# In ibkr_core/your_module.py
from ibkr_core.logging_config import log_with_context, get_correlation_id
from ibkr_core.persistence import record_audit_event

def your_function(client: IBKRClient, params: YourParams) -> YourResult:
    """Docstring with Args, Returns, Raises."""
    log_with_context(logger, logging.INFO, "Starting operation", param=params.value)

    # Your logic here

    # Record audit event if important
    record_audit_event("YOUR_EVENT", {"param": params.value})

    return result
```

### 3. New Test

```python
# In tests/test_your_module.py
import pytest
from ibkr_core.your_module import your_function

class TestYourFunction:
    def test_basic_case(self):
        # Arrange
        # Act
        # Assert
        pass

    def test_edge_case(self):
        pass
```

## Common Patterns

### Correlation ID Propagation

```python
from ibkr_core.logging_config import get_correlation_id, set_correlation_id

# Set at request entry
set_correlation_id(str(uuid.uuid4()))

# Get anywhere in call stack
correlation_id = get_correlation_id()

# Automatically included in all log messages
log_with_context(logger, logging.INFO, "Operation completed")
# Output: {"correlation_id": "abc-123", "message": "Operation completed", ...}
```

### Metrics Recording

```python
from ibkr_core.metrics import record_api_request, record_ibkr_operation

# API request (middleware does this automatically)
record_api_request("/endpoint", "POST", 200, 0.05)

# IBKR operation
record_ibkr_operation("place_order", "success", 0.25)
```

### Audit Events

```python
from ibkr_core.persistence import record_audit_event

record_audit_event(
    event_type="ORDER_SUBMIT",
    event_data={"symbol": "AAPL", "side": "BUY", "quantity": 100},
    correlation_id=get_correlation_id(),
    account_id="DU12345",
)
```

## Debugging

### Enable Debug Logging

```bash
export LOG_LEVEL=DEBUG
export LOG_FORMAT=text  # Human-readable
```

### Query Audit Database

```bash
# View recent events
poetry run python scripts/query_audit_log.py --limit 20 -v

# Filter by account
poetry run python scripts/query_audit_log.py --account DU12345

# Export orders
poetry run python scripts/export_order_history.py --output orders.csv
```

### Check Metrics

```bash
curl http://localhost:8000/metrics | jq
```

## Environment Variables Reference

| Variable | Default | Description |
|----------|---------|-------------|
| `TRADING_MODE` | `paper` | `paper` or `live` |
| `ORDERS_ENABLED` | `false` | Enable order placement |
| `IBKR_MODE` | - | Override to `simulation` |
| `IBKR_GATEWAY_HOST` | `127.0.0.1` | Gateway hostname |
| `PAPER_GATEWAY_PORT` | `4002` | Paper trading port |
| `LIVE_GATEWAY_PORT` | `4001` | Live trading port |
| `API_PORT` | `8000` | REST API port |
| `LOG_LEVEL` | `INFO` | DEBUG, INFO, WARNING, ERROR |
| `LOG_FORMAT` | `json` | `json` or `text` |
| `AUDIT_DB_PATH` | `./data/audit.db` | SQLite database path |
