"""Order execution helpers."""
from __future__ import annotations

import logging
from datetime import datetime

from app.db import Database
from app.ibkr.client import IbkrClient
from app.portfolio import build_position_metadata

logger = logging.getLogger(__name__)

TARGET_PCT_STRONG = 0.03
TARGET_PCT_NORMAL = 0.015
DEFAULT_NAV = 100000
DEFAULT_FILL_PRICE = 100.0


def execute_signals(db: Database, client: IbkrClient) -> dict[str, int]:
    signals = db.fetch_signals_for_trade()
    placed = 0
    for signal in signals:
        strength = signal["strength"]
        target_pct = TARGET_PCT_STRONG if strength == "STRONG" else TARGET_PCT_NORMAL
        notional = DEFAULT_NAV * target_pct
        payload = {
            "signal_id": signal["signal_id"],
            "ticker": signal["ticker"],
            "side": signal["action"],
            "notional": notional,
            "qty": None,
            "order_type": "MKT",
            "tif": "DAY",
        }
        response = client.place_order(payload)
        order_id = db.record_order(payload, response)
        placed += 1

        if response.get("status") == "submitted":
            qty = notional / DEFAULT_FILL_PRICE
            fill = {
                "ticker": payload["ticker"],
                "qty": qty,
                "fill_price": DEFAULT_FILL_PRICE,
                "commissions": 0.0,
                "fill_time": datetime.utcnow().isoformat(),
            }
            db.record_fill(order_id, fill)
            if payload["side"] == "BUY":
                metadata = build_position_metadata()
                db.upsert_position(payload["ticker"], qty, DEFAULT_FILL_PRICE, metadata)
        logger.info("order handled", extra={"signal_id": signal["signal_id"], "status": response.get("status")})
    return {"signals": len(signals), "orders": placed}
