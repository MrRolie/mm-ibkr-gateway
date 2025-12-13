"""
IBKR Core Integration Module
"""

from ibkr_core.config import (
    Config,
    InvalidConfigError,
    TradingDisabledError,
    get_config,
    load_config,
    reset_config,
)
from ibkr_core.client import (
    ConnectionError,
    IBKRClient,
    create_client,
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
