# 01_RULES.md: The Guardrails (Non-Negotiable Invariants)

## Purpose

This document lists **hard constraints** that must never be violated. These are not suggestions—they are laws of the system. Any code change that breaks these rules will break production safety.

---

## Core Invariants (The Laws)

### 1. **Default Safe Mode**

```
TRADING_MODE=paper (ALWAYS at startup, unless explicitly reconfigured)
ORDERS_ENABLED=false (ALWAYS at startup, unless explicitly reconfigured)
```

**Consequence**: Even if someone misconfigures `.env`, live orders are impossible until BOTH flags are true AND override file exists.

**Never Violate**: Do not add code that assumes orders are enabled by default.

---

### 2. **Five Safety Gates for Live Orders**

All 5 gates must pass before a live order is placed:

```python
# Gate 1: Config valid (startup check)
assert TRADING_MODE in ("paper", "live")

# Gate 2: Override file exists (startup check)
if TRADING_MODE == "live" and ORDERS_ENABLED:
    assert Path(LIVE_TRADING_OVERRIDE_FILE).exists()

# Gate 3: Runtime trading mode check
if TRADING_MODE == "paper":
    return simulate_order()
if not ORDERS_ENABLED:
    return simulate_order()

# Gate 4: Order spec validation
assert quantity > 0
assert orderType in ("MKT", "LMT", "STP", "TRAIL")
assert action in ("BUY", "SELL", "BUYTOCOVER", "SELLSHORT")
assert account_has_sufficient_buying_power()

# Gate 5: Deterministic orderId + audit logging
orderId = hash(symbol + action + quantity + orderType + price)
assert not_already_in_audit_db(orderId)
log_to_audit_db(correlation_id, orderId, "place", config_snapshot)
```

**Never Violate**:
- Do not remove any gate
- Do not add "shortcut" paths for "testing" that bypass gates
- Do not default ORDERS_ENABLED to true
- Do not remove override file check

---

### 3. **Decimal Precision for Money (No Floats)**

```python
# ✅ CORRECT
from decimal import Decimal
balance = Decimal("10250.50")    # $10,250.50
pnl = Decimal("-125.00")          # -$125.00

# ❌ FORBIDDEN
balance = 10250.50                # FLOAT! Precision loss!
pnl = -125                        # INTEGER! Ambiguous!
```

**Why**: Floats lose precision (e.g., 0.1 + 0.2 ≠ 0.3). In financial systems, every cent matters.

**Never Violate**:
- Do not use `float` for cash values
- Do not use `int` for dollar amounts (ambiguous currency)
- Always use `Decimal` with 2 decimal places (cents)
- When converting from IBKR API, wrap in `Decimal(str(value))`

---

### 4. **UTC Timestamps Only (ISO 8601)**

```python
# ✅ CORRECT
from datetime import datetime
import pytz
ts = datetime.now(pytz.UTC).isoformat()
# "2025-01-30T14:35:22.123456+00:00"

# ❌ FORBIDDEN
ts = datetime.now()               # Local time! Ambiguous across regions!
ts = time.time()                  # Unix epoch! Hard to debug!
ts = "2025-01-30 14:35:22"        # No timezone! Which timezone?
```

**Why**: Orders must be globally unambiguous. IBKR runs in NYC. UTC eliminates confusion.

**Never Violate**:
- All timestamps must be ISO 8601 formatted
- All timestamps must have UTC timezone info
- Local timezone conversion happens only at display time (API responses)
- Never store or log local time

---

### 5. **Order Idempotency (Deterministic orderId)**

```python
# Same input MUST always produce same orderId
def get_or_create_orderId(symbol: str, action: str, qty: int, orderType: str) -> str:
    # Hash input deterministically
    orderId = hash(f"{symbol}|{action}|{qty}|{orderType}")
    
    # Check if already in audit.db
    existing = audit_db.query("SELECT * FROM orders WHERE orderId = ?", orderId)
    if existing:
        # Return the previous result (idempotent)
        return existing[0]
    
    # New order
    return orderId
```

**Why**: If a client retries (network timeout, client crashes), we don't want duplicate orders.

**Invariant**: 
- Same (symbol, action, qty, orderType, limit, stop) → same orderId
- orderId already placed → return previous result, don't place again
- Audit table has UNIQUE(orderId, action, timestamp) constraint

**Never Violate**:
- Do not generate random orderIds
- Do not skip idempotency checks
- Do not remove the audit table constraint

---

### 6. **Append-Only Audit Trail (No Deletes or Updates)**

```python
# ✅ CORRECT
audit_db.append((correlation_id, orderId, "place", config_snapshot))
audit_db.append((correlation_id, orderId, "filled", 100 @ $150.50))

# ❌ FORBIDDEN
audit_db.update(orderId, status="cancelled")  # NO! Audit trail must not change
audit_db.delete(orderId)                      # NO! Destroy evidence!
```

**Why**: Regulatory compliance. Every trade must be auditable forever.

**Never Violate**:
- Do not update order records
- Do not delete order records
- Do not modify audit trail
- All changes must be NEW inserts (immutable log)

---

### 7. **Contract Resolution Cache (Session-Scoped)**

```python
# ✅ CORRECT: Cache for the session
contracts_cache = {}  # Invalidated on restart

def resolve_contract(symbol: str, securityType: str, exchange: str) -> Contract:
    key = (symbol, securityType, exchange)
    if key in contracts_cache:
        return contracts_cache[key]
    
    # Cache miss: call IBKR API
    contract = ib.resolve_contract(symbol, securityType, exchange)
    contracts_cache[key] = contract
    return contract

# ❌ FORBIDDEN: Persist contract cache across restarts
# Don't do this:
# pickle.dump(contracts_cache, open("contracts.pkl", "wb"))
```

**Why**: Contracts change (delistings, symbol changes). Cache must be fresh on restart.

**Never Violate**:
- Do not persist contract cache to disk
- Invalidate cache on restart
- Cache hit is OK; cache miss triggers fresh IBKR call

---

### 8. **No Negative Account Balance**

```python
# ✅ CORRECT: Check before trading
buying_power = get_buying_power()
if quantity * price > buying_power:
    raise InsufficientBuyingPowerError(f"Need ${quantity * price}, have ${buying_power}")

# ❌ FORBIDDEN: Allow negative balance
account.balance -= order_cost  # NO! Negative balance!
```

**Why**: Margin calls are expensive. IBKR has strict limits.

**Never Violate**:
- Always check buying power before order placement
- Reject orders if insufficient margin
- Never allow negative cash balance

---

### 9. **Immutable Config at Runtime**

```python
# ✅ CORRECT: Validate once at startup
config = Config.from_env()
config.validate()  # Raises if invalid
# Use config throughout session (immutable)

# ❌ FORBIDDEN: Change config mid-session
config.trading_mode = "live"  # NO! Config must be static!
```

**Why**: If config changes mid-session, different orders follow different rules. Chaos.

**Never Violate**:
- Load & validate config once at startup
- Make config objects immutable (frozen Pydantic models)
- Do not change TRADING_MODE or ORDERS_ENABLED at runtime
- If config must change, restart the entire application

---

### 10. **No Trades Outside Market Hours** (If Enforced)

```python
# ✅ CORRECT: Check if trading outside hours
from market_calendar import get_nyse_calendar
nyse = get_nyse_calendar()
if not nyse.is_session(now()):
    raise OutsideMarketHoursError("NYSE closed")

# ❌ FORBIDDEN: Allow trades outside hours (unless explicit MKT or SMART routing)
# Risk: Huge slippage, gaps, no liquidity
```

**Current Status**: NOT enforced (future enhancement)

**When adding**: Update this rule.

---

### System Integration Boundaries

The system interacts with these external services. Never modify their behavior; only consume:

| System | Type | Failure Mode | Our Responsibility |
|--------|------|--------------|-------------------|
| **IBKR Gateway** (TCP 4002) | External API | Connection timeout, rejection | Connect, resolve contracts, place orders, handle disconnection |
| **SQLite audit.db** | Local file | Disk full, permission denied | Immutable appends only; never delete/update |
| **HTTP REST API** (port 8000) | Entry point | Depends on FastAPI | Validate requests, return responses, log correlation IDs |
| **MCP Server** | Entry point | Claude unavailable | Marshal tool calls, handle errors gracefully |
| **Environment (.env)** | Configuration source | File missing | Fail at startup with clear error message |
| **Override file** | Safety gate | File missing | Block live trading until file exists |

**Never Violate**:
- Do not try to modify IBKR accounts/positions directly (read-only access)
- Do not modify SQLite except append (immutable audit trail)
- Do not swallow errors from external systems (always log + propagate)
- Do not ignore IBKR rate limits (50 orders/sec, 100 contract resolves/sec)

---

## Data Integrity Rules

### Rule 1: Unique Order IDs

```sql
-- ✅ CORRECT: Unique constraint prevents duplicates
CREATE TABLE orders (
    orderId TEXT PRIMARY KEY,  -- Hash of input
    symbol TEXT NOT NULL,
    action TEXT NOT NULL,
    quantity INT NOT NULL,
    status TEXT NOT NULL,
    correlation_id TEXT NOT NULL,
    timestamp TEXT NOT NULL,  -- ISO 8601 UTC
    config_snapshot JSON NOT NULL
);

CREATE UNIQUE INDEX idx_order_unique 
ON orders (orderId, action, timestamp);
```

**Never Violate**: Do not allow duplicate orderIds.

---

### Rule 2: Correlation ID Tracing

Every HTTP request, order, and market data query must have a **correlation_id** (UUID):

```python
# ✅ CORRECT
correlation_id = uuid.uuid4().hex
log(f"[{correlation_id}] Place order {orderId}")
audit_db.insert((correlation_id, orderId, "place", ...))
return OrderResult(orderId=orderId, correlation_id=correlation_id)
```

**Never Violate**: Do not lose or omit correlation IDs.

---

### Rule 3: Config Snapshot in Audit Trail

Every order action must include a snapshot of config at the time:

```python
# ✅ CORRECT
config_snapshot = {
    "trading_mode": config.trading_mode,
    "orders_enabled": config.orders_enabled,
    "override_file_exists": Path(config.override_file).exists()
}
audit_db.insert((
    correlation_id, orderId, "place", 
    timestamp=now_utc(), 
    config_snapshot=json.dumps(config_snapshot)
))
```

**Why**: If config changes (unlikely but possible), we can replay history with original config intent.

**Never Violate**: Do not skip config snapshots.

---

## Forbidden Patterns

### ❌ Pattern 1: Hardcoded Credentials

```python
# FORBIDDEN
API_KEY = "sk-1234567890abcdef"  # NO! Commit secrets!
PASSWORD = "my_password"          # NO!

# ✅ CORRECT
import os
API_KEY = os.getenv("IBKR_API_KEY")
if not API_KEY:
    raise ConfigError("IBKR_API_KEY not set in .env")
```

**Never Violate**: Credentials ONLY from environment or secure vaults.

---

### ❌ Pattern 2: Floating Point Math

```python
# FORBIDDEN
balance = 10000.0
trade_cost = 99.99
balance -= trade_cost  # 9900.0099999... (precision loss!)

# ✅ CORRECT
balance = Decimal("10000.00")
trade_cost = Decimal("99.99")
balance -= trade_cost  # 9900.01 (exact)
```

**Never Violate**: Always use Decimal for money.

---

### ❌ Pattern 3: Global State Mutations

```python
# FORBIDDEN
global ORDERS_ENABLED
ORDERS_ENABLED = True  # Mutates global, hard to debug!

# ✅ CORRECT
config = Config.from_env()
if config.orders_enabled:
    place_real_order()
else:
    simulate_order()
```

**Never Violate**: Pass config as argument, don't mutate globals.

---

### ❌ Pattern 4: Blocking Calls in Event Loop

```python
# FORBIDDEN
async def get_quote(symbol):
    contract = ib.resolve_contract(symbol)  # Blocking! No!
    return get_quote(contract)

# ✅ CORRECT
async def get_quote(symbol):
    contract = await resolve_contract_async(symbol)  # Use dedicated thread
    return await get_quote_async(contract)
```

**Never Violate**: All IBKR calls must run in dedicated executor thread.

---

### ❌ Pattern 5: Silent Error Suppression

```python
# FORBIDDEN
try:
    place_order(spec)
except Exception:
    pass  # Silent fail!

# ✅ CORRECT
try:
    place_order(spec)
except OrderValidationError as e:
    logger.error(f"Order validation failed: {e}", extra={"correlation_id": cid})
    raise
except Exception as e:
    logger.error(f"Unexpected error: {e}", extra={"correlation_id": cid})
    raise
```

**Never Violate**: Log all errors with correlation_id; never silent pass.

---

### ❌ Pattern 6: Shared Mutable Objects Across Requests

```python
# FORBIDDEN
shared_config = {}  # Global dict, shared across requests!

def handle_request(request):
    shared_config["user"] = request.user  # Race condition!

# ✅ CORRECT
def handle_request(request):
    local_config = {"user": request.user}  # Scoped to request
    return local_config
```

**Never Violate**: Isolate state per request; don't share mutable objects.

---

## Enforcement

### At Code Review

Reviewers must check:

- ✅ No floats used for money
- ✅ All timestamps are UTC ISO 8601
- ✅ Config validated at startup
- ✅ Override file check present
- ✅ Correlation IDs logged
- ✅ Audit trail appends (no deletes/updates)
- ✅ Tests updated

### At Runtime

The system enforces:

- ✅ Five safety gates prevent live orders
- ✅ Paper mode by default
- ✅ Orders disabled by default
- ✅ Override file must exist
- ✅ Order IDs deterministic
- ✅ Audit trail immutable

### If Violated

- **Critical violations** (hardcoded secrets, order duplication): Immediate rollback + incident review
- **Data loss violations** (deleting audit trail): Immediate incident + compliance review
- **Safety violations** (bypassing gates): Immediate hotfix + safety audit

---

## Related Files

- [02_OPS.md](.context/02_OPS.md): How to run and test safely
- [03_DECISIONS.md](.context/03_DECISIONS.md): Why these rules exist
- [04_RISK_GUARDRAILS.md](.context/04_RISK_GUARDRAILS.md): Detailed risk analysis
- [07_STYLE_AND_PATTERNS.md](.context/07_STYLE_AND_PATTERNS.md): Coding patterns that enforce these rules
