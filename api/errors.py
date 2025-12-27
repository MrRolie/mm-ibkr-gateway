"""
API error handling and consistent error model.

Provides:
- Consistent error response schema
- Error code definitions
- Exception handlers for FastAPI
"""

from enum import Enum
from typing import Any, Dict, Optional

from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field


class ErrorCode(str, Enum):
    """Standard error codes for API responses."""

    # Connection errors
    IBKR_CONNECTION_ERROR = "IBKR_CONNECTION_ERROR"
    IBKR_TIMEOUT = "IBKR_TIMEOUT"

    # Market data errors
    MARKET_DATA_PERMISSION_DENIED = "MARKET_DATA_PERMISSION_DENIED"
    NO_DATA = "NO_DATA"
    PACING_VIOLATION = "PACING_VIOLATION"
    CONTRACT_RESOLUTION_ERROR = "CONTRACT_RESOLUTION_ERROR"

    # Account errors
    ACCOUNT_ERROR = "ACCOUNT_ERROR"
    ACCOUNT_NOT_FOUND = "ACCOUNT_NOT_FOUND"

    # Order errors
    TRADING_DISABLED = "TRADING_DISABLED"
    ORDER_VALIDATION_ERROR = "ORDER_VALIDATION_ERROR"
    ORDER_PLACEMENT_ERROR = "ORDER_PLACEMENT_ERROR"
    ORDER_NOT_FOUND = "ORDER_NOT_FOUND"
    ORDER_CANCEL_ERROR = "ORDER_CANCEL_ERROR"

    # Auth errors
    UNAUTHORIZED = "UNAUTHORIZED"
    FORBIDDEN = "FORBIDDEN"

    # General errors
    VALIDATION_ERROR = "VALIDATION_ERROR"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    TIMEOUT = "TIMEOUT"
    BAD_REQUEST = "BAD_REQUEST"


class ErrorResponse(BaseModel):
    """Standard error response model."""

    error_code: str = Field(..., description="Machine-readable error code")
    message: str = Field(..., description="Human-readable error message")
    details: Optional[Dict[str, Any]] = Field(None, description="Additional error details")

    class Config:
        json_schema_extra = {
            "example": {
                "error_code": "VALIDATION_ERROR",
                "message": "Invalid order specification",
                "details": {"field": "quantity", "reason": "must be positive"},
            }
        }


class APIError(Exception):
    """Base exception for API errors."""

    def __init__(
        self,
        error_code: ErrorCode,
        message: str,
        details: Optional[Dict[str, Any]] = None,
        status_code: int = 500,
    ):
        self.error_code = error_code
        self.message = message
        self.details = details or {}
        self.status_code = status_code
        super().__init__(message)

    def to_response(self) -> ErrorResponse:
        """Convert to ErrorResponse model."""
        return ErrorResponse(
            error_code=self.error_code.value,
            message=self.message,
            details=self.details if self.details else None,
        )


# Specific API exceptions
class ConnectionError(APIError):
    """IBKR connection error."""

    def __init__(self, message: str, details: Optional[Dict] = None):
        super().__init__(
            ErrorCode.IBKR_CONNECTION_ERROR,
            message,
            details,
            status_code=503,
        )


class AuthenticationError(APIError):
    """Authentication failure."""

    def __init__(self, message: str = "Invalid or missing API key"):
        super().__init__(
            ErrorCode.UNAUTHORIZED,
            message,
            status_code=401,
        )


class TradingDisabledError(APIError):
    """Trading is disabled."""

    def __init__(self, message: str = "Trading is disabled (ORDERS_ENABLED=false)"):
        super().__init__(
            ErrorCode.TRADING_DISABLED,
            message,
            status_code=403,
        )


class ValidationError(APIError):
    """Request validation error."""

    def __init__(self, message: str, details: Optional[Dict] = None):
        super().__init__(
            ErrorCode.VALIDATION_ERROR,
            message,
            details,
            status_code=400,
        )


class TimeoutError(APIError):
    """Request timeout."""

    def __init__(self, message: str = "Request timed out"):
        super().__init__(
            ErrorCode.TIMEOUT,
            message,
            status_code=504,
        )


def create_error_response(
    error_code: ErrorCode,
    message: str,
    details: Optional[Dict] = None,
    status_code: int = 500,
) -> JSONResponse:
    """Create a JSON error response."""
    return JSONResponse(
        status_code=status_code,
        content=ErrorResponse(
            error_code=error_code.value,
            message=message,
            details=details,
        ).model_dump(exclude_none=True),
    )


# Exception handlers for FastAPI
async def api_error_handler(request: Request, exc: APIError) -> JSONResponse:
    """Handle APIError exceptions."""
    return JSONResponse(
        status_code=exc.status_code,
        content=exc.to_response().model_dump(exclude_none=True),
    )


async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle uncaught exceptions."""
    return JSONResponse(
        status_code=500,
        content=ErrorResponse(
            error_code=ErrorCode.INTERNAL_ERROR.value,
            message=f"Internal server error: {type(exc).__name__}",
            details={"error": str(exc)},
        ).model_dump(exclude_none=True),
    )


# Map ibkr_core exceptions to API error codes
def map_ibkr_exception(exc: Exception) -> APIError:
    """Map ibkr_core exceptions to API errors."""
    from ibkr_core.account import (
        AccountError,
        AccountPnlError,
        AccountPositionsError,
        AccountSummaryError,
    )
    from ibkr_core.client import ConnectionError as IBKRConnectionError
    from ibkr_core.config import TradingDisabledError as IBKRTradingDisabled
    from ibkr_core.contracts import ContractResolutionError
    from ibkr_core.market_data import (
        MarketDataError,
        MarketDataPermissionError,
        MarketDataTimeoutError,
        NoMarketDataError,
        PacingViolationError,
    )
    from ibkr_core.orders import (
        OrderCancelError,
        OrderError,
        OrderNotFoundError,
        OrderPlacementError,
        OrderPreviewError,
        OrderValidationError,
    )

    error_msg = str(exc)

    # Connection errors
    if isinstance(exc, IBKRConnectionError):
        return APIError(
            ErrorCode.IBKR_CONNECTION_ERROR,
            f"IBKR connection failed: {error_msg}",
            status_code=503,
        )

    # Trading disabled
    if isinstance(exc, IBKRTradingDisabled):
        return APIError(
            ErrorCode.TRADING_DISABLED,
            error_msg,
            status_code=403,
        )

    # Contract resolution
    if isinstance(exc, ContractResolutionError):
        return APIError(
            ErrorCode.CONTRACT_RESOLUTION_ERROR,
            f"Contract resolution failed: {error_msg}",
            status_code=400,
        )

    # Market data errors
    if isinstance(exc, MarketDataPermissionError):
        return APIError(
            ErrorCode.MARKET_DATA_PERMISSION_DENIED,
            f"Market data permission denied: {error_msg}",
            status_code=403,
        )

    if isinstance(exc, NoMarketDataError):
        return APIError(
            ErrorCode.NO_DATA,
            f"No market data available: {error_msg}",
            status_code=404,
        )

    if isinstance(exc, PacingViolationError):
        return APIError(
            ErrorCode.PACING_VIOLATION,
            f"Pacing violation: {error_msg}",
            status_code=429,
        )

    if isinstance(exc, MarketDataTimeoutError):
        return APIError(
            ErrorCode.IBKR_TIMEOUT,
            f"Market data timeout: {error_msg}",
            status_code=504,
        )

    if isinstance(exc, MarketDataError):
        return APIError(
            ErrorCode.INTERNAL_ERROR,
            f"Market data error: {error_msg}",
            status_code=500,
        )

    # Account errors
    if isinstance(exc, (AccountSummaryError, AccountPositionsError, AccountPnlError)):
        return APIError(
            ErrorCode.ACCOUNT_ERROR,
            f"Account error: {error_msg}",
            status_code=500,
        )

    if isinstance(exc, AccountError):
        return APIError(
            ErrorCode.ACCOUNT_ERROR,
            f"Account error: {error_msg}",
            status_code=500,
        )

    # Order errors
    if isinstance(exc, OrderValidationError):
        return APIError(
            ErrorCode.ORDER_VALIDATION_ERROR,
            f"Order validation failed: {error_msg}",
            status_code=400,
        )

    if isinstance(exc, OrderNotFoundError):
        return APIError(
            ErrorCode.ORDER_NOT_FOUND,
            f"Order not found: {error_msg}",
            status_code=404,
        )

    if isinstance(exc, OrderPlacementError):
        return APIError(
            ErrorCode.ORDER_PLACEMENT_ERROR,
            f"Order placement failed: {error_msg}",
            status_code=500,
        )

    if isinstance(exc, OrderCancelError):
        return APIError(
            ErrorCode.ORDER_CANCEL_ERROR,
            f"Order cancellation failed: {error_msg}",
            status_code=500,
        )

    if isinstance(exc, (OrderPreviewError, OrderError)):
        return APIError(
            ErrorCode.INTERNAL_ERROR,
            f"Order error: {error_msg}",
            status_code=500,
        )

    # Default: internal error
    return APIError(
        ErrorCode.INTERNAL_ERROR,
        f"Unexpected error: {type(exc).__name__}: {error_msg}",
        status_code=500,
    )
