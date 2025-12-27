"""
Integration tests for metrics collection during operations.

Verifies that metrics are properly populated when:
- API requests are made
- IBKR operations are performed
- Orders are processed
"""

from unittest.mock import MagicMock, patch

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


class TestAPIMetricsIntegration:
    """Tests for metrics populated during API operations."""

    def test_health_check_records_metrics(self, client):
        # Make health request
        response = client.get("/health")
        assert response.status_code == 200

        # Check metrics recorded
        metrics = get_metrics()
        all_data = metrics.get_all_metrics()

        assert "api_requests_total" in all_data["counters"]
        assert "api_request_duration_seconds" in all_data["histograms"]

    def test_api_request_labels(self, client):
        # Make requests to different endpoints
        client.get("/health")
        client.get("/metrics")

        metrics = get_metrics()
        all_data = metrics.get_all_metrics()

        # Should have counters with different endpoint labels
        counters = all_data["counters"]["api_requests_total"]
        assert len(counters) >= 2

    def test_api_latency_histogram(self, client):
        # Make several requests
        for _ in range(5):
            client.get("/health")

        metrics = get_metrics()
        histograms = metrics.get_all_metrics()["histograms"]

        assert "api_request_duration_seconds" in histograms
        # Find health endpoint histogram
        for label, stats in histograms["api_request_duration_seconds"].items():
            if "/health" in label:
                assert stats["count"] >= 5
                assert stats["mean"] > 0
                break

    def test_error_response_recorded(self, client):
        # Make a request that will fail (invalid endpoint)
        response = client.get("/nonexistent")
        assert response.status_code == 404

        metrics = get_metrics()
        all_data = metrics.get_all_metrics()

        # Should still record the request
        assert "api_requests_total" in all_data["counters"]


class TestIBKRMetricsIntegration:
    """Tests for metrics during IBKR operations."""

    def test_connection_status_gauge(self):
        from ibkr_core.metrics import set_connection_status

        # Simulate connection status changes
        set_connection_status("paper", connected=True)

        metrics = get_metrics()
        assert metrics.gauge_get("ibkr_connection_status", labels={"mode": "paper"}) == 1.0

        set_connection_status("paper", connected=False)
        assert metrics.gauge_get("ibkr_connection_status", labels={"mode": "paper"}) == 0.0

    def test_ibkr_operation_counter(self):
        from ibkr_core.metrics import record_ibkr_operation

        # Simulate IBKR operations
        record_ibkr_operation("connect", "success", 0.5)
        record_ibkr_operation("connect", "success", 0.3)
        record_ibkr_operation("connect", "error", 1.0)

        metrics = get_metrics()
        all_data = metrics.get_all_metrics()

        assert "ibkr_operations_total" in all_data["counters"]

        # Check specific labels
        success_count = metrics.counter_get(
            "ibkr_operations_total", labels={"operation": "connect", "status": "success"}
        )
        error_count = metrics.counter_get(
            "ibkr_operations_total", labels={"operation": "connect", "status": "error"}
        )

        assert success_count == 2
        assert error_count == 1

    def test_ibkr_operation_histogram(self):
        from ibkr_core.metrics import record_ibkr_operation

        # Simulate operations with different durations
        record_ibkr_operation("connect", "success", 0.5)
        record_ibkr_operation("connect", "success", 0.3)
        record_ibkr_operation("connect", "success", 0.7)

        metrics = get_metrics()
        stats = metrics.histogram_get(
            "ibkr_operation_duration_seconds", labels={"operation": "connect"}
        )

        assert stats["count"] == 3
        assert stats["min"] == 0.3
        assert stats["max"] == 0.7
        assert abs(stats["mean"] - 0.5) < 0.01


class TestOrderMetricsIntegration:
    """Tests for metrics during order operations."""

    def test_order_event_counter(self):
        from ibkr_core.metrics import record_order_event

        # Simulate order lifecycle
        record_order_event("submitted", "AAPL", "pending")
        record_order_event("accepted", "AAPL", "working")
        record_order_event("filled", "AAPL", "filled", duration_seconds=2.5)

        metrics = get_metrics()
        all_data = metrics.get_all_metrics()

        assert "orders_total" in all_data["counters"]

    def test_order_time_to_fill_histogram(self):
        from ibkr_core.metrics import record_order_event

        # Simulate multiple fills
        record_order_event("filled", "AAPL", "filled", duration_seconds=1.0)
        record_order_event("filled", "AAPL", "filled", duration_seconds=2.0)
        record_order_event("filled", "MSFT", "filled", duration_seconds=1.5)

        metrics = get_metrics()

        # Check AAPL histogram
        aapl_stats = metrics.histogram_get(
            "order_time_to_fill_seconds", labels={"symbol": "AAPL"}
        )
        assert aapl_stats["count"] == 2
        assert aapl_stats["min"] == 1.0
        assert aapl_stats["max"] == 2.0

        # Check MSFT histogram
        msft_stats = metrics.histogram_get(
            "order_time_to_fill_seconds", labels={"symbol": "MSFT"}
        )
        assert msft_stats["count"] == 1

    def test_active_orders_gauge(self):
        from ibkr_core.metrics import update_active_orders

        # Simulate changing order states
        update_active_orders("pending", 3)
        update_active_orders("working", 2)
        update_active_orders("filled", 5)

        metrics = get_metrics()

        assert metrics.gauge_get("active_orders", labels={"status": "pending"}) == 3.0
        assert metrics.gauge_get("active_orders", labels={"status": "working"}) == 2.0
        assert metrics.gauge_get("active_orders", labels={"status": "filled"}) == 5.0

        # Simulate order state changes
        update_active_orders("pending", 1)
        update_active_orders("working", 3)

        assert metrics.gauge_get("active_orders", labels={"status": "pending"}) == 1.0
        assert metrics.gauge_get("active_orders", labels={"status": "working"}) == 3.0


class TestMetricsPercentiles:
    """Tests for histogram percentile calculations."""

    def test_percentile_accuracy(self):
        metrics = get_metrics()

        # Add values from 1 to 100
        for i in range(1, 101):
            metrics.histogram_observe("test_percentiles", float(i))

        stats = metrics.histogram_get("test_percentiles")

        # Check percentiles are approximately correct
        assert 49 <= stats["p50"] <= 51, f"p50 was {stats['p50']}"
        assert 89 <= stats["p90"] <= 91, f"p90 was {stats['p90']}"
        assert 94 <= stats["p95"] <= 96, f"p95 was {stats['p95']}"
        assert 98 <= stats["p99"] <= 100, f"p99 was {stats['p99']}"

    def test_percentiles_with_skewed_distribution(self):
        metrics = get_metrics()

        # Most requests are fast (0.1s), few are slow (1.0s)
        for _ in range(90):
            metrics.histogram_observe("skewed", 0.1)
        for _ in range(10):
            metrics.histogram_observe("skewed", 1.0)

        stats = metrics.histogram_get("skewed")

        # p50, p90 should be near 0.1
        assert stats["p50"] < 0.2
        # p99 should be near 1.0
        assert stats["p99"] >= 0.9
