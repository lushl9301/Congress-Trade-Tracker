"""
Financial Modeling Prep (FMP) data source implementation.

Congressional trading data from financialmodelingprep.com
Free tier: 250 requests/day
"""

from datetime import date, datetime
from typing import Any, Dict, List, Optional

import requests
from loguru import logger

from app.data_sources.base import CongressDataSource


class FinancialModelingPrepSource(CongressDataSource):
    """
    Financial Modeling Prep API client for congressional trading data.

    Free tier: 250 requests/day
    Endpoint: /v4/senate-trading
    Rate limit tracking: Manual (based on daily usage)
    """

    BASE_URL = "https://financialmodelingprep.com/api/v4"

    def __init__(self, api_key: Optional[str] = None, timeout: int = 30):
        """
        Initialize Financial Modeling Prep client.

        Args:
            api_key: FMP API key (required for free tier)
            timeout: Request timeout in seconds

        TODO: Replace dummy API key with real key from https://financialmodelingprep.com
        To get your API key:
        1. Sign up at https://financialmodelingprep.com/register
        2. Verify your email
        3. Find API key in dashboard
        4. Set FMP_API_KEY environment variable
        """
        # TODO: USER MUST REPLACE THIS WITH REAL API KEY
        self.api_key = api_key or "DUMMY_FMP_API_KEY_REPLACE_ME"
        self.timeout = timeout
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": "Congress-Trade-Tracker/1.0"
        })

        if self.api_key == "DUMMY_FMP_API_KEY_REPLACE_ME":
            logger.warning(
                "FMP client initialized with DUMMY API key. "
                "Set FMP_API_KEY environment variable with real key from "
                "https://financialmodelingprep.com"
            )

    def get_name(self) -> str:
        """Return source name."""
        return "financial_modeling_prep"

    def get_trades(
        self,
        symbol: Optional[str] = None,
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
    ) -> List[Dict[str, Any]]:
        """
        Fetch congressional trades from FMP.

        Args:
            symbol: Filter by ticker symbol (optional)
            from_date: Start date for trades (optional)
            to_date: End date for trades (optional)

        Returns:
            List of raw trade records

        Raises:
            requests.RequestException: If API request fails
            ValueError: If API key is invalid
        """
        if self.api_key == "DUMMY_FMP_API_KEY_REPLACE_ME":
            logger.error("Cannot fetch trades with dummy API key. Set FMP_API_KEY.")
            raise ValueError(
                "FMP API key not configured. Set FMP_API_KEY environment variable."
            )

        try:
            # FMP senate-trading endpoint
            url = f"{self.BASE_URL}/senate-trading"

            params = {"apikey": self.api_key}

            # Add symbol filter if provided
            if symbol:
                params["symbol"] = symbol.upper()

            logger.info(f"Fetching trades from FMP: {url}")
            response = self._session.get(url, params=params, timeout=self.timeout)

            # Check for API key errors
            if response.status_code == 401:
                raise ValueError("Invalid FMP API key")
            elif response.status_code == 403:
                raise ValueError("FMP API key forbidden - check your subscription")

            response.raise_for_status()
            trades = response.json()

            logger.info(f"Fetched {len(trades)} trades from FMP")

            # Apply client-side date filtering
            if from_date or to_date:
                trades = self._filter_by_date(trades, from_date, to_date)
                logger.info(f"After date filtering: {len(trades)} trades")

            return trades

        except requests.RequestException as e:
            logger.error(f"FMP API request failed: {e}")
            raise

    def _filter_by_date(
        self,
        trades: List[Dict[str, Any]],
        from_date: Optional[date],
        to_date: Optional[date]
    ) -> List[Dict[str, Any]]:
        """Apply date range filter to trades."""
        filtered = []

        for trade in trades:
            trade_date_str = trade.get("transactionDate")
            if not trade_date_str:
                filtered.append(trade)
                continue

            try:
                trade_date = datetime.strptime(trade_date_str, "%Y-%m-%d").date()

                if from_date and trade_date < from_date:
                    continue
                if to_date and trade_date > to_date:
                    continue

                filtered.append(trade)
            except (ValueError, TypeError):
                filtered.append(trade)  # Include if date parsing fails

        return filtered

    def normalize_trade(self, raw_trade: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalize FMP trade to common format.

        FMP format example:
        {
            "firstName": "John",
            "lastName": "Doe",
            "office": "Senate",
            "link": "https://...",
            "dateRecieved": "2021-01-15",
            "transactionDate": "2021-01-01",
            "owner": "Self",
            "ticker": "AAPL",
            "assetDescription": "Apple Inc.",
            "assetType": "Stock",
            "type": "Purchase",
            "amount": "$1,001 - $15,000",
            "comment": null
        }
        """
        # Build member name
        first_name = raw_trade.get("firstName", "")
        last_name = raw_trade.get("lastName", "")
        member_name = f"{first_name} {last_name}".strip() or None

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
        trade_date = self._parse_date(raw_trade.get("transactionDate"))
        disclosure_date = self._parse_date(raw_trade.get("dateRecieved"))

        # Parse owner
        owner = self._normalize_owner(raw_trade.get("owner", ""))

        return {
            "source": self.get_name(),
            "member_name": member_name,
            "member_id": None,  # FMP doesn't provide member ID
            "ticker": raw_trade.get("ticker", "").upper(),
            "asset_description": raw_trade.get("assetDescription"),
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

        FMP uses: "Self", "Spouse", "Child", "Joint", etc.
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
        Check if FMP is available and configured.

        Returns False if using dummy API key.
        """
        if self.api_key == "DUMMY_FMP_API_KEY_REPLACE_ME":
            logger.debug("FMP not available: using dummy API key")
            return False

        try:
            # Quick health check - try to fetch with limit=1
            url = f"{self.BASE_URL}/senate-trading"
            params = {"apikey": self.api_key, "limit": 1}

            response = self._session.get(url, params=params, timeout=5)
            return response.status_code == 200
        except requests.RequestException:
            return False

    def get_rate_limit_info(self) -> Dict[str, Any]:
        """
        Return rate limit information for FMP free tier.

        Free tier: 250 requests/day
        """
        return {
            "source": self.get_name(),
            "limit_per_day": 250,
            "limit_per_minute": None,
            "requires_auth": True,
            "cost": "free",
            "upgrade_url": "https://financialmodelingprep.com/pricing",
        }
