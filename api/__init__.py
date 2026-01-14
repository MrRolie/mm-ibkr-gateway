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

# Ensure an asyncio event loop exists at package import time to avoid
# third-party modules (e.g., eventkit/ib_insync) calling
# asyncio.get_event_loop() during import and raising RuntimeError.
import asyncio
try:
    asyncio.get_event_loop()
except RuntimeError:
    _loop = asyncio.new_event_loop()
    asyncio.set_event_loop(_loop)

from api.server import app

__all__ = ["app"]
