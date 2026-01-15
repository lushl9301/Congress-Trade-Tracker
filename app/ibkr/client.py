"""IBKR client abstraction (paper trading stub)."""
from __future__ import annotations

import logging
from datetime import datetime

from app.config import AppConfig

logger = logging.getLogger(__name__)


class IbkrClient:
    def __init__(self, config: AppConfig) -> None:
        self.config = config

    def place_order(self, payload: dict) -> dict:
        if not self.config.trading_enabled:
            logger.info("trading disabled; skipping order", extra=payload)
            return {
                "status": "skipped",
                "timestamp": datetime.utcnow().isoformat(),
                "details": "TRADING_ENABLED is false",
            }
        if self.config.trading_mode != "paper":
            logger.warning("live trading requested", extra={"mode": self.config.trading_mode})
        logger.info("placing order", extra=payload)
        return {
            "status": "submitted",
            "timestamp": datetime.utcnow().isoformat(),
            "order_id": f"paper-{payload['ticker']}-{datetime.utcnow().timestamp()}",
        }
