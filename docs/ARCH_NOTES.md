# Architecture Notes

## Overview

This document captures key architectural decisions, deviations from the plan, and technical rationale.

## Current Phase: 0 (Repo Setup)

### Decision: Python + FastAPI + ib_insync

- **Rationale**: ib_insync is the most mature Python wrapper for IBKR API. FastAPI provides modern async HTTP layer with built-in OpenAPI.
- **Dependencies**: Listed in `pyproject.toml` or `requirements.txt`.

### Decision: Dedicated IBKR Executor Thread

- **Rationale**: ib_insync expects an asyncio event loop in the thread where it runs; a dedicated single-thread executor initializes its own loop to avoid missing event loop errors in the default executor.
- **Pattern**: All ib_insync operations are funneled through the IBKR executor.

### Decision: Pydantic Models for Schema Compliance

- **Rationale**: Schema in `.context/SCHEMAS.md` is serialized to Pydantic models for full IDE support, type checking, and JSON validation.
- **Pattern**: Every top-level schema in `.context/SCHEMAS.md` gets a Pydantic model in the appropriate module:
  - `ibkr_core/models.py` for core data types (SymbolSpec, Quote, Bar, AccountSummary, Position, etc.)
  - `api/schemas.py` for HTTP request/response wrappers if needed
  - Tests validate that Pydantic serialization matches the schema.

### Decision: Safety Rails in Phase 0

- **Config-based gating**: `TRADING_MODE` (paper|live) and `ORDERS_ENABLED` (false|true) are loaded at startup.
- **Enforcement**: Any order placement function raises `TradingDisabledError` if `ORDERS_ENABLED=false`.
- **Design rationale**: Prevent accidental live trades during development. Paper mode is the default.

### Decision: MCP Tool Layer is Thin

- **Rationale**: MCP tools only translate JSON input → HTTP call → response. No business logic in `mcp_server/`.
- **Error handling**: MCP errors are mapped from HTTP error responses; structured JSON → MCP error format.

### Decision: Contract Resolution Cache

- **In-memory cache** (keyed by symbol + security_type + exchange + currency).
- **Rationale**: Reduces IBKR API calls during development. No persistence (optional for Phase 8).

## Deviations from Plan

(None yet. Will update as work progresses.)

## Known Limitations

1. **PnL timeframes**: Currently restricted to simple realized/unrealized per position. Custom timeframes deferred to Phase 8.
2. **Order types**: Phase 4 supports only MKT, LMT, STP, STP_LMT. Advanced order types (algos, etc.) deferred.
3. **Simulation**: Phase 8 includes optional mock exchange; currently no simulation backend.
4. **Historical data**: Phase 2 uses simple ib_insync API; no advanced bar-rolling or gap-fill logic.

## API Error Model

```json
{
  "error_code": "...",
  "message": "...",
  "details": {...}
}
```

Standard HTTP status codes:
- `200`: Success
- `400`: Bad request (invalid schema, missing fields)
- `401`: Unauthorized (auth failure)
- `403`: Forbidden (ORDERS_ENABLED=false when order is attempted)
- `500`: Internal server error
- `503`: Service unavailable (IBKR connection down)

## Environment Variables

- `IBKR_GATEWAY_HOST` (default: `127.0.0.1`): IBKR Gateway/TWS hostname
- `IBKR_GATEWAY_PORT` (default: `4001` or `7497` for paper/live): IBKR Gateway port
- `TRADING_MODE` (default: `paper`): `paper` or `live`
- `ORDERS_ENABLED` (default: `false`): `true` to enable order placement
- `API_PORT` (default: `8000`): REST API listening port
- `LOG_LEVEL` (default: `INFO`): Logging level

## Logging Strategy

- All request/response pairs logged with correlation ID (UUID).
- Timing information included for performance monitoring.
- Sensitive fields (account IDs, order IDs) logged but redacted in certain contexts for security.

## Future Enhancements

1. **Phase 8 Monitoring**: Add Prometheus metrics, custom dashboards.
2. **Simulation**: Build mock IBKR exchange for strategy backtesting.
3. **Persistence**: Add database layer for order history, audit trail.
4. **Advanced orders**: Support algos, conditional orders.
5. **WebSocket stream**: Replace polling with streaming market data.
