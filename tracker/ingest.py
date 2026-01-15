"""Data ingestion from Finnhub and other sources."""

from datetime import datetime, timedelta
from typing import Any

import finnhub
from sqlalchemy.orm import Session

from tracker.config import settings
from tracker.database import DisclosureDB, SessionLocal
from tracker.logger import logger
from tracker.models import Disclosure, TransactionType


class DataIngestor:
    """Fetch and store congressional trade disclosures."""

    def __init__(self):
        self.finnhub_client = finnhub.Client(api_key=settings.finnhub_api_key)

    def fetch_finnhub_trades(
        self, symbol: str | None = None, from_date: str | None = None, to_date: str | None = None
    ) -> list[dict[str, Any]]:
        """Fetch congressional trades from Finnhub.

        Args:
            symbol: Stock ticker (optional, fetches all if None)
            from_date: Start date in YYYY-MM-DD format
            to_date: End date in YYYY-MM-DD format

        Returns:
            List of trade records
        """
        # Default date range: last 30 days
        if not from_date:
            from_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        if not to_date:
            to_date = datetime.now().strftime("%Y-%m-%d")

        logger.info(
            f"Fetching congressional trades from Finnhub",
            symbol=symbol or "ALL",
            from_date=from_date,
            to_date=to_date,
        )

        try:
            # Finnhub API call
            result = self.finnhub_client.congressional_trading(
                symbol=symbol or "", from_date=from_date, to_date=to_date
            )

            trades = result.get("data", []) if isinstance(result, dict) else []
            logger.info(f"Fetched {len(trades)} trades from Finnhub")
            return trades

        except Exception as e:
            logger.error(f"Error fetching from Finnhub: {e}")
            return []

    def normalize_disclosure(self, raw: dict[str, Any]) -> Disclosure | None:
        """Convert Finnhub response to normalized Disclosure model.

        Finnhub fields:
        - name: Politician name
        - symbol: Stock ticker
        - transactionType: BUY/SELL/etc
        - transactionDate: Trade date (YYYY-MM-DD)
        - filingDate: Disclosure date (YYYY-MM-DD)
        - amount: Amount range string (e.g., "$15,001 - $50,000")
        """
        try:
            # Parse amount range
            amount_str = raw.get("amount", "")
            amount_min, amount_max = self._parse_amount_range(amount_str)

            # Parse dates
            trade_date = None
            if raw.get("transactionDate"):
                try:
                    trade_date = datetime.strptime(raw["transactionDate"], "%Y-%m-%d").date()
                except ValueError:
                    logger.warning(f"Invalid trade_date format: {raw.get('transactionDate')}")

            disclosure_date = None
            if raw.get("filingDate"):
                try:
                    disclosure_date = datetime.strptime(raw["filingDate"], "%Y-%m-%d").date()
                except ValueError:
                    logger.warning(f"Invalid disclosure_date format: {raw.get('filingDate')}")

            # Calculate delay
            delay_days = None
            if trade_date and disclosure_date:
                delay_days = (disclosure_date - trade_date).days

            # Map transaction type
            tx_type_raw = raw.get("transactionType", "").upper()
            if "BUY" in tx_type_raw or "PURCHASE" in tx_type_raw:
                tx_type = TransactionType.BUY
            elif "SELL" in tx_type_raw or "SALE" in tx_type_raw:
                tx_type = TransactionType.SELL
            else:
                tx_type = TransactionType.OTHER

            disclosure = Disclosure(
                source="finnhub",
                politician=raw.get("name", "UNKNOWN"),
                ticker=raw.get("symbol", "").upper(),
                transaction_type=tx_type,
                trade_date=trade_date,
                disclosure_date=disclosure_date,
                amount_min=amount_min,
                amount_max=amount_max,
                amount_estimate=(amount_min + amount_max) / 2,
                delay_days=delay_days,
                raw_data=raw,
            )

            return disclosure

        except Exception as e:
            logger.error(f"Error normalizing disclosure: {e}", raw=raw)
            return None

    def _parse_amount_range(self, amount_str: str) -> tuple[float, float]:
        """Parse amount range string to min/max floats.

        Examples:
            "$15,001 - $50,000" -> (15001, 50000)
            "$1,000,001 - $5,000,000" -> (1000001, 5000000)
        """
        # Remove $ and commas, split by dash
        cleaned = amount_str.replace("$", "").replace(",", "").strip()

        if " - " in cleaned:
            parts = cleaned.split(" - ")
            try:
                return float(parts[0]), float(parts[1])
            except ValueError:
                pass

        # Default if parsing fails
        return 0.0, 0.0

    def deduplicate_and_save(self, disclosures: list[Disclosure], db: Session) -> int:
        """Save disclosures to database, avoiding duplicates.

        Duplicate check: (politician, ticker, trade_date, amount_estimate)

        Returns:
            Number of new disclosures saved
        """
        saved_count = 0

        for disclosure in disclosures:
            # Check if already exists
            existing = (
                db.query(DisclosureDB)
                .filter(
                    DisclosureDB.politician == disclosure.politician,
                    DisclosureDB.ticker == disclosure.ticker,
                    DisclosureDB.trade_date == disclosure.trade_date,
                    DisclosureDB.amount_estimate == disclosure.amount_estimate,
                )
                .first()
            )

            if existing:
                logger.debug(
                    f"Disclosure already exists",
                    politician=disclosure.politician,
                    ticker=disclosure.ticker,
                )
                continue

            # Save new disclosure
            db_disclosure = DisclosureDB(
                id=str(disclosure.id),
                source=disclosure.source,
                politician=disclosure.politician,
                ticker=disclosure.ticker,
                transaction_type=disclosure.transaction_type.value,
                trade_date=disclosure.trade_date,
                disclosure_date=disclosure.disclosure_date,
                amount_min=disclosure.amount_min,
                amount_max=disclosure.amount_max,
                amount_estimate=disclosure.amount_estimate,
                delay_days=disclosure.delay_days,
                raw_data=disclosure.raw_data,
            )

            db.add(db_disclosure)
            saved_count += 1

        db.commit()
        logger.info(f"Saved {saved_count} new disclosures to database")
        return saved_count

    def ingest(
        self, symbol: str | None = None, from_date: str | None = None, to_date: str | None = None
    ) -> int:
        """Main ingestion pipeline.

        Returns:
            Number of new disclosures saved
        """
        # Fetch from Finnhub
        raw_trades = self.fetch_finnhub_trades(symbol, from_date, to_date)

        # Normalize
        disclosures = []
        for raw in raw_trades:
            disclosure = self.normalize_disclosure(raw)
            if disclosure:
                disclosures.append(disclosure)

        logger.info(f"Normalized {len(disclosures)} disclosures")

        # Save to database
        db = SessionLocal()
        try:
            saved_count = self.deduplicate_and_save(disclosures, db)
            return saved_count
        finally:
            db.close()
