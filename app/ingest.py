"""Ingest Finnhub congressional trading data."""
from __future__ import annotations

import logging

from app.db import Database
from app.finnhub_client import FinnhubClient
from app.models import CongressTradeEvent

logger = logging.getLogger(__name__)


def ingest_congress_trades(client: FinnhubClient, db: Database) -> dict[str, int]:
    records = client.fetch_congress_trades()
    events: list[CongressTradeEvent] = []
    for record in records:
        try:
            events.append(CongressTradeEvent.from_finnhub(record))
        except Exception as exc:  # noqa: BLE001 - keep ingest resilient
            logger.warning("failed to normalize record", extra={"error": str(exc)})
    inserted = db.upsert_events(events)
    logger.info("ingest complete", extra={"records": len(records), "inserted": inserted})
    return {"records": len(records), "inserted": inserted}
