"""
Unit tests for config module.

Tests:
  - Configuration loading from environment
  - Validation of TRADING_MODE
  - Validation of ORDERS_ENABLED
  - TradingDisabledError when orders are disabled
  - Invalid configuration detection
"""

import os
import tempfile
from pathlib import Path

import pytest

from ibkr_core.config import (
    Config,
    InvalidConfigError,
    TradingDisabledError,
    get_config,
    load_config,
    reset_config,
)


@pytest.fixture(autouse=True)
def reset_config_fixture():
    """Reset config before each test."""
    reset_config()
    # Save and clear relevant env vars
    old_env = {}
    env_keys = [
        "IBKR_GATEWAY_HOST",
        "PAPER_GATEWAY_PORT",
        "PAPER_CLIENT_ID",
        "LIVE_GATEWAY_PORT",
        "LIVE_CLIENT_ID",
        "TRADING_MODE",
        "ORDERS_ENABLED",
        "API_PORT",
        "LOG_LEVEL",
        "LIVE_TRADING_OVERRIDE_FILE",
    ]
    for key in env_keys:
        old_env[key] = os.environ.get(key)
        if key in os.environ:
            del os.environ[key]

    yield

    # Restore
    for key, value in old_env.items():
        if value is not None:
            os.environ[key] = value
        elif key in os.environ:
            del os.environ[key]
    reset_config()


class TestConfigDefaults:
    """Test default configuration values."""

    def test_defaults(self):
        """Test that defaults are applied when env vars are not set."""
        config = load_config()

        assert config.ibkr_gateway_host == "127.0.0.1"
        assert config.paper_gateway_port == 4002
        assert config.paper_client_id == 1
        assert config.live_gateway_port == 4001
        assert config.live_client_id == 777
        # Since default mode is paper, port should be paper port
        assert config.ibkr_gateway_port == 4002
        assert config.client_id == 1
        assert config.trading_mode == "paper"
        assert config.orders_enabled is False
        assert config.api_port == 8000
        assert config.log_level == "INFO"


class TestTradingMode:
    """Test TRADING_MODE validation."""

    def test_valid_paper_mode(self):
        """Test that paper mode is valid."""
        os.environ["TRADING_MODE"] = "paper"
        config = load_config()
        assert config.trading_mode == "paper"

    def test_valid_live_mode(self):
        """Test that live mode is valid (with orders disabled)."""
        os.environ["TRADING_MODE"] = "live"
        os.environ["ORDERS_ENABLED"] = "false"
        config = load_config()
        assert config.trading_mode == "live"

    def test_invalid_trading_mode(self):
        """Test that invalid TRADING_MODE raises InvalidConfigError."""
        os.environ["TRADING_MODE"] = "invalid"
        with pytest.raises(InvalidConfigError, match="TRADING_MODE must be"):
            load_config()

    def test_trading_mode_case_insensitive(self):
        """Test that TRADING_MODE is case-insensitive."""
        os.environ["TRADING_MODE"] = "PAPER"
        config = load_config()
        assert config.trading_mode == "paper"


class TestOrdersEnabled:
    """Test ORDERS_ENABLED validation."""

    def test_orders_enabled_false(self):
        """Test that ORDERS_ENABLED=false is parsed correctly."""
        os.environ["ORDERS_ENABLED"] = "false"
        config = load_config()
        assert config.orders_enabled is False

    def test_orders_enabled_true(self):
        """Test that ORDERS_ENABLED=true is parsed correctly."""
        os.environ["TRADING_MODE"] = "paper"
        os.environ["ORDERS_ENABLED"] = "true"
        config = load_config()
        assert config.orders_enabled is True

    def test_orders_enabled_yes(self):
        """Test that ORDERS_ENABLED=yes is parsed as true."""
        os.environ["TRADING_MODE"] = "paper"
        os.environ["ORDERS_ENABLED"] = "yes"
        config = load_config()
        assert config.orders_enabled is True

    def test_orders_enabled_1(self):
        """Test that ORDERS_ENABLED=1 is parsed as true."""
        os.environ["TRADING_MODE"] = "paper"
        os.environ["ORDERS_ENABLED"] = "1"
        config = load_config()
        assert config.orders_enabled is True


class TestLiveTradingOverride:
    """Test live trading override requirement."""

    def test_live_mode_with_orders_enabled_requires_override(self):
        """Test that live mode + orders enabled requires override file."""
        os.environ["TRADING_MODE"] = "live"
        os.environ["ORDERS_ENABLED"] = "true"

        with pytest.raises(InvalidConfigError, match="LIVE_TRADING_OVERRIDE_FILE"):
            load_config()

    def test_live_mode_with_orders_enabled_and_override_file(self):
        """Test that live mode + orders enabled works with override file."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
            f.write("override")
            override_path = f.name

        try:
            os.environ["TRADING_MODE"] = "live"
            os.environ["ORDERS_ENABLED"] = "true"
            os.environ["LIVE_TRADING_OVERRIDE_FILE"] = override_path

            config = load_config()
            assert config.trading_mode == "live"
            assert config.orders_enabled is True
        finally:
            Path(override_path).unlink()


class TestTradingDisabledError:
    """Test TradingDisabledError behavior."""

    def test_check_trading_enabled_raises_when_disabled(self):
        """Test that check_trading_enabled raises when orders are disabled."""
        os.environ["ORDERS_ENABLED"] = "false"
        config = load_config()

        with pytest.raises(TradingDisabledError):
            config.check_trading_enabled()

    def test_check_trading_enabled_ok_when_enabled(self):
        """Test that check_trading_enabled does not raise when orders are enabled."""
        os.environ["TRADING_MODE"] = "paper"
        os.environ["ORDERS_ENABLED"] = "true"
        config = load_config()

        # Should not raise
        config.check_trading_enabled()


class TestInvalidConfiguration:
    """Test invalid configuration handling."""

    def test_invalid_ibkr_port(self):
        """Test that invalid PAPER_GATEWAY_PORT raises InvalidConfigError."""
        os.environ["PAPER_GATEWAY_PORT"] = "not_a_number"

        with pytest.raises(InvalidConfigError, match="PAPER_GATEWAY_PORT must be an integer"):
            load_config()

    def test_invalid_api_port(self):
        """Test that invalid API_PORT raises InvalidConfigError."""
        os.environ["API_PORT"] = "not_a_number"

        with pytest.raises(InvalidConfigError, match="API_PORT must be an integer"):
            load_config()


class TestGlobalConfig:
    """Test global config singleton."""

    def test_get_config_singleton(self):
        """Test that get_config returns the same instance."""
        config1 = get_config()
        config2 = get_config()

        assert config1 is config2

    def test_reset_config(self):
        """Test that reset_config clears the singleton."""
        config1 = get_config()
        reset_config()
        config2 = get_config()

        # Different instances
        assert config1 is not config2
