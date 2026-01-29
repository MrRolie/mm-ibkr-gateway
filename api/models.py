"""
API request and response models.

Wraps ibkr_core models with API-specific additions for request validation
and response formatting.
"""

from typing import List, Optional

from pydantic import BaseModel, Field, field_validator

# Re-export core models for use in responses
from ibkr_core.models import (  # noqa: F401
    AccountPnl,
    AccountSummary,
    Bar,
    CancelResult,
    OrderLeg,
    OrderPreview,
    OrderResult,
    OrderSpec,
    OrderStatus,
    PnlDetail,
    Position,
    Quote,
    SymbolSpec,
)

# =============================================================================
# Health Check
# =============================================================================


class HealthResponse(BaseModel):
    """Health check response."""

    status: str = Field(..., description="Overall status: 'ok' or 'degraded'")
    ibkr_connected: bool = Field(..., description="Whether IBKR gateway is connected")
    server_time: Optional[str] = Field(None, description="IBKR server time if connected")
    trading_mode: str = Field(..., description="Current trading mode (paper/live)")
    orders_enabled: bool = Field(..., description="Whether orders are enabled")
    version: str = Field(default="0.1.0", description="API version")

    class Config:
        json_schema_extra = {
            "example": {
                "status": "ok",
                "ibkr_connected": True,
                "server_time": "2024-01-15T14:30:00Z",
                "trading_mode": "paper",
                "orders_enabled": False,
                "version": "0.1.0",
            }
        }


# =============================================================================
# Market Data Requests
# =============================================================================


class QuoteRequest(BaseModel):
    """Request for a market data quote."""

    symbol: str = Field(..., description="Symbol/ticker, e.g. 'AAPL', 'MES'")
    securityType: str = Field(..., description="Security type: STK, ETF, FUT, OPT, IND")
    exchange: Optional[str] = Field(None, description="Exchange, e.g. 'SMART', 'GLOBEX'")
    currency: Optional[str] = Field(None, description="Currency, e.g. 'USD'")
    expiry: Optional[str] = Field(None, description="Contract expiry for derivatives (YYYY-MM-DD)")

    def to_symbol_spec(self) -> SymbolSpec:
        """Convert to SymbolSpec for ibkr_core."""
        return SymbolSpec(
            symbol=self.symbol,
            securityType=self.securityType,
            exchange=self.exchange,
            currency=self.currency,
            expiry=self.expiry,
        )

    class Config:
        json_schema_extra = {
            "example": {
                "symbol": "AAPL",
                "securityType": "STK",
                "exchange": "SMART",
                "currency": "USD",
            }
        }


class HistoricalBarsRequest(BaseModel):
    """Request for historical bar data."""

    symbol: str = Field(..., description="Symbol/ticker")
    securityType: str = Field(..., description="Security type: STK, ETF, FUT, OPT, IND")
    exchange: Optional[str] = Field(None, description="Exchange")
    currency: Optional[str] = Field(None, description="Currency")
    expiry: Optional[str] = Field(None, description="Contract expiry for derivatives")
    barSize: str = Field(..., description="Bar size: 1m, 5m, 15m, 1h, 1d, etc.")
    duration: str = Field(..., description="Duration: 1d, 5d, 1w, 1mo, 3mo, 1y, etc.")
    whatToShow: str = Field(
        default="TRADES", description="Data type: TRADES, MIDPOINT, BID, ASK, etc."
    )
    rthOnly: bool = Field(default=True, description="Regular trading hours only")

    def to_symbol_spec(self) -> SymbolSpec:
        """Convert to SymbolSpec for ibkr_core."""
        return SymbolSpec(
            symbol=self.symbol,
            securityType=self.securityType,
            exchange=self.exchange,
            currency=self.currency,
            expiry=self.expiry,
        )

    class Config:
        json_schema_extra = {
            "example": {
                "symbol": "AAPL",
                "securityType": "STK",
                "exchange": "SMART",
                "currency": "USD",
                "barSize": "1d",
                "duration": "1mo",
                "whatToShow": "TRADES",
                "rthOnly": True,
            }
        }


class HistoricalBarsResponse(BaseModel):
    """Response containing historical bars."""

    symbol: str = Field(..., description="Symbol requested")
    bars: List[Bar] = Field(..., description="List of OHLCV bars")
    barCount: int = Field(..., description="Number of bars returned")

    class Config:
        json_schema_extra = {"example": {"symbol": "AAPL", "barCount": 20, "bars": []}}


# =============================================================================
# Account Responses
# =============================================================================


class PositionsResponse(BaseModel):
    """Response containing account positions."""

    accountId: str = Field(..., description="Account identifier")
    positions: List[Position] = Field(..., description="List of positions")
    positionCount: int = Field(..., description="Number of positions")

    class Config:
        json_schema_extra = {
            "example": {"accountId": "DU1234567", "positionCount": 3, "positions": []}
        }


# =============================================================================
# Order Request/Response
# =============================================================================


class OrderRequest(BaseModel):
    """Request to place an order.

    This wraps OrderSpec with the same fields for clarity.
    """

    accountId: Optional[str] = Field(None, description="Target account")
    strategyId: Optional[str] = Field(
        None, description="Strategy identifier for virtual subaccount tracking."
    )
    virtualSubaccountId: Optional[str] = Field(
        None, description="Virtual subaccount identifier for allocation tracking."
    )
    instrument: SymbolSpec = Field(..., description="Instrument to trade")
    side: str = Field(..., description="Order side: BUY or SELL")
    quantity: float = Field(..., gt=0, description="Order quantity")
    orderType: str = Field(
        ..., description="Order type: MKT, LMT, STP, STP_LMT, TRAIL, BRACKET, MOC, OPG"
    )
    limitPrice: Optional[float] = Field(None, ge=0, description="Limit price")
    stopPrice: Optional[float] = Field(None, ge=0, description="Stop price")
    tif: str = Field(default="DAY", description="Time-in-force: DAY, GTC, IOC, FOK")
    outsideRth: bool = Field(default=False, description="Allow outside RTH")
    clientOrderId: Optional[str] = Field(None, description="Client order ID")
    transmit: bool = Field(default=True, description="Transmit order immediately")

    # Trailing stop parameters
    trailingAmount: Optional[float] = Field(None, gt=0, description="Trailing amount")
    trailingPercent: Optional[float] = Field(None, gt=0, le=100, description="Trailing percent")
    trailStopPrice: Optional[float] = Field(None, ge=0, description="Initial trail stop")

    # Bracket parameters
    takeProfitPrice: Optional[float] = Field(None, ge=0, description="Take profit price")
    stopLossPrice: Optional[float] = Field(None, ge=0, description="Stop loss price")
    stopLossLimitPrice: Optional[float] = Field(None, ge=0, description="Stop loss limit price")
    bracketTransmit: bool = Field(default=True, description="Transmit bracket legs")

    # OCA parameters
    ocaGroup: Optional[str] = Field(None, description="OCA group name")
    ocaType: Optional[int] = Field(None, ge=1, le=3, description="OCA type")

    @field_validator("side")
    @classmethod
    def validate_side(cls, v: str) -> str:
        """Validate order side."""
        if v not in {"BUY", "SELL"}:
            raise ValueError(f"side must be 'BUY' or 'SELL', got {v}")
        return v

    @field_validator("orderType")
    @classmethod
    def validate_order_type(cls, v: str) -> str:
        """Validate order type."""
        allowed = {"MKT", "LMT", "STP", "STP_LMT", "TRAIL", "TRAIL_LIMIT", "BRACKET", "MOC", "OPG"}
        if v not in allowed:
            raise ValueError(f"orderType must be one of {allowed}, got {v}")
        return v

    def to_order_spec(self) -> OrderSpec:
        """Convert to OrderSpec for ibkr_core."""
        return OrderSpec(
            accountId=self.accountId,
            strategyId=self.strategyId,
            virtualSubaccountId=self.virtualSubaccountId,
            instrument=self.instrument,
            side=self.side,
            quantity=self.quantity,
            orderType=self.orderType,
            limitPrice=self.limitPrice,
            stopPrice=self.stopPrice,
            tif=self.tif,
            outsideRth=self.outsideRth,
            clientOrderId=self.clientOrderId,
            transmit=self.transmit,
            trailingAmount=self.trailingAmount,
            trailingPercent=self.trailingPercent,
            trailStopPrice=self.trailStopPrice,
            takeProfitPrice=self.takeProfitPrice,
            stopLossPrice=self.stopLossPrice,
            stopLossLimitPrice=self.stopLossLimitPrice,
            bracketTransmit=self.bracketTransmit,
            ocaGroup=self.ocaGroup,
            ocaType=self.ocaType,
        )

    class Config:
        json_schema_extra = {
            "example": {
                "instrument": {
                    "symbol": "AAPL",
                    "securityType": "STK",
                    "exchange": "SMART",
                    "currency": "USD",
                },
                "side": "BUY",
                "quantity": 10,
                "orderType": "LMT",
                "limitPrice": 150.00,
                "tif": "DAY",
            }
        }


class OrderPreviewRequest(BaseModel):
    """Request to preview an order.

    Same as OrderRequest, allows previewing before placement.
    """

    accountId: Optional[str] = Field(None, description="Target account")
    strategyId: Optional[str] = Field(
        None, description="Strategy identifier for virtual subaccount tracking."
    )
    virtualSubaccountId: Optional[str] = Field(
        None, description="Virtual subaccount identifier for allocation tracking."
    )
    instrument: SymbolSpec = Field(..., description="Instrument to trade")
    side: str = Field(..., description="Order side: BUY or SELL")
    quantity: float = Field(..., gt=0, description="Order quantity")
    orderType: str = Field(..., description="Order type")
    limitPrice: Optional[float] = Field(None, ge=0, description="Limit price")
    stopPrice: Optional[float] = Field(None, ge=0, description="Stop price")
    tif: str = Field(default="DAY", description="Time-in-force")
    outsideRth: bool = Field(default=False, description="Allow outside RTH")
    clientOrderId: Optional[str] = Field(None, description="Client order ID")
    transmit: bool = Field(default=True, description="Transmit flag")

    # Trailing stop parameters
    trailingAmount: Optional[float] = Field(None, gt=0)
    trailingPercent: Optional[float] = Field(None, gt=0, le=100)
    trailStopPrice: Optional[float] = Field(None, ge=0)

    # Bracket parameters
    takeProfitPrice: Optional[float] = Field(None, ge=0)
    stopLossPrice: Optional[float] = Field(None, ge=0)
    stopLossLimitPrice: Optional[float] = Field(None, ge=0)
    bracketTransmit: bool = Field(default=True)

    # OCA parameters
    ocaGroup: Optional[str] = Field(None)
    ocaType: Optional[int] = Field(None, ge=1, le=3)

    @field_validator("side")
    @classmethod
    def validate_side(cls, v: str) -> str:
        """Validate order side."""
        if v not in {"BUY", "SELL"}:
            raise ValueError(f"side must be 'BUY' or 'SELL', got {v}")
        return v

    @field_validator("orderType")
    @classmethod
    def validate_order_type(cls, v: str) -> str:
        """Validate order type."""
        allowed = {"MKT", "LMT", "STP", "STP_LMT", "TRAIL", "TRAIL_LIMIT", "BRACKET", "MOC", "OPG"}
        if v not in allowed:
            raise ValueError(f"orderType must be one of {allowed}, got {v}")
        return v

    def to_order_spec(self) -> OrderSpec:
        """Convert to OrderSpec for ibkr_core."""
        return OrderSpec(
            accountId=self.accountId,
            strategyId=self.strategyId,
            virtualSubaccountId=self.virtualSubaccountId,
            instrument=self.instrument,
            side=self.side,
            quantity=self.quantity,
            orderType=self.orderType,
            limitPrice=self.limitPrice,
            stopPrice=self.stopPrice,
            tif=self.tif,
            outsideRth=self.outsideRth,
            clientOrderId=self.clientOrderId,
            transmit=self.transmit,
            trailingAmount=self.trailingAmount,
            trailingPercent=self.trailingPercent,
            trailStopPrice=self.trailStopPrice,
            takeProfitPrice=self.takeProfitPrice,
            stopLossPrice=self.stopLossPrice,
            stopLossLimitPrice=self.stopLossLimitPrice,
            bracketTransmit=self.bracketTransmit,
            ocaGroup=self.ocaGroup,
            ocaType=self.ocaType,
        )
