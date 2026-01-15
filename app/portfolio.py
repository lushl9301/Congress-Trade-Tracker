"""Portfolio state helpers."""
from __future__ import annotations

from datetime import datetime

DEFAULT_EXIT_RULE = "HOLD_30D"
DEFAULT_MAX_HOLD_DAYS = 30
DEFAULT_STOP_LOSS_PCT = -0.08
DEFAULT_TAKE_PROFIT_PCT = 0.20


def build_position_metadata(opened_at: datetime | None = None) -> dict:
    timestamp = (opened_at or datetime.utcnow()).isoformat()
    return {
        "opened_at": timestamp,
        "last_updated_at": timestamp,
        "exit_rule": DEFAULT_EXIT_RULE,
        "max_hold_days": DEFAULT_MAX_HOLD_DAYS,
        "stop_loss_pct": DEFAULT_STOP_LOSS_PCT,
        "take_profit_pct": DEFAULT_TAKE_PROFIT_PCT,
    }
