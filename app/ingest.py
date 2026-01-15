"""
Ingestion module for congressional trading data.
Fetches from Finnhub, normalizes, deduplicates, and stores in database.
"""
from datetime import datetime
from typing import Any

from app.config import config
from app.db import db
from app.finnhub_client import get_finnhub_client
from app.logging import get_logger
from app.models import CongressTradeEvent

logger = get_logger(__name__)


class CongressTradeIngester:
    """Ingest congressional trading data from Finnhub into normalized database."""

    def __init__(self):
        """Initialize ingester with Finnhub client and database."""
        self.client = get_finnhub_client()
        self.db = db

    def ingest_latest(
        self, symbol: str | None = None, from_date: str | None = None, to_date: str | None = None
    ) -> dict[str, Any]:
        """
        Fetch latest congressional trading data and store in database.

        Args:
            symbol: Optional ticker symbol to filter by
            from_date: Optional start date (YYYY-MM-DD)
            to_date: Optional end date (YYYY-MM-DD)

        Returns:
            Summary dict with counts of new/duplicate events
        """
        logger.info(
            f"Starting ingestion: symbol={symbol}, from={from_date}, to={to_date}"
        )

        # Fetch raw records from Finnhub
        try:
            raw_records = self.client.get_congress_trading(
                symbol=symbol, from_date=from_date, to_date=to_date
            )
        except Exception as e:
            logger.error(f"Failed to fetch data from Finnhub: {e}")
            return {
                "status": "error",
                "error": str(e),
                "fetched": 0,
                "new_events": 0,
                "duplicates": 0,
            }

        if not raw_records:
            logger.info("No records fetched from Finnhub")
            return {
                "status": "success",
                "fetched": 0,
                "new_events": 0,
                "duplicates": 0,
            }

        # Normalize and deduplicate
        new_events = 0
        duplicates = 0
        errors = 0

        for raw_record in raw_records:
            try:
                event = self._normalize_record(raw_record)

                # Upsert to database (returns True if new, False if duplicate)
                is_new = self.db.upsert_event(event)

                if is_new:
                    new_events += 1
                else:
                    duplicates += 1

            except Exception as e:
                logger.error(f"Failed to process record: {e}", extra={"record": raw_record})
                errors += 1

        summary = {
            "status": "success",
            "fetched": len(raw_records),
            "new_events": new_events,
            "duplicates": duplicates,
            "errors": errors,
        }

        logger.info(
            f"Ingestion complete: {new_events} new, {duplicates} duplicates, {errors} errors"
        )

        return summary

    def _normalize_record(self, raw: dict[str, Any]) -> CongressTradeEvent:
        """
        Normalize a raw Finnhub record into canonical CongressTradeEvent.

        Args:
            raw: Raw record from Finnhub API

        Returns:
            Normalized CongressTradeEvent
        """
        # Extract and normalize fields
        ticker = raw.get("symbol", "").upper()
        member_name = raw.get("representativeName") or raw.get("name")
        transaction_type_raw = raw.get("transactionType", "")
        transaction_type = self.client.parse_transaction_type(transaction_type_raw)

        # Parse dates
        trade_date = self.client.parse_date(raw.get("transactionDate"))
        disclosure_date = self.client.parse_date(raw.get("filingDate"))

        # Parse amount range
        amount_str = raw.get("amount", "")
        amount_low, amount_high = self.client.parse_amount_range(amount_str)

        # Infer owner
        owner = self.client.infer_owner(raw)

        # Asset type inference (simple heuristic)
        asset_type = self._infer_asset_type(ticker, raw)

        # Generate stable event ID
        event_id = CongressTradeEvent.generate_event_id(
            source="finnhub",
            ticker=ticker,
            transaction_type=transaction_type,
            trade_date=trade_date,
            disclosure_date=disclosure_date,
            amount_low=amount_low,
            amount_high=amount_high,
            member_name=member_name,
            owner=owner,
        )

        # Create event
        event = CongressTradeEvent(
            event_id=event_id,
            source="finnhub",
            member_name=member_name,
            member_id=raw.get("representativeDistrict"),
            owner=owner,
            ticker=ticker,
            asset_type=asset_type,
            transaction_type=transaction_type,
            trade_date=trade_date,
            disclosure_date=disclosure_date,
            amount_low=amount_low,
            amount_high=amount_high,
            currency="USD",
            raw=raw,
        )

        return event

    def _infer_asset_type(self, ticker: str, raw: dict[str, Any]) -> str:
        """
        Infer asset type (stock, etf, or unknown).

        For MVP, use simple heuristics. Can be enhanced later with market data.

        Args:
            ticker: Stock ticker symbol
            raw: Raw Finnhub record

        Returns:
            Asset type: "stock", "etf", or "unknown"
        """
        # Common ETF patterns
        etf_keywords = ["fund", "etf", "trust", "index"]
        name = (raw.get("name") or "").lower()

        if any(keyword in name for keyword in etf_keywords):
            return "etf"

        # Check for common ETF tickers (this is a small subset)
        common_etfs = {
            "SPY",
            "QQQ",
            "IWM",
            "DIA",
            "VTI",
            "VOO",
            "IVV",
            "VEA",
            "VWO",
            "AGG",
            "BND",
            "LQD",
            "VIG",
            "VUG",
            "VTV",
            "XLF",
            "XLE",
            "XLK",
            "XLV",
            "XLI",
            "XLP",
            "XLY",
            "XLU",
            "XLRE",
            "XLB",
            "XLC",
        }

        if ticker in common_etfs:
            return "etf"

        # Default to stock (most common case)
        return "stock"


def run_ingestion(
    symbol: str | None = None, from_date: str | None = None, to_date: str | None = None
) -> dict[str, Any]:
    """
    Run ingestion pipeline.

    This is the main entry point for the 'ingest' CLI command.

    Args:
        symbol: Optional ticker to filter by
        from_date: Optional start date
        to_date: Optional end date

    Returns:
        Summary dictionary
    """
    ingester = CongressTradeIngester()
    return ingester.ingest_latest(symbol=symbol, from_date=from_date, to_date=to_date)
