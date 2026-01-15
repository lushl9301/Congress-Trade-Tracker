"""Data models for the application."""

from datetime import date, datetime
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator


# Enums
class TransactionType(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    OTHER = "OTHER"


class SignalAction(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    WATCH = "WATCH"
    IGNORE = "IGNORE"


class SignalConfidence(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"


class OrderStatus(str, Enum):
    PENDING = "PENDING"
    SUBMITTED = "SUBMITTED"
    FILLED = "FILLED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


class PositionStatus(str, Enum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"


# Pydantic Models
class Disclosure(BaseModel):
    """Congressional trade disclosure."""

    id: UUID = Field(default_factory=uuid4)
    source: str
    politician: str
    ticker: str
    transaction_type: TransactionType
    trade_date: date | None = None
    disclosure_date: date | None = None
    amount_min: float
    amount_max: float
    amount_estimate: float
    delay_days: int | None = None
    raw_data: dict[str, Any]
    created_at: datetime = Field(default_factory=datetime.utcnow)

    @field_validator("amount_estimate", mode="before")
    @classmethod
    def calculate_estimate(cls, v, info):
        """Calculate amount estimate from min/max if not provided."""
        if v is None and info.data.get("amount_min") and info.data.get("amount_max"):
            return (info.data["amount_min"] + info.data["amount_max"]) / 2
        return v

    @field_validator("delay_days", mode="before")
    @classmethod
    def calculate_delay(cls, v, info):
        """Calculate delay from dates if not provided."""
        if v is None:
            trade = info.data.get("trade_date")
            disclosure = info.data.get("disclosure_date")
            if trade and disclosure:
                return (disclosure - trade).days
        return v


class Signal(BaseModel):
    """Trading signal generated from a disclosure."""

    id: UUID = Field(default_factory=uuid4)
    disclosure_id: UUID
    ticker: str
    action: SignalAction
    confidence: SignalConfidence
    score: int = Field(ge=0, le=100)
    reasons: list[str]
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Position(BaseModel):
    """Portfolio position."""

    id: UUID = Field(default_factory=uuid4)
    ticker: str
    quantity: float
    avg_cost: float
    current_price: float | None = None
    unrealized_pnl: float | None = None
    opened_at: datetime = Field(default_factory=datetime.utcnow)
    opened_by_signals: list[UUID] = Field(default_factory=list)
    exit_strategy: dict[str, Any] = Field(default_factory=dict)
    status: PositionStatus = PositionStatus.OPEN

    def calculate_pnl(self) -> float | None:
        """Calculate unrealized P&L."""
        if self.current_price is None:
            return None
        return (self.current_price - self.avg_cost) * self.quantity

    def calculate_return_pct(self) -> float | None:
        """Calculate percentage return."""
        if self.avg_cost == 0:
            return None
        if self.current_price is None:
            return None
        return (self.current_price - self.avg_cost) / self.avg_cost


class Order(BaseModel):
    """Trade order."""

    id: UUID = Field(default_factory=uuid4)
    signal_id: UUID | None = None
    ticker: str
    side: OrderSide
    quantity: float
    order_type: OrderType = OrderType.MARKET
    status: OrderStatus = OrderStatus.PENDING
    broker_order_id: str | None = None
    filled_price: float | None = None
    filled_at: datetime | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class PortfolioSnapshot(BaseModel):
    """Portfolio snapshot for tracking performance."""

    timestamp: datetime = Field(default_factory=datetime.utcnow)
    total_value: float
    cash: float
    positions_value: float
    unrealized_pnl: float
    realized_pnl: float
    num_positions: int
