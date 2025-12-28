# API Quick Reference

## REST API Endpoints

Base URL: `http://localhost:8000`

### Health & Metrics

```bash
# Health check
curl http://localhost:8000/health

# Application metrics
curl http://localhost:8000/metrics
```

### Market Data

```bash
# Get quote
curl -X POST http://localhost:8000/market-data/quote \
  -H "Content-Type: application/json" \
  -d '{"symbol": "AAPL", "securityType": "STK", "exchange": "SMART", "currency": "USD"}'

# Get historical bars
curl -X POST http://localhost:8000/market-data/historical \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "AAPL",
    "securityType": "STK",
    "exchange": "SMART",
    "currency": "USD",
    "barSize": "1 hour",
    "duration": "1 D"
  }'
```

### Account

```bash
# Account summary
curl http://localhost:8000/account/summary

# Positions
curl http://localhost:8000/account/positions

# P&L
curl http://localhost:8000/account/pnl
```

### Orders

```bash
# Preview order
curl -X POST http://localhost:8000/orders/preview \
  -H "Content-Type: application/json" \
  -d '{
    "instrument": {"symbol": "AAPL", "securityType": "STK", "exchange": "SMART", "currency": "USD"},
    "side": "BUY",
    "quantity": 10,
    "orderType": "LMT",
    "limitPrice": 150.00
  }'

# Place order
curl -X POST http://localhost:8000/orders \
  -H "Content-Type: application/json" \
  -d '{
    "instrument": {"symbol": "AAPL", "securityType": "STK", "exchange": "SMART", "currency": "USD"},
    "side": "BUY",
    "quantity": 10,
    "orderType": "MKT"
  }'

# Cancel order
curl -X POST http://localhost:8000/orders/{order_id}/cancel

# Get order status
curl http://localhost:8000/orders/{order_id}/status

# List open orders
curl http://localhost:8000/orders/open
```

## CLI Commands

```bash
# Quotes
poetry run python -m ibkr_core.cli quote AAPL
poetry run python -m ibkr_core.cli quote AAPL --mode paper

# Historical data
poetry run python -m ibkr_core.cli bars AAPL --duration "5 D" --bar-size "1 hour"

# Account
poetry run python -m ibkr_core.cli account
poetry run python -m ibkr_core.cli positions
poetry run python -m ibkr_core.cli pnl

# Orders
poetry run python -m ibkr_core.cli preview BUY 10 AAPL --order-type LMT --limit-price 150
poetry run python -m ibkr_core.cli order BUY 10 AAPL --order-type MKT
poetry run python -m ibkr_core.cli cancel <order_id>
poetry run python -m ibkr_core.cli status <order_id>
```

## MCP Tools

Available via MCP server for LLM integration:

| Tool | Description |
|------|-------------|
| `ibkr_health` | Check gateway connection status |
| `ibkr_quote` | Get real-time quote |
| `ibkr_historical` | Get historical bars |
| `ibkr_account_summary` | Account balances |
| `ibkr_positions` | Open positions |
| `ibkr_pnl` | Profit/loss |
| `ibkr_preview_order` | Preview order execution |
| `ibkr_place_order` | Place order (if enabled) |
| `ibkr_cancel_order` | Cancel order |
| `ibkr_order_status` | Get order status |
| `ibkr_open_orders` | List open orders |

## Request/Response Models

### SymbolSpec
```json
{
  "symbol": "AAPL",
  "securityType": "STK",       // STK, OPT, FUT, CASH, etc.
  "exchange": "SMART",
  "currency": "USD",
  "expiry": null,              // For options/futures
  "strike": null,              // For options
  "right": null                // "C" or "P" for options
}
```

### OrderSpec
```json
{
  "instrument": { /* SymbolSpec */ },
  "side": "BUY",               // BUY or SELL
  "quantity": 100,
  "orderType": "LMT",          // MKT, LMT, STP, STP_LMT, TRAIL, etc.
  "limitPrice": 150.00,        // Required for LMT
  "stopPrice": null,           // For STP orders
  "accountId": null            // Optional, uses default
}
```

### Quote Response
```json
{
  "symbol": "AAPL",
  "bid": 149.95,
  "ask": 150.05,
  "last": 150.00,
  "bidSize": 100,
  "askSize": 200,
  "lastSize": 50,
  "volume": 1000000,
  "timestamp": "2025-01-15T10:30:00"
}
```

### OrderResult
```json
{
  "orderId": "uuid-here",
  "status": "ACCEPTED",        // ACCEPTED, REJECTED, SIMULATED
  "message": "Order placed successfully",
  "ibkrOrderId": 12345,
  "orderStatus": {
    "status": "Submitted",
    "filled": 0,
    "remaining": 100,
    "avgFillPrice": 0.0
  }
}
```

## Error Responses

```json
{
  "error_code": "VALIDATION_ERROR",
  "message": "Invalid order type: INVALID",
  "details": { ... }
}
```

Error codes:
- `VALIDATION_ERROR` - Invalid request parameters
- `IBKR_ERROR` - IBKR Gateway error
- `TIMEOUT` - Operation timed out
- `NOT_FOUND` - Resource not found
- `PERMISSION_DENIED` - Orders disabled or auth failed
