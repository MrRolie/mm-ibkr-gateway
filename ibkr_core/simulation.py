"""
Simulated IBKR client for testing without a live connection.

Provides a SimulatedIBKRClient that implements the same interface as IBKRClient
but operates entirely in-memory with simulated responses.

Usage:
    client = SimulatedIBKRClient()
    client.connect()  # Always succeeds
    # Use same API as real client...
"""

import random
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from ibkr_core.config import Config, get_config
from ibkr_core.metrics import record_ibkr_operation, set_connection_status


@dataclass
class SimulatedQuote:
    """Simulated quote data."""

    symbol: str
    bid: float
    ask: float
    last: float
    bid_size: int = 100
    ask_size: int = 100
    last_size: int = 50
    volume: int = 1000000
    timestamp: datetime = field(default_factory=datetime.now)

    @property
    def mid(self) -> float:
        """Mid price."""
        return (self.bid + self.ask) / 2


@dataclass
class SimulatedOrder:
    """Simulated order tracking."""

    order_id: str
    symbol: str
    side: str
    quantity: float
    order_type: str
    limit_price: Optional[float]
    status: str
    account_id: str
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    filled_quantity: float = 0.0
    fill_price: Optional[float] = None
    ibkr_order_id: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "order_id": self.order_id,
            "symbol": self.symbol,
            "side": self.side,
            "quantity": self.quantity,
            "order_type": self.order_type,
            "limit_price": self.limit_price,
            "status": self.status,
            "account_id": self.account_id,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "filled_quantity": self.filled_quantity,
            "fill_price": self.fill_price,
            "ibkr_order_id": self.ibkr_order_id,
        }


class SimulatedIBKRClient:
    """
    Simulated IBKR client for testing without a live connection.

    Implements the same interface as IBKRClient but operates entirely
    in-memory. Useful for:
    - Unit testing without IBKR Gateway
    - Development without market data subscriptions
    - CI/CD pipelines

    Features:
    - Simulated connection (always succeeds)
    - Synthetic quote generation
    - Order lifecycle simulation with state transitions
    - Thread-safe order registry
    """

    # Base prices for common symbols (simulated)
    BASE_PRICES: Dict[str, float] = {
        "AAPL": 250.00,
        "MSFT": 400.00,
        "GOOGL": 175.00,
        "AMZN": 200.00,
        "META": 550.00,
        "NVDA": 140.00,
        "TSLA": 250.00,
        "SPY": 600.00,
        "QQQ": 525.00,
        "IWM": 225.00,
    }

    DEFAULT_PRICE = 100.00

    def __init__(
        self,
        config: Optional[Config] = None,
        mode: str = "simulation",
        client_id: Optional[int] = None,
        account_id: str = "SIM000001",
    ):
        """
        Initialize SimulatedIBKRClient.

        Args:
            config: Configuration object (optional, for compatibility)
            mode: Always 'simulation' for this client
            client_id: Simulated client ID (default: 999)
            account_id: Simulated account ID (default: SIM000001)
        """
        self._config = config or get_config()
        self._mode = "simulation"
        self._client_id = client_id or 999
        self._account_id = account_id
        self._connected = False
        self._connection_time: Optional[datetime] = None

        # Order registry (thread-safe)
        self._orders: Dict[str, SimulatedOrder] = {}
        self._order_lock = threading.Lock()
        self._next_ibkr_order_id = 1000

        # Quote cache for consistency
        self._quote_cache: Dict[str, SimulatedQuote] = {}
        self._quote_lock = threading.Lock()

    @property
    def is_connected(self) -> bool:
        """Check if client is connected."""
        return self._connected

    @property
    def mode(self) -> str:
        """Current trading mode (always 'simulation')."""
        return self._mode

    @property
    def host(self) -> str:
        """Simulated gateway host."""
        return "simulation"

    @property
    def port(self) -> int:
        """Simulated gateway port."""
        return 0

    @property
    def client_id(self) -> int:
        """Client ID."""
        return self._client_id

    @property
    def connection_time(self) -> Optional[datetime]:
        """Time when connection was established."""
        return self._connection_time

    @property
    def managed_accounts(self) -> List[str]:
        """List of managed accounts."""
        if not self.is_connected:
            return []
        return [self._account_id]

    @property
    def ib(self) -> "SimulatedIB":
        """Simulated IB interface for compatibility."""
        return SimulatedIB(self)

    def connect(self, timeout: int = 10, readonly: bool = False) -> None:
        """
        Simulate connection to IBKR.

        Always succeeds after a small delay to simulate network latency.
        """
        if self._connected:
            return

        start_time = time.time()

        # Simulate connection delay
        time.sleep(0.05)

        self._connected = True
        self._connection_time = datetime.now()

        elapsed_seconds = time.time() - start_time
        record_ibkr_operation("connect", "success", elapsed_seconds)
        set_connection_status(self._mode, connected=True)

    def disconnect(self) -> None:
        """Simulate disconnection."""
        if self._connected:
            set_connection_status(self._mode, connected=False)

        self._connected = False
        self._connection_time = None

    def ensure_connected(self, timeout: int = 10) -> None:
        """Ensure connection is active."""
        if not self._connected:
            self.connect(timeout=timeout)

    def get_server_time(self, timeout_s: Optional[float] = None) -> datetime:
        """Get simulated server time."""
        if not self._connected:
            raise RuntimeError("Not connected")
        return datetime.now()

    def get_quote(self, symbol: str) -> SimulatedQuote:
        """
        Get a simulated quote for a symbol.

        Generates consistent synthetic quotes with realistic bid/ask spreads.
        """
        if not self._connected:
            raise RuntimeError("Not connected")

        with self._quote_lock:
            if symbol not in self._quote_cache:
                self._quote_cache[symbol] = self._generate_quote(symbol)
            else:
                # Update with small price movement
                self._quote_cache[symbol] = self._update_quote(
                    self._quote_cache[symbol]
                )
            return self._quote_cache[symbol]

    def _generate_quote(self, symbol: str) -> SimulatedQuote:
        """Generate initial quote for a symbol."""
        base_price = self.BASE_PRICES.get(symbol.upper(), self.DEFAULT_PRICE)

        # Add some randomness
        variation = base_price * random.uniform(-0.02, 0.02)
        mid_price = base_price + variation

        # Typical spread of 0.01-0.05%
        spread = mid_price * random.uniform(0.0001, 0.0005)

        return SimulatedQuote(
            symbol=symbol.upper(),
            bid=round(mid_price - spread / 2, 2),
            ask=round(mid_price + spread / 2, 2),
            last=round(mid_price + random.uniform(-spread, spread), 2),
        )

    def _update_quote(self, quote: SimulatedQuote) -> SimulatedQuote:
        """Update quote with small price movement."""
        # Small random movement (±0.1%)
        movement = quote.mid * random.uniform(-0.001, 0.001)
        new_mid = quote.mid + movement
        spread = quote.ask - quote.bid

        return SimulatedQuote(
            symbol=quote.symbol,
            bid=round(new_mid - spread / 2, 2),
            ask=round(new_mid + spread / 2, 2),
            last=round(new_mid + random.uniform(-spread / 2, spread / 2), 2),
            timestamp=datetime.now(),
        )

    def submit_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        order_type: str,
        limit_price: Optional[float] = None,
        account_id: Optional[str] = None,
    ) -> SimulatedOrder:
        """
        Submit a simulated order.

        Validates the order and simulates state transitions.
        Market orders fill immediately; limit orders check price.
        """
        if not self._connected:
            raise RuntimeError("Not connected")

        # Validate order
        if side.upper() not in ("BUY", "SELL"):
            raise ValueError(f"Invalid side: {side}")
        if quantity <= 0:
            raise ValueError(f"Invalid quantity: {quantity}")
        if order_type.upper() not in ("MKT", "LMT"):
            raise ValueError(f"Invalid order type: {order_type}")
        if order_type.upper() == "LMT" and limit_price is None:
            raise ValueError("Limit price required for LMT orders")

        order_id = str(uuid.uuid4())

        with self._order_lock:
            ibkr_order_id = self._next_ibkr_order_id
            self._next_ibkr_order_id += 1

            order = SimulatedOrder(
                order_id=order_id,
                symbol=symbol.upper(),
                side=side.upper(),
                quantity=quantity,
                order_type=order_type.upper(),
                limit_price=limit_price,
                status="PendingSubmit",
                account_id=account_id or self._account_id,
                ibkr_order_id=ibkr_order_id,
            )

            self._orders[order_id] = order

        # Simulate async state transitions
        self._process_order(order_id)

        return order

    def _process_order(self, order_id: str) -> None:
        """Process order through state machine."""
        with self._order_lock:
            order = self._orders.get(order_id)
            if not order:
                return

            # Transition: PendingSubmit -> Submitted
            order.status = "Submitted"
            order.updated_at = datetime.now()

            # Get current quote
            quote = self.get_quote(order.symbol)

            # Determine if order should fill
            should_fill = False
            fill_price = None

            if order.order_type == "MKT":
                # Market orders always fill immediately
                should_fill = True
                fill_price = quote.ask if order.side == "BUY" else quote.bid
            elif order.order_type == "LMT":
                # Limit orders fill if price is favorable
                if order.side == "BUY" and order.limit_price >= quote.ask:
                    should_fill = True
                    fill_price = min(order.limit_price, quote.ask)
                elif order.side == "SELL" and order.limit_price <= quote.bid:
                    should_fill = True
                    fill_price = max(order.limit_price, quote.bid)

            if should_fill:
                order.status = "Filled"
                order.filled_quantity = order.quantity
                order.fill_price = fill_price
                order.updated_at = datetime.now()

    def cancel_order(self, order_id: str) -> bool:
        """
        Cancel a simulated order.

        Returns True if order was cancelled, False if not found or already filled.
        """
        with self._order_lock:
            order = self._orders.get(order_id)
            if not order:
                return False

            if order.status in ("Filled", "Cancelled"):
                return False

            order.status = "Cancelled"
            order.updated_at = datetime.now()
            return True

    def get_order(self, order_id: str) -> Optional[SimulatedOrder]:
        """Get order by ID."""
        with self._order_lock:
            return self._orders.get(order_id)

    def get_open_orders(self) -> List[SimulatedOrder]:
        """Get all open (non-filled, non-cancelled) orders."""
        with self._order_lock:
            return [
                o
                for o in self._orders.values()
                if o.status not in ("Filled", "Cancelled")
            ]

    def get_all_orders(self) -> List[SimulatedOrder]:
        """Get all orders in the registry."""
        with self._order_lock:
            return list(self._orders.values())

    def clear_orders(self) -> None:
        """Clear order registry (for testing)."""
        with self._order_lock:
            self._orders.clear()

    def __enter__(self) -> "SimulatedIBKRClient":
        """Context manager entry."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit."""
        self.disconnect()

    def __repr__(self) -> str:
        status = "connected" if self._connected else "disconnected"
        return f"SimulatedIBKRClient(account={self._account_id}, {status})"


class SimulatedIB:
    """
    Simulated ib_insync.IB interface for compatibility.

    Provides the minimal interface needed by existing code that
    accesses client.ib directly.
    """

    def __init__(self, client: SimulatedIBKRClient):
        self._client = client

    def isConnected(self) -> bool:
        """Check connection status."""
        return self._client.is_connected

    def managedAccounts(self) -> List[str]:
        """Get managed accounts."""
        return self._client.managed_accounts

    def reqCurrentTime(self) -> datetime:
        """Get current server time."""
        return self._client.get_server_time()

    def disconnect(self) -> None:
        """Disconnect."""
        self._client.disconnect()


# Factory function to get appropriate client
def get_ibkr_client(
    mode: Optional[str] = None,
    client_id: Optional[int] = None,
) -> "IBKRClient | SimulatedIBKRClient":
    """
    Get an IBKR client based on mode.

    Args:
        mode: Trading mode ('paper', 'live', or 'simulation').
              If None, reads from IBKR_MODE env var, defaulting to config.

    Returns:
        IBKRClient for paper/live modes, SimulatedIBKRClient for simulation.
    """
    import os

    from ibkr_core.client import IBKRClient

    if mode is None:
        mode = os.environ.get("IBKR_MODE", "").lower()

    if not mode:
        # Fall back to config trading_mode
        config = get_config()
        mode = config.trading_mode

    if mode == "simulation":
        return SimulatedIBKRClient(client_id=client_id)
    else:
        return IBKRClient(mode=mode, client_id=client_id)
