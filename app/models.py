"""Data models for Congress Trade Tracker."""
from __future__ import annotations

import hashlib
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

OwnerType = Literal["member", "spouse", "dependent", "unknown"]
AssetType = Literal["stock", "etf", "unknown"]
TransactionType = Literal["BUY", "SELL", "OTHER"]
SignalAction = Literal["BUY", "SELL", "NONE"]
SignalStrength = Literal["STRONG", "NORMAL", "WATCH", "IGNORE"]


def _normalize_amount(value: float | int | None) -> float | None:
    if value is None:
        return None
    return float(round(value))


def compute_event_id(
    *,
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
    parts = [
        source,
        ticker.upper() if ticker else "",
        transaction_type or "",
        trade_date.isoformat() if trade_date else "",
        disclosure_date.isoformat() if disclosure_date else "",
        f"{_normalize_amount(amount_low) or ''}",
        f"{_normalize_amount(amount_high) or ''}",
        member_name or "",
        owner or "",
    ]
    payload = "|".join(parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class CongressTradeEvent(BaseModel):
    event_id: str
    source: Literal["finnhub"]
    member_name: str | None
    member_id: str | None
    owner: OwnerType
    ticker: str
    asset_type: AssetType
    transaction_type: TransactionType
    trade_date: date | None
    disclosure_date: date | None
    amount_low: float | None
    amount_high: float | None
    currency: str | None
    raw: dict
    delay_days: int | None = None
    amount_mid: float | None = None

    @classmethod
    def from_finnhub(cls, record: dict) -> "CongressTradeEvent":
        trade_date = _parse_date(record.get("transactionDate"))
        disclosure_date = _parse_date(record.get("reportDate"))
        amount_low, amount_high = _parse_amount_range(record.get("amount"))
        owner = _normalize_owner(record.get("owner"))
        ticker = (record.get("symbol") or "").upper()
        transaction_type = _normalize_transaction(record.get("transactionType"))
        asset_type = _infer_asset_type(record.get("assetType"))
        event_id = compute_event_id(
            source="finnhub",
            ticker=ticker,
            transaction_type=transaction_type,
            trade_date=trade_date,
            disclosure_date=disclosure_date,
            amount_low=amount_low,
            amount_high=amount_high,
            member_name=record.get("name"),
            owner=owner,
        )
        delay_days = None
        if trade_date and disclosure_date:
            delay_days = (disclosure_date - trade_date).days
        amount_mid = None
        if amount_low is not None and amount_high is not None:
            amount_mid = (amount_low + amount_high) / 2
        return cls(
            event_id=event_id,
            source="finnhub",
            member_name=record.get("name"),
            member_id=record.get("memberId"),
            owner=owner,
            ticker=ticker,
            asset_type=asset_type,
            transaction_type=transaction_type,
            trade_date=trade_date,
            disclosure_date=disclosure_date,
            amount_low=amount_low,
            amount_high=amount_high,
            currency=record.get("currency"),
            raw=record,
            delay_days=delay_days,
            amount_mid=amount_mid,
        )


class TradeSignal(BaseModel):
    signal_id: str
    event_id: str
    ticker: str
    action: SignalAction
    strength: SignalStrength
    score: int
    reason: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    strategy_version: str


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def _parse_amount_range(value: str | None) -> tuple[float | None, float | None]:
    if not value:
        return None, None
    cleaned = value.replace("$", "").replace(",", "").strip()
    if "-" in cleaned:
        low, high = cleaned.split("-", maxsplit=1)
        return _to_float(low), _to_float(high)
    return _to_float(cleaned), _to_float(cleaned)


def _to_float(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _normalize_owner(value: str | None) -> OwnerType:
    if not value:
        return "unknown"
    value = value.strip().lower()
    if "spouse" in value:
        return "spouse"
    if "dependent" in value:
        return "dependent"
    if "self" in value or "member" in value:
        return "member"
    return "unknown"


def _normalize_transaction(value: str | None) -> TransactionType:
    if not value:
        return "OTHER"
    value = value.strip().upper()
    if value in {"PURCHASE", "BUY"}:
        return "BUY"
    if value in {"SALE", "SELL"}:
        return "SELL"
    return "OTHER"


def _infer_asset_type(value: str | None) -> AssetType:
    if not value:
        return "unknown"
    value = value.strip().lower()
    if "etf" in value:
        return "etf"
    if "stock" in value:
        return "stock"
    return "unknown"
