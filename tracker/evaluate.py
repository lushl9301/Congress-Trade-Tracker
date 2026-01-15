"""Signal generation and evaluation logic."""

from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from tracker.database import DisclosureDB, SessionLocal, SignalDB
from tracker.logger import logger
from tracker.models import Disclosure, Signal, SignalAction, SignalConfidence, TransactionType


class SignalGenerator:
    """Generate trading signals from congressional disclosures."""

    def __init__(self):
        pass

    def filter_disclosure(self, disclosure: Disclosure) -> tuple[bool, str]:
        """Apply hard filters to disclosure.

        Returns:
            (should_process, reason_if_filtered)
        """
        # Filter 1: Delay too large
        if disclosure.delay_days is not None and disclosure.delay_days > 45:
            return False, f"STALE_DISCLOSURE_{disclosure.delay_days}D"

        # Filter 2: Amount too small
        if disclosure.amount_max < 5000:
            return False, f"AMOUNT_TOO_SMALL_{disclosure.amount_max}"

        # Filter 3: Invalid ticker
        if not disclosure.ticker or len(disclosure.ticker) > 5:
            return False, f"INVALID_TICKER_{disclosure.ticker}"

        # Filter 4: OTHER transaction type
        if disclosure.transaction_type == TransactionType.OTHER:
            return False, "TRANSACTION_TYPE_OTHER"

        return True, ""

    def score_disclosure(self, disclosure: Disclosure, db: Session) -> tuple[int, list[str]]:
        """Score a disclosure from 0-100.

        Returns:
            (score, reasons)
        """
        score = 50
        reasons = []

        # Freshness scoring (max +30)
        if disclosure.delay_days is not None:
            if disclosure.delay_days <= 7:
                score += 30
                reasons.append(f"FRESH_{disclosure.delay_days}D")
            elif disclosure.delay_days <= 14:
                score += 20
                reasons.append(f"RECENT_{disclosure.delay_days}D")
            elif disclosure.delay_days <= 30:
                score += 10
                reasons.append(f"MODERATE_{disclosure.delay_days}D")
            else:
                score += 5
                reasons.append(f"OLDER_{disclosure.delay_days}D")

        # Amount scoring (max +25)
        amount = disclosure.amount_estimate
        if amount >= 1_000_000:
            score += 25
            reasons.append("AMOUNT_1M+")
        elif amount >= 500_000:
            score += 20
            reasons.append("AMOUNT_500K+")
        elif amount >= 250_000:
            score += 15
            reasons.append("AMOUNT_250K+")
        elif amount >= 100_000:
            score += 10
            reasons.append("AMOUNT_100K+")
        elif amount >= 50_000:
            score += 5
            reasons.append("AMOUNT_50K+")
        else:
            score += 2
            reasons.append("AMOUNT_5K+")

        # Politician importance (max +15)
        # For MVP, assume all are "member" level
        # In future, parse owner type from raw_data
        score += 15
        reasons.append("MEMBER_TRADE")

        # Cluster signal (max +15)
        cluster_bonus, cluster_reason = self._check_cluster_signal(disclosure, db)
        score += cluster_bonus
        if cluster_reason:
            reasons.append(cluster_reason)

        # Cap score
        score = min(100, max(0, score))

        return score, reasons

    def _check_cluster_signal(self, disclosure: Disclosure, db: Session) -> tuple[int, str]:
        """Check if multiple politicians bought same ticker recently.

        Returns:
            (bonus_points, reason)
        """
        if not disclosure.trade_date:
            return 0, ""

        # Look for similar trades in last 14 days
        lookback_date = disclosure.trade_date - timedelta(days=14)

        similar_count = (
            db.query(func.count(DisclosureDB.id))
            .filter(
                DisclosureDB.ticker == disclosure.ticker,
                DisclosureDB.transaction_type == disclosure.transaction_type.value,
                DisclosureDB.trade_date >= lookback_date,
                DisclosureDB.trade_date <= disclosure.trade_date,
                DisclosureDB.id != str(disclosure.id),  # Exclude self
            )
            .scalar()
        )

        if similar_count >= 3:
            return 15, f"CLUSTER_4+_POLITICIANS"
        elif similar_count >= 2:
            return 10, f"CLUSTER_3_POLITICIANS"
        elif similar_count >= 1:
            return 5, f"CLUSTER_2_POLITICIANS"

        return 0, ""

    def map_score_to_action(
        self, score: int, disclosure: Disclosure, has_position: bool
    ) -> tuple[SignalAction, SignalConfidence]:
        """Map score to action and confidence.

        Args:
            score: Score 0-100
            disclosure: The disclosure
            has_position: Whether we currently own this ticker

        Returns:
            (action, confidence)
        """
        # SELL signals
        if disclosure.transaction_type == TransactionType.SELL:
            if has_position:
                return SignalAction.SELL, SignalConfidence.HIGH
            else:
                return SignalAction.IGNORE, SignalConfidence.LOW

        # BUY signals
        if disclosure.transaction_type == TransactionType.BUY:
            if score >= 85:
                return SignalAction.BUY, SignalConfidence.HIGH
            elif score >= 70:
                return SignalAction.BUY, SignalConfidence.MEDIUM
            elif score >= 50:
                return SignalAction.WATCH, SignalConfidence.LOW
            else:
                return SignalAction.IGNORE, SignalConfidence.LOW

        return SignalAction.IGNORE, SignalConfidence.LOW

    def generate_signal(
        self, disclosure: Disclosure, db: Session, has_position: bool = False
    ) -> Signal | None:
        """Generate a signal from a disclosure.

        Args:
            disclosure: The disclosure to evaluate
            db: Database session
            has_position: Whether we currently own this ticker

        Returns:
            Signal if actionable, None otherwise
        """
        # Apply filters
        should_process, filter_reason = self.filter_disclosure(disclosure)
        if not should_process:
            logger.debug(
                f"Filtered out disclosure",
                ticker=disclosure.ticker,
                reason=filter_reason,
            )
            return None

        # Score
        score, reasons = self.score_disclosure(disclosure, db)

        # Map to action
        action, confidence = self.map_score_to_action(score, disclosure, has_position)

        signal = Signal(
            disclosure_id=disclosure.id,
            ticker=disclosure.ticker,
            action=action,
            confidence=confidence,
            score=score,
            reasons=reasons,
        )

        logger.info(
            f"Generated signal",
            ticker=signal.ticker,
            action=signal.action.value,
            confidence=signal.confidence.value,
            score=signal.score,
            reasons=reasons,
        )

        return signal

    def save_signal(self, signal: Signal, db: Session) -> None:
        """Save signal to database."""
        # Check if signal already exists for this disclosure
        existing = (
            db.query(SignalDB).filter(SignalDB.disclosure_id == str(signal.disclosure_id)).first()
        )

        if existing:
            logger.debug(f"Signal already exists for disclosure {signal.disclosure_id}")
            return

        db_signal = SignalDB(
            id=str(signal.id),
            disclosure_id=str(signal.disclosure_id),
            ticker=signal.ticker,
            action=signal.action.value,
            confidence=signal.confidence.value,
            score=signal.score,
            reasons=signal.reasons,
        )

        db.add(db_signal)
        db.commit()
        logger.info(f"Saved signal {signal.id} to database")

    def process_new_disclosures(self) -> int:
        """Process all disclosures that don't have signals yet.

        Returns:
            Number of signals generated
        """
        db = SessionLocal()
        signals_generated = 0

        try:
            # Find disclosures without signals
            disclosures_without_signals = (
                db.query(DisclosureDB)
                .outerjoin(SignalDB, DisclosureDB.id == SignalDB.disclosure_id)
                .filter(SignalDB.id.is_(None))
                .all()
            )

            logger.info(f"Processing {len(disclosures_without_signals)} new disclosures")

            for db_disclosure in disclosures_without_signals:
                # Convert to Pydantic model
                disclosure = Disclosure(
                    id=UUID(db_disclosure.id),
                    source=db_disclosure.source,
                    politician=db_disclosure.politician,
                    ticker=db_disclosure.ticker,
                    transaction_type=TransactionType(db_disclosure.transaction_type),
                    trade_date=db_disclosure.trade_date,
                    disclosure_date=db_disclosure.disclosure_date,
                    amount_min=db_disclosure.amount_min,
                    amount_max=db_disclosure.amount_max,
                    amount_estimate=db_disclosure.amount_estimate,
                    delay_days=db_disclosure.delay_days,
                    raw_data=db_disclosure.raw_data,
                    created_at=db_disclosure.created_at,
                )

                # TODO: Check if we have position (for now, assume False)
                has_position = False

                # Generate signal
                signal = self.generate_signal(disclosure, db, has_position)

                if signal:
                    self.save_signal(signal, db)
                    signals_generated += 1

            logger.info(f"Generated {signals_generated} signals")
            return signals_generated

        finally:
            db.close()
