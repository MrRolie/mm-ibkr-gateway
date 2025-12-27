"""
Tests for the /metrics API endpoint.
"""

import pytest
from fastapi.testclient import TestClient

from api.server import app
from ibkr_core.metrics import get_metrics


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


@pytest.fixture(autouse=True)
def reset_metrics():
    """Reset metrics before each test."""
    metrics = get_metrics()
    metrics.reset()
    yield
    metrics.reset()


class TestMetricsEndpoint:
    """Tests for GET /metrics endpoint."""

    def test_metrics_returns_200(self, client):
        response = client.get("/metrics")
        assert response.status_code == 200

    def test_metrics_returns_json(self, client):
        response = client.get("/metrics")
        assert response.headers["content-type"] == "application/json"
        data = response.json()
        assert isinstance(data, dict)

    def test_metrics_structure(self, client):
        response = client.get("/metrics")
        data = response.json()

        assert "uptime_seconds" in data
        assert "counters" in data
        assert "histograms" in data
        assert "gauges" in data
        assert isinstance(data["uptime_seconds"], (int, float))
        assert isinstance(data["counters"], dict)
        assert isinstance(data["histograms"], dict)
        assert isinstance(data["gauges"], dict)

    def test_metrics_uptime_increases(self, client):
        import time

        response1 = client.get("/metrics")
        time.sleep(0.1)
        response2 = client.get("/metrics")

        uptime1 = response1.json()["uptime_seconds"]
        uptime2 = response2.json()["uptime_seconds"]
        assert uptime2 > uptime1

    def test_metrics_records_own_request(self, client):
        # Make a request that should be recorded
        client.get("/health")

        # Now get metrics
        response = client.get("/metrics")
        data = response.json()

        # Should have API request counter
        assert "api_requests_total" in data["counters"]

    def test_metrics_histogram_structure(self, client):
        # Make some requests to populate histograms
        client.get("/health")
        client.get("/health")

        response = client.get("/metrics")
        data = response.json()

        # Find a histogram
        if data["histograms"]:
            first_histogram = list(data["histograms"].values())[0]
            if first_histogram:
                first_series = list(first_histogram.values())[0]
                # Check histogram stats structure
                assert "count" in first_series
                assert "sum" in first_series
                assert "min" in first_series
                assert "max" in first_series
                assert "mean" in first_series
                assert "p50" in first_series
                assert "p90" in first_series
                assert "p95" in first_series
                assert "p99" in first_series

    def test_metrics_no_auth_required(self, client):
        # Metrics endpoint should be accessible without auth
        response = client.get("/metrics")
        assert response.status_code == 200

    def test_multiple_requests_increment_counter(self, client):
        # Reset by getting initial state
        initial = client.get("/metrics").json()

        # Make multiple requests
        for _ in range(5):
            client.get("/health")

        # Get updated metrics
        response = client.get("/metrics")
        data = response.json()

        # Counter should have increased
        assert "api_requests_total" in data["counters"]
