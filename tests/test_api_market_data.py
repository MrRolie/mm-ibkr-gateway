"""
Tests for market data API endpoints.

Includes:
- POST /market-data/quote
- POST /market-data/historical

Unit tests use mocked IBKR client.
Integration tests (marked) require running IBKR Gateway.
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
    from api.server import app
    from api.dependencies import get_client_manager

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
# Quote Endpoint Tests
# =============================================================================


class TestQuoteEndpoint:
    """Tests for POST /market-data/quote."""

    def test_quote_returns_503_when_not_connected(self, client_disconnected):
        """Quote endpoint returns 503 when IBKR not connected."""
        response = client_disconnected.post(
            "/market-data/quote",
            json={
                "symbol": "AAPL",
                "securityType": "STK",
                "exchange": "SMART",
                "currency": "USD",
            },
        )

        # Without IBKR connection, should return 503
        assert response.status_code == 503
        data = response.json()
        assert data["error_code"] == "IBKR_CONNECTION_ERROR"

    def test_quote_missing_symbol(self, client):
        """Quote request without symbol should return 422."""
        response = client.post(
            "/market-data/quote",
            json={
                "securityType": "STK",
            },
        )

        assert response.status_code == 422  # Validation error

    def test_quote_missing_security_type(self, client):
        """Quote request without securityType should return 422."""
        response = client.post(
            "/market-data/quote",
            json={
                "symbol": "AAPL",
            },
        )

        assert response.status_code == 422


# =============================================================================
# Historical Bars Endpoint Tests
# =============================================================================


class TestHistoricalBarsEndpoint:
    """Tests for POST /market-data/historical."""

    def test_historical_returns_503_when_not_connected(self, client_disconnected):
        """Historical endpoint returns 503 when IBKR not connected."""
        response = client_disconnected.post(
            "/market-data/historical",
            json={
                "symbol": "AAPL",
                "securityType": "STK",
                "barSize": "1d",
                "duration": "5d",
                "whatToShow": "TRADES",
                "rthOnly": True,
            },
        )

        assert response.status_code == 503

    def test_historical_missing_bar_size(self, client):
        """Historical request without barSize should return 422."""
        response = client.post(
            "/market-data/historical",
            json={
                "symbol": "AAPL",
                "securityType": "STK",
                "duration": "5d",
            },
        )

        assert response.status_code == 422

    def test_historical_missing_duration(self, client):
        """Historical request without duration should return 422."""
        response = client.post(
            "/market-data/historical",
            json={
                "symbol": "AAPL",
                "securityType": "STK",
                "barSize": "1d",
            },
        )

        assert response.status_code == 422


# =============================================================================
# Authentication Tests
# =============================================================================


class TestMarketDataAuth:
    """Tests for API key authentication on market data endpoints."""

    def test_quote_requires_api_key_when_set(self):
        """Quote endpoint should require API key when API_KEY is set."""
        os.environ["API_KEY"] = "test-secret-key"
        from ibkr_core.config import reset_config
        reset_config()

        from api.server import app
        test_client = TestClient(app)

        response = test_client.post(
            "/market-data/quote",
            json={
                "symbol": "AAPL",
                "securityType": "STK",
            },
        )

        assert response.status_code == 401
        data = response.json()
        assert data["detail"]["error_code"] == "UNAUTHORIZED"

        os.environ.pop("API_KEY", None)

    def test_quote_rejects_invalid_api_key(self):
        """Quote endpoint should reject invalid API key."""
        os.environ["API_KEY"] = "correct-key"
        from ibkr_core.config import reset_config
        reset_config()

        from api.server import app
        test_client = TestClient(app)

        response = test_client.post(
            "/market-data/quote",
            json={
                "symbol": "AAPL",
                "securityType": "STK",
            },
            headers={"X-API-Key": "wrong-key"},
        )

        assert response.status_code == 401

        os.environ.pop("API_KEY", None)

    def test_quote_accepts_valid_api_key(self):
        """Quote endpoint should accept valid API key (connection may fail, but auth passes)."""
        os.environ["API_KEY"] = "test-secret-key"
        from ibkr_core.config import reset_config
        reset_config()

        from api.server import app
        from api.dependencies import get_client_manager

        # Create mock client manager
        mock_manager = MagicMock()
        mock_manager.is_connected = False
        mock_manager.get_client = AsyncMock(
            side_effect=IBKRConnectionError("IBKR Gateway not available")
        )
        app.dependency_overrides[get_client_manager] = lambda: mock_manager

        test_client = TestClient(app)

        response = test_client.post(
            "/market-data/quote",
            json={
                "symbol": "AAPL",
                "securityType": "STK",
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


@pytest.mark.skipif(
    not should_run_integration_tests(),
    reason="Integration tests skipped. Set RUN_IBKR_INTEGRATION_TESTS=true to run.",
)
class TestMarketDataIntegration:
    """Integration tests for market data endpoints."""

    @pytest.fixture
    def integration_client(self):
        """Create client for integration tests."""
        os.environ["TRADING_MODE"] = "paper"
        os.environ["ORDERS_ENABLED"] = "false"
        os.environ.pop("API_KEY", None)

        from ibkr_core.config import reset_config
        reset_config()

        from api.server import app
        return TestClient(app)

    def test_quote_aapl_integration(self, integration_client):
        """Get live quote for AAPL."""
        response = integration_client.post(
            "/market-data/quote",
            json={
                "symbol": "AAPL",
                "securityType": "STK",
                "exchange": "SMART",
                "currency": "USD",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["symbol"] == "AAPL"
        assert data["conId"] > 0
        # At least one price should be non-zero
        assert data["bid"] > 0 or data["ask"] > 0 or data["last"] > 0

    def test_historical_aapl_integration(self, integration_client):
        """Get historical bars for AAPL."""
        response = integration_client.post(
            "/market-data/historical",
            json={
                "symbol": "AAPL",
                "securityType": "STK",
                "exchange": "SMART",
                "currency": "USD",
                "barSize": "1d",
                "duration": "5d",
                "whatToShow": "TRADES",
                "rthOnly": True,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["symbol"] == "AAPL"
        assert data["barCount"] > 0
        assert len(data["bars"]) > 0
        assert data["bars"][0]["open"] > 0
