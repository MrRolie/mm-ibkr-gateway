"""
MCP Server Module for IBKR Gateway.

Provides MCP tools for interacting with Interactive Brokers
through the REST API layer.

Usage:
    python -m mcp_server.main

Tools:
    - get_quote: Get market quote for a symbol
    - get_historical_data: Get historical OHLCV bars
    - get_account_status: Get account summary and positions
    - get_pnl: Get account P&L
    - preview_order: Preview an order without placing
    - place_order: Place an order
    - get_order_status: Get status of an order
    - cancel_order: Cancel an order
"""

from mcp_server.main import mcp

__all__ = ["mcp"]
