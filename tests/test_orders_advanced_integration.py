"""
Integration tests for advanced order types (Phase 4.5).

These tests require a running IBKR Gateway in paper trading mode.
They are skipped by default unless RUN_IBKR_INTEGRATION_TESTS=true.

Run integration tests:
    RUN_IBKR_INTEGRATION_TESTS=true pytest tests/test_orders_advanced_integration.py -v

IMPORTANT: These tests place real orders in paper trading!
They use far-from-market limit prices to avoid fills, but be aware.

Tests:
- Trailing stop orders (TRAIL)
- Bracket orders (entry + take profit + stop loss)
- Preview for advanced order types
- cancel_order_set and get_order_set_status
"""

import os
import random
import time

import pytest

from ibkr_core.client import IBKRClient
from ibkr_core.config import reset_config
from ibkr_core.models import OrderSpec, SymbolSpec
from ibkr_core.orders import (
    cancel_order,
    cancel_order_set,
    get_order_set_status,
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
    client_id = random.randint(6000, 7999)

    # Ensure we're in paper mode with orders enabled
    os.environ["TRADING_MODE"] = "paper"
    os.environ["ORDERS_ENABLED"] = "true"
    reset_config()

    client = IBKRClient(mode="paper", client_id=client_id)
    client.connect(timeout=15)

    yield client

    client.disconnect()


@pytest.fixture
def aapl_symbol():
    """AAPL stock symbol spec."""
    return SymbolSpec(
        symbol="AAPL",
        securityType="STK",
        exchange="SMART",
        currency="USD",
    )


@pytest.fixture
def spy_symbol():
    """SPY ETF symbol spec."""
    return SymbolSpec(
        symbol="SPY",
        securityType="STK",
        exchange="SMART",
        currency="USD",
    )


# =============================================================================
# Trailing Stop Order Tests
# =============================================================================


class TestTrailingStopIntegration:
    """Integration tests for trailing stop orders."""

    def test_preview_trailing_stop_with_amount(self, client, aapl_symbol):
        """Test previewing a trailing stop with dollar amount."""
        order_spec = OrderSpec(
            instrument=aapl_symbol,
            side="SELL",
            quantity=1,
            orderType="TRAIL",
            trailingAmount=5.00,  # $5 trailing
        )

        preview = preview_order(client, order_spec)

        assert preview is not None
        assert preview.estimatedPrice is not None
        assert preview.estimatedNotional is not None
        assert "Trailing stop" in " ".join(preview.warnings)
        print(f"TRAIL preview: price={preview.estimatedPrice}, notional={preview.estimatedNotional}")

    def test_preview_trailing_stop_with_percent(self, client, aapl_symbol):
        """Test previewing a trailing stop with percentage."""
        order_spec = OrderSpec(
            instrument=aapl_symbol,
            side="SELL",
            quantity=1,
            orderType="TRAIL",
            trailingPercent=2.5,  # 2.5% trailing
        )

        preview = preview_order(client, order_spec)

        assert preview is not None
        assert "2.5%" in " ".join(preview.warnings)
        print(f"TRAIL percent preview: price={preview.estimatedPrice}")

    def test_place_and_cancel_trailing_stop(self, client, aapl_symbol):
        """Test placing and cancelling a trailing stop order."""
        # Get current price for reference
        preview = preview_order(
            client,
            OrderSpec(
                instrument=aapl_symbol,
                side="SELL",
                quantity=1,
                orderType="MKT",
            ),
        )
        current_price = preview.estimatedPrice

        # Place trailing stop far below market (to avoid immediate trigger)
        # For a SELL trailing stop, the stop will trail below the market
        order_spec = OrderSpec(
            instrument=aapl_symbol,
            side="SELL",
            quantity=1,
            orderType="TRAIL",
            trailingAmount=50.00,  # $50 trailing - very far to avoid fill
            trailStopPrice=current_price - 100,  # Start very far below
        )

        result = place_order(client, order_spec)

        assert result.status == "ACCEPTED"
        assert result.orderId is not None
        print(f"Trailing stop placed: order_id={result.orderId}")

        # Get status
        status = get_order_status(client, result.orderId)
        assert status.status in ("SUBMITTED", "PENDING_SUBMIT")

        # Cancel the order
        time.sleep(1)
        cancel_result = cancel_order(client, result.orderId)
        assert cancel_result.status == "CANCELLED"
        print("Trailing stop cancelled successfully")


# =============================================================================
# Bracket Order Tests
# =============================================================================


class TestBracketOrderIntegration:
    """Integration tests for bracket orders."""

    def test_preview_bracket_order(self, client, spy_symbol):
        """Test previewing a bracket order."""
        # Get current price
        simple_preview = preview_order(
            client,
            OrderSpec(
                instrument=spy_symbol,
                side="BUY",
                quantity=1,
                orderType="MKT",
            ),
        )
        current_price = simple_preview.estimatedPrice

        # Create bracket order
        order_spec = OrderSpec(
            instrument=spy_symbol,
            side="BUY",
            quantity=1,
            orderType="BRACKET",
            limitPrice=current_price - 50,  # Entry far below market
            takeProfitPrice=current_price + 10,  # Take profit above
            stopLossPrice=current_price - 60,  # Stop loss below entry
        )

        preview = preview_order(client, order_spec)

        assert preview is not None
        assert len(preview.legs) == 3
        assert preview.legs[0].role == "entry"
        assert preview.legs[1].role == "take_profit"
        assert preview.legs[2].role == "stop_loss"
        assert "Bracket order" in " ".join(preview.warnings)

        print(f"Bracket preview: {len(preview.legs)} legs")
        for leg in preview.legs:
            print(f"  {leg.role}: {leg.orderType} @ {leg.limitPrice or leg.stopPrice}")

    def test_place_and_cancel_bracket_order(self, client, spy_symbol):
        """Test placing and cancelling a bracket order."""
        # Get current price
        simple_preview = preview_order(
            client,
            OrderSpec(
                instrument=spy_symbol,
                side="BUY",
                quantity=1,
                orderType="MKT",
            ),
        )
        current_price = simple_preview.estimatedPrice

        # Create bracket order with prices far from market
        order_spec = OrderSpec(
            instrument=spy_symbol,
            side="BUY",
            quantity=1,
            orderType="BRACKET",
            limitPrice=current_price - 100,  # Entry $100 below market
            takeProfitPrice=current_price + 50,  # Take profit $50 above
            stopLossPrice=current_price - 150,  # Stop loss $150 below market
        )

        result = place_order(client, order_spec)

        assert result.status == "ACCEPTED"
        assert result.orderId is not None
        assert len(result.orderIds) == 3
        assert "entry" in result.orderRoles
        assert "take_profit" in result.orderRoles
        assert "stop_loss" in result.orderRoles

        print("Bracket order placed:")
        print(f"  Entry: {result.orderRoles['entry']}")
        print(f"  Take Profit: {result.orderRoles['take_profit']}")
        print(f"  Stop Loss: {result.orderRoles['stop_loss']}")

        # Wait for orders to settle
        time.sleep(2)

        # Get status of all orders
        statuses = get_order_set_status(client, result.orderIds)
        assert len(statuses) > 0
        print(f"Order set status: {len(statuses)} orders found")
        for s in statuses:
            print(f"  {s.orderId}: {s.status}")

        # Cancel all orders
        cancel_result = cancel_order_set(client, result.orderIds)
        assert cancel_result.status in ("CANCELLED", "REJECTED")  # Some may already be inactive
        print(f"Bracket order cancelled: {cancel_result.message}")

    def test_bracket_order_with_stop_limit(self, client, aapl_symbol):
        """Test bracket order with stop-limit for stop loss."""
        # Get current price
        simple_preview = preview_order(
            client,
            OrderSpec(
                instrument=aapl_symbol,
                side="BUY",
                quantity=1,
                orderType="MKT",
            ),
        )
        current_price = simple_preview.estimatedPrice

        # Create bracket with stop-limit stop loss
        order_spec = OrderSpec(
            instrument=aapl_symbol,
            side="BUY",
            quantity=1,
            orderType="BRACKET",
            limitPrice=current_price - 100,  # Entry far below
            takeProfitPrice=current_price + 50,
            stopLossPrice=current_price - 120,  # Stop trigger
            stopLossLimitPrice=current_price - 125,  # Stop limit price
        )

        preview = preview_order(client, order_spec)
        assert preview.legs[2].orderType == "STP_LMT"
        print(f"Bracket with stop-limit: stop@{preview.legs[2].stopPrice}, limit@{preview.legs[2].limitPrice}")


# =============================================================================
# Order Set Operations Tests
# =============================================================================


class TestOrderSetOperationsIntegration:
    """Integration tests for cancel_order_set and get_order_set_status."""

    def test_cancel_order_set_multiple_orders(self, client, aapl_symbol):
        """Test cancelling multiple independent orders."""
        # Place two separate orders
        order1 = OrderSpec(
            instrument=aapl_symbol,
            side="BUY",
            quantity=1,
            orderType="LMT",
            limitPrice=50.00,  # Very far from market
        )
        order2 = OrderSpec(
            instrument=aapl_symbol,
            side="BUY",
            quantity=1,
            orderType="LMT",
            limitPrice=51.00,  # Very far from market
        )

        result1 = place_order(client, order1)
        result2 = place_order(client, order2)

        assert result1.status == "ACCEPTED"
        assert result2.status == "ACCEPTED"

        order_ids = [result1.orderId, result2.orderId]
        print(f"Placed orders: {order_ids}")

        time.sleep(1)

        # Cancel both
        cancel_result = cancel_order_set(client, order_ids)
        assert cancel_result.status == "CANCELLED"
        assert "2 cancelled" in cancel_result.message
        print(f"Cancelled: {cancel_result.message}")

    def test_get_order_set_status_with_valid_orders(self, client, aapl_symbol):
        """Test getting status of multiple orders."""
        # Place two orders
        order1 = OrderSpec(
            instrument=aapl_symbol,
            side="BUY",
            quantity=1,
            orderType="LMT",
            limitPrice=50.00,
        )
        order2 = OrderSpec(
            instrument=aapl_symbol,
            side="SELL",
            quantity=1,
            orderType="LMT",
            limitPrice=500.00,  # Very far from market
        )

        result1 = place_order(client, order1)
        result2 = place_order(client, order2)

        order_ids = [result1.orderId, result2.orderId]

        time.sleep(1)

        # Get status
        statuses = get_order_set_status(client, order_ids)
        assert len(statuses) == 2

        for s in statuses:
            print(f"Order {s.orderId}: {s.status}")
            assert s.status in ("SUBMITTED", "PENDING_SUBMIT", "CANCELLED")

        # Cleanup
        cancel_order_set(client, order_ids)


# =============================================================================
# MOC/OPG Preview Tests (actual execution only during market hours)
# =============================================================================


class TestMOCOPGIntegration:
    """Integration tests for MOC/OPG order previews."""

    def test_preview_moc_order(self, client, spy_symbol):
        """Test previewing a market-on-close order."""
        order_spec = OrderSpec(
            instrument=spy_symbol,
            side="BUY",
            quantity=1,
            orderType="MOC",
        )

        preview = preview_order(client, order_spec)

        assert preview is not None
        assert preview.estimatedPrice is not None
        assert "market close" in " ".join(preview.warnings).lower()
        print(f"MOC preview: estimated price={preview.estimatedPrice}")

    def test_preview_opg_order(self, client, spy_symbol):
        """Test previewing a market-on-open order."""
        order_spec = OrderSpec(
            instrument=spy_symbol,
            side="SELL",
            quantity=1,
            orderType="OPG",
        )

        preview = preview_order(client, order_spec)

        assert preview is not None
        assert preview.estimatedPrice is not None
        assert "market open" in " ".join(preview.warnings).lower()
        print(f"OPG preview: estimated price={preview.estimatedPrice}")


# =============================================================================
# OCA Group Tests
# =============================================================================


class TestOCAGroupIntegration:
    """Integration tests for OCA (One-Cancels-All) groups."""

    def test_preview_order_with_oca(self, client, aapl_symbol):
        """Test previewing an order with OCA group."""
        order_spec = OrderSpec(
            instrument=aapl_symbol,
            side="BUY",
            quantity=1,
            orderType="LMT",
            limitPrice=100.00,
            ocaGroup="test_oca_group_preview",
            ocaType=1,
        )

        preview = preview_order(client, order_spec)

        assert preview is not None
        assert preview.estimatedPrice == 100.00
        print(f"OCA preview: price={preview.estimatedPrice}")
