"""
Tests for account API endpoints.

Includes:
- GET /account/summary
- GET /account/positions
- GET /account/pnl
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
# Account Summary Tests
# =============================================================================


class TestAccountSummaryEndpoint:
    """Tests for GET /account/summary."""

    def test_summary_returns_503_when_not_connected(self, client_disconnected):
        """Account summary returns 503 when IBKR not connected."""
        response = client_disconnected.get("/account/summary")

        assert response.status_code == 503
        data = response.json()
        assert data["error_code"] == "IBKR_CONNECTION_ERROR"

    def test_summary_accepts_account_id_param(self, client_disconnected):
        """Account summary should accept account_id query parameter."""
        response = client_disconnected.get("/account/summary?account_id=DU9999999")

        # Still fails due to no IBKR, but validates param is accepted
        assert response.status_code == 503


# =============================================================================
# Positions Tests
# =============================================================================


class TestPositionsEndpoint:
    """Tests for GET /account/positions."""

    def test_positions_returns_503_when_not_connected(self, client_disconnected):
        """Positions endpoint returns 503 when IBKR not connected."""
        response = client_disconnected.get("/account/positions")

        assert response.status_code == 503

    def test_positions_accepts_account_id_param(self, client_disconnected):
        """Positions should accept account_id query parameter."""
        response = client_disconnected.get("/account/positions?account_id=DU9999999")

        assert response.status_code == 503


# =============================================================================
# PnL Tests
# =============================================================================


class TestPnlEndpoint:
    """Tests for GET /account/pnl."""

    def test_pnl_returns_503_when_not_connected(self, client_disconnected):
        """P&L endpoint returns 503 when IBKR not connected."""
        response = client_disconnected.get("/account/pnl")

        assert response.status_code == 503

    def test_pnl_accepts_account_id_param(self, client_disconnected):
        """P&L should accept account_id query parameter."""
        response = client_disconnected.get("/account/pnl?account_id=DU9999999")

        assert response.status_code == 503


# =============================================================================
# Authentication Tests
# =============================================================================


class TestAccountAuth:
    """Tests for API key authentication on account endpoints."""

    def test_account_requires_api_key_when_set(self):
        """Account endpoints should require API key when API_KEY is set."""
        os.environ["API_KEY"] = "test-secret-key"
        from ibkr_core.config import reset_config

        reset_config()

        from api.server import app

        test_client = TestClient(app)

        response = test_client.get("/account/summary")

        assert response.status_code == 401
        data = response.json()
        assert data["detail"]["error_code"] == "UNAUTHORIZED"

        os.environ.pop("API_KEY", None)

    def test_account_accepts_valid_api_key(self):
        """Account endpoint should accept valid API key."""
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

        response = test_client.get(
            "/account/summary",
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
class TestAccountIntegration:
    """Integration tests for account endpoints."""

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

    def test_account_summary_integration(self, integration_client):
        """Get live account summary."""
        response = integration_client.get("/account/summary")

        assert response.status_code == 200
        data = response.json()
        assert "accountId" in data
        assert "netLiquidation" in data
        assert "currency" in data
        assert data["netLiquidation"] >= 0

    def test_positions_integration(self, integration_client):
        """Get live positions."""
        response = integration_client.get("/account/positions")

        assert response.status_code == 200
        data = response.json()
        assert "accountId" in data
        assert "positions" in data
        assert "positionCount" in data
        # positionCount should match positions length
        assert data["positionCount"] == len(data["positions"])

    def test_pnl_integration(self, integration_client):
        """Get live P&L."""
        response = integration_client.get("/account/pnl")

        assert response.status_code == 200
        data = response.json()
        assert "accountId" in data
        assert "realized" in data
        assert "unrealized" in data
