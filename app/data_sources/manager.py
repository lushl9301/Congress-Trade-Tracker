"""
Data source manager with multi-source support and cross-verification.

Implements smart fallback and verification strategies for congressional trade data.
"""

from datetime import date
from enum import Enum
from typing import Any, Dict, List, Optional, Set

from loguru import logger

from app.data_sources.base import CongressDataSource


class SourceStrategy(str, Enum):
    """Strategy for fetching data from multiple sources."""

    PRIMARY_ONLY = "primary_only"  # Use only primary source
    FALLBACK = "fallback"  # Try primary, fallback to secondary if primary fails
    ALL = "all"  # Fetch from all sources, merge results
    CROSS_VERIFY = "verify"  # Fetch from all, cross-verify, flag discrepancies


class DataSourceManager:
    """
    Manages multiple congressional data sources with verification and fallback.

    Features:
    - Smart fallback when sources are unavailable
    - Cross-verification of data from multiple sources
    - Automatic alerting on discrepancies
    - Rate limit tracking
    """

    def __init__(
        self,
        sources: List[CongressDataSource],
        strategy: SourceStrategy = SourceStrategy.CROSS_VERIFY,
        primary_source_index: int = 0,
    ):
        """
        Initialize data source manager.

        Args:
            sources: List of data sources to manage
            strategy: Strategy for fetching data (default: CROSS_VERIFY)
            primary_source_index: Index of primary source for FALLBACK strategy
        """
        if not sources:
            raise ValueError("At least one data source must be provided")

        self.sources = sources
        self.strategy = strategy
        self.primary_source_index = primary_source_index

        logger.info(
            f"DataSourceManager initialized with {len(sources)} sources, "
            f"strategy={strategy.value}"
        )

    def get_trades(
        self,
        symbol: Optional[str] = None,
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
    ) -> List[Dict[str, Any]]:
        """
        Fetch congressional trades using configured strategy.

        Args:
            symbol: Filter by ticker symbol
            from_date: Start date for trades
            to_date: End date for trades

        Returns:
            List of normalized trade records with verification metadata
        """
        if self.strategy == SourceStrategy.PRIMARY_ONLY:
            return self._fetch_primary_only(symbol, from_date, to_date)
        elif self.strategy == SourceStrategy.FALLBACK:
            return self._fetch_with_fallback(symbol, from_date, to_date)
        elif self.strategy == SourceStrategy.ALL:
            return self._fetch_from_all(symbol, from_date, to_date)
        elif self.strategy == SourceStrategy.CROSS_VERIFY:
            return self._fetch_with_verification(symbol, from_date, to_date)
        else:
            raise ValueError(f"Unknown strategy: {self.strategy}")

    def _fetch_primary_only(
        self,
        symbol: Optional[str],
        from_date: Optional[date],
        to_date: Optional[date]
    ) -> List[Dict[str, Any]]:
        """Fetch from primary source only."""
        primary = self.sources[self.primary_source_index]

        logger.info(f"Fetching from primary source: {primary.get_name()}")

        raw_trades = primary.get_trades(symbol, from_date, to_date)
        normalized = [primary.normalize_trade(t) for t in raw_trades]

        logger.info(f"Fetched {len(normalized)} trades from {primary.get_name()}")
        return normalized

    def _fetch_with_fallback(
        self,
        symbol: Optional[str],
        from_date: Optional[date],
        to_date: Optional[date]
    ) -> List[Dict[str, Any]]:
        """
        Try primary source first, fallback to others if primary fails.

        This implements smart fallback with alerts.
        """
        primary = self.sources[self.primary_source_index]
        fallback_sources = [
            s for i, s in enumerate(self.sources)
            if i != self.primary_source_index
        ]

        # Try primary first
        logger.info(f"Attempting to fetch from primary: {primary.get_name()}")

        try:
            if not primary.is_available():
                raise RuntimeError(f"Primary source {primary.get_name()} not available")

            raw_trades = primary.get_trades(symbol, from_date, to_date)
            normalized = [primary.normalize_trade(t) for t in raw_trades]

            logger.info(
                f"Successfully fetched {len(normalized)} trades from "
                f"primary source {primary.get_name()}"
            )
            return normalized

        except Exception as e:
            logger.warning(
                f"Primary source {primary.get_name()} failed: {e}. "
                f"Trying fallback sources..."
            )

            # Try fallback sources
            for fallback in fallback_sources:
                logger.info(f"Attempting fallback source: {fallback.get_name()}")

                try:
                    if not fallback.is_available():
                        logger.warning(
                            f"Fallback source {fallback.get_name()} not available"
                        )
                        continue

                    raw_trades = fallback.get_trades(symbol, from_date, to_date)
                    normalized = [fallback.normalize_trade(t) for t in raw_trades]

                    logger.warning(
                        f"⚠️  USING FALLBACK SOURCE: {fallback.get_name()} "
                        f"(primary {primary.get_name()} failed). "
                        f"Fetched {len(normalized)} trades."
                    )
                    return normalized

                except Exception as fallback_error:
                    logger.error(
                        f"Fallback source {fallback.get_name()} also failed: "
                        f"{fallback_error}"
                    )
                    continue

            # All sources failed
            logger.error("All data sources failed!")
            raise RuntimeError(
                f"All data sources failed. Primary: {e}, "
                f"checked {len(fallback_sources)} fallback sources."
            )

    def _fetch_from_all(
        self,
        symbol: Optional[str],
        from_date: Optional[date],
        to_date: Optional[date]
    ) -> List[Dict[str, Any]]:
        """Fetch from all sources and merge results (no deduplication)."""
        all_trades = []

        for source in self.sources:
            logger.info(f"Fetching from {source.get_name()}")

            try:
                if not source.is_available():
                    logger.warning(f"Source {source.get_name()} not available, skipping")
                    continue

                raw_trades = source.get_trades(symbol, from_date, to_date)
                normalized = [source.normalize_trade(t) for t in raw_trades]

                logger.info(
                    f"Fetched {len(normalized)} trades from {source.get_name()}"
                )
                all_trades.extend(normalized)

            except Exception as e:
                logger.error(f"Failed to fetch from {source.get_name()}: {e}")
                continue

        logger.info(f"Total trades from all sources: {len(all_trades)}")
        return all_trades

    def _fetch_with_verification(
        self,
        symbol: Optional[str],
        from_date: Optional[date],
        to_date: Optional[date]
    ) -> List[Dict[str, Any]]:
        """
        Fetch from all sources and cross-verify.

        This is the recommended strategy for production use.
        If only one source is available, it falls back gracefully with alerts.
        """
        results_by_source = {}
        available_sources = []

        # Attempt to fetch from all sources
        for source in self.sources:
            source_name = source.get_name()
            logger.info(f"Checking availability: {source_name}")

            try:
                if not source.is_available():
                    logger.warning(
                        f"⚠️  Source {source_name} is not available "
                        f"(check configuration/API key)"
                    )
                    continue

                logger.info(f"Fetching from {source_name} for verification")
                raw_trades = source.get_trades(symbol, from_date, to_date)
                normalized = [source.normalize_trade(t) for t in raw_trades]

                results_by_source[source_name] = normalized
                available_sources.append(source)

                logger.info(
                    f"Successfully fetched {len(normalized)} trades from {source_name}"
                )

            except Exception as e:
                logger.error(
                    f"Failed to fetch from {source_name}: {e}. "
                    f"Continuing with other sources..."
                )
                continue

        # Handle case where no sources are available
        if not available_sources:
            logger.error("No data sources are available!")
            raise RuntimeError(
                "No data sources are available. Check configuration and connectivity."
            )

        # Handle case where only one source is available
        if len(available_sources) == 1:
            single_source = available_sources[0]
            trades = results_by_source[single_source.get_name()]

            logger.warning(
                f"⚠️  SINGLE SOURCE MODE: Only {single_source.get_name()} is available. "
                f"Cross-verification disabled. Consider configuring additional sources."
            )

            # Mark all trades as unverified (single source)
            for trade in trades:
                trade["verified"] = False
                trade["verification_sources"] = [single_source.get_name()]
                trade["verification_status"] = "single_source"

            return trades

        # Multiple sources available - perform cross-verification
        logger.info(
            f"Cross-verifying data from {len(available_sources)} sources: "
            f"{[s.get_name() for s in available_sources]}"
        )

        verified_trades = self._cross_verify_trades(results_by_source)

        logger.info(
            f"Cross-verification complete. "
            f"{len(verified_trades)} total trades after verification."
        )

        return verified_trades

    def _cross_verify_trades(
        self, results_by_source: Dict[str, List[Dict[str, Any]]]
    ) -> List[Dict[str, Any]]:
        """
        Cross-verify trades from multiple sources.

        Matching logic:
        - Same ticker + transaction_type + trade_date = match
        - Trades found in multiple sources are marked as verified
        - Discrepancies in amounts are flagged
        """
        # Build a set of all unique trade keys
        all_trade_keys: Set[str] = set()
        trades_by_key: Dict[str, List[tuple[str, Dict[str, Any]]]] = {}

        for source_name, trades in results_by_source.items():
            for trade in trades:
                key = self._make_trade_key(trade)
                all_trade_keys.add(key)

                if key not in trades_by_key:
                    trades_by_key[key] = []

                trades_by_key[key].append((source_name, trade))

        # Verify and merge trades
        verified_trades = []

        for key in all_trade_keys:
            sources_with_trade = trades_by_key[key]
            num_sources = len(sources_with_trade)

            # Get the first occurrence as the canonical trade
            primary_source_name, canonical_trade = sources_with_trade[0]

            # Add verification metadata
            canonical_trade["verified"] = num_sources > 1
            canonical_trade["verification_sources"] = [s for s, _ in sources_with_trade]
            canonical_trade["verification_status"] = (
                "verified" if num_sources > 1 else "unverified"
            )

            # Check for discrepancies in amount ranges
            if num_sources > 1:
                discrepancies = self._check_amount_discrepancies(sources_with_trade)
                if discrepancies:
                    canonical_trade["verification_discrepancies"] = discrepancies
                    logger.warning(
                        f"Amount discrepancy detected for {canonical_trade['ticker']}: "
                        f"{discrepancies}"
                    )

            verified_trades.append(canonical_trade)

        # Log verification statistics
        verified_count = sum(1 for t in verified_trades if t["verified"])
        unverified_count = len(verified_trades) - verified_count

        logger.info(
            f"Verification stats: {verified_count} verified, "
            f"{unverified_count} unverified (single source only)"
        )

        if unverified_count > 0:
            logger.warning(
                f"⚠️  {unverified_count} trades found in only one source. "
                f"Consider this when making trading decisions."
            )

        return verified_trades

    def _make_trade_key(self, trade: Dict[str, Any]) -> str:
        """
        Create a unique key for trade matching.

        Key components: ticker + transaction_type + trade_date
        """
        ticker = trade.get("ticker", "").upper()
        transaction_type = trade.get("transaction_type", "")
        trade_date = trade.get("trade_date")

        # Convert date to string for hashing
        date_str = trade_date.isoformat() if trade_date else "UNKNOWN"

        return f"{ticker}|{transaction_type}|{date_str}"

    def _check_amount_discrepancies(
        self, sources_with_trade: List[tuple[str, Dict[str, Any]]]
    ) -> Optional[Dict[str, Any]]:
        """
        Check if different sources report different amount ranges.

        Returns discrepancy info if amounts differ significantly.
        """
        amounts = []

        for source_name, trade in sources_with_trade:
            amount_low = trade.get("amount_low")
            amount_high = trade.get("amount_high")

            if amount_low is not None and amount_high is not None:
                amounts.append({
                    "source": source_name,
                    "low": amount_low,
                    "high": amount_high,
                })

        # Check if all amounts are the same
        if len(amounts) < 2:
            return None

        first_amount = amounts[0]
        for other_amount in amounts[1:]:
            if (
                first_amount["low"] != other_amount["low"]
                or first_amount["high"] != other_amount["high"]
            ):
                return {
                    "type": "amount_mismatch",
                    "amounts_by_source": amounts,
                }

        return None

    def get_source_health(self) -> Dict[str, Any]:
        """
        Check health of all configured sources.

        Returns health status for each source.
        """
        health = {
            "strategy": self.strategy.value,
            "sources": [],
        }

        for source in self.sources:
            source_health = source.health_check()
            rate_limits = source.get_rate_limit_info()

            health["sources"].append({
                "name": source.get_name(),
                "available": source_health["available"],
                "error": source_health.get("error"),
                "rate_limits": rate_limits,
            })

        return health
