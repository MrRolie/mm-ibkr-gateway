# 03_DECISIONS.md: Architectural Decision Record (ADR)

## Purpose

This document logs **non-obvious design choices**, their rationale, and trade-offs. When a future developer asks "Why did they do it this way?", the answer is here.

---

## Decision Format

```text
[Date] | [Decision] | [Status]
────────────────────────────────────────────────────────────
Problem:     What we were trying to solve
Solution:    What we chose
Alternatives: What we considered instead
Trade-offs:  Pros/Cons of this choice
Related:     Links to code or context files
```

---

## Decisions Log

### 1. Use Decimal for Money, Not Float

**[2024-12] | Enforce Decimal(2) precision for all cash values | APPROVED**

**Problem**: Floating-point arithmetic loses precision in financial systems. Example: `0.1 + 0.2 ≠ 0.3` in binary floats.

**Solution**: All monetary values use Python's `Decimal` type with 2 decimal places (cents). Enforced in Pydantic models and order validation.

**Code Example**:

```python
# ✅ REQUIRED
balance = Decimal("10250.50")

# ❌ FORBIDDEN
balance = 10250.50  # Float! Precision loss at scale.
```

**Alternatives**:

- **Integer representation** (store cents): More work, less readable
- **BigDecimal** (Java-like): Overkill for Python; use native Decimal

**Trade-offs**:

- **Pro**: Exact precision, auditable math
- **Pro**: Industry standard (all fintech uses Decimal)
- **Con**: Slightly slower than float (negligible for order latency)
- **Con**: Requires explicit conversion from IBKR API (`Decimal(str(value))`)

**Enforcement**:

- Code review: Check all money variables are `Decimal`
- Type hints: Use `Decimal` type annotation
- Tests: Assert `isinstance(value, Decimal)`

**Related**: [01_RULES.md](.context/01_RULES.md) Rule #3

---

### 2. Five Safety Gates for Live Orders (Not One)

**[2024-12] | Implement 5-layer safety gates (not single gate) | APPROVED**

**Problem**: Live trading is dangerous. Single safety check is insufficient (one code path might bypass it).

**Solution**: Implement 5 independent gates:

1. Startup: Config validation (TRADING_MODE valid)
2. Startup: Override file exists
3. Runtime: Check TRADING_MODE == paper
4. Runtime: Check ORDERS_ENABLED == true
5. Runtime: Deterministic orderId + audit logging

**Why 5 gates?**

```python
# Each gate catches different failure modes:
# Gate 1: Catches config typos (TRADING_MODE="LIVE" vs "live")
# Gate 2: Catches copy-paste errors (override file path wrong)
# Gate 3: Catches env var override mistakes
# Gate 4: Catches ORDERS_ENABLED default (false)
# Gate 5: Catches duplicate order placement (idempotency)

# Redundancy: Even if 1-4 fail, gate 5 prevents duplicate placement
# Defense in depth: Multiple independent checks
```

**Alternatives**:

- **Single gate**: `if is_safe_to_trade(): place_order()` - **Rejected** (too fragile)
- **Two gates** (config + runtime): **Rejected** (insufficient)
- **Three gates** (what competitors do): **Rejected** (we need more safety)

**Trade-offs**:

- **Pro**: Nearly impossible to accidentally trade live
- **Pro**: Each gate catches different error types
- **Pro**: Can disable gates independently for testing
- **Con**: More code to write and maintain
- **Con**: Slightly more latency (~1ms per gate check)

**Enforcement**:

- Test: Each gate independently, then all together
- Code review: No "shortcuts" or "testing modes"

**Related**: [01_RULES.md](.context/01_RULES.md) Rule #2; [04_RISK_GUARDRAILS.md](.context/04_RISK_GUARDRAILS.md)

---

### 3. Immutable Audit Trail (Append-Only, No Deletes)

**[2024-12] | Make audit.db append-only (no deletes or updates) | APPROVED**

**Problem**: Regulatory compliance requires permanent audit trail. Deletions or updates destroy evidence.

**Solution**: SQLite schema with UNIQUE constraints and append-only inserts. Never UPDATE or DELETE orders/audit records.

**Schema**:

```sql
CREATE TABLE orders (
    orderId TEXT PRIMARY KEY,  -- Immutable
    symbol TEXT,
    action TEXT,
    status TEXT,
    timestamp TEXT,
    correlation_id TEXT,
    config_snapshot JSON
    -- No UPDATE or DELETE allowed; only INSERT
);

CREATE UNIQUE INDEX idx_order_unique 
ON orders (orderId, action, timestamp);
```

**Alternatives**:

- **Soft deletes** (add `deleted` column): **Rejected** (still ambiguous)
- **Event sourcing** (log all state changes): **Too complex** (overkill)
- **Relational normalization** (separate tables): **Okay** (current choice)

**Trade-offs**:

- **Pro**: Audit trail is immutable (regulatory compliant)
- **Pro**: Can replay order history deterministically
- **Pro**: Simple implementation (just INSERT)
- **Con**: Storage grows over time (solution: archive monthly)
- **Con**: No ability to fix mistakes (solution: new order, not update)

**Enforcement**:

- Code review: No UPDATE/DELETE on orders table
- Tests: Verify UNIQUE constraint on inserts
- Operations: Archive audit.db monthly to archive/ folder

**Related**: [01_RULES.md](.context/01_RULES.md) Rule #6

---

### 4. Deterministic Order IDs (Hash-Based, Not Random)

**[2024-12] | Generate orderId deterministically (hash input) | APPROVED**

**Problem**: Network timeouts → client retries → duplicate orders placed. Need idempotency without state mutation.

**Solution**: Hash order input (symbol + action + qty + price) to generate deterministic orderId. Check audit.db for existing orderId; if found, return previous result.

**Code Example**:

```python
def place_order(symbol, action, qty, orderType, limit=None):
    # Deterministic ID
    orderId = hash_input(symbol, action, qty, orderType, limit)
    
    # Check if already placed
    existing = audit_db.query("SELECT * FROM orders WHERE orderId = ?", orderId)
    if existing:
        return existing[0]  # Return previous result (idempotent)
    
    # New order
    result = _place_real_order(symbol, action, qty, orderType, limit)
    audit_db.insert(result)
    return result
```

**Alternatives**:

- **Random UUIDs**: **Rejected** (not idempotent; retries = duplicates)
- **Sequence numbers**: **Rejected** (global state, hard to sync)
- **ULID** (timestamp + random): **Considered** (less deterministic)

**Trade-offs**:

- **Pro**: Retries are safe (idempotent)
- **Pro**: Same input always produces same orderId
- **Pro**: Works without centralized state
- **Con**: Predictable orderIds (security: orderIds can be guessed)
- **Con**: Requires audit.db lookup (micro-latency)

**Enforcement**:

- Tests: Verify `place_order(A) == place_order(A)` (same result)
- Tests: Verify retry returns cached result
- Code review: Hash function is stable

**Related**: [01_RULES.md](.context/01_RULES.md) Rule #5

---

### 5. Contract Resolution Cache (Session-Scoped, Not Persistent)

**[2024-12] | Cache contracts in-memory; invalidate on restart | APPROVED**

**Problem**: Resolving contracts (symbol → IBKR conId) is slow (IBKR API call). But contracts can change (delistings, splits, symbol changes).

**Solution**: Cache contracts in-memory during session. Invalidate entire cache on restart.

**Code Example**:

```python
# In-memory cache
contract_cache = {}  # Dict[key] -> Contract

def resolve_contract(symbol, securityType, exchange="SMART"):
    key = (symbol, securityType, exchange)
    
    if key in contract_cache:
        return contract_cache[key]  # Cache hit
    
    # Cache miss: call IBKR API
    contract = ib.qualifyContract(Contract(
        symbol=symbol,
        securityType=securityType,
        exchange=exchange
    ))
    
    contract_cache[key] = contract  # Store in cache
    return contract

# On restart:
contract_cache = {}  # Cache invalidated
```

**Alternatives**:

- **Persistent cache** (save to disk): **Rejected** (stale contracts are dangerous)
- **TTL cache** (expire after 1 hour): **Considered** (too complex; restart is cleaner)
- **No cache** (always call IBKR): **Too slow** (~100ms per contract)

**Trade-offs**:

- **Pro**: Fast (cache hits ~99%)
- **Pro**: Simple implementation (dict)
- **Pro**: Safe (invalidates on restart)
- **Con**: Cold start is slow (first 100 contracts = 10 seconds)
- **Con**: If IBKR contracts change mid-session, cache is stale

**Enforcement**:

- Code: Don't persist cache to disk
- Code: Clear cache on startup
- Tests: Mock IBKR API; verify cache behavior
- Ops: Restart service if contract issue suspected

**Related**: [01_RULES.md](.context/01_RULES.md) Rule #7

---

### 6. UTC Timestamps (ISO 8601) for All Time

**[2024-12] | All timestamps must be UTC ISO 8601 | APPROVED**

**Problem**: Trading spans time zones (NYSE opens 9:30 AM EST, IBKR Gateway in multiple zones). Local time is ambiguous and error-prone.

**Solution**: All internal timestamps are UTC in ISO 8601 format. Local time conversion happens only at display time.

**Code Example**:

```python
# ✅ CORRECT
from datetime import datetime
import pytz

ts = datetime.now(pytz.UTC).isoformat()
# Result: "2025-01-30T14:35:22.123456+00:00"

# ❌ FORBIDDEN
ts = datetime.now()  # Local time! Ambiguous!
ts = time.time()     # Unix epoch! Hard to debug!
ts = "2025-01-30 14:35"  # No timezone!
```

**Alternatives**:

- **Unix epoch** (seconds since 1970): **Rejected** (not human-readable; hard to debug)
- **Local time** (system timezone): **Rejected** (ambiguous across regions)
- **EST/EDT** (market hours): **Rejected** (daylight savings confusion)

**Trade-offs**:

- **Pro**: Unambiguous globally
- **Pro**: Human-readable (ISO 8601 is standard)
- **Pro**: Easy to compare/sort
- **Con**: Requires timezone-aware datetime (more verbose)
- **Con**: Display requires conversion (minor inconvenience)

**Enforcement**:

- Type: Always `datetime` with `tzinfo=pytz.UTC`
- Type: String timestamps are ISO 8601
- Tests: Assert `"+00:00"` in timestamp string
- Code review: No `datetime.now()` (use `datetime.now(pytz.UTC)`)

**Related**: [01_RULES.md](.context/01_RULES.md) Rule #4

---

### 7. Dedicated Executor Thread for IBKR Calls (Not Event Loop)

**[2024-12] | Run IBKR calls in dedicated thread; don't block event loop | APPROVED**

**Problem**: IBKR SDK (ib-insync) uses blocking I/O. Running in async event loop causes deadlocks and timeouts.

**Solution**: Create dedicated executor thread. All IBKR calls (`resolve_contract`, `get_quote`, `place_order`) run in this thread, not in async event loop.

**Code Pattern**:

```python
# ✅ CORRECT
executor = ThreadPoolExecutor(max_workers=1)
loop = asyncio.get_event_loop()

async def get_quote(symbol):
    contract = await loop.run_in_executor(
        executor, 
        resolve_contract_sync,  # Blocking function
        symbol
    )
    quote = await loop.run_in_executor(
        executor,
        get_quote_sync,
        contract
    )
    return quote

# ❌ FORBIDDEN (deadlock!)
async def get_quote_bad(symbol):
    contract = resolve_contract_sync(symbol)  # Blocks event loop!
    return contract
```

**Alternatives**:

- **Pure async** (rewrite ib-insync): **Too much work** (would require months)
- **Blocking event loop** (no executor): **Causes deadlocks** (rejected)
- **Multiple threads** (ThreadPoolExecutor with N workers): **Okay**, but 1 thread is safer

**Trade-offs**:

- **Pro**: No deadlocks; event loop stays responsive
- **Pro**: IBKR SDK works out-of-the-box
- **Pro**: Single-threaded executor avoids race conditions
- **Con**: Serializes IBKR calls (can't parallelize)
- **Con**: Adds complexity (loop.run_in_executor)

**Enforcement**:

- Code review: No blocking calls in async functions
- Tests: Verify executor thread is used
- Operations: Monitor thread pool for stalls

**Related**: [02_ARCHITECTURE.md](.context/02_ARCHITECTURE.md); [07_STYLE_AND_PATTERNS.md](.context/07_STYLE_AND_PATTERNS.md)

---

### 8. Correlation IDs for Request Tracing (End-to-End)

**[2024-12] | Every request gets unique correlation_id (UUID) | APPROVED**

**Problem**: Debugging production issues requires tracing a request through multiple components (API → ibkr_core → IBKR → audit.db). Hard without correlation.

**Solution**: Generate UUID for each request. Attach to all logs, audit records, and responses.

**Code Example**:

```python
# HTTP middleware
async def trace_middleware(request, call_next):
    correlation_id = request.headers.get("X-Correlation-ID") or uuid.uuid4().hex
    request.state.correlation_id = correlation_id
    response = await call_next(request)
    response.headers["X-Correlation-ID"] = correlation_id
    return response

# In order placement
@app.post("/api/orders/place")
async def place_order_endpoint(req: OrderRequest, request: Request):
    cid = request.state.correlation_id
    logger.info(f"[{cid}] Placing order", extra={"correlation_id": cid})
    
    result = await place_order(req)
    audit_db.insert({
        "correlation_id": cid,
        "orderId": result.orderId,
        "action": "place"
    })
    
    return {"orderId": result.orderId, "correlation_id": cid}
```

**Alternatives**:

- **No correlation IDs**: **Rejected** (hard to debug)
- **Request IDs per service**: **Rejected** (not end-to-end)
- **Tracing library (Jaeger, DataDog)**: **Overkill** (not used yet)

**Trade-offs**:

- **Pro**: End-to-end tracing for any request
- **Pro**: Simple to implement (just pass UUID)
- **Pro**: Zero performance overhead
- **Con**: Requires discipline (must pass through all functions)

**Enforcement**:

- Middleware: Auto-inject correlation_id
- Code: Always pass correlation_id to nested functions
- Logging: Always include in structured logs
- Audit: Always store with order records

**Related**: [07_STYLE_AND_PATTERNS.md](.context/07_STYLE_AND_PATTERNS.md)

---

### 9. Three Interfaces (Python API, REST API, MCP)

**[2024-12] | Support 3 interfaces: Python, REST, MCP | APPROVED**

**Problem**: Different users have different needs:

- Developers want Python API (programmatic)
- Infrastructure wants REST API (HTTP, firewall-friendly)
- AI (Claude) wants MCP (structured tool calls)

**Solution**: Single `ibkr_core` business logic. Three independent interfaces (api/, mcp_server/, direct Python).

**Architecture**:

```text
┌─────────────────────────────┐
│    ibkr_core (Logic)        │
├────────┬────────┬───────────┤
│        │        │           │
▼        ▼        ▼           ▼
Python   REST     MCP       Direct
API      API      Server    Use
```

**Alternatives**:

- **Single monolithic interface**: **Rejected** (not flexible)
- **Separate codebases per interface**: **Rejected** (duplication, hard to maintain)
- **Only REST API**: **Rejected** (not Pythonic)

**Trade-offs**:

- **Pro**: Flexible; use the interface you need
- **Pro**: Logic is DRY (one place)
- **Pro**: Easy to add new interfaces (4th, 5th, etc.)
- **Con**: Three places to test (Python, REST, MCP)
- **Con**: Slightly more code (three entry points)

**Enforcement**:

- Code: `ibkr_core` has no HTTP/MCP dependencies
- Tests: Test each interface independently
- Code review: Changes to ibkr_core might affect 3 interfaces

**Related**: [02_ARCHITECTURE.md](.context/02_ARCHITECTURE.md)

---

### 10. Paper Mode by Default (Not Live)

**[2024-12] | Default TRADING_MODE=paper | APPROVED**

**Problem**: Accidental live trading is catastrophic. Many systems default to "safe mode"; we should too.

**Solution**: `TRADING_MODE=paper` by default. Live trading requires explicit `.env` configuration + override file.

**Enforcement**:

```python
# In config.py
TRADING_MODE = os.getenv("TRADING_MODE", "paper")  # Default: paper
ORDERS_ENABLED = os.getenv("ORDERS_ENABLED", "false")  # Default: false
```

**Alternatives**:

- **Live by default**: **Too dangerous** (rejected immediately)
- **Autodetect** (prod vs dev): **Ambiguous** (rejected)

**Trade-offs**:

- **Pro**: Safe by default
- **Pro**: Developers can't accidentally trade live
- **Con**: Production deployment requires config (not hard)

**Related**: [01_RULES.md](.context/01_RULES.md) Rule #1; [04_RISK_GUARDRAILS.md](.context/04_RISK_GUARDRAILS.md)

---

### 11. Use ib-insync for IBKR Integration (Not Manual API)

**[2024-12] | Use ib_insync SDK wrapper | APPROVED**

**Problem**: Interactive Brokers API is complex (socket protocol, async callback hell). Manual implementation would be fragile and unmaintained.

**Solution**: Use mature `ib_insync` library (>=0.9.17) as abstraction layer.

**Code**:

```python
from ib_insync import IB, Contract, Order

# Connection
ib = IB()
await ib.connectAsync("127.0.0.1", 4002, clientId=1)

# Contract resolution
contract = Contract(symbol="AAPL", securityType="STK", exchange="SMART")
contract = ib.qualifyContracts(contract)[0]

# Order placement
order = Order(action="BUY", totalQuantity=100, orderType="MKT")
orderId = ib.placeOrder(contract, order)
```

**Alternatives**:

- **Manual API** (socket protocol): **Too complex**, high maintenance burden
- **Java API** (via subprocess): **Rejected**, adds process management complexity
- **Official Python API**: **Doesn't exist** (only Java/C++)

**Trade-offs**:

- **Pro**: Stable library maintained by community
- **Pro**: Handles reconnection, async properly
- **Pro**: Good error messages
- **Con**: Dependency on third-party library (version pins required)
- **Con**: Library updates require testing

**Enforcement**:

- Pin version: `ib-insync>=0.9.17,<1.0`
- Test all IBKR operations with mock
- Monitor GitHub issues for breaking changes

**Related**: [08_DEPENDENCIES.md](08_DEPENDENCIES.md)

---

### 12. SQLite for Audit Trail (Not Postgres/Cloud)

**[2024-12] | Use SQLite for audit.db | APPROVED**

**Problem**: Need immutable audit trail of all orders. Options: SQLite, Postgres, DynamoDB, etc.

**Solution**: SQLite embedded database (data/audit.db) with append-only schema.

**Why SQLite**:

- Simple (single file, no server)
- ACID-compliant (immutable audit trail guaranteed)
- Portable (ships with Python)
- Fast enough (635 tests pass in 30 sec)

**Schema**:

```sql
CREATE TABLE orders (
    orderId TEXT PRIMARY KEY,
    symbol TEXT,
    action TEXT,
    status TEXT,
    timestamp TEXT,
    correlation_id TEXT,
    config_snapshot JSON
    -- Never UPDATE or DELETE
);
```

**Alternatives**:

- **Postgres**: Too heavy, requires external server
- **DynamoDB**: Overkill for local system, plus AWS costs
- **Files**: Loss of ACID guarantees
- **In-memory**: Loss of persistence across restarts

**Trade-offs**:

- **Pro**: Zero configuration, ships with Python
- **Pro**: ACID compliance for audit trail
- **Pro**: Single-file deployment
- **Con**: Storage limited to single machine (not cloud)
- **Con**: Scales poorly with 1000s of orders (but OK for trading)

**Enforcement**:

- Use SQLite for all audit/order persistence
- Never UPDATE or DELETE orders (append-only)
- Archive audit.db monthly to archive/ folder

**Related**: [01_RULES.md](.context/01_RULES.md) Rule #6

---

### 13. Pydantic for Request/Response Validation (Not Manual)

**[2024-12] | Use Pydantic for all API models | APPROVED**

**Problem**: Manual validation of API requests is error-prone and repetitive.

**Solution**: Pydantic BaseModel for automatic validation, serialization, and documentation.

**Code**:

```python
from pydantic import BaseModel, Field

class OrderSpec(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=20)
    action: str = Field(..., pattern="^(BUY|SELL|BUYTOCOVER|SELLSHORT)$")
    quantity: int = Field(..., gt=0)
    orderType: str = Field(..., pattern="^(MKT|LMT|STP|STP_LMT)$")
    
    class Config:
        # Pydantic V2 config
        strict = True  # No type coercion
```

**Benefits**:

- Automatic validation
- Type coercion (safe)
- JSON schema generation (FastAPI /docs)
- Serialization round-trip

**Alternatives**:

- **Manual validation**: Too error-prone
- **Marshmallow**: More verbose than Pydantic

**Trade-offs**:

- **Pro**: Auto validation + documentation
- **Pro**: Serialization for JSON/DB
- **Con**: Requires learning Pydantic patterns
- **Con**: Adds dependency (pydantic>=2.0)

**Enforcement**:

- All API models inherit from `pydantic.BaseModel`
- Use `Field()` for validation rules
- Tests verify serialization round-trip

**Related**: [03_DATA_CONTRACTS.md](03_DATA_CONTRACTS.md)

---

### 14. MOC Orders Use orderType="MOC" with DAY TIF

**[2026-02] | Map MOC orders to orderType=MOC and enforce DAY TIF | APPROVED**

**Problem**: IBKR rejects orders that set `tif="MOC"` with error `Invalid time in force:MOC`.
MOC is an order type, not a time-in-force. Our prior mapping used `MarketOrder` with `tif="MOC"`,
which caused IBKR errors even though the order could later fill.

**Solution**: Build MOC orders with `orderType="MOC"` and `tif="DAY"` regardless of user input,
and validate MOC specs so `tif` must be `DAY`.

**Code Example**:

```python
order = Order()
order.orderType = "MOC"
order.tif = "DAY"
```

**Alternatives**:

- **Leave as MarketOrder + tif=MOC**: Rejected (IBKR rejects TIF=MOC).
- **Ignore tif validation**: Rejected (allows invalid specs to slip through).

**Trade-offs**:

- **Pro**: Matches IBKR semantics; no TIF errors.
- **Pro**: MOC orders execute at close as intended.
- **Con**: Stricter validation may reject previously accepted (but invalid) requests.

**Enforcement**:

- `validate_order_spec` enforces `tif="DAY"` for `orderType="MOC"`.
- `_build_ib_order` sets `orderType="MOC"` and `tif="DAY"`.

**Related**: `ibkr_core/orders.py`, `ibkr_core/models.py`

---

## External Systems Integration

| System | Purpose | Protocol | Failure Impact | Recovery |
| -------- | --------- | ---------- | ---------------- | ---------- |
| **IBKR Gateway** (port 4002) | Market data, orders, account | TCP socket | Orders can't be placed | Retry with backoff |
| **IBKR Live/Paper** (via Gateway) | Real trading (if enabled) | IB Protocol | REAL MONEY at risk | Idempotent order IDs prevent duplication |
| **SQLite (audit.db)** | Order history, audit trail | File I/O | Can't log orders | Queue in memory, retry on startup |
| **HTTP REST API** | External clients | HTTP/JSON | API unavailable | Client retries |
| **MCP (stdio)** | Claude integration | stdin/stdout | Claude can't trade | Retry from Claude |

---

## Decision Template

Use this for future decisions:

```markdown
### N. [Title]

**[YYYY-MM] | [Decision] | [Status: APPROVED/REJECTED/PENDING]**

**Problem**: 

**Solution**: 

**Code Example**:
\`\`\`python
# Your code
\`\`\`

**Alternatives**: 

**Trade-offs**: 
- **Pro**: 
- **Pro**: 
- **Con**: 
- **Con**: 

**Enforcement**: 

**Related**: 
```

---

## Summary Table

| Decision | Status | Risk | Impact |
| -------- | -------- | ------ | -------- |
| Decimal for money | ✅ Approved | Low | High (prevents errors) |
| 5 safety gates | ✅ Approved | Low | Critical (prevents live accidents) |
| Append-only audit | ✅ Approved | Low | High (compliance) |
| Deterministic orderIds | ✅ Approved | Low | High (idempotency) |
| Session-scoped contracts | ✅ Approved | Low | Medium (performance) |
| UTC ISO 8601 time | ✅ Approved | Low | Medium (clarity) |
| Executor thread | ✅ Approved | Low | Medium (reliability) |
| Correlation IDs | ✅ Approved | Low | Medium (debuggability) |
| 3 interfaces | ✅ Approved | Low | High (flexibility) |
| Paper mode by default | ✅ Approved | Low | Critical (safety) |
| ib-insync SDK | ✅ Approved | Low | High (stability) |
| SQLite audit | ✅ Approved | Low | High (compliance) |
| Pydantic validation | ✅ Approved | Low | Medium (quality) |
| MOC orderType + DAY TIF | ✅ Approved | Low | Medium (correctness) |

---

## How to Add Decisions

When you make a non-obvious architectural choice:

1. **Document it here** with Decision template
2. **Update 01_RULES.md** if it affects system invariants
3. **Link from relevant .context/ files**
4. **Get PR review approval** before merging

This keeps context current and prevents loss of institutional knowledge.

