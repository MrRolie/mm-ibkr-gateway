"""
Healthcheck script for IBKR connection.

Usage:
    python scripts/healthcheck.py [paper|live]
    python -m scripts.healthcheck [paper|live]

Connects to IBKR, queries server time, prints it, then disconnects.
Exit codes:
    0 = success
    1 = error (IBKR down, connection failure, etc.)
"""

import sys
from pathlib import Path
from typing import Optional

# Add parent directory to path to import ibkr_core
sys.path.insert(0, str(Path(__file__).parent.parent))

from ibkr_core.config import InvalidConfigError, get_config


def healthcheck(mode: Optional[str] = None) -> bool:
    """Check IBKR connection and server time.

    Args:
        mode: Optional trading mode override ('paper' or 'live').
              If not provided, uses TRADING_MODE from config.
    """

    try:
        from ib_insync import IB
    except ImportError:
        print("ERROR: ib_insync is not installed. Please install it via pip/poetry.")
        return False

    try:
        config = get_config()
    except InvalidConfigError as e:
        print(f"ERROR: Configuration error - {e}")
        return False

    # Override trading mode if specified
    if mode is not None:
        if mode.lower() not in ("paper", "live"):
            print(f"ERROR: Invalid mode '{mode}'. Must be 'paper' or 'live'.")
            return False
        trading_mode = mode.lower()
    else:
        trading_mode = config.trading_mode

    # Select appropriate port and client ID based on mode
    if trading_mode == "live":
        gateway_port = config.live_gateway_port
        client_id = config.live_client_id
    else:
        gateway_port = config.paper_gateway_port
        client_id = config.paper_client_id

    ib = IB()

    try:
        # Attempt connection
        print(
            f"Connecting to IBKR Gateway at {config.ibkr_gateway_host}:{gateway_port} ({trading_mode.upper()} mode)..."
        )
        print(f"Using client ID: {client_id}")

        ib.connect(
            host=config.ibkr_gateway_host,
            port=gateway_port,
            clientId=client_id,
            timeout=10,
        )

        if not ib.isConnected():
            print("ERROR: Failed to connect to IBKR Gateway.")
            return False

        print("[OK] Connected to IBKR Gateway")

        # Query server time
        server_time = ib.reqCurrentTime()
        print(f"[OK] Server time: {server_time}")

        # Get managed accounts
        accounts = ib.managedAccounts()
        if accounts:
            print(f"[OK] Managed accounts: {', '.join(accounts)}")
        else:
            print("[OK] No managed accounts (this is normal for some configurations)")

        # Verify trading mode
        print(f"[OK] Trading mode: {trading_mode.upper()}")
        print(f"[OK] Orders enabled: {config.orders_enabled}")

        return True

    except ConnectionRefusedError:
        print(f"ERROR: Connection refused. Is IBKR Gateway/TWS running on port {gateway_port}?")
        return False
    except TimeoutError:
        print(f"ERROR: Connection timeout. IBKR Gateway/TWS not responding on port {gateway_port}.")
        return False
    except Exception as e:
        print(f"ERROR: {type(e).__name__}: {e}")
        import traceback

        traceback.print_exc()
        return False
    finally:
        if ib.isConnected():
            ib.disconnect()
            print("[OK] Disconnected from IBKR Gateway")


def main() -> int:
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="IBKR Gateway healthcheck")
    parser.add_argument(
        "mode",
        nargs="?",
        choices=["paper", "live"],
        help="Trading mode to test (paper or live). If not specified, uses TRADING_MODE from .env",
    )
    args = parser.parse_args()

    try:
        success = healthcheck(mode=args.mode)
        return 0 if success else 1
    except KeyboardInterrupt:
        print("\nInterrupted by user.")
        return 1
    except Exception as e:
        print(f"FATAL ERROR: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
