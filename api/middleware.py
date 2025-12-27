"""
FastAPI middleware for correlation ID management and request logging.
"""

import logging
import time
from typing import Callable

from fastapi import Request, Response
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
