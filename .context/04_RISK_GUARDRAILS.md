# 04_RISK_GUARDRAILS.md: Safety Constraints & Forbidden Patterns

## Executive Summary

This system is **safe by default**. Live trading requires explicit opt-in with multiple safety gates. This document lists all hard constraints, forbidden patterns, and operational gates.

---

## Core Safety Principles

1. **Paper by default**: `TRADING_MODE=paper` at startup
2. **Orders disabled by default**: `ORDERS_ENABLED=false` at startup
3. **No accidental live trades**: Even with live mode, orders are simulated unless ORDERS_ENABLED=true AND override file exists
4. **Audit trail required**: Every order action logged immutably
5. **Deterministic order IDs**: Same input always produces same orderId (prevents duplicates)
6. **Config validated at startup AND runtime**: Never trust env vars alone

---

## Safety Gates (In Order of Enforcement)

### Gate 1: Trading Mode Validation (Startup)

```python
# In ibkr_core/config.py::Config.validate()
if self.trading_mode not in ("paper", "live"):
    raise InvalidConfigError(
        f"TRADING_MODE must be 'paper' or 'live', got '{self.trading_mode}'"
    )
```

**Invariant**: Config must explicitly set `TRADING_MODE`. No ambiguity.

---

### Gate 2: Override File Requirement (Startup)

```python
# In ibkr_core/config.py::Config.validate()
if self.trading_mode == "live" and self.orders_enabled:
    if self.live_trading_override_file:
        override_path = Path(self.live_trading_override_file)
        if not override_path.exists():
            raise InvalidConfigError(
                f"TRADING_MODE=live and ORDERS_ENABLED=true requires override file "
                f"at {self.live_trading_override_file}"
            )
    else:
        raise InvalidConfigError(
            "TRADING_MODE=live and ORDERS_ENABLED=true is extremely dangerous. "
            "Set LIVE_TRADING_OVERRIDE_FILE to the path of a file you have created. "
            "After creating the file, the system will allow live trading."
        )
```

**Invariant**: Live trading + orders enabled REQUIRES:
1. Explicit `LIVE_TRADING_OVERRIDE_FILE` path in `.env`
2. File must physically exist on disk
3. Prevents typos and accidental enables

**Procedure to enable**:
```bash
# 1. Create the file
touch ~/ibkr_live_trading_confirmed.txt

# 2. Set in .env
LIVE_TRADING_OVERRIDE_FILE=~/ibkr_live_trading_confirmed.txt
TRADING_MODE=live
ORDERS_ENABLED=true

# 3. Start system
# System validates at startup: override file exists ✓
```

---

### Gate 3: Order Placement Check (Runtime)

```python
# In ibkr_core/orders.py::place_order_internal()
def place_order_internal(...) -> OrderResult:
    config = get_config()
    
    # Simulate if paper mode
    if config.trading_mode == "paper":
        return simulate_order(spec)  # Returns status=SIMULATED
    
    # Simulate if orders disabled
    if not config.orders_enabled:
        return simulate_order(spec)  # Returns status=SIMULATED
    
    # Only here: trading_mode=live AND orders_enabled=true AND override file exists
    # Proceed with real order placement
    return place_real_order(spec)
```

**Invariant**: Order placement simulates UNLESS **all three** conditions true:
1. `TRADING_MODE=live`
2. `ORDERS_ENABLED=true`
3. Override file exists (checked at startup)

---

### Gate 4: Order Validation

```python
# In ibkr_core/orders.py::validate_order_spec()
def validate_order_spec(spec: OrderSpec) -> None:
    # Quantity must be positive integer
    if spec.quantity < 1 or not isinstance(spec.quantity, int):
        raise OrderValidationError(f"quantity must be >= 1, got {spec.quantity}")
    
    # Limit orders must have limitPrice
    if spec.order_type == "LMT" and not spec.limit_price:
        raise OrderValidationError("LMT orders require limitPrice")
    
    # Stop orders must have stopPrice
    if spec.order_type in ("STP", "STP_LMT") and not spec.stop_price:
        raise OrderValidationError("STP orders require stopPrice")
    
    # Prices must be positive
    if spec.limit_price and spec.limit_price <= 0:
        raise OrderValidationError(f"limitPrice must be > 0, got {spec.limit_price}")
    
    if spec.stop_price and spec.stop_price <= 0:
        raise OrderValidationError(f"stopPrice must be > 0, got {spec.stop_price}")
```

**Invariant**: All order specs validated before placement.

---

### Gate 5: Audit Trail

```python
# In ibkr_core/persistence.py::log_order_action()
def log_order_action(order_detail: OrderDetail, config: Config) -> None:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # Append-only: INSERT, never UPDATE
        cursor.execute("""
            INSERT INTO audit_log 
            (correlation_id, timestamp, event_type, event_data, account_id)
            VALUES (?, ?, ?, ?, ?)
        """, (
            get_correlation_id(),  # UUID from request context
            datetime.utcnow().isoformat() + 'Z',
            'ORDER_PLACED',
            order_detail.model_dump_json(),
            order_detail.account_id
        ))
        
        # Unique constraint prevents duplicates
        conn.commit()
```

**Invariant**: Every order action logged with:
- Correlation ID (request tracing)
- Timestamp (UTC, ISO 8601)
- Full order spec + result
- Config snapshot (TRADING_MODE, ORDERS_ENABLED at order time)

**Query for history**:
```python
# See all orders placed today
order_history = query_audit_log(
    event_type="ORDER_PLACED",
    start_time=datetime(2025, 1, 1)
)
```

---

## Forbidden Patterns

### ❌ DO NOT

1. **Store floats for cash/P&L**
   ```python
   # WRONG
   balance = 10250.50  # float - precision loss
   
   # CORRECT
   balance = Decimal("10250.50")
   ```

2. **Modify audit log rows**
   ```python
   # WRONG
   cursor.execute("UPDATE audit_log SET status = 'FILLED' WHERE orderId = 1001")
   
   # CORRECT
   cursor.execute("INSERT INTO audit_log (...) VALUES (...)")  # Append only
   ```

3. **Trust env vars without validation**
   ```python
   # WRONG
   trading_mode = os.environ.get("TRADING_MODE", "paper")  # Might be typo: "papeer"
   if trading_mode == "paper": ...  # Silently defaults to paper!
   
   # CORRECT
   config = get_config()  # Validates at startup
   config.validate()  # Raises InvalidConfigError if invalid
   ```

4. **Bypass order validation**
   ```python
   # WRONG
   place_real_order(OrderSpec(quantity=-100))  # Negative quantity!
   
   # CORRECT
   validate_order_spec(spec)  # Raises OrderValidationError
   place_order(spec)
   ```

5. **Skip deterministic order ID**
   ```python
   # WRONG
   orderId = random.randint(0, 999999)  # Can't replay, duplicates possible
   
   # CORRECT
   orderId = hash(symbol + action + quantity + timestamp)  # Deterministic
   ```

6. **Mix currencies without conversion**
   ```python
   # WRONG
   usd_value = 100
   eur_value = 80
   total = usd_value + eur_value  # Nonsense!
   
   # CORRECT
   exchange_rate = get_exchange_rate("USD", "EUR")
   total = usd_value + (eur_value / exchange_rate)
   ```

7. **Allow order placement without correlation ID**
   ```python
   # WRONG
   place_order(spec)  # Can't trace in audit log
   
   # CORRECT
   correlation_id = str(uuid.uuid4())
   log_with_context(correlation_id, lambda: place_order(spec))
   ```

8. **Cache contracts longer than session**
   ```python
   # WRONG
   # Contract resolved at startup, used all day
   # Symbol might be delisted, contract might expire
   
   # CORRECT
   # Cache expires at end of trading day or after N hours
   # Fresh resolution on next day
   ```

9. **Place orders in paper mode manually**
   ```python
   # WRONG
   if config.trading_mode == "paper":
       # Place real order anyway
       client.place_order_real(spec)
   
   # CORRECT
   # Let place_order() check config and simulate if needed
   order_result = client.place_order(spec)
   # Will return status=SIMULATED in paper mode
   ```

10. **Remove or rename order status values**
    ```python
    # WRONG
    # Change status from "FILLED" to "COMPLETED" in code
    # Old audit logs now unreadable
    
    # CORRECT
    # Status values are append-only
    # If new status needed, ADD it: {"SUBMITTED", "ACCEPTED", "FILLED", "PARTIAL_FILLED"}
    ```

---

## Operational Constraints

### Contract Resolution

**Constraint**: Resolved contracts are cached in-memory per session.

**Why**: Reduces IBKR API calls during development; prevents stale cache issues.

**Enforcement**:
```python
# In ibkr_core/contracts.py
contract_cache: Dict[str, Contract] = {}  # In-memory, session-only

def resolve_contract(spec: SymbolSpec) -> Contract:
    cache_key = (spec.symbol, spec.securityType, spec.exchange, spec.currency)
    
    if cache_key in contract_cache:
        return contract_cache[cache_key]  # Cache hit
    
    # Cache miss: resolve from IBKR
    contract = ibkr_resolve(spec)
    contract_cache[cache_key] = contract
    return contract
```

**Implications**:
- Restart client to refresh contracts
- Delisted symbols cache stale contracts until restart
- Multi-session environments should clear cache periodically

---

### Position Accuracy

**Constraint**: Position quantities must match IBKR account, reconciled nightly.

**Why**: Prevents silently lost fills, phantom positions.

**Enforcement**:
```python
# In ibkr_core/account.py
def get_positions() -> List[Position]:
    # Fetch from IBKR (single source of truth)
    positions = ibkr_get_positions()
    
    # Optional: Reconcile with audit log
    audit_positions = reconstruct_from_audit_log()
    
    # If mismatch, log warning
    if positions != audit_positions:
        logger.warning(f"Position mismatch: IBKR={positions}, Audit={audit_positions}")
    
    return positions  # Always trust IBKR
```

---

### Order Fill Determinism

**Constraint**: Same order spec always produces same orderId.

**Why**: Enables idempotent retries; prevents duplicate fills.

**Enforcement**:
```python
# In ibkr_core/orders.py
def generate_order_id(spec: OrderSpec) -> int:
    # Hash inputs to produce deterministic ID
    import hashlib
    key = f"{spec.symbol}:{spec.action}:{spec.quantity}:{spec.order_type}"
    return int(hashlib.md5(key.encode()).hexdigest(), 16) % (2**31)
```

**Implication**: If user retries same order twice:
1. First call: orderId=X, placed
2. Second call: orderId=X, rejected as duplicate (IBKR)
3. Query status: Shows original fill

---

### Timeframe Windows

**Constraint**: All timestamps in UTC, ISO 8601.

**Why**: Eliminates ambiguity, enables global trading.

**Enforcement**:
```python
# In ibkr_core/logging_config.py
from datetime import datetime, timezone

def log_order_action(...):
    timestamp = datetime.now(timezone.utc).isoformat()  # Always UTC
    # Never: datetime.now().isoformat()  # Could be local time!
```

---

### Rounding & Precision

**Constraint**: All monetary values use `Decimal` with 2 decimal places.

**Why**: Prevents floating-point arithmetic errors (classic bug: 0.1 + 0.2 != 0.3 in floats).

**Enforcement**:
```python
# In ibkr_core/models.py
from decimal import Decimal

class Position(BaseModel):
    # CORRECT
    avgCost: Decimal  # Decimal, not float
    
    @field_validator("avgCost")
    def validate_precision(cls, v):
        # Round to 2 decimal places
        if isinstance(v, Decimal):
            v = v.quantize(Decimal("0.01"))
        return v
```

---

## Monitoring & Alerting

### Critical Logs to Watch

| Log Pattern | Severity | Action |
|-------------|----------|--------|
| `TRADING_MODE=live` | INFO | Confirm intended; expected in production |
| `ORDERS_ENABLED=true` | WARNING | Verify config; high-risk state |
| `Position mismatch:` | ERROR | Investigate; possible fill loss |
| `TradingDisabledError` | INFO | Expected; order simulated |
| `Contract resolution failed` | ERROR | Symbol not found; check symbol |
| `IBKR Gateway unreachable` | CRITICAL | Stop trading; service down |

---

## Runbook: Incident Response

### Scenario 1: User Accidentally Enabled Live Trading

**Symptom**: Orders showing `status=ACCEPTED` instead of `SIMULATED`.

**Response**:
```bash
# 1. Immediate: Delete override file
rm ~/ibkr_live_trading_confirmed.txt

# 2. Edit .env
echo "ORDERS_ENABLED=false" >> .env

# 3. Restart client
# System will validate at startup: override file missing, live trading disabled

# 4. Review audit log for unintended trades
sqlite3 data/audit.db "SELECT * FROM audit_log WHERE event_type='ORDER_PLACED' AND timestamp > '2025-01-01T12:00:00Z'"

# 5. Contact broker to cancel unexecuted orders
```

### Scenario 2: Position Mismatch Detected

**Symptom**: "Position mismatch: IBKR=100 AAPL, Audit=95 AAPL"

**Response**:
```bash
# 1. Immediate: Halt new orders
# Set ORDERS_ENABLED=false

# 2. Investigate
# Query audit log: did we log all fills?
sqlite3 data/audit.db "SELECT * FROM audit_log WHERE event_type='ORDER_FILLED' ORDER BY timestamp DESC LIMIT 20"

# 3. Query IBKR directly via API
curl http://localhost:8000/api/account/positions

# 4. Manual reconciliation
# Was there a fill we didn't capture? Call broker.

# 5. Update audit log with manual adjustment
# Add entry for missing fill

# 6. Resume trading once resolved
```

### Scenario 3: IBKR Gateway Unreachable

**Symptom**: "Connection refused: 127.0.0.1:4002"

**Response**:
```bash
# 1. Check IBKR Gateway running
# Is TWS/Gateway window open?
# Is API enabled in settings?

# 2. Check port
lsof -i :4002

# 3. Restart IBKR Gateway
# (Not automated; manual IBKR application)

# 4. System will retry automatically (exponential backoff)
# Once connection restored, operations resume

# 5. Check audit log for missed fills during downtime
```

---

## Compliance & Audit

### What Gets Logged

✅ **Every order action**:
- Placement
- Acceptance
- Fill (partial or full)
- Cancellation
- Rejection

✅ **Every query**:
- Market data request
- Account summary request
- Position query

❌ **NOT logged** (for privacy):
- API key
- Account credentials
- User personal info

### Audit Log Queries

```bash
# All orders placed in last 24 hours
sqlite3 data/audit.db "
SELECT timestamp, event_type, event_data FROM audit_log
WHERE event_type='ORDER_PLACED'
AND timestamp > datetime('now', '-1 day')
ORDER BY timestamp DESC
"

# All fills with commission
sqlite3 data/audit.db "
SELECT json_extract(event_data, '$.symbol') as symbol,
       json_extract(event_data, '$.orderId') as orderId,
       json_extract(event_data, '$.commission') as commission
FROM audit_log
WHERE event_type='ORDER_FILLED'
AND date(timestamp) = date('now')
"

# Positions by correlation ID (trace single request)
sqlite3 data/audit.db "
SELECT * FROM audit_log
WHERE correlation_id='req-550e8400-e29b-41d4-a716-446655440000'
ORDER BY timestamp
"
```

---

## Summary

| Constraint | Gate | Bypass? |
|-----------|------|---------|
| Paper by default | Startup validation | No |
| Orders disabled by default | Startup validation | No |
| Override file required | Startup validation | No |
| Order validation | Runtime check | No |
| Audit trail | Append-only DB | No (design prevents updates) |
| Deterministic order ID | Hash-based | No |
| UTC timestamps | Code enforcement | No |
| Decimal precision | Pydantic validator | No |
| Config validation | `get_config()` | No |

**Verdict**: System is designed to be nearly impossible to accidentally enable live trading without explicit, multi-step confirmation.
