"""
Data models for Congress Trade Tracker.
All models use Pydantic for validation and serialization.
"""

import hashlib
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, computed_field


class CongressTradeEvent(BaseModel):
    """
    Canonical normalized congressional trading event.
    Source data is normalized into this schema for consistent processing.
    """

    event_id: str = Field(..., description="Stable hash for deduplication")
    source: str = Field(
        ...,
        description="Data source (house_stock_watcher, financial_modeling_prep, finnhub)"
    )

    # Member information
    member_name: str | None = Field(None, description="Congress member name")
    member_id: str | None = Field(None, description="Member identifier if available")
    owner: Literal["member", "spouse", "dependent", "unknown"] = Field(
        default="unknown", description="Who made the trade"
    )

    # Trade details
    ticker: str = Field(..., description="Stock ticker symbol (e.g., HAL)")
    asset_type: Literal["stock", "etf", "unknown"] = Field(
        default="unknown", description="Asset type"
    )
    transaction_type: Literal["BUY", "SELL", "OTHER"] = Field(
        ..., description="Transaction type"
    )

    # Dates
    trade_date: date | None = Field(None, description="Date trade was executed")
    disclosure_date: date | None = Field(None, description="Date trade was disclosed")

    # Amount
    amount_low: float | None = Field(None, description="Lower bound of trade amount")
    amount_high: float | None = Field(None, description="Upper bound of trade amount")
    currency: str | None = Field(default="USD", description="Currency")

    # Raw data
    raw: dict = Field(default_factory=dict, description="Full raw API response")

    # Verification (multi-source cross-verification)
    verified: bool = Field(
        default=False, description="Whether trade was verified from multiple sources"
    )
    verification_sources: list[str] = Field(
        default_factory=list,
        description="List of source names that reported this trade"
    )
    verification_status: str = Field(
        default="unverified",
        description="Verification status: verified, unverified, single_source"
    )
    verification_discrepancies: dict | None = Field(
        None, description="Any discrepancies found during cross-verification"
    )

    # Metadata
    created_at: datetime = Field(
        default_factory=datetime.utcnow, description="When record was created"
    )

    @computed_field  # type: ignore[misc]
    @property
    def delay_days(self) -> int | None:
        """Calculate days between trade and disclosure."""
        if self.trade_date and self.disclosure_date:
            return (self.disclosure_date - self.trade_date).days
        return None

    @computed_field  # type: ignore[misc]
    @property
    def amount_mid(self) -> float | None:
        """Calculate midpoint of amount range."""
        if self.amount_low is not None and self.amount_high is not None:
            return (self.amount_low + self.amount_high) / 2
        return None

    @staticmethod
    def generate_event_id(
        source: str,
        ticker: str,
        transaction_type: str,
        trade_date: date | None,
        disclosure_date: date | None,
        amount_low: float | None,
        amount_high: float | None,
        member_name: str | None,
        owner: str,
    ) -> str:
        """
        Generate stable event_id hash for deduplication.

        Hash is based on: source|ticker|transaction_type|trade_date|disclosure_date|
                         amount_low|amount_high|member_name|owner
        """
        # Normalize inputs
        ticker_norm = ticker.upper() if ticker else ""
        trade_date_str = trade_date.isoformat() if trade_date else ""
        disclosure_date_str = disclosure_date.isoformat() if disclosure_date else ""
        amount_low_str = str(int(amount_low)) if amount_low is not None else ""
        amount_high_str = str(int(amount_high)) if amount_high is not None else ""
        member_name_norm = member_name.upper() if member_name else ""
        owner_norm = owner.upper() if owner else ""
        transaction_type_norm = transaction_type.upper() if transaction_type else ""
        source_norm = source.lower()

        # Create canonical string
        canonical = "|".join(
            [
                source_norm,
                ticker_norm,
                transaction_type_norm,
                trade_date_str,
                disclosure_date_str,
                amount_low_str,
                amount_high_str,
                member_name_norm,
                owner_norm,
            ]
        )

        # Generate SHA256 hash
        return hashlib.sha256(canonical.encode()).hexdigest()

    class Config:
        """Pydantic config."""

        json_encoders = {
            datetime: lambda v: v.isoformat(),
            date: lambda v: v.isoformat(),
        }


class TradeSignal(BaseModel):
    """
    Trading signal generated from a congressional trade event.
    Contains action, strength, and reasoning.
    """

    signal_id: str = Field(..., description="Hash of event_id + strategy version")
    event_id: str = Field(..., description="Source event ID")
    ticker: str = Field(..., description="Stock ticker")

    action: Literal["BUY", "SELL", "NONE"] = Field(..., description="Trading action")
    strength: Literal["STRONG", "NORMAL", "WATCH", "IGNORE"] = Field(
        ..., description="Signal strength"
    )
    score: int = Field(..., ge=0, le=100, description="Numeric score (0-100)")
    reason: list[str] = Field(
        default_factory=list, description="Human-readable reasons"
    )

    strategy_version: str = Field(
        ..., description="Strategy version that generated this signal"
    )
    created_at: datetime = Field(
        default_factory=datetime.utcnow, description="Signal creation time"
    )

    @staticmethod
    def generate_signal_id(event_id: str, strategy_version: str) -> str:
        """Generate signal ID from event ID and strategy version."""
        canonical = f"{event_id}|{strategy_version}"
        return hashlib.sha256(canonical.encode()).hexdigest()

    class Config:
        """Pydantic config."""

        json_encoders = {
            datetime: lambda v: v.isoformat(),
        }


class Position(BaseModel):
    """
    Current portfolio position.
    Tracks open positions with entry and exit rules.
    """

    ticker: str = Field(..., description="Stock ticker")
    qty: float = Field(..., description="Current quantity held")
    avg_cost: float = Field(..., description="Average cost basis per share")

    opened_at: datetime = Field(..., description="When position was opened")
    last_updated_at: datetime = Field(
        default_factory=datetime.utcnow, description="Last update time"
    )

    # Exit rules
    exit_rule: str = Field(default="HOLD_30D", description="Exit rule type")
    max_hold_days: int = Field(default=30, description="Maximum holding period")
    stop_loss_pct: float = Field(default=-0.08, description="Stop loss percentage")
    take_profit_pct: float = Field(default=0.20, description="Take profit percentage")

    @computed_field  # type: ignore[misc]
    @property
    def notional_value(self) -> float:
        """Calculate notional value at average cost."""
        return self.qty * self.avg_cost

    @computed_field  # type: ignore[misc]
    @property
    def holding_days(self) -> int:
        """Calculate number of days position has been held."""
        return (datetime.utcnow() - self.opened_at).days

    def should_exit_time(self) -> bool:
        """Check if position should exit based on time rule."""
        return self.holding_days >= self.max_hold_days

    def should_exit_price(self, current_price: float) -> tuple[bool, str | None]:
        """
        Check if position should exit based on price rules.

        Returns:
            (should_exit, reason)
        """
        pnl_pct = (current_price - self.avg_cost) / self.avg_cost

        if pnl_pct <= self.stop_loss_pct:
            return True, f"STOP_LOSS: {pnl_pct:.2%}"

        if pnl_pct >= self.take_profit_pct:
            return True, f"TAKE_PROFIT: {pnl_pct:.2%}"

        return False, None

    class Config:
        """Pydantic config."""

        json_encoders = {
            datetime: lambda v: v.isoformat(),
        }


class Order(BaseModel):
    """
    Order tracking record.
    Stores order requests, responses, and status.
    """

    order_id: str = Field(..., description="Local order ID")
    ibkr_order_id: int | None = Field(None, description="IBKR order ID")
    ibkr_perm_id: int | None = Field(None, description="IBKR permanent ID")

    ticker: str = Field(..., description="Stock ticker")
    side: Literal["BUY", "SELL"] = Field(..., description="Order side")
    qty: float = Field(..., description="Order quantity")
    order_type: str = Field(default="MKT", description="Order type (MKT, LMT, etc.)")
    limit_price: float | None = Field(None, description="Limit price if applicable")
    tif: str = Field(default="DAY", description="Time in force")

    status: str = Field(default="PENDING", description="Order status")
    request_payload: dict = Field(
        default_factory=dict, description="Order request details"
    )
    response_payload: dict = Field(
        default_factory=dict, description="Order response details"
    )

    signal_id: str | None = Field(None, description="Source signal ID")
    created_at: datetime = Field(
        default_factory=datetime.utcnow, description="Order creation time"
    )
    updated_at: datetime = Field(
        default_factory=datetime.utcnow, description="Last update time"
    )

    class Config:
        """Pydantic config."""

        json_encoders = {
            datetime: lambda v: v.isoformat(),
        }


class Fill(BaseModel):
    """
    Order fill record.
    Tracks execution details including price and commissions.
    """

    fill_id: str = Field(..., description="Fill ID")
    order_id: str = Field(..., description="Local order ID")
    ibkr_exec_id: str | None = Field(None, description="IBKR execution ID")

    ticker: str = Field(..., description="Stock ticker")
    side: Literal["BUY", "SELL"] = Field(..., description="Fill side")
    qty: float = Field(..., description="Filled quantity")
    price: float = Field(..., description="Fill price")
    commission: float = Field(default=0.0, description="Commission paid")

    filled_at: datetime = Field(
        default_factory=datetime.utcnow, description="Fill timestamp"
    )

    class Config:
        """Pydantic config."""

        json_encoders = {
            datetime: lambda v: v.isoformat(),
        }


class PnLSnapshot(BaseModel):
    """
    Point-in-time PnL snapshot.
    Used for performance tracking and reporting.
    """

    snapshot_id: str = Field(..., description="Snapshot ID")
    snapshot_at: datetime = Field(
        default_factory=datetime.utcnow, description="Snapshot timestamp"
    )

    total_equity: float = Field(..., description="Total equity value")
    cash: float = Field(..., description="Cash balance")
    positions_value: float = Field(..., description="Total value of positions")
    realized_pnl: float = Field(default=0.0, description="Realized P&L")
    unrealized_pnl: float = Field(default=0.0, description="Unrealized P&L")

    num_positions: int = Field(default=0, description="Number of open positions")
    positions_detail: list[dict] = Field(
        default_factory=list, description="Position details"
    )

    class Config:
        """Pydantic config."""

        json_encoders = {
            datetime: lambda v: v.isoformat(),
        }
