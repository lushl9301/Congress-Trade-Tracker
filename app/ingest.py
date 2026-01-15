"""
Ingestion module for congressional trading data.
Fetches from multiple sources with cross-verification, normalizes, deduplicates, and stores in database.
"""

from datetime import date as date_type
from typing import Any

from app.config import config
from app.data_sources import (
    DataSourceManager,
    FinancialModelingPrepSource,
    HouseStockWatcherSource,
    SourceStrategy,
)
from app.db import db
from app.logging import get_logger
from app.models import CongressTradeEvent

logger = get_logger(__name__)


class CongressTradeIngester:
    """Ingest congressional trading data from multiple sources into normalized database."""

    def __init__(self):
        """Initialize ingester with data source manager and database."""
        self.db = db
        self.manager = self._init_data_source_manager()

    def _init_data_source_manager(self) -> DataSourceManager:
        """Initialize data source manager based on configuration."""
        sources = []

        # Add House Stock Watcher if enabled
        if config.HSW_ENABLED:
            logger.info("Initializing House Stock Watcher source")
            hsw = HouseStockWatcherSource()
            sources.append(hsw)

        # Add Financial Modeling Prep if enabled
        if config.FMP_ENABLED:
            logger.info("Initializing Financial Modeling Prep source")
            fmp = FinancialModelingPrepSource(api_key=config.FMP_API_KEY)
            sources.append(fmp)

        if not sources:
            logger.error("No data sources enabled! Check configuration.")
            raise RuntimeError(
                "No data sources enabled. Set HSW_ENABLED=true or FMP_ENABLED=true"
            )

        # Parse strategy from config
        strategy_map = {
            "primary_only": SourceStrategy.PRIMARY_ONLY,
            "fallback": SourceStrategy.FALLBACK,
            "all": SourceStrategy.ALL,
            "verify": SourceStrategy.CROSS_VERIFY,
        }
        strategy = strategy_map.get(
            config.DATA_SOURCE_STRATEGY, SourceStrategy.CROSS_VERIFY
        )

        logger.info(
            f"Initializing DataSourceManager with {len(sources)} sources, "
            f"strategy={strategy.value}"
        )

        return DataSourceManager(sources=sources, strategy=strategy)

    def ingest_latest(
        self,
        symbol: str | None = None,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> dict[str, Any]:
        """
        Fetch latest congressional trading data from configured sources and store in database.

        Args:
            symbol: Optional ticker symbol to filter by
            from_date: Optional start date (YYYY-MM-DD)
            to_date: Optional end date (YYYY-MM-DD)

        Returns:
            Summary dict with counts of new/duplicate events
        """
        logger.info(
            f"Starting ingestion: symbol={symbol}, from={from_date}, to={to_date}, "
            f"strategy={config.DATA_SOURCE_STRATEGY}"
        )

        # Convert date strings to date objects
        from_date_obj = self._parse_date_string(from_date) if from_date else None
        to_date_obj = self._parse_date_string(to_date) if to_date else None

        # Fetch normalized records from data source manager
        try:
            normalized_trades = self.manager.get_trades(
                symbol=symbol, from_date=from_date_obj, to_date=to_date_obj
            )
        except Exception as e:
            logger.error(f"Failed to fetch data from sources: {e}")
            return {
                "status": "error",
                "error": str(e),
                "fetched": 0,
                "new_events": 0,
                "duplicates": 0,
                "verified": 0,
                "unverified": 0,
            }

        if not normalized_trades:
            logger.info("No records fetched from data sources")
            return {
                "status": "success",
                "fetched": 0,
                "new_events": 0,
                "duplicates": 0,
                "verified": 0,
                "unverified": 0,
            }

        # Convert normalized dicts to CongressTradeEvent models and store
        new_events = 0
        duplicates = 0
        errors = 0
        verified_count = 0
        unverified_count = 0

        for normalized_trade in normalized_trades:
            try:
                event = self._dict_to_event(normalized_trade)

                # Track verification stats
                if event.verified:
                    verified_count += 1
                else:
                    unverified_count += 1

                # Upsert to database (returns True if new, False if duplicate)
                is_new = self.db.upsert_event(event)

                if is_new:
                    new_events += 1
                    logger.debug(
                        f"New event: {event.ticker} ({event.source}, "
                        f"verified={event.verified})"
                    )
                else:
                    duplicates += 1

            except Exception as e:
                logger.error(
                    f"Failed to process normalized trade: {e}",
                    extra={"trade": normalized_trade},
                )
                errors += 1

        summary = {
            "status": "success",
            "fetched": len(normalized_trades),
            "new_events": new_events,
            "duplicates": duplicates,
            "errors": errors,
            "verified": verified_count,
            "unverified": unverified_count,
            "verification_rate": (
                f"{verified_count / len(normalized_trades) * 100:.1f}%"
                if normalized_trades
                else "0%"
            ),
        }

        logger.info(
            f"Ingestion complete: {new_events} new, {duplicates} duplicates, "
            f"{errors} errors, {verified_count} verified, {unverified_count} unverified"
        )

        return summary

    def _parse_date_string(self, date_str: str) -> date_type:
        """Parse date string (YYYY-MM-DD) to date object."""
        from datetime import datetime

        return datetime.strptime(date_str, "%Y-%m-%d").date()

    def _dict_to_event(self, normalized_trade: dict[str, Any]) -> CongressTradeEvent:
        """
        Convert normalized trade dict to CongressTradeEvent model.

        The normalized_trade dict comes from the data source manager
        and already has all the standard fields.
        """
        # Infer asset type
        ticker = normalized_trade.get("ticker", "")
        asset_description = normalized_trade.get("asset_description", "")
        asset_type = self._infer_asset_type(ticker, asset_description)

        # Generate stable event ID
        event_id = CongressTradeEvent.generate_event_id(
            source=normalized_trade["source"],
            ticker=normalized_trade["ticker"],
            transaction_type=normalized_trade["transaction_type"],
            trade_date=normalized_trade.get("trade_date"),
            disclosure_date=normalized_trade.get("disclosure_date"),
            amount_low=normalized_trade.get("amount_low"),
            amount_high=normalized_trade.get("amount_high"),
            member_name=normalized_trade.get("member_name"),
            owner=normalized_trade["owner"],
        )

        # Create event model
        event = CongressTradeEvent(
            event_id=event_id,
            source=normalized_trade["source"],
            member_name=normalized_trade.get("member_name"),
            member_id=normalized_trade.get("member_id"),
            owner=normalized_trade["owner"],
            ticker=normalized_trade["ticker"],
            asset_type=asset_type,
            transaction_type=normalized_trade["transaction_type"],
            trade_date=normalized_trade.get("trade_date"),
            disclosure_date=normalized_trade.get("disclosure_date"),
            amount_low=normalized_trade.get("amount_low"),
            amount_high=normalized_trade.get("amount_high"),
            currency="USD",
            raw=normalized_trade.get("raw", {}),
            verified=normalized_trade.get("verified", False),
            verification_sources=normalized_trade.get("verification_sources", []),
            verification_status=normalized_trade.get(
                "verification_status", "unverified"
            ),
            verification_discrepancies=normalized_trade.get(
                "verification_discrepancies"
            ),
        )

        return event

    def _infer_asset_type(self, ticker: str, asset_description: str) -> str:
        """
        Infer asset type (stock, etf, or unknown).

        For MVP, use simple heuristics. Can be enhanced later with market data.

        Args:
            ticker: Stock ticker symbol
            asset_description: Asset description from data source

        Returns:
            Asset type: "stock", "etf", or "unknown"
        """
        # Common ETF patterns
        etf_keywords = ["fund", "etf", "trust", "index"]
        description_lower = (asset_description or "").lower()

        if any(keyword in description_lower for keyword in etf_keywords):
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

        if ticker.upper() in common_etfs:
            return "etf"

        # Default to stock (most common case)
        return "stock"

    def get_source_health(self) -> dict[str, Any]:
        """Get health status of all data sources."""
        return self.manager.get_source_health()


def run_ingestion(
    symbol: str | None = None, from_date: str | None = None, to_date: str | None = None
) -> dict[str, Any]:
    """
    Run ingestion pipeline with multi-source support.

    This is the main entry point for the 'ingest' CLI command.

    Args:
        symbol: Optional ticker to filter by
        from_date: Optional start date (YYYY-MM-DD)
        to_date: Optional end date (YYYY-MM-DD)

    Returns:
        Summary dictionary
    """
    ingester = CongressTradeIngester()
    return ingester.ingest_latest(symbol=symbol, from_date=from_date, to_date=to_date)
