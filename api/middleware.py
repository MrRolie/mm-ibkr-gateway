"""
FastAPI middleware for correlation ID management, request logging,
time-window enforcement, and trading control integration.
"""

import logging
import time
from datetime import datetime
from typing import Callable
from zoneinfo import ZoneInfo

from fastapi import HTTPException, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from ibkr_core.logging_config import clear_correlation_id, log_with_context, set_correlation_id
from ibkr_core.metrics import record_api_request

logger = logging.getLogger(__name__)


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """
    Middleware that adds correlation ID to all requests and responses.

    For each request:
    1. Checks for X-Correlation-ID header from client (optional)
    2. Generates a new correlation ID if not provided
    3. Sets correlation ID in context for all logs
    4. Adds X-Correlation-ID to response headers
    5. Logs request start and completion with structured data
    6. Cleans up correlation ID after request completes
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Process request with correlation ID.

        Args:
            request: Incoming request
            call_next: Next middleware/route handler

        Returns:
            Response with X-Correlation-ID header
        """
        # Get or generate correlation ID
        correlation_id = request.headers.get("X-Correlation-ID")
        if not correlation_id:
            import uuid

            correlation_id = str(uuid.uuid4())

        # Set correlation ID in context for logging
        set_correlation_id(correlation_id)

        # Log request start
        start_time = time.time()
        log_with_context(
            logger,
            logging.INFO,
            "Request started",
            method=request.method,
            path=str(request.url.path),
            client_ip=request.client.host if request.client else "unknown",
        )

        # Process request
        try:
            response = await call_next(request)

            # Log request completion
            elapsed_seconds = time.time() - start_time
            elapsed_ms = elapsed_seconds * 1000
            log_with_context(
                logger,
                logging.INFO,
                "Request completed",
                method=request.method,
                path=str(request.url.path),
                status_code=response.status_code,
                elapsed_ms=round(elapsed_ms, 2),
            )

            # Record metrics
            record_api_request(
                endpoint=str(request.url.path),
                method=request.method,
                status_code=response.status_code,
                duration_seconds=elapsed_seconds,
            )

            # Add correlation ID to response headers
            response.headers["X-Correlation-ID"] = correlation_id

            return response

        except Exception as e:
            # Log request failure
            elapsed_seconds = time.time() - start_time
            elapsed_ms = elapsed_seconds * 1000
            log_with_context(
                logger,
                logging.ERROR,
                "Request failed",
                method=request.method,
                path=str(request.url.path),
                error=str(e),
                error_type=type(e).__name__,
                elapsed_ms=round(elapsed_ms, 2),
            )

            # Record failed request metric (500 status)
            record_api_request(
                endpoint=str(request.url.path),
                method=request.method,
                status_code=500,
                duration_seconds=elapsed_seconds,
            )
            raise

        finally:
            # Always clean up correlation ID
            clear_correlation_id()

class TimeWindowMiddleware(BaseHTTPMiddleware):
    """
    Middleware that enforces time-window restrictions for API access.

    Returns 503 Service Unavailable for all endpoints outside the configured
    RUN_WINDOW_* settings, except for health and status endpoints.
    """

    def __init__(self, app):
        super().__init__(app)
        self.start_time = "04:00"
        self.end_time = "20:00"
        self.days_str = "Mon,Tue,Wed,Thu,Fri"
        self.timezone_str = "America/Toronto"

    def _refresh_config(self) -> None:
        from ibkr_core.config import get_config

        config = get_config()
        self.start_time = config.run_window_start
        self.end_time = config.run_window_end
        self.days_str = config.run_window_days
        self.timezone_str = config.run_window_timezone

    def is_in_run_window(self) -> bool:
        """Check if current time is within RUN_WINDOW_* settings."""
        self._refresh_config()
        try:
            tz = ZoneInfo(self.timezone_str)
            now = datetime.now(tz)

            # Check day
            day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
            current_day = day_names[now.weekday()]
            if current_day not in self.days_str:
                return False

            # Check time
            start = datetime.strptime(self.start_time, "%H:%M").time()
            end = datetime.strptime(self.end_time, "%H:%M").time()
            return start <= now.time() < end
        except Exception as e:
            logger.error(f"Error checking run window: {e}")
            return False  # Fail closed

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Process request with time-window check.

        Args:
            request: Incoming request
            call_next: Next middleware/route handler

        Returns:
            Response or 503 if outside window

        Raises:
            HTTPException: 503 if outside run window
        """
        # Allow health checks and control status endpoints outside window
        exempt_paths = ["/health", "/control/status", "/docs", "/openapi.json"]
        if any(request.url.path.startswith(path) for path in exempt_paths):
            return await call_next(request)

        # Check if we're in the run window
        if not self.is_in_run_window():
            logger.warning(
                f"Request rejected: outside run window",
                extra={
                    "path": str(request.url.path),
                    "method": request.method,
                    "window": f"{self.start_time}-{self.end_time} {self.timezone_str}",
                },
            )
            raise HTTPException(
                status_code=503,
                detail=(
                    f"Service unavailable outside run window "
                    f"({self.start_time}-{self.end_time} {self.timezone_str} on {self.days_str})"
                ),
            )

        return await call_next(request)


class TradingDisabledMiddleware(BaseHTTPMiddleware):
    """
    Middleware that checks mm-control trading disabled status.

    Returns 403 Forbidden for order-related endpoints when trading is disabled
    via mm-control guard file or toggle store.
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Process request with trading disabled check.

        Args:
            request: Incoming request
            call_next: Next middleware/route handler

        Returns:
            Response or 403 if trading disabled

        Raises:
            HTTPException: 403 if trading is disabled
        """
        # Only check on order endpoints (POST/PUT)
        if "/orders" in request.url.path and request.method in ["POST", "PUT"]:
            try:
                from mm_control import is_trading_disabled

                if is_trading_disabled():
                    logger.warning(
                        f"Order request rejected: trading is disabled via mm-control",
                        extra={
                            "path": str(request.url.path),
                            "method": request.method,
                        },
                    )
                    raise HTTPException(
                        status_code=403,
                        detail=(
                            "Trading is disabled via mm-control. "
                            "Check C:\\ProgramData\\mm-control for details."
                        ),
                    )
            except ImportError:
                logger.debug("mm-control not installed - guard file check skipped")

        return await call_next(request)
