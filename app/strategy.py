"""Signal generation for congressional trades."""
from __future__ import annotations

import hashlib
import logging
from datetime import datetime

from app.db import Database
from app.models import TradeSignal

logger = logging.getLogger(__name__)

MAX_DELAY_DAYS = 14
MIN_AMOUNT_HIGH = 5000
STRATEGY_VERSION = "mvp_v1"


def _hash_signal(event_id: str, strategy_version: str) -> str:
    payload = f"{event_id}|{strategy_version}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _score_buy(delay_days: int, amount_high: float, owner: str) -> tuple[int, list[str]]:
    score = 50
    reasons: list[str] = ["base score"]

    if delay_days <= 2:
        score += 25
        reasons.append("fresh disclosure")
    elif delay_days <= 7:
        score += 15
        reasons.append("recent disclosure")
    elif delay_days <= 14:
        score += 5
        reasons.append("stale disclosure")

    if amount_high >= 250000:
        score += 15
        reasons.append("large amount")
    elif amount_high >= 50000:
        score += 10
        reasons.append("medium amount")
    elif amount_high >= 5000:
        score += 5
        reasons.append("small amount")

    if owner == "member":
        score += 10
        reasons.append("member trade")
    elif owner == "spouse":
        score += 5
        reasons.append("spouse trade")
    elif owner == "dependent":
        score += 2
        reasons.append("dependent trade")

    score = max(0, min(100, score))
    return score, reasons


def generate_signals(db: Database) -> dict[str, int]:
    events = db.fetch_events_without_signals()
    positions = {row["ticker"] for row in db.fetch_positions()}
    signals: list[TradeSignal] = []
    for row in events:
        delay_days = row["delay_days"]
        amount_high = row["amount_high"]
        transaction_type = row["transaction_type"]
        owner = row["owner"]
        ticker = row["ticker"]
        reasons: list[str] = []

        if transaction_type == "SELL":
            if ticker in positions:
                reasons.append("sell disclosure while holding")
                signals.append(
                    TradeSignal(
                        signal_id=_hash_signal(row["event_id"], STRATEGY_VERSION),
                        event_id=row["event_id"],
                        ticker=ticker,
                        action="SELL",
                        strength="STRONG",
                        score=100,
                        reason=reasons,
                        created_at=datetime.utcnow(),
                        strategy_version=STRATEGY_VERSION,
                    )
                )
            else:
                signals.append(
                    TradeSignal(
                        signal_id=_hash_signal(row["event_id"], STRATEGY_VERSION),
                        event_id=row["event_id"],
                        ticker=ticker,
                        action="NONE",
                        strength="IGNORE",
                        score=0,
                        reason=["sell disclosure without position"],
                        created_at=datetime.utcnow(),
                        strategy_version=STRATEGY_VERSION,
                    )
                )
            continue

        if transaction_type != "BUY":
            signals.append(
                TradeSignal(
                    signal_id=_hash_signal(row["event_id"], STRATEGY_VERSION),
                    event_id=row["event_id"],
                    ticker=ticker,
                    action="NONE",
                    strength="IGNORE",
                    score=0,
                    reason=["unsupported transaction type"],
                    created_at=datetime.utcnow(),
                    strategy_version=STRATEGY_VERSION,
                )
            )
            continue

        if delay_days is None or delay_days > MAX_DELAY_DAYS:
            signals.append(
                TradeSignal(
                    signal_id=_hash_signal(row["event_id"], STRATEGY_VERSION),
                    event_id=row["event_id"],
                    ticker=ticker,
                    action="NONE",
                    strength="IGNORE",
                    score=0,
                    reason=["delay too long"],
                    created_at=datetime.utcnow(),
                    strategy_version=STRATEGY_VERSION,
                )
            )
            continue

        if amount_high is None or amount_high < MIN_AMOUNT_HIGH:
            signals.append(
                TradeSignal(
                    signal_id=_hash_signal(row["event_id"], STRATEGY_VERSION),
                    event_id=row["event_id"],
                    ticker=ticker,
                    action="NONE",
                    strength="IGNORE",
                    score=0,
                    reason=["amount below threshold"],
                    created_at=datetime.utcnow(),
                    strategy_version=STRATEGY_VERSION,
                )
            )
            continue

        score, reasons = _score_buy(delay_days, amount_high, owner)
        if score >= 80:
            strength = "STRONG"
        elif score >= 65:
            strength = "NORMAL"
        elif score >= 50:
            strength = "WATCH"
        else:
            strength = "IGNORE"

        action = "BUY" if strength in {"STRONG", "NORMAL", "WATCH"} else "NONE"
        signals.append(
            TradeSignal(
                signal_id=_hash_signal(row["event_id"], STRATEGY_VERSION),
                event_id=row["event_id"],
                ticker=ticker,
                action=action,
                strength=strength,
                score=score,
                reason=reasons,
                created_at=datetime.utcnow(),
                strategy_version=STRATEGY_VERSION,
            )
        )

    inserted = db.insert_signals(signals)
    logger.info("signals generated", extra={"events": len(events), "inserted": inserted})
    return {"events": len(events), "inserted": inserted}
