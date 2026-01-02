# START HERE: IBKR Gateway Agent Onboarding

## What This Repository Does

A complete, modular integration of Interactive Brokers (IBKR) with three interfaces: direct Python API (`ibkr_core`), REST API (`api/`), and Claude MCP server (`mcp_server/`). Provides market data, account management, and order execution with **paper trading by default** and explicit safety gates for live trading. All order logic is simulated unless both `TRADING_MODE=live` AND `ORDERS_ENABLED=true` with an override file.

---

## Non-Negotiable Invariants

These constraints **must never be violated**:

- **🔴 Default Safety**: System boots in `TRADING_MODE=paper` and `ORDERS_ENABLED=false`. Live orders are **always simulated** unless BOTH flags are true AND override file exists.
- **🔴 Order Idempotency**: Order placement returns deterministic `orderId` for same input. Subsequent calls with same orderId are no-ops (Postgres audit table uses `(orderId, action, timestamp)` unique constraint).
- **🔴 Audit Trail**: Every order action (place, fill, cancel) writes immutable log to `data/audit.db` with correlation ID and config snapshot.
- **🔴 No Lost Fills**: Position tracking is accurate. Double-check against IBKR account nightly via reconciliation. Never discard a fill.
- **🔴 Rounding**: All money values use Python `Decimal` with 2 decimal places (cents). No floats for cash/P&L.
- **🔴 Timezone**: All timestamps are UTC in ISO 8601 format. Conversion to local tz happens at display time only.
- **🔴 Contract Resolution**: Resolved contracts are cached in-memory per session. Cache misses trigger fresh IBKR API call. No stale cache persists across restarts.

---

## Fast Start (Copy & Paste)

### Setup (5 minutes)

```bash
# 1. Clone and enter repo
git clone <repo-url>
cd mm-ibkr-gateway

# 2. Copy environment
cp .env.example .env

# 3. Install dependencies
poetry install

# 4. Verify IBKR Gateway is running on port 4002
# (Ensure TWS or Gateway is running in paper mode)

# 5. Run healthcheck
poetry run ibkr-gateway healthcheck
```

### Run Demo (Paper Mode)

```bash
# Interactive demo with market data + account status
poetry run ibkr-gateway demo
```

**Expected output**:

- Connection status ✓
- AAPL quote (bid/ask/last) ✓
- SPY historical bars (5-day) ✓
- Account summary (buying power, net liquidation) ✓
- Current positions (if any) ✓

### Start REST API

```bash
# Launch FastAPI server on port 8000
poetry run ibkr-gateway start-api

# In another terminal:
curl http://localhost:8000/health
```

API documentation at: <http://localhost:8000/docs>

### Run Tests

```bash
# Unit + integration tests (no live trading)
poetry run pytest tests/ -v

# Skip slow/integration tests
poetry run pytest tests/ -v -m "not integration"

# Single test file
poetry run pytest tests/test_config.py -v
```

---

## Safety & Configuration

### ⚠️ Configuration Files

- **`.env`**: Contains all runtime configuration. **NEVER commit `.env` to git.**
- **`.env.example`**: Safe template; commit this instead.
- **Key settings**:
  - `TRADING_MODE`: `paper` (default, safe) or `live` (dangerous)
  - `ORDERS_ENABLED`: `false` (default) or `true`
  - `LIVE_TRADING_OVERRIDE_FILE`: Path to file that must exist for live trading (e.g., `~/ibkr_live_confirmed.txt`)

### Paper vs. Live Mode

| Feature | Paper Mode | Live Mode |
| --------- | ----------- | ----------- |
| Orders placed | Simulated (return status `SIMULATED`) | Real (status `ACCEPTED`, `FILLED`, etc.) |
| Account impact | No real money | **REAL MONEY** |
| Default | ✓ Yes | ❌ Requires explicit config |

### How to Enable Live Trading (⚠️ EXTREMELY DANGEROUS)

Only do this after extensive paper mode testing:

```bash
# 1. Create override file
touch ~/ibkr_live_confirmed.txt

# 2. Edit .env
echo "TRADING_MODE=live" >> .env
echo "ORDERS_ENABLED=true" >> .env
echo "LIVE_TRADING_OVERRIDE_FILE=~/ibkr_live_confirmed.txt" >> .env

# 3. Verify config
poetry run ibkr-gateway healthcheck

# 4. Test with TINY orders, limit orders FAR from market price
poetry run ibkr-gateway --live demo
```

**After enabling live trading, monitor your IBKR account portal immediately.**

### No-Side-Effects Dry-Run

All read operations (quotes, account status, historical bars) are safe:

```bash
# Safe in paper or live mode:
poetry run ibkr-gateway --paper demo
curl http://localhost:8000/health
curl http://localhost:8000/api/account/summary
curl "http://localhost:8000/api/market/quote?symbol=AAPL&securityType=STK"
```

Order **preview** is also safe (no placement):

```bash
curl -X POST http://localhost:8000/api/orders/preview \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "AAPL",
    "securityType": "STK",
    "action": "BUY",
    "quantity": 1,
    "orderType": "MKT"
  }'
```

Only `/api/orders/place` and `/api/orders/cancel` have side effects (and only if `ORDERS_ENABLED=true` + `TRADING_MODE=live` + override file).

---

## Context Maintenance Rule

### The Golden Rule

**`.context/` is AUTHORITATIVE. Tasks are incomplete if code changes without updating context.**

Any change that affects:

- Behavior, workflows, or execution flow
- Data schemas, persisted outputs, or database structure
- Invariants, assumptions, risk constraints, or safety gates
- External integrations, dependencies, or APIs
- Runtime configuration or operational procedures

**REQUIRES updating the relevant `.context/` files.**

### How to Maintain Context

1. **Before coding**: Read [02_ARCHITECTURE.md](.context/02_ARCHITECTURE.md) and [03_DATA_CONTRACTS.md](.context/03_DATA_CONTRACTS.md) to understand boundaries.
2. **While coding**: If you add a new module, endpoint, or schema, note where it belongs.
3. **After coding**: Update the relevant `.context/` file(s):
   - Added new API endpoint? Update [02_ARCHITECTURE.md](.context/02_ARCHITECTURE.md)
   - Changed order lifecycle? Update [03_DATA_CONTRACTS.md](.context/03_DATA_CONTRACTS.md)
   - New design decision? Add entry to [09_DECISIONS.md](.context/09_DECISIONS.md)
   - New safety rule? Update [04_RISK_GUARDRAILS.md](.context/04_RISK_GUARDRAILS.md)

4. **Code review**: Check that `.context/` changes match code changes. PR should not be approved if context is stale.

### Consequences of Stale Context

- **New agents onboard incorrectly** and waste time reverse-engineering
- **Invariants are violated** silently (e.g., adding floats instead of Decimal)
- **Risk constraints are bypassed** (e.g., removing safety checks)
- **Data contracts break** and cause corruption (e.g., schema mismatches)

**Prevent this: treat `.context/` as living documentation with the same rigor as tests.**

---

## Critical Context Files (Read These First)

1. **[02_ARCHITECTURE.md](.context/02_ARCHITECTURE.md)**: System design, entry points, data flow, module boundaries.
2. **[03_DATA_CONTRACTS.md](.context/03_DATA_CONTRACTS.md)**: Database schemas, API models, example rows, backward-compatibility rules.
3. **[04_RISK_GUARDRAILS.md](.context/04_RISK_GUARDRAILS.md)**: Hard safety constraints, forbidden patterns, live-mode gates.

---

## Key Directories

```text
mm-ibkr-gateway/
├── .context/              ← YOU ARE HERE (agent knowledge base)
├── ibkr_core/             ← Core domain logic (client, orders, account, market data)
├── api/                   ← FastAPI REST server (routes, models, errors)
├── mcp_server/            ← Claude MCP tool server (8 tools for Claude)
├── tests/                 ← Pytest suite (635 tests, all pass)
├── docs/                  ← Architecture notes, schemas, checklists
├── data/                  ← Runtime data (audit.db, logs, etc.)
├── pyproject.toml         ← Dependencies, pytest config, tool settings
└── README.md              ← User-facing documentation
```

---

## Entrypoints

- **CLI**: `poetry run ibkr-gateway [healthcheck|demo|start-api]`
- **API**: `uvicorn api.server:app --host 0.0.0.0 --port 8000`
- **MCP**: `python -m mcp_server.main`
- **Direct Python**: `from ibkr_core.client import create_client`

---

## Questions?

1. **How does the system know when it's safe to trade?**
   → See [04_RISK_GUARDRAILS.md](.context/04_RISK_GUARDRAILS.md) "Safety Gates".

2. **What data does the system persist?**
   → See [03_DATA_CONTRACTS.md](.context/03_DATA_CONTRACTS.md) "Persisted Schemas".

3. **How do I add a new endpoint?**
   → See [07_STYLE_AND_PATTERNS.md](.context/07_STYLE_AND_PATTERNS.md) "API Endpoint Pattern".

4. **How are tests organized?**
   → See [06_TESTING.md](.context/06_TESTING.md).

5. **What external APIs does this talk to?**
   → See [08_DEPENDENCIES.md](.context/08_DEPENDENCIES.md).

---

## Summary

- **Safe by default**: Paper mode, orders disabled, dual-gate for live
- **Three interfaces**: Python, REST, MCP
- **Fully tested**: 635 tests pass
- **Audit-ready**: Every order logged with correlation ID
- **Agent-friendly**: Read `.context/` docs first, then explore code

**You're ready. Start with the demo:**

```bash
poetry install
poetry run ibkr-gateway demo
```
