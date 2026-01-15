"""
CapitolTrades data source implementation.

CapitolTrades.com aggregates congressional trading data from official STOCK Act
disclosures and makes it publicly available. This source requires web scraping.

IMPORTANT NOTES:
- Respect CapitolTrades.com rate limits and terms of service
- Implement caching to minimize requests (1-hour TTL recommended)
- Add delays between requests (2-3 seconds minimum)
- Use proper User-Agent headers
- Consider supporting CapitolTrades if using heavily

Data Coverage: Both House and Senate, ~500 most recent trades by default
Update Frequency: Daily (45-day disclosure lag per STOCK Act)
Cost: Free (public data)
"""

import time
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

import requests
from loguru import logger

from app.data_sources.base import CongressDataSource


class CapitolTradesSource(CongressDataSource):
    """
    CapitolTrades.com data source client.

    Features:
    - Aggregated congressional trading data (House + Senate)
    - ~500 most recent trades (2-3 weeks)
    - Public data from STOCK Act disclosures
    - Requires web scraping (no official API)

    Ethical Scraping:
    - 1-hour cache TTL (avoid repeated requests)
    - 2-3 second delays between requests
    - Proper User-Agent identification
    - Respects robots.txt

    Rate Limits:
    - Self-imposed: Max 1 request per minute
    - Cache TTL: 1 hour (as used by congress-cli)
    - Daily reasonable use: < 50 requests/day
    """

    BASE_URL = "https://www.capitoltrades.com"
    TRADES_ENDPOINT = "/trades"

    # Cache settings (following congress-cli pattern)
    CACHE_TTL_SECONDS = 3600  # 1 hour
    REQUEST_DELAY_SECONDS = 3  # 3 seconds between requests

    def __init__(self, timeout: int = 30, use_cache: bool = True):
        """
        Initialize CapitolTrades client.

        Args:
            timeout: Request timeout in seconds
            use_cache: Enable response caching (default: True)
        """
        self.timeout = timeout
        self.use_cache = use_cache
        self._cache: Dict[str, Any] = {}
        self._last_request_time: Optional[datetime] = None

        self._session = requests.Session()
        self._session.headers.update(
            {
                "User-Agent": (
                    "Congress-Trade-Tracker/1.0 "
                    "(Educational/Research; "
                    "github.com/lushl9301/Congress-Trade-Tracker)"
                ),
                "Accept": "text/html,application/json",
                "Accept-Language": "en-US,en;q=0.9",
            }
        )

        logger.info("CapitolTrades source initialized with caching and rate limiting")

    def get_name(self) -> str:
        """Return source name."""
        return "capitol_trades"

    def get_trades(
        self,
        symbol: Optional[str] = None,
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
    ) -> List[Dict[str, Any]]:
        """
        Fetch congressional trades from CapitolTrades.

        NOTE: This is a placeholder implementation. Actual scraping requires:
        1. Playwright or Selenium for JavaScript rendering
        2. Proper HTML parsing (BeautifulSoup/lxml)
        3. Pagination handling
        4. Anti-bot detection handling

        For production use, consider:
        - Using congress-cli as a library
        - Implementing proper scraping with Playwright
        - Adding proxy rotation if needed

        Args:
            symbol: Filter by ticker symbol (optional)
            from_date: Start date for trades (optional)
            to_date: End date for trades (optional)

        Returns:
            List of raw trade records

        Raises:
            NotImplementedError: Full scraping implementation required
        """
        logger.warning(
            "CapitolTrades source requires full scraping implementation. "
            "Consider using congress-cli library or implementing Playwright scraper."
        )

        # Check cache first
        cache_key = f"trades_{symbol}_{from_date}_{to_date}"
        if self.use_cache and cache_key in self._cache:
            cached_data, cached_time = self._cache[cache_key]
            age_seconds = (datetime.now() - cached_time).total_seconds()

            if age_seconds < self.CACHE_TTL_SECONDS:
                logger.info(
                    f"Using cached data (age: {age_seconds:.0f}s / "
                    f"{self.CACHE_TTL_SECONDS}s TTL)"
                )
                return cached_data

        # Rate limiting
        self._enforce_rate_limit()

        # TODO: Implement actual scraping
        # Options:
        # 1. Use Playwright: playwright.sync_api.sync_playwright()
        # 2. Use Selenium: webdriver.Chrome()
        # 3. Integrate congress-cli as library
        # 4. Parse HTML with BeautifulSoup

        raise NotImplementedError(
            "CapitolTrades scraping not yet implemented. "
            "To enable:\n"
            "1. Install Playwright: pip install playwright && "
            "python -m playwright install chromium\n"
            "2. Implement HTML parsing in this method\n"
            "3. Or use congress-cli: pip install congress-cli\n"
            "\n"
            "For now, use HSW or FMP sources which have official APIs."
        )

    def _enforce_rate_limit(self) -> None:
        """Enforce rate limiting between requests."""
        if self._last_request_time is not None:
            elapsed = (datetime.now() - self._last_request_time).total_seconds()
            if elapsed < self.REQUEST_DELAY_SECONDS:
                sleep_time = self.REQUEST_DELAY_SECONDS - elapsed
                logger.debug(f"Rate limiting: sleeping {sleep_time:.1f}s")
                time.sleep(sleep_time)

        self._last_request_time = datetime.now()

    def normalize_trade(self, raw_trade: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalize CapitolTrades trade to common format.

        Expected raw_trade format (based on congress-cli):
        {
            "politician": "Hon. John Doe",
            "chamber": "House",  # or "Senate"
            "party": "Republican",
            "ticker": "AAPL",
            "asset_description": "Apple Inc. - Common Stock",
            "transaction_type": "Purchase",  # or "Sale"
            "transaction_date": "2024-01-10",
            "disclosure_date": "2024-01-15",
            "amount": "$15,001 - $50,000",
            "owner": "Spouse",  # or "Self", "Joint", "Dependent"
        }
        """
        # Parse transaction type
        raw_type = raw_trade.get("transaction_type", "").lower()
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

        # Parse owner
        owner = self._normalize_owner(raw_trade.get("owner", ""))

        return {
            "source": self.get_name(),
            "member_name": raw_trade.get("politician"),
            "member_id": None,  # CapitolTrades doesn't provide member ID
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

    def _parse_amount_range(
        self, amount_str: str
    ) -> tuple[Optional[float], Optional[float]]:
        """
        Parse amount range string to (low, high) tuple.

        Examples:
            "$1,001 - $15,000" -> (1001.0, 15000.0)
            "$15,001 - $50,000" -> (15001.0, 50000.0)
            "$1,000,001 - $5,000,000" -> (1000001.0, 5000000.0)
        """
        if not amount_str or amount_str in ["N/A", "Unknown"]:
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

        # Try multiple date formats
        formats = ["%Y-%m-%d", "%m/%d/%Y", "%m-%d-%Y"]

        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt).date()
            except (ValueError, TypeError):
                continue

        return None

    def _normalize_owner(self, owner_str: str) -> str:
        """
        Normalize owner field.

        CapitolTrades uses: "Self", "Spouse", "Joint", "Dependent", etc.
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
        Check if CapitolTrades is available.

        Returns False until full scraping is implemented.
        """
        logger.debug(
            "CapitolTrades source not yet fully implemented - returning False"
        )
        return False

    def get_rate_limit_info(self) -> Dict[str, Any]:
        """
        Return rate limit information for CapitolTrades.

        Self-imposed limits for ethical scraping.
        """
        return {
            "source": self.get_name(),
            "limit_per_day": 50,  # Self-imposed
            "limit_per_minute": 1,  # Self-imposed
            "requires_auth": False,
            "cost": "free",
            "cache_ttl_seconds": self.CACHE_TTL_SECONDS,
            "request_delay_seconds": self.REQUEST_DELAY_SECONDS,
            "note": (
                "CapitolTrades provides public data. "
                "Please use responsibly and consider supporting them."
            ),
        }

    def health_check(self) -> Dict[str, Any]:
        """
        Perform health check.

        Returns not available until full implementation.
        """
        return {
            "source": self.get_name(),
            "available": False,
            "error": "Full scraping implementation required. See docstring for details.",
            "implementation_status": "placeholder",
            "recommended_approach": "Use congress-cli library or implement Playwright scraper",
        }
