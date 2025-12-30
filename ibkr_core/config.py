"""
Configuration management and safety rails for IBKR integration.
"""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

# Load .env file
env_file = Path(__file__).parent.parent / ".env"
if env_file.exists():
    load_dotenv(env_file)


class TradingDisabledError(Exception):
    """Raised when order placement is attempted but ORDERS_ENABLED=false."""

    pass


class InvalidConfigError(Exception):
    """Raised when configuration is invalid."""

    pass


@dataclass
class Config:
    """Central configuration holder."""

    # IBKR Connection
    ibkr_gateway_host: str

    # Paper trading connection
    paper_gateway_port: int
    paper_client_id: int

    # Live trading connection
    live_gateway_port: int
    live_client_id: int

    # Trading Mode
    trading_mode: str  # "paper" or "live"
    orders_enabled: bool

    # API Server
    api_port: int
    api_bind_host: str
    log_level: str

    # Path settings
    gdrive_base_path: Optional[str]
    log_file_path: Optional[str]
    
    # Arm file for orders (additional safety layer)
    arm_orders_file: Optional[str]

    # Override file for live trading (for extra safety)
    live_trading_override_file: Optional[str]

    @property
    def ibkr_gateway_port(self) -> int:
        """Return the appropriate gateway port based on trading mode."""
        return self.live_gateway_port if self.trading_mode == "live" else self.paper_gateway_port

    @property
    def client_id(self) -> int:
        """Return the appropriate client ID based on trading mode."""
        return self.live_client_id if self.trading_mode == "live" else self.paper_client_id

    def validate(self) -> None:
        """Validate configuration."""
        if self.trading_mode not in ("paper", "live"):
            raise InvalidConfigError(
                f"TRADING_MODE must be 'paper' or 'live', got '{self.trading_mode}'"
            )

        if self.trading_mode == "live" and self.orders_enabled:
            # Extra safety check
            if self.live_trading_override_file:
                override_path = Path(self.live_trading_override_file)
                if not override_path.exists():
                    raise InvalidConfigError(
                        f"TRADING_MODE=live and ORDERS_ENABLED=true requires override file "
                        f"at {self.live_trading_override_file}"
                    )
            else:
                raise InvalidConfigError(
                    "TRADING_MODE=live and ORDERS_ENABLED=true is extremely dangerous. "
                    "Set LIVE_TRADING_OVERRIDE_FILE to proceed."
                )

    def check_trading_enabled(self) -> None:
        """Raise TradingDisabledError if orders are not enabled."""
        if not self.orders_enabled:
            raise TradingDisabledError(
                "Order placement is disabled (ORDERS_ENABLED=false). "
                "Set ORDERS_ENABLED=true in .env to enable."
            )


def load_config() -> Config:
    """Load and validate configuration from environment."""

    # IBKR Connection
    ibkr_host = os.getenv("IBKR_GATEWAY_HOST", "127.0.0.1")

    # Paper trading connection
    try:
        paper_port = int(os.getenv("PAPER_GATEWAY_PORT", "4002"))
    except ValueError:
        raise InvalidConfigError("PAPER_GATEWAY_PORT must be an integer")

    try:
        paper_client_id = int(os.getenv("PAPER_CLIENT_ID", "1"))
    except ValueError:
        raise InvalidConfigError("PAPER_CLIENT_ID must be an integer")

    # Live trading connection
    try:
        live_port = int(os.getenv("LIVE_GATEWAY_PORT", "4001"))
    except ValueError:
        raise InvalidConfigError("LIVE_GATEWAY_PORT must be an integer")

    try:
        live_client_id = int(os.getenv("LIVE_CLIENT_ID", "777"))
    except ValueError:
        raise InvalidConfigError("LIVE_CLIENT_ID must be an integer")

    # Trading Mode
    trading_mode = os.getenv("TRADING_MODE", "paper").lower()
    orders_enabled_str = os.getenv("ORDERS_ENABLED", "false").lower()
    orders_enabled = orders_enabled_str in ("true", "yes", "1")

    # API Server
    try:
        api_port = int(os.getenv("API_PORT", "8000"))
    except ValueError:
        raise InvalidConfigError("API_PORT must be an integer")

    # API bind host (for LAN access)
    api_bind_host = os.getenv("API_BIND_HOST", "127.0.0.1")

    log_level = os.getenv("LOG_LEVEL", "INFO").upper()

    # Path settings
    gdrive_base_path = os.getenv("GDRIVE_BASE_PATH")
    log_file_path = os.getenv("LOG_FILE_PATH")
    arm_orders_file = os.getenv("ARM_ORDERS_FILE")

    # Live Trading Override
    live_trading_override_file = os.getenv("LIVE_TRADING_OVERRIDE_FILE")

    config = Config(
        ibkr_gateway_host=ibkr_host,
        paper_gateway_port=paper_port,
        paper_client_id=paper_client_id,
        live_gateway_port=live_port,
        live_client_id=live_client_id,
        trading_mode=trading_mode,
        orders_enabled=orders_enabled,
        api_port=api_port,
        api_bind_host=api_bind_host,
        log_level=log_level,
        gdrive_base_path=gdrive_base_path,
        log_file_path=log_file_path,
        arm_orders_file=arm_orders_file,
        live_trading_override_file=live_trading_override_file,
    )

    config.validate()
    return config


# Global config instance
_config: Optional[Config] = None


def get_config() -> Config:
    """Get the global config instance, loading if necessary."""
    global _config
    if _config is None:
        _config = load_config()
    return _config


def reset_config() -> None:
    """Reset config (useful for testing)."""
    global _config
    _config = None
