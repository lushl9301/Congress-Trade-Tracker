"""
Finnhub API client for fetching congressional trading data.
Uses the free tier congressional trading endpoint.
"""

from datetime import date, datetime
from typing import Any

import requests

from app.config import config
from app.logging import get_logger

logger = get_logger(__name__)


class FinnhubClient:
    """Client for interacting with Finnhub API."""

    def __init__(self, api_key: str | None = None):
        """
        Initialize Finnhub client.

        Args:
            api_key: Finnhub API key. If None, uses config.FINNHUB_API_KEY
        """
        self.api_key = api_key or config.FINNHUB_API_KEY
        self.base_url = config.FINNHUB_BASE_URL

        if not self.api_key:
            raise ValueError("FINNHUB_API_KEY is required")

        self.session = requests.Session()
        self.session.headers.update({"X-Finnhub-Token": self.api_key})

    def get_congress_trading(
        self,
        symbol: str | None = None,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Fetch congressional trading data from Finnhub.

        API endpoint: https://finnhub.io/api/v1/stock/congress-trading

        Args:
            symbol: Stock symbol to filter by (optional)
            from_date: Start date in YYYY-MM-DD format (optional)
            to_date: End date in YYYY-MM-DD format (optional)

        Returns:
            List of congressional trading records

        Example response format:
        [
            {
                "symbol": "HAL",
                "name": "Halliburton Company",
                "transactionDate": "2021-01-01",
                "transactionType": "Purchase",
                "representativeName": "John Doe",
                "representativeDistrict": "TX-01",
                "amount": "$1,001 - $15,000",
                "filingDate": "2021-01-15",
                "link": "https://..."
            },
            ...
        ]
        """
        endpoint = f"{self.base_url}/stock/congress-trading"

        params = {}
        if symbol:
            params["symbol"] = symbol.upper()
        if from_date:
            params["from"] = from_date
        if to_date:
            params["to"] = to_date

        try:
            logger.info(f"Fetching congress trading data: {params}")
            response = self.session.get(endpoint, params=params, timeout=30)
            response.raise_for_status()

            data = response.json()

            # Finnhub returns data in a 'data' field
            if isinstance(data, dict) and "data" in data:
                records = data["data"]
            elif isinstance(data, list):
                records = data
            else:
                logger.warning(f"Unexpected response format: {type(data)}")
                records = []

            logger.info(f"Fetched {len(records)} congressional trading records")
            return records

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to fetch congress trading data: {e}")
            raise

    def parse_amount_range(self, amount_str: str) -> tuple[float | None, float | None]:
        """
        Parse amount string from Finnhub into (low, high) tuple.

        Examples:
            "$1,001 - $15,000" -> (1001, 15000)
            "$50,001 - $100,000" -> (50001, 100000)
            "$1,000,001 - $5,000,000" -> (1000001, 5000000)
            "Over $50,000,000" -> (50000000, None)

        Args:
            amount_str: Amount range string from Finnhub

        Returns:
            Tuple of (amount_low, amount_high)
        """
        if not amount_str:
            return None, None

        try:
            # Remove dollar signs and commas
            amount_str = amount_str.replace("$", "").replace(",", "")

            # Handle "Over X" format
            if amount_str.lower().startswith("over "):
                value = float(amount_str.lower().replace("over ", "").strip())
                return value, None

            # Handle "X - Y" format
            if " - " in amount_str:
                parts = amount_str.split(" - ")
                if len(parts) == 2:
                    low = float(parts[0].strip())
                    high = float(parts[1].strip())
                    return low, high

            # Try to parse as single number
            value = float(amount_str.strip())
            return value, value

        except (ValueError, AttributeError) as e:
            logger.warning(f"Failed to parse amount '{amount_str}': {e}")
            return None, None

    def parse_transaction_type(self, transaction_type: str) -> str:
        """
        Normalize transaction type to BUY, SELL, or OTHER.

        Args:
            transaction_type: Transaction type string from Finnhub

        Returns:
            Normalized transaction type
        """
        if not transaction_type:
            return "OTHER"

        tx_lower = transaction_type.lower()

        if "purchase" in tx_lower or "buy" in tx_lower:
            return "BUY"
        elif "sale" in tx_lower or "sell" in tx_lower:
            return "SELL"
        else:
            return "OTHER"

    def parse_date(self, date_str: str | None) -> date | None:
        """
        Parse date string to date object.

        Args:
            date_str: Date string in various formats

        Returns:
            date object or None if parsing fails
        """
        if not date_str:
            return None

        # Try common date formats
        formats = [
            "%Y-%m-%d",
            "%m/%d/%Y",
            "%d/%m/%Y",
            "%Y/%m/%d",
        ]

        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt).date()
            except ValueError:
                continue

        logger.warning(f"Failed to parse date: {date_str}")
        return None

    def infer_owner(self, record: dict[str, Any]) -> str:
        """
        Infer who made the trade based on available fields.

        Args:
            record: Raw Finnhub record

        Returns:
            Owner type: "member", "spouse", "dependent", or "unknown"
        """
        # Check if there's an owner field in the raw data
        if "owner" in record:
            owner_str = str(record["owner"]).lower()
            if "self" in owner_str or "member" in owner_str:
                return "member"
            elif "spouse" in owner_str:
                return "spouse"
            elif "child" in owner_str or "dependent" in owner_str:
                return "dependent"

        # Default to unknown
        return "unknown"

    def close(self) -> None:
        """Close the HTTP session."""
        self.session.close()
        logger.debug("Finnhub client session closed")


# Global client instance (lazy initialization)
_client: FinnhubClient | None = None


def get_finnhub_client() -> FinnhubClient:
    """Get or create global Finnhub client instance."""
    global _client
    if _client is None:
        _client = FinnhubClient()
    return _client
