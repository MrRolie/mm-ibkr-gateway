"""
IBKR Core Integration Module
"""

from ibkr_core.client import ConnectionError, IBKRClient, create_client
from ibkr_core.config import (
    Config,
    InvalidConfigError,
    TradingDisabledError,
    get_config,
    load_config,
    reset_config,
)
from ibkr_core.contracts import (
    AmbiguousContractError,
    ContractCache,
    ContractNotFoundError,
    ContractResolutionError,
    get_contract_cache,
    get_front_month_expiry,
    resolve_contract,
    resolve_contracts,
)
from ibkr_core.market_data import (
    MarketDataError,
    MarketDataPermissionError,
    MarketDataTimeoutError,
    NoMarketDataError,
    PacingViolationError,
    QuoteMode,
    StreamingQuote,
    get_historical_bars,
    get_quote,
    get_quote_with_mode,
    get_quotes,
    get_streaming_quote,
    normalize_bar_size,
    normalize_duration,
    normalize_what_to_show,
)
from ibkr_core.models import (
    AccountPnl,
    AccountSummary,
    Bar,
    CancelResult,
    OrderPreview,
    OrderResult,
    OrderSpec,
    OrderStatus,
    PnlDetail,
    Position,
    Quote,
    SymbolSpec,
)

__all__ = [
    # Config
    "Config",
    "InvalidConfigError",
    "TradingDisabledError",
    "get_config",
    "load_config",
    "reset_config",
    # Client
    "IBKRClient",
    "ConnectionError",
    "create_client",
    # Contracts
    "ContractCache",
    "ContractResolutionError",
    "ContractNotFoundError",
    "AmbiguousContractError",
    "get_contract_cache",
    "resolve_contract",
    "resolve_contracts",
    "get_front_month_expiry",
    # Market Data
    "MarketDataError",
    "MarketDataPermissionError",
    "MarketDataTimeoutError",
    "NoMarketDataError",
    "PacingViolationError",
    "QuoteMode",
    "StreamingQuote",
    "get_quote",
    "get_quote_with_mode",
    "get_quotes",
    "get_streaming_quote",
    "get_historical_bars",
    "normalize_bar_size",
    "normalize_duration",
    "normalize_what_to_show",
    # Models
    "SymbolSpec",
    "Quote",
    "Bar",
    "AccountSummary",
    "Position",
    "PnlDetail",
    "AccountPnl",
    "OrderSpec",
    "OrderPreview",
    "OrderStatus",
    "OrderResult",
    "CancelResult",
]
