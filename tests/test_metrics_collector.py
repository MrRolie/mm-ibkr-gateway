"""
Tests for metrics collection and aggregation.

Tests the MetricsCollector singleton, Counter, Gauge, and Histogram
data types, and convenience functions.
"""

import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from ibkr_core.metrics import (
    Counter,
    Gauge,
    Histogram,
    MetricsCollector,
    get_metrics,
    record_api_request,
    record_ibkr_operation,
    record_order_event,
    set_connection_status,
    update_active_orders,
)


class TestCounter:
    """Tests for Counter data type."""

    def test_initial_value_is_zero(self):
        counter = Counter()
        assert counter.get() == 0

    def test_increment_by_one(self):
        counter = Counter()
        counter.inc()
        assert counter.get() == 1

    def test_increment_by_amount(self):
        counter = Counter()
        counter.inc(5)
        assert counter.get() == 5

    def test_multiple_increments(self):
        counter = Counter()
        counter.inc(3)
        counter.inc(2)
        counter.inc(1)
        assert counter.get() == 6

    def test_thread_safety(self):
        counter = Counter()
        num_threads = 10
        increments_per_thread = 100

        def increment():
            for _ in range(increments_per_thread):
                counter.inc()

        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [executor.submit(increment) for _ in range(num_threads)]
            for f in futures:
                f.result()

        assert counter.get() == num_threads * increments_per_thread


class TestGauge:
    """Tests for Gauge data type."""

    def test_initial_value_is_zero(self):
        gauge = Gauge()
        assert gauge.get() == 0.0

    def test_set_value(self):
        gauge = Gauge()
        gauge.set(42.5)
        assert gauge.get() == 42.5

    def test_increment(self):
        gauge = Gauge()
        gauge.set(10.0)
        gauge.inc(5.0)
        assert gauge.get() == 15.0

    def test_decrement(self):
        gauge = Gauge()
        gauge.set(10.0)
        gauge.dec(3.0)
        assert gauge.get() == 7.0

    def test_thread_safety(self):
        gauge = Gauge()
        gauge.set(0.0)
        num_threads = 10

        def modify():
            for _ in range(100):
                gauge.inc(1.0)
                gauge.dec(1.0)

        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [executor.submit(modify) for _ in range(num_threads)]
            for f in futures:
                f.result()

        # After equal increments and decrements, should be back to 0
        assert gauge.get() == 0.0


class TestHistogram:
    """Tests for Histogram data type."""

    def test_empty_histogram(self):
        hist = Histogram()
        stats = hist.get_stats()
        assert stats["count"] == 0
        assert stats["sum"] == 0.0
        assert stats["p50"] == 0.0

    def test_single_observation(self):
        hist = Histogram()
        hist.observe(5.0)
        stats = hist.get_stats()
        assert stats["count"] == 1
        assert stats["sum"] == 5.0
        assert stats["min"] == 5.0
        assert stats["max"] == 5.0
        assert stats["mean"] == 5.0
        assert stats["p50"] == 5.0

    def test_multiple_observations(self):
        hist = Histogram()
        values = [1.0, 2.0, 3.0, 4.0, 5.0]
        for v in values:
            hist.observe(v)

        stats = hist.get_stats()
        assert stats["count"] == 5
        assert stats["sum"] == 15.0
        assert stats["min"] == 1.0
        assert stats["max"] == 5.0
        assert stats["mean"] == 3.0

    def test_percentiles(self):
        hist = Histogram()
        # Add 100 values from 1 to 100
        for i in range(1, 101):
            hist.observe(float(i))

        stats = hist.get_stats()
        assert stats["count"] == 100
        # Percentiles should be approximately correct
        assert 49 <= stats["p50"] <= 51
        assert 89 <= stats["p90"] <= 91
        assert 94 <= stats["p95"] <= 96
        assert 98 <= stats["p99"] <= 100

    def test_max_samples_limit(self):
        hist = Histogram(max_samples=100)
        # Add more than max_samples
        for i in range(200):
            hist.observe(float(i))

        stats = hist.get_stats()
        # Should only have the last 100 values (100-199)
        assert stats["count"] == 100
        assert stats["min"] == 100.0
        assert stats["max"] == 199.0

    def test_thread_safety(self):
        hist = Histogram()
        num_threads = 10
        observations_per_thread = 100

        def observe():
            for i in range(observations_per_thread):
                hist.observe(float(i))

        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [executor.submit(observe) for _ in range(num_threads)]
            for f in futures:
                f.result()

        stats = hist.get_stats()
        assert stats["count"] == num_threads * observations_per_thread


class TestMetricsCollector:
    """Tests for MetricsCollector singleton."""

    @pytest.fixture(autouse=True)
    def reset_metrics(self):
        """Reset metrics before each test."""
        metrics = get_metrics()
        metrics.reset()
        yield
        metrics.reset()

    def test_singleton_pattern(self):
        m1 = MetricsCollector()
        m2 = MetricsCollector()
        assert m1 is m2

    def test_get_metrics_returns_singleton(self):
        m1 = get_metrics()
        m2 = get_metrics()
        assert m1 is m2

    def test_counter_with_labels(self):
        metrics = get_metrics()
        metrics.counter_inc("requests", labels={"endpoint": "/health", "status": "200"})
        metrics.counter_inc("requests", labels={"endpoint": "/health", "status": "200"})
        metrics.counter_inc("requests", labels={"endpoint": "/health", "status": "500"})

        assert metrics.counter_get("requests", labels={"endpoint": "/health", "status": "200"}) == 2
        assert metrics.counter_get("requests", labels={"endpoint": "/health", "status": "500"}) == 1

    def test_histogram_with_labels(self):
        metrics = get_metrics()
        metrics.histogram_observe("latency", 0.1, labels={"endpoint": "/health"})
        metrics.histogram_observe("latency", 0.2, labels={"endpoint": "/health"})
        metrics.histogram_observe("latency", 0.5, labels={"endpoint": "/orders"})

        health_stats = metrics.histogram_get("latency", labels={"endpoint": "/health"})
        orders_stats = metrics.histogram_get("latency", labels={"endpoint": "/orders"})

        assert health_stats["count"] == 2
        assert orders_stats["count"] == 1

    def test_gauge_with_labels(self):
        metrics = get_metrics()
        metrics.gauge_set("connections", 1.0, labels={"mode": "paper"})
        metrics.gauge_set("connections", 0.0, labels={"mode": "live"})

        assert metrics.gauge_get("connections", labels={"mode": "paper"}) == 1.0
        assert metrics.gauge_get("connections", labels={"mode": "live"}) == 0.0

    def test_get_all_metrics(self):
        metrics = get_metrics()
        metrics.counter_inc("test_counter")
        metrics.histogram_observe("test_histogram", 1.5)
        metrics.gauge_set("test_gauge", 42.0)

        all_metrics = metrics.get_all_metrics()

        assert "uptime_seconds" in all_metrics
        assert all_metrics["uptime_seconds"] >= 0
        assert "counters" in all_metrics
        assert "histograms" in all_metrics
        assert "gauges" in all_metrics
        assert "test_counter" in all_metrics["counters"]
        assert "test_histogram" in all_metrics["histograms"]
        assert "test_gauge" in all_metrics["gauges"]

    def test_reset(self):
        metrics = get_metrics()
        metrics.counter_inc("test_counter", amount=10)
        metrics.reset()

        assert metrics.counter_get("test_counter") == 0
        all_metrics = metrics.get_all_metrics()
        assert len(all_metrics["counters"]) == 0


class TestConvenienceFunctions:
    """Tests for convenience recording functions."""

    @pytest.fixture(autouse=True)
    def reset_metrics(self):
        """Reset metrics before each test."""
        metrics = get_metrics()
        metrics.reset()
        yield
        metrics.reset()

    def test_record_api_request(self):
        record_api_request("/health", "GET", 200, 0.05)
        record_api_request("/health", "GET", 200, 0.03)
        record_api_request("/orders", "POST", 201, 0.15)

        metrics = get_metrics()
        all_data = metrics.get_all_metrics()

        assert "api_requests_total" in all_data["counters"]
        assert "api_request_duration_seconds" in all_data["histograms"]

    def test_record_ibkr_operation(self):
        record_ibkr_operation("connect", "success", 0.5)
        record_ibkr_operation("connect", "error", 1.0)

        metrics = get_metrics()
        all_data = metrics.get_all_metrics()

        assert "ibkr_operations_total" in all_data["counters"]
        assert "ibkr_operation_duration_seconds" in all_data["histograms"]

    def test_record_order_event(self):
        record_order_event("submitted", "AAPL", "pending")
        record_order_event("filled", "AAPL", "filled", duration_seconds=2.5)

        metrics = get_metrics()
        all_data = metrics.get_all_metrics()

        assert "orders_total" in all_data["counters"]
        assert "order_time_to_fill_seconds" in all_data["histograms"]

    def test_set_connection_status(self):
        set_connection_status("paper", connected=True)
        set_connection_status("live", connected=False)

        metrics = get_metrics()

        assert metrics.gauge_get("ibkr_connection_status", labels={"mode": "paper"}) == 1.0
        assert metrics.gauge_get("ibkr_connection_status", labels={"mode": "live"}) == 0.0

    def test_update_active_orders(self):
        update_active_orders("pending", 5)
        update_active_orders("filled", 10)

        metrics = get_metrics()

        assert metrics.gauge_get("active_orders", labels={"status": "pending"}) == 5.0
        assert metrics.gauge_get("active_orders", labels={"status": "filled"}) == 10.0
