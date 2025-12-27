"""
Tests for order API endpoints.

Includes:
- POST /orders/preview
- POST /orders
- POST /orders/{order_id}/cancel
- GET /orders/{order_id}/status
- GET /orders/open
"""

import os
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from ibkr_core.client import ConnectionError as IBKRConnectionError


@pytest.fixture(autouse=True)
def reset_env():
    """Reset environment before each test."""
    os.environ["TRADING_MODE"] = "paper"
    os.environ["ORDERS_ENABLED"] = "false"
    os.environ.pop("API_KEY", None)

    from ibkr_core.config import reset_config

    reset_config()
    yield
    reset_config()


@pytest.fixture
def client():
    """Create a test client for the API."""
    from api.server import app

    return TestClient(app)


@pytest.fixture
def client_disconnected():
    """Create a test client with mocked IBKR client manager as disconnected."""
    from api.dependencies import get_client_manager
    from api.server import app

    # Create mock client manager
    mock_manager = MagicMock()
    mock_manager.is_connected = False
    mock_manager.get_client = AsyncMock(
        side_effect=IBKRConnectionError("IBKR Gateway not available")
    )

    # Override the dependency
    app.dependency_overrides[get_client_manager] = lambda: mock_manager

    client = TestClient(app)
    yield client

    # Clean up
    app.dependency_overrides.clear()


# =============================================================================
# Order Preview Tests
# =============================================================================


class TestOrderPreviewEndpoint:
    """Tests for POST /orders/preview."""

    def test_preview_returns_503_when_not_connected(self, client_disconnected):
        """Preview returns 503 when IBKR not connected."""
        response = client_disconnected.post(
            "/orders/preview",
            json={
                "instrument": {
                    "symbol": "AAPL",
                    "securityType": "STK",
                },
                "side": "BUY",
                "quantity": 10,
                "orderType": "LMT",
                "limitPrice": 150.0,
            },
        )

        assert response.status_code == 503

    def test_preview_validation_error_invalid_side(self, client):
        """Preview with invalid side should return 422."""
        response = client.post(
            "/orders/preview",
            json={
                "instrument": {
                    "symbol": "AAPL",
                    "securityType": "STK",
                },
                "side": "INVALID",
                "quantity": 10,
                "orderType": "LMT",
                "limitPrice": 150.0,
            },
        )

        assert response.status_code == 422

    def test_preview_validation_error_missing_instrument(self, client):
        """Preview without instrument should return 422."""
        response = client.post(
            "/orders/preview",
            json={
                "side": "BUY",
                "quantity": 10,
                "orderType": "LMT",
                "limitPrice": 150.0,
            },
        )

        assert response.status_code == 422


# =============================================================================
# Place Order Tests
# =============================================================================


class TestPlaceOrderEndpoint:
    """Tests for POST /orders."""

    def test_place_order_returns_503_when_not_connected(self, client_disconnected):
        """Place order returns 503 when IBKR not connected."""
        response = client_disconnected.post(
            "/orders",
            json={
                "instrument": {
                    "symbol": "AAPL",
                    "securityType": "STK",
                },
                "side": "BUY",
                "quantity": 10,
                "orderType": "LMT",
                "limitPrice": 150.0,
            },
        )

        assert response.status_code == 503

    def test_place_order_invalid_quantity(self, client):
        """Place order with zero quantity returns 422."""
        response = client.post(
            "/orders",
            json={
                "instrument": {
                    "symbol": "AAPL",
                    "securityType": "STK",
                },
                "side": "BUY",
                "quantity": 0,  # Invalid
                "orderType": "LMT",
                "limitPrice": 150.0,
            },
        )

        assert response.status_code == 422

    def test_place_order_missing_order_type(self, client):
        """Place order without orderType returns 422."""
        response = client.post(
            "/orders",
            json={
                "instrument": {
                    "symbol": "AAPL",
                    "securityType": "STK",
                },
                "side": "BUY",
                "quantity": 10,
            },
        )

        assert response.status_code == 422


# =============================================================================
# Cancel Order Tests
# =============================================================================


class TestCancelOrderEndpoint:
    """Tests for POST /orders/{order_id}/cancel."""

    def test_cancel_order_returns_503_when_not_connected(self, client_disconnected):
        """Cancel order returns 503 when IBKR not connected."""
        response = client_disconnected.post("/orders/12345/cancel")

        assert response.status_code == 503


# =============================================================================
# Order Status Tests
# =============================================================================


class TestOrderStatusEndpoint:
    """Tests for GET /orders/{order_id}/status."""

    def test_get_order_status_returns_503_when_not_connected(self, client_disconnected):
        """Get order status returns 503 when IBKR not connected."""
        response = client_disconnected.get("/orders/12345/status")

        assert response.status_code == 503


# =============================================================================
# Open Orders Tests
# =============================================================================


class TestOpenOrdersEndpoint:
    """Tests for GET /orders/open."""

    def test_get_open_orders_returns_503_when_not_connected(self, client_disconnected):
        """Get open orders returns 503 when IBKR not connected."""
        response = client_disconnected.get("/orders/open")

        assert response.status_code == 503


# =============================================================================
# Authentication Tests
# =============================================================================


class TestOrdersAuth:
    """Tests for API key authentication on order endpoints."""

    def test_orders_require_api_key_when_set(self):
        """Order endpoints should require API key when API_KEY is set."""
        os.environ["API_KEY"] = "test-secret-key"
        from ibkr_core.config import reset_config

        reset_config()

        from api.server import app

        test_client = TestClient(app)

        response = test_client.post(
            "/orders/preview",
            json={
                "instrument": {
                    "symbol": "AAPL",
                    "securityType": "STK",
                },
                "side": "BUY",
                "quantity": 10,
                "orderType": "LMT",
                "limitPrice": 150.0,
            },
        )

        assert response.status_code == 401
        data = response.json()
        assert data["detail"]["error_code"] == "UNAUTHORIZED"

        os.environ.pop("API_KEY", None)

    def test_orders_accept_valid_api_key(self):
        """Order endpoint should accept valid API key."""
        os.environ["API_KEY"] = "test-secret-key"
        from ibkr_core.config import reset_config

        reset_config()

        from api.dependencies import get_client_manager
        from api.server import app

        # Create mock client manager
        mock_manager = MagicMock()
        mock_manager.is_connected = False
        mock_manager.get_client = AsyncMock(
            side_effect=IBKRConnectionError("IBKR Gateway not available")
        )
        app.dependency_overrides[get_client_manager] = lambda: mock_manager

        test_client = TestClient(app)

        response = test_client.post(
            "/orders/preview",
            json={
                "instrument": {
                    "symbol": "AAPL",
                    "securityType": "STK",
                },
                "side": "BUY",
                "quantity": 10,
                "orderType": "LMT",
                "limitPrice": 150.0,
            },
            headers={"X-API-Key": "test-secret-key"},
        )

        # Auth passes but IBKR connection fails -> 503
        assert response.status_code == 503

        os.environ.pop("API_KEY", None)
        app.dependency_overrides.clear()


# =============================================================================
# Integration Tests (require running IBKR Gateway)
# =============================================================================


def should_run_integration_tests():
    """Check if integration tests should run."""
    return os.environ.get("RUN_IBKR_INTEGRATION_TESTS", "").lower() in ("true", "1", "yes")


def should_enable_orders():
    """Check if orders should be enabled for tests."""
    return os.environ.get("ORDERS_ENABLED", "").lower() in ("true", "1", "yes")


@pytest.mark.skipif(
    not should_run_integration_tests(),
    reason="Integration tests skipped. Set RUN_IBKR_INTEGRATION_TESTS=true to run.",
)
class TestOrdersIntegration:
    """Integration tests for order endpoints."""

    @pytest.fixture
    def integration_client(self):
        """Create client for integration tests."""
        os.environ["TRADING_MODE"] = "paper"
        os.environ.pop("API_KEY", None)

        from ibkr_core.config import reset_config

        reset_config()

        from api.server import app

        return TestClient(app)

    def test_preview_order_integration(self, integration_client):
        """Preview order against live gateway."""
        response = integration_client.post(
            "/orders/preview",
            json={
                "instrument": {
                    "symbol": "AAPL",
                    "securityType": "STK",
                    "exchange": "SMART",
                    "currency": "USD",
                },
                "side": "BUY",
                "quantity": 1,
                "orderType": "LMT",
                "limitPrice": 100.0,  # Far from market
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["estimatedPrice"] is not None
        assert data["estimatedNotional"] is not None

    def test_place_order_simulated_integration(self, integration_client):
        """Place order returns SIMULATED when disabled."""
        os.environ["ORDERS_ENABLED"] = "false"
        from ibkr_core.config import reset_config

        reset_config()

        response = integration_client.post(
            "/orders",
            json={
                "instrument": {
                    "symbol": "AAPL",
                    "securityType": "STK",
                    "exchange": "SMART",
                    "currency": "USD",
                },
                "side": "BUY",
                "quantity": 1,
                "orderType": "LMT",
                "limitPrice": 100.0,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "SIMULATED"

    @pytest.mark.skipif(
        not should_enable_orders(),
        reason="Order placement tests skipped. Set ORDERS_ENABLED=true to run.",
    )
    def test_place_and_cancel_order_integration(self, integration_client):
        """Place and cancel a real order (paper trading only)."""
        os.environ["ORDERS_ENABLED"] = "true"
        os.environ["TRADING_MODE"] = "paper"
        from ibkr_core.config import reset_config

        reset_config()

        # Place far-from-market order
        response = integration_client.post(
            "/orders",
            json={
                "instrument": {
                    "symbol": "AAPL",
                    "securityType": "STK",
                    "exchange": "SMART",
                    "currency": "USD",
                },
                "side": "BUY",
                "quantity": 1,
                "orderType": "LMT",
                "limitPrice": 50.0,  # Very far from market
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] in ("ACCEPTED", "SIMULATED")

        if data["status"] == "ACCEPTED":
            order_id = data["orderId"]

            # Get status
            status_response = integration_client.get(f"/orders/{order_id}/status")
            assert status_response.status_code == 200

            # Cancel
            cancel_response = integration_client.post(f"/orders/{order_id}/cancel")
            assert cancel_response.status_code == 200
            assert cancel_response.json()["status"] in ("CANCELLED", "ALREADY_FILLED")
