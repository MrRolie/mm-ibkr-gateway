"""
IBKR Gateway MCP Server.

Exposes 8 MCP tools for interacting with Interactive Brokers:
- get_quote: Get market quote for a symbol
- get_historical_data: Get historical OHLCV bars
- get_account_status: Get account summary and positions
- get_pnl: Get account P&L
- preview_order: Preview an order without placing
- place_order: Place an order
- get_order_status: Get status of an order
- cancel_order: Cancel an order

Usage:
    python -m mcp_server.main
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, Dict, Optional

from mcp.server.fastmcp import FastMCP

from mcp_server.config import get_mcp_config, MCPConfig
from mcp_server.http_client import IBKRAPIClient
from mcp_server.errors import handle_response, MCPToolError

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


# =============================================================================
# Application Context
# =============================================================================


@dataclass
class AppContext:
    """Application context with shared resources."""

    config: MCPConfig
    api_client: IBKRAPIClient


# Global context - set during lifespan
_app_context: Optional[AppContext] = None


@asynccontextmanager
async def app_lifespan(server: FastMCP):
    """
    Lifespan context manager for MCP server.

    Initializes the HTTP client on startup and cleans up on shutdown.
    """
    global _app_context

    config = get_mcp_config()
    api_client = IBKRAPIClient(config)

    logger.info(f"MCP Server starting, API URL: {config.api_base_url}")

    _app_context = AppContext(config=config, api_client=api_client)

    try:
        yield _app_context
    finally:
        await api_client.close()
        _app_context = None
        logger.info("MCP Server shutting down")


def get_api_client() -> IBKRAPIClient:
    """Get the API client from the global context."""
    if _app_context is None:
        raise RuntimeError("MCP server not initialized")
    return _app_context.api_client


# =============================================================================
# MCP Server Instance
# =============================================================================


mcp = FastMCP(
    name="ibkr-gateway",
    instructions="""IBKR Gateway MCP Tools for Interactive Brokers integration.

Available tools:
- get_quote: Get current market quote for a symbol
- get_historical_data: Get historical OHLCV bars
- get_account_status: Get account summary and positions
- get_pnl: Get account P&L (profit and loss)
- preview_order: Preview an order without placing
- place_order: Place an order
- get_order_status: Get status of an order
- cancel_order: Cancel an order

Note: Order placement respects ORDERS_ENABLED setting. If disabled, orders return SIMULATED status.
""",
    lifespan=app_lifespan,
)


# =============================================================================
# Market Data Tools
# =============================================================================


@mcp.tool()
async def get_quote(
    symbol: str,
    security_type: str,
    exchange: Optional[str] = None,
    currency: Optional[str] = None,
    expiry: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Get current market quote for a symbol.

    Returns bid, ask, last price, sizes, volume, and timestamp.

    Args:
        symbol: Symbol/ticker (e.g., 'AAPL', 'MES', 'SPY')
        security_type: Security type - STK (stock), ETF, FUT (futures), OPT (options), IND (index)
        exchange: Exchange routing (e.g., 'SMART', 'GLOBEX'). Optional.
        currency: Currency (e.g., 'USD'). Optional.
        expiry: Contract expiry for derivatives in YYYY-MM-DD format. Optional.

    Returns:
        Quote with: symbol, conId, bid, ask, last, bidSize, askSize, lastSize, volume, timestamp, source
    """
    api = get_api_client()

    payload: Dict[str, Any] = {
        "symbol": symbol,
        "securityType": security_type,
    }
    if exchange:
        payload["exchange"] = exchange
    if currency:
        payload["currency"] = currency
    if expiry:
        payload["expiry"] = expiry

    response = await api.post("/market-data/quote", json=payload)
    return await handle_response(response)


@mcp.tool()
async def get_historical_data(
    symbol: str,
    security_type: str,
    bar_size: str,
    duration: str,
    exchange: Optional[str] = None,
    currency: Optional[str] = None,
    expiry: Optional[str] = None,
    what_to_show: str = "TRADES",
    rth_only: bool = True,
) -> Dict[str, Any]:
    """
    Get historical OHLCV bars for a symbol.

    Args:
        symbol: Symbol/ticker (e.g., 'AAPL', 'SPY', 'MES')
        security_type: Security type - STK, ETF, FUT, OPT, IND
        bar_size: Bar size - 1s, 5s, 1m, 5m, 15m, 30m, 1h, 1d, 1w, 1mo
        duration: Duration - 60s, 1d, 5d, 1w, 1mo, 3mo, 1y
        exchange: Exchange routing. Optional.
        currency: Currency. Optional.
        expiry: Contract expiry for derivatives. Optional.
        what_to_show: Data type - TRADES, MIDPOINT, BID, ASK. Default: TRADES
        rth_only: Regular trading hours only. Default: True

    Returns:
        Object with: symbol, barCount, bars (list of OHLCV with time, open, high, low, close, volume)
    """
    api = get_api_client()

    payload: Dict[str, Any] = {
        "symbol": symbol,
        "securityType": security_type,
        "barSize": bar_size,
        "duration": duration,
        "whatToShow": what_to_show,
        "rthOnly": rth_only,
    }
    if exchange:
        payload["exchange"] = exchange
    if currency:
        payload["currency"] = currency
    if expiry:
        payload["expiry"] = expiry

    response = await api.post("/market-data/historical", json=payload)
    return await handle_response(response)


# =============================================================================
# Account Tools
# =============================================================================


@mcp.tool()
async def get_account_status(
    account_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Get account summary and positions.

    Returns balances, margin info, buying power, and all open positions.

    Args:
        account_id: Account ID. Optional - uses default account if not specified.

    Returns:
        Object with:
        - summary: accountId, currency, netLiquidation, cash, buyingPower, marginExcess, maintenanceMargin, initialMargin
        - positions: list of positions with symbol, quantity, avgPrice, marketPrice, marketValue, unrealizedPnl
        - positionCount: number of positions
    """
    api = get_api_client()

    params: Dict[str, str] = {}
    if account_id:
        params["account_id"] = account_id

    # Get summary and positions in parallel
    summary_resp, positions_resp = await asyncio.gather(
        api.get("/account/summary", params=params if params else None),
        api.get("/account/positions", params=params if params else None),
    )

    summary = await handle_response(summary_resp)
    positions = await handle_response(positions_resp)

    return {
        "summary": summary,
        "positions": positions.get("positions", []),
        "positionCount": positions.get("positionCount", 0),
    }


@mcp.tool()
async def get_pnl(
    account_id: Optional[str] = None,
    timeframe: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Get account P&L (profit and loss).

    Args:
        account_id: Account ID. Optional - uses default account if not specified.
        timeframe: P&L timeframe - CURRENT, INTRADAY, 1D, MTD, YTD. Optional.

    Returns:
        Object with:
        - accountId, currency, timeframe
        - realized: total realized P&L
        - unrealized: total unrealized P&L
        - bySymbol: per-symbol P&L breakdown
        - timestamp
    """
    api = get_api_client()

    params: Dict[str, str] = {}
    if account_id:
        params["account_id"] = account_id
    if timeframe:
        params["timeframe"] = timeframe

    response = await api.get("/account/pnl", params=params if params else None)
    return await handle_response(response)


# =============================================================================
# Order Tools
# =============================================================================


def _build_order_payload(
    instrument_symbol: str,
    instrument_security_type: str,
    side: str,
    quantity: float,
    order_type: str,
    instrument_exchange: Optional[str] = None,
    instrument_currency: Optional[str] = None,
    instrument_expiry: Optional[str] = None,
    limit_price: Optional[float] = None,
    stop_price: Optional[float] = None,
    tif: str = "DAY",
    outside_rth: bool = False,
    account_id: Optional[str] = None,
    client_order_id: Optional[str] = None,
    # Trailing stop parameters
    trailing_amount: Optional[float] = None,
    trailing_percent: Optional[float] = None,
    trail_stop_price: Optional[float] = None,
    # Bracket parameters
    take_profit_price: Optional[float] = None,
    stop_loss_price: Optional[float] = None,
    stop_loss_limit_price: Optional[float] = None,
) -> Dict[str, Any]:
    """Build order payload for REST API."""
    instrument: Dict[str, Any] = {
        "symbol": instrument_symbol,
        "securityType": instrument_security_type,
    }
    if instrument_exchange:
        instrument["exchange"] = instrument_exchange
    if instrument_currency:
        instrument["currency"] = instrument_currency
    if instrument_expiry:
        instrument["expiry"] = instrument_expiry

    payload: Dict[str, Any] = {
        "instrument": instrument,
        "side": side,
        "quantity": quantity,
        "orderType": order_type,
        "tif": tif,
        "outsideRth": outside_rth,
    }

    if limit_price is not None:
        payload["limitPrice"] = limit_price
    if stop_price is not None:
        payload["stopPrice"] = stop_price
    if account_id:
        payload["accountId"] = account_id
    if client_order_id:
        payload["clientOrderId"] = client_order_id

    # Trailing stop parameters
    if trailing_amount is not None:
        payload["trailingAmount"] = trailing_amount
    if trailing_percent is not None:
        payload["trailingPercent"] = trailing_percent
    if trail_stop_price is not None:
        payload["trailStopPrice"] = trail_stop_price

    # Bracket parameters
    if take_profit_price is not None:
        payload["takeProfitPrice"] = take_profit_price
    if stop_loss_price is not None:
        payload["stopLossPrice"] = stop_loss_price
    if stop_loss_limit_price is not None:
        payload["stopLossLimitPrice"] = stop_loss_limit_price

    return payload


@mcp.tool()
async def preview_order(
    instrument_symbol: str,
    instrument_security_type: str,
    side: str,
    quantity: float,
    order_type: str,
    instrument_exchange: Optional[str] = None,
    instrument_currency: Optional[str] = None,
    instrument_expiry: Optional[str] = None,
    limit_price: Optional[float] = None,
    stop_price: Optional[float] = None,
    tif: str = "DAY",
    outside_rth: bool = False,
    trailing_amount: Optional[float] = None,
    trailing_percent: Optional[float] = None,
    take_profit_price: Optional[float] = None,
    stop_loss_price: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Preview an order without placing it.

    Returns estimated execution details including price, notional, commission,
    and margin impact. Use this before placing an order to verify the details.

    Args:
        instrument_symbol: Symbol/ticker (e.g., 'AAPL', 'MES')
        instrument_security_type: Security type - STK, ETF, FUT, OPT
        side: Order side - BUY or SELL
        quantity: Order quantity (must be positive)
        order_type: Order type - MKT, LMT, STP, STP_LMT, TRAIL, TRAIL_LIMIT, BRACKET, MOC, OPG
        instrument_exchange: Exchange. Optional.
        instrument_currency: Currency. Optional.
        instrument_expiry: Contract expiry for derivatives. Optional.
        limit_price: Limit price for LMT/STP_LMT orders. Optional.
        stop_price: Stop price for STP/STP_LMT orders. Optional.
        tif: Time-in-force - DAY (default), GTC, IOC, FOK
        outside_rth: Allow execution outside regular trading hours. Default: False
        trailing_amount: Trailing amount in dollars for TRAIL orders. Optional.
        trailing_percent: Trailing percentage for TRAIL orders. Optional.
        take_profit_price: Take profit price for BRACKET orders. Optional.
        stop_loss_price: Stop loss price for BRACKET orders. Optional.

    Returns:
        Preview with: estimatedPrice, estimatedNotional, estimatedCommission, warnings, legs (for bracket)
    """
    api = get_api_client()

    payload = _build_order_payload(
        instrument_symbol=instrument_symbol,
        instrument_security_type=instrument_security_type,
        side=side,
        quantity=quantity,
        order_type=order_type,
        instrument_exchange=instrument_exchange,
        instrument_currency=instrument_currency,
        instrument_expiry=instrument_expiry,
        limit_price=limit_price,
        stop_price=stop_price,
        tif=tif,
        outside_rth=outside_rth,
        trailing_amount=trailing_amount,
        trailing_percent=trailing_percent,
        take_profit_price=take_profit_price,
        stop_loss_price=stop_loss_price,
    )

    response = await api.post("/orders/preview", json=payload)
    return await handle_response(response)


@mcp.tool()
async def place_order(
    instrument_symbol: str,
    instrument_security_type: str,
    side: str,
    quantity: float,
    order_type: str,
    instrument_exchange: Optional[str] = None,
    instrument_currency: Optional[str] = None,
    instrument_expiry: Optional[str] = None,
    limit_price: Optional[float] = None,
    stop_price: Optional[float] = None,
    tif: str = "DAY",
    outside_rth: bool = False,
    account_id: Optional[str] = None,
    client_order_id: Optional[str] = None,
    trailing_amount: Optional[float] = None,
    trailing_percent: Optional[float] = None,
    take_profit_price: Optional[float] = None,
    stop_loss_price: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Place an order.

    IMPORTANT: Respects ORDERS_ENABLED setting. If orders are disabled,
    returns SIMULATED status instead of actually placing the order.

    Args:
        instrument_symbol: Symbol/ticker (e.g., 'AAPL', 'MES')
        instrument_security_type: Security type - STK, ETF, FUT, OPT
        side: Order side - BUY or SELL
        quantity: Order quantity (must be positive)
        order_type: Order type - MKT, LMT, STP, STP_LMT, TRAIL, TRAIL_LIMIT, BRACKET, MOC, OPG
        instrument_exchange: Exchange. Optional.
        instrument_currency: Currency. Optional.
        instrument_expiry: Contract expiry for derivatives. Optional.
        limit_price: Limit price for LMT/STP_LMT orders. Optional.
        stop_price: Stop price for STP/STP_LMT orders. Optional.
        tif: Time-in-force - DAY (default), GTC, IOC, FOK
        outside_rth: Allow execution outside regular trading hours. Default: False
        account_id: Target account. Optional.
        client_order_id: Client order ID for tracking. Optional.
        trailing_amount: Trailing amount in dollars for TRAIL orders. Optional.
        trailing_percent: Trailing percentage for TRAIL orders. Optional.
        take_profit_price: Take profit price for BRACKET orders. Optional.
        stop_loss_price: Stop loss price for BRACKET orders. Optional.

    Returns:
        OrderResult with: orderId, status (ACCEPTED, REJECTED, or SIMULATED), orderStatus, errors
        For BRACKET orders, includes orderIds and orderRoles mapping
    """
    api = get_api_client()

    payload = _build_order_payload(
        instrument_symbol=instrument_symbol,
        instrument_security_type=instrument_security_type,
        side=side,
        quantity=quantity,
        order_type=order_type,
        instrument_exchange=instrument_exchange,
        instrument_currency=instrument_currency,
        instrument_expiry=instrument_expiry,
        limit_price=limit_price,
        stop_price=stop_price,
        tif=tif,
        outside_rth=outside_rth,
        account_id=account_id,
        client_order_id=client_order_id,
        trailing_amount=trailing_amount,
        trailing_percent=trailing_percent,
        take_profit_price=take_profit_price,
        stop_loss_price=stop_loss_price,
    )

    response = await api.post("/orders", json=payload)
    return await handle_response(response)


@mcp.tool()
async def get_order_status(
    order_id: str,
) -> Dict[str, Any]:
    """
    Get the current status of an order.

    Args:
        order_id: Order ID to query

    Returns:
        OrderStatus with:
        - orderId, clientOrderId
        - status: PENDING_SUBMIT, PENDING_CANCEL, SUBMITTED, PARTIALLY_FILLED, FILLED, CANCELLED, REJECTED, EXPIRED
        - filledQuantity, remainingQuantity
        - avgFillPrice
        - lastUpdate
        - warnings
    """
    api = get_api_client()

    response = await api.get(f"/orders/{order_id}/status")
    return await handle_response(response)


@mcp.tool()
async def cancel_order(
    order_id: str,
) -> Dict[str, Any]:
    """
    Cancel an open order.

    Args:
        order_id: Order ID to cancel

    Returns:
        CancelResult with:
        - orderId
        - status: CANCELLED, ALREADY_FILLED, NOT_FOUND, REJECTED
        - message
    """
    api = get_api_client()

    response = await api.post(f"/orders/{order_id}/cancel")
    return await handle_response(response)


# =============================================================================
# Entry Point
# =============================================================================


def main():
    """Run the MCP server with stdio transport."""
    mcp.run()


if __name__ == "__main__":
    main()
