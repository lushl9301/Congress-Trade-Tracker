"""
House Stock Watcher data source implementation.

Free API for congressional trading disclosures.
No API key required - completely free.
"""

from datetime import date, datetime
from typing import Any, Dict, List, Optional

import requests
from loguru import logger

from app.data_sources.base import CongressDataSource


class HouseStockWatcherSource(CongressDataSource):
    """
    House Stock Watcher API client.

    Free congressional trading data from housestockwatcher.com
    No authentication required.
    Rate limit: ~250 requests/day (reasonable use policy)
    """

    BASE_URL = "https://house-stock-watcher-data.s3-us-west-2.amazonaws.com/data"

    def __init__(self, timeout: int = 30):
        """
        Initialize House Stock Watcher client.

        Args:
            timeout: Request timeout in seconds
        """
        self.timeout = timeout
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": "Congress-Trade-Tracker/1.0"
        })

    def get_name(self) -> str:
        """Return source name."""
        return "house_stock_watcher"

    def get_trades(
        self,
        symbol: Optional[str] = None,
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
    ) -> List[Dict[str, Any]]:
        """
        Fetch congressional trades from House Stock Watcher.

        Args:
            symbol: Filter by ticker symbol (optional)
            from_date: Start date for trades (optional)
            to_date: End date for trades (optional)

        Returns:
            List of raw trade records

        Raises:
            requests.RequestException: If API request fails
        """
        try:
            # House Stock Watcher provides all transactions in a single JSON file
            url = f"{self.BASE_URL}/all_transactions.json"

            logger.info(f"Fetching trades from House Stock Watcher: {url}")
            response = self._session.get(url, timeout=self.timeout)
            response.raise_for_status()

            trades = response.json()
            logger.info(f"Fetched {len(trades)} total trades from House Stock Watcher")

            # Apply client-side filtering
            filtered_trades = self._filter_trades(
                trades, symbol=symbol, from_date=from_date, to_date=to_date
            )

            logger.info(f"After filtering: {len(filtered_trades)} trades")
            return filtered_trades

        except requests.RequestException as e:
            logger.error(f"House Stock Watcher API request failed: {e}")
            raise

    def _filter_trades(
        self,
        trades: List[Dict[str, Any]],
        symbol: Optional[str] = None,
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
    ) -> List[Dict[str, Any]]:
        """Apply client-side filters to trades."""
        filtered = trades

        # Filter by symbol
        if symbol:
            symbol_upper = symbol.upper()
            filtered = [
                t for t in filtered
                if t.get("ticker", "").upper() == symbol_upper
            ]

        # Filter by date range
        if from_date or to_date:
            filtered = [
                t for t in filtered
                if self._in_date_range(t, from_date, to_date)
            ]

        return filtered

    def _in_date_range(
        self,
        trade: Dict[str, Any],
        from_date: Optional[date],
        to_date: Optional[date]
    ) -> bool:
        """Check if trade falls within date range."""
        # Try to parse transaction_date or disclosure_date
        trade_date_str = trade.get("transaction_date") or trade.get("disclosure_date")
        if not trade_date_str:
            return True  # Include if no date available

        try:
            # Parse date (format: YYYY-MM-DD)
            trade_date = datetime.strptime(trade_date_str, "%Y-%m-%d").date()

            if from_date and trade_date < from_date:
                return False
            if to_date and trade_date > to_date:
                return False

            return True
        except (ValueError, TypeError):
            return True  # Include if date parsing fails

    def normalize_trade(self, raw_trade: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalize House Stock Watcher trade to common format.

        HSW format example:
        {
            "disclosure_year": "2021",
            "disclosure_date": "2021-01-15",
            "transaction_date": "2021-01-01",
            "owner": "joint",
            "ticker": "AAPL",
            "asset_description": "Apple Inc.",
            "type": "purchase",
            "amount": "$1,001 - $15,000",
            "representative": "Hon. John Doe",
            "district": "CA-12",
            "ptr_link": "https://...",
            "cap_gains_over_200_usd": false
        }
        """
        # Parse transaction type
        raw_type = raw_trade.get("type", "").lower()
        if "purchase" in raw_type or "buy" in raw_type:
            transaction_type = "BUY"
        elif "sale" in raw_type or "sell" in raw_type:
            transaction_type = "SELL"
        else:
            transaction_type = "OTHER"

        # Parse amount range
        amount_low, amount_high = self._parse_amount_range(
            raw_trade.get("amount", "")
        )

        # Parse dates
        trade_date = self._parse_date(raw_trade.get("transaction_date"))
        disclosure_date = self._parse_date(raw_trade.get("disclosure_date"))

        # Parse owner type
        owner = self._normalize_owner(raw_trade.get("owner", ""))

        return {
            "source": self.get_name(),
            "member_name": raw_trade.get("representative"),
            "member_id": None,  # HSW doesn't provide member ID
            "ticker": raw_trade.get("ticker", "").upper(),
            "asset_description": raw_trade.get("asset_description"),
            "transaction_type": transaction_type,
            "trade_date": trade_date,
            "disclosure_date": disclosure_date,
            "amount_low": amount_low,
            "amount_high": amount_high,
            "owner": owner,
            "raw": raw_trade,
        }

    def _parse_amount_range(self, amount_str: str) -> tuple[Optional[float], Optional[float]]:
        """
        Parse amount range string to (low, high) tuple.

        Examples:
            "$1,001 - $15,000" -> (1001.0, 15000.0)
            "$15,001 - $50,000" -> (15001.0, 50000.0)
            "$50,001 - $100,000" -> (50001.0, 100000.0)
        """
        if not amount_str or amount_str == "N/A":
            return None, None

        try:
            # Remove $ and , characters
            cleaned = amount_str.replace("$", "").replace(",", "")

            # Split on " - " or "-"
            if " - " in cleaned:
                parts = cleaned.split(" - ")
            elif "-" in cleaned:
                parts = cleaned.split("-")
            else:
                # Single value
                val = float(cleaned)
                return val, val

            if len(parts) == 2:
                low = float(parts[0].strip())
                high = float(parts[1].strip())
                return low, high
        except (ValueError, AttributeError):
            pass

        return None, None

    def _parse_date(self, date_str: Optional[str]) -> Optional[date]:
        """Parse date string to date object."""
        if not date_str:
            return None

        try:
            return datetime.strptime(date_str, "%Y-%m-%d").date()
        except (ValueError, TypeError):
            return None

    def _normalize_owner(self, owner_str: str) -> str:
        """
        Normalize owner field.

        HSW uses: "self", "spouse", "child", "joint", etc.
        We map to: "member", "spouse", "dependent", "unknown"
        """
        owner_lower = owner_str.lower()

        if owner_lower in ["self", "member"]:
            return "member"
        elif owner_lower in ["spouse", "joint"]:
            return "spouse"
        elif owner_lower in ["child", "dependent"]:
            return "dependent"
        else:
            return "unknown"

    def is_available(self) -> bool:
        """
        Check if House Stock Watcher is available.

        No API key needed, just check connectivity.
        """
        try:
            url = f"{self.BASE_URL}/all_transactions.json"
            response = self._session.head(url, timeout=5)
            return response.status_code == 200
        except requests.RequestException:
            return False

    def get_rate_limit_info(self) -> Dict[str, Any]:
        """
        Return rate limit information.

        HSW has no official rate limits but requests reasonable use.
        """
        return {
            "source": self.get_name(),
            "limit_per_day": 250,  # Estimated reasonable use
            "limit_per_minute": None,
            "requires_auth": False,
            "cost": "free",
        }
