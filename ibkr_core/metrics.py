"""
In-memory metrics collection for monitoring.

Provides thread-safe metrics collection with support for:
- Counters: Monotonically increasing values
- Histograms: Distribution of values with percentile calculations
- Gauges: Point-in-time values

Metrics reset on process restart (acceptable for Phase 8).
"""

import statistics
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Counter:
    """Thread-safe counter metric."""

    value: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def inc(self, amount: int = 1) -> None:
        """Increment the counter."""
        with self._lock:
            self.value += amount

    def get(self) -> int:
        """Get current value."""
        with self._lock:
            return self.value


@dataclass
class Gauge:
    """Thread-safe gauge metric."""

    value: float = 0.0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def set(self, value: float) -> None:
        """Set the gauge value."""
        with self._lock:
            self.value = value

    def inc(self, amount: float = 1.0) -> None:
        """Increment the gauge."""
        with self._lock:
            self.value += amount

    def dec(self, amount: float = 1.0) -> None:
        """Decrement the gauge."""
        with self._lock:
            self.value -= amount

    def get(self) -> float:
        """Get current value."""
        with self._lock:
            return self.value


@dataclass
class Histogram:
    """Thread-safe histogram metric with percentile calculations."""

    values: list = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    max_samples: int = 10000

    def observe(self, value: float) -> None:
        """Record a value."""
        with self._lock:
            self.values.append(value)
            # Trim to max_samples to prevent unbounded growth
            if len(self.values) > self.max_samples:
                self.values = self.values[-self.max_samples :]

    def get_stats(self) -> dict:
        """Get histogram statistics including percentiles."""
        with self._lock:
            if not self.values:
                return {
                    "count": 0,
                    "sum": 0.0,
                    "min": 0.0,
                    "max": 0.0,
                    "mean": 0.0,
                    "p50": 0.0,
                    "p90": 0.0,
                    "p95": 0.0,
                    "p99": 0.0,
                }

            sorted_values = sorted(self.values)
            count = len(sorted_values)

            return {
                "count": count,
                "sum": sum(sorted_values),
                "min": sorted_values[0],
                "max": sorted_values[-1],
                "mean": statistics.mean(sorted_values),
                "p50": self._percentile(sorted_values, 50),
                "p90": self._percentile(sorted_values, 90),
                "p95": self._percentile(sorted_values, 95),
                "p99": self._percentile(sorted_values, 99),
            }

    def _percentile(self, sorted_values: list, percentile: int) -> float:
        """Calculate percentile from sorted values."""
        if not sorted_values:
            return 0.0
        k = (len(sorted_values) - 1) * percentile / 100
        f = int(k)
        c = f + 1 if f + 1 < len(sorted_values) else f
        if f == c:
            return sorted_values[f]
        return sorted_values[f] * (c - k) + sorted_values[c] * (k - f)


class MetricsCollector:
    """
    Singleton metrics collector with thread-safe operations.

    Provides centralized metrics collection for monitoring API requests,
    IBKR operations, and order execution.
    """

    _instance: "MetricsCollector | None" = None
    _lock: threading.Lock = threading.Lock()

    def __new__(cls) -> "MetricsCollector":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return
        self._initialized = True
        self._start_time = time.time()

        # Counters with labels
        self._counters: dict[str, dict[tuple, Counter]] = defaultdict(dict)
        self._counter_lock = threading.Lock()

        # Histograms with labels
        self._histograms: dict[str, dict[tuple, Histogram]] = defaultdict(dict)
        self._histogram_lock = threading.Lock()

        # Gauges with labels
        self._gauges: dict[str, dict[tuple, Gauge]] = defaultdict(dict)
        self._gauge_lock = threading.Lock()

    def _labels_to_key(self, labels: dict | None) -> tuple:
        """Convert labels dict to hashable tuple."""
        if not labels:
            return ()
        return tuple(sorted(labels.items()))

    # Counter operations
    def counter_inc(self, name: str, amount: int = 1, labels: dict | None = None) -> None:
        """Increment a counter."""
        key = self._labels_to_key(labels)
        with self._counter_lock:
            if key not in self._counters[name]:
                self._counters[name][key] = Counter()
        self._counters[name][key].inc(amount)

    def counter_get(self, name: str, labels: dict | None = None) -> int:
        """Get counter value."""
        key = self._labels_to_key(labels)
        with self._counter_lock:
            if name not in self._counters:
                return 0
            if key not in self._counters[name]:
                return 0
            return self._counters[name][key].get()

    # Histogram operations
    def histogram_observe(self, name: str, value: float, labels: dict | None = None) -> None:
        """Record a histogram observation."""
        key = self._labels_to_key(labels)
        with self._histogram_lock:
            if key not in self._histograms[name]:
                self._histograms[name][key] = Histogram()
        self._histograms[name][key].observe(value)

    def histogram_get(self, name: str, labels: dict | None = None) -> dict:
        """Get histogram statistics."""
        key = self._labels_to_key(labels)
        with self._histogram_lock:
            if name not in self._histograms:
                return Histogram().get_stats()
            if key not in self._histograms[name]:
                return Histogram().get_stats()
            return self._histograms[name][key].get_stats()

    # Gauge operations
    def gauge_set(self, name: str, value: float, labels: dict | None = None) -> None:
        """Set a gauge value."""
        key = self._labels_to_key(labels)
        with self._gauge_lock:
            if key not in self._gauges[name]:
                self._gauges[name][key] = Gauge()
        self._gauges[name][key].set(value)

    def gauge_inc(self, name: str, amount: float = 1.0, labels: dict | None = None) -> None:
        """Increment a gauge."""
        key = self._labels_to_key(labels)
        with self._gauge_lock:
            if key not in self._gauges[name]:
                self._gauges[name][key] = Gauge()
        self._gauges[name][key].inc(amount)

    def gauge_dec(self, name: str, amount: float = 1.0, labels: dict | None = None) -> None:
        """Decrement a gauge."""
        key = self._labels_to_key(labels)
        with self._gauge_lock:
            if key not in self._gauges[name]:
                self._gauges[name][key] = Gauge()
        self._gauges[name][key].dec(amount)

    def gauge_get(self, name: str, labels: dict | None = None) -> float:
        """Get gauge value."""
        key = self._labels_to_key(labels)
        with self._gauge_lock:
            if name not in self._gauges:
                return 0.0
            if key not in self._gauges[name]:
                return 0.0
            return self._gauges[name][key].get()

    # Bulk export
    def get_all_metrics(self) -> dict[str, Any]:
        """Export all metrics as a dictionary."""
        result: dict[str, Any] = {
            "uptime_seconds": time.time() - self._start_time,
            "counters": {},
            "histograms": {},
            "gauges": {},
        }

        # Export counters
        with self._counter_lock:
            for name, label_counters in self._counters.items():
                result["counters"][name] = {}
                for labels_tuple, counter in label_counters.items():
                    label_str = (
                        ",".join(f"{k}={v}" for k, v in labels_tuple)
                        if labels_tuple
                        else "__total__"
                    )
                    result["counters"][name][label_str] = counter.get()

        # Export histograms
        with self._histogram_lock:
            for name, label_histograms in self._histograms.items():
                result["histograms"][name] = {}
                for labels_tuple, histogram in label_histograms.items():
                    label_str = (
                        ",".join(f"{k}={v}" for k, v in labels_tuple)
                        if labels_tuple
                        else "__total__"
                    )
                    result["histograms"][name][label_str] = histogram.get_stats()

        # Export gauges
        with self._gauge_lock:
            for name, label_gauges in self._gauges.items():
                result["gauges"][name] = {}
                for labels_tuple, gauge in label_gauges.items():
                    label_str = (
                        ",".join(f"{k}={v}" for k, v in labels_tuple)
                        if labels_tuple
                        else "__total__"
                    )
                    result["gauges"][name][label_str] = gauge.get()

        return result

    def reset(self) -> None:
        """Reset all metrics. Primarily for testing."""
        with self._counter_lock:
            self._counters.clear()
        with self._histogram_lock:
            self._histograms.clear()
        with self._gauge_lock:
            self._gauges.clear()
        self._start_time = time.time()


# Singleton instance
_metrics: MetricsCollector | None = None


def get_metrics() -> MetricsCollector:
    """Get the metrics collector singleton."""
    global _metrics
    if _metrics is None:
        _metrics = MetricsCollector()
    return _metrics


# Convenience functions for common metrics


def record_api_request(
    endpoint: str, method: str, status_code: int, duration_seconds: float
) -> None:
    """Record an API request metric."""
    metrics = get_metrics()
    labels = {"endpoint": endpoint, "method": method, "status": str(status_code)}
    metrics.counter_inc("api_requests_total", labels=labels)
    metrics.histogram_observe(
        "api_request_duration_seconds",
        duration_seconds,
        labels={"endpoint": endpoint, "method": method},
    )


def record_ibkr_operation(operation: str, status: str, duration_seconds: float) -> None:
    """Record an IBKR operation metric."""
    metrics = get_metrics()
    labels = {"operation": operation, "status": status}
    metrics.counter_inc("ibkr_operations_total", labels=labels)
    metrics.histogram_observe(
        "ibkr_operation_duration_seconds",
        duration_seconds,
        labels={"operation": operation},
    )


def record_order_event(
    event: str, symbol: str, status: str, duration_seconds: float | None = None
) -> None:
    """Record an order event metric."""
    metrics = get_metrics()

    # Increment order counter
    labels = {"event": event, "symbol": symbol, "status": status}
    metrics.counter_inc("orders_total", labels=labels)

    # Record time to fill if applicable
    if duration_seconds is not None and event == "filled":
        metrics.histogram_observe(
            "order_time_to_fill_seconds",
            duration_seconds,
            labels={"symbol": symbol},
        )


def set_connection_status(mode: str, connected: bool) -> None:
    """Set IBKR connection status gauge."""
    metrics = get_metrics()
    metrics.gauge_set(
        "ibkr_connection_status",
        1.0 if connected else 0.0,
        labels={"mode": mode},
    )


def update_active_orders(status: str, count: int) -> None:
    """Update active orders gauge."""
    metrics = get_metrics()
    metrics.gauge_set("active_orders", float(count), labels={"status": status})
