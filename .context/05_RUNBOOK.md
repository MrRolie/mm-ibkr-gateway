# 05_RUNBOOK.md: Operational Workflows & Playbooks

## Quick Reference

| Task | Command | Notes |
|------|---------|-------|
| Health check | `poetry run ibkr-gateway healthcheck` | No side effects |
| Run demo | `poetry run ibkr-gateway demo` | Paper mode only, 5 min |
| Start API | `poetry run ibkr-gateway start-api` | Port 8000 by default |
| Run tests | `poetry run pytest tests/ -v` | All 635 tests, ~30 sec |
| Query audit | `sqlite3 data/audit.db "SELECT * FROM audit_log LIMIT 10"` | View order history |
| View logs | `tail -f data/logs/app.log` | Structured JSON logs |

---

## Startup Sequence

### Prerequisites

- IBKR Gateway or TWS running on port 4002 (paper or live)
- Python 3.10+ with Poetry
- `.env` file with configuration

### Startup Steps

```bash
# 1. Verify environment
cat .env | grep -E "TRADING_MODE|ORDERS_ENABLED|IBKR_GATEWAY_HOST"
# Expected output:
# TRADING_MODE=paper
# ORDERS_ENABLED=false
# IBKR_GATEWAY_HOST=localhost

# 2. Verify IBKR Gateway is accessible
poetry run ibkr-gateway healthcheck
# Expected: [OK] Connection established, [OK] Trading mode: PAPER, [OK] Orders enabled: False

# 3. (Optional) Run quick sanity check
poetry run pytest tests/test_config.py -v
# Expected: All tests pass

# 4. Start API server
poetry run ibkr-gateway start-api
# Expected: "Uvicorn running on http://0.0.0.0:8000"

# 5. In another terminal, test API health
curl http://localhost:8000/health
# Expected: {"status": "healthy", "serverTime": "2025-01-01T...", "tradingMode": "paper", ...}
```

---

## Regular Operations

### Daily Checklist

```bash
# Morning (before trading)
1. ibkr-gateway healthcheck          # Verify connection
2. curl http://localhost:8000/health # Verify API
3. Review overnight audit log:
   sqlite3 data/audit.db "SELECT * FROM audit_log WHERE date(timestamp) = date('now')"
4. Check for position mismatches:
   curl http://localhost:8000/api/account/positions | jq '.'
5. Verify TRADING_MODE is still "paper" (or your intended mode)
   cat .env | grep TRADING_MODE

# End of day
1. Export order history:
   poetry run python -m scripts.export_order_history > orders_$(date +%Y%m%d).json
2. Reconcile fills with IBKR account portal (manual spot-check)
3. Archive audit log (optional):
   cp data/audit.db data/audit_backup_$(date +%Y%m%d).db
```

### Market Data Queries

```bash
# Get current AAPL quote
curl "http://localhost:8000/api/market/quote?symbol=AAPL&securityType=STK" | jq '.'

# Get 5-day historical data for SPY
curl -X POST http://localhost:8000/api/market/historical \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "SPY",
    "securityType": "ETF",
    "period": "1 day",
    "durationStr": "5 D"
  }' | jq '.'

# Get account summary
curl http://localhost:8000/api/account/summary | jq '.'

# Get all positions
curl http://localhost:8000/api/account/positions | jq '.'

# Get P&L breakdown
curl http://localhost:8000/api/account/pnl | jq '.'
```

### Order Workflows

#### Preview Order (Safe, No Side Effects)

```bash
curl -X POST http://localhost:8000/api/orders/preview \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "AAPL",
    "securityType": "STK",
    "action": "BUY",
    "quantity": 10,
    "orderType": "MKT"
  }' | jq '.'

# Expected response (in paper mode):
# {
#   "orderId": <deterministic_id>,
#   "status": "SIMULATED",
#   "symbol": "AAPL",
#   "quantity": 10,
#   "filled": 10,
#   "message": "Simulated order in paper mode"
# }
```

#### Place Order (Gated in Live Mode)

```bash
# In paper mode or with ORDERS_ENABLED=false:
curl -X POST http://localhost:8000/api/orders/place \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "AAPL",
    "securityType": "STK",
    "action": "BUY",
    "quantity": 10,
    "orderType": "LMT",
    "limitPrice": 150.00
  }' | jq '.'

# Expected response:
# {
#   "orderId": 1001,
#   "status": "SIMULATED",
#   "symbol": "AAPL",
#   "quantity": 10,
#   "filled": 0,
#   "remaining": 10
# }
```

#### Check Order Status

```bash
curl http://localhost:8000/api/orders/1001/status | jq '.'

# Response includes filled quantity, avg fill price, commission
```

#### Cancel Order

```bash
curl -X POST http://localhost:8000/api/orders/1001/cancel | jq '.'

# Response: {"orderId": 1001, "status": "CANCELLED", "message": "..."}
```

---

## Failure Scenarios & Recovery

### Scenario 1: IBKR Gateway Disconnected

**Symptom**:

```
$ ibkr-gateway healthcheck
[ERROR] IBKR Gateway not detected on localhost:4002
```

**Root Cause**: TWS/Gateway not running or API disabled.

**Recovery**:

```bash
# 1. Restart IBKR Gateway (manual application)
# 2. Verify API settings enabled (Configure → API → Settings)
# 3. Re-run healthcheck
ibkr-gateway healthcheck

# 4. If still failing, check firewall
lsof -i :4002  # Should show IBKR process listening

# 5. Clear in-memory contract cache (no persistence impact)
poetry run python -c "from ibkr_core.contracts import clear_cache; clear_cache()"

# 6. Restart API server
```

**Prevention**: Monitor connection status in production via `/health` endpoint.

---

### Scenario 2: Order Not Found

**Symptom**:

```
$ curl http://localhost:8000/api/orders/9999/status
{"error": "Order 9999 not found"}
```

**Root Cause**: Order ID doesn't exist, or order from previous session (not persisted).

**Recovery**:

```bash
# 1. Verify order was actually placed
sqlite3 data/audit.db "SELECT * FROM audit_log WHERE event_type='ORDER_PLACED'"

# 2. Check order history table
sqlite3 data/audit.db "SELECT * FROM order_history WHERE order_id=9999"

# 3. Query IBKR directly via API for recent orders
# (Note: IBKR API may not return old orders)

# 4. If order exists in audit log but not IBKR:
#    - Order may have been cancelled by broker
#    - Order may have been filled and closed
#    - Check audit log for ORDER_FILLED or ORDER_CANCELLED event
```

---

### Scenario 3: Position Mismatch

**Symptom**:

```
# Your code shows: 100 AAPL
# IBKR account shows: 95 AAPL
```

**Root Cause**: Fill not captured, duplicate order, or manual adjustment on broker side.

**Recovery**:

```bash
# 1. Immediate: Halt trading (set ORDERS_ENABLED=false)

# 2. Get current positions from IBKR
curl http://localhost:8000/api/account/positions | jq '.[] | select(.symbol == "AAPL")'

# 3. Check audit log for all fills on AAPL
sqlite3 data/audit.db "
SELECT timestamp, event_type, json_extract(event_data, '$.filled') as filled
FROM audit_log
WHERE json_extract(event_data, '$.symbol') = 'AAPL'
AND event_type IN ('ORDER_PLACED', 'ORDER_FILLED')
ORDER BY timestamp DESC
"

# 4. Manual reconciliation
# If missing a fill in audit log:
# → Insert manual audit entry (ideally with explanation)

# 5. Update order_history to match IBKR
sqlite3 data/audit.db "
UPDATE order_history SET quantity = 95 WHERE symbol = 'AAPL'
"

# 6. Resume trading
```

**Prevention**: Run nightly reconciliation script (see `scripts/reconcile.py`).

---

### Scenario 4: Stale Contract Cache

**Symptom**:

```
# Symbol DEAD (delisted) still resolves, causing orders to fail at IBKR
```

**Root Cause**: Contract cached at session start; symbol delisted intraday.

**Recovery**:

```bash
# 1. Clear contract cache
# (Cache is in-memory; restart service to clear)
# OR
poetry run python -c "from ibkr_core.contracts import clear_cache; clear_cache()"

# 2. Retry order
# Next resolution will fetch fresh contract from IBKR

# 3. If still failing, symbol is truly delisted
# → Order will be rejected by IBKR with clear error
```

**Prevention**:

- Restart service daily during non-trading hours
- Monitor resolution errors in logs

---

### Scenario 5: Config Mismatch (Live Trading Enabled Unintentionally)

**Symptom**:

```
# Orders now executing in live account instead of simulated!
$ ibkr-gateway healthcheck
[WARNING] TRADING_MODE=live, ORDERS_ENABLED=true, live trading ENABLED
```

**Root Cause**: `.env` was modified, or override file was accidentally created.

**Recovery**:

```bash
# IMMEDIATE (Stop the bleeding)
# 1. Delete override file
rm ~/ibkr_live_trading_confirmed.txt

# 2. Edit .env
# Set ORDERS_ENABLED=false
# OR set TRADING_MODE=paper

# 3. Restart API server

# 4. Verify
ibkr-gateway healthcheck

# 5. Review audit log for unintended trades in last hour
sqlite3 data/audit.db "
SELECT timestamp, json_extract(event_data, '$.symbol') as symbol,
       json_extract(event_data, '$.action') as action,
       json_extract(event_data, '$.quantity') as qty
FROM audit_log
WHERE event_type='ORDER_PLACED'
AND datetime(timestamp) > datetime('now', '-1 hour')
ORDER BY timestamp DESC
"

# 6. Contact broker to cancel unexecuted orders
# 7. Review and close unwanted positions
# 8. Update .env safeguards
```

---

## Maintenance Tasks

### Weekly

```bash
# 1. Backup audit database
cp data/audit.db data/audit_backup_$(date +%Y%m%d).db

# 2. Check disk space
du -h data/

# 3. Review error logs
grep ERROR data/logs/app.log | tail -20

# 4. Verify API response times
curl -w "@curl-format.txt" -o /dev/null -s http://localhost:8000/health
```

### Monthly

```bash
# 1. Export full audit log for analysis
sqlite3 data/audit.db ".mode json" "SELECT * FROM audit_log LIMIT 100000" > audit_export_$(date +%Y%m).json

# 2. Run full test suite (including integration tests)
poetry run pytest tests/ -v --tb=short

# 3. Review CHANGELOG and update `.context/` if needed

# 4. Check for dependency updates
poetry update --dry-run

# 5. Audit active positions and P&L
curl http://localhost:8000/api/account/pnl | jq '.totalPnL'
```

### Quarterly

```bash
# 1. Full reconciliation with IBKR account
# (Manual comparison of positions, cash, P&L)

# 2. Review and prune old audit log entries (optional archive)
sqlite3 data/audit.db "DELETE FROM audit_log WHERE date(timestamp) < date('now', '-1 year')"

# 3. Security audit: Review `.env` and API keys
# Ensure no secrets are in git history
git log --all --full-history -- '.env' '*secret*' '*key*'

# 4. Update documentation if any changes
# Review `.context/` for accuracy
```

---

## Logging & Observability

### Log Levels

- **DEBUG**: Detailed execution, contract cache hits, retry logic
- **INFO**: Order placements, account updates, normal operations
- **WARNING**: Config warnings (live mode enabled), minor issues
- **ERROR**: Failed connections, order rejections, reconciliation mismatches
- **CRITICAL**: IBKR Gateway unreachable, unrecoverable state

### Accessing Logs

```bash
# Structured JSON logs (production format)
tail -f data/logs/app.log | jq '.'

# Filter by correlation ID (trace single request)
grep -r "req-550e8400-e29b-41d4-a716-446655440000" data/logs/

# Filter by event type
grep '"event_type":"ORDER_PLACED"' data/logs/app.log

# View last 100 lines of errors
grep '"level":"ERROR"' data/logs/app.log | tail -100 | jq '.message'
```

### Metrics

```bash
# Get current metrics (via HTTP endpoint)
curl http://localhost:8000/api/metrics | jq '.'

# Expected metrics:
# - trades_placed: Total orders attempted
# - trades_filled: Total fills received
# - trades_cancelled: Total cancellations
# - avg_fill_latency_ms: Average time to fill
```

---

## Troubleshooting Checklist

```
[ ] Service starts without errors?
    → poetry run ibkr-gateway healthcheck

[ ] IBKR Gateway reachable on port 4002?
    → lsof -i :4002

[ ] API responding?
    → curl http://localhost:8000/health

[ ] Database writable?
    → sqlite3 data/audit.db "SELECT COUNT(*) FROM audit_log"

[ ] Config valid (no typos)?
    → cat .env | grep -E "TRADING_MODE|ORDERS_ENABLED"

[ ] No stale contracts affecting orders?
    → Clear cache and retry: poetry run python -c "from ibkr_core.contracts import clear_cache; clear_cache()"

[ ] Logs readable (no permission errors)?
    → ls -la data/logs/

[ ] API key configured (if external access)?
    → cat .env | grep API_KEY

[ ] Override file exists (if live trading)?
    → ls -la ~/ibkr_live_trading_confirmed.txt

[ ] Audit log consistent?
    → sqlite3 data/audit.db "SELECT COUNT(*) FROM audit_log WHERE id IS NOT NULL"
```

---

## Emergency Procedures

### Halt All Trading (Immediate)

```bash
# 1. Kill API server (Ctrl+C in terminal)

# 2. Set ORDERS_ENABLED=false in .env
echo "ORDERS_ENABLED=false" > .env.tmp
cat .env | grep -v "ORDERS_ENABLED" >> .env.tmp
mv .env.tmp .env

# 3. Delete override file (if live trading was enabled)
rm -f ~/ibkr_live_trading_confirmed.txt

# 4. Restart API
poetry run ibkr-gateway start-api

# 5. Verify
ibkr-gateway healthcheck
# Expected: [OK] Orders enabled: False
```

### Contact Broker to Close Unwanted Positions

```bash
# 1. Get current positions
curl http://localhost:8000/api/account/positions | jq '.[].symbol'

# 2. Call IBKR support or use TWS/Gateway to close
# (Manual action in broker UI)

# 3. Monitor audit log for fills
sqlite3 data/audit.db "SELECT * FROM audit_log WHERE event_type='ORDER_FILLED' ORDER BY timestamp DESC LIMIT 5"
```

---

## Summary

**Safe by default**: All operations in paper mode are simulated.

**Always verify**:

- TRADING_MODE before running
- Override file doesn't exist unless intentional
- Audit log for unexpected orders

**When in doubt**: Delete override file, set ORDERS_ENABLED=false, restart, and investigate.
