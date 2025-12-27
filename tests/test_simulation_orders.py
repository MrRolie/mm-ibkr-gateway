"""
Tests for order flow simulation.

Verifies that SimulatedIBKRClient correctly simulates order
submission, state transitions, fills, and cancellations.
"""

import pytest
from datetime import datetime

from ibkr_core.simulation import SimulatedIBKRClient, SimulatedOrder


class TestOrderSubmission:
    """Tests for order submission."""

    @pytest.fixture
    def client(self):
        """Connected client fixture."""
        client = SimulatedIBKRClient()
        client.connect()
        yield client
        client.disconnect()

    def test_submit_market_buy_order(self, client):
        order = client.submit_order(
            symbol="AAPL",
            side="BUY",
            quantity=100,
            order_type="MKT",
        )

        assert isinstance(order, SimulatedOrder)
        assert order.symbol == "AAPL"
        assert order.side == "BUY"
        assert order.quantity == 100
        assert order.order_type == "MKT"
        assert order.order_id is not None

    def test_submit_market_sell_order(self, client):
        order = client.submit_order(
            symbol="MSFT",
            side="SELL",
            quantity=50,
            order_type="MKT",
        )

        assert order.side == "SELL"
        assert order.symbol == "MSFT"

    def test_submit_limit_order(self, client):
        order = client.submit_order(
            symbol="GOOGL",
            side="BUY",
            quantity=10,
            order_type="LMT",
            limit_price=150.00,
        )

        assert order.order_type == "LMT"
        assert order.limit_price == 150.00

    def test_submit_order_assigns_ibkr_id(self, client):
        order1 = client.submit_order("AAPL", "BUY", 1, "MKT")
        order2 = client.submit_order("AAPL", "BUY", 1, "MKT")

        assert order1.ibkr_order_id is not None
        assert order2.ibkr_order_id is not None
        assert order1.ibkr_order_id != order2.ibkr_order_id

    def test_submit_order_uses_default_account(self, client):
        order = client.submit_order("AAPL", "BUY", 1, "MKT")
        assert order.account_id == "SIM000001"

    def test_submit_order_with_custom_account(self, client):
        order = client.submit_order(
            "AAPL", "BUY", 1, "MKT", account_id="CUSTOM123"
        )
        assert order.account_id == "CUSTOM123"

    def test_submit_order_when_disconnected(self):
        client = SimulatedIBKRClient()
        with pytest.raises(RuntimeError, match="Not connected"):
            client.submit_order("AAPL", "BUY", 1, "MKT")


class TestOrderValidation:
    """Tests for order validation."""

    @pytest.fixture
    def client(self):
        client = SimulatedIBKRClient()
        client.connect()
        yield client
        client.disconnect()

    def test_invalid_side_rejected(self, client):
        with pytest.raises(ValueError, match="Invalid side"):
            client.submit_order("AAPL", "HOLD", 1, "MKT")

    def test_zero_quantity_rejected(self, client):
        with pytest.raises(ValueError, match="Invalid quantity"):
            client.submit_order("AAPL", "BUY", 0, "MKT")

    def test_negative_quantity_rejected(self, client):
        with pytest.raises(ValueError, match="Invalid quantity"):
            client.submit_order("AAPL", "BUY", -10, "MKT")

    def test_invalid_order_type_rejected(self, client):
        with pytest.raises(ValueError, match="Invalid order type"):
            client.submit_order("AAPL", "BUY", 1, "STOP")

    def test_limit_order_without_price_rejected(self, client):
        with pytest.raises(ValueError, match="Limit price required"):
            client.submit_order("AAPL", "BUY", 1, "LMT")

    def test_case_insensitive_side(self, client):
        order = client.submit_order("AAPL", "buy", 1, "MKT")
        assert order.side == "BUY"

    def test_case_insensitive_order_type(self, client):
        order = client.submit_order("AAPL", "BUY", 1, "mkt")
        assert order.order_type == "MKT"

    def test_symbol_normalized_to_uppercase(self, client):
        order = client.submit_order("aapl", "BUY", 1, "MKT")
        assert order.symbol == "AAPL"


class TestMarketOrderFills:
    """Tests for market order fill behavior."""

    @pytest.fixture
    def client(self):
        client = SimulatedIBKRClient()
        client.connect()
        yield client
        client.disconnect()

    def test_market_buy_fills_immediately(self, client):
        order = client.submit_order("AAPL", "BUY", 100, "MKT")

        assert order.status == "Filled"
        assert order.filled_quantity == 100
        assert order.fill_price is not None
        assert order.fill_price > 0

    def test_market_sell_fills_immediately(self, client):
        order = client.submit_order("AAPL", "SELL", 50, "MKT")

        assert order.status == "Filled"
        assert order.filled_quantity == 50

    def test_market_buy_fills_at_ask(self, client):
        quote = client.get_quote("AAPL")
        order = client.submit_order("AAPL", "BUY", 1, "MKT")

        # Buy fills at ask (or close to it due to quote update)
        assert abs(order.fill_price - quote.ask) < quote.ask * 0.01

    def test_market_sell_fills_at_bid(self, client):
        quote = client.get_quote("AAPL")
        order = client.submit_order("AAPL", "SELL", 1, "MKT")

        # Sell fills at bid (or close to it)
        assert abs(order.fill_price - quote.bid) < quote.bid * 0.01


class TestLimitOrderFills:
    """Tests for limit order fill behavior."""

    @pytest.fixture
    def client(self):
        client = SimulatedIBKRClient()
        client.connect()
        yield client
        client.disconnect()

    def test_limit_buy_above_ask_fills(self, client):
        quote = client.get_quote("AAPL")
        # Set limit price above ask - should fill
        limit_price = quote.ask * 1.10

        order = client.submit_order(
            "AAPL", "BUY", 10, "LMT", limit_price=limit_price
        )

        assert order.status == "Filled"
        assert order.fill_price <= limit_price

    def test_limit_buy_below_ask_stays_open(self, client):
        quote = client.get_quote("AAPL")
        # Set limit price well below current price
        limit_price = quote.bid * 0.80

        order = client.submit_order(
            "AAPL", "BUY", 10, "LMT", limit_price=limit_price
        )

        # Order should not fill immediately
        assert order.status == "Submitted"
        assert order.filled_quantity == 0

    def test_limit_sell_below_bid_fills(self, client):
        quote = client.get_quote("AAPL")
        # Set limit price below bid - should fill
        limit_price = quote.bid * 0.90

        order = client.submit_order(
            "AAPL", "SELL", 10, "LMT", limit_price=limit_price
        )

        assert order.status == "Filled"
        assert order.fill_price >= limit_price

    def test_limit_sell_above_bid_stays_open(self, client):
        quote = client.get_quote("AAPL")
        # Set limit price well above current price
        limit_price = quote.ask * 1.20

        order = client.submit_order(
            "AAPL", "SELL", 10, "LMT", limit_price=limit_price
        )

        assert order.status == "Submitted"
        assert order.filled_quantity == 0


class TestOrderCancellation:
    """Tests for order cancellation."""

    @pytest.fixture
    def client(self):
        client = SimulatedIBKRClient()
        client.connect()
        yield client
        client.disconnect()

    def test_cancel_open_order(self, client):
        quote = client.get_quote("AAPL")
        # Create order that won't fill
        order = client.submit_order(
            "AAPL", "BUY", 10, "LMT", limit_price=quote.bid * 0.50
        )
        assert order.status == "Submitted"

        result = client.cancel_order(order.order_id)
        assert result is True

        updated = client.get_order(order.order_id)
        assert updated.status == "Cancelled"

    def test_cancel_filled_order_fails(self, client):
        order = client.submit_order("AAPL", "BUY", 10, "MKT")
        assert order.status == "Filled"

        result = client.cancel_order(order.order_id)
        assert result is False

    def test_cancel_already_cancelled_order_fails(self, client):
        quote = client.get_quote("AAPL")
        order = client.submit_order(
            "AAPL", "BUY", 10, "LMT", limit_price=quote.bid * 0.50
        )

        client.cancel_order(order.order_id)
        result = client.cancel_order(order.order_id)
        assert result is False

    def test_cancel_nonexistent_order_fails(self, client):
        result = client.cancel_order("fake-order-id")
        assert result is False


class TestOrderRegistry:
    """Tests for order registry and querying."""

    @pytest.fixture
    def client(self):
        client = SimulatedIBKRClient()
        client.connect()
        client.clear_orders()  # Start fresh
        yield client
        client.disconnect()

    def test_get_order_by_id(self, client):
        order = client.submit_order("AAPL", "BUY", 1, "MKT")
        retrieved = client.get_order(order.order_id)

        assert retrieved is not None
        assert retrieved.order_id == order.order_id

    def test_get_nonexistent_order(self, client):
        result = client.get_order("fake-id")
        assert result is None

    def test_get_open_orders(self, client):
        quote = client.get_quote("AAPL")

        # Create one filled order
        client.submit_order("AAPL", "BUY", 1, "MKT")

        # Create two open orders
        client.submit_order(
            "AAPL", "BUY", 1, "LMT", limit_price=quote.bid * 0.50
        )
        client.submit_order(
            "MSFT", "SELL", 1, "LMT", limit_price=quote.ask * 2.0
        )

        open_orders = client.get_open_orders()
        assert len(open_orders) == 2

    def test_get_all_orders(self, client):
        client.submit_order("AAPL", "BUY", 1, "MKT")
        client.submit_order("MSFT", "BUY", 1, "MKT")

        all_orders = client.get_all_orders()
        assert len(all_orders) == 2

    def test_clear_orders(self, client):
        client.submit_order("AAPL", "BUY", 1, "MKT")
        client.submit_order("MSFT", "BUY", 1, "MKT")

        client.clear_orders()
        assert len(client.get_all_orders()) == 0

    def test_order_to_dict(self, client):
        order = client.submit_order("AAPL", "BUY", 100, "MKT")
        d = order.to_dict()

        assert d["order_id"] == order.order_id
        assert d["symbol"] == "AAPL"
        assert d["side"] == "BUY"
        assert d["quantity"] == 100
        assert d["status"] == "Filled"
        assert "created_at" in d
        assert "updated_at" in d


class TestOrderTimestamps:
    """Tests for order timestamp tracking."""

    @pytest.fixture
    def client(self):
        client = SimulatedIBKRClient()
        client.connect()
        yield client
        client.disconnect()

    def test_order_has_created_at(self, client):
        before = datetime.now()
        order = client.submit_order("AAPL", "BUY", 1, "MKT")
        after = datetime.now()

        assert before <= order.created_at <= after

    def test_order_updated_at_changes_on_fill(self, client):
        order = client.submit_order("AAPL", "BUY", 1, "MKT")

        # For market orders, filled immediately so updated_at >= created_at
        assert order.updated_at >= order.created_at

    def test_cancelled_order_updated_at_changes(self, client):
        quote = client.get_quote("AAPL")
        order = client.submit_order(
            "AAPL", "BUY", 1, "LMT", limit_price=quote.bid * 0.50
        )
        created = order.created_at

        client.cancel_order(order.order_id)
        updated = client.get_order(order.order_id)

        assert updated.updated_at >= created
