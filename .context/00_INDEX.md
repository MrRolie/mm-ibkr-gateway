# 00_INDEX.md: IBKR Gateway System Map

## Mission

Production-grade Interactive Brokers integration providing market data, account management, and order execution via Python API, REST API, and Claude MCP server. **Safe by default** (paper trading + orders disabled) with 5-layer safety gates for live trading.

---

## Tech Stack

| Component | Purpose | Version/Details |
| ----------- | --------- | ----------------- |
| **ib-insync** | IBKR SDK wrapper | ≥0.9.17 |
| **FastAPI** | REST API framework | ≥0.104.0 |
| **Pydantic** | Request/response validation | ≥2.0 |
| **SQLite** | Audit trail & order history | Embedded (audit.db) |
| **Python** | Runtime | ≥3.10 |
| **Loguru** | Structured logging | ≥0.7 |
| **MCP** | Claude integration | ≥1.2 |
| **Typer** | CLI framework | ≥0.9.0 |

---

## Repo Map

```text
mm-ibkr-gateway/
│
├── .context/                       ← YOU ARE HERE (Agent Knowledge Base)
│   ├── 00_INDEX.md                 ← System Map (this file)
│   ├── 01_RULES.md                 ← Guardrails & Invariants
│   ├── 02_OPS.md                   ← Setup, Run, Side Effects
│   └── 03_DECISIONS.md             ← Architectural Memory
│
├── ibkr_core/                      ← Core Domain Logic (Business Logic)
│   ├── client.py                   ← Main facade (connect/disconnect)
│   ├── contracts.py                ← Contract resolution & in-memory cache
│   ├── market_data.py              ← Quotes & historical bars
│   ├── account.py                  ← Account summary, positions, P&L
│   ├── orders.py                   ← Order placement, cancellation, status (1549 lines)
│   ├── persistence.py              ← SQLite audit trail & correlation IDs (846 lines)
│   ├── config.py                   ← Env loading & 5 safety gates (238 lines)
│   ├── simulation.py               ← Paper trading simulator
│   ├── cli.py                      ← CLI commands (healthcheck, demo, start-api)
│   ├── demo.py                     ← Interactive 5-minute walkthrough
│   └── [others]                    ← logging_config, metrics, healthcheck, __main__
│
├── api/                            ← REST API Layer (HTTP Interface)
│   ├── server.py                   ← FastAPI app, routes, lifespan (717 lines)
│   ├── models.py                   ← Pydantic request/response schemas
│   ├── errors.py                   ← Error codes & exception mapping
│   ├── auth.py                     ← API key validation
│   ├── middleware.py               ← Correlation ID injection, logging
│   ├── dependencies.py             ← FastAPI dependency injection
│   └── admin.py                    ← Admin endpoints
│
├── mcp_server/                     ← Claude MCP Integration (8 Tools)
│   ├── main.py                     ← MCP server entry point (577 lines)
│   ├── tools/                      ← Tool implementations
│   │   ├── market_tools.py         ← get_quote, get_bars
│   │   ├── account_tools.py        ← account_summary, positions
│   │   └── order_tools.py          ← place_order, cancel_order, etc.
│   └── schemas.py                  ← MCP message schemas
│
├── tests/                          ← Pytest Suite (635 tests, all passing)
│   ├── unit/                       ← No external deps (contracts, config, simulation)
│   ├── integration/                ← Hits IBKR Gateway (marked @pytest.mark.integration)
│   ├── conftest.py                 ← Fixtures, mocks, paper mode override
│   └── [fixtures/]                 ← Mock data
│
├── docs/                           ← User & Architecture Documentation
│   ├── ARCHITECTURE.md             ← Design notes
│   ├── API_REFERENCE.md            ← API docs
│   ├── IBKR_2FA_PLAN.md            ← Two-factor setup
│   └── [others]                    ← Scheduler notes, archived docs
│
├── data/                           ← Runtime Data (Created at startup)
│   └── audit.db                    ← SQLite: orders, fills, audit trail
│
├── deploy/                         ← Deployment Scripts
│   └── windows/                    ← Windows service setup (NSSM)
│
├── scripts/                        ← Utility Scripts
│
├── pyproject.toml                  ← Poetry config, dependencies, scripts
├── .env.example                    ← Environment template (NEVER commit .env)
├── docker-compose.yml              ← Docker setup for IBKR Gateway + app
├── Dockerfile                      ← Container image
├── README.md                       ← User-facing docs
└── CHANGELOG.md                    ← Release notes
```

---

## Core Entities

| Entity | Purpose | Key Fields | Invariants |
| ----------- | --------- | ----------- | ----------- |
| **SymbolSpec** | User-facing instrument specification | symbol, securityType, exchange, currency, expiry, strike, right | One SymbolSpec → exactly one resolved Contract (cached by symbol+type+exchange+currency) |
| **Contract** | IBKR's instrument representation | conId, symbol, securityType, exchange, currency, localSymbol, tradingClass | Immutable within session; cache invalidates on restart |
| **Quote** | Market snapshot | bid, ask, last, bidSize, askSize, volume, timestamp (UTC), source | Timestamp is ISO 8601; bid ≤ last ≤ ask (or missing); source in [REALTIME, DELAYED, FROZEN] |
| **Bar** | OHLCV historical candle | time, open, high, low, close, volume, barSize | close ≥ low; close ≤ high; time is ISO 8601 UTC |
| **OrderSpec** | Request to place/preview an order | symbol, securityType, action (BUY/SELL/BUYTOCOVER/SELLSHORT), quantity, orderType, limit, stop, timeInForce | action ∈ [BUY, SELL, BUYTOCOVER, SELLSHORT]; quantity > 0; timeInForce ∈ [DAY, GTC, IOC, FOK, OPG]; MOC orders use orderType=MOC with TIF=DAY |
| **OrderResult** | Order placement response | orderId (UUID), status (SIMULATED/ACCEPTED/FILLED/REJECTED), fills, avgPrice, correlation_id | orderId deterministic (same input → same orderId); status depends on paper/live mode; every action logged to audit.db |
| **AccountSummary** | Account state snapshot | netLiquidation, buyingPower, positions, cash, unrealizedPnL, realizedPnL | All money values are Decimal; unrealizedPnL = sum(position.unrealizedPnL) |
| **Config** | Runtime configuration | trading_mode (paper/live), orders_enabled (bool), live_trading_override_file (path), ibkr_host, ibkr_port | Validated at startup AND runtime; trading_mode default=paper; orders_enabled default=false |

---

## Data Flow Diagram

```text
┌─────────────────────────────────────────────────────────────────┐
│                    QUOTE REQUEST FLOW                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  API Client (REST/Python/MCP)                                   │
│         │                                                       │
│         └─→ ibkr_core.market_data.get_quote(symbol)             │
│                    │                                            │
│                    ├─→ ibkr_core.contracts.resolve_contract()   │
│                    │   (check cache, call IBKR if miss)         │
│                    │                                            │
│                    └─→ ib_insync.IB.reqMktData()                │
│                        (async, dedicated thread)                │
│                            │                                    │
│                            └─→ IBKR Gateway (port 4002)         │
│                                │                                │
│                                └─→ Quote snapshot               │
│                                    (bid/ask/last/timestamp)     │
│                                                                 │
│                    [Log correlation ID + request/response]      │
│                                                                 │
│         ←─ Quote object (Decimal precision, UTC timestamp)      │
│                                                                 │
│  API Client (response)                                          │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘


┌──────────────────────────────────────────────────────────────────┐
│                  ORDER PLACEMENT FLOW (5 Gates)                  │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  API Client: POST /api/orders/place {symbol, action, qty, ...}   │
│         │                                                        │
│         └─→ Gate 1: Config validated (TRADING_MODE ∈ paper|live) │
│         │  (Startup only, but re-checked)                        │
│         │                                                        │
│         └─→ Gate 2: Override file exists (if live + enabled)     │
│         │  (Startup only, but re-checked)                        │
│         │                                                        │
│         └─→ Gate 3: Runtime check                                │
│         │  if TRADING_MODE=paper → SIMULATE (status=SIMULATED)   │
│         │  if ORDERS_ENABLED=false → SIMULATE                    │
│         │  if override file missing → SIMULATE                   │
│         │  else → REAL ORDER                                     │
│         │                                                        │
│         └─→ Gate 4: Order spec validation                        │
│         │  (qty > 0, orderType in [MKT, LMT], etc.)              │
│         │  (Check account balance, margin, etc.)                 │
│         │                                                        │
│         └─→ generate deterministic orderId (hash(input))         │
│         │  check if orderId already in audit.db                  │
│         │  if exists → return previous result (idempotent)       │
│         │                                                        │
│         └─→ Gate 5: Log order action to audit.db                 │
│         │  INSERT (correlation_id, orderId, action='place',      │
│         │          timestamp, config_snapshot, request_snapshot) │
│         │  constraint: UNIQUE(orderId, action, timestamp)        │
│         │  (prevents duplicate logging)                          │
│         │                                                        │
│         └─→ REAL ORDER (if all gates passed):                    │
│         │  ib_insync.IB.placeOrder(contract, order)              │
│         │  (dedicated thread, async)                             │
│         │                                                        │
│         │  IBKR Gateway → IBKR Live/Paper                        │
│         │                                                        │
│         └─→ Return OrderResult                                   │
│         │  {orderId, status, fills, avgPrice, correlation_id}    │
│         │                                                        │
│         └─→ Log fill events to audit.db (as they arrive)         │
│                                                                  │
│  API Response ← OrderResult (with correlation_id)                │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

---

## Entry Points

| Interface | Command | Purpose |
| ----------- | --------- | --------- |
| **CLI** | `poetry run ibkr-gateway healthcheck` | Verify connection to IBKR Gateway |
| **CLI** | `poetry run ibkr-gateway demo` | Interactive 5-min walkthrough (quotes, account, positions) |
| **CLI** | `poetry run ibkr-gateway start-api` | Launch REST API on port 8000 |
| **Admin UI** | `http://localhost:8000/ui` | Operator dashboard (includes Gateway verification via account summary) |
| **Admin API** | `GET http://localhost:8000/admin/gateway/verify?mode=direct` | Verify Gateway access via direct account summary (random high client_id) |
| **REST API** | `POST http://localhost:8000/api/orders/place` | Place order (subject to 5 gates) |
| **REST API** | `GET http://localhost:8000/api/market/quote` | Get quote |
| **MCP** | `python -m mcp_server.main` | Claude MCP server (8 tools) |
| **Python** | `from ibkr_core.client import create_client` | Direct API |

---

## Safety Gates (Visual)

```text
┌───────────────────────────────────────────────────────────────┐
│              LIVE TRADING SAFETY GATES (5 Layers)             │
├───────────────────────────────────────────────────────────────┤
│                                                               │
│ Gate 1 (Startup):   TRADING_MODE ∈ {paper, live}              │
│                     ✓ Must be valid                           │
│                     ✗ Ambiguous config → REJECT               │
│                                                               │
│ Gate 2 (Startup):   Override file exists (if live + enabled)  │
│                     ✓ File created manually on disk           │
│                     ✗ Typo in path → REJECT                   │
│                     ✗ File missing → REJECT                   │
│                                                               │
│ Gate 3 (Runtime):   Check TRADING_MODE & ORDERS_ENABLED       │
│                     ✓ paper mode → SIMULATE                   │
│                     ✓ orders disabled → SIMULATE              │
│                     ✓ override file missing → SIMULATE        │
│                     ✓ all gates passed → REAL                 │
│                                                               │
│ Gate 4 (Runtime):   Validate order spec & account state       │
│                     ✓ qty > 0, orderType valid, margin OK     │
│                     ✗ Invalid spec → REJECT                   │
│                     ✗ Insufficient buying power → REJECT      │
│                                                               │
│ Gate 5 (Runtime):   Deterministic orderId + idempotency       │
│                     ✓ Same input → same orderId               │
│                     ✓ Already placed → return previous result │
│                     ✗ Prevents double-placing                 │
│                                                               │
│ ──────────────────────────────────────────────────────────────│
│ RESULT: IMPOSSIBLE to accidentally place live orders          │
│ ──────────────────────────────────────────────────────────────│
│                                                               │
│ DEFAULT STATE (Safe):   paper + orders_disabled               │
│ AUDIT TRAIL:            Every action logged immutably         │
│ ROLLBACK:               Never; append-only log                │
│                                                               │
└───────────────────────────────────────────────────────────────┘
```

---

## Persistence & Audit

| Entity | Storage | Schema | Access |
| -------- | --------- | -------- | -------- |
| **Orders** | SQLite (audit.db) | orders: (orderId, symbol, action, status, fills, correlation_id, timestamp, config_snapshot) | Read-only (appends only) |
| **Audit Trail** | SQLite (audit.db) | audit: (correlation_id, orderId, action, timestamp, request_snapshot) | Read-only (appends only) |
| **Contract Cache** | In-Memory | Dict[symbol+type+exchange+currency] → Contract | Session-scoped; invalidates on restart |
| **Configuration** | Environment (.env) | TRADING_MODE, ORDERS_ENABLED, LIVE_TRADING_OVERRIDE_FILE, etc. | Validated at startup & runtime |

---

## Glossary (Key Terms)

| Term | Definition |
| ------ | -------------- |
| **Contract** | IBKR internal representation of a security, uniquely identified by conId (contract ID) |
| **SymbolSpec** | User-facing request to describe an instrument (symbol, security type, exchange, currency) |
| **Quote** | Market snapshot at a point in time (bid, ask, last, volume, timestamp) |
| **Bar** | Historical OHLCV candlestick data (time, open, high, low, close, volume) |
| **OrderSpec** | Request to place/preview an order (symbol, action, qty, orderType, limit, stop) |
| **Fill** | Execution of an order (can be partial or full, with fill price and timestamp) |
| **Position** | Current open lot of a security (positive=long, negative=short) |
| **Margin** | Borrowing buying power from broker (2x leverage on margin account) |
| **P&L** | Profit/Loss (Realized=closed positions, Unrealized=open positions at current mark) |
| **Correlation ID** | UUID tracking end-to-end request flow (API request → ibkr_core → IBKR → audit.db) |
| **Security Types** | STK (stock), ETF, FUT (futures), OPT (options), IND (index), CASH, CFD, BOND, FUND, CRYPTO |
| **Paper Mode** | Simulated trading (no real money) |
| **Live Mode** | Real money trading (requires explicit configuration + override file) |
| **Idempotency** | Same input always produces same orderId (prevents duplicate orders on retry) |

---

## Related Context Files

| File | Purpose | Read When |
| ------ | --------- | ----------- |
| [01_RULES.md](.context/01_RULES.md) | Hard invariants, forbidden patterns, data integrity rules | Planning changes to order logic or schemas |
| [02_OPS.md](.context/02_OPS.md) | Setup, build, run, test commands; side effects list | Setting up environment or understanding system boundaries |
| [03_DECISIONS.md](.context/03_DECISIONS.md) | Architectural decisions, trade-offs, memory | Understanding why a design choice was made |
| [01_DOMAIN.md](.context/01_DOMAIN.md) | Terminology, units, domain concepts | Understanding order types, security types, account types |
| [02_ARCHITECTURE.md](.context/02_ARCHITECTURE.md) | Module boundaries, data flow, patterns | Adding new features or debugging |
| [03_DATA_CONTRACTS.md](.context/03_DATA_CONTRACTS.md) | API schemas, database schemas, backward compatibility | Modifying APIs or database |
| [04_RISK_GUARDRAILS.md](.context/04_RISK_GUARDRAILS.md) | Detailed safety rules, forbidden patterns, order placement gates | Touching order/config/trading logic |
| [05_RUNBOOK.md](.context/05_RUNBOOK.md) | Operational runbook, troubleshooting, emergency procedures | Debugging production issues |
| [06_TESTING.md](.context/06_TESTING.md) | Test strategy, fixtures, mocking, integration tests | Writing or modifying tests |
| [07_STYLE_AND_PATTERNS.md](.context/07_STYLE_AND_PATTERNS.md) | Code style, error handling, logging patterns | Writing new code |
| [08_DEPENDENCIES.md](.context/08_DEPENDENCIES.md) | External integrations (IBKR, SQLite, files) | Changing integrations or understanding surface area |
| [09_DECISIONS.md](.context/09_DECISIONS.md) | ADRs, memory of why things are the way they are | Considering changing a design |

---

## Definition of Done (Context Maintenance)

**This system is safe because `.context/` is kept current. If `.context/` gets out of sync with code, safety breaks.**

Any PR adding features, changing schemas, or modifying safety logic **MUST**:

1. ✅ Update relevant `.context/` file(s)
2. ✅ Add entry to [03_DECISIONS.md](.context/03_DECISIONS.md) if non-obvious
3. ✅ Update [01_RULES.md](.context/01_RULES.md) if new invariants added
4. ✅ Test pass (635 tests)
5. ✅ Code review checks both `.context/` AND code changes

**If context is stale, PR is INCOMPLETE.**

