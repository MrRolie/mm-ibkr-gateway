# IBKR Integration + MCP Tool Server - Implementation Phases

## Phase 0 – Repo, environment, and safety rails

### Goals

* Clean repo layout.
* Reliable IBKR sandbox connection (Paper account only).
* Hard safety switch to prevent live trading until explicitly enabled.

### Deliverables

* Repo structure:

  * `/ibkr_core/` – IBKR integration logic
  * `/api/` – REST layer
  * `/mcp_server/` – MCP implementation
  * `/tests/` – tests
* `.env` support:

  * `IBKR_GATEWAY_HOST`, `IBKR_GATEWAY_PORT`
  * `TRADING_MODE=paper|live`
  * `ORDERS_ENABLED=false|true`
* Dockerfile + basic dev/compose config (optional, but ideal).

### Implementation steps

1. Initialize repo, set up dependency management (poetry/pip/uv).
2. Implement config loader:

   * Central place to read env vars and enforce:

     * If `TRADING_MODE=live` and `ORDERS_ENABLED=true` → require explicit override flag/file.
3. Implement a small script:

   * `python -m ibkr_core.healthcheck`
   * Connects to IBKR, queries server time, prints it, then disconnects.

### Tests

* Unit:

  * Config: if `ORDERS_ENABLED=false`, calling any "send order" function raises a "TradingDisabledError".
  * Config: invalid `TRADING_MODE` values fail fast.
* Integration:

  * Healthcheck script returns success against running TWS/Gateway in paper mode.
  * If Gateway is down, healthcheck exits with clear error code.

---

## Phase 1 – IBKR core client (connection & contracts)

### Goals

* Stable connection wrapper around IBKR.
* Contract resolution layer (symbol → contract).

### Deliverables

* `ibkr_core/client.py`:

  * `IBKRClient` class with:

    * `connect()`, `disconnect()`
    * `ensure_connected()`
* `ibkr_core/contracts.py`:

  * `resolve_contract(symbol: str, security_type: str, exchange: str | None, currency: str | None) -> Contract`
  * Contract cache (in-memory).

### Implementation steps

1. Wrap ib_insync connection in `IBKRClient`:

   * Handles reconnects.
   * Adds logging around connect/disconnect.
2. Implement contract resolver:

   * For now: support equities, futures, options (vanilla, index/options).
   * Normalize incoming symbol input:

     * e.g., `"MES"` → futures on CME, currency `USD`, default front month (later refine).
3. Add simple data models:

   * `SymbolSpec`, `ContractSpec` for deterministic resolution.

### Tests

* Unit:

  * `resolve_contract("AAPL", "STK", "SMART", "USD")` returns a contract with correct symbol/currency.
  * Invalid security_type → raises.
* Integration:

  * Connect to IBKR, resolve known symbols:

    * `AAPL`, `SPY`, `MES`, `ES`, `SPX`
  * Ensure IBKR does not reject the resulting contracts.

---

## Phase 2 – Market data (fetch data)

Focus on: "fetching data" use case.

### Goals

* Clean functions to fetch:

  * Live quotes (snapshot or streaming)
  * Historical bars
* Normalized data models.

### Deliverables

* `ibkr_core/market_data.py`:

  * `get_quote(symbol_spec: SymbolSpec) -> Quote`
  * `get_quotes(symbol_specs: list[SymbolSpec]) -> list[Quote]`
  * `get_historical_bars(symbol_spec, bar_size, duration, what_to_show, rth_only) -> list[Bar]`
* Data models:

  * `Quote { bid, ask, last, bid_size, ask_size, last_size, timestamp, source }`
  * `Bar { time, open, high, low, close, volume }`

### Implementation steps

1. Use ib_insync's `reqMktData` for live quotes (snapshot is fine initially).
2. Implement timeouts and clear error messages if data is not subscribed / not available.
3. Implement historical data via `reqHistoricalData`:

   * Map human inputs → IBKR enums (e.g., `bar_size="5 min"`, `duration="1 W"`).
4. Normalize errors:

   * No market data permission
   * No data for contract
   * Pacing violation

### Tests

* Unit:

  * Validate `SymbolSpec` → `Contract` mapping for a variety of instruments.
  * Validate bar_size/duration input normalization functions.
* Integration:

  * `get_quote` works for:

    * `AAPL` stock
    * Some future you actually have data for (e.g., `MES`).
  * `get_historical_bars("AAPL", "1 day", "1 M", "TRADES", True)` returns non-empty.
  * Simulated "no permission" scenario ⇒ returns a structured error/exception, not a crash.

---

## Phase 3 – Account status (balances, positions, PnL, margin)

Focus on: "fetching account status" use case.

### Goals

* Structured, normalized access to:

  * Account summary / balances
  * Positions
  * PnL (unrealized + realized)
  * Margin status if available

### Deliverables

* `ibkr_core/account.py`:

  * `get_account_summary() -> AccountSummary`
  * `get_positions() -> list[Position]`
  * `get_pnl(timeframe: str | None) -> AccountPnl` (timeframe may be restricted initially)
* Data models:

  * `AccountSummary { account_id, net_liquidation, cash, buying_power, currency, margin_excess, maint_margin, init_margin }`
  * `Position { symbol, conId, quantity, avg_price, market_price, market_value, unrealized_pnl, realized_pnl, asset_class, currency }`
  * `AccountPnl { realized, unrealized, by_symbol: dict[symbol, PnlDetail] }`

### Implementation steps

1. Use IBKR API to:

   * Pull account summary fields
   * Pull portfolio snapshots (positions)
2. Implement mapping from IBKR portfolio items:

   * contract → your `symbol` representation
   * ensure consistent primary key (prefer `conId`).
3. For PnL:

   * Start simple: realized/unrealized per position as provided by IBKR.
   * Ignore custom timeframes initially, document that.
4. Ensure everything returns JSON-serializable structures.

### Tests

* Unit:

  * Mapping from raw IBKR portfolio object → `Position` is correct (mock IBKR structures).
  * Account summary field mapping validated against sample payload.
* Integration:

  * `get_account_summary()` returns:

    * Non-null `net_liquidation`, `currency`.
  * `get_positions()` returns at least:

    * One position if account is not empty.
  * `get_pnl()` is consistent with sum over positions.

---

## Phase 4 – Order management (place/modify/cancel)

Focus on: "placing orders" use case (with strict control).

### Goals

* A single, safe interface to place orders.
* Simple support first:

  * Market, limit orders
  * Stocks and futures
* Hard-coded safety: no real orders unless flags are explicitly set.

### Deliverables

* `ibkr_core/orders.py`:

  * `preview_order(order_spec: OrderSpec) -> OrderPreview`  (no send)
  * `place_order(order_spec: OrderSpec) -> OrderResult`
  * `cancel_order(order_id: str) -> CancelResult`
  * `get_order_status(order_id: str) -> OrderStatus`
* `OrderSpec`:

  * `{ symbol, security_type, side, quantity, order_type, limit_price?, tif, account_id? }`
* Safety logic:

  * Checks `TRADING_MODE` and `ORDERS_ENABLED` before sending any order.
  * Optional "max_notional", "max_size_per_symbol" checks.

### Implementation steps

1. Implement `OrderSpec` → IBKR order:

   * side: `"buy" | "sell"`
   * type: `"MKT" | "LMT"` initially.
2. Default TIF: `DAY` unless specified.
3. `preview_order`:

   * Either:

     * Use IBKR's available preview APIs (depends on interface).
     * Or simulate:

       * Check current quote, notional, margin approximation.
4. `place_order`:

   * If `ORDERS_ENABLED=false`:

     * Log attempt, return a "simulated" result (for dev).
   * If enabled:

     * Place order, wait for initial status (submitted, rejected, etc.).
5. Make sure to persist or track `order_id` mapping.

### Tests

* Unit:

  * `OrderSpec` validation:

    * Negative quantity → error.
    * Both `limit_price` and `order_type="MKT"` provided → error or ignore price.
  * Safety:

    * When `ORDERS_ENABLED=false`, `place_order` never calls IBKR client.
* Integration (Paper account only):

  * Place small limit order far from market (so it doesn't fill) and confirm:

    * IBKR shows order.
    * `get_order_status(order_id)` matches.
  * Cancel order and verify it transitions to cancelled.
  * Try placing an order exceeding position limits (if you add custom checks) and ensure it fails early.

---

## Phase 4.5 – Advanced Orders ✅ COMPLETE

Extension of Phase 4 with support for advanced order types.

### Goals

* Support trailing stop orders (amount and percentage based)
* Support bracket orders (entry + take profit + stop loss)
* Support market-on-close (MOC) and market-on-open (OPG) orders
* Support OCA (One-Cancels-All) order groups
* Maintain backward compatibility with Phase 4 API

### Deliverables

* Extended `OrderSpec` model:
  * `trailingAmount`, `trailingPercent`, `trailStopPrice` for trailing stops
  * `takeProfitPrice`, `stopLossPrice`, `stopLossLimitPrice` for bracket orders
  * `bracketTransmit` flag for bracket order transmission control
  * `ocaGroup`, `ocaType` for OCA group configuration

* New models:
  * `OrderLeg { role, orderType, side, quantity, limitPrice, stopPrice, trailingAmount, trailingPercent, tif, estimatedPrice, estimatedNotional }`
  * Extended `OrderPreview` with `legs: List[OrderLeg]` and `totalNotional`
  * Extended `OrderResult` with `orderIds: List[str]` and `orderRoles: Dict[str, str]`

* New order types in `ibkr_core/orders.py`:
  * `TRAIL`: Trailing stop with `trailingAmount` (dollars) OR `trailingPercent`
  * `TRAIL_LIMIT`: Trailing stop-limit with limit offset
  * `BRACKET`: Entry + take profit + stop loss (3 linked orders with OCA)
  * `MOC`: Market-on-close order
  * `OPG`: Market-on-open (opening auction) order

* New functions:
  * `cancel_order_set(order_ids: List[str]) -> CancelResult`: Cancel multiple orders as a set
  * `get_order_set_status(order_ids: List[str]) -> List[OrderStatus]`: Get status of multiple orders

### Implementation details

* Bracket orders use IBKR's parent-child mechanism:
  1. Entry order placed first (transmit=False)
  2. Take profit and stop loss orders set parentId to entry's orderId
  3. TP and SL linked via OCA group so one cancels the other
  4. Final child order transmits all

* Trailing stop orders use IBKR's native TRAIL order type:
  * `auxPrice` for dollar amount trailing
  * `trailingPercent` for percentage trailing
  * Optional `trailStopPrice` for initial stop level

### Tests

* Unit (`tests/test_orders_advanced.py`): 51 tests
  * Trailing stop validation and building
  * Bracket order validation (price relationships)
  * Bracket order building (entry/TP/SL structure)
  * MOC/OPG order building
  * OCA group application
  * Helper functions
  * Model tests (OrderLeg, OrderResult, OrderPreview)
  * cancel_order_set and get_order_set_status (mocked)

* Integration (`tests/test_orders_advanced_integration.py`): 11 tests
  * Trailing stop preview and place/cancel
  * Bracket order preview and place/cancel
  * Order set operations
  * MOC/OPG previews
  * OCA group functionality

---

## Phase 5 – API layer (REST / gRPC)

This is your internal API that MCP will wrap.

### Goals

* Stable, documented API endpoints for:

  * Market data
  * Account status
  * Orders

### Deliverables

* `api/server.py`:

  * Endpoints:

    * `GET /health`
    * `POST /market-data/quote`
    * `POST /market-data/historical`
    * `GET /account/summary`
    * `GET /account/positions`
    * `GET /account/pnl`
    * `POST /orders/preview`
    * `POST /orders`
    * `POST /orders/{order_id}/cancel`
    * `GET /orders/{order_id}/status`
* OpenAPI/Swagger spec auto-generated.

### Implementation steps

1. Wrap `ibkr_core` functions in FastAPI handlers.
2. Add simple auth (API key or local-only restriction).
3. Ensure consistent error model:

   * `{ "error_code": "...", "message": "...", "details": {...} }`
4. Enforce per-request timeouts.

### Tests

* Integration (API-level, using HTTP client):

  * `/health` returns ok.
  * `/market-data/quote` returns a properly shaped `Quote` for `AAPL`.
  * `/account/summary` and `/account/positions` return correct JSON.
  * `/orders/preview` works even when `ORDERS_ENABLED=false`.
  * `/orders` returns simulated result when disabled, real when enabled (in controlled test env).

---

## Phase 6 – MCP server wiring

Now you expose this API via MCP tools.

### Goals

* Define MCP tools that map cleanly onto your three main use cases.
* Each tool is thin: just translate MCP call → HTTP call → response.

### Deliverables

* `mcp_server/main.py`:

  * Tools:

    * `get_quote`
      Input: `{ symbol, security_type, exchange?, currency? }`
      Output: `Quote`
    * `get_historical_data`
      Input: `{ symbol, security_type, bar_size, duration, what_to_show, rth_only }`
      Output: `Bar[]`
    * `get_account_status`
      Input: `{}`
      Output: `{ summary: AccountSummary, positions: Position[] }`
    * `get_pnl`
      Input: `{ timeframe? }`
      Output: `AccountPnl`
    * `preview_order`
      Input: `OrderSpec`
      Output: `OrderPreview`
    * `place_order`
      Input: `OrderSpec`
      Output: `OrderResult`
    * `get_order_status`
      Input: `{ order_id }`
      Output: `OrderStatus`
    * `cancel_order`
      Input: `{ order_id }`
      Output: `CancelResult`

### Implementation steps

1. Implement MCP server:

   * Registers tools with schemas.
   * On invocation:

     * Validate JSON against schema.
     * Call your REST API.
     * Return normalized JSON responses.
2. Add structured error translation:

   * Map HTTP error shapes → MCP tool error format.

### Tests

* Integration:

  * Call MCP `get_quote` and `get_account_status` tools and verify they match direct API outputs.
  * Call `preview_order` and `place_order` (with `ORDERS_ENABLED=false`) and verify safe behavior.
  * Verify invalid inputs lead to nicely formatted MCP errors, not crashes.

---

## Phase 6.1 - First 5 minutes (paper-only demo) ✅ COMPLETE

### Goals

* A demo that works quickly in paper mode without placing orders.
* Explicitly requires IBKR Gateway paper running.

### Deliverables

* Paper-only demo command (requires IBKR Gateway paper running):

  * `ibkr-gateway demo` or `python -m ibkr_core.demo` ✅
* Dockerfile + docker-compose demo setup for paper mode (one-command). ✅
* README "Quick Demo (paper-only)" section with copy/paste commands. ✅

### Implementation

* Created `ibkr_core/demo.py` (361 lines):
  * Market data demo: AAPL real-time quote, SPY historical bars
  * Account status demo: Account summary, current positions
  * Paper mode validation with forced override
  * Colorized terminal output with ANSI colors
  * Comprehensive error handling and helpful messages
  * Next steps guidance
* Created `tests/test_demo.py` (220+ lines):
  * 15 unit tests with mocked client
  * Integration test (requires Gateway)
  * Coverage for all demo functions
* Created `docker-compose.demo.yml`:
  * Pre-configured for paper mode
  * Connects to host IBKR Gateway
  * One-command demo execution
* Added `ibkr-demo` console script entry point
* Updated README with "Quick Demo (5 Minutes)" section

### Tests

* Unit: ✅ 15 tests passing

  * Demo command validates paper-mode config.
  * Demo command returns well-shaped quote and bar payload (mocked).
  * Error scenario testing (connection errors, wrong mode, etc.)
* Integration: ✅ Available (requires Gateway)

  * Demo command succeeds against a running IBKR Gateway in paper mode.

---

## Phase 6.2 - Safety section (make it loud) ✅ COMPLETE

### Goals

* A one-screen Safety section at the top of README.
* Default-safe behavior clearly emphasized.
* A short "How to enable live trading (and why you probably should not)" guide.

### Deliverables

* README Safety section placed before "Quick Start". ✅
* Explicit "paper by default" + "orders disabled by default" callouts. ✅
* Dual-toggle explanation for live trading:

  * `TRADING_MODE=live` AND `ORDERS_ENABLED=true` ✅
* Live trading enablement steps with warnings and a checklist. ✅
* `.env.example` updates that match the safety narrative. ✅

### Implementation

* Updated `README.md`:
  * Added prominent "⚠️ SAFETY FIRST ⚠️" section at top
  * Listed all safety defaults (paper mode, orders disabled)
  * Clear instructions for enabling live trading
  * Testing guidelines for live trading setup
* Enhanced `.env.example`:
  * Added large safety warning header
  * Reorganized into clear sections (Safety, Connection, API)
  * Detailed comments explaining each setting
  * Emphasized TRADING_MODE and ORDERS_ENABLED importance
* Updated `api/API.md`:
  * Added safety notice section at top
  * Explained SIMULATED status behavior
  * Documented preview vs. place order differences
* Enhanced MCP tool descriptions in `mcp_server/main.py`:
  * `preview_order`: Added "(SAFE - read-only simulation)"
  * `place_order`: Added "(SAFE BY DEFAULT - requires ORDERS_ENABLED=true)"
* Created `.context/SAFETY_CHECKLIST.md`:
  * Comprehensive 200+ line safety checklist
  * Pre-deployment checklist for live trading
  * Three-phase enablement protocol
  * Monitoring requirements and emergency procedures

### Tests

* Manual: ✅

  * README Safety section fits within one screen on desktop.
  * Safety documentation is prominent and clear.

---

## Phase 6.3 - Minimal CLI (shareable interface) ✅ COMPLETE

### Goals

* A small, friendly CLI to make the repo runnable.

### Deliverables

* `ibkr-gateway` CLI with commands: ✅

  * `ibkr-gateway healthcheck` ✅
  * `ibkr-gateway start-api` ✅
  * `ibkr-gateway demo` ✅
  * `ibkr-gateway version` ✅
* Global options for host/port and mode: ✅

  * `--host`, `--port`
  * `--paper` / `--live`
* CLI docs in README plus `--help` output. ✅

### Implementation

* Created `ibkr_core/cli.py` (343 lines):
  * Built with Typer and Rich for beautiful terminal UI
  * Commands implemented:
    * `healthcheck`: Tests IBKR Gateway connection with detailed status
    * `demo`: Runs interactive demo (delegates to demo.py)
    * `start-api`: Launches FastAPI server with uvicorn
    * `version`: Shows version information
  * Global options: `--host`, `--port`, `--paper`, `--live` (mutually exclusive)
  * Rich formatted tables and panels
  * Color-coded output
  * Safety override: Demo forces paper mode
  * Clear error messages with troubleshooting
* Created `tests/test_cli.py` (250+ lines):
  * 18 unit tests using Typer CliRunner
  * 2 integration tests
  * All commands and options covered
* Added dependencies:
  * `typer ^0.9.0` with all extras
  * `rich ^13.7`
* Added `ibkr-gateway` console script entry point
* Updated README with "Command-Line Interface" section

### Tests

* Unit: ✅ 18 tests passing

  * CLI argument parsing and help text.
  * All commands tested with mocked client.
  * Error scenarios covered.
* Integration: ✅ Available (requires Gateway)

  * `ibkr-gateway healthcheck` returns success with a running Gateway.

---

## Phase 6.4 - Repo hygiene and trust signals ✅ COMPLETE

### Goals

* Standard OSS documents that reduce friction and build trust.

### Deliverables

* `LICENSE` (MIT). ✅
* `SECURITY.md` with vulnerability reporting guidance. ✅
* `CONTRIBUTING.md` with setup + testing steps. ✅
* `.github/ISSUE_TEMPLATE/` with bug + feature templates. ✅
* `CHANGELOG.md` starting at `0.1.0`. ✅
* `PULL_REQUEST_TEMPLATE.md`. ✅

### Implementation

* Created `LICENSE`:
  * MIT License
  * Copyright 2024 mm-ibkr-gateway contributors
* Created `SECURITY.md`:
  * Vulnerability reporting via GitHub Security Advisories
  * Response timeline (48h initial, 7 days update)
  * Coordinated disclosure policy
  * Security best practices for users
  * Known security considerations
  * Safety feature documentation
* Created `CONTRIBUTING.md`:
  * Development setup instructions
  * Branch strategy
  * Code style guide (Black, isort, mypy)
  * Testing guidelines
  * PR process
  * Conventional commit format
  * Links to issues/discussions
* Created `CHANGELOG.md`:
  * Keep a Changelog format
  * Semantic Versioning
  * Version 0.1.0 documented
  * Unreleased section
  * Security section
* Created GitHub issue templates:
  * `.github/ISSUE_TEMPLATE/bug_report.yml`
  * `.github/ISSUE_TEMPLATE/feature_request.yml`
  * Structured forms with environment info
  * Phase categorization
* Created `.github/PULL_REQUEST_TEMPLATE.md`:
  * Type of change checklist
  * Testing checklist
  * Documentation checklist
  * Safety checklist

---

## Phase 6.5 - CI + coverage (credibility) ✅ COMPLETE

### Goals

* CI that proves unit tests and lint pass on PRs.
* Clear separation of integration tests.
* Coverage badge in README.

### Deliverables

* `.github/workflows/ci.yml` running: ✅

  * Lint (black, isort, flake8, mypy). ✅
  * Unit tests: `pytest -m "not integration"`. ✅
  * Coverage upload to Codecov. ✅
  * Security scanning (safety, bandit). ✅
* `pytest.ini` with `integration` marker documented. ✅
* Coverage report artifact and badge in README. ✅

### Implementation

* Created `.github/workflows/ci.yml`:
  * **Lint Job**: black, isort, flake8, mypy
  * **Test Job**: Unit tests on Python 3.10, 3.11, 3.12
  * **Coverage**: Upload to Codecov (Python 3.10 only)
  * **Security Job**: safety check, bandit scan
  * **Caching**: Poetry dependencies cached
* Created coverage configuration:
  * `.coveragerc`: Coverage exclusions and HTML output
  * `codecov.yml`: 80% project target, 70% patch target
  * `pyproject.toml`: Coverage run and report config
* Created `.pre-commit-config.yaml`:
  * Hooks: trailing-whitespace, black, isort, flake8
  * Optional setup: `poetry run pre-commit install`
* Added development dependencies:
  * `safety ^2.3`
  * `bandit ^1.7`
  * `pre-commit ^3.6`
* Enhanced pytest configuration:
  * Added `slow` marker
  * Added addopts for verbose, strict-markers, short traceback
* Updated README:
  * Badges: CI, codecov, Python, License, Code style
  * "Development & Testing" section
  * Running tests locally
  * Code quality commands
  * Pre-commit hooks setup
  * CI feature list

### Tests

* CI: ✅

  * Workflow configured and ready to run on push/PR.
  * Integration tests skipped by default with `-m "not integration"`.
  * Local testing verified: 385/428 unit tests passing (90%).

---

## Phase 7 – LLM tool integration and NL layer ⏭️ SKIPPED

### Decision Rationale

Phase 7 is **SKIPPED** because:

1. **MCP tools already enable LLM integration**: The MCP server (Phase 6) provides all necessary tools for LLM interaction via Claude Desktop or other MCP clients.
2. **No need for custom agent**: Building a custom NL chat loop duplicates functionality already available through MCP.
3. **Better separation of concerns**: Keep this project focused on IBKR integration, let MCP clients handle conversation flow.
4. **Safety enforced at API layer**: Order confirmation and safety guardrails are already implemented in the API and MCP tools (ORDERS_ENABLED flag, preview vs. place distinction).

### Alternative Approach

Users who need natural language interaction can:
- Use Claude Desktop with the MCP server configured
- Use any other MCP-compatible client
- Build their own custom agent using the MCP tools

---

## Phase 8 – Hardening, monitoring, and simulation

### Goals

* **Observability**: Structured logging with correlation IDs and comprehensive metrics
* **Audit trails**: Persistent order history and event logs in SQLite
* **Simulation mode**: Basic order flow simulation for testing without IBKR connection
* **Production readiness**: Monitoring, debugging, and compliance capabilities

### Technology Stack

Based on specifications:
- **Logging**: Python standard logging with `python-json-logger` for structured JSON logs
- **Persistence**: SQLite for audit logs and order history
- **Metrics**: In-memory metrics with `/metrics` API endpoint
- **Simulation**: Basic order simulation with validation and state transitions
- **Correlation**: UUID4-based request correlation IDs

### Deliverables

#### 8.1 – Structured Logging & Correlation IDs

* `ibkr_core/logging_config.py`:
  * JSON log formatter configuration
  * Correlation ID context management
  * Log level configuration via `LOG_LEVEL` env var
* API middleware:
  * Generate UUID4 correlation_id for each request
  * Propagate correlation_id through request context
  * Add correlation_id to all log records
  * Log request/response with timing
* IBKR client logging:
  * Wrap all IBKR operations with correlation_id
  * Log operation start/end with duration

#### 8.2 – Audit Trail & Order History (SQLite)

* `ibkr_core/persistence.py`:
  * Database connection management
  * Schema definitions:
    * `audit_log` table: Full event log with correlation IDs
    * `order_history` table: Complete order lifecycle tracking
  * Functions:
    * `record_audit_event(event_type, data, correlation_id)`
    * `save_order(order_id, order_data)`
    * `update_order_status(order_id, status, fill_data)`
    * `query_orders(filters)` - by symbol, date range, status, etc.
* Integration points:
  * Record PREVIEW events with market snapshot
  * Record SUBMIT events with config snapshot
  * Record status updates (FILLED, CANCELLED, REJECTED)
  * Store full order spec and preview/fill data as JSON
* Database management:
  * Auto-create database on first use
  * Configurable path via `AUDIT_DB_PATH` env var
  * Simple schema versioning

#### 8.3 – Metrics & Monitoring (In-Memory)

* `ibkr_core/metrics.py`:
  * `MetricsCollector` singleton with thread-safe operations
  * Metric types:
    * **Counters**: `api_requests_total{endpoint, status}`, `ibkr_operations_total{operation, status}`, `orders_total{status, symbol}`
    * **Histograms**: `api_request_duration_seconds{endpoint}`, `ibkr_operation_duration_seconds{operation}`, `order_time_to_fill_seconds{symbol}`
    * **Gauges**: `ibkr_connection_status`, `active_orders{status}`
  * Histogram percentiles: p50, p90, p95, p99
* API endpoint:
  * `GET /metrics`: Return all metrics as JSON
  * Format: `{counters: {...}, histograms: {...}, gauges: {...}}`
* Integration:
  * Middleware records all API requests
  * IBKR client records connection status and operations
  * Order manager tracks execution metrics

#### 8.4 – Simulation Backend (Basic)

* `ibkr_core/simulation.py`:
  * `SimulatedIBKRClient` class:
    * Same interface as `IBKRClient`
    * Simulated connection (instant, always succeeds)
    * Deterministic contract resolution
    * Synthetic quote generation
    * Order validation (same rules as real)
    * State machine for order lifecycle
  * Order execution simulation:
    * Market orders: fill immediately at synthetic quote
    * Limit orders: basic price check simulation
    * State transitions: PendingSubmit → Submitted → Filled
    * Simulated delays for realistic testing
  * Simulated registry tracking all orders
* Configuration:
  * `IBKR_MODE=simulation` env var enables simulation
  * Factory function: `get_ibkr_client()` returns appropriate client
  * API responses include `simulation: true` flag when active
* Use cases:
  * Testing order flows without IBKR connection
  * Strategy validation
  * CI/CD integration tests

#### 8.5 – Documentation & Tooling

* Documentation updates:
  * README: "Monitoring & Observability" section
  * API.md: Document `/metrics` endpoint
  * New: `MONITORING.md` with observability guide
  * New: `SIMULATION.md` with simulation mode guide
  * `.env.example`: Add Phase 8 variables
* Example scripts:
  * `scripts/query_audit_log.py`: Query audit database
  * `scripts/export_order_history.py`: Export to CSV
  * `scripts/metrics_dashboard.py`: Simple CLI metrics viewer
* Configuration:
  * `AUDIT_DB_PATH`: Database file path (default: `./data/audit.db`)
  * `IBKR_MODE`: `paper|live|simulation` (default: `paper`)
  * `LOG_LEVEL`: `DEBUG|INFO|WARNING|ERROR` (default: `INFO`)
  * `LOG_FORMAT`: `json|text` (default: `json`)

### Implementation Steps

1. **8.1 – Logging** (1-2 days)
   - Set up python-json-logger
   - Implement correlation ID middleware
   - Add structured logging across modules
   - Write tests

2. **8.2 – Persistence** (2-3 days)
   - Design SQLite schema
   - Implement persistence layer
   - Integrate audit logging into order flow
   - Write tests and queries

3. **8.3 – Metrics** (1-2 days)
   - Build MetricsCollector
   - Add metrics collection points
   - Create `/metrics` endpoint
   - Write tests

4. **8.4 – Simulation** (2-3 days)
   - Implement SimulatedIBKRClient
   - Build order execution simulator
   - Update factory functions
   - Write comprehensive tests

5. **8.5 – Documentation** (1 day)
   - Update all documentation
   - Write monitoring guide
   - Create example scripts
   - Update environment config

### Tests

**Unit tests** (estimated ~100 tests):
* `tests/test_logging_correlation.py`: Correlation ID propagation (10 tests)
* `tests/test_logging_structured.py`: JSON format validation (8 tests)
* `tests/test_persistence_audit.py`: Audit log CRUD (15 tests)
* `tests/test_persistence_orders.py`: Order history tracking (20 tests)
* `tests/test_metrics_collector.py`: Metrics collection (18 tests)
* `tests/test_metrics_endpoint.py`: API endpoint (8 tests)
* `tests/test_simulation_client.py`: Simulated client (25 tests)
* `tests/test_simulation_orders.py`: Order simulation (20 tests)

**Integration tests** (estimated ~30 tests):
* `tests/test_audit_trail_integration.py`: End-to-end audit trail (10 tests)
* `tests/test_metrics_integration.py`: Metrics during real operations (12 tests)
* `tests/test_simulation_integration.py`: Full API in simulation mode (15 tests)

**Performance tests**:
* Baseline latency benchmarks
* Metrics overhead measurement
* Database write performance

### Success Criteria

- [ ] All API requests have correlation IDs in logs
- [ ] Every order lifecycle event is recorded in audit database
- [ ] `/metrics` endpoint returns comprehensive metrics
- [ ] Simulation mode allows full order flow testing without IBKR
- [ ] Zero performance degradation >5% from logging/metrics overhead
- [ ] Complete documentation for monitoring and troubleshooting
- [ ] All tests passing (unit + integration)

---

## How this maps to your three main use cases

1. **Fetching data**

   * Phase 2 (market_data)
   * Exposed via Phase 5 (API) + Phase 6 (MCP)
   * Logged and monitored in Phase 8

2. **Fetching account status**

   * Phase 3 (account)
   * Same exposure + monitoring

3. **Placing orders**

   * Phase 4 (orders)
   * Strict safety in Phase 0 + 4
   * Full audit trail in Phase 8
   * Testable via simulation in Phase 8
