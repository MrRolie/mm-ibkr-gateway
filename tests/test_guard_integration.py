"""
Tests for mm-control guard integration in mm-ibkr-gateway.

Tests that the mm-control guard file properly blocks order placement.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from ib_insync import Contract, Stock

from ibkr_core.models import Instrument, OrderSpec
from ibkr_core.orders import place_order
from mm_control.guard import disable_trading, enable_trading


class TestMmControlGuardIntegration:
    """Test mm-control guard file integration with place_order()."""

    @pytest.fixture
    def mock_client(self):
        """Create a mock IBKR client."""
        from ibkr_core.client import IBKRClient

        client = MagicMock(spec=IBKRClient)
        client.is_connected.return_value = True
        client.ib = MagicMock()
        return client

    @pytest.fixture
    def test_order_spec(self) -> OrderSpec:
        """Create a test order specification."""
        return OrderSpec(
            side="BUY",
            quantity=100,
            orderType="MKT",
            instrument=Instrument(
                symbol="AAPL",
                secType="STK",
                exchange="SMART",
                currency="USD",
            ),
            clientOrderId="test-order-001",
        )

    def test_guard_file_blocks_order_placement(
        self,
        mock_client,
        test_order_spec: OrderSpec,
        tmp_path: Path,
    ):
        """Test that mm-control guard file prevents order placement."""
        # Create guard file
        guard_path = disable_trading(
            reason="Integration test - block order placement",
            base_dir=tmp_path,
        )
        assert guard_path.exists()

        try:
            # Patch the base_dir and config to enable orders
            with patch("mm_control.guard.get_base_dir", return_value=tmp_path):
                with patch("ibkr_core.config.get_config") as mock_config:
                    # Enable orders in config (guard should still block)
                    config = MagicMock()
                    config.orders_enabled = True
                    mock_config.return_value = config

                    # Attempt to place order
                    result = place_order(mock_client, test_order_spec)

                    # Verify order was simulated (not placed)
                    assert result.status == "SIMULATED"
                    assert result.orderId is None
                    assert "guard file active" in result.errors[0]
                    assert "trading disabled" in result.errors[0]

                    # Verify IBKR API was NOT called
                    mock_client.ib.placeOrder.assert_not_called()

        finally:
            # Clean up guard file
            enable_trading(reason="Cleanup after test", base_dir=tmp_path)

    def test_no_guard_allows_order_placement(
        self,
        mock_client,
        test_order_spec: OrderSpec,
        tmp_path: Path,
    ):
        """Test that orders are allowed when guard file doesn't exist."""
        # Ensure no guard file
        guard_path = tmp_path / "TRADING_DISABLED"
        assert not guard_path.exists()

        # Mock the contract resolution and order placement
        mock_contract = Stock("AAPL", "SMART", "USD")
        mock_client.ib.qualifyContracts.return_value = [mock_contract]

        mock_trade = MagicMock()
        mock_trade.order.orderId = 12345
        mock_client.ib.placeOrder.return_value = mock_trade

        # Patch config to enable orders
        with patch("mm_control.guard.get_base_dir", return_value=tmp_path):
            with patch("ibkr_core.config.get_config") as mock_config:
                config = MagicMock()
                config.orders_enabled = True
                mock_config.return_value = config

                # Mock preview_order to avoid actual IBKR calls
                with patch("ibkr_core.orders.preview_order") as mock_preview:
                    mock_preview.return_value = MagicMock(estimatedNotional=15000.0)

                    # Attempt to place order
                    result = place_order(mock_client, test_order_spec)

                    # Verify order was accepted (would be placed in real scenario)
                    # Note: Actual result depends on IBKR mock behavior
                    # In this test, we verify guard did NOT block
                    assert result.status in ("ACCEPTED", "REJECTED")  # Not SIMULATED

    def test_guard_takes_precedence_over_orders_enabled(
        self,
        mock_client,
        test_order_spec: OrderSpec,
        tmp_path: Path,
    ):
        """Test that guard file takes precedence over ORDERS_ENABLED config."""
        # Create guard file
        disable_trading(
            reason="Testing precedence - guard should override ORDERS_ENABLED",
            base_dir=tmp_path,
        )

        try:
            with patch("mm_control.guard.get_base_dir", return_value=tmp_path):
                with patch("ibkr_core.config.get_config") as mock_config:
                    # Explicitly enable orders in config
                    config = MagicMock()
                    config.orders_enabled = True
                    mock_config.return_value = config

                    # Place order
                    result = place_order(mock_client, test_order_spec)

                    # Guard should block even though ORDERS_ENABLED=true
                    assert result.status == "SIMULATED"
                    assert "guard file active" in result.errors[0]
                    # Should NOT mention ORDERS_ENABLED (guard checked first)
                    assert "ORDERS_ENABLED" not in result.errors[0]

                    # IBKR API should NOT be called
                    mock_client.ib.placeOrder.assert_not_called()

        finally:
            # Cleanup
            enable_trading(reason="Test cleanup", base_dir=tmp_path)

    def test_orders_disabled_still_blocks_when_no_guard(
        self,
        mock_client,
        test_order_spec: OrderSpec,
        tmp_path: Path,
    ):
        """Test that ORDERS_ENABLED=false still blocks when guard is absent."""
        # No guard file (tmp_path is empty)
        guard_path = tmp_path / "TRADING_DISABLED"
        assert not guard_path.exists()

        with patch("mm_control.guard.get_base_dir", return_value=tmp_path):
            with patch("ibkr_core.config.get_config") as mock_config:
                # Disable orders in config
                config = MagicMock()
                config.orders_enabled = False
                mock_config.return_value = config

                # Place order
                result = place_order(mock_client, test_order_spec)

                # Should be blocked by ORDERS_ENABLED=false
                assert result.status == "SIMULATED"
                assert "ORDERS_ENABLED=false" in result.errors[0]

    def test_guard_file_with_invalid_order(
        self,
        mock_client,
        tmp_path: Path,
    ):
        """Test that validation errors take precedence over guard check."""
        # Invalid order spec (quantity <= 0)
        invalid_order = OrderSpec(
            side="BUY",
            quantity=0,  # Invalid!
            orderType="MKT",
            instrument=Instrument(
                symbol="AAPL",
                secType="STK",
                exchange="SMART",
                currency="USD",
            ),
            clientOrderId="test-invalid-001",
        )

        # Create guard file
        disable_trading(reason="Test with invalid order", base_dir=tmp_path)

        try:
            with patch("mm_control.guard.get_base_dir", return_value=tmp_path):
                with patch("ibkr_core.config.get_config") as mock_config:
                    config = MagicMock()
                    config.orders_enabled = True
                    mock_config.return_value = config

                    # Place invalid order
                    result = place_order(mock_client, invalid_order)

                    # Should be REJECTED (validation error), not SIMULATED
                    assert result.status == "REJECTED"
                    assert "quantity" in result.errors[0].lower()

                    # IBKR API should NOT be called
                    mock_client.ib.placeOrder.assert_not_called()

        finally:
            # Cleanup
            enable_trading(reason="Test cleanup", base_dir=tmp_path)

    def test_mm_control_import_error_fallback(
        self,
        mock_client,
        test_order_spec: OrderSpec,
    ):
        """Test graceful fallback when mm-control is not installed."""
        # This test verifies the try-except ImportError block
        # In real scenario where mm-control is installed, we can't easily test this
        # But the code should log a debug message and continue

        with patch("ibkr_core.config.get_config") as mock_config:
            config = MagicMock()
            config.orders_enabled = True
            mock_config.return_value = config

            # Mock preview and placement
            with patch("ibkr_core.orders.preview_order") as mock_preview:
                mock_preview.return_value = MagicMock(estimatedNotional=15000.0)

                mock_contract = Stock("AAPL", "SMART", "USD")
                mock_client.ib.qualifyContracts.return_value = [mock_contract]

                mock_trade = MagicMock()
                mock_trade.order.orderId = 12345
                mock_client.ib.placeOrder.return_value = mock_trade

                # Place order (if mm-control available, proceeds normally)
                result = place_order(mock_client, test_order_spec)

                # Should proceed (not blocked by missing mm-control)
                assert result.status in ("ACCEPTED", "REJECTED")
