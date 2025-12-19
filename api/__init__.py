"""
API Module - REST API layer for IBKR Gateway.

This module provides:
- FastAPI application with endpoints for market data, account, and orders
- Authentication via API key header
- Consistent error handling
- Per-request timeouts and logging

Usage:
    # Run the server
    uvicorn api.server:app --host 0.0.0.0 --port 8000

    # Or use the main entry point
    python -m api.server
"""

from api.server import app

__all__ = ["app"]
