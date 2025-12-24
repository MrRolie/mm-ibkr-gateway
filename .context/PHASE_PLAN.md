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

## Phase 6.1 - First 5 minutes (paper-only demo)

### Goals

* A demo that works quickly in paper mode without placing orders.
* Explicitly requires IBKR Gateway paper running.

### Deliverables

* Paper-only demo command (requires IBKR Gateway paper running):

  * `ibkr-gateway demo` or `python -m ibkr_core.demo`
* Dockerfile + docker-compose demo setup for paper mode (one-command).
* README "Quick Demo (paper-only)" section with copy/paste commands.

### Implementation steps

1. Add a demo script/CLI command that connects in paper mode and prints a quote plus a small bar series.
2. Detect and fail fast with a clear error if IBKR Gateway paper is not reachable.
3. Document the required market data subscriptions for the demo symbols.
4. Add a proper Dockerfile and docker-compose demo setup for paper mode.
5. Update README to show the paper-only quick demo steps and prerequisites.

### Tests

* Unit:

  * Demo command validates paper-mode config.
  * Demo command returns a well-shaped quote and bar payload (mocked).
* Integration:

  * Demo command succeeds against a running IBKR Gateway in paper mode.

---

## Phase 6.2 - Safety section (make it loud)

### Goals

* A one-screen Safety section at the top of README.
* Default-safe behavior clearly emphasized.
* A short "How to enable live trading (and why you probably should not)" guide.

### Deliverables

* README Safety section placed before "Quick Start".
* Explicit "paper by default" + "orders disabled by default" callouts.
* Dual-toggle explanation for live trading:

  * `TRADING_MODE=live` AND `ORDERS_ENABLED=true`
* Live trading enablement steps with warnings and a checklist.
* `.env.example` updates that match the safety narrative.

### Implementation steps

1. Move Safety content near the top of README (one screen).
2. Add a short "How to enable live trading" block with numbered steps.
3. Reconfirm config safeguards and any extra live-trading ack flag/file.
4. Ensure CLI and API docs mention the safety defaults.

### Tests

* Manual:

  * New README Safety section fits within one screen on desktop.

---

## Phase 6.3 - Minimal CLI (shareable interface)

### Goals

* A small, friendly CLI to make the repo runnable.

### Deliverables

* `ibkr-gateway` CLI with commands:

  * `ibkr-gateway healthcheck`
  * `ibkr-gateway quote AAPL`
  * `ibkr-gateway start-api`
  * `ibkr-gateway demo`
* Global options for host/port and mode:

  * `--host`, `--port`
  * `--paper` / `--live`
* CLI docs in README plus `--help` output.

### Implementation steps

1. Pick a CLI framework (argparse or Typer) and create `ibkr_core/cli.py`.
2. Add console-script entry point in `pyproject.toml`.
3. Implement `healthcheck`, `quote`, `start-api`, and `demo` commands.
4. Add JSON output option for scripting (`--json`).
5. Document CLI usage and examples in README.

### Tests

* Unit:

  * CLI argument parsing and help text.
  * `quote` returns a well-shaped response in paper mode (mocked client).
* Integration:

  * `ibkr-gateway healthcheck` returns success with a running Gateway.

---

## Phase 6.4 - Repo hygiene and trust signals

### Goals

* Standard OSS documents that reduce friction and build trust.

### Deliverables

* `LICENSE` (MIT or Apache-2.0).
* `SECURITY.md` with vulnerability reporting guidance.
* `CODE_OF_CONDUCT.md`.
* `CONTRIBUTING.md` with setup + testing steps.
* `.github/ISSUE_TEMPLATE/` with bug + feature templates.
* `CHANGELOG.md` starting at `0.1.0`.
* Optional: `PULL_REQUEST_TEMPLATE.md`.

### Implementation steps

1. Choose license and add the canonical license text.
2. Add SECURITY policy with contact method and response expectations.
3. Add contributor guidelines (setup, tests, style, PR flow).
4. Add issue templates (YAML) and optional PR template.
5. Add a minimal CHANGELOG structure with "Unreleased" and `0.1.0`.

---

## Phase 6.5 - CI + coverage (credibility)

### Goals

* CI that proves unit tests and lint pass on PRs.
* Clear separation of integration tests.
* Coverage badge in README.

### Deliverables

* `.github/workflows/ci.yml` running:

  * Lint (use existing tooling or add ruff/black).
  * Unit tests: `pytest -m "not integration"`.
* `pytest.ini` with `integration` marker documented.
* Coverage report artifact and badge in README.
* Optional: separate manual workflow for integration tests.

### Implementation steps

1. Add GitHub Actions workflow for lint + unit tests on PRs.
2. Configure `pytest` markers and default skip of integration tests.
3. Add coverage config and generate `coverage.xml`.
4. Add a coverage badge to README (Codecov or Coveralls).
5. Document how to run integration tests locally.

### Tests

* CI:

  * Verify lint + unit test workflow passes.
  * Ensure integration tests are skipped by default.

---

## Phase 7 – LLM tool integration and NL layer

Now you wire this into a model for natural-language.

### Goals

* Natural language → correct tool calls.
* Guardrails around order placement.

### Deliverables

* `nl/agent_prompts.md`:

  * System prompt describing:

    * Available tools and when to use them.
    * Safety rules:

      * Always show an order preview before placing an order.
      * Never place a real order unless user explicitly confirms and environment allows.
* `nl/agent.py`:

  * Functions to:

    * Take user prompt, call LLM with MCP tools available.
    * Stream responses.
    * Optionally implement two-step confirmation for trades.

### Implementation steps

1. Define canonical intents:

   * "fetch data": ask for quotes/historical.
   * "fetch account": call account tools.
   * "place order": always:

     1. Call `preview_order`.
     2. Explain to user what will be done.
     3. Wait for a clear "confirm" message.
     4. Call `place_order`.
2. Implement simple chat loop:

   * User text → LLM with tools.
   * Execute tools when requested.
   * Return combined answer.

### Tests

* Manual scripted tests:

  * "What's my net liquidation?" → only calls account tools.
  * "Get me the last 5 days of MES futures data" → historical data tool.
  * "Buy 1 MES at market":

    * Step 1: LLM calls `preview_order`.
    * Step 2: LLM explains preview in natural language.
    * Step 3: Only when user replies "Yes, confirm" → tool call `place_order`.
* Edge cases:

  * Ambiguous requests ("buy some MES") → LLM must ask for quantity or clarify.
  * User says "never mind" after preview → no order placed.

---

## Phase 8 – Hardening, monitoring, and simulation

### Goals

* Observability.
* Simulation mode for strategies / order flows without touching IBKR.
* Clear audit trails.

### Deliverables

* Logging:

  * Per tool call: correlation ID, request, response summary, timing.
* Metrics:

  * Market data latency, failure rates, order error rates.
* Simulation backend (optional extension):

  * Replace IBKR client with a mock exchange for certain environments.

### Tests

* Confirm every order attempt (even rejected) is logged with details.
* Run a "replay" script:

  * Read a log of previous requests.
  * Replay them in simulation mode and compare outcomes.

---

## How this maps to your three main use cases

1. **Fetching data**

   * Phase 2 (market_data)
   * Exposed via Phase 5 (API) + Phase 6 (MCP)
   * Used by Phase 7 (NL agent)

2. **Fetching account status**

   * Phase 3 (account)
   * Same exposure + NL flow as above

3. **Placing orders**

   * Phase 4 (orders)
   * Strict safety in Phase 0 + 4
   * NL agent in Phase 7 enforces preview/confirm flow
