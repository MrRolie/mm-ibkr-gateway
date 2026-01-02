# 10_GLOSSARY.md: Terms, Acronyms, and Definitions

## Financial Terms

### Account

The customer's account at Interactive Brokers. Identified by account ID (e.g., `DU123456`). Accounts can be paper (simulated) or live (real money).

### Bid/Ask

- **Bid**: Price at which buyers are willing to buy
- **Ask**: Price at which sellers are willing to sell
- **Spread**: Ask - Bid (transaction cost)

### Cash

Available liquid funds in the account, net of margin requirements.

### Commission

Fee charged by the broker for executing an order. Typically a per-order fee (e.g., $5) or per-share (e.g., $0.01/share).

### Contract

IBKR's internal representation of a security. Uniquely identified by `conId` (contract ID). Linked to symbol, exchange, currency, and security type.

### Contract Expiry

Date when futures or options contracts expire. Format: `YYYY-MM-DD`. After expiry, contract becomes invalid.

### Currency

ISO 4217 code (e.g., `USD`, `EUR`, `JPY`). Base currency for account is typically USD.

### Delisting

When a security is removed from an exchange (bankruptcy, merger, etc.). Contract becomes invalid; orders fail.

### Fill / Filled

Execution of an order. "100 shares filled" means 100 shares were bought/sold at the market. Can be partial or full.

### Fill Price

Price at which shares were executed (average if multiple fills).

### Futures (FUT)

Leveraged contracts on commodities, indices, or currencies with fixed expiry dates. E.g., `ES` (E-mini S&P 500).

### Leverage / Margin

Borrowing buying power from the broker. Margin account allows 2x buying power (50% capital requirement).

### Long

Position where you own shares (bullish bet). Positive quantity in positions.

### Market Data

Real-time or delayed quotes and historical bars for securities.

### Options (OPT)

Derivatives giving right to buy (call) or sell (put) at a strike price by expiry date.

### P&L (Profit and Loss)

- **Realized P&L**: Profit/loss from closed positions (sold)
- **Unrealized P&L**: Profit/loss from open positions at current mark
- **Total P&L**: Realized + Unrealized

### Position

Current open lot of a security. Quantity positive (long) or negative (short).

### Quote

Market snapshot at a point in time. Includes bid, ask, last price, volume.

### Short

Position where you owe shares (bearish bet). Negative quantity in positions.

### Symbol / Ticker

Human-readable identifier for a security. E.g., `AAPL` (Apple), `ES` (E-mini S&P 500).

### Strike Price

Price at which an option can be exercised. E.g., `AAPL 150 C` = call option to buy AAPL at $150.

---

## Technical Terms

### API

**Application Programming Interface**. In this project: REST API on port 8000 or MCP protocol via Claude.

### ASGI

**Asynchronous Server Gateway Interface**. Protocol that Uvicorn implements to serve FastAPI.

### Async/Await

Python keywords for asynchronous I/O. `async def` defines coroutine; `await` suspends execution until result.

### Audit Log

Immutable record of all order actions. Stored in SQLite with correlation IDs for tracing.

### Cache

In-memory storage for resolved contracts. Persists during session; cleared on restart. Key: (symbol, type, exchange, currency).

### Correlation ID

UUID generated per request to trace logs across system. Enables debugging: "show me all logs for request X".

### Event Loop

Asyncio mechanism that manages asynchronous tasks. ib_insync requires persistent event loop in its thread.

### Executor

Thread pool for running blocking code (ib_insync calls) without blocking async event loop.

### Gateway

IBKR's server that exposes market data and order management. Runs on localhost:4002 (paper) or 4001 (live).

### Handler

HTTP endpoint function (e.g., `place_order_endpoint()`) that processes requests and returns responses.

### Idempotent

Property where repeating operation has same effect as single operation. E.g., placing same order twice returns same orderId.

### JSON

JavaScript Object Notation. Standard text format for API requests/responses.

### MCP

**Model Context Protocol**. Tool server that exposes functions to Claude AI for natural language interaction.

### Middleware

Layer that processes requests before reaching handlers. E.g., CorrelationIdMiddleware adds tracing ID.

### ORM

**Object-Relational Mapping**. Maps Python objects to database rows. Not used here (raw SQL + Pydantic instead).

### Pydantic

Python library for data validation. Enforces types and constraints at runtime.

### REST

**Representational State Transfer**. API style using HTTP verbs (GET, POST, PUT, DELETE) and resources.

### Schema

Definition of data structure. In this project: JSON Schema in docs, Pydantic models in code.

### Serialization

Converting Python objects to JSON (or vice versa). E.g., `Quote.model_dump_json()`.

### Socket

Network connection between client and server. IBKR Gateway listens on TCP socket port 4002.

### Status Code

HTTP response code. E.g., 200 (success), 400 (bad request), 500 (server error).

### Validation

Checking that data matches expected schema and constraints. Pydantic handles this for API.

### Webhook

URL that receives notifications when events occur. Not used here (polling instead).

---

## IBKR-Specific Terms

### Client ID

Unique identifier per connection to IBKR Gateway. Multiple client IDs can connect simultaneously (for scaling).

### Commission

Fee per order. IBKR charges flat or per-share commission based on account type.

### Contract ID (conId)

IBKR's internal unique identifier for a security. Derived from symbol + exchange + currency + type.

### Gateway / TWS

- **Gateway**: Lightweight connection service
- **TWS (Trader Workstation)**: Full-featured UI application
Both expose same API on port 4002 (paper) or 4001 (live).

### Margin Excess

Amount of excess margin (cushion above maintenance requirement). Negative = margin call.

### Order Type

Classification of how order executes:

- **MKT** (Market): Execute immediately at market price
- **LMT** (Limit): Execute only at specified price or better
- **STP** (Stop): Execute at stop price once triggered
- **STP_LMT** (Stop-Limit): Combination of stop and limit
- **MOC** (Market on Close): Execute at market close
- **OPG** (Opening): Execute at market open

### Portfolio

Aggregate of all positions in an account.

### Smart Routing

IBKR's `SMART` exchange that automatically routes orders to best venue.

### Time in Force

How long order remains active:

- **DAY**: Cancels at market close
- **GTC** (Good Till Cancel): Remains until manually cancelled
- **IOC** (Immediate Or Cancel): Execute what's available immediately, cancel remainder
- **FOK** (Fill Or Kill): All or nothing; cancel if can't fill fully

---

## Order Status Values

### SUBMITTED

Order sent to IBKR but not yet acknowledged.

### ACCEPTED

IBKR Gateway accepted the order.

### PENDING

Order is in broker's queue, not yet executed.

### PARTIAL_FILLED

Some shares filled; remainder still open.

### FILLED

All shares filled and execution complete.

### CANCELLED

Order cancelled by user or broker before execution.

### REJECTED

Broker rejected order (invalid contract, margin, etc.).

### SIMULATED

Order placement simulated (not sent to broker). Occurs when `TRADING_MODE=paper` or `ORDERS_ENABLED=false`.

---

## Configuration Terms

### Trading Mode

- **Paper**: Simulated trading (no real money)
- **Live**: Real trading (real money, real fills)

### Orders Enabled

Boolean flag: `true` (allow real order placement) or `false` (simulate all orders).

### Override File

File that must exist for live trading to be enabled. Path: typically `~/ibkr_live_trading_confirmed.txt`. Deletion immediately disables live trading.

### Environment Variable

Configuration key-value pair loaded from `.env` file. E.g., `TRADING_MODE=paper`.

---

## Database Terms

### Append-Only

Design where records are only inserted (never updated or deleted). Ensures audit trail immutability.

### Correlation ID

UUID stored in audit log to link all events from single request. Enables tracing across logs.

### Primary Key

Column(s) that uniquely identify a row. E.g., `order_id` in `order_history`.

### Unique Constraint

Database rule preventing duplicate values. E.g., `UNIQUE(correlation_id, event_type, timestamp)` in `audit_log`.

### SQLite

File-based relational database. Used for audit logs and order history in this project.

### Schema Version

Database structure version number. Incremented when table definitions change (for migrations).

---

## API Terms

### Endpoint

Specific URL path that handles requests. E.g., `/api/orders/place` is an endpoint.

### Query Parameter

Key-value pair appended to URL. E.g., `?symbol=AAPL&securityType=STK`.

### Request Body

Data sent in POST/PUT request body (typically JSON).

### Response Body

Data returned by server (typically JSON).

### Status Code

HTTP response code. E.g., 200 (OK), 400 (Bad Request), 503 (Service Unavailable).

### Authentication

Verification that requester is authorized. This API uses optional `API_KEY` header.

### Rate Limiting

Restricting number of requests per time period. IBKR Gateway has soft limits; explicit rate limiter not implemented yet.

---

## Time-Related Terms

### UTC

Coordinated Universal Time (GMT). Standard time zone used throughout system.

### ISO 8601

International standard for date/time format: `2025-01-01T09:35:00Z`.

### Timezone

Offset from UTC. E.g., EST = UTC-5 hours. System stores UTC; display converts to local tz.

### Market Hours

When exchanges are open. US equities: 9:30 AM - 4:00 PM ET.

### After-Hours

Trading outside regular market hours. 4:00 PM - 8:00 PM ET for US equities.

### Timestamp

Date and time recorded in a log or database. All timestamps in system are UTC.

---

## Security-Related Terms

### Security Type

Classification of instrument:

- **STK**: Stock
- **FUT**: Futures
- **OPT**: Options
- **ETF**: Exchange-Traded Fund
- **IND**: Index
- **CASH**: Cash equivalent
- **CFD**: Contract for Difference
- **BOND**: Bond
- **FUND**: Mutual fund
- **CRYPTO**: Cryptocurrency

### Exchange

Venue where security trades. E.g., `NASDAQ`, `NYSE`, `GLOBEX`, `CBOE`.

### Symbol

Ticker identifier. E.g., `AAPL` (Apple), `ES` (E-mini S&P 500), `SPX` (S&P 500 Index).

### Multiplier

Scaling factor for contract value. Options typically have multiplier=100 (1 contract = 100 shares); futures vary.

---

## Logging-Related Terms

### Correlation ID

UUID that tags related log entries. Enables tracing: "Show all logs for this request."

### Structured Logging

Logging with key-value pairs (JSON format) instead of plain text. Enables querying and filtering.

### Log Level

Severity: DEBUG, INFO, WARNING, ERROR, CRITICAL.

### JSON Logger

Formatter that outputs logs as JSON objects. Enables programmatic parsing.

---

## Common Abbreviations

| Abbreviation | Full Form | Context |
|---|---|---|
| AAPL | Apple Inc. | Stock symbol |
| API | Application Programming Interface | Software interface |
| ASGI | Asynchronous Server Gateway Interface | Web server protocol |
| CLI | Command-Line Interface | Terminal commands |
| conId | Contract ID | IBKR identifier |
| ETF | Exchange-Traded Fund | Security type |
| FUT | Futures | Security type |
| GTC | Good Till Cancel | Time in force |
| HTTP | HyperText Transfer Protocol | Web protocol |
| IBKR | Interactive Brokers | Broker |
| IDC | Interactive Data | Market data provider |
| IOC | Immediate Or Cancel | Time in force |
| JSON | JavaScript Object Notation | Data format |
| MCP | Model Context Protocol | Claude integration |
| MES | E-mini S&P 500 | Futures symbol |
| MOC | Market on Close | Order type |
| OPG | Opening | Order type |
| OPT | Options | Security type |
| P&L | Profit and Loss | Financial metric |
| REST | Representational State Transfer | API style |
| STP | Stop | Order type |
| STK | Stock | Security type |
| UUID | Universally Unique Identifier | Unique reference |
| UTC | Coordinated Universal Time | Time zone |

---

## Example Scenarios

### "Place a BUY order for 100 AAPL at $150 limit"

Translate to `OrderSpec`:

```python
OrderSpec(
    symbol="AAPL",                    # Stock symbol
    securityType="STK",               # Stock type
    action="BUY",                     # Buy (not sell)
    quantity=100,                     # 100 shares
    orderType="LMT",                  # Limit order
    limitPrice=150.00,                # Limit price in dollars
    timeInForce="DAY"                 # Cancel at market close
)
```

### "What is my net liquidation value?"

Query: `GET /api/account/summary`

Response includes:

```json
{
    "netLiquidation": 100000.00,      # Total account value
    "cash": 50000.00,                 # Available cash
    "buyingPower": 100000.00          # Can buy up to $100k (2x leverage)
}
```

### "Cancel order #1001"

Query: `POST /api/orders/1001/cancel`

Response:

```json
{
    "orderId": 1001,
    "status": "CANCELLED",
    "message": "Order cancelled successfully"
}
```

---

## Summary

- **Financial**: Account, position, P&L, fill, commission
- **Technical**: API, async, pydantic, validation, serialization
- **IBKR**: Contract, gateway, client ID, order types, commissions
- **Time**: UTC, ISO 8601, market hours
- **Database**: Audit log, append-only, correlation ID, schema
- **API**: Endpoint, request/response, status codes, authentication
