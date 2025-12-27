"""
End-to-end API tests in simulation mode.

Verifies that the API works correctly when using the simulated
IBKR client, allowing full integration testing without a live gateway.
"""

import pytest
from unittest.mock import patch, MagicMock

from ibkr_core.simulation import SimulatedIBKRClient, SimulatedQuote


class TestSimulationModeDetection:
    """Tests for simulation mode detection and configuration."""

    def test_get_ibkr_client_simulation_mode(self, monkeypatch):
        from ibkr_core.simulation import get_ibkr_client

        monkeypatch.setenv("IBKR_MODE", "simulation")
        client = get_ibkr_client()

        assert isinstance(client, SimulatedIBKRClient)

    def test_simulation_client_mode_property(self):
        client = SimulatedIBKRClient()
        assert client.mode == "simulation"

    def test_simulation_client_ignores_trading_mode(self):
        # SimulatedIBKRClient always reports mode as "simulation"
        client = SimulatedIBKRClient()
        assert client.mode == "simulation"


class TestSimulatedMarketData:
    """Tests for market data in simulation mode."""

    @pytest.fixture
    def client(self):
        client = SimulatedIBKRClient()
        client.connect()
        yield client
        client.disconnect()

    def test_quote_has_all_fields(self, client):
        quote = client.get_quote("AAPL")

        assert quote.symbol == "AAPL"
        assert isinstance(quote.bid, float)
        assert isinstance(quote.ask, float)
        assert isinstance(quote.last, float)
        assert isinstance(quote.bid_size, int)
        assert isinstance(quote.ask_size, int)
        assert quote.bid > 0
        assert quote.ask > quote.bid
        assert quote.last > 0

    def test_quote_for_common_symbols(self, client):
        symbols = ["AAPL", "MSFT", "GOOGL", "AMZN", "SPY"]

        for symbol in symbols:
            quote = client.get_quote(symbol)
            assert quote.symbol == symbol
            assert quote.bid > 0

    def test_quote_spread_is_narrow(self, client):
        quote = client.get_quote("SPY")
        spread_pct = (quote.ask - quote.bid) / quote.mid * 100

        # SPY should have very tight spread
        assert spread_pct < 0.1


class TestSimulatedOrderFlow:
    """Tests for complete order flow in simulation mode."""

    @pytest.fixture
    def client(self):
        client = SimulatedIBKRClient()
        client.connect()
        client.clear_orders()
        yield client
        client.disconnect()

    def test_full_market_order_lifecycle(self, client):
        # Submit order
        order = client.submit_order(
            symbol="AAPL",
            side="BUY",
            quantity=100,
            order_type="MKT",
        )

        # Verify filled
        assert order.status == "Filled"
        assert order.filled_quantity == 100
        assert order.fill_price > 0

        # Verify in registry
        retrieved = client.get_order(order.order_id)
        assert retrieved.status == "Filled"

    def test_limit_order_and_cancel(self, client):
        quote = client.get_quote("AAPL")

        # Submit limit order that won't fill
        order = client.submit_order(
            symbol="AAPL",
            side="BUY",
            quantity=50,
            order_type="LMT",
            limit_price=quote.bid * 0.50,  # Way below market
        )

        assert order.status == "Submitted"

        # Cancel it
        success = client.cancel_order(order.order_id)
        assert success is True

        # Verify cancelled
        updated = client.get_order(order.order_id)
        assert updated.status == "Cancelled"

    def test_multiple_orders_tracked(self, client):
        # Submit multiple orders
        order1 = client.submit_order("AAPL", "BUY", 10, "MKT")
        order2 = client.submit_order("MSFT", "BUY", 20, "MKT")
        order3 = client.submit_order("GOOGL", "SELL", 5, "MKT")

        all_orders = client.get_all_orders()
        assert len(all_orders) == 3

        symbols = {o.symbol for o in all_orders}
        assert symbols == {"AAPL", "MSFT", "GOOGL"}


class TestSimulatedAccountInfo:
    """Tests for account information in simulation mode."""

    def test_managed_accounts_when_connected(self):
        client = SimulatedIBKRClient(account_id="TEST123")
        client.connect()

        assert client.managed_accounts == ["TEST123"]
        client.disconnect()

    def test_managed_accounts_when_disconnected(self):
        client = SimulatedIBKRClient()
        assert client.managed_accounts == []

    def test_server_time_returns_current_time(self):
        client = SimulatedIBKRClient()
        client.connect()

        from datetime import datetime

        before = datetime.now()
        server_time = client.get_server_time()
        after = datetime.now()

        assert before <= server_time <= after
        client.disconnect()


class TestSimulatedIBInterface:
    """Tests for SimulatedIB compatibility interface."""

    @pytest.fixture
    def client(self):
        client = SimulatedIBKRClient()
        client.connect()
        yield client
        client.disconnect()

    def test_ib_is_connected(self, client):
        assert client.ib.isConnected() is True

    def test_ib_managed_accounts(self, client):
        accounts = client.ib.managedAccounts()
        assert accounts == ["SIM000001"]

    def test_ib_req_current_time(self, client):
        from datetime import datetime

        time = client.ib.reqCurrentTime()
        assert isinstance(time, datetime)

    def test_ib_disconnect(self, client):
        client.ib.disconnect()
        assert client.ib.isConnected() is False


class TestSimulationMetrics:
    """Tests for metrics in simulation mode."""

    @pytest.fixture(autouse=True)
    def reset_metrics(self):
        from ibkr_core.metrics import get_metrics

        metrics = get_metrics()
        metrics.reset()
        yield
        metrics.reset()

    def test_connect_records_metrics(self):
        from ibkr_core.metrics import get_metrics

        client = SimulatedIBKRClient()
        client.connect()

        metrics = get_metrics()
        all_data = metrics.get_all_metrics()

        # Should have connection metric
        assert "ibkr_operations_total" in all_data["counters"]

        client.disconnect()

    def test_connection_status_gauge_updated(self):
        from ibkr_core.metrics import get_metrics

        client = SimulatedIBKRClient()

        metrics = get_metrics()
        # Initially disconnected
        assert (
            metrics.gauge_get("ibkr_connection_status", labels={"mode": "simulation"})
            == 0.0
        )

        client.connect()
        assert (
            metrics.gauge_get("ibkr_connection_status", labels={"mode": "simulation"})
            == 1.0
        )

        client.disconnect()
        assert (
            metrics.gauge_get("ibkr_connection_status", labels={"mode": "simulation"})
            == 0.0
        )


class TestSimulationThreadSafety:
    """Tests for thread safety in simulation mode."""

    def test_concurrent_order_submission(self):
        from concurrent.futures import ThreadPoolExecutor

        client = SimulatedIBKRClient()
        client.connect()
        client.clear_orders()

        def submit_order(i):
            return client.submit_order(
                symbol="AAPL",
                side="BUY",
                quantity=i + 1,
                order_type="MKT",
            )

        with ThreadPoolExecutor(max_workers=10) as executor:
            orders = list(executor.map(submit_order, range(20)))

        assert len(orders) == 20
        assert len(client.get_all_orders()) == 20

        # All should have unique IDs
        order_ids = {o.order_id for o in orders}
        assert len(order_ids) == 20

        client.disconnect()

    def test_concurrent_quote_requests(self):
        from concurrent.futures import ThreadPoolExecutor

        client = SimulatedIBKRClient()
        client.connect()

        def get_quote(symbol):
            return client.get_quote(symbol)

        symbols = ["AAPL", "MSFT", "GOOGL"] * 10

        with ThreadPoolExecutor(max_workers=10) as executor:
            quotes = list(executor.map(get_quote, symbols))

        assert len(quotes) == 30
        assert all(q.bid > 0 for q in quotes)

        client.disconnect()
