"""
Unit tests for MCP tools.

Tests each tool with mocked HTTP client to verify:
- Correct payload construction
- Response parsing
- Parameter handling (required vs optional)
"""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from mcp_server.config import MCPConfig
from mcp_server.errors import MCPToolError
from mcp_server.http_client import IBKRAPIClient

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_config():
    """Create test configuration."""
    return MCPConfig(
        api_base_url="http://localhost:8000",
        api_key="test-api-key",
        request_timeout=30.0,
    )


@pytest.fixture
def mock_api_client(mock_config):
    """Create mock API client."""
    client = IBKRAPIClient(mock_config)
    client.get = AsyncMock()
    client.post = AsyncMock()
    return client


def create_mock_response(status_code: int, json_data: dict) -> MagicMock:
    """Create a mock HTTP response."""
    response = MagicMock(spec=httpx.Response)
    response.status_code = status_code
    response.json.return_value = json_data
    return response


# =============================================================================
# Test get_quote
# =============================================================================


class TestGetQuote:
    """Tests for get_quote tool."""

    @pytest.mark.asyncio
    async def test_get_quote_minimal_params(self, mock_api_client):
        """Test quote with only required parameters."""
        mock_api_client.post.return_value = create_mock_response(
            200,
            {
                "symbol": "AAPL",
                "conId": 265598,
                "bid": 150.00,
                "ask": 150.05,
                "last": 150.02,
                "bidSize": 100,
                "askSize": 200,
                "lastSize": 50,
                "volume": 1000000,
                "timestamp": "2024-01-15T14:30:00Z",
                "source": "IBKR_REALTIME",
            },
        )

        # Import and patch the get_api_client function
        with patch("mcp_server.main._app_context") as mock_ctx:
            mock_ctx.api_client = mock_api_client

            from mcp_server.main import get_quote

            result = await get_quote(
                symbol="AAPL",
                security_type="STK",
            )

        assert result["symbol"] == "AAPL"
        assert result["bid"] == 150.00
        assert result["ask"] == 150.05

        # Verify payload
        call_args = mock_api_client.post.call_args
        assert call_args[0][0] == "/market-data/quote"
        payload = call_args[1]["json"]
        assert payload["symbol"] == "AAPL"
        assert payload["securityType"] == "STK"
        assert "exchange" not in payload
        assert "currency" not in payload

    @pytest.mark.asyncio
    async def test_get_quote_all_params(self, mock_api_client):
        """Test quote with all parameters."""
        mock_api_client.post.return_value = create_mock_response(
            200,
            {
                "symbol": "MES",
                "conId": 123456,
                "bid": 4500.00,
                "ask": 4500.25,
            },
        )

        with patch("mcp_server.main._app_context") as mock_ctx:
            mock_ctx.api_client = mock_api_client

            from mcp_server.main import get_quote

            await get_quote(
                symbol="MES",
                security_type="FUT",
                exchange="GLOBEX",
                currency="USD",
                expiry="2024-12-20",
            )

        payload = mock_api_client.post.call_args[1]["json"]
        assert payload["symbol"] == "MES"
        assert payload["securityType"] == "FUT"
        assert payload["exchange"] == "GLOBEX"
        assert payload["currency"] == "USD"
        assert payload["expiry"] == "2024-12-20"


# =============================================================================
# Test get_historical_data
# =============================================================================


class TestGetHistoricalData:
    """Tests for get_historical_data tool."""

    @pytest.mark.asyncio
    async def test_get_historical_data_minimal(self, mock_api_client):
        """Test historical data with minimal parameters."""
        mock_api_client.post.return_value = create_mock_response(
            200,
            {
                "symbol": "AAPL",
                "barCount": 20,
                "bars": [
                    {
                        "time": "2024-01-15T00:00:00Z",
                        "open": 150.0,
                        "high": 151.0,
                        "low": 149.0,
                        "close": 150.5,
                        "volume": 1000000,
                    }
                ],
            },
        )

        with patch("mcp_server.main._app_context") as mock_ctx:
            mock_ctx.api_client = mock_api_client

            from mcp_server.main import get_historical_data

            result = await get_historical_data(
                symbol="AAPL",
                security_type="STK",
                bar_size="1d",
                duration="1mo",
            )

        assert result["symbol"] == "AAPL"
        assert result["barCount"] == 20
        assert len(result["bars"]) == 1

        payload = mock_api_client.post.call_args[1]["json"]
        assert payload["symbol"] == "AAPL"
        assert payload["securityType"] == "STK"
        assert payload["barSize"] == "1d"
        assert payload["duration"] == "1mo"
        assert payload["whatToShow"] == "TRADES"  # default
        assert payload["rthOnly"] is True  # default

    @pytest.mark.asyncio
    async def test_get_historical_data_custom_options(self, mock_api_client):
        """Test historical data with custom options."""
        mock_api_client.post.return_value = create_mock_response(
            200,
            {
                "symbol": "SPY",
                "barCount": 5,
                "bars": [],
            },
        )

        with patch("mcp_server.main._app_context") as mock_ctx:
            mock_ctx.api_client = mock_api_client

            from mcp_server.main import get_historical_data

            await get_historical_data(
                symbol="SPY",
                security_type="ETF",
                bar_size="5m",
                duration="1d",
                what_to_show="MIDPOINT",
                rth_only=False,
            )

        payload = mock_api_client.post.call_args[1]["json"]
        assert payload["whatToShow"] == "MIDPOINT"
        assert payload["rthOnly"] is False


# =============================================================================
# Test get_account_status
# =============================================================================


class TestGetAccountStatus:
    """Tests for get_account_status tool."""

    @pytest.mark.asyncio
    async def test_get_account_status_default(self, mock_api_client):
        """Test account status with default account."""
        mock_api_client.get.side_effect = [
            create_mock_response(
                200,
                {
                    "accountId": "DU1234567",
                    "currency": "USD",
                    "netLiquidation": 100000.0,
                    "cash": 50000.0,
                    "buyingPower": 200000.0,
                },
            ),
            create_mock_response(
                200,
                {
                    "accountId": "DU1234567",
                    "positionCount": 2,
                    "positions": [
                        {"symbol": "AAPL", "quantity": 100},
                        {"symbol": "MSFT", "quantity": 50},
                    ],
                },
            ),
        ]

        with patch("mcp_server.main._app_context") as mock_ctx:
            mock_ctx.api_client = mock_api_client

            from mcp_server.main import get_account_status

            result = await get_account_status()

        assert result["summary"]["accountId"] == "DU1234567"
        assert result["summary"]["netLiquidation"] == 100000.0
        assert result["positionCount"] == 2
        assert len(result["positions"]) == 2

        # Verify both endpoints were called without params
        assert mock_api_client.get.call_count == 2

    @pytest.mark.asyncio
    async def test_get_account_status_specific_account(self, mock_api_client):
        """Test account status with specific account ID."""
        mock_api_client.get.side_effect = [
            create_mock_response(200, {"accountId": "U9876543"}),
            create_mock_response(200, {"positionCount": 0, "positions": []}),
        ]

        with patch("mcp_server.main._app_context") as mock_ctx:
            mock_ctx.api_client = mock_api_client

            from mcp_server.main import get_account_status

            await get_account_status(account_id="U9876543")

        # Verify params were passed
        call_args = mock_api_client.get.call_args_list[0]
        assert call_args[1]["params"]["account_id"] == "U9876543"


# =============================================================================
# Test get_pnl
# =============================================================================


class TestGetPnl:
    """Tests for get_pnl tool."""

    @pytest.mark.asyncio
    async def test_get_pnl_default(self, mock_api_client):
        """Test P&L with default parameters."""
        mock_api_client.get.return_value = create_mock_response(
            200,
            {
                "accountId": "DU1234567",
                "currency": "USD",
                "timeframe": "CURRENT",
                "realized": 500.0,
                "unrealized": 1200.0,
                "bySymbol": {"AAPL": {"symbol": "AAPL", "realized": 200.0, "unrealized": 800.0}},
            },
        )

        with patch("mcp_server.main._app_context") as mock_ctx:
            mock_ctx.api_client = mock_api_client

            from mcp_server.main import get_pnl

            result = await get_pnl()

        assert result["realized"] == 500.0
        assert result["unrealized"] == 1200.0
        assert "AAPL" in result["bySymbol"]

    @pytest.mark.asyncio
    async def test_get_pnl_with_timeframe(self, mock_api_client):
        """Test P&L with specific timeframe."""
        mock_api_client.get.return_value = create_mock_response(
            200,
            {
                "timeframe": "MTD",
                "realized": 1000.0,
                "unrealized": 500.0,
            },
        )

        with patch("mcp_server.main._app_context") as mock_ctx:
            mock_ctx.api_client = mock_api_client

            from mcp_server.main import get_pnl

            await get_pnl(timeframe="MTD")

        call_args = mock_api_client.get.call_args
        assert call_args[1]["params"]["timeframe"] == "MTD"


# =============================================================================
# Test preview_order
# =============================================================================


class TestPreviewOrder:
    """Tests for preview_order tool."""

    @pytest.mark.asyncio
    async def test_preview_market_order(self, mock_api_client):
        """Test preview of market order."""
        mock_api_client.post.return_value = create_mock_response(
            200,
            {
                "orderSpec": {},
                "estimatedPrice": 150.0,
                "estimatedNotional": 1500.0,
                "estimatedCommission": 1.0,
                "warnings": [],
            },
        )

        with patch("mcp_server.main._app_context") as mock_ctx:
            mock_ctx.api_client = mock_api_client

            from mcp_server.main import preview_order

            result = await preview_order(
                instrument_symbol="AAPL",
                instrument_security_type="STK",
                side="BUY",
                quantity=10,
                order_type="MKT",
            )

        assert result["estimatedPrice"] == 150.0
        assert result["estimatedNotional"] == 1500.0

        payload = mock_api_client.post.call_args[1]["json"]
        assert payload["instrument"]["symbol"] == "AAPL"
        assert payload["instrument"]["securityType"] == "STK"
        assert payload["side"] == "BUY"
        assert payload["quantity"] == 10
        assert payload["orderType"] == "MKT"

    @pytest.mark.asyncio
    async def test_preview_limit_order(self, mock_api_client):
        """Test preview of limit order."""
        mock_api_client.post.return_value = create_mock_response(
            200,
            {
                "estimatedPrice": 150.0,
                "estimatedNotional": 1500.0,
            },
        )

        with patch("mcp_server.main._app_context") as mock_ctx:
            mock_ctx.api_client = mock_api_client

            from mcp_server.main import preview_order

            await preview_order(
                instrument_symbol="AAPL",
                instrument_security_type="STK",
                side="BUY",
                quantity=10,
                order_type="LMT",
                limit_price=150.0,
                tif="GTC",
            )

        payload = mock_api_client.post.call_args[1]["json"]
        assert payload["orderType"] == "LMT"
        assert payload["limitPrice"] == 150.0
        assert payload["tif"] == "GTC"

    @pytest.mark.asyncio
    async def test_preview_bracket_order(self, mock_api_client):
        """Test preview of bracket order."""
        mock_api_client.post.return_value = create_mock_response(
            200,
            {
                "legs": [
                    {"role": "entry", "orderType": "LMT"},
                    {"role": "take_profit", "orderType": "LMT"},
                    {"role": "stop_loss", "orderType": "STP"},
                ],
                "totalNotional": 1500.0,
            },
        )

        with patch("mcp_server.main._app_context") as mock_ctx:
            mock_ctx.api_client = mock_api_client

            from mcp_server.main import preview_order

            result = await preview_order(
                instrument_symbol="AAPL",
                instrument_security_type="STK",
                side="BUY",
                quantity=10,
                order_type="BRACKET",
                limit_price=150.0,
                take_profit_price=160.0,
                stop_loss_price=145.0,
            )

        assert len(result["legs"]) == 3

        payload = mock_api_client.post.call_args[1]["json"]
        assert payload["orderType"] == "BRACKET"
        assert payload["limitPrice"] == 150.0
        assert payload["takeProfitPrice"] == 160.0
        assert payload["stopLossPrice"] == 145.0


# =============================================================================
# Test place_order
# =============================================================================


class TestPlaceOrder:
    """Tests for place_order tool."""

    @pytest.mark.asyncio
    async def test_place_order_accepted(self, mock_api_client):
        """Test successful order placement."""
        mock_api_client.post.return_value = create_mock_response(
            200,
            {
                "orderId": "12345",
                "status": "ACCEPTED",
                "orderStatus": {
                    "orderId": "12345",
                    "status": "SUBMITTED",
                    "filledQuantity": 0,
                    "remainingQuantity": 10,
                },
                "errors": [],
            },
        )

        with patch("mcp_server.main._app_context") as mock_ctx:
            mock_ctx.api_client = mock_api_client

            from mcp_server.main import place_order

            result = await place_order(
                instrument_symbol="AAPL",
                instrument_security_type="STK",
                side="BUY",
                quantity=10,
                order_type="LMT",
                limit_price=150.0,
            )

        assert result["orderId"] == "12345"
        assert result["status"] == "ACCEPTED"

    @pytest.mark.asyncio
    async def test_place_order_simulated(self, mock_api_client):
        """Test order placement when orders disabled."""
        mock_api_client.post.return_value = create_mock_response(
            200,
            {
                "orderId": None,
                "status": "SIMULATED",
                "errors": [],
            },
        )

        with patch("mcp_server.main._app_context") as mock_ctx:
            mock_ctx.api_client = mock_api_client

            from mcp_server.main import place_order

            result = await place_order(
                instrument_symbol="AAPL",
                instrument_security_type="STK",
                side="BUY",
                quantity=10,
                order_type="MKT",
            )

        assert result["status"] == "SIMULATED"

    @pytest.mark.asyncio
    async def test_place_order_with_client_id(self, mock_api_client):
        """Test order placement with client order ID."""
        mock_api_client.post.return_value = create_mock_response(
            200,
            {
                "orderId": "12345",
                "clientOrderId": "my-order-123",
                "status": "ACCEPTED",
            },
        )

        with patch("mcp_server.main._app_context") as mock_ctx:
            mock_ctx.api_client = mock_api_client

            from mcp_server.main import place_order

            await place_order(
                instrument_symbol="AAPL",
                instrument_security_type="STK",
                side="BUY",
                quantity=10,
                order_type="MKT",
                client_order_id="my-order-123",
            )

        payload = mock_api_client.post.call_args[1]["json"]
        assert payload["clientOrderId"] == "my-order-123"


# =============================================================================
# Test get_order_status
# =============================================================================


class TestGetOrderStatus:
    """Tests for get_order_status tool."""

    @pytest.mark.asyncio
    async def test_get_order_status_submitted(self, mock_api_client):
        """Test getting status of submitted order."""
        mock_api_client.get.return_value = create_mock_response(
            200,
            {
                "orderId": "12345",
                "status": "SUBMITTED",
                "filledQuantity": 0,
                "remainingQuantity": 10,
                "avgFillPrice": 0,
                "lastUpdate": "2024-01-15T14:30:00Z",
                "warnings": [],
            },
        )

        with patch("mcp_server.main._app_context") as mock_ctx:
            mock_ctx.api_client = mock_api_client

            from mcp_server.main import get_order_status

            result = await get_order_status(order_id="12345")

        assert result["orderId"] == "12345"
        assert result["status"] == "SUBMITTED"
        assert result["remainingQuantity"] == 10

        mock_api_client.get.assert_called_once_with("/orders/12345/status")

    @pytest.mark.asyncio
    async def test_get_order_status_filled(self, mock_api_client):
        """Test getting status of filled order."""
        mock_api_client.get.return_value = create_mock_response(
            200,
            {
                "orderId": "12345",
                "status": "FILLED",
                "filledQuantity": 10,
                "remainingQuantity": 0,
                "avgFillPrice": 150.25,
            },
        )

        with patch("mcp_server.main._app_context") as mock_ctx:
            mock_ctx.api_client = mock_api_client

            from mcp_server.main import get_order_status

            result = await get_order_status(order_id="12345")

        assert result["status"] == "FILLED"
        assert result["avgFillPrice"] == 150.25


# =============================================================================
# Test cancel_order
# =============================================================================


class TestCancelOrder:
    """Tests for cancel_order tool."""

    @pytest.mark.asyncio
    async def test_cancel_order_success(self, mock_api_client):
        """Test successful order cancellation."""
        mock_api_client.post.return_value = create_mock_response(
            200,
            {
                "orderId": "12345",
                "status": "CANCELLED",
                "message": "Order cancelled successfully",
            },
        )

        with patch("mcp_server.main._app_context") as mock_ctx:
            mock_ctx.api_client = mock_api_client

            from mcp_server.main import cancel_order

            result = await cancel_order(order_id="12345")

        assert result["orderId"] == "12345"
        assert result["status"] == "CANCELLED"

        mock_api_client.post.assert_called_once_with("/orders/12345/cancel")

    @pytest.mark.asyncio
    async def test_cancel_order_already_filled(self, mock_api_client):
        """Test cancelling already filled order."""
        mock_api_client.post.return_value = create_mock_response(
            200,
            {
                "orderId": "12345",
                "status": "ALREADY_FILLED",
                "message": "Order was already filled",
            },
        )

        with patch("mcp_server.main._app_context") as mock_ctx:
            mock_ctx.api_client = mock_api_client

            from mcp_server.main import cancel_order

            result = await cancel_order(order_id="12345")

        assert result["status"] == "ALREADY_FILLED"


# =============================================================================
# Test Payload Construction
# =============================================================================


class TestPayloadConstruction:
    """Tests for order payload construction."""

    @pytest.mark.asyncio
    async def test_trailing_stop_payload(self, mock_api_client):
        """Test trailing stop order payload."""
        mock_api_client.post.return_value = create_mock_response(200, {})

        with patch("mcp_server.main._app_context") as mock_ctx:
            mock_ctx.api_client = mock_api_client

            from mcp_server.main import preview_order

            await preview_order(
                instrument_symbol="AAPL",
                instrument_security_type="STK",
                side="SELL",
                quantity=10,
                order_type="TRAIL",
                trailing_percent=5.0,
            )

        payload = mock_api_client.post.call_args[1]["json"]
        assert payload["orderType"] == "TRAIL"
        assert payload["trailingPercent"] == 5.0
        assert payload["side"] == "SELL"

    @pytest.mark.asyncio
    async def test_futures_order_payload(self, mock_api_client):
        """Test futures order payload with expiry."""
        mock_api_client.post.return_value = create_mock_response(200, {})

        with patch("mcp_server.main._app_context") as mock_ctx:
            mock_ctx.api_client = mock_api_client

            from mcp_server.main import place_order

            await place_order(
                instrument_symbol="MES",
                instrument_security_type="FUT",
                instrument_exchange="GLOBEX",
                instrument_currency="USD",
                instrument_expiry="2024-12-20",
                side="BUY",
                quantity=1,
                order_type="LMT",
                limit_price=4500.0,
            )

        payload = mock_api_client.post.call_args[1]["json"]
        assert payload["instrument"]["symbol"] == "MES"
        assert payload["instrument"]["securityType"] == "FUT"
        assert payload["instrument"]["exchange"] == "GLOBEX"
        assert payload["instrument"]["currency"] == "USD"
        assert payload["instrument"]["expiry"] == "2024-12-20"
