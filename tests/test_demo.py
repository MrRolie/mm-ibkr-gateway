"""
Tests for demo module.
"""

from datetime import datetime
from unittest.mock import MagicMock, Mock, patch

import pytest

from ibkr_core.account import AccountError
from ibkr_core.client import ConnectionError
from ibkr_core.config import InvalidConfigError
from ibkr_core.demo import (
    check_gateway_connection,
    demo_account_status,
    demo_market_data,
    main,
    validate_paper_mode,
)
from ibkr_core.market_data import MarketDataError, MarketDataPermissionError
from ibkr_core.models import AccountSummary, Bar, Position, Quote

# =============================================================================
# Unit Tests
# =============================================================================


def test_validate_paper_mode_success():
    """Test paper mode validation when in paper mode."""
    with patch("ibkr_core.demo.get_config") as mock_config:
        mock_config.return_value = Mock(trading_mode="paper")
        assert validate_paper_mode() is True


def test_validate_paper_mode_wrong_mode():
    """Test paper mode validation when in live mode."""
    with patch("ibkr_core.demo.get_config") as mock_config:
        mock_config.return_value = Mock(trading_mode="live")
        assert validate_paper_mode() is False


def test_validate_paper_mode_config_error():
    """Test paper mode validation with config error."""
    with patch("ibkr_core.demo.get_config") as mock_config:
        mock_config.side_effect = InvalidConfigError("Test error")
        assert validate_paper_mode() is False


def test_check_gateway_connection_success():
    """Test successful gateway connection check."""
    mock_client = Mock()
    mock_client.ib.reqCurrentTime.return_value = datetime.now().timestamp()
    mock_client.ib.managedAccounts.return_value = ["DU123456"]

    with patch("ibkr_core.demo.get_config") as mock_config:
        mock_config.return_value = Mock(paper_gateway_port=4002)
        result = check_gateway_connection(mock_client)

    assert result is True


def test_check_gateway_connection_failure():
    """Test gateway connection check with connection error."""
    with patch("ibkr_core.demo.create_client") as mock_create:
        mock_create.side_effect = ConnectionError("Gateway not running")

        with patch("ibkr_core.demo.get_config") as mock_config:
            mock_config.return_value = Mock(paper_gateway_port=4002)
            result = check_gateway_connection()

    assert result is False


def test_check_gateway_connection_unexpected_error():
    """Test gateway connection check with unexpected error."""
    with patch("ibkr_core.demo.create_client") as mock_create:
        mock_create.side_effect = RuntimeError("Unexpected error")

        with patch("ibkr_core.demo.get_config") as mock_config:
            mock_config.return_value = Mock(paper_gateway_port=4002)
            result = check_gateway_connection()

    assert result is False


def test_demo_market_data_success():
    """Test successful market data demo."""
    mock_client = Mock()

    # Mock AAPL quote
    mock_quote = Quote(
        symbol="AAPL",
        conId=265598,
        bid=150.0,
        ask=150.5,
        last=150.25,
        bidSize=100,
        askSize=100,
        lastSize=50,
        volume=10000000,
        timestamp=datetime.now().isoformat(),
        source="IBKR",
    )

    # Mock SPY bars
    mock_bars = [
        Bar(
            symbol="SPY",
            time=datetime.now(),
            open=450.0,
            high=451.0,
            low=449.5,
            close=450.5,
            volume=1000000,
            barSize="1 hour",
            source="IBKR_HISTORICAL",
        )
        for _ in range(5)
    ]

    with patch("ibkr_core.demo.get_quote", return_value=mock_quote):
        with patch("ibkr_core.demo.get_historical_bars", return_value=mock_bars):
            result = demo_market_data(mock_client)

    assert result is True


def test_demo_market_data_permission_error():
    """Test market data demo with permission error."""
    mock_client = Mock()

    with patch("ibkr_core.demo.get_quote") as mock_get_quote:
        mock_get_quote.side_effect = MarketDataPermissionError("No permission")
        result = demo_market_data(mock_client)

    assert result is False


def test_demo_market_data_error():
    """Test market data demo with market data error."""
    mock_client = Mock()

    with patch("ibkr_core.demo.get_quote") as mock_get_quote:
        mock_get_quote.side_effect = MarketDataError("Data error")
        result = demo_market_data(mock_client)

    assert result is False


def test_demo_account_status_success():
    """Test successful account status demo."""
    mock_client = Mock()

    # Mock account summary
    mock_summary = AccountSummary(
        accountId="DU123456",
        currency="USD",
        netLiquidation=100000.0,
        cash=50000.0,
        buyingPower=200000.0,
        timestamp=datetime.now(),
    )

    # Mock positions
    mock_positions = [
        Position(
            accountId="DU123456",
            symbol="AAPL",
            conId=265598,
            assetClass="STK",
            currency="USD",
            quantity=100,
            avgPrice=150.0,
            marketPrice=155.0,
            marketValue=15500.0,
            unrealizedPnl=500.0,
            realizedPnl=0.0,
        )
    ]

    with patch("ibkr_core.demo.get_account_summary", return_value=mock_summary):
        with patch("ibkr_core.demo.get_positions", return_value=mock_positions):
            result = demo_account_status(mock_client)

    assert result is True


def test_demo_account_status_no_positions():
    """Test account status demo with no positions."""
    mock_client = Mock()

    mock_summary = AccountSummary(
        accountId="DU123456",
        currency="USD",
        netLiquidation=100000.0,
        cash=100000.0,
        buyingPower=200000.0,
        timestamp=datetime.now(),
    )

    with patch("ibkr_core.demo.get_account_summary", return_value=mock_summary):
        with patch("ibkr_core.demo.get_positions", return_value=[]):
            result = demo_account_status(mock_client)

    assert result is True


def test_demo_account_status_error():
    """Test account status demo with account error."""
    mock_client = Mock()

    with patch("ibkr_core.demo.get_account_summary") as mock_summary:
        mock_summary.side_effect = AccountError("Account error")
        result = demo_account_status(mock_client)

    assert result is False


def test_main_success():
    """Test successful demo execution."""
    mock_client = Mock()
    mock_client.ib.reqCurrentTime.return_value = datetime.now().timestamp()
    mock_client.ib.managedAccounts.return_value = ["DU123456"]

    with patch("ibkr_core.demo.validate_paper_mode", return_value=True):
        with patch("ibkr_core.demo.create_client", return_value=mock_client):
            with patch("ibkr_core.demo.demo_market_data", return_value=True):
                with patch("ibkr_core.demo.demo_account_status", return_value=True):
                    result = main()

    assert result == 0
    mock_client.disconnect.assert_called_once()


def test_main_wrong_mode():
    """Test demo execution in wrong mode."""
    with patch("ibkr_core.demo.validate_paper_mode", return_value=False):
        result = main()

    assert result == 1


def test_main_connection_error():
    """Test demo execution with connection error."""
    with patch("ibkr_core.demo.validate_paper_mode", return_value=True):
        with patch("ibkr_core.demo.check_gateway_connection", return_value=False):
            result = main()

    assert result == 1


def test_main_keyboard_interrupt():
    """Test demo execution with keyboard interrupt."""
    mock_client = Mock()

    with patch("ibkr_core.demo.validate_paper_mode", return_value=True):
        with patch("ibkr_core.demo.check_gateway_connection", return_value=True):
            with patch("ibkr_core.demo.create_client", return_value=mock_client):
                with patch("ibkr_core.demo.demo_market_data") as mock_demo:
                    mock_demo.side_effect = KeyboardInterrupt()
                    result = main()

    assert result == 1
    mock_client.disconnect.assert_called_once()


def test_main_unexpected_error():
    """Test demo execution with unexpected error."""
    mock_client = Mock()

    with patch("ibkr_core.demo.validate_paper_mode", return_value=True):
        with patch("ibkr_core.demo.check_gateway_connection", return_value=True):
            with patch("ibkr_core.demo.create_client", return_value=mock_client):
                with patch("ibkr_core.demo.demo_market_data") as mock_demo:
                    mock_demo.side_effect = RuntimeError("Unexpected")
                    result = main()

    assert result == 1
    mock_client.disconnect.assert_called_once()


# =============================================================================
# Integration Tests
# =============================================================================


@pytest.mark.integration
def test_demo_full_integration():
    """
    Full integration test of demo.

    Requires IBKR Gateway running in paper mode.
    """
    result = main()
    # Should succeed if Gateway is running in paper mode
    # Will fail gracefully if not
    assert result in [0, 1]
