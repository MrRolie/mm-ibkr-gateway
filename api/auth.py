"""
API authentication middleware.

Provides API key authentication via the X-API-Key header.
The expected API key is read from the API_KEY environment variable.
If API_KEY is not set, authentication is disabled (local-only mode).
"""

import os
from typing import Optional

from fastapi import HTTPException, Request, Security
from fastapi.security import APIKeyHeader

from api.errors import ErrorCode, ErrorResponse

# API key header name
API_KEY_HEADER = APIKeyHeader(
    name="X-API-Key",
    auto_error=False,
    description="API key for authentication. Required if API_KEY env var is set.",
)


def get_api_key() -> Optional[str]:
    """Get the expected API key from environment."""
    return os.environ.get("API_KEY")


def is_auth_enabled() -> bool:
    """Check if authentication is enabled."""
    return get_api_key() is not None


async def verify_api_key(
    request: Request,
    api_key: Optional[str] = Security(API_KEY_HEADER),
) -> Optional[str]:
    """
    Verify API key from request header.

    If API_KEY environment variable is set, requires matching X-API-Key header.
    If API_KEY is not set, allows all requests (local-only mode).

    Args:
        request: FastAPI request object
        api_key: API key from X-API-Key header

    Returns:
        The API key if valid, None if auth is disabled

    Raises:
        HTTPException: If authentication fails
    """
    expected_key = get_api_key()

    # If API_KEY not set, allow all requests (local-only mode)
    if expected_key is None:
        return None

    # API_KEY is set, require valid key
    if api_key is None:
        raise HTTPException(
            status_code=401,
            detail=ErrorResponse(
                error_code=ErrorCode.UNAUTHORIZED.value,
                message="Missing API key. Provide X-API-Key header.",
            ).model_dump(exclude_none=True),
        )

    if api_key != expected_key:
        raise HTTPException(
            status_code=401,
            detail=ErrorResponse(
                error_code=ErrorCode.UNAUTHORIZED.value,
                message="Invalid API key.",
            ).model_dump(exclude_none=True),
        )

    return api_key


def get_auth_status() -> dict:
    """Get authentication status for health check."""
    return {
        "enabled": is_auth_enabled(),
        "method": "api_key" if is_auth_enabled() else "none",
    }
