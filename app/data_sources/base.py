"""
Abstract base class for congressional trading data sources.
"""

from abc import ABC, abstractmethod
from datetime import date
from typing import Any, Dict, List, Optional


class CongressDataSource(ABC):
    """Abstract base class for congressional trading data sources."""

    @abstractmethod
    def get_name(self) -> str:
        """Return source name for logging and tracking."""
        pass

    @abstractmethod
    def get_trades(
        self,
        symbol: Optional[str] = None,
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
    ) -> List[Dict[str, Any]]:
        """
        Fetch congressional trades from source.

        Args:
            symbol: Filter by ticker symbol (optional)
            from_date: Start date for trades (optional)
            to_date: End date for trades (optional)

        Returns:
            List of raw trade records from the source

        Raises:
            Exception: If fetching fails
        """
        pass

    @abstractmethod
    def normalize_trade(self, raw_trade: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalize raw trade data to common format.

        Args:
            raw_trade: Raw trade data from source

        Returns:
            Dict with standard fields:
            - source: str (source name)
            - member_name: str
            - member_id: Optional[str]
            - ticker: str
            - asset_description: Optional[str]
            - transaction_type: str (BUY/SELL/OTHER)
            - trade_date: Optional[date]
            - disclosure_date: Optional[date]
            - amount_low: Optional[float]
            - amount_high: Optional[float]
            - owner: str (member/spouse/dependent/unknown)
            - raw: Dict (original data)
        """
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check if source is available and configured."""
        pass

    @abstractmethod
    def get_rate_limit_info(self) -> Dict[str, Any]:
        """
        Return rate limit information for this source.

        Returns:
            Dict with rate limit details
        """
        pass

    def health_check(self) -> Dict[str, Any]:
        """
        Perform health check on the data source.

        Returns:
            Dict with health status
        """
        try:
            available = self.is_available()
            return {
                "source": self.get_name(),
                "available": available,
                "error": None,
            }
        except Exception as e:
            return {
                "source": self.get_name(),
                "available": False,
                "error": str(e),
            }
