"""
Integration tests for order management.

These tests require a running IBKR Gateway in paper trading mode.
They are skipped by default unless RUN_IBKR_INTEGRATION_TESTS=true.

Run integration tests:
    RUN_IBKR_INTEGRATION_TESTS=true pytest tests/test_orders_integration.py -v

IMPORTANT: These tests place real orders in paper trading!
They use far-from-market limit prices to avoid fills, but be aware.
"""

import os
import random
import time

import pytest

from ibkr_core.client import IBKRClient
from ibkr_core.config import reset_config
from ibkr_core.models import OrderSpec, SymbolSpec
from ibkr_core.orders import (
    OrderError,
    OrderNotFoundError,
    OrderPlacementError,
    OrderPreviewError,
    OrderResult,
    cancel_order,
    get_open_orders,
    get_order_registry,
    get_order_status,
    place_order,
    preview_order,
)


# =============================================================================
# Skip Conditions
# =============================================================================


def should_run_integration_tests():
    """Check if integration tests should run."""
    return os.environ.get("RUN_IBKR_INTEGRATION_TESTS", "").lower() in ("true", "1", "yes")


pytestmark = pytest.mark.skipif(
    not should_run_integration_tests(),
    reason="Integration tests skipped. Set RUN_IBKR_INTEGRATION_TESTS=true to run.",
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture(autouse=True)
def reset_environment():
    """Reset config before each test."""
    reset_config()
    yield
    reset_config()


@pytest.fixture(scope="module")
def client():
    """Create and connect a client for integration tests."""
    # Use a unique client ID to avoid conflicts
    client_id = random.randint(5000, 9999)

    # Ensure we're in paper mode
    os.environ["TRADING_MODE"] = "paper"
    reset_config()

    client = IBKRClient(mode="paper", client_id=client_id)
    client.connect(timeout=15)

    yield client

    # Cleanup: cancel any open orders from our tests
    try:
        for trade in client.ib.openTrades():
            client.ib.cancelOrder(trade.order)
            client.ib.sleep(0.5)
    except Exception:
        pass

    client.disconnect()


@pytest.fixture
def aapl_spec():
    """Create AAPL stock specification."""
    return SymbolSpec(
        symbol="AAPL",
        securityType="STK",
        exchange="SMART",
        currency="USD",
    )


@pytest.fixture
def mes_spec():
    """Create MES futures specification."""
    return SymbolSpec(
        symbol="MES",
        securityType="FUT",
        exchange="CME",
        currency="USD",
    )


# =============================================================================
# Preview Tests
# =============================================================================


@pytest.mark.integration
class TestOrderPreviewIntegration:
    """Integration tests for order preview."""

    def test_preview_market_order(self, client, aapl_spec):
        """Test previewing a market order."""
        order_spec = OrderSpec(
            instrument=aapl_spec,
            side="BUY",
            quantity=1,
            orderType="MKT",
            tif="DAY",
        )

        preview = preview_order(client, order_spec)

        assert preview is not None
        assert preview.orderSpec == order_spec
        assert preview.estimatedPrice is not None
        assert preview.estimatedPrice > 0
        assert preview.estimatedNotional is not None
        assert preview.estimatedNotional > 0
        assert isinstance(preview.warnings, list)

        print(f"\nPreview MKT: estimated_price={preview.estimatedPrice:.2f}, "
              f"notional={preview.estimatedNotional:.2f}")

    def test_preview_limit_order(self, client, aapl_spec):
        """Test previewing a limit order."""
        order_spec = OrderSpec(
            instrument=aapl_spec,
            side="BUY",
            quantity=10,
            orderType="LMT",
            limitPrice=100.00,  # Far from market
            tif="DAY",
        )

        preview = preview_order(client, order_spec)

        assert preview is not None
        assert preview.estimatedPrice == 100.00  # Uses limit price
        assert preview.estimatedNotional == 1000.00  # 10 * 100
        print(f"\nPreview LMT: price={preview.estimatedPrice}, "
              f"notional={preview.estimatedNotional}")

    def test_preview_futures_order(self, client, mes_spec):
        """Test previewing a futures order."""
        order_spec = OrderSpec(
            instrument=mes_spec,
            side="BUY",
            quantity=1,
            orderType="LMT",
            limitPrice=5000.00,  # Far from market
            tif="DAY",
        )

        preview = preview_order(client, order_spec)

        assert preview is not None
        assert preview.estimatedPrice == 5000.00
        # MES has multiplier of 5, so notional = 1 * 5000 * 5 = 25000
        assert preview.estimatedNotional is not None
        print(f"\nPreview FUT: price={preview.estimatedPrice}, "
              f"notional={preview.estimatedNotional}")

    def test_preview_does_not_place_order(self, client, aapl_spec):
        """Test that preview does not actually place an order."""
        order_spec = OrderSpec(
            instrument=aapl_spec,
            side="BUY",
            quantity=100,
            orderType="MKT",
            tif="DAY",
        )

        # Get open orders before preview
        open_before = len(client.ib.openTrades())

        # Preview
        preview = preview_order(client, order_spec)

        # Allow time for any potential order to appear
        client.ib.sleep(1.0)

        # Get open orders after preview
        open_after = len(client.ib.openTrades())

        # Should not have increased
        assert open_after == open_before, "Preview should not create orders"
        assert preview is not None


# =============================================================================
# Order Placement Tests (with ORDERS_ENABLED)
# =============================================================================


@pytest.mark.integration
class TestOrderPlacementIntegration:
    """Integration tests for order placement."""

    @pytest.fixture(autouse=True)
    def enable_orders(self):
        """Enable orders for placement tests."""
        os.environ["TRADING_MODE"] = "paper"
        os.environ["ORDERS_ENABLED"] = "true"
        reset_config()
        yield
        # Disable after test
        os.environ["ORDERS_ENABLED"] = "false"
        reset_config()

    def test_place_far_from_market_limit_order(self, client, aapl_spec):
        """Test placing a limit order far from market (won't fill)."""
        # Use a price very far from market to avoid fills
        order_spec = OrderSpec(
            instrument=aapl_spec,
            side="BUY",
            quantity=1,
            orderType="LMT",
            limitPrice=1.00,  # Very low, won't fill
            tif="DAY",
        )

        result = place_order(client, order_spec)

        assert result is not None
        assert result.status == "ACCEPTED"
        assert result.orderId is not None
        assert result.orderStatus is not None
        assert result.orderStatus.status in ("SUBMITTED", "PENDING_SUBMIT")

        print(f"\nPlaced order: id={result.orderId}, status={result.orderStatus.status}")

        # Cleanup: cancel the order
        cancel_result = cancel_order(client, result.orderId)
        assert cancel_result.status in ("CANCELLED", "NOT_FOUND")

    def test_place_and_cancel_order(self, client, aapl_spec):
        """Test placing and then cancelling an order."""
        order_spec = OrderSpec(
            instrument=aapl_spec,
            side="SELL",
            quantity=1,
            orderType="LMT",
            limitPrice=9999.00,  # Very high, won't fill
            tif="GTC",
        )

        # Place order
        result = place_order(client, order_spec)
        assert result.status == "ACCEPTED"
        order_id = result.orderId

        # Give it a moment
        client.ib.sleep(1.0)

        # Check status
        status = get_order_status(client, order_id)
        assert status.status in ("SUBMITTED", "PENDING_SUBMIT", "PARTIALLY_FILLED")
        print(f"\nOrder status before cancel: {status.status}")

        # Cancel
        cancel_result = cancel_order(client, order_id)
        assert cancel_result.status in ("CANCELLED", "ALREADY_FILLED")
        print(f"Cancel result: {cancel_result.status}")

    def test_get_order_status_after_placement(self, client, aapl_spec):
        """Test getting order status after placement."""
        order_spec = OrderSpec(
            instrument=aapl_spec,
            side="BUY",
            quantity=1,
            orderType="LMT",
            limitPrice=1.00,
            tif="DAY",
        )

        result = place_order(client, order_spec)
        assert result.status == "ACCEPTED"
        order_id = result.orderId

        # Get status
        status = get_order_status(client, order_id)

        assert status.orderId == order_id
        assert status.status in ("SUBMITTED", "PENDING_SUBMIT", "PARTIALLY_FILLED")
        assert status.filledQuantity >= 0
        assert status.remainingQuantity >= 0
        assert status.avgFillPrice >= 0

        print(f"\nStatus: {status.status}, filled={status.filledQuantity}, "
              f"remaining={status.remainingQuantity}")

        # Cleanup
        cancel_order(client, order_id)

    def test_order_registry_tracks_orders(self, client, aapl_spec):
        """Test that order registry tracks placed orders."""
        registry = get_order_registry()
        initial_size = registry.size

        order_spec = OrderSpec(
            instrument=aapl_spec,
            side="BUY",
            quantity=1,
            orderType="LMT",
            limitPrice=1.00,
            tif="DAY",
        )

        result = place_order(client, order_spec)
        assert result.status == "ACCEPTED"

        # Registry should have increased
        assert registry.size == initial_size + 1

        # Should be able to lookup
        trade = registry.lookup(result.orderId)
        assert trade is not None

        # Cleanup
        cancel_order(client, result.orderId)


# =============================================================================
# Cancellation Tests
# =============================================================================


@pytest.mark.integration
class TestOrderCancellationIntegration:
    """Integration tests for order cancellation."""

    @pytest.fixture(autouse=True)
    def enable_orders(self):
        """Enable orders for cancellation tests."""
        os.environ["TRADING_MODE"] = "paper"
        os.environ["ORDERS_ENABLED"] = "true"
        reset_config()
        yield
        os.environ["ORDERS_ENABLED"] = "false"
        reset_config()

    def test_cancel_submitted_order(self, client, aapl_spec):
        """Test cancelling a submitted order."""
        order_spec = OrderSpec(
            instrument=aapl_spec,
            side="BUY",
            quantity=1,
            orderType="LMT",
            limitPrice=1.00,
            tif="DAY",
        )

        result = place_order(client, order_spec)
        assert result.status == "ACCEPTED"

        # Cancel
        cancel_result = cancel_order(client, result.orderId)

        assert cancel_result.orderId == result.orderId
        assert cancel_result.status in ("CANCELLED", "ALREADY_FILLED")
        assert cancel_result.message is not None

        print(f"\nCancel result: {cancel_result.status} - {cancel_result.message}")

    def test_cancel_nonexistent_order(self, client):
        """Test cancelling an order that doesn't exist."""
        cancel_result = cancel_order(client, "nonexistent-order-12345")

        assert cancel_result.status == "NOT_FOUND"
        assert "not found" in cancel_result.message.lower()

    def test_cancel_already_cancelled_order(self, client, aapl_spec):
        """Test cancelling an already cancelled order."""
        order_spec = OrderSpec(
            instrument=aapl_spec,
            side="BUY",
            quantity=1,
            orderType="LMT",
            limitPrice=1.00,
            tif="DAY",
        )

        result = place_order(client, order_spec)
        assert result.status == "ACCEPTED"

        # Cancel first time
        cancel1 = cancel_order(client, result.orderId)
        assert cancel1.status in ("CANCELLED", "ALREADY_FILLED")

        # Wait a moment
        client.ib.sleep(1.0)

        # Cancel second time - should indicate already cancelled
        cancel2 = cancel_order(client, result.orderId)
        assert cancel2.status in ("CANCELLED", "NOT_FOUND", "ALREADY_FILLED")


# =============================================================================
# Status Query Tests
# =============================================================================


@pytest.mark.integration
class TestOrderStatusIntegration:
    """Integration tests for order status queries."""

    @pytest.fixture(autouse=True)
    def enable_orders(self):
        """Enable orders for status tests."""
        os.environ["TRADING_MODE"] = "paper"
        os.environ["ORDERS_ENABLED"] = "true"
        reset_config()
        yield
        os.environ["ORDERS_ENABLED"] = "false"
        reset_config()

    def test_get_status_nonexistent_order(self, client):
        """Test getting status of nonexistent order."""
        with pytest.raises(OrderNotFoundError):
            get_order_status(client, "nonexistent-order-99999")

    def test_status_updates_after_cancel(self, client, aapl_spec):
        """Test that status updates after cancellation."""
        order_spec = OrderSpec(
            instrument=aapl_spec,
            side="BUY",
            quantity=1,
            orderType="LMT",
            limitPrice=1.00,
            tif="DAY",
        )

        result = place_order(client, order_spec)
        assert result.status == "ACCEPTED"

        # Initial status
        status1 = get_order_status(client, result.orderId)
        assert status1.status in ("SUBMITTED", "PENDING_SUBMIT")

        # Cancel
        cancel_order(client, result.orderId)
        client.ib.sleep(1.0)

        # Status after cancel
        status2 = get_order_status(client, result.orderId)
        assert status2.status == "CANCELLED"


# =============================================================================
# Open Orders Tests
# =============================================================================


@pytest.mark.integration
class TestOpenOrdersIntegration:
    """Integration tests for open orders query."""

    @pytest.fixture(autouse=True)
    def enable_orders(self):
        """Enable orders for open orders tests."""
        os.environ["TRADING_MODE"] = "paper"
        os.environ["ORDERS_ENABLED"] = "true"
        reset_config()
        yield
        os.environ["ORDERS_ENABLED"] = "false"
        reset_config()

    def test_get_open_orders(self, client, aapl_spec):
        """Test getting list of open orders."""
        # Place a few orders
        order_ids = []
        for i in range(2):
            order_spec = OrderSpec(
                instrument=aapl_spec,
                side="BUY",
                quantity=1,
                orderType="LMT",
                limitPrice=1.00 + i * 0.01,  # Slightly different prices
                tif="DAY",
            )
            result = place_order(client, order_spec)
            assert result.status == "ACCEPTED"
            order_ids.append(result.orderId)

        client.ib.sleep(1.0)

        # Get open orders
        open_orders = get_open_orders(client)

        # Should have at least our orders
        assert len(open_orders) >= 2

        # Check structure of orders
        for order in open_orders:
            assert "order_id" in order
            assert "symbol" in order
            assert "side" in order
            assert "quantity" in order
            assert "status" in order

        print(f"\nOpen orders: {len(open_orders)}")
        for order in open_orders:
            print(f"  {order['symbol']} {order['side']} {order['quantity']} - {order['status']}")

        # Cleanup
        for order_id in order_ids:
            cancel_order(client, order_id)


# =============================================================================
# Simulated Mode Tests (ORDERS_ENABLED=false)
# =============================================================================


@pytest.mark.integration
class TestSimulatedModeIntegration:
    """Integration tests for simulated mode (ORDERS_ENABLED=false)."""

    @pytest.fixture(autouse=True)
    def disable_orders(self):
        """Disable orders for simulated tests."""
        os.environ["TRADING_MODE"] = "paper"
        os.environ["ORDERS_ENABLED"] = "false"
        reset_config()
        yield
        reset_config()

    def test_place_order_returns_simulated(self, client, aapl_spec):
        """Test that place_order returns SIMULATED when disabled."""
        order_spec = OrderSpec(
            instrument=aapl_spec,
            side="BUY",
            quantity=100,
            orderType="MKT",
            tif="DAY",
        )

        result = place_order(client, order_spec)

        assert result.status == "SIMULATED"
        assert result.orderId is None
        assert "ORDERS_ENABLED=false" in result.errors[0]

        print(f"\nSimulated result: {result.errors[0]}")

    def test_preview_works_when_disabled(self, client, aapl_spec):
        """Test that preview still works when orders disabled."""
        order_spec = OrderSpec(
            instrument=aapl_spec,
            side="BUY",
            quantity=10,
            orderType="LMT",
            limitPrice=200.00,
            tif="DAY",
        )

        preview = preview_order(client, order_spec)

        assert preview is not None
        assert preview.estimatedPrice == 200.00
        assert preview.estimatedNotional == 2000.00


# =============================================================================
# Error Handling Tests
# =============================================================================


@pytest.mark.integration
class TestOrderErrorHandling:
    """Integration tests for error handling."""

    @pytest.fixture(autouse=True)
    def enable_orders(self):
        """Enable orders for error tests."""
        os.environ["TRADING_MODE"] = "paper"
        os.environ["ORDERS_ENABLED"] = "true"
        reset_config()
        yield
        os.environ["ORDERS_ENABLED"] = "false"
        reset_config()

    def test_invalid_symbol_preview_error(self, client):
        """Test preview with invalid symbol raises error."""
        invalid_spec = SymbolSpec(
            symbol="INVALID_SYMBOL_XYZ",
            securityType="STK",
            exchange="SMART",
            currency="USD",
        )
        order_spec = OrderSpec(
            instrument=invalid_spec,
            side="BUY",
            quantity=1,
            orderType="MKT",
            tif="DAY",
        )

        with pytest.raises(OrderPreviewError):
            preview_order(client, order_spec)

    def test_validation_error_returns_rejected(self, client, aapl_spec):
        """Test that validation errors return REJECTED status."""
        # MKT order with limit price is invalid
        order_spec = OrderSpec(
            instrument=aapl_spec,
            side="BUY",
            quantity=1,
            orderType="MKT",
            limitPrice=100.00,  # Invalid for MKT
            tif="DAY",
        )

        result = place_order(client, order_spec)

        assert result.status == "REJECTED"
        assert len(result.errors) > 0
        assert "limit price" in result.errors[0].lower()


# =============================================================================
# Cleanup Fixture
# =============================================================================


@pytest.fixture(scope="module", autouse=True)
def cleanup_all_orders(client):
    """Cleanup any remaining orders after all tests."""
    yield

    # Cancel all open orders
    try:
        for trade in client.ib.openTrades():
            client.ib.cancelOrder(trade.order)
            client.ib.sleep(0.5)
    except Exception:
        pass
