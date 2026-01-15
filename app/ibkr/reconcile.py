"""Reconciliation stub."""
from __future__ import annotations

import logging

from app.db import Database

logger = logging.getLogger(__name__)


def reconcile(db: Database) -> dict[str, int]:
    positions = db.fetch_positions()
    logger.info("reconcile complete", extra={"positions": len(positions)})
    return {"positions": len(positions)}
