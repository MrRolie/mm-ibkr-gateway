"""
Tests for SimulatedIBKRClient behavior.

Verifies the simulated client provides the same interface as IBKRClient
and produces consistent, realistic simulated data.
"""

from datetime import datetime

import pytest

from ibkr_core.simulation import (
    SimulatedIBKRClient,
    SimulatedOrder,
    SimulatedQuote,
    get_ibkr_client,
)


class TestSimulatedIBKRClientConnection:
    """Tests for connection lifecycle."""

    def test_initial_state_disconnected(self):
        client = SimulatedIBKRClient()
        assert not client.is_connected
        assert client.connection_time is None
        assert client.managed_accounts == []

    def test_connect_succeeds(self):
        client = SimulatedIBKRClient()
        client.connect()
        assert client.is_connected
        assert client.connection_time is not None
        assert isinstance(client.connection_time, datetime)

    def test_connect_idempotent(self):
        client = SimulatedIBKRClient()
        client.connect()
        first_time = client.connection_time
        client.connect()
        assert client.connection_time == first_time

    def test_disconnect(self):
        client = SimulatedIBKRClient()
        client.connect()
        client.disconnect()
        assert not client.is_connected
        assert client.connection_time is None

    def test_disconnect_when_not_connected(self):
        client = SimulatedIBKRClient()
        client.disconnect()  # Should not raise
        assert not client.is_connected

    def test_ensure_connected(self):
        client = SimulatedIBKRClient()
        assert not client.is_connected
        client.ensure_connected()
        assert client.is_connected

    def test_context_manager(self):
        with SimulatedIBKRClient() as client:
            assert client.is_connected
        assert not client.is_connected


class TestSimulatedIBKRClientProperties:
    """Tests for client properties."""

    def test_mode_is_simulation(self):
        client = SimulatedIBKRClient()
        assert client.mode == "simulation"

    def test_default_account_id(self):
        client = SimulatedIBKRClient()
        client.connect()
        assert client.managed_accounts == ["SIM000001"]

    def test_custom_account_id(self):
        client = SimulatedIBKRClient(account_id="CUSTOM123")
        client.connect()
        assert client.managed_accounts == ["CUSTOM123"]

    def test_client_id(self):
        client = SimulatedIBKRClient(client_id=123)
        assert client.client_id == 123

    def test_default_client_id(self):
        client = SimulatedIBKRClient()
        assert client.client_id == 999

    def test_host_and_port(self):
        client = SimulatedIBKRClient()
        assert client.host == "simulation"
        assert client.port == 0

    def test_ib_interface(self):
        client = SimulatedIBKRClient()
        client.connect()
        assert client.ib.isConnected()
        assert client.ib.managedAccounts() == ["SIM000001"]

    def test_repr(self):
        client = SimulatedIBKRClient()
        assert "SimulatedIBKRClient" in repr(client)
        assert "disconnected" in repr(client)
        client.connect()
        assert "connected" in repr(client)


class TestSimulatedIBKRClientServerTime:
    """Tests for server time."""

    def test_get_server_time(self):
        client = SimulatedIBKRClient()
        client.connect()
        server_time = client.get_server_time()
        assert isinstance(server_time, datetime)
        # Should be close to now
        diff = abs((datetime.now() - server_time).total_seconds())
        assert diff < 1.0

    def test_get_server_time_when_disconnected(self):
        client = SimulatedIBKRClient()
        with pytest.raises(RuntimeError, match="Not connected"):
            client.get_server_time()


class TestSimulatedQuotes:
    """Tests for quote generation."""

    def test_get_quote_for_known_symbol(self):
        client = SimulatedIBKRClient()
        client.connect()
        quote = client.get_quote("AAPL")

        assert isinstance(quote, SimulatedQuote)
        assert quote.symbol == "AAPL"
        assert quote.bid > 0
        assert quote.ask > quote.bid
        assert quote.last > 0

    def test_get_quote_for_unknown_symbol(self):
        client = SimulatedIBKRClient()
        client.connect()
        quote = client.get_quote("UNKNOWN")

        assert quote.symbol == "UNKNOWN"
        # Should use default price
        assert 50 < quote.mid < 150

    def test_quote_consistency(self):
        client = SimulatedIBKRClient()
        client.connect()

        # Multiple calls should return similar prices
        quotes = [client.get_quote("MSFT") for _ in range(5)]
        prices = [q.mid for q in quotes]

        # All prices should be within 1% of each other
        min_price = min(prices)
        max_price = max(prices)
        assert (max_price - min_price) / min_price < 0.01

    def test_quote_mid_price(self):
        client = SimulatedIBKRClient()
        client.connect()
        quote = client.get_quote("SPY")

        expected_mid = (quote.bid + quote.ask) / 2
        assert abs(quote.mid - expected_mid) < 0.01

    def test_get_quote_when_disconnected(self):
        client = SimulatedIBKRClient()
        with pytest.raises(RuntimeError, match="Not connected"):
            client.get_quote("AAPL")

    def test_quote_spread_is_realistic(self):
        client = SimulatedIBKRClient()
        client.connect()
        quote = client.get_quote("AAPL")

        spread = quote.ask - quote.bid
        spread_percent = spread / quote.mid * 100

        # Spread should be less than 0.1%
        assert spread_percent < 0.1


class TestGetIBKRClientFactory:
    """Tests for get_ibkr_client factory function."""

    def test_simulation_mode(self):
        client = get_ibkr_client(mode="simulation")
        assert isinstance(client, SimulatedIBKRClient)

    def test_paper_mode_returns_ibkr_client(self):
        from ibkr_core.client import IBKRClient

        client = get_ibkr_client(mode="paper")
        assert isinstance(client, IBKRClient)

    def test_live_mode_returns_ibkr_client(self):
        from ibkr_core.client import IBKRClient

        client = get_ibkr_client(mode="live")
        assert isinstance(client, IBKRClient)

    def test_env_var_override(self, monkeypatch):
        monkeypatch.setenv("IBKR_MODE", "simulation")
        client = get_ibkr_client()
        assert isinstance(client, SimulatedIBKRClient)

    def test_explicit_mode_overrides_env(self, monkeypatch):
        from ibkr_core.client import IBKRClient

        monkeypatch.setenv("IBKR_MODE", "simulation")
        client = get_ibkr_client(mode="paper")
        assert isinstance(client, IBKRClient)
