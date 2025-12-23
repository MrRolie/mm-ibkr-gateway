# IBKR Gateway API Documentation

REST API for Interactive Brokers Gateway integration.

## Quick Start

### Running the Server

```bash
# Start the API server (default port 8000)
uvicorn api.server:app --host 0.0.0.0 --port 8000

# With auto-reload for development
uvicorn api.server:app --reload

# Using the main entry point
python -m api.server
```

### Environment Configuration

Create a `.env` file with the following variables:

```bash
# IBKR Gateway Connection
IBKR_GATEWAY_HOST=127.0.0.1

# Paper Trading (default)
PAPER_GATEWAY_PORT=4002
PAPER_CLIENT_ID=1

# Live Trading (if needed)
LIVE_GATEWAY_PORT=4001
LIVE_CLIENT_ID=777

# Trading Mode: paper or live
TRADING_MODE=paper

# Order Placement: false (simulation) or true (real orders)
ORDERS_ENABLED=false

# API Server
API_PORT=8000
LOG_LEVEL=INFO

# Optional: API Key for authentication
# If set, all requests must include X-API-Key header
# API_KEY=your-secret-key

# Optional: Request timeout in seconds
# API_REQUEST_TIMEOUT=30
```

## Authentication

Authentication is optional. If the `API_KEY` environment variable is set, all requests must include the `X-API-Key` header.

```bash
# With authentication enabled
curl -H "X-API-Key: your-secret-key" http://localhost:8000/account/summary

# Without authentication (local-only mode)
curl http://localhost:8000/account/summary
```

## Endpoints

### Health Check

#### GET /health

Check API and IBKR connection status.

**Response:**

```json
{
  "status": "ok",
  "ibkr_connected": true,
  "server_time": "2024-01-15T14:30:00Z",
  "trading_mode": "paper",
  "orders_enabled": false,
  "version": "0.1.0"
}
```

**Note:** `server_time` is best-effort and may be `null` even when
`ibkr_connected=true` if the server time request times out.

| Field | Description |
|-------|-------------|
| status | `ok` if connected, `degraded` if not |
| ibkr_connected | Boolean connection status |
| server_time | IBKR server time (best-effort; may be null if request times out) |
| trading_mode | Current mode: `paper` or `live` |
| orders_enabled | Whether real orders can be placed |

---

### Market Data

#### POST /market-data/quote

Get current quote for a symbol.

**Request:**

```json
{
  "symbol": "AAPL",
  "securityType": "STK",
  "exchange": "SMART",
  "currency": "USD"
}
```

**Response:**

```json
{
  "symbol": "AAPL",
  "conId": 265598,
  "bid": 150.0,
  "ask": 150.05,
  "last": 150.02,
  "bidSize": 100,
  "askSize": 200,
  "lastSize": 50,
  "volume": 1000000,
  "timestamp": "2024-01-15T14:30:00Z",
  "source": "IBKR_SNAPSHOT"
}
```

#### POST /market-data/historical

Get historical OHLCV bars.

**Request:**

```json
{
  "symbol": "AAPL",
  "securityType": "STK",
  "exchange": "SMART",
  "currency": "USD",
  "barSize": "1d",
  "duration": "1mo",
  "whatToShow": "TRADES",
  "rthOnly": true
}
```

| Field | Description |
|-------|-------------|
| barSize | Bar size: `1s`, `5s`, `1m`, `5m`, `15m`, `1h`, `1d`, `1w`, `1mo` |
| duration | Duration: `60s`, `1d`, `5d`, `1w`, `1mo`, `3mo`, `1y` |
| whatToShow | Data type: `TRADES`, `MIDPOINT`, `BID`, `ASK` |
| rthOnly | Regular trading hours only |

**Response:**

```json
{
  "symbol": "AAPL",
  "barCount": 20,
  "bars": [
    {
      "symbol": "AAPL",
      "time": "2024-01-15T00:00:00Z",
      "open": 150.0,
      "high": 151.0,
      "low": 149.0,
      "close": 150.5,
      "volume": 1000000,
      "barSize": "1 day",
      "source": "IBKR_HISTORICAL"
    }
  ]
}
```

---

### Account

#### GET /account/summary

Get account balances, margin, and buying power.

**Query Parameters:**

- `account_id` (optional): Specific account ID. Defaults to first managed account.

**Response:**

```json
{
  "accountId": "DU1234567",
  "currency": "USD",
  "netLiquidation": 100000.0,
  "cash": 50000.0,
  "buyingPower": 200000.0,
  "marginExcess": 75000.0,
  "maintenanceMargin": 10000.0,
  "initialMargin": 15000.0,
  "timestamp": "2024-01-15T14:30:00Z"
}
```

#### GET /account/positions

Get all open positions.

**Query Parameters:**

- `account_id` (optional): Specific account ID.

**Response:**

```json
{
  "accountId": "DU1234567",
  "positionCount": 2,
  "positions": [
    {
      "accountId": "DU1234567",
      "symbol": "AAPL",
      "conId": 265598,
      "assetClass": "STK",
      "currency": "USD",
      "quantity": 100,
      "avgPrice": 150.0,
      "marketPrice": 152.0,
      "marketValue": 15200.0,
      "unrealizedPnl": 200.0,
      "realizedPnl": 0.0
    }
  ]
}
```

#### GET /account/pnl

Get realized and unrealized P&L.

**Query Parameters:**

- `account_id` (optional): Specific account ID.
- `timeframe` (optional): Not yet implemented.

**Response:**

```json
{
  "accountId": "DU1234567",
  "currency": "USD",
  "timeframe": "CURRENT",
  "realized": 500.0,
  "unrealized": 1200.0,
  "bySymbol": {
    "AAPL": {
      "symbol": "AAPL",
      "conId": 265598,
      "currency": "USD",
      "realized": 200.0,
      "unrealized": 800.0
    }
  },
  "timestamp": "2024-01-15T14:30:00Z"
}
```

---

### Orders

#### POST /orders/preview

Preview an order without placing it.

**Request:**

```json
{
  "instrument": {
    "symbol": "AAPL",
    "securityType": "STK",
    "exchange": "SMART",
    "currency": "USD"
  },
  "side": "BUY",
  "quantity": 10,
  "orderType": "LMT",
  "limitPrice": 150.0,
  "tif": "DAY"
}
```

**Supported Order Types:**

- `MKT` - Market order
- `LMT` - Limit order (requires `limitPrice`)
- `STP` - Stop order (requires `stopPrice`)
- `STP_LMT` - Stop-limit order (requires both prices)
- `TRAIL` - Trailing stop (requires `trailingAmount` OR `trailingPercent`)
- `TRAIL_LIMIT` - Trailing stop-limit
- `BRACKET` - Entry + take profit + stop loss (requires `limitPrice`, `takeProfitPrice`, `stopLossPrice`)
- `MOC` - Market-on-close
- `OPG` - Market-on-open

**Response:**

```json
{
  "orderSpec": { ... },
  "estimatedPrice": 150.0,
  "estimatedNotional": 1500.0,
  "estimatedCommission": 1.0,
  "warnings": ["Preview is simulated using current market data"],
  "legs": [],
  "totalNotional": 1500.0
}
```

#### POST /orders

Place an order.

**Important:** Respects `ORDERS_ENABLED` setting. If `false`, returns `SIMULATED` status.

**Request:** Same as `/orders/preview`

**Response:**

```json
{
  "orderId": "12345",
  "clientOrderId": null,
  "status": "ACCEPTED",
  "orderStatus": {
    "orderId": "12345",
    "status": "SUBMITTED",
    "filledQuantity": 0,
    "remainingQuantity": 10,
    "avgFillPrice": 0,
    "lastUpdate": "2024-01-15T14:30:00Z"
  },
  "errors": [],
  "orderIds": [],
  "orderRoles": {}
}
```

| Status | Description |
|--------|-------------|
| ACCEPTED | Order placed successfully |
| REJECTED | Order was rejected |
| SIMULATED | ORDERS_ENABLED=false (not actually placed) |

For **BRACKET** orders, `orderIds` contains all 3 order IDs and `orderRoles` maps role to ID:

```json
{
  "orderIds": ["12345", "12346", "12347"],
  "orderRoles": {
    "entry": "12345",
    "take_profit": "12346",
    "stop_loss": "12347"
  }
}
```

#### POST /orders/{order_id}/cancel

Cancel an open order.

**Response:**

```json
{
  "orderId": "12345",
  "status": "CANCELLED",
  "message": "Order cancelled successfully"
}
```

| Status | Description |
|--------|-------------|
| CANCELLED | Order cancelled |
| ALREADY_FILLED | Order was already filled |
| NOT_FOUND | Order not found |
| REJECTED | Cancel failed |

#### GET /orders/{order_id}/status

Get current order status.

**Response:**

```json
{
  "orderId": "12345",
  "clientOrderId": null,
  "status": "SUBMITTED",
  "filledQuantity": 0,
  "remainingQuantity": 10,
  "avgFillPrice": 0,
  "lastUpdate": "2024-01-15T14:30:00Z",
  "warnings": []
}
```

| Status | Description |
|--------|-------------|
| PENDING_SUBMIT | Order being submitted |
| PENDING_CANCEL | Cancel in progress |
| SUBMITTED | Order active |
| PARTIALLY_FILLED | Partially filled |
| FILLED | Fully filled |
| CANCELLED | Cancelled |
| REJECTED | Rejected by broker |
| EXPIRED | Order expired |

#### GET /orders/open

Get all currently open orders.

**Response:**

```json
[
  {
    "order_id": "12345",
    "symbol": "AAPL",
    "side": "BUY",
    "quantity": 10,
    "order_type": "LMT",
    "status": "Submitted",
    "filled": 0,
    "remaining": 10
  }
]
```

---

## Error Model

All errors follow a consistent format:

```json
{
  "error_code": "VALIDATION_ERROR",
  "message": "Human-readable error description",
  "details": {
    "field": "quantity",
    "reason": "must be positive"
  }
}
```

### Common Error Codes

| Code | HTTP Status | Description |
|------|-------------|-------------|
| IBKR_CONNECTION_ERROR | 503 | Cannot connect to IBKR Gateway |
| IBKR_TIMEOUT | 504 | Request timed out |
| MARKET_DATA_PERMISSION_DENIED | 403 | No permission for market data |
| NO_DATA | 404 | No data available |
| PACING_VIOLATION | 429 | Too many requests |
| CONTRACT_RESOLUTION_ERROR | 400 | Invalid contract specification |
| ACCOUNT_ERROR | 500 | Account data retrieval failed |
| TRADING_DISABLED | 403 | ORDERS_ENABLED=false |
| ORDER_VALIDATION_ERROR | 400 | Invalid order parameters |
| ORDER_PLACEMENT_ERROR | 500 | Order placement failed |
| ORDER_NOT_FOUND | 404 | Order not found |
| ORDER_CANCEL_ERROR | 500 | Cancel failed |
| UNAUTHORIZED | 401 | Invalid or missing API key |
| VALIDATION_ERROR | 400 | Request validation failed |
| INTERNAL_ERROR | 500 | Unexpected server error |
| TIMEOUT | 504 | Request timeout |

---

## Timeouts

- Default request timeout: 30 seconds
- Historical data requests: 60 seconds
- Connection timeout: 10 seconds
- Health check server time: 2 seconds (best-effort)

Configure via `API_REQUEST_TIMEOUT` environment variable.

---

## Safety Notes

1. **Paper Trading Only**: By default, `TRADING_MODE=paper`. Never set to `live` without explicit override file.

2. **Orders Disabled**: By default, `ORDERS_ENABLED=false`. Orders return `SIMULATED` status.

3. **Live Trading Override**: To enable live trading:
   - Set `TRADING_MODE=live`
   - Set `ORDERS_ENABLED=true`
   - Set `LIVE_TRADING_OVERRIDE_FILE` to path of an existing file

4. **No Destructive Operations**: API never performs destructive operations without explicit request.

---

## OpenAPI / Swagger

Interactive API documentation available at:

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`
- OpenAPI JSON: `http://localhost:8000/openapi.json`
