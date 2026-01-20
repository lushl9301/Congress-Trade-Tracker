"""
Trading strategy module for Congress Trade Tracker.
Implements MVP scoring rules and signal generation.
"""

from typing import Any

from app.config import config
from app.db import db
from app.logging import get_logger
from app.models import CongressTradeEvent, TradeSignal
from app.rejection_stats import get_rejection_stats

logger = get_logger(__name__)


class CongressTradeStrategy:
    """
    Strategy for generating trading signals from congressional trade events.

    Implements deterministic scoring based on:
    - Disclosure delay (freshness)
    - Trade amount
    - Owner type (member vs spouse vs dependent)
    - Clustering (multiple buys of same ticker)
    """

    def __init__(self, strategy_version: str | None = None):
        """
        Initialize strategy.

        Args:
            strategy_version: Strategy version string (defaults to config)
        """
        self.strategy_version = strategy_version or config.STRATEGY_VERSION
        self.max_delay_days = config.MAX_DELAY_DAYS
        self.min_amount_high = config.MIN_AMOUNT_HIGH

    def generate_signal(self, event: CongressTradeEvent) -> TradeSignal:
        """
        Generate a trading signal from a congressional trade event.

        Args:
            event: Normalized congressional trade event

        Returns:
            TradeSignal with action, strength, score, and reasoning
        """
        reasons: list[str] = []
        score = 50  # Base score

        # === Filter: Basic validation ===
        if not event.ticker:
            return self._create_ignore_signal(event, ["No ticker symbol"])

        # === Filter: Delay days ===
        if event.delay_days is None:
            return self._create_ignore_signal(
                event, ["Cannot compute delay (missing trade_date or disclosure_date)"]
            )

        if event.delay_days > self.max_delay_days:
            return self._create_ignore_signal(
                event,
                [
                    f"Delay too long: {event.delay_days} days (max {self.max_delay_days})"
                ],
            )

        # === Filter: Minimum amount ===
        if event.amount_high is None or event.amount_high < self.min_amount_high:
            amount_str = (
                f"${event.amount_high:,.0f}" if event.amount_high else "unknown"
            )
            return self._create_ignore_signal(
                event,
                [f"Amount too small: {amount_str} (min ${self.min_amount_high:,.0f})"],
            )

        # === Scoring: Freshness ===
        if event.delay_days <= 2:
            score += 25
            reasons.append(f"Very fresh disclosure ({event.delay_days} days)")
        elif event.delay_days <= 7:
            score += 15
            reasons.append(f"Fresh disclosure ({event.delay_days} days)")
        elif event.delay_days <= 14:
            score += 5
            reasons.append(f"Recent disclosure ({event.delay_days} days)")
        elif event.delay_days <= 21:
            score += 2  # Lower score for older disclosures (handles holiday delays)
            reasons.append(f"Delayed disclosure ({event.delay_days} days)")

        # === Scoring: Amount ===
        if event.amount_high >= 250000:
            score += 15
            reasons.append(f"Large trade (${event.amount_high:,.0f})")
        elif event.amount_high >= 50000:
            score += 10
            reasons.append(f"Significant trade (${event.amount_high:,.0f})")
        elif event.amount_high >= 5000:
            score += 5
            reasons.append(f"Moderate trade (${event.amount_high:,.0f})")

        # === Scoring: Owner ===
        if event.owner == "member":
            score += 10
            reasons.append("Direct member trade")
        elif event.owner == "spouse":
            score += 5
            reasons.append("Spouse trade")
        elif event.owner == "dependent":
            score += 2
            reasons.append("Dependent trade")

        # === Scoring: Clustering (multiple buys of same ticker) ===
        recent_events = db.get_recent_events_by_ticker(event.ticker, days=7)
        buy_count = sum(
            1
            for e in recent_events
            if e.transaction_type == "BUY" and e.event_id != event.event_id
        )

        if buy_count >= 2:
            score += 10
            reasons.append(
                f"Cluster buying detected ({buy_count + 1} BUY events in 7 days)"
            )

        # === Cap score ===
        score = max(0, min(100, score))

        # === Map score to signal ===
        signal = self._score_to_signal(event, score, reasons)

        logger.info(
            f"Generated signal for {event.ticker}: "
            f"{signal.action}/{signal.strength} (score={score})"
        )

        return signal

    def _score_to_signal(
        self, event: CongressTradeEvent, score: int, reasons: list[str]
    ) -> TradeSignal:
        """
        Map score and transaction type to trading signal.

        Args:
            event: Congressional trade event
            score: Computed score (0-100)
            reasons: List of scoring reasons

        Returns:
            TradeSignal
        """
        signal_id = TradeSignal.generate_signal_id(
            event.event_id, self.strategy_version
        )

        # For BUY transactions
        if event.transaction_type == "BUY":
            if score >= 80:
                return TradeSignal(
                    signal_id=signal_id,
                    event_id=event.event_id,
                    ticker=event.ticker,
                    action="BUY",
                    strength="STRONG",
                    score=score,
                    reason=reasons,
                    strategy_version=self.strategy_version,
                )
            elif score >= 65:
                return TradeSignal(
                    signal_id=signal_id,
                    event_id=event.event_id,
                    ticker=event.ticker,
                    action="BUY",
                    strength="NORMAL",
                    score=score,
                    reason=reasons,
                    strategy_version=self.strategy_version,
                )
            else:  # 50-64
                return TradeSignal(
                    signal_id=signal_id,
                    event_id=event.event_id,
                    ticker=event.ticker,
                    action="NONE",
                    strength="WATCH",
                    score=score,
                    reason=reasons + ["Score below BUY threshold"],
                    strategy_version=self.strategy_version,
                )

        # For SELL transactions
        elif event.transaction_type == "SELL":
            # Check if we have a position in this ticker
            position = db.get_position(event.ticker)

            if position:
                return TradeSignal(
                    signal_id=signal_id,
                    event_id=event.event_id,
                    ticker=event.ticker,
                    action="SELL",
                    strength="STRONG",
                    score=score,
                    reason=reasons + ["Member sold + we have position"],
                    strategy_version=self.strategy_version,
                )
            else:
                return TradeSignal(
                    signal_id=signal_id,
                    event_id=event.event_id,
                    ticker=event.ticker,
                    action="NONE",
                    strength="IGNORE",
                    score=score,
                    reason=reasons + ["Member sold but we have no position"],
                    strategy_version=self.strategy_version,
                )

        # For OTHER transactions
        else:
            return TradeSignal(
                signal_id=signal_id,
                event_id=event.event_id,
                ticker=event.ticker,
                action="NONE",
                strength="IGNORE",
                score=score,
                reason=reasons
                + [f"Transaction type not actionable: {event.transaction_type}"],
                strategy_version=self.strategy_version,
            )

    def _create_ignore_signal(
        self, event: CongressTradeEvent, reasons: list[str]
    ) -> TradeSignal:
        """
        Create an IGNORE signal for filtered-out events.

        Args:
            event: Congressional trade event
            reasons: Reasons for ignoring

        Returns:
            TradeSignal with IGNORE strength
        """
        # Track rejection statistics
        stats = get_rejection_stats()
        for reason in reasons:
            stats.record_rejection(reason)

        signal_id = TradeSignal.generate_signal_id(
            event.event_id, self.strategy_version
        )

        return TradeSignal(
            signal_id=signal_id,
            event_id=event.event_id,
            ticker=event.ticker,
            action="NONE",
            strength="IGNORE",
            score=0,
            reason=reasons,
            strategy_version=self.strategy_version,
        )


def run_signal_generation() -> dict[str, Any]:
    """
    Generate signals for all events that don't have signals yet.

    This is the main entry point for the 'signals' CLI command.

    Returns:
        Summary dictionary with signal counts
    """
    logger.info("Starting signal generation")

    strategy = CongressTradeStrategy()

    # Get events without signals
    events = db.get_events_without_signals(strategy.strategy_version)

    if not events:
        logger.info("No new events to process")
        return {
            "status": "success",
            "processed": 0,
            "signals_by_strength": {},
        }

    # Generate and store signals
    signals_by_strength: dict[str, int] = {
        "STRONG": 0,
        "NORMAL": 0,
        "WATCH": 0,
        "IGNORE": 0,
    }

    for event in events:
        try:
            signal = strategy.generate_signal(event)
            db.insert_signal(signal)
            signals_by_strength[signal.strength] += 1

        except Exception as e:
            logger.error(f"Failed to generate signal for event {event.event_id}: {e}")

    summary = {
        "status": "success",
        "processed": len(events),
        "signals_by_strength": signals_by_strength,
    }

    logger.info(
        f"Signal generation complete: {len(events)} events processed, "
        f"{signals_by_strength['STRONG']} STRONG, {signals_by_strength['NORMAL']} NORMAL, "
        f"{signals_by_strength['WATCH']} WATCH, {signals_by_strength['IGNORE']} IGNORE"
    )

    return summary
