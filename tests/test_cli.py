"""
Tests for CLI module.
"""

from datetime import datetime
from unittest.mock import MagicMock, Mock, patch

import pytest
from typer.testing import CliRunner

from ibkr_core.cli import app
from ibkr_core.client import ConnectionError
from ibkr_core.config import InvalidConfigError

# Test runner
runner = CliRunner()


# =============================================================================
# Unit Tests
# =============================================================================


def test_cli_help():
    """Test CLI help message."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "IBKR Gateway CLI" in result.output
    assert "healthcheck" in result.output
    assert "demo" in result.output
    assert "start-api" in result.output


def test_cli_version():
    """Test version command."""
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "IBKR Gateway" in result.output
    assert "0.1.0" in result.output


def test_cli_mutually_exclusive_flags():
    """Test that --paper and --live are mutually exclusive."""
    result = runner.invoke(app, ["--paper", "--live", "healthcheck"])
    assert result.exit_code == 1
    assert "mutually exclusive" in result.output


def test_healthcheck_help():
    """Test healthcheck command help."""
    result = runner.invoke(app, ["healthcheck", "--help"])
    assert result.exit_code == 0
    assert "Check IBKR Gateway connection" in result.output


def test_healthcheck_success():
    """Test successful health check."""
    mock_client = Mock()
    mock_client.ib.reqCurrentTime.return_value = datetime.now().timestamp()
    mock_client.ib.managedAccounts.return_value = ["DU123456"]

    with patch("ibkr_core.cli.create_client", return_value=mock_client):
        with patch("ibkr_core.cli.get_config") as mock_config:
            mock_config.return_value = Mock(
                trading_mode="paper",
                ibkr_gateway_host="127.0.0.1",
                paper_gateway_port=4002,
                paper_client_id=1,
            )
            result = runner.invoke(app, ["healthcheck"])

    assert result.exit_code == 0
    assert "Connected successfully" in result.output
    assert "Health check passed" in result.output
    mock_client.disconnect.assert_called_once()


def test_healthcheck_connection_error():
    """Test health check with connection error."""
    with patch("ibkr_core.cli.create_client") as mock_create:
        mock_create.side_effect = ConnectionError("Gateway not running")

        with patch("ibkr_core.cli.get_config") as mock_config:
            mock_config.return_value = Mock(
                trading_mode="paper",
                ibkr_gateway_host="127.0.0.1",
                paper_gateway_port=4002,
                paper_client_id=1,
            )
            result = runner.invoke(app, ["healthcheck"])

    assert result.exit_code == 1
    assert "Connection failed" in result.output
    assert "Troubleshooting" in result.output


def test_healthcheck_config_error():
    """Test health check with config error."""
    with patch("ibkr_core.cli.get_config") as mock_config:
        mock_config.side_effect = InvalidConfigError("Invalid config")
        result = runner.invoke(app, ["healthcheck"])

    assert result.exit_code == 1
    assert "Configuration error" in result.output


def test_healthcheck_with_paper_flag():
    """Test health check with --paper flag."""
    mock_client = Mock()
    mock_client.ib.reqCurrentTime.return_value = datetime.now().timestamp()
    mock_client.ib.managedAccounts.return_value = ["DU123456"]

    with patch("ibkr_core.cli.create_client", return_value=mock_client):
        with patch("ibkr_core.cli.get_config") as mock_config:
            mock_config.return_value = Mock(
                trading_mode="paper",
                ibkr_gateway_host="127.0.0.1",
                paper_gateway_port=4002,
                paper_client_id=1,
            )
            result = runner.invoke(app, ["--paper", "healthcheck"])

    assert result.exit_code == 0
    assert "PAPER" in result.output


def test_demo_help():
    """Test demo command help."""
    result = runner.invoke(app, ["demo", "--help"])
    assert result.exit_code == 0
    assert "Run interactive demo" in result.output


def test_demo_success():
    """Test successful demo execution."""
    with patch("ibkr_core.cli.demo_module.main", return_value=0):
        result = runner.invoke(app, ["demo"])

    assert result.exit_code == 0


def test_demo_failure():
    """Test demo execution with failure."""
    with patch("ibkr_core.cli.demo_module.main", return_value=1):
        result = runner.invoke(app, ["demo"])

    assert result.exit_code == 1


def test_demo_forces_paper_mode():
    """Test that demo forces paper mode even when --live is specified."""
    with patch("ibkr_core.cli.demo_module.main", return_value=0):
        with patch("ibkr_core.cli.reset_config"):
            result = runner.invoke(app, ["--live", "demo"])

    assert result.exit_code == 0
    assert "paper" in result.output.lower() or "safety" in result.output.lower()


def test_start_api_help():
    """Test start-api command help."""
    result = runner.invoke(app, ["start-api", "--help"])
    assert result.exit_code == 0
    assert "Start the FastAPI REST server" in result.output


def test_start_api_displays_config():
    """Test that start-api displays configuration before starting."""
    with patch("ibkr_core.cli.subprocess.run") as mock_run:
        mock_run.side_effect = KeyboardInterrupt()  # Stop immediately

        result = runner.invoke(app, ["start-api"])

    assert "Starting IBKR Gateway API Server" in result.output
    assert "Host" in result.output
    assert "Port" in result.output
    assert "8000" in result.output  # Default port


def test_start_api_with_custom_port():
    """Test start-api with custom port."""
    with patch("ibkr_core.cli.subprocess.run") as mock_run:
        mock_run.side_effect = KeyboardInterrupt()

        result = runner.invoke(app, ["start-api", "--port", "8080"])

    assert "8080" in result.output


def test_start_api_with_reload():
    """Test start-api with reload flag."""
    with patch("ibkr_core.cli.subprocess.run") as mock_run:
        mock_run.side_effect = KeyboardInterrupt()

        result = runner.invoke(app, ["start-api", "--reload"])

    assert "Auto-reload" in result.output
    # Verify --reload was passed to subprocess
    mock_run.assert_called_once()
    call_args = mock_run.call_args[0][0]
    assert "--reload" in call_args


def test_start_api_keyboard_interrupt():
    """Test start-api handles Ctrl+C gracefully."""
    with patch("ibkr_core.cli.subprocess.run") as mock_run:
        mock_run.side_effect = KeyboardInterrupt()

        result = runner.invoke(app, ["start-api"])

    assert result.exit_code == 0
    assert "stopped" in result.output.lower()


def test_start_api_subprocess_error():
    """Test start-api handles subprocess errors."""
    import subprocess

    with patch("ibkr_core.cli.subprocess.run") as mock_run:
        mock_run.side_effect = subprocess.CalledProcessError(1, "uvicorn")

        result = runner.invoke(app, ["start-api"])

    assert result.exit_code == 1
    assert "failed" in result.output.lower()


def test_start_api_uvicorn_not_found():
    """Test start-api when uvicorn is not installed."""
    with patch("ibkr_core.cli.subprocess.run") as mock_run:
        mock_run.side_effect = FileNotFoundError()

        result = runner.invoke(app, ["start-api"])

    assert result.exit_code == 1
    assert "uvicorn not found" in result.output


# =============================================================================
# Integration Tests
# =============================================================================


@pytest.mark.integration
def test_healthcheck_integration():
    """
    Full integration test of healthcheck command.

    Requires IBKR Gateway running in paper mode.
    """
    result = runner.invoke(app, ["--paper", "healthcheck"])
    # Should succeed if Gateway is running, fail gracefully if not
    assert result.exit_code in [0, 1]


@pytest.mark.integration
def test_demo_integration():
    """
    Full integration test of demo command.

    Requires IBKR Gateway running in paper mode.
    """
    result = runner.invoke(app, ["demo"])
    # Should succeed if Gateway is running, fail gracefully if not
    assert result.exit_code in [0, 1]
