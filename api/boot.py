"""
Boot module used to ensure an asyncio event loop is present at import time
so downstream libraries that query get_event_loop() during import do not
fail (workaround for packages that access the loop at module import).

This module then imports and exposes the FastAPI app as `app` so uvicorn
can be run as `uvicorn api.boot:app`.
"""

import asyncio

# Ensure a default event loop exists (some libraries call get_event_loop()
# at import time which raises if no loop has been set on the main thread).
try:
    asyncio.get_event_loop()
except RuntimeError:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

# Import the application after ensuring the loop exists
from api.server import app  # noqa: E402, F401
