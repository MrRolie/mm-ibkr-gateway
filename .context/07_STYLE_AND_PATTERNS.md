# 07_STYLE_AND_PATTERNS.md: Code Conventions & Best Practices

## Python Style Guide

### Adopted Standards

- **PEP 8**: Core style
- **Black**: Formatter (100 character line length)
- **isort**: Import organization (black profile)
- **Type hints**: All function signatures must have type hints
- **Docstrings**: Google-style for all public functions/classes

### Running Formatters

```bash
# Format code (black + isort)
poetry run black ibkr_core/ api/ mcp_server/
poetry run isort ibkr_core/ api/ mcp_server/

# Check without modifying
poetry run black --check ibkr_core/
poetry run flake8 ibkr_core/

# Type checking
poetry run mypy ibkr_core/ api/
```

---

## Naming Conventions

### Variables & Functions

```python
# Functions: snake_case
def place_order(spec: OrderSpec) -> OrderResult:
    pass

# Constants: UPPER_CASE
TRADING_DISABLED_ERROR = "Orders are disabled"
DEFAULT_TIMEOUT_SECONDS = 30

# Class names: PascalCase
class AccountSummary(BaseModel):
    pass

# Private functions: _leading_underscore
def _validate_internal(spec: OrderSpec) -> bool:
    pass

# Private attributes: self._leading_underscore
class Client:
    def __init__(self):
        self._executor = ThreadPoolExecutor(max_workers=1)
```

### Module Organization

```python
# Imports at top (sorted by isort)
from datetime import datetime
from typing import Dict, List, Optional

# Constants
DEFAULT_TIMEOUT = 30
SUPPORTED_ORDER_TYPES = {"MKT", "LMT", "STP", "STP_LMT"}

# Exceptions
class OrderError(Exception):
    pass

# Pydantic models
class OrderSpec(BaseModel):
    pass

# Main functions (public API)
async def place_order(spec: OrderSpec) -> OrderResult:
    pass

# Private helpers
def _validate_spec(spec: OrderSpec) -> None:
    pass
```

---

## Type Hints

### Comprehensive Type Annotations

```python
# CORRECT: Full type hints
from typing import Dict, List, Optional
from datetime import datetime

async def get_positions(
    account_id: str,
    filter_symbol: Optional[str] = None
) -> List[Position]:
    """Fetch positions for account.
    
    Args:
        account_id: IBKR account identifier
        filter_symbol: Optional symbol to filter by
        
    Returns:
        List of Position objects for the account
        
    Raises:
        ConnectionError: If IBKR Gateway unreachable
        AccountError: If account not found
    """
    pass

# Type hints for class attributes
class Client:
    """IBKR client facade."""
    
    _executor: ThreadPoolExecutor
    _ib: ib_insync.IB
    _contract_cache: Dict[str, Contract]
    
    def __init__(self):
        self._executor = ThreadPoolExecutor(max_workers=1)
        self._ib = ib_insync.IB()
        self._contract_cache: Dict[str, Contract] = {}
```

### Generic Types

```python
from typing import Dict, List, Tuple, Union

# Dictionary with key/value types
positions: Dict[str, Position] = {}

# Union types (when multiple possible)
result: Union[OrderResult, OrderError]

# Tuple with specific types
trade_info: Tuple[str, int, float] = ("AAPL", 100, 150.25)

# Optional (preferred over Union[X, None])
symbol: Optional[str] = None  # Good
symbol: Union[str, None] = None  # Bad
```

---

## Error Handling

### Exception Hierarchy

```python
# Base exception
class IBKRException(Exception):
    """Base for all IBKR-related errors."""
    pass

# Domain-specific exceptions
class ContractResolutionError(IBKRException):
    """Failed to resolve symbol to contract."""
    pass

class OrderError(IBKRException):
    """Order-related error."""
    pass

class TradingDisabledError(OrderError):
    """Order placement disabled by config."""
    pass
```

### Error Handling Pattern

```python
# Catch and re-raise with context
try:
    quote = await client.get_quote(spec)
except ib_insync.ContractError as e:
    raise ContractResolutionError(
        f"Failed to resolve {spec.symbol}: {str(e)}"
    ) from e

# Never swallow exceptions silently
# BAD:
try:
    risky_operation()
except Exception:
    pass  # Silently fails!

# GOOD:
try:
    risky_operation()
except SpecificException as e:
    logger.warning(f"Operation failed: {e}")
    # Re-raise or return safe default
    raise
```

### API Error Mapping

```python
# In api/errors.py
def map_ibkr_exception(e: IBKRException) -> Tuple[int, APIError]:
    """Map domain exception to HTTP status."""
    if isinstance(e, ContractResolutionError):
        return 422, APIError(
            code="CONTRACT_RESOLUTION_FAILED",
            message=str(e),
            status_code=422
        )
    elif isinstance(e, OrderValidationError):
        return 400, APIError(
            code="ORDER_VALIDATION_FAILED",
            message=str(e),
            status_code=400
        )
    else:
        return 500, APIError(
            code="INTERNAL_ERROR",
            message="Unexpected error",
            status_code=500
        )
```

---

## Async/Await Pattern

### Executor for Blocking Calls

```python
# IBKR operations run in dedicated executor thread
import asyncio
from concurrent.futures import ThreadPoolExecutor

class Client:
    def __init__(self):
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="IBKR")
    
    async def get_quote(self, spec: SymbolSpec) -> Quote:
        """Get market quote (blocking call in executor)."""
        loop = asyncio.get_event_loop()
        
        # Run blocking ib_insync call in executor
        quote = await loop.run_in_executor(
            self.executor,
            self._get_quote_sync,  # Blocking function
            spec
        )
        return quote
    
    def _get_quote_sync(self, spec: SymbolSpec) -> Quote:
        """Synchronous IBKR call (runs in executor thread)."""
        contract = self._ib.qualifyContracts(spec.to_ibkr_contract())[0]
        ticker = self._ib.reqMktData(contract)
        return ticker_to_quote(ticker)
```

### Async Context Managers

```python
from contextlib import asynccontextmanager

@asynccontextmanager
async def get_client():
    """Async context manager for client lifecycle."""
    client = await create_client()
    try:
        yield client
    finally:
        await client.close()

# Usage
async def main():
    async with get_client() as client:
        quote = await client.get_quote(spec)
        # Client automatically closed after block
```

---

## Logging Pattern

### Structured Logging with Correlation IDs

```python
import logging
from ibkr_core.logging_config import log_with_context, get_correlation_id

logger = logging.getLogger(__name__)

async def place_order(spec: OrderSpec) -> OrderResult:
    """Place order with structured logging."""
    # Log with automatic correlation ID
    logger.info(
        "Order placement started",
        extra={
            "symbol": spec.symbol,
            "action": spec.action,
            "quantity": spec.quantity,
            "correlation_id": get_correlation_id()
        }
    )
    
    try:
        result = await _place_order_internal(spec)
        logger.info(
            "Order placed successfully",
            extra={
                "orderId": result.order_id,
                "status": result.status,
                "correlation_id": get_correlation_id()
            }
        )
        return result
    except OrderError as e:
        logger.error(
            f"Order placement failed: {str(e)}",
            extra={
                "error": str(e),
                "symbol": spec.symbol,
                "correlation_id": get_correlation_id()
            }
        )
        raise
```

### Log Levels

- **DEBUG**: Contract cache hits, connection state changes
- **INFO**: Order placements, fills, account updates
- **WARNING**: Config warnings (live mode enabled), minor issues
- **ERROR**: Order rejections, connection losses, validation failures
- **CRITICAL**: IBKR Gateway unreachable, unrecoverable state

---

## Pydantic Model Pattern

### Field Validation

```python
from pydantic import BaseModel, Field, field_validator

class OrderSpec(BaseModel):
    """Order specification with validation."""
    
    symbol: str = Field(..., min_length=1, max_length=10)
    action: str = Field(..., description="BUY or SELL")
    quantity: int = Field(..., ge=1, description="Quantity >= 1")
    orderType: str = Field(..., description="MKT, LMT, STP, STP_LMT, MOC, OPG")
    limitPrice: Optional[float] = Field(None, gt=0)
    
    @field_validator("action")
    @classmethod
    def validate_action(cls, v: str) -> str:
        if v not in {"BUY", "SELL"}:
            raise ValueError(f"action must be BUY or SELL, got {v}")
        return v
    
    @field_validator("orderType")
    @classmethod
    def validate_order_type(cls, v: str) -> str:
        allowed = {"MKT", "LMT", "STP", "STP_LMT", "MOC", "OPG"}
        if v not in allowed:
            raise ValueError(f"orderType must be one of {allowed}, got {v}")
        return v

# Validation happens automatically on instantiation
spec = OrderSpec(symbol="AAPL", action="BUY", quantity=100, orderType="MKT")
# ✓ Valid

try:
    bad_spec = OrderSpec(symbol="AAPL", action="INVALID", quantity=100, orderType="MKT")
except ValueError as e:
    print(e)  # "action must be BUY or SELL, got INVALID"
```

### JSON Schema & Serialization

```python
class Quote(BaseModel):
    """Market quote."""
    
    symbol: str
    bid: float = Field(..., ge=0)
    ask: float = Field(..., ge=0)
    
    model_config = ConfigDict(json_schema_extra={
        "examples": [
            {
                "symbol": "AAPL",
                "bid": 150.25,
                "ask": 150.26
            }
        ]
    })

# JSON serialization
quote = Quote(symbol="AAPL", bid=150.25, ask=150.26)
json_str = quote.model_dump_json()  # Serialize to JSON string
dict_obj = quote.model_dump()       # Serialize to dict

# JSON parsing
quote_from_json = Quote.model_validate_json(json_str)
quote_from_dict = Quote.model_validate(dict_obj)
```

---

## API Endpoint Pattern

### Request/Response Handler

```python
from fastapi import FastAPI, Depends
from api.dependencies import get_ibkr_client

app = FastAPI()

@app.post("/api/orders/place")
async def place_order_endpoint(
    request: OrderSpecRequest,
    client: IBKRClient = Depends(get_ibkr_client)
) -> OrderResult:
    """Place an order.
    
    Args:
        request: Order specification from client
        client: IBKR client (injected)
        
    Returns:
        OrderResult with status and details
        
    Raises:
        422: Validation error (bad input)
        503: IBKR Gateway unreachable
    """
    # Pydantic validates request automatically
    # (400 if invalid schema)
    
    try:
        result = await client.place_order(
            symbol_spec=SymbolSpec.from_request(request),
            action=request.action,
            quantity=request.quantity,
            order_type=request.orderType,
            limit_price=request.limitPrice
        )
        return result
    except IBKRException as e:
        status_code, error = map_ibkr_exception(e)
        raise HTTPException(status_code=status_code, detail=error.model_dump())
```

---

## Database Pattern

### Context Manager for Connections

```python
from contextlib import contextmanager
import sqlite3

@contextmanager
def get_db_connection(db_path: Optional[str] = None):
    """Get a database connection context manager.
    
    Usage:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM orders")
    """
    path = db_path or get_db_path()
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row  # Access columns by name
    
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

# Usage
def log_order_action(order_detail: OrderDetail):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO audit_log (correlation_id, timestamp, event_type, event_data)
            VALUES (?, ?, ?, ?)
        """, (
            get_correlation_id(),
            datetime.utcnow().isoformat() + "Z",
            "ORDER_PLACED",
            order_detail.model_dump_json()
        ))
```

---

## Forbidden Patterns

### ❌ Never Do

1. **Use `float` for money**
   ```python
   # BAD
   commission = 5.99  # Precision loss
   
   # GOOD
   commission = Decimal("5.99")
   ```

2. **Use `datetime.now()` without `timezone.utc`**
   ```python
   # BAD
   timestamp = datetime.now().isoformat()  # Local time!
   
   # GOOD
   timestamp = datetime.now(timezone.utc).isoformat()
   ```

3. **Catch all exceptions**
   ```python
   # BAD
   try:
       risky_operation()
   except Exception:
       pass  # Masks bugs
   
   # GOOD
   try:
       risky_operation()
   except SpecificException as e:
       logger.error(f"Expected error: {e}")
       raise
   ```

4. **Trust environment variables without validation**
   ```python
   # BAD
   mode = os.environ.get("TRADING_MODE", "paper")
   
   # GOOD
   config = get_config()  # Validates at startup
   config.validate()  # Raises if invalid
   ```

5. **Modify audit logs**
   ```python
   # BAD
   cursor.execute("UPDATE audit_log SET status='CORRECTED' WHERE id=?")
   
   # GOOD
   # Append-only: only INSERT, never UPDATE/DELETE
   cursor.execute("INSERT INTO audit_log ...")
   ```

6. **Use mutable default arguments**
   ```python
   # BAD
   def add_position(positions: List[Position] = []):  # Mutable default!
       positions.append(new_position)
   
   # GOOD
   def add_position(positions: Optional[List[Position]] = None):
       if positions is None:
           positions = []
       positions.append(new_position)
   ```

---

## Code Review Checklist

- [ ] Type hints on all function signatures
- [ ] Docstrings on public functions/classes
- [ ] Proper error handling (specific exceptions, not generic)
- [ ] No floats for money (Decimal instead)
- [ ] No `datetime.now()` without UTC timezone
- [ ] Logging includes correlation ID
- [ ] Tests written for new functionality
- [ ] No hardcoded secrets/credentials
- [ ] No mutable default arguments
- [ ] Imports sorted (isort black profile)
- [ ] Formatted with black (100 char lines)
- [ ] Passes mypy type checking
- [ ] Audit log unchanged (append-only)
- [ ] Context files updated if behavior changed

---

## Summary

- **Type hints**: Required on all function signatures
- **Docstrings**: Google-style, include Args/Returns/Raises
- **Logging**: Structured, correlation IDs, appropriate levels
- **Errors**: Specific exceptions, proper hierarchy, mapped to HTTP codes
- **Async**: Executor for blocking IBKR calls
- **Money**: Always Decimal, never float
- **Timestamps**: Always UTC, ISO 8601
- **Database**: Append-only, context managers, validation
- **Testing**: Comprehensive, deterministic, mocked external calls
