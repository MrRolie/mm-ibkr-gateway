# 03_DATA_CONTRACTS.md: Schemas, Keys, and Invariants

## Overview

This file defines all persisted and API-facing data structures, their schemas, unique constraints, and backward-compatibility rules.

---

## API Models (Pydantic)

All API request/response models live in `api/models.py`. These are derived from domain schemas in `docs/SCHEMAS.md`.

### Request Models

#### SymbolSpec

```python
class SymbolSpec(BaseModel):
    symbol: str                      # Required: ticker, e.g. "AAPL"
    securityType: str                # Required: "STK", "FUT", "OPT", etc.
    exchange: Optional[str] = None   # Optional: "SMART", "GLOBEX"
    currency: Optional[str] = None   # Optional: "USD", "EUR"
    expiry: Optional[str] = None     # Optional: "2025-01-17" for derivatives
    strike: Optional[float] = None   # Optional: strike price for options
    right: Optional[str] = None      # Optional: "C" (call) or "P" (put)
    multiplier: Optional[str] = None # Optional: multiplier string
```

**Validation**:

- `securityType` in {"STK", "ETF", "FUT", "OPT", "IND", "CASH", "CFD", "BOND", "FUND", "CRYPTO"}
- `right` in {"C", "P"} or None
- `expiry` matches `YYYY-MM-DD` if provided
- `strike` >= 0 if provided

**Example**:

```json
{"symbol": "AAPL", "securityType": "STK"}
{"symbol": "MES", "securityType": "FUT", "expiry": "2025-01-17"}
```

#### QuoteRequest

```python
class QuoteRequest(BaseModel):
    symbol: str
    securityType: str
    exchange: Optional[str] = None
    currency: Optional[str] = None
```

Alias for SymbolSpec in quote context.

#### HistoricalBarsRequest

```python
class HistoricalBarsRequest(BaseModel):
    symbol: str
    securityType: str
    exchange: Optional[str] = None
    currency: Optional[str] = None
    period: str = "1 day"          # "1 min", "5 mins", "1 hour", "1 day"
    durationStr: str = "1 Y"       # "1 D", "5 D", "1 M", "1 Y", "10 Y"
```

#### OrderSpecRequest

```python
class OrderSpecRequest(BaseModel):
    symbol: str
    securityType: str
    action: str                    # "BUY" or "SELL"
    quantity: int                  # >= 1
    orderType: str                 # "MKT", "LMT", "STP", "STP_LMT", "MOC", "OPG"
    limitPrice: Optional[float] = None
    stopPrice: Optional[float] = None
    timeInForce: str = "DAY"       # "DAY", "GTC", "IOC", "FOK"
    transmit: bool = True          # False = held locally (paper only)
```

**Validation**:

- `action` in {"BUY", "SELL"}
- `quantity` >= 1
- `orderType` in {"MKT", "LMT", "STP", "STP_LMT", "MOC", "OPG"}
- `timeInForce` in {"DAY", "GTC", "IOC", "FOK"}
- If `orderType == "LMT"`: `limitPrice` required and > 0
- If `orderType in {"STP", "STP_LMT"}`: `stopPrice` required and > 0

---

### Response Models

#### Quote

```python
class Quote(BaseModel):
    symbol: str
    conId: int
    bid: float >= 0
    ask: float >= 0
    last: float >= 0
    bidSize: float >= 0
    askSize: float >= 0
    lastSize: float >= 0
    volume: float >= 0
    timestamp: datetime            # ISO 8601 UTC
    source: str                    # "IBKR_REALTIME", "IBKR_DELAYED", "IBKR_FROZEN"
```

**Example**:

```json
{
  "symbol": "AAPL",
  "conId": 265598,
  "bid": 150.25,
  "ask": 150.26,
  "last": 150.255,
  "bidSize": 1000.0,
  "askSize": 500.0,
  "lastSize": 100.0,
  "volume": 50000000.0,
  "timestamp": "2025-01-01T09:35:00Z",
  "source": "IBKR_REALTIME"
}
```

#### Bar

```python
class Bar(BaseModel):
    symbol: str
    time: datetime                 # ISO 8601 UTC
    open: float >= 0
    high: float >= 0
    low: float >= 0
    close: float >= 0
    volume: float >= 0
    barSize: str                   # "1 min", "5 mins", "1 hour", "1 day"
    source: str = "IBKR_HISTORICAL"
```

**Example**:

```json
{
  "symbol": "SPY",
  "time": "2025-01-01T09:30:00Z",
  "open": 650.0,
  "high": 652.5,
  "low": 649.8,
  "close": 651.5,
  "volume": 5000000.0,
  "barSize": "1 day",
  "source": "IBKR_HISTORICAL"
}
```

#### Position

```python
class Position(BaseModel):
    accountId: str
    symbol: str
    securityType: str
    contractId: int
    quantity: float                # Positive = long, negative = short
    avgCost: float >= 0
    marketValue: float             # Can be negative for shorts
    unrealizedPnL: float
    percentPnL: float              # Percentage
    multiplier: float = 1.0
    currency: str
```

**Example**:

```json
{
  "accountId": "DU123456",
  "symbol": "AAPL",
  "securityType": "STK",
  "contractId": 265598,
  "quantity": 100.0,
  "avgCost": 150.00,
  "marketValue": 15025.00,
  "unrealizedPnL": 25.00,
  "percentPnL": 0.17,
  "multiplier": 1.0,
  "currency": "USD"
}
```

#### AccountSummary

```python
class AccountSummary(BaseModel):
    accountId: str
    currency: str                  # Base currency, e.g. "USD"
    netLiquidation: float >= 0
    cash: float >= 0
    buyingPower: float >= 0
    marginExcess: float            # Can be negative
    maintenanceMargin: float >= 0
    initialMargin: float >= 0
    grossPositionValue: float >= 0
```

**Example**:

```json
{
  "accountId": "DU123456",
  "currency": "USD",
  "netLiquidation": 100000.00,
  "cash": 50000.00,
  "buyingPower": 100000.00,
  "marginExcess": 5000.00,
  "maintenanceMargin": 20000.00,
  "initialMargin": 20000.00,
  "grossPositionValue": 50000.00
}
```

#### PnLDetail

```python
class PnLDetail(BaseModel):
    symbol: str
    realizedPnL: float
    unrealizedPnL: float
    totalPnL: float
    position: Optional[Position] = None
```

#### AccountPnL

```python
class AccountPnL(BaseModel):
    accountId: str
    totalRealizedPnL: float
    totalUnrealizedPnL: float
    totalPnL: float
    bySymbol: Dict[str, PnLDetail]  # Keyed by symbol
```

**Example**:

```json
{
  "accountId": "DU123456",
  "totalRealizedPnL": -125.50,
  "totalUnrealizedPnL": 2500.75,
  "totalPnL": 2375.25,
  "bySymbol": {
    "AAPL": {
      "symbol": "AAPL",
      "realizedPnL": 0.0,
      "unrealizedPnL": 25.00,
      "totalPnL": 25.00,
      "position": { ... }
    }
  }
}
```

#### OrderResult

```python
class OrderResult(BaseModel):
    orderId: int
    status: str                    # "SUBMITTED", "ACCEPTED", "FILLED", "SIMULATED", etc.
    symbol: str
    quantity: int
    filled: int
    remaining: int
    avgFillPrice: float
    message: Optional[str] = None
```

**Example**:

```json
{
  "orderId": 1001,
  "status": "ACCEPTED",
  "symbol": "AAPL",
  "quantity": 100,
  "filled": 0,
  "remaining": 100,
  "avgFillPrice": 0.0,
  "message": "Order accepted by broker"
}
```

#### OrderDetail

```python
class OrderDetail(BaseModel):
    orderId: int
    symbol: str
    securityType: str
    action: str                    # "BUY" or "SELL"
    quantity: int
    orderType: str
    status: str
    filled: int
    avgFillPrice: float
    commission: float
    timestamp: datetime            # ISO 8601 UTC
    configSnapshot: Dict[str, Any] # {"TRADING_MODE": "paper", "ORDERS_ENABLED": false}
```

#### CancelResult

```python
class CancelResult(BaseModel):
    orderId: int
    status: str                    # "CANCELLED", "ALREADY_FILLED", "NOT_FOUND"
    message: Optional[str] = None
```

#### HealthResponse

```python
class HealthResponse(BaseModel):
    status: str                    # "healthy", "degraded", "unhealthy"
    serverTime: datetime           # Server's current time (UTC)
    tradingMode: str               # "paper" or "live"
    ordersEnabled: bool
    message: Optional[str] = None
```

---

## Persisted Data (SQLite)

### Database: `data/audit.db`

All audit data is **append-only** and **immutable**.

#### Table: `audit_log`

```sql
CREATE TABLE audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    correlation_id TEXT,
    timestamp TEXT NOT NULL,              -- ISO 8601 UTC
    event_type TEXT NOT NULL,             -- "ORDER_PLACED", "ORDER_FILLED", etc.
    event_data TEXT NOT NULL,             -- JSON-serialized OrderDetail
    user_context TEXT,                    -- Who/what triggered (API, CLI, etc.)
    account_id TEXT,
    UNIQUE(correlation_id, event_type, timestamp)
);

CREATE INDEX idx_audit_correlation ON audit_log(correlation_id);
CREATE INDEX idx_audit_account ON audit_log(account_id);
CREATE INDEX idx_audit_timestamp ON audit_log(timestamp);
```

**event_type values**:

- `ORDER_PLACED`: User-initiated order placement
- `ORDER_ACCEPTED`: Broker accepted order
- `ORDER_FILLED`: Partial or full fill
- `ORDER_CANCELLED`: User or system cancelled
- `ORDER_REJECTED`: Broker rejected

**Uniqueness**: `(correlation_id, event_type, timestamp)` prevents duplicate entries for same order action in same request.

**Example row**:

```sql
INSERT INTO audit_log (correlation_id, timestamp, event_type, event_data, user_context, account_id)
VALUES (
  'req-550e8400-e29b-41d4-a716-446655440000',
  '2025-01-01T09:35:15Z',
  'ORDER_PLACED',
  '{"orderId": 1001, "symbol": "AAPL", "action": "BUY", "quantity": 100, "orderType": "MKT", "status": "SIMULATED", ...}',
  'API /api/orders/place',
  'DU123456'
);
```

#### Table: `order_history`

```sql
CREATE TABLE order_history (
    order_id INTEGER PRIMARY KEY,
    symbol TEXT NOT NULL,
    action TEXT NOT NULL,             -- "BUY" or "SELL"
    quantity REAL NOT NULL,
    order_type TEXT NOT NULL,
    status TEXT NOT NULL,             -- Current status
    filled REAL NOT NULL DEFAULT 0,
    avg_fill_price REAL NOT NULL DEFAULT 0,
    commission REAL NOT NULL DEFAULT 0,
    placed_at TEXT NOT NULL,          -- ISO 8601 UTC
    updated_at TEXT NOT NULL,         -- ISO 8601 UTC
    config_snapshot TEXT NOT NULL,    -- JSON: TRADING_MODE, ORDERS_ENABLED
    UNIQUE(order_id, symbol)
);

CREATE INDEX idx_order_history_symbol ON order_history(symbol);
CREATE INDEX idx_order_history_status ON order_history(status);
CREATE INDEX idx_order_history_placed_at ON order_history(placed_at);
```

**Invariant**: Primary key is `order_id` (unique per order). Never update rows; append new events to `audit_log`.

**Example row**:

```sql
INSERT INTO order_history (order_id, symbol, action, quantity, order_type, status, filled, avg_fill_price, commission, placed_at, updated_at, config_snapshot)
VALUES (
  1001,
  'AAPL',
  'BUY',
  100,
  'MKT',
  'FILLED',
  100,
  150.25,
  5.00,
  '2025-01-01T09:35:15Z',
  '2025-01-01T09:35:20Z',
  '{"TRADING_MODE": "paper", "ORDERS_ENABLED": false}'
);
```

---

## Backward-Compatibility Rules

### Adding a New Field

1. **Optional fields only**: Add with `Optional[type] = None`
2. **Default value**: Provide sensible default in Pydantic
3. **Update schema docs**: Document in `docs/SCHEMAS.md`
4. **Update this file**: Add to relevant section
5. **Test**: Ensure old clients still work (field missing in request)

**Example**:

```python
# Old API
class Quote(BaseModel):
    symbol: str
    bid: float

# New API (backward-compatible)
class Quote(BaseModel):
    symbol: str
    bid: float
    bidSize: float = 0.0  # New field, optional
```

### Removing a Field

**FORBIDDEN** for response models. Deprecated fields must remain for backward compatibility.

For internal-only fields, mark as `@deprecated` and remove in next major version (but announce in CHANGELOG).

### Renaming Fields

**FORBIDDEN** for response models. Create new field, deprecate old one.

```python
# Deprecated but kept for compatibility
old_field: Optional[float] = None

# New field
new_field: float
```

### Changing Field Type

**FORBIDDEN** for response models.

If type must change (e.g., `int` → `str`), create new field and deprecate old.

### Enum Values (Status, Action, etc.)

**Append-only**. Never remove or rename existing values:

- `status` in {"SUBMITTED", "ACCEPTED", "FILLED", "CANCELLED", "REJECTED", "SIMULATED"}
- `action` in {"BUY", "SELL"}
- `orderType` in {"MKT", "LMT", "STP", "STP_LMT", "MOC", "OPG"}

New values can be added (e.g., "PARTIAL_FILLED" for future status).

---

## Data Relationships

```
┌──────────────┐
│ SymbolSpec   │ (user input)
└──────┬───────┘
       │ (resolves to)
       ↓
┌──────────────────┐
│ Contract         │ (IBKR identifier)
└──────┬───────────┘
       │ (queried for)
       ↓
┌──────────────────┐
│ Quote / Bar      │ (market data snapshot)
└──────────────────┘

┌──────────────────┐
│ OrderSpec        │ (user request)
└──────┬───────────┘
       │ (creates)
       ↓
┌──────────────────┐
│ Order (IBKR)     │ (broker entity, orderId)
└──────┬───────────┘
       │ (generates)
       ↓
┌──────────────────┐
│ OrderDetail      │ (result + audit log entry)
└──────────────────┘

┌──────────────────┐
│ Position         │ (current holding)
└──────┬───────────┘
       │ (aggregates)
       ↓
┌──────────────────┐
│ AccountSummary   │ (account-level aggregate)
│ AccountPnL       │ (P&L by symbol + total)
└──────────────────┘
```

---

## Constraints Summary

| Entity | Constraint | Rationale |
|--------|-----------|-----------|
| Quote | bid <= ask | Market integrity |
| Quote | volume >= 0 | Non-negative volume |
| Position | avgCost >= 0 | Entry price always >= 0 |
| Order | quantity >= 1 | At least 1 share/contract |
| Order | orderId unique per symbol | Prevent duplicates |
| Audit log | `(correlation_id, event_type, timestamp)` unique | Idempotent writes |
| Config | TRADING_MODE in ("paper", "live") | Enum enforcement |
| Config | ORDERS_ENABLED requires override file if TRADING_MODE=live | Safety gate |

---

## Example: Full Order Lifecycle

```
1. User sends POST /api/orders/place with:
   {
     "symbol": "AAPL",
     "securityType": "STK",
     "action": "BUY",
     "quantity": 100,
     "orderType": "MKT"
   }

2. API validates (Pydantic model enforcement)

3. Server resolves symbol → Contract (cached)

4. Server calls ibkr_core/orders.py::place_order()

5. If TRADING_MODE=paper OR ORDERS_ENABLED=false:
   → Simulated order, returns OrderResult(status="SIMULATED")
   Else:
   → IBKR Gateway places real order, returns OrderResult(status="ACCEPTED")

6. Audit log entry created:
   INSERT INTO audit_log (...) VALUES (
     correlation_id='req-xxx',
     event_type='ORDER_PLACED',
     event_data={OrderDetail JSON},
     ...
   )

7. INSERT INTO order_history:
   (orderId=1001, symbol='AAPL', status='ACCEPTED', ...)

8. User polls GET /api/orders/{orderId}/status
   → Query IBKR for current status
   → Update order_history row (status column)
   → Return OrderDetail

9. Broker fills order:
   → MCP/API detects fill (via subscription or polling)
   → Updates order_history (filled=100, status='FILLED')
   → Creates audit log entry (event_type='ORDER_FILLED')

10. User calls GET /api/account/pnl:
    → Fetches positions from IBKR
    → Calculates unrealizedPnL for each position
    → Queries audit log for realizedPnL (closed trades)
    → Returns AccountPnL with bySymbol breakdown
```

---

## Migration & Schema Evolution

### Adding a column to audit_log

```sql
ALTER TABLE audit_log ADD COLUMN new_field TEXT DEFAULT NULL;
```

Existing rows will have NULL; new rows will populate it.

### Creating a new table

1. Document in this file
2. Run migration script at startup (see `persistence.py::init_db()`)
3. Add to `.context/03_DATA_CONTRACTS.md`
4. Add to `09_DECISIONS.md` if non-trivial

### Backward compatibility in code

All code reads must handle missing columns gracefully:

```python
def query_audit_log(...):
    cursor.execute("SELECT * FROM audit_log")
    rows = cursor.fetchall()
    for row in rows:
        # Use .get() to handle missing columns
        new_field = row.get("new_field")  # Returns None if column missing
```
