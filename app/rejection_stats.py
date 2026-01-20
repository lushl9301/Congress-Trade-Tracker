"""
Rejection statistics tracking for signal generation.
Helps understand why Congressional trade events are being filtered out.
"""

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Dict

from app.db import db
from app.logging import get_logger

logger = get_logger(__name__)


class RejectionStats:
    """Track rejection reasons for signal generation."""

    def __init__(self):
        """Initialize rejection stats tracker."""
        self.stats: Dict[str, int] = defaultdict(int)

    def record_rejection(self, reason: str) -> None:
        """
        Record a rejection reason.

        Args:
            reason: Short description of why event was rejected
        """
        self.stats[reason] += 1

    def get_summary(self) -> Dict[str, int]:
        """
        Get summary of rejection statistics.

        Returns:
            Dictionary mapping reason to count
        """
        return dict(self.stats)

    def clear(self) -> None:
        """Clear all statistics."""
        self.stats.clear()


def get_rejection_summary_from_db(days: int = 7) -> Dict[str, any]:
    """
    Analyze signals in database to compute rejection statistics.

    Args:
        days: Number of days to look back

    Returns:
        Dictionary with rejection statistics
    """
    cutoff_date = datetime.utcnow() - timedelta(days=days)

    with db.get_connection() as conn:
        cursor = conn.cursor()

        # Count all signals by action/strength
        cursor.execute(
            """
            SELECT action, strength, COUNT(*) as count
            FROM trade_signals
            WHERE created_at >= ?
            GROUP BY action, strength
            """,
            (cutoff_date.isoformat(),),
        )

        signal_counts = {}
        for row in cursor.fetchall():
            key = f"{row['action']}_{row['strength']}"
            signal_counts[key] = row['count']

        # Count events without signals (rejected before signal generation)
        cursor.execute(
            """
            SELECT COUNT(*) as count
            FROM congress_trade_events
            WHERE created_at >= ?
            AND event_id NOT IN (SELECT event_id FROM trade_signals)
            """,
            (cutoff_date.isoformat(),),
        )
        events_without_signals = cursor.fetchone()['count']

        # Get total events
        cursor.execute(
            """
            SELECT COUNT(*) as count
            FROM congress_trade_events
            WHERE created_at >= ?
            """,
            (cutoff_date.isoformat(),),
        )
        total_events = cursor.fetchone()['count']

    # Compute rejection stats
    ignore_count = signal_counts.get('NONE_IGNORE', 0)
    watch_count = signal_counts.get('BUY_WATCH', 0) + signal_counts.get('SELL_WATCH', 0)
    buy_count = signal_counts.get('BUY_NORMAL', 0) + signal_counts.get('BUY_STRONG', 0)
    sell_count = signal_counts.get('SELL_NORMAL', 0) + signal_counts.get('SELL_STRONG', 0)

    total_signals = sum(signal_counts.values())
    passed_filters = buy_count + sell_count + watch_count

    return {
        'days': days,
        'total_events': total_events,
        'total_signals': total_signals,
        'events_without_signals': events_without_signals,
        'rejected_ignore': ignore_count,
        'watch': watch_count,
        'buy_signals': buy_count,
        'sell_signals': sell_count,
        'passed_filters': passed_filters,
        'rejection_rate': (ignore_count / total_signals * 100) if total_signals > 0 else 0,
    }


# Global instance
_rejection_stats = None


def get_rejection_stats() -> RejectionStats:
    """Get global rejection stats instance."""
    global _rejection_stats
    if _rejection_stats is None:
        _rejection_stats = RejectionStats()
    return _rejection_stats
