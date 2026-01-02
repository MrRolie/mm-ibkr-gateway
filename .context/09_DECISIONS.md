# 09_DECISIONS.md: Architectural & Design Decisions

## Decision Record Template

When making non-trivial decisions, record them here:

```markdown
### Decision: [Title]

**Date**: YYYY-MM-DD
**Status**: Decided | Proposed | Superseded
**Severity**: Critical | High | Medium | Low

**Context**:
- Why was this decision needed?
- What was the problem being solved?

**Options Considered**:
1. Option A: [Description] - Pros: [...] Cons: [...]
2. Option B: [Description] - Pros: [...] Cons: [...]

**Decision**:
We chose [Option X] because [rationale].

**Consequences**:
- What changes as a result?
- Any new constraints or assumptions?

**Revisit**: [Date or condition when we should reconsider]
```

---

## Active Decisions

### Decision: Dual-Gate Safety Model for Live Trading

**Date**: 2024-12 (Inferred from code)
**Status**: Decided
**Severity**: Critical

**Context**:
System must prevent accidental live trading, especially in development. Paper trading is the safe default.

**Options Considered**:

1. **Single boolean flag**: `TRADING_MODE=true` or `TRADING_MODE=false`
   - Pros: Simple
   - Cons: Easy to typo, toggle; no recovery mechanism

2. **Override file only**: Requires file to exist for live mode
   - Pros: Physical confirmation (can be deleted to disable)
   - Cons: Unclear what enables it

3. **Dual gate** (chosen): `TRADING_MODE` + `ORDERS_ENABLED` + override file for live
   - Pros: Multiple confirmation steps; file deletion disables immediately
   - Cons: More complex config

**Decision**:
Implemented dual-gate model:

1. `TRADING_MODE` env var (paper or live)
2. `ORDERS_ENABLED` env var (false by default)
3. Override file must exist if `TRADING_MODE=live` AND `ORDERS_ENABLED=true`

All three gates validated at startup, preventing accidental bypasses.

**Consequences**:

- Configuration is explicit and validated
- Requires three separate steps to enable live trading
- Deleting override file immediately disables live mode
- Safe by default (paper mode disabled orders)

**Revisit**: Never (foundational safety invariant)

---

### Decision: SQLite for Audit Log (Not PostgreSQL)

**Date**: 2024-12 (Inferred)
**Status**: Decided
**Severity**: High

**Context**:
Need append-only audit trail for order history. Trade-off between simplicity and scalability.

**Options Considered**:

1. **SQLite** (chosen): File-based, zero setup
   - Pros: No server, no auth, embedded, simple, append-only enforced
   - Cons: Not clustered, limited concurrency

2. **PostgreSQL**: Full relational DB
   - Pros: Clustered, scalable, better concurrency
   - Cons: Requires server, authentication, more ops

3. **Append-only file**: Raw JSON log
   - Pros: Truly immutable, no DB setup
   - Cons: No querying, no schema

**Decision**:
SQLite. Sufficient for single-account retail trading; simple to backup and move.

**Consequences**:

- Audit data stored in `data/audit.db`
- Schema versioned for migrations
- Backups via file copy: `cp data/audit.db data/audit_backup.db`
- Scaling to multi-account requires migration to PostgreSQL (future decision)

**Revisit**: If handling >10k orders/day or multi-account, reconsider PostgreSQL

---

### Decision: Dedicated IBKR Executor Thread

**Date**: 2024-12 (Inferred)
**Status**: Decided
**Severity**: High

**Context**:
ib_insync requires persistent asyncio event loop in the thread where it runs. FastAPI runs in default asyncio executor, which may not have event loop on every thread.

**Options Considered**:

1. **Dedicated thread** (chosen): Single-threaded executor with its own event loop
   - Pros: Guaranteed event loop, no "no event loop" errors, thread-safe
   - Cons: Requires `run_in_executor()` calls

2. **Default executor**: Run ib_insync in same thread as FastAPI
   - Pros: Simpler code
   - Cons: Risk of "no event loop in current thread" errors

3. **Separate process**: IBKR operations in different process
   - Pros: Isolation
   - Cons: IPC overhead, complexity

**Decision**:
Dedicated single-threaded executor for all ib_insync operations.

```python
self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="IBKR")
# All ib_insync calls via:
await loop.run_in_executor(self.executor, blocking_call, *args)
```

**Consequences**:

- All IBKR operations are thread-safe (single thread)
- Event loop guaranteed to exist in IBKR thread
- No "no event loop" errors
- Slight latency overhead (thread context switch)

**Revisit**: If performance bottleneck on IBKR operations, consider thread pool with size>1 and proper event loop management

---

### Decision: Pydantic for All API Models

**Date**: 2024-12 (Inferred)
**Status**: Decided
**Severity**: Medium

**Context**:
Need validation and serialization for HTTP requests/responses. Also need OpenAPI schema generation.

**Options Considered**:

1. **Pydantic v2** (chosen): Modern validation, FastAPI-native
   - Pros: Built into FastAPI, excellent IDE support, custom validators, JSON schema
   - Cons: Breaking changes from v1 (but v2 is stable)

2. **Manual validation**: Custom code
   - Pros: Full control
   - Cons: Error-prone, verbose, no schema generation

3. **JSON Schema + validators**: Separate schema definition
   - Pros: Standard format
   - Cons: Disconnected from code

**Decision**:
Pydantic v2 for all request/response models and domain models.

**Consequences**:

- Validation happens automatically on instantiation
- JSON schema auto-generated for OpenAPI docs
- Type hints and IDE autocomplete
- Config changes require Pydantic model updates

**Revisit**: Never (production-ready standard)

---

### Decision: Contract Resolution Caching (In-Memory Only)

**Date**: 2024-12 (Inferred)
**Status**: Decided
**Severity**: Medium

**Context**:
Contract resolution (symbol → IBKR contract ID) is slow (~500ms). Caching reduces IBKR API calls.

**Options Considered**:

1. **In-memory cache** (chosen): Per-session cache
   - Pros: Fast, no persistence needed, simple
   - Cons: Cache stale after delisting, cleared on restart

2. **Persistent cache**: SQLite or Redis
   - Pros: Survives restarts
   - Cons: Stale data risk, added complexity

3. **No cache**: Every resolution hits IBKR
   - Pros: Always fresh
   - Cons: Slow, high API load

**Decision**:
In-memory cache with session lifetime. Cache cleared on client restart.

```python
contract_cache: Dict[str, Contract] = {}
def resolve_contract(spec: SymbolSpec) -> Contract:
    key = (spec.symbol, spec.securityType, spec.exchange, spec.currency)
    if key in contract_cache:
        return contract_cache[key]
    # Resolve from IBKR...
    contract_cache[key] = contract
    return contract
```

**Consequences**:

- Eliminates ~500ms latency for second+ requests to same symbol
- Stale cache if symbol delisted (rare; restart clears)
- No persistence; fresh resolve on app restart
- Suitable for single-day trading sessions

**Revisit**: If handling multi-day sessions or high delisting risk, consider persistent cache with TTL

---

### Decision: MCP Tools as Thin HTTP Wrappers

**Date**: 2024-12 (Inferred)
**Status**: Decided
**Severity**: Medium

**Context**:
MCP server needs to expose IBKR functions to Claude. Two architectures: thick wrapper or thin wrapper.

**Options Considered**:

1. **Thin HTTP wrapper** (chosen): MCP tools call REST API via HTTP
   - Pros: No code duplication, single source of truth (ibkr_core), testable in isolation
   - Cons: HTTP overhead, dependency on REST API

2. **Thick wrapper**: MCP tools call ibkr_core directly
   - Pros: No HTTP overhead
   - Cons: Code duplication, two integration paths

3. **Shared SDK**: Extract ibkr_core as package, import in both MCP and API
   - Pros: Single source, direct use
   - Cons: Packaging complexity, requires installing locally

**Decision**:
Thin HTTP wrapper. MCP tools call REST API at <http://localhost:8000>.

```python
# In mcp_server/main.py
@mcp.tool()
async def get_quote(symbol: str, security_type: str) -> str:
    client = IBKRAPIClient(base_url="http://localhost:8000")
    response = await client.get_quote(symbol, security_type)
    return response.model_dump_json()
```

**Consequences**:

- Single source of truth: `ibkr_core`
- REST API must be running for MCP to work
- HTTP overhead negligible (~10ms per call)
- Easy to test each layer independently
- Clear separation of concerns

**Revisit**: If HTTP latency becomes bottleneck or MCP needs to run standalone, extract shared SDK

---

### Decision: Deterministic Order IDs

**Date**: 2024-12 (Inferred)
**Status**: Decided
**Severity**: Critical

**Context**:
Need to prevent duplicate orders if user retries placement request. Also need idempotent audit log writes.

**Options Considered**:

1. **Deterministic hash** (chosen): Hash of (symbol, action, quantity, type) → orderId
   - Pros: Same input = same ID, idempotent, no sequence needed
   - Cons: Predictable IDs, same order twice appears as duplicate

2. **Sequence (UUID/serial)**: Database-assigned sequential or random ID
   - Pros: Unique, non-predictable
   - Cons: Non-idempotent (retry = new ID), no deduplication

3. **Server-side dedup**: Track request hash, return cached result
   - Pros: Idempotent without deterministic IDs
   - Cons: Requires state management, cache eviction

**Decision**:
Deterministic hash: `orderId = hash(symbol + action + quantity + orderType + timestamp_rounded_to_second)`

```python
def generate_order_id(spec: OrderSpec) -> int:
    import hashlib
    key = f"{spec.symbol}:{spec.action}:{spec.quantity}:{spec.order_type}"
    return int(hashlib.md5(key.encode()).hexdigest(), 16) % (2**31)
```

**Consequences**:

- Same order placed twice gets same orderId (IBKR rejects as duplicate)
- Audit log unique constraint prevents duplicate writes
- Enables safe retries without duplicating orders

**Revisit**: Never (foundational for order idempotency)

---

### Decision: UTC Timestamps with ISO 8601 Format

**Date**: 2024-12 (Inferred)
**Status**: Decided
**Severity**: High

**Context**:
System operates globally. Need unambiguous, standardized timestamps.

**Options Considered**:

1. **UTC + ISO 8601** (chosen): e.g., "2025-01-01T09:35:00Z"
   - Pros: Standard, unambiguous, no timezone confusion
   - Cons: Requires conversion to display in local tz

2. **Unix timestamp**: e.g., 1735744500
   - Pros: Compact, language-agnostic
   - Cons: Not human-readable

3. **Local timezone**: Store with tz info, e.g., "2025-01-01T09:35:00-05:00"
   - Pros: Preserves local context
   - Cons: Confused by DST, ambiguous

**Decision**:
All persisted timestamps UTC + ISO 8601 format with Z suffix (e.g., "2025-01-01T09:35:00Z").

```python
from datetime import datetime, timezone
timestamp = datetime.now(timezone.utc).isoformat()  # "2025-01-01T09:35:00.123456+00:00"
# Or with Z: datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
```

**Consequences**:

- All audit log and API timestamps are UTC
- Local display requires conversion (handled in UI)
- No ambiguity across time zones
- Enables global replaying of event history

**Revisit**: Never (international standard)

---

### Decision: Decimal for All Money Values

**Date**: 2024-12 (Inferred)
**Status**: Decided
**Severity**: Critical

**Context**:
Financial applications cannot use IEEE 754 floats (0.1 + 0.2 != 0.3 problem). Need exact decimal arithmetic.

**Options Considered**:

1. **Python Decimal** (chosen): `from decimal import Decimal`
   - Pros: Exact arithmetic, 2 decimal place precision, standard
   - Cons: Slightly slower than float

2. **Integer cents**: Store all amounts as integers (100 = $1.00)
   - Pros: No floating point at all
   - Cons: Verbose, harder to debug

3. **Float with rounding**: Use float but round carefully
   - Pros: Familiar
   - Cons: Unreliable (rounding still loses precision)

**Decision**:
Decimal with 2 decimal places (cents precision) for all money values: prices, commissions, P&L, cash.

```python
from decimal import Decimal

price = Decimal("150.25")  # $150.25
# Never: price = 150.25  (float - WRONG)

# Rounding
price = price.quantize(Decimal("0.01"))  # Round to 2 decimals
```

**Consequences**:

- No hidden rounding errors in P&L calculations
- All Pydantic money fields use Decimal type
- JSON serialization uses `Decimal(str(...))` for parsing
- Slight performance cost (negligible at order volumes)

**Revisit**: Never (critical for financial correctness)

---

## Proposed Decisions (Under Consideration)

### Proposal: Persistent Contract Cache with TTL

**Context**: In-memory cache stales on delisting (rare but can happen intraday)

**Suggested Approach**: SQLite cache with 24-hour TTL

**Status**: Proposed (revisit if multi-day sessions become common)

---

### Proposal: PostgreSQL Migration

**Context**: If system scales to 100k+ orders/day or multi-account

**Suggested Approach**: Migrate audit log to PostgreSQL, keep SQLite as optional fallback

**Status**: Proposed (revisit if load exceeds 10k orders/day)

---

### Proposal: Explicit Rate Limiter

**Context**: ib_insync has implicit rate limits; explicit limiter would be clearer

**Suggested Approach**: `ratelimit` library with 50 orders/sec limit

**Status**: Proposed (implement if seeing broker rate limit rejections)

---

## Superseded Decisions

(None yet, will record as decisions are revisited)

---

## How to Add a Decision

1. **Discuss**: Team aligns on the problem
2. **Decide**: Pick best option with rationale
3. **Record**: Add to this file under "Active Decisions"
4. **Implement**: Update code, tests, `.context/` docs
5. **Revisit**: Mark any conditions for reconsideration

---

## Summary

Key invariants embedded in these decisions:

- ✅ Safety first (dual-gate live trading)
- ✅ Audit trail (append-only SQLite)
- ✅ Idempotency (deterministic order IDs)
- ✅ Correctness (Decimal for money, UTC timestamps)
- ✅ Simplicity (thin MCP wrapper, in-memory contract cache)

None of these decisions should be reversed without careful consideration and team discussion.
