# Safety Checklist for Live Trading

This document provides a comprehensive checklist for safely enabling and testing live trading with the IBKR Gateway system.

## ⚠️ Important Disclaimer

**This system can place REAL trades with REAL money when configured for live trading.**

We **strongly recommend** staying in paper trading mode for all testing and development. Only enable live trading after thoroughly testing in paper mode and fully understanding the system's behavior.

---

## Pre-Deployment Checklist

### 1. Paper Trading Validation

Before considering live trading, complete ALL of the following in paper mode:

- [ ] Successfully connect to IBKR Gateway (paper mode)
- [ ] Fetch market data for at least 5 different symbols
- [ ] Retrieve account summary and positions
- [ ] Preview at least 10 different order types (MKT, LMT, STP, etc.)
- [ ] Place and fill at least 5 simulated orders
- [ ] Cancel pending simulated orders
- [ ] Test bracket orders with take profit and stop loss
- [ ] Test trailing stop orders (both dollar amount and percentage)
- [ ] Verify MOC (market-on-close) and OPG (opening) orders
- [ ] Run full integration test suite: `pytest -m integration`
- [ ] Review all test results for failures or warnings

### 2. Code Review

- [ ] Review all order placement code in `ibkr_core/orders.py`
- [ ] Verify safety checks in `ibkr_core/config.py`
- [ ] Understand the dual-toggle protection mechanism
- [ ] Review error handling in `api/errors.py`
- [ ] Confirm order validation logic is working correctly
- [ ] Check that `SIMULATED` status is returned when `ORDERS_ENABLED=false`

### 3. Configuration Validation

- [ ] `.env` file is configured correctly (not using `.env.example`)
- [ ] `TRADING_MODE` is explicitly set
- [ ] `ORDERS_ENABLED` is explicitly set
- [ ] `LIVE_TRADING_OVERRIDE_FILE` path is correct (if using live mode)
- [ ] No credentials or API keys are committed to version control
- [ ] API authentication (`API_KEY`) is enabled if exposing the API externally

### 4. Risk Limits Setup

Before enabling live trading, set strict limits in your code or configuration:

- [ ] **Maximum order size**: Define max shares/contracts per order
- [ ] **Maximum notional value**: Define max dollar amount per order
- [ ] **Daily loss limit**: Define max acceptable loss per day
- [ ] **Position size limit**: Define max total position size
- [ ] **Symbols whitelist**: Restrict trading to specific approved symbols
- [ ] **Time restrictions**: Define trading hours (avoid extended hours initially)

**Example limit checks to add to your code:**

```python
MAX_ORDER_SIZE = 10  # Max 10 shares per order
MAX_NOTIONAL = 1000  # Max $1000 per order
ALLOWED_SYMBOLS = ["AAPL", "SPY", "QQQ"]  # Whitelist

def validate_order_limits(symbol, quantity, price):
    if symbol not in ALLOWED_SYMBOLS:
        raise ValueError(f"Symbol {symbol} not in whitelist")
    if quantity > MAX_ORDER_SIZE:
        raise ValueError(f"Quantity {quantity} exceeds max {MAX_ORDER_SIZE}")
    notional = quantity * price
    if notional > MAX_NOTIONAL:
        raise ValueError(f"Notional ${notional} exceeds max ${MAX_NOTIONAL}")
```

---

## Live Trading Enablement Protocol

### Phase 1: Live Mode with Orders Disabled

Test connection to live Gateway without order placement enabled:

1. [ ] Set `TRADING_MODE=live` in `.env`
2. [ ] Keep `ORDERS_ENABLED=false` in `.env`
3. [ ] Start IBKR Gateway in LIVE mode
4. [ ] Run healthcheck: `python -m ibkr_core.healthcheck`
5. [ ] Verify connection shows "live" mode
6. [ ] Fetch real-time market data
7. [ ] Check account summary (verify it shows your real account)
8. [ ] Preview orders (should work in read-only mode)
9. [ ] **Attempt** to place an order (should return `SIMULATED` status)
10. [ ] Verify no real orders appear in IBKR account portal

### Phase 2: Enable Orders with Small Test

Enable order placement with minimal risk:

1. [ ] Read ALL safety documentation in README and this checklist
2. [ ] Set `TRADING_MODE=live` in `.env`
3. [ ] Set `ORDERS_ENABLED=true` in `.env`
4. [ ] Create override file: `touch ~/ibkr_live_trading_confirmed.txt`
5. [ ] Set `LIVE_TRADING_OVERRIDE_FILE=~/ibkr_live_trading_confirmed.txt` in `.env`
6. [ ] Restart API server
7. [ ] **CRITICAL**: Use a liquid stock (e.g., SPY, AAPL)
8. [ ] **CRITICAL**: Use a limit order FAR from market price
   - Example: If SPY is trading at $450, place buy limit at $400 (won't fill)
9. [ ] Place the test order
10. [ ] Verify order appears in IBKR account portal with status "SUBMITTED"
11. [ ] Immediately cancel the test order: `cancel_order(order_id)`
12. [ ] Verify cancellation in IBKR account portal

### Phase 3: Gradual Ramp-Up

If Phase 2 succeeded, gradually increase order size and complexity:

1. [ ] Place small market order (1 share of liquid stock)
2. [ ] Monitor fill price and execution
3. [ ] Close position immediately
4. [ ] Review P&L and commissions
5. [ ] Test stop loss with small position
6. [ ] Test take profit with small position
7. [ ] Test bracket order with minimal size
8. [ ] Verify all order types work as expected

---

## Monitoring Requirements

### Real-Time Monitoring

When live trading is enabled, you MUST have:

- [ ] **IBKR Account Portal**: Open in browser for real-time order visibility
- [ ] **Position monitoring**: Check positions frequently
- [ ] **P&L tracking**: Monitor unrealized/realized P&L
- [ ] **Order status checks**: Verify all orders behave as expected
- [ ] **Log monitoring**: Watch application logs for errors or warnings

### Automated Alerts

Consider setting up alerts for:

- [ ] Order placement events
- [ ] Order fills
- [ ] Order rejections
- [ ] Position limit breaches
- [ ] Loss limit breaches
- [ ] System errors or disconnections

---

## Testing Protocol Summary

### Paper → Small Live → Production

**Never skip steps. Always progress in order:**

1. **Weeks in Paper Mode**
   - Test ALL functionality thoroughly
   - Run automated tests daily
   - Understand every error and edge case

2. **Days in Live Mode (Orders Disabled)**
   - Verify real-time data works correctly
   - Monitor account in read-only mode
   - Ensure no accidental order placement

3. **Hours with Small Live Orders**
   - Use limit orders far from market
   - Test with 1-10 shares maximum
   - Cancel before fills if possible

4. **Gradual Production Ramp-Up**
   - Increase size slowly over weeks
   - Monitor every trade manually
   - Keep detailed logs of all activity

---

## Emergency Procedures

### Kill Switch

If something goes wrong, immediately:

1. **Stop the API server**: `Ctrl+C` or kill the process
2. **Close IBKR Gateway**: Shut down TWS/Gateway application
3. **Flatten positions in IBKR portal**: Manually close all positions if needed
4. **Disable orders**: Set `ORDERS_ENABLED=false` in `.env`
5. **Review logs**: Check application logs for root cause
6. **Contact IBKR support**: If positions or orders are unexpected

### Common Issues

| Issue | Solution |
|-------|----------|
| Orders not being placed | Check `ORDERS_ENABLED` setting, verify override file exists |
| Unexpected fills | Use limit orders far from market during testing |
| Connection errors | Verify IBKR Gateway is running, check port settings |
| Permission errors | Check IBKR account has required market data subscriptions |
| Duplicate orders | Review client_order_id handling, check for retries |

---

## Recommended Limits (Conservative)

For initial live trading, we recommend these conservative limits:

- **Max order size**: 10 shares (stocks) or 1 contract (futures/options)
- **Max notional per order**: $1,000
- **Max daily notional**: $5,000
- **Max open positions**: 3 concurrent positions
- **Symbols**: Highly liquid stocks/ETFs only (SPY, QQQ, AAPL, MSFT, etc.)
- **Order types**: Start with LMT orders only, add others gradually
- **Time-in-force**: DAY only (avoid GTC initially)
- **Outside RTH**: Disabled (avoid extended hours trading initially)

Increase limits gradually as you gain confidence and verify system behavior.

---

## Documentation to Review

Before enabling live trading, read and understand:

- [ ] Main [README.md](../README.md) - Safety section
- [ ] [API Documentation](../api/API.md) - SIMULATED status behavior
- [ ] [Phase Plan](./ PHASE_PLAN.md) - Safety design decisions
- [ ] `.env.example` - Configuration safety comments
- [ ] `ibkr_core/config.py` - Safety validation logic
- [ ] `ibkr_core/orders.py` - Order placement implementation

---

## Final Pre-Live Checklist

Before enabling live order placement for the first time:

- [ ] I have tested EVERYTHING in paper mode for at least 1 week
- [ ] I understand that REAL money is at risk
- [ ] I have set strict position and risk limits
- [ ] I will start with TINY orders (1-10 shares max)
- [ ] I will use limit orders FAR from market price initially
- [ ] I have the IBKR account portal open for monitoring
- [ ] I am prepared to manually close positions if needed
- [ ] I will not leave the system running unattended initially
- [ ] I have read and understood ALL safety documentation
- [ ] I accept full responsibility for any trades placed

**If you cannot check ALL boxes above, DO NOT enable live trading.**

---

## Additional Resources

- **IBKR API Documentation**: https://interactivebrokers.github.io/tws-api/
- **IBKR Paper Trading**: https://www.interactivebrokers.com/en/index.php?f=1286
- **ib_insync Documentation**: https://ib-insync.readthedocs.io/
- **IBKR Support**: https://www.interactivebrokers.com/en/support/contact.php

---

**Remember**: When in doubt, stay in paper mode. There is no rush to enable live trading.
