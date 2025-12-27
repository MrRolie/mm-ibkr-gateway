"""
FastAPI dependencies for the API layer.

Provides:
- IBKR client management (singleton with connection pooling)
- Request timeout handling
- Logging context
"""

import asyncio
import logging
import os
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from typing import Callable, Optional

from fastapi import Request

from ibkr_core.client import ConnectionError as IBKRConnectionError
from ibkr_core.client import IBKRClient
from ibkr_core.config import get_config

logger = logging.getLogger(__name__)


# =============================================================================
# IBKR Executor
# =============================================================================


def _init_ibkr_executor():
    """Ensure an asyncio loop exists for the IBKR worker thread."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)


def _create_ibkr_executor() -> ThreadPoolExecutor:
    return ThreadPoolExecutor(
        max_workers=1,
        thread_name_prefix="ibkr",
        initializer=_init_ibkr_executor,
    )


_IBKR_EXECUTOR: Optional[ThreadPoolExecutor] = None


def get_ibkr_executor() -> ThreadPoolExecutor:
    """Get the dedicated executor for IBKR operations."""
    global _IBKR_EXECUTOR
    if _IBKR_EXECUTOR is None or getattr(_IBKR_EXECUTOR, "_shutdown", False):
        _IBKR_EXECUTOR = _create_ibkr_executor()
    return _IBKR_EXECUTOR


def shutdown_ibkr_executor() -> None:
    """Shut down the dedicated IBKR executor."""
    global _IBKR_EXECUTOR
    if _IBKR_EXECUTOR is not None:
        _IBKR_EXECUTOR.shutdown(wait=True)
        _IBKR_EXECUTOR = None


# =============================================================================
# IBKR Client Management
# =============================================================================


class IBKRClientManager:
    """
    Manages the IBKR client connection for the API.

    Provides a singleton client that can be reconnected on failure.
    Thread-safe for use with FastAPI's async context.
    """

    def __init__(self):
        self._client: Optional[IBKRClient] = None
        self._lock = asyncio.Lock()

    @property
    def is_connected(self) -> bool:
        """Check if client is connected."""
        return self._client is not None and self._client.is_connected

    async def get_client(self, timeout: int = 10) -> IBKRClient:
        """
        Get a connected IBKR client.

        Creates a new client if needed, or returns the existing one.
        Reconnects if connection was lost.

        Args:
            timeout: Connection timeout in seconds

        Returns:
            Connected IBKRClient

        Raises:
            ConnectionError: If connection fails
        """
        async with self._lock:
            if self._client is None or not self._client.is_connected:
                logger.info("Creating new IBKR client connection")
                self._client = self._create_client()

                try:
                    # ib_insync is sync, run in thread pool
                    loop = asyncio.get_running_loop()
                    await loop.run_in_executor(
                        get_ibkr_executor(),
                        lambda: self._client.connect(timeout=timeout),
                    )
                    logger.info(
                        f"IBKR client connected: mode={self._client.mode}, "
                        f"accounts={self._client.managed_accounts}"
                    )
                except IBKRConnectionError as e:
                    self._client = None
                    raise e
                except Exception as e:
                    self._client = None
                    raise IBKRConnectionError(f"Failed to connect to IBKR: {e}") from e

            return self._client

    def _create_client(self) -> IBKRClient:
        """Create a new IBKR client with unique client ID."""
        config = get_config()

        # Use a somewhat random client ID to avoid conflicts
        # Base it on PID to be unique per process
        base_client_id = config.client_id
        pid_offset = os.getpid() % 1000

        return IBKRClient(
            mode=config.trading_mode,
            client_id=base_client_id + pid_offset,
        )

    async def disconnect(self):
        """Disconnect the client."""
        async with self._lock:
            if self._client is not None:
                try:
                    loop = asyncio.get_running_loop()
                    await loop.run_in_executor(
                        get_ibkr_executor(),
                        self._client.disconnect,
                    )
                except Exception as e:
                    logger.warning(f"Error disconnecting IBKR client: {e}")
                finally:
                    self._client = None

    def get_client_sync(self, timeout: int = 10) -> IBKRClient:
        """
        Synchronous version of get_client for use in sync contexts.

        Creates a new client if needed, or returns the existing one.
        """
        if self._client is None or not self._client.is_connected:
            logger.info("Creating new IBKR client connection (sync)")
            self._client = self._create_client()
            self._client.connect(timeout=timeout)
            logger.info(
                f"IBKR client connected: mode={self._client.mode}, "
                f"accounts={self._client.managed_accounts}"
            )

        return self._client


# Global client manager
_client_manager = IBKRClientManager()


def get_client_manager() -> IBKRClientManager:
    """Get the global client manager."""
    return _client_manager


# =============================================================================
# Request Context
# =============================================================================


class RequestContext:
    """Context for a single API request."""

    def __init__(self, request: Request):
        self.request = request
        self.request_id = str(uuid.uuid4())[:8]
        self.start_time = time.time()
        self.endpoint = f"{request.method} {request.url.path}"

    @property
    def elapsed_ms(self) -> float:
        """Elapsed time in milliseconds."""
        return (time.time() - self.start_time) * 1000


def get_request_context(request: Request) -> RequestContext:
    """Dependency to get request context."""
    return RequestContext(request)


# =============================================================================
# Logging Middleware
# =============================================================================


def log_request(ctx: RequestContext, status: str = "success", error: str = None):
    """Log request completion."""
    log_data = {
        "request_id": ctx.request_id,
        "endpoint": ctx.endpoint,
        "elapsed_ms": round(ctx.elapsed_ms, 2),
        "status": status,
    }

    if error:
        log_data["error"] = error
        logger.warning(f"Request failed: {log_data}")
    else:
        logger.info(f"Request completed: {log_data}")


# =============================================================================
# Timeout Handling
# =============================================================================


def get_request_timeout() -> float:
    """Get request timeout from environment or default."""
    default_timeout = 30.0  # 30 seconds
    try:
        return float(os.environ.get("API_REQUEST_TIMEOUT", default_timeout))
    except (ValueError, TypeError):
        return default_timeout


async def run_with_timeout(coro, timeout_s: float):
    """
    Run a coroutine with timeout.

    Args:
        coro: Coroutine to run
        timeout_s: Timeout in seconds

    Returns:
        Result of the coroutine

    Raises:
        asyncio.TimeoutError: If timeout is exceeded
    """
    return await asyncio.wait_for(coro, timeout=timeout_s)


def run_sync_with_timeout(func: Callable, timeout_s: float, *args, **kwargs):
    """
    Run a sync function in executor with timeout.

    This is useful for running ib_insync operations that are blocking.
    """

    async def _run():
        loop = asyncio.get_running_loop()
        return await asyncio.wait_for(
            loop.run_in_executor(
                get_ibkr_executor(),
                lambda: func(*args, **kwargs),
            ),
            timeout=timeout_s,
        )

    return asyncio.get_event_loop().run_until_complete(_run())


# =============================================================================
# Lifespan Management
# =============================================================================


@asynccontextmanager
async def lifespan_context(app):
    """
    Lifespan context manager for FastAPI.

    Handles startup and shutdown of IBKR client.
    """
    logger.info("API server starting up")

    # Optional: Pre-connect to IBKR on startup
    # Uncomment if you want eager connection
    # try:
    #     await _client_manager.get_client()
    # except Exception as e:
    #     logger.warning(f"Could not pre-connect to IBKR: {e}")

    yield

    # Cleanup on shutdown
    logger.info("API server shutting down")
    await _client_manager.disconnect()
    logger.info("IBKR client disconnected")

    shutdown_ibkr_executor()
