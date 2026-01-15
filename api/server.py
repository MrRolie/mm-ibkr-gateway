"""
IBKR Gateway REST API Server.

FastAPI application providing REST endpoints for:
- Health check
- Market data (quotes, historical bars)
- Account status (summary, positions, PnL)
- Order management (preview, place, cancel, status)

Usage:
    uvicorn api.server:app --host 0.0.0.0 --port 8000

    # With auto-reload for development:
    uvicorn api.server:app --reload
"""

import asyncio
# Ensure a default event loop exists at module import time.
# Some third-party modules (e.g., eventkit) call asyncio.get_event_loop()
# during import which raises RuntimeError if no loop has been set in the
# main thread. Creating and setting a new event loop here prevents that
# import-time failure.
try:
    asyncio.get_event_loop()
except RuntimeError:
    _loop = asyncio.new_event_loop()
    asyncio.set_event_loop(_loop)

import contextvars
import logging
from typing import List, Optional

from pathlib import Path as FilePath

from fastapi import Depends, FastAPI, Path
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from api.auth import verify_api_key
from api.dependencies import (
    IBKRClientManager,
    RequestContext,
    get_client_manager,
    get_ibkr_executor,
    get_request_context,
    get_request_timeout,
    lifespan_context,
    log_request,
)
from api.errors import (
    APIError,
    ErrorCode,
    ErrorResponse,
    api_error_handler,
    general_exception_handler,
    map_ibkr_exception,
)
from api.admin import router as admin_router
from api.middleware import CorrelationIdMiddleware, TimeWindowMiddleware, TradingDisabledMiddleware
from api.models import (
    AccountPnl,
    AccountSummary,
    CancelResult,
    HealthResponse,
    HistoricalBarsRequest,
    HistoricalBarsResponse,
    OrderPreview,
    OrderPreviewRequest,
    OrderRequest,
    OrderResult,
    OrderStatus,
    PositionsResponse,
    Quote,
    QuoteRequest,
)
from ibkr_core.config import get_config
from ibkr_core.logging_config import configure_logging
from ibkr_core.metrics import get_metrics
from ibkr_core.schedule import get_window_status

# Configure structured logging with correlation IDs
configure_logging()
logger = logging.getLogger(__name__)


# =============================================================================
# FastAPI Application
# =============================================================================


app = FastAPI(
    title="IBKR Gateway API",
    description=(
        "REST API for Interactive Brokers Gateway integration.\n\n"
        "Provides endpoints for market data, account status, and order management.\n\n"
        "**Authentication**: If API_KEY environment variable is set, all requests "
        "must include the X-API-Key header."
    ),
    version="0.1.0",
    lifespan=lifespan_context,
    responses={
        401: {"model": ErrorResponse, "description": "Unauthorized"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
)

# Add CORS middleware for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add correlation ID middleware for request tracking
# Note: Middlewares are executed in reverse order of addition,
# so this will run BEFORE CORS middleware
app.add_middleware(CorrelationIdMiddleware)

# Add time-window enforcement middleware
# This ensures API is only accessible during configured RUN_WINDOW_*
app.add_middleware(TimeWindowMiddleware)

# Add trading disabled middleware
# This checks mm-control guard file/toggle store for order endpoints
app.add_middleware(TradingDisabledMiddleware)

# Register exception handlers
app.add_exception_handler(APIError, api_error_handler)
app.add_exception_handler(Exception, general_exception_handler)

# Include admin router for trading control operations
app.include_router(admin_router)

# =============================================================================
# Operator UI Static Files
# =============================================================================

# Path to static files directory
_static_dir = FilePath(__file__).parent / "static"

# Mount static files for UI assets (CSS, JS)
if _static_dir.exists():
    app.mount("/ui/static", StaticFiles(directory=str(_static_dir)), name="ui-static")


@app.get("/ui", tags=["UI"], summary="Operator Dashboard", include_in_schema=False)
async def serve_operator_ui():
    """Serve the operator dashboard UI."""
    index_path = _static_dir / "index.html"
    if index_path.exists():
        return FileResponse(str(index_path), media_type="text/html")
    return {"error": "UI not found", "message": "Operator UI files not installed"}


# =============================================================================
# Helper Functions
# =============================================================================


async def execute_ibkr_operation(
    client_manager: IBKRClientManager,
    operation: callable,
    ctx: RequestContext,
    timeout_s: float = None,
    *args,
    **kwargs,
):
    """
    Execute an IBKR operation with proper error handling and timeout.

    Args:
        client_manager: IBKR client manager
        operation: Function to call with client
        ctx: Request context for logging
        timeout_s: Optional timeout override
        *args, **kwargs: Arguments to pass to operation

    Returns:
        Result of the operation

    Raises:
        APIError: On failure
    """
    if timeout_s is None:
        timeout_s = get_request_timeout()

    try:
        # Get connected client
        client = await client_manager.get_client()

        # Run the blocking ibkr operation in thread pool with timeout
        loop = asyncio.get_running_loop()
        ctx_vars = contextvars.copy_context()
        result = await asyncio.wait_for(
            loop.run_in_executor(
                get_ibkr_executor(),
                # Preserve contextvars (e.g., correlation id) while keeping request ctx for logging
                lambda: ctx_vars.run(operation, client, *args, **kwargs),
            ),
            timeout=timeout_s,
        )

        log_request(ctx, status="success")
        return result

    except asyncio.TimeoutError:
        log_request(ctx, status="timeout", error="Request timed out")
        raise APIError(
            ErrorCode.TIMEOUT,
            f"Request timed out after {timeout_s}s",
            status_code=504,
        )
    except APIError:
        raise
    except Exception as e:
        log_request(ctx, status="error", error=str(e))
        raise map_ibkr_exception(e)


# =============================================================================
# Health Check
# =============================================================================


@app.get(
    "/health",
    response_model=HealthResponse,
    tags=["Health"],
    summary="Health check",
    description="Check API and IBKR connection status",
)
async def health_check(
    client_manager: IBKRClientManager = Depends(get_client_manager),
):
    """
    Health check endpoint.

    Returns:
        - status: 'ok' if connected, 'degraded' if not
        - ibkr_connected: Boolean connection status
        - server_time: IBKR server time if connected
        - trading_mode: Current trading mode
        - orders_enabled: Whether orders are enabled
    """
    config = get_config()
    server_time = None
    ibkr_connected = False

    try:
        client = await client_manager.get_client(timeout=5)
        ibkr_connected = client.is_connected
    except Exception as e:
        logger.warning(f"Health check: IBKR not connected - {e}")
        ibkr_connected = False
    else:
        if ibkr_connected:
            try:
                loop = asyncio.get_running_loop()
                server_time_dt = await loop.run_in_executor(
                    get_ibkr_executor(),
                    lambda: client.get_server_time(timeout_s=2.0),
                )
                server_time = server_time_dt.isoformat()
            except Exception as e:
                logger.warning(f"Health check: server time unavailable - {e}")

    status = "ok" if ibkr_connected else "degraded"

    return HealthResponse(
        status=status,
        ibkr_connected=ibkr_connected,
        server_time=server_time,
        trading_mode=config.trading_mode,
        orders_enabled=config.orders_enabled,
    )


@app.get(
    "/control/status",
    tags=["Control"],
    summary="Trading control status",
    description="Get current trading control status from mm-control (guard file, toggles, TTL)",
)
async def get_control_status():
    """
    Get trading control status from mm-control.

    Returns toggle status including:
        - trading_enabled: Whether trading is currently enabled
        - disabled_at: Timestamp when trading was disabled (if applicable)
        - disabled_by: User who disabled trading
        - disabled_reason: Reason for disabling
        - expires_at: TTL expiry timestamp (if applicable)
        - time_until_expiry_seconds: Seconds until auto-revert (if applicable)

    Returns:
        dict: Trading control status from mm-control
    """
    try:
        from mm_control import get_toggle_status

        status = get_toggle_status()
        return status
    except ImportError:
        logger.warning("mm-control not installed - control status unavailable")
        return {
            "error": "mm-control not installed",
            "trading_enabled": None,
            "disabled_at": None,
            "disabled_by": None,
            "disabled_reason": None,
            "expires_at": None,
        }


# =============================================================================
# Schedule Endpoint
# =============================================================================


@app.get(
    "/schedule",
    tags=["Health"],
    summary="Get schedule status",
    description="Check if services are within the configured run window",
)
async def schedule_status():
    """
    Schedule status endpoint.

    Returns the current schedule configuration and whether we're
    within the run window. Useful for the Pi to check if the
    execution node should be active.
    """
    return get_window_status()


# =============================================================================
# Metrics Endpoint
# =============================================================================


@app.get(
    "/metrics",
    tags=["Health"],
    summary="Get application metrics",
    description=(
        "Get all application metrics including counters, histograms, and gauges. "
        "Metrics include API request counts/latencies, IBKR operation stats, and connection status."
    ),
)
async def get_application_metrics():
    """
    Get application metrics.

    Returns:
        - uptime_seconds: Time since process start
        - counters: Request counts by endpoint/status
        - histograms: Latency distributions with percentiles (p50, p90, p95, p99)
        - gauges: Point-in-time values (connection status, etc.)
    """
    metrics = get_metrics()
    return metrics.get_all_metrics()


# =============================================================================
# Market Data Endpoints
# =============================================================================


@app.post(
    "/market-data/quote",
    response_model=Quote,
    tags=["Market Data"],
    summary="Get quote for a symbol",
    description="Get current bid/ask/last quote for a single instrument",
    responses={
        400: {"model": ErrorResponse, "description": "Invalid request"},
        403: {"model": ErrorResponse, "description": "Permission denied"},
        404: {"model": ErrorResponse, "description": "No data available"},
    },
)
async def get_quote(
    request: QuoteRequest,
    ctx: RequestContext = Depends(get_request_context),
    client_manager: IBKRClientManager = Depends(get_client_manager),
    _: str = Depends(verify_api_key),
):
    """Get a snapshot quote for a symbol."""
    from ibkr_core.market_data import get_quote as ibkr_get_quote

    logger.info(f"[{ctx.request_id}] Quote request: {request.symbol}")

    def _get_quote(client):
        spec = request.to_symbol_spec()
        return ibkr_get_quote(spec, client, timeout_s=10.0)

    return await execute_ibkr_operation(client_manager, _get_quote, ctx)


@app.post(
    "/market-data/historical",
    response_model=HistoricalBarsResponse,
    tags=["Market Data"],
    summary="Get historical bars",
    description="Get historical OHLCV bars for a symbol",
    responses={
        400: {"model": ErrorResponse, "description": "Invalid request"},
        403: {"model": ErrorResponse, "description": "Permission denied"},
        404: {"model": ErrorResponse, "description": "No data available"},
        429: {"model": ErrorResponse, "description": "Pacing violation"},
    },
)
async def get_historical_bars(
    request: HistoricalBarsRequest,
    ctx: RequestContext = Depends(get_request_context),
    client_manager: IBKRClientManager = Depends(get_client_manager),
    _: str = Depends(verify_api_key),
):
    """Get historical bars for a symbol."""
    from ibkr_core.market_data import get_historical_bars as ibkr_get_bars

    logger.info(
        f"[{ctx.request_id}] Historical bars request: {request.symbol} "
        f"({request.barSize}, {request.duration})"
    )

    def _get_bars(client):
        spec = request.to_symbol_spec()
        return ibkr_get_bars(
            spec,
            client,
            bar_size=request.barSize,
            duration=request.duration,
            what_to_show=request.whatToShow,
            rth_only=request.rthOnly,
            timeout_s=30.0,
        )

    bars = await execute_ibkr_operation(client_manager, _get_bars, ctx, timeout_s=60.0)

    return HistoricalBarsResponse(
        symbol=request.symbol,
        bars=bars,
        barCount=len(bars),
    )


# =============================================================================
# Account Endpoints
# =============================================================================


@app.get(
    "/account/summary",
    response_model=AccountSummary,
    tags=["Account"],
    summary="Get account summary",
    description="Get account balances, margin, and buying power",
    responses={
        500: {"model": ErrorResponse, "description": "Account error"},
    },
)
async def get_account_summary(
    account_id: Optional[str] = None,
    ctx: RequestContext = Depends(get_request_context),
    client_manager: IBKRClientManager = Depends(get_client_manager),
    _: str = Depends(verify_api_key),
):
    """Get account summary."""
    from ibkr_core.account import get_account_summary as ibkr_get_summary

    logger.info(f"[{ctx.request_id}] Account summary request: {account_id or 'default'}")

    def _get_summary(client):
        return ibkr_get_summary(client, account_id=account_id)

    return await execute_ibkr_operation(client_manager, _get_summary, ctx)


@app.get(
    "/account/positions",
    response_model=PositionsResponse,
    tags=["Account"],
    summary="Get account positions",
    description="Get all open positions in the account",
    responses={
        500: {"model": ErrorResponse, "description": "Account error"},
    },
)
async def get_positions(
    account_id: Optional[str] = None,
    ctx: RequestContext = Depends(get_request_context),
    client_manager: IBKRClientManager = Depends(get_client_manager),
    _: str = Depends(verify_api_key),
):
    """Get account positions."""
    from ibkr_core.account import get_positions as ibkr_get_positions

    logger.info(f"[{ctx.request_id}] Positions request: {account_id or 'default'}")

    def _get_positions(client):
        positions = ibkr_get_positions(client, account_id=account_id)
        # Get account ID from first position or managed accounts
        actual_account = account_id
        if positions:
            actual_account = positions[0].accountId
        elif not actual_account:
            accounts = client.managed_accounts
            actual_account = accounts[0] if accounts else "unknown"
        return actual_account, positions

    result = await execute_ibkr_operation(client_manager, _get_positions, ctx)
    actual_account, positions = result

    return PositionsResponse(
        accountId=actual_account,
        positions=positions,
        positionCount=len(positions),
    )


@app.get(
    "/account/pnl",
    response_model=AccountPnl,
    tags=["Account"],
    summary="Get account P&L",
    description="Get realized and unrealized P&L with per-symbol breakdown",
    responses={
        500: {"model": ErrorResponse, "description": "Account error"},
    },
)
async def get_pnl(
    account_id: Optional[str] = None,
    timeframe: Optional[str] = None,
    ctx: RequestContext = Depends(get_request_context),
    client_manager: IBKRClientManager = Depends(get_client_manager),
    _: str = Depends(verify_api_key),
):
    """Get account P&L."""
    from ibkr_core.account import get_pnl as ibkr_get_pnl

    logger.info(f"[{ctx.request_id}] P&L request: {account_id or 'default'}")

    def _get_pnl(client):
        return ibkr_get_pnl(client, account_id=account_id, timeframe=timeframe)

    return await execute_ibkr_operation(client_manager, _get_pnl, ctx)


# =============================================================================
# Order Endpoints
# =============================================================================


@app.post(
    "/orders/preview",
    response_model=OrderPreview,
    tags=["Orders"],
    summary="Preview an order",
    description="Get estimated execution details without placing the order",
    responses={
        400: {"model": ErrorResponse, "description": "Validation error"},
    },
)
async def preview_order(
    request: OrderPreviewRequest,
    ctx: RequestContext = Depends(get_request_context),
    client_manager: IBKRClientManager = Depends(get_client_manager),
    _: str = Depends(verify_api_key),
):
    """Preview an order."""
    from ibkr_core.orders import preview_order as ibkr_preview

    symbol = request.instrument.symbol
    logger.info(f"[{ctx.request_id}] Order preview: {request.side} {request.quantity} {symbol}")

    def _preview(client):
        order_spec = request.to_order_spec()
        return ibkr_preview(client, order_spec)

    return await execute_ibkr_operation(client_manager, _preview, ctx)


@app.post(
    "/orders",
    response_model=OrderResult,
    tags=["Orders"],
    summary="Place an order",
    description=(
        "Place an order. Respects ORDERS_ENABLED and TRADING_MODE settings. "
        "Returns SIMULATED status if ORDERS_ENABLED=false."
    ),
    responses={
        400: {"model": ErrorResponse, "description": "Validation error"},
        403: {"model": ErrorResponse, "description": "Trading disabled"},
    },
)
async def place_order(
    request: OrderRequest,
    ctx: RequestContext = Depends(get_request_context),
    client_manager: IBKRClientManager = Depends(get_client_manager),
    _: str = Depends(verify_api_key),
):
    """Place an order."""
    from ibkr_core.orders import place_order as ibkr_place

    symbol = request.instrument.symbol
    logger.info(
        f"[{ctx.request_id}] Place order: {request.side} {request.quantity} {symbol} "
        f"({request.orderType})"
    )

    def _place(client):
        order_spec = request.to_order_spec()
        return ibkr_place(client, order_spec)

    return await execute_ibkr_operation(client_manager, _place, ctx)


@app.post(
    "/orders/{order_id}/cancel",
    response_model=CancelResult,
    tags=["Orders"],
    summary="Cancel an order",
    description="Cancel an open order by order ID",
    responses={
        404: {"model": ErrorResponse, "description": "Order not found"},
        500: {"model": ErrorResponse, "description": "Cancel failed"},
    },
)
async def cancel_order(
    order_id: str = Path(..., description="Order ID to cancel"),
    ctx: RequestContext = Depends(get_request_context),
    client_manager: IBKRClientManager = Depends(get_client_manager),
    _: str = Depends(verify_api_key),
):
    """Cancel an order."""
    from ibkr_core.orders import cancel_order as ibkr_cancel

    logger.info(f"[{ctx.request_id}] Cancel order: {order_id}")

    def _cancel(client):
        return ibkr_cancel(client, order_id)

    return await execute_ibkr_operation(client_manager, _cancel, ctx)


@app.get(
    "/orders/{order_id}/status",
    response_model=OrderStatus,
    tags=["Orders"],
    summary="Get order status",
    description="Get current status of an order",
    responses={
        404: {"model": ErrorResponse, "description": "Order not found"},
    },
)
async def get_order_status(
    order_id: str = Path(..., description="Order ID to query"),
    ctx: RequestContext = Depends(get_request_context),
    client_manager: IBKRClientManager = Depends(get_client_manager),
    _: str = Depends(verify_api_key),
):
    """Get order status."""
    from ibkr_core.orders import get_order_status as ibkr_get_status

    logger.info(f"[{ctx.request_id}] Order status: {order_id}")

    def _get_status(client):
        return ibkr_get_status(client, order_id)

    return await execute_ibkr_operation(client_manager, _get_status, ctx)


# =============================================================================
# Additional Endpoints
# =============================================================================


@app.get(
    "/orders/open",
    response_model=List[dict],
    tags=["Orders"],
    summary="Get open orders",
    description="Get all currently open orders",
)
async def get_open_orders(
    ctx: RequestContext = Depends(get_request_context),
    client_manager: IBKRClientManager = Depends(get_client_manager),
    _: str = Depends(verify_api_key),
):
    """Get all open orders."""
    from ibkr_core.orders import get_open_orders as ibkr_get_open

    logger.info(f"[{ctx.request_id}] Get open orders")

    def _get_open(client):
        return ibkr_get_open(client)

    return await execute_ibkr_operation(client_manager, _get_open, ctx)


# =============================================================================
# Entry Point
# =============================================================================


def main():
    """Run the API server."""
    import uvicorn

    config = get_config()
    port = config.api_port
    log_level = config.log_level.lower()

    logger.info(f"Starting IBKR Gateway API on port {port}")
    logger.info(f"Trading mode: {config.trading_mode}")
    logger.info(f"Orders enabled: {config.orders_enabled}")

    uvicorn.run(
        "api.server:app",
        host="0.0.0.0",
        port=port,
        log_level=log_level,
        reload=False,
    )


if __name__ == "__main__":
    main()
