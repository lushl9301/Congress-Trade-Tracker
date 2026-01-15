"""Email notification stub."""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def send_email(subject: str, body: str) -> None:
    logger.info("email notification skipped", extra={"subject": subject, "body": body})
