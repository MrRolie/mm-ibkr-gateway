"""
IBKR Gateway Demo - 5 Minute Showcase

Demonstrates the system's capabilities in under 5 minutes:
1. Market Data: Fetch quote for AAPL and historical bars for SPY
2. Account Status: Show account summary and positions

Usage:
    python -m ibkr_core.demo
"""

import sys
from datetime import datetime, timedelta
from typing import Optional

from ibkr_core.client import IBKRClient, create_client, ConnectionError
from ibkr_core.config import get_config, InvalidConfigError
from ibkr_core.models import SymbolSpec, BarSize, Duration
from ibkr_core.market_data import (
    get_quote,
    get_historical_bars,
    MarketDataError,
    MarketDataPermissionError,
)
from ibkr_core.account import get_account_summary, get_positions, AccountError


# ANSI color codes for terminal output
class Colors:
    HEADER = "\033[95m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    BOLD = "\033[1m"
    UNDERLINE = "\033[4m"
    END = "\033[0m"


def print_box(title: str, width: int = 70) -> None:
    """Print a formatted box header."""
    print()
    print("=" * width)
    print(f"{Colors.BOLD}{Colors.CYAN}{title.center(width)}{Colors.END}")
    print("=" * width)
    print()


def print_section(title: str) -> None:
    """Print a section header."""
    print(f"\n{Colors.BOLD}{Colors.BLUE}▶ {title}{Colors.END}")
    print("-" * 70)


def print_success(message: str) -> None:
    """Print a success message."""
    print(f"{Colors.GREEN}✓ {message}{Colors.END}")


def print_error(message: str) -> None:
    """Print an error message."""
    print(f"{Colors.RED}✗ {message}{Colors.END}")


def print_warning(message: str) -> None:
    """Print a warning message."""
    print(f"{Colors.YELLOW}⚠ {message}{Colors.END}")


def print_info(label: str, value: str) -> None:
    """Print labeled information."""
    print(f"  {Colors.BOLD}{label}:{Colors.END} {value}")


def validate_paper_mode() -> bool:
    """
    Ensure demo is running in paper trading mode.

    Returns:
        True if in paper mode, False otherwise
    """
    try:
        config = get_config()
        if config.trading_mode != "paper":
            print_error(f"Demo requires TRADING_MODE=paper. Current mode: {config.trading_mode}")
            print_info("Solution", "Set TRADING_MODE=paper in your .env file")
            return False
        return True
    except InvalidConfigError as e:
        print_error(f"Configuration error: {e}")
        return False


def check_gateway_connection(client: Optional[IBKRClient] = None) -> bool:
    """
    Test connection to IBKR Gateway.

    Args:
        client: Optional existing client instance

    Returns:
        True if connection successful, False otherwise
    """
    print_section("Checking IBKR Gateway Connection")

    try:
        # Create client if not provided
        if client is None:
            config = get_config()
            print_info("Mode", f"Paper Trading (port {config.paper_gateway_port})")
            client = create_client(mode="paper")

        # Connection test is implicit in create_client
        server_time = client.ib.reqCurrentTime()
        print_success("Connected to IBKR Gateway")
        print_info("Server Time", str(datetime.fromtimestamp(server_time)))

        # Get managed accounts
        accounts = client.ib.managedAccounts()
        if accounts:
            print_info("Managed Accounts", ", ".join(accounts))

        return True

    except ConnectionError as e:
        print_error("Failed to connect to IBKR Gateway")
        print()
        print_warning("Please ensure IBKR Gateway or TWS is running in paper mode")
        print_info("Default Port", "4002 for paper trading")
        print_info("Error Details", str(e))
        print()
        print("Troubleshooting steps:")
        print("  1. Start IBKR Gateway or TWS")
        print("  2. Enable API connections in settings")
        print("  3. Verify port 4002 is configured for paper trading")
        print("  4. Check IBKR_GATEWAY_HOST and PAPER_GATEWAY_PORT in .env")
        return False

    except Exception as e:
        print_error(f"Unexpected error: {e}")
        return False


def demo_market_data(client: IBKRClient) -> bool:
    """
    Demonstrate market data fetching.

    Args:
        client: Connected IBKR client instance

    Returns:
        True if successful, False otherwise
    """
    print_box("MARKET DATA DEMO")

    # Demo 1: Get quote for AAPL
    print_section("1. Real-Time Quote: AAPL (Stock)")

    try:
        aapl_spec = SymbolSpec(
            symbol="AAPL",
            securityType="STK",
            exchange="SMART",
            currency="USD"
        )

        print_info("Fetching", "AAPL real-time quote...")
        quote = get_quote(aapl_spec, client)

        print_success("Quote retrieved successfully")
        print()
        print(f"  {Colors.BOLD}Symbol:{Colors.END} {quote.symbol} (Contract ID: {quote.conId})")
        print(f"  {Colors.BOLD}Last Price:{Colors.END} ${quote.last:.2f}")
        print(f"  {Colors.BOLD}Bid/Ask:{Colors.END} ${quote.bid:.2f} / ${quote.ask:.2f}")
        print(f"  {Colors.BOLD}Sizes:{Colors.END} {quote.bidSize} / {quote.askSize}")
        print(f"  {Colors.BOLD}Volume:{Colors.END} {quote.volume:,}")
        print(f"  {Colors.BOLD}Timestamp:{Colors.END} {quote.timestamp}")

    except MarketDataPermissionError as e:
        print_error(f"Market data permission error: {e}")
        print_warning("You may need to subscribe to market data for US stocks")
        print_info("Note", "Paper trading accounts have free delayed data")
        return False

    except MarketDataError as e:
        print_error(f"Market data error: {e}")
        return False

    except Exception as e:
        print_error(f"Unexpected error: {e}")
        return False

    # Demo 2: Get historical bars for SPY
    print_section("2. Historical Bars: SPY (ETF) - Last 5 Days")

    try:
        spy_spec = SymbolSpec(
            symbol="SPY",
            securityType="ETF",
            exchange="SMART",
            currency="USD"
        )

        print_info("Fetching", "SPY historical bars (1-hour bars, 5 days)...")
        bars = get_historical_bars(
            spy_spec,
            client,
            bar_size=BarSize.HOUR_1,
            duration=Duration.DAYS_5
        )

        print_success(f"Retrieved {len(bars)} bars")
        print()
        print(f"  {Colors.BOLD}Latest Bars:{Colors.END}")
        print()

        # Show last 5 bars
        for bar in bars[-5:]:
            print(f"    {bar.timestamp.strftime('%Y-%m-%d %H:%M')} | "
                  f"O: ${bar.open:7.2f} | H: ${bar.high:7.2f} | "
                  f"L: ${bar.low:7.2f} | C: ${bar.close:7.2f} | "
                  f"V: {bar.volume:>10,}")

    except MarketDataError as e:
        print_error(f"Market data error: {e}")
        return False

    except Exception as e:
        print_error(f"Unexpected error: {e}")
        return False

    return True


def demo_account_status(client: IBKRClient) -> bool:
    """
    Demonstrate account status queries.

    Args:
        client: Connected IBKR client instance

    Returns:
        True if successful, False otherwise
    """
    print_box("ACCOUNT STATUS DEMO")

    # Demo 1: Get account summary
    print_section("1. Account Summary")

    try:
        print_info("Fetching", "Account summary...")
        summary = get_account_summary(client)

        print_success("Account summary retrieved")
        print()
        print(f"  {Colors.BOLD}Account ID:{Colors.END} {summary.accountId}")
        print(f"  {Colors.BOLD}Currency:{Colors.END} {summary.currency}")
        print(f"  {Colors.BOLD}Net Liquidation:{Colors.END} ${summary.netLiquidation:,.2f}")
        print(f"  {Colors.BOLD}Total Cash:{Colors.END} ${summary.totalCash:,.2f}")
        print(f"  {Colors.BOLD}Buying Power:{Colors.END} ${summary.buyingPower:,.2f}")
        print(f"  {Colors.BOLD}Gross Position Value:{Colors.END} ${summary.grossPositionValue:,.2f}")

        if summary.unrealizedPnL:
            pnl_color = Colors.GREEN if summary.unrealizedPnL >= 0 else Colors.RED
            print(f"  {Colors.BOLD}Unrealized P&L:{Colors.END} {pnl_color}${summary.unrealizedPnL:,.2f}{Colors.END}")

        if summary.realizedPnL:
            pnl_color = Colors.GREEN if summary.realizedPnL >= 0 else Colors.RED
            print(f"  {Colors.BOLD}Realized P&L:{Colors.END} {pnl_color}${summary.realizedPnL:,.2f}{Colors.END}")

    except AccountError as e:
        print_error(f"Account error: {e}")
        return False

    except Exception as e:
        print_error(f"Unexpected error: {e}")
        return False

    # Demo 2: Get positions
    print_section("2. Current Positions")

    try:
        print_info("Fetching", "Current positions...")
        positions = get_positions(client)

        if not positions:
            print_warning("No open positions")
            print()
            print(f"  {Colors.BOLD}Note:{Colors.END} To see positions, place some trades in your paper account first.")
            print(f"  {Colors.BOLD}Tip:{Colors.END} You can use the notebooks in the 'notebooks/' directory to place test trades.")
        else:
            print_success(f"Found {len(positions)} position(s)")
            print()

            for pos in positions:
                pnl_color = Colors.GREEN if pos.unrealizedPnL >= 0 else Colors.RED
                print(f"  {Colors.BOLD}{pos.symbol}{Colors.END} ({pos.securityType})")
                print(f"    Position: {pos.position:,.2f} @ ${pos.averageCost:.2f}")
                print(f"    Market Value: ${pos.marketValue:,.2f}")
                print(f"    Unrealized P&L: {pnl_color}${pos.unrealizedPnL:,.2f}{Colors.END}")
                print()

    except AccountError as e:
        print_error(f"Account error: {e}")
        return False

    except Exception as e:
        print_error(f"Unexpected error: {e}")
        return False

    return True


def print_summary() -> None:
    """Print demo summary and next steps."""
    print_box("DEMO COMPLETE")

    print(f"{Colors.GREEN}✓ Successfully demonstrated IBKR Gateway capabilities!{Colors.END}")
    print()
    print(f"{Colors.BOLD}What you just saw:{Colors.END}")
    print("  • Real-time market data (quotes for AAPL)")
    print("  • Historical data (5 days of SPY bars)")
    print("  • Account summary (balance, buying power, P&L)")
    print("  • Current positions")
    print()
    print(f"{Colors.BOLD}Next Steps:{Colors.END}")
    print()
    print(f"  {Colors.CYAN}1. Explore the Notebooks{Colors.END}")
    print("     cd notebooks/")
    print("     jupyter notebook")
    print()
    print(f"  {Colors.CYAN}2. Try the REST API{Colors.END}")
    print("     python -m api.server")
    print("     curl http://localhost:8000/health")
    print()
    print(f"  {Colors.CYAN}3. Use with Claude Desktop (MCP){Colors.END}")
    print("     Add to claude_desktop_config.json")
    print("     Ask Claude to fetch quotes and manage orders")
    print()
    print(f"  {Colors.CYAN}4. Read the Documentation{Colors.END}")
    print("     • README.md - Complete guide")
    print("     • api/API.md - REST API reference")
    print("     • .context/SAFETY_CHECKLIST.md - Live trading safety")
    print()
    print(f"{Colors.YELLOW}⚠  Remember: This demo uses PAPER TRADING mode (simulated){Colors.END}")
    print(f"   For live trading, see .context/SAFETY_CHECKLIST.md")
    print()


def main() -> int:
    """
    Run the demo.

    Returns:
        Exit code (0 for success, 1 for error)
    """
    print_box("IBKR GATEWAY DEMO - 5 MINUTE SHOWCASE", width=70)

    print(f"{Colors.BOLD}This demo will showcase:{Colors.END}")
    print("  • Connection to IBKR Gateway")
    print("  • Real-time and historical market data")
    print("  • Account summary and positions")
    print()
    print(f"{Colors.YELLOW}Mode: Paper Trading (Simulated){Colors.END}")
    print()

    # Step 1: Validate paper mode
    if not validate_paper_mode():
        return 1

    # Step 2: Connect to Gateway
    client = None
    try:
        if not check_gateway_connection():
            return 1

        # Create client for demos
        client = create_client(mode="paper")

        # Step 3: Demo market data
        if not demo_market_data(client):
            print_warning("Market data demo completed with errors")
            # Continue anyway to show account status

        # Step 4: Demo account status
        if not demo_account_status(client):
            print_warning("Account status demo completed with errors")

        # Step 5: Print summary
        print_summary()

        return 0

    except KeyboardInterrupt:
        print()
        print_warning("Demo interrupted by user")
        return 1

    except Exception as e:
        print()
        print_error(f"Demo failed with unexpected error: {e}")
        return 1

    finally:
        # Clean up
        if client:
            try:
                client.disconnect()
            except:
                pass


if __name__ == "__main__":
    sys.exit(main())
