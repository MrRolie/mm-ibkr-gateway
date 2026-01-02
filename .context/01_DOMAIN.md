# 01_DOMAIN.md: IBKR Gateway Domain Concepts

## Overview

This file defines domain concepts, terminology, units, and conventions used throughout the system.

---

## Core Concepts

### Security Types (IBKR Codes)

| Code | Name | Example | Notes |
|------|------|---------|-------|
| `STK` | Stock | AAPL, MSFT | Equities |
| `ETF` | Exchange Traded Fund | SPY, QQQ | Index tracking |
| `FUT` | Futures | ES, NQ, CL | Leveraged, expiring |
| `OPT` | Options | AAPL 150 C Jan 2025 | Calls, puts, strikes |
| `IND` | Index | SPX, VIX | Spot indexes |
| `CASH` | Cash Equivalent | USD | Not tradeable |
| `CFD` | Contract for Difference | GBP.USD | Some jurisdictions |
| `BOND` | Bonds | TLT, AGG | Fixed income |
| `FUND` | Mutual Fund | Varies | Closed-end |
| `CRYPTO` | Cryptocurrency | BTC, ETH | Via IBKR |

**Key invariant**: Every resolved contract has exactly one security type.

---

### Account Types

- **Paper Account**: Simulated trading, no real money. Default safe mode.
- **Live Account**: Real money. Requires explicit configuration and override file.

---

## Instruments & Contracts

### SymbolSpec (Logical Specification)

User-facing request to describe an instrument:

```python
# User provides this:
{
  "symbol": "AAPL",
  "securityType": "STK",
  "exchange": "SMART",
  "currency": "USD"
}
```

- **symbol**: Ticker or base identifier (e.g., `AAPL`, `ES`, `MES`)
- **securityType**: IBKR code (see table above)
- **exchange** (optional): Routing venue (e.g., `SMART`, `GLOBEX`, `CBOE`)
- **currency** (optional): Trading currency (e.g., `USD`, `EUR`)

For derivatives:

- **expiry**: `YYYY-MM-DD` format for futures/options
- **strike**: Option strike price
- **right**: `C` (call) or `P` (put)
- **multiplier**: Contract multiplier as string (e.g., `"100"` for options)

### Contract (Resolved)

IBKR's internal representation after resolution:

```python
{
  "conId": 265598,           # IBKR unique ID
  "symbol": "AAPL",
  "securityType": "STK",
  "exchange": "SMART",
  "currency": "USD",
  "localSymbol": "AAPL",
  "tradingClass": "NMS"
}
```

**Invariant**: One SymbolSpec → one Contract (cached in-memory by symbol + type + exchange + currency).

---

## Market Data

### Quote (Snapshot)

Single-point-in-time market prices:

```json
{
  "symbol": "AAPL",
  "conId": 265598,
  "bid": 150.25,
  "ask": 150.26,
  "last": 150.255,
  "bidSize": 1000.0,
  "askSize": 500.0,
  "lastSize": 100.0,
  "volume": 50000000.0,
  "timestamp": "2025-01-01T09:35:00Z",
  "source": "IBKR_REALTIME"
}
```

- **bid/ask**: Best bid/offer prices
- **last**: Last traded price (may be stale)
- **volume**: Session-to-date total volume
- **timestamp**: UTC, ISO 8601
- **source**: `IBKR_REALTIME`, `IBKR_DELAYED`, or `IBKR_FROZEN`

### Bar (OHLCV)

Historical candlestick data:

```json
{
  "symbol": "SPY",
  "time": "2025-01-01T09:30:00Z",
  "open": 650.0,
  "high": 652.5,
  "low": 649.8,
  "close": 651.5,
  "volume": 5000000.0,
  "barSize": "1 day",
  "source": "IBKR_HISTORICAL"
}
```

- **barSize**: `1 min`, `5 mins`, `1 hour`, `1 day`, etc.
- **time**: Bar close time (UTC)
- **source**: Always `IBKR_HISTORICAL`

---

## Money & Precision

### Cash Values

All monetary quantities use **Decimal precision** (2 decimal places = cents):

```python
from decimal import Decimal

# Correct
balance = Decimal("10250.50")  # $10,250.50
pnl = Decimal("-125.00")       # -$125.00

# FORBIDDEN
balance = 10250.50             # FLOAT - WRONG
```

**Rounding rule**: Round to nearest cent, ties to even (banker's rounding).

### P&L Components

```json
{
  "realizedPnL": -125.50,      # Closed positions
  "unrealizedPnL": 2500.75,    # Open positions at current mark
  "totalPnL": 2375.25          # Sum
}
```

- **Realized**: From filled and closed trades
- **Unrealized**: From open position mark-to-market
- **Total**: Always realized + unrealized

### Currency Handling

- Base currency: Defined per account (usually USD)
- **Multi-currency accounts**: All P&L converted to base currency at daily exchange rate
- **Invariant**: Never mix currencies in calculations without explicit conversion

---

## Positions

### Position (Open Lot)

Single open position in one contract:

```json
{
  "accountId": "DU123456",
  "symbol": "AAPL",
  "securityType": "STK",
  "contractId": 265598,
  "quantity": 100.0,
  "avgCost": 150.00,
  "marketValue": 15025.00,
  "unrealizedPnL": 25.00,
  "percentPnL": 0.17,
  "multiplier": 1.0,
  "currency": "USD"
}
```

- **quantity**: Positive = long, negative = short
- **avgCost**: Average entry price
- **marketValue**: quantity × current mark price
- **unrealizedPnL**: (mark - avgCost) × quantity
- **percentPnL**: (unrealizedPnL / (avgCost × abs(quantity))) × 100

**Invariant**: Position quantity is always an integer (shares/contracts).

---

## Orders

### Order Status Lifecycle

```
SUBMITTED → ACCEPTED → [PARTIAL_FILLED] → FILLED → CLOSED
                           ↓
                     CANCELLED
                           ↓
                     REJECTED
```

### OrderSpec (User Request)

```json
{
  "symbol": "AAPL",
  "securityType": "STK",
  "action": "BUY",
  "quantity": 100,
  "orderType": "MKT",
  "limitPrice": null,
  "stopPrice": null,
  "timeInForce": "DAY",
  "transmit": true
}
```

- **action**: `BUY`, `SELL`
- **orderType**: `MKT`, `LMT`, `STP`, `STP_LMT`, `MOC`, `OPG`
- **quantity**: Positive integer
- **timeInForce**: `DAY`, `GTC` (Good Till Cancel), `IOC` (Immediate Or Cancel), `FOK` (Fill Or Kill)
- **transmit**: If false, order is held locally (paper trading only)

### OrderResult (After Placement)

```json
{
  "orderId": 1001,
  "status": "ACCEPTED",
  "symbol": "AAPL",
  "quantity": 100,
  "filled": 0,
  "remaining": 100,
  "avgFillPrice": 0.0,
  "message": "Order accepted by broker"
}
```

- **status**: See lifecycle above; in paper mode, always `SIMULATED`
- **orderId**: Unique ID for this order (deterministic for same input)
- **filled/remaining**: Running totals

### OrderDetail (Full Lifecycle)

Audit log entry combining spec + result + fills:

```json
{
  "orderId": 1001,
  "symbol": "AAPL",
  "action": "BUY",
  "quantity": 100,
  "orderType": "MKT",
  "status": "FILLED",
  "filled": 100,
  "avgFillPrice": 150.25,
  "commission": 5.00,
  "timestamp": "2025-01-01T09:35:15Z",
  "config_snapshot": {
    "TRADING_MODE": "paper",
    "ORDERS_ENABLED": false
  }
}
```

**Invariant**: Every action appends immutably to audit log. No updates or deletes.

---

## Account Status

### AccountSummary (Snapshot)

High-level account overview:

```json
{
  "accountId": "DU123456",
  "currency": "USD",
  "netLiquidation": 100000.00,
  "cash": 50000.00,
  "buyingPower": 100000.00,
  "marginExcess": 5000.00,
  "maintenanceMargin": 20000.00,
  "initialMargin": 20000.00,
  "grossPositionValue": 50000.00
}
```

- **netLiquidation**: Total account value (cash + positions at mark)
- **cash**: Available cash balance
- **buyingPower**: Available cash for new purchases (2×cash on margin)
- **margin\***: Requirements and excess for regulatory compliance
- **grossPositionValue**: Absolute value of all positions

---

## Timeframes & Timestamps

### Convention

All timestamps are **UTC** in **ISO 8601** format:

- `2025-01-01T09:30:00Z` (with Z = UTC)
- `2025-01-01T09:30:00+00:00` (with explicit offset)

**Invariant**: Never store local time. Convert at display time only.

### Market Hours (US Equities)

- **Regular**: 9:30 AM – 4:00 PM ET
- **Pre-market**: 4:00 AM – 9:30 AM ET
- **After-hours**: 4:00 PM – 8:00 PM ET

### Expiry Formats

Futures/options use `YYYY-MM-DD`:

- `2025-01-17` (January 17, 2025)

---

## Fees & Commissions

### Commission Model

Commission is charged per order and recorded in audit log:

```json
{
  "orderId": 1001,
  "commission": 5.00,
  "commission_currency": "USD"
}
```

- Subtracted from realized P&L
- Never charged for simulated orders
- Varies by account and product type

---

## Examples: Common Workflows

### Buy 100 AAPL at Market

```python
spec = SymbolSpec(symbol="AAPL", securityType="STK")
result = await client.place_order(
    symbol_spec=spec,
    action="BUY",
    quantity=100,
    order_type="MKT"
)
# In paper mode: status = SIMULATED
# In live mode (if enabled): status = ACCEPTED, then FILLED
```

### Get Current Quote

```python
quote = await client.get_quote(symbol_spec=spec)
# Returns bid, ask, last, volume, timestamp
```

### Get Account Status

```python
summary = await client.get_account_summary()
positions = await client.get_positions()
# summary.netLiquidation, positions[0].quantity, etc.
```

### Check Order Status

```python
order_detail = await client.get_order_status(order_id=1001)
# Shows filled quantity, avg fill price, commission
```
