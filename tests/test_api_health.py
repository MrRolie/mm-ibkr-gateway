"""
Tests for the /health endpoint.

These tests verify the health check endpoint works correctly
both with and without IBKR connection.
"""

import os
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import datetime, timezone

from fastapi.testclient import TestClient


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


class TestHealthEndpoint:
    """Tests for GET /health."""

    def test_health_returns_200_degraded_when_not_connected(self, client):
        """Health endpoint should return 200 with degraded status when IBKR not connected."""
        # The test client won't have IBKR, so it will be degraded
        response = client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "ibkr_connected" in data
        assert "trading_mode" in data
        assert "orders_enabled" in data
        # Without IBKR connection, status should be degraded
        assert data["status"] == "degraded"
        assert data["ibkr_connected"] is False

    def test_health_shows_trading_mode(self, client):
        """Health should show current trading mode."""
        response = client.get("/health")

        data = response.json()
        assert data["trading_mode"] == "paper"

    def test_health_shows_orders_enabled(self, client):
        """Health should show orders enabled status."""
        response = client.get("/health")

        data = response.json()
        assert data["orders_enabled"] is False

    def test_health_shows_version(self, client):
        """Health should include API version."""
        response = client.get("/health")

        data = response.json()
        assert "version" in data
        assert data["version"] == "0.1.0"


class TestHealthNoAuth:
    """Verify health endpoint does not require authentication."""

    def test_health_no_api_key_required_when_auth_disabled(self, client):
        """Health check should work without API key when auth is disabled."""
        # Note: No X-API-Key header, and API_KEY env var is not set
        response = client.get("/health")

        assert response.status_code == 200

    def test_health_no_api_key_required_when_auth_enabled(self):
        """Health check should work without API key even when auth is enabled."""
        os.environ["API_KEY"] = "test-secret-key"
        from ibkr_core.config import reset_config
        reset_config()

        from api.server import app
        test_client = TestClient(app)

        # Note: No X-API-Key header
        response = test_client.get("/health")

        # Health endpoint doesn't require auth
        assert response.status_code == 200

        os.environ.pop("API_KEY", None)
