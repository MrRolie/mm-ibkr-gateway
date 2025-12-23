"""
Tests for MCP error handling and translation.

Verifies that HTTP errors are correctly translated to MCP errors.
"""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
import httpx

from mcp_server.errors import (
    MCPToolError,
    translate_http_error,
    handle_response,
    HTTP_STATUS_TO_ERROR,
)


# =============================================================================
# Test MCPToolError
# =============================================================================


class TestMCPToolError:
    """Tests for MCPToolError class."""

    def test_error_with_code_and_message(self):
        """Test creating error with code and message."""
        error = MCPToolError("VALIDATION_ERROR", "Invalid quantity")

        assert error.code == "VALIDATION_ERROR"
        assert error.message == "Invalid quantity"
        assert error.details == {}
        assert str(error) == "[VALIDATION_ERROR] Invalid quantity"

    def test_error_with_details(self):
        """Test creating error with details."""
        error = MCPToolError(
            "ORDER_VALIDATION_ERROR",
            "Invalid order parameters",
            {"field": "quantity", "reason": "must be positive"},
        )

        assert error.code == "ORDER_VALIDATION_ERROR"
        assert error.details["field"] == "quantity"
        assert "field" in str(error)

    def test_error_is_exception(self):
        """Test that MCPToolError is an exception."""
        error = MCPToolError("TEST_ERROR", "Test message")
        assert isinstance(error, Exception)

        with pytest.raises(MCPToolError) as exc_info:
            raise error

        assert exc_info.value.code == "TEST_ERROR"


# =============================================================================
# Test Error Translation
# =============================================================================


class TestTranslateHttpError:
    """Tests for translate_http_error function."""

    def test_translate_connection_error_503(self):
        """503 should translate to IBKR_CONNECTION_ERROR."""
        response = MagicMock(spec=httpx.Response)
        response.status_code = 503
        response.json.return_value = {
            "error_code": "IBKR_CONNECTION_ERROR",
            "message": "IBKR Gateway not connected",
        }

        error = translate_http_error(response)

        assert error.code == "IBKR_CONNECTION_ERROR"
        assert "not connected" in error.message

    def test_translate_timeout_504(self):
        """504 should translate to TIMEOUT."""
        response = MagicMock(spec=httpx.Response)
        response.status_code = 504
        response.json.return_value = {
            "error_code": "TIMEOUT",
            "message": "Request timed out after 30s",
        }

        error = translate_http_error(response)

        assert error.code == "TIMEOUT"

    def test_translate_unauthorized_401(self):
        """401 should translate to UNAUTHORIZED."""
        response = MagicMock(spec=httpx.Response)
        response.status_code = 401
        response.json.return_value = {
            "error_code": "UNAUTHORIZED",
            "message": "Invalid API key",
        }

        error = translate_http_error(response)

        assert error.code == "UNAUTHORIZED"
        assert "Invalid API key" in error.message

    def test_translate_validation_error_400(self):
        """400 should translate to VALIDATION_ERROR."""
        response = MagicMock(spec=httpx.Response)
        response.status_code = 400
        response.json.return_value = {
            "error_code": "ORDER_VALIDATION_ERROR",
            "message": "Invalid order: quantity must be positive",
            "details": {"field": "quantity"},
        }

        error = translate_http_error(response)

        assert error.code == "ORDER_VALIDATION_ERROR"
        assert error.details["field"] == "quantity"

    def test_translate_not_found_404(self):
        """404 should translate to appropriate error."""
        response = MagicMock(spec=httpx.Response)
        response.status_code = 404
        response.json.return_value = {
            "error_code": "ORDER_NOT_FOUND",
            "message": "Order 12345 not found",
        }

        error = translate_http_error(response)

        assert error.code == "ORDER_NOT_FOUND"

    def test_translate_trading_disabled_403(self):
        """403 with TRADING_DISABLED should preserve code."""
        response = MagicMock(spec=httpx.Response)
        response.status_code = 403
        response.json.return_value = {
            "error_code": "TRADING_DISABLED",
            "message": "Trading is disabled (ORDERS_ENABLED=false)",
        }

        error = translate_http_error(response)

        assert error.code == "TRADING_DISABLED"

    def test_translate_rate_limit_429(self):
        """429 should translate to RATE_LIMITED."""
        response = MagicMock(spec=httpx.Response)
        response.status_code = 429
        response.json.return_value = {
            "error_code": "PACING_VIOLATION",
            "message": "Too many requests",
        }

        error = translate_http_error(response)

        assert error.code == "PACING_VIOLATION"

    def test_translate_internal_error_500(self):
        """500 should translate to INTERNAL_ERROR."""
        response = MagicMock(spec=httpx.Response)
        response.status_code = 500
        response.json.return_value = {
            "error_code": "INTERNAL_ERROR",
            "message": "Unexpected server error",
        }

        error = translate_http_error(response)

        assert error.code == "INTERNAL_ERROR"

    def test_translate_fallback_on_json_parse_error(self):
        """Fallback to generic error when JSON parsing fails."""
        response = MagicMock(spec=httpx.Response)
        response.status_code = 503
        response.json.side_effect = Exception("Invalid JSON")

        error = translate_http_error(response)

        assert error.code == "IBKR_CONNECTION_ERROR"  # from HTTP_STATUS_TO_ERROR

    def test_translate_unknown_status_code(self):
        """Unknown status code should use generic message."""
        response = MagicMock(spec=httpx.Response)
        response.status_code = 418  # I'm a teapot
        response.json.side_effect = Exception("Invalid JSON")

        error = translate_http_error(response)

        assert error.code == "INTERNAL_ERROR"
        assert "418" in error.message


# =============================================================================
# Test Response Handling
# =============================================================================


class TestHandleResponse:
    """Tests for handle_response function."""

    @pytest.mark.asyncio
    async def test_handle_success_response_200(self):
        """200 response should return JSON data."""
        response = MagicMock(spec=httpx.Response)
        response.status_code = 200
        response.json.return_value = {"symbol": "AAPL", "bid": 150.0}

        result = await handle_response(response)

        assert result == {"symbol": "AAPL", "bid": 150.0}

    @pytest.mark.asyncio
    async def test_handle_success_response_201(self):
        """201 response should return JSON data."""
        response = MagicMock(spec=httpx.Response)
        response.status_code = 201
        response.json.return_value = {"orderId": "12345"}

        result = await handle_response(response)

        assert result == {"orderId": "12345"}

    @pytest.mark.asyncio
    async def test_handle_error_response_raises(self):
        """Error response should raise MCPToolError."""
        response = MagicMock(spec=httpx.Response)
        response.status_code = 503
        response.json.return_value = {
            "error_code": "IBKR_CONNECTION_ERROR",
            "message": "Not connected",
        }

        with pytest.raises(MCPToolError) as exc_info:
            await handle_response(response)

        assert exc_info.value.code == "IBKR_CONNECTION_ERROR"

    @pytest.mark.asyncio
    async def test_handle_400_raises(self):
        """400 response should raise MCPToolError."""
        response = MagicMock(spec=httpx.Response)
        response.status_code = 400
        response.json.return_value = {
            "error_code": "VALIDATION_ERROR",
            "message": "Invalid request",
        }

        with pytest.raises(MCPToolError) as exc_info:
            await handle_response(response)

        assert exc_info.value.code == "VALIDATION_ERROR"

    @pytest.mark.asyncio
    async def test_handle_401_raises(self):
        """401 response should raise MCPToolError."""
        response = MagicMock(spec=httpx.Response)
        response.status_code = 401
        response.json.return_value = {
            "error_code": "UNAUTHORIZED",
            "message": "Missing API key",
        }

        with pytest.raises(MCPToolError) as exc_info:
            await handle_response(response)

        assert exc_info.value.code == "UNAUTHORIZED"


# =============================================================================
# Test HTTP Status Mapping
# =============================================================================


class TestHttpStatusMapping:
    """Tests for HTTP_STATUS_TO_ERROR mapping."""

    def test_mapping_completeness(self):
        """Verify all expected status codes are mapped."""
        expected_codes = [400, 401, 403, 404, 429, 500, 503, 504]

        for code in expected_codes:
            assert code in HTTP_STATUS_TO_ERROR
            error_code, message = HTTP_STATUS_TO_ERROR[code]
            assert isinstance(error_code, str)
            assert isinstance(message, str)

    def test_mapping_values(self):
        """Verify specific mappings are correct."""
        assert HTTP_STATUS_TO_ERROR[400][0] == "VALIDATION_ERROR"
        assert HTTP_STATUS_TO_ERROR[401][0] == "UNAUTHORIZED"
        assert HTTP_STATUS_TO_ERROR[403][0] == "FORBIDDEN"
        assert HTTP_STATUS_TO_ERROR[404][0] == "NOT_FOUND"
        assert HTTP_STATUS_TO_ERROR[429][0] == "RATE_LIMITED"
        assert HTTP_STATUS_TO_ERROR[500][0] == "INTERNAL_ERROR"
        assert HTTP_STATUS_TO_ERROR[503][0] == "IBKR_CONNECTION_ERROR"
        assert HTTP_STATUS_TO_ERROR[504][0] == "TIMEOUT"


# =============================================================================
# Integration Tests - Error Propagation
# =============================================================================


class TestErrorPropagation:
    """Tests for error propagation through tool calls."""

    @pytest.mark.asyncio
    async def test_tool_propagates_connection_error(self):
        """Tool should propagate connection error from API."""
        from mcp_server.http_client import IBKRAPIClient
        from mcp_server.config import MCPConfig

        config = MCPConfig(api_base_url="http://localhost:8000")
        client = IBKRAPIClient(config)
        client.post = AsyncMock()

        response = MagicMock(spec=httpx.Response)
        response.status_code = 503
        response.json.return_value = {
            "error_code": "IBKR_CONNECTION_ERROR",
            "message": "Cannot connect to IBKR Gateway",
        }
        client.post.return_value = response

        with patch("mcp_server.main._app_context") as mock_ctx:
            mock_ctx.api_client = client

            from mcp_server.main import get_quote

            with pytest.raises(MCPToolError) as exc_info:
                await get_quote(symbol="AAPL", security_type="STK")

            assert exc_info.value.code == "IBKR_CONNECTION_ERROR"

    @pytest.mark.asyncio
    async def test_tool_propagates_validation_error(self):
        """Tool should propagate validation error from API."""
        from mcp_server.http_client import IBKRAPIClient
        from mcp_server.config import MCPConfig

        config = MCPConfig(api_base_url="http://localhost:8000")
        client = IBKRAPIClient(config)
        client.post = AsyncMock()

        response = MagicMock(spec=httpx.Response)
        response.status_code = 400
        response.json.return_value = {
            "error_code": "ORDER_VALIDATION_ERROR",
            "message": "Limit price required for LMT orders",
            "details": {"field": "limitPrice"},
        }
        client.post.return_value = response

        with patch("mcp_server.main._app_context") as mock_ctx:
            mock_ctx.api_client = client

            from mcp_server.main import place_order

            with pytest.raises(MCPToolError) as exc_info:
                await place_order(
                    instrument_symbol="AAPL",
                    instrument_security_type="STK",
                    side="BUY",
                    quantity=10,
                    order_type="LMT",
                    # Missing limit_price
                )

            assert exc_info.value.code == "ORDER_VALIDATION_ERROR"
            assert exc_info.value.details["field"] == "limitPrice"
