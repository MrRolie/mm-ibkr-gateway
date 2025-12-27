"""
MCP Error Handling.

Translates HTTP errors from the REST API to MCP-compatible errors.
Preserves error codes from the REST API for consistency.
"""

from typing import Any, Dict, Optional

import httpx


class MCPToolError(Exception):
    """
    Base error for MCP tool failures.

    Raised when an HTTP request to the REST API fails.
    Preserves the error code from the REST API response.
    """

    def __init__(
        self,
        code: str,
        message: str,
        details: Optional[Dict[str, Any]] = None,
    ):
        self.code = code
        self.message = message
        self.details = details or {}
        super().__init__(message)

    def __str__(self) -> str:
        if self.details:
            return f"[{self.code}] {self.message} - {self.details}"
        return f"[{self.code}] {self.message}"


# Fallback error mappings for when REST API doesn't return structured error
HTTP_STATUS_TO_ERROR = {
    400: ("VALIDATION_ERROR", "Invalid request parameters"),
    401: ("UNAUTHORIZED", "Authentication required"),
    403: ("FORBIDDEN", "Operation not permitted"),
    404: ("NOT_FOUND", "Resource not found"),
    429: ("RATE_LIMITED", "Too many requests"),
    500: ("INTERNAL_ERROR", "Internal server error"),
    503: ("IBKR_CONNECTION_ERROR", "IBKR Gateway not connected"),
    504: ("TIMEOUT", "Request timed out"),
}


def translate_http_error(response: httpx.Response) -> MCPToolError:
    """
    Translate HTTP error response to MCPToolError.

    First attempts to parse the structured error response from the REST API.
    Falls back to generic error based on HTTP status code.

    Args:
        response: HTTP response with error status code

    Returns:
        MCPToolError with appropriate error code and message
    """
    status = response.status_code

    # Try to parse error body from REST API
    try:
        body = response.json()
        error_code = body.get("error_code", "UNKNOWN_ERROR")
        message = body.get("message", f"HTTP {status} error")
        details = body.get("details")
    except Exception:
        # Fallback to generic error based on status code
        code_info = HTTP_STATUS_TO_ERROR.get(status, ("INTERNAL_ERROR", f"HTTP {status} error"))
        error_code, message = code_info
        details = None

    return MCPToolError(error_code, message, details)


async def handle_response(response: httpx.Response) -> Dict[str, Any]:
    """
    Handle HTTP response, raising MCPToolError on failure.

    Args:
        response: HTTP response to handle

    Returns:
        Parsed JSON response on success

    Raises:
        MCPToolError: If response indicates an error (status >= 400)
    """
    if response.status_code >= 400:
        raise translate_http_error(response)
    return response.json()
