"""
CapitolTrades data source implementation.

CapitolTrades.com aggregates congressional trading data from official STOCK Act
disclosures. This implementation uses Playwright for web scraping.

Based on: https://github.com/austron24/congress-cli

SETUP REQUIRED:
    pip install playwright beautifulsoup4 lxml
    python -m playwright install chromium

Data Coverage: Both House and Senate, ~500 most recent trades
Update Frequency: Daily (45-day disclosure lag per STOCK Act)
Cost: Free (public data)
"""

import json
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger

from app.data_sources.base import CongressDataSource


class CapitolTradesSource(CongressDataSource):
    """
    CapitolTrades.com data source client using Playwright scraping.

    Features:
    - Aggregated congressional trading data (House + Senate)
    - ~500 most recent trades per scrape
    - Pagination support (URL-based: page=N)
    - 1-hour cache TTL
    - Ethical scraping with delays

    Scraping Guidelines:
    - 1.5 second delay between page loads
    - Self-imposed limit: ~50 requests/day
    - Caches results for 1 hour
    - Uses realistic User-Agent
    """

    BASE_URL = "https://www.capitoltrades.com"
    TRADES_ENDPOINT = "/trades"

    # Cache settings
    CACHE_TTL_SECONDS = 3600  # 1 hour
    CACHE_DIR = Path("./data/cache")

    # Scraping settings
    PAGE_DELAY_SECONDS = 1.5  # Delay between pages
    MAX_TRADES = 500  # Maximum trades to fetch
    MAX_PAGES = 50  # Maximum pages to scrape

    def __init__(
        self,
        timeout: int = 30000,
        use_cache: bool = True,
        headless: bool = True,
    ):
        """
        Initialize CapitolTrades client.

        Args:
            timeout: Page load timeout in milliseconds (default: 30000)
            use_cache: Enable response caching (default: True)
            headless: Run browser in headless mode (default: True)
        """
        self.timeout = timeout
        self.use_cache = use_cache
        self.headless = headless

        # Ensure cache directory exists
        if self.use_cache:
            self.CACHE_DIR.mkdir(parents=True, exist_ok=True)

        logger.info(
            f"CapitolTrades source initialized (headless={headless}, "
            f"cache={use_cache})"
        )

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

        Args:
            symbol: Filter by ticker symbol (optional, applied after fetching)
            from_date: Start date for trades (optional, applied after fetching)
            to_date: End date for trades (optional, applied after fetching)

        Returns:
            List of raw trade records (only trades with valid tickers)

        Raises:
            RuntimeError: If Playwright is not installed
            Exception: If scraping fails
        """
        # Check for Playwright
        if not self._check_playwright():
            raise RuntimeError(
                "Playwright not installed. Run:\n"
                "  pip install playwright\n"
                "  python -m playwright install chromium"
            )

        # Try cache first
        if self.use_cache:
            cached_trades = self._load_cache()
            if cached_trades is not None:
                logger.info(
                    f"Using cached CapitolTrades data ({len(cached_trades)} trades)"
                )
                return self._filter_trades(cached_trades, symbol, from_date, to_date)

        # Scrape fresh data
        logger.info("Scraping CapitolTrades.com (this may take 30-60 seconds)...")
        raw_trades = self._scrape_trades()

        # Filter out trades without valid tickers
        trades_with_tickers = [t for t in raw_trades if t.get("ticker")]
        if len(raw_trades) > len(trades_with_tickers):
            skipped = len(raw_trades) - len(trades_with_tickers)
            logger.info(
                f"Filtered out {skipped} trades without valid ticker symbols "
                f"(mutual funds, bonds, etc.)"
            )

        # Cache the results
        if self.use_cache and trades_with_tickers:
            self._save_cache(trades_with_tickers)

        logger.info(f"Fetched {len(trades_with_tickers)} trades from CapitolTrades")

        # Apply filters
        return self._filter_trades(trades_with_tickers, symbol, from_date, to_date)

    def _check_playwright(self) -> bool:
        """Check if Playwright is installed and available."""
        try:
            from playwright.sync_api import sync_playwright  # noqa: F401

            return True
        except ImportError:
            return False

    def _scrape_trades(self) -> List[Dict[str, Any]]:
        """
        Scrape trades using Playwright.

        Returns:
            List of raw trade dictionaries
        """
        from playwright.sync_api import sync_playwright

        trades = []
        pages_scraped = 0

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=self.headless)
                context = browser.new_context(
                    user_agent=(
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36"
                    )
                )
                page = context.new_page()

                current_page = 1

                while len(trades) < self.MAX_TRADES and pages_scraped < self.MAX_PAGES:
                    # Navigate to trades page
                    url = f"{self.BASE_URL}{self.TRADES_ENDPOINT}?page={current_page}"
                    logger.debug(f"Scraping page {current_page}: {url}")

                    page.goto(url, timeout=self.timeout)

                    try:
                        page.wait_for_selector("table tbody tr", timeout=self.timeout)
                    except Exception:
                        logger.debug(f"No table rows found on page {current_page}")
                        break

                    # Allow React to fully render
                    time.sleep(self.PAGE_DELAY_SECONDS)

                    # Parse the page
                    page_trades = self._parse_table_rows(page)

                    if not page_trades:
                        logger.debug(f"No trades parsed from page {current_page}")
                        break

                    trades.extend(page_trades)
                    pages_scraped += 1
                    current_page += 1

                    logger.debug(
                        f"Page {pages_scraped}: +{len(page_trades)} trades "
                        f"(total: {len(trades)})"
                    )

                browser.close()

            # Deduplicate
            trades = self._deduplicate_trades(trades)[:self.MAX_TRADES]

            logger.info(
                f"Scraped {len(trades)} unique trades from {pages_scraped} pages"
            )
            return trades

        except Exception as e:
            logger.error(f"Scraping failed: {e}")
            raise

    def _parse_table_rows(self, page) -> List[Dict[str, Any]]:
        """
        Parse trade rows from current page.

        Args:
            page: Playwright page object

        Returns:
            List of trade dictionaries
        """
        trades = []

        # Find table rows
        rows = page.query_selector_all("table tbody tr")

        if not rows:
            rows = page.query_selector_all("[data-testid='trade-row']")

        if not rows:
            rows = page.query_selector_all(".trade-row, .MuiTableRow-root")

        for row in rows:
            try:
                cells = row.query_selector_all("td")

                if len(cells) < 8:
                    continue

                # Capitol Trades table structure:
                # 0: Member (name\nPartyChState)
                # 1: Issuer (company\nTICKER:US)
                # 2: Filed date (DD Mon\nYYYY)
                # 3: Traded date (DD Mon\nYYYY)
                # 4: Days (days\nN)
                # 5: Owner (Self/Spouse/etc)
                # 6: Type (BUY/SELL)
                # 7: Size (1K-15K)

                cell_texts = [cell.inner_text().strip() for cell in cells]

                member_name, chamber, party = self._parse_member_info(cell_texts[0])
                asset_description, ticker = self._parse_ticker(cell_texts[1])
                filed_date = self._parse_date(cell_texts[2])
                traded_date = self._parse_date(cell_texts[3])
                owner = cell_texts[5].lower() if len(cell_texts) > 5 else "unknown"
                tx_type_str = cell_texts[6] if len(cell_texts) > 6 else ""
                tx_type = self._parse_transaction_type(tx_type_str)
                amount_str = cell_texts[7] if len(cell_texts) > 7 else ""

                trade = {
                    "politician": member_name,
                    "chamber": chamber,
                    "party": party,
                    "ticker": ticker,
                    "asset_description": asset_description,
                    "transaction_type": tx_type,
                    "transaction_date": traded_date.isoformat() if traded_date else None,
                    "disclosure_date": filed_date.isoformat() if filed_date else None,
                    "amount": amount_str,
                    "owner": owner,
                }
                trades.append(trade)

            except Exception as e:
                logger.debug(f"Failed to parse row: {e}")
                continue

        return trades

    def _parse_member_info(self, member_cell: str) -> tuple[str, str, Optional[str]]:
        """
        Parse member name, chamber, and party.

        Format: 'Ed Case\nDemocratHouseHI'
        Returns: (member_name, chamber, party)
        """
        if not member_cell:
            return ("Unknown", "unknown", None)

        lines = member_cell.split("\n")
        member_name = lines[0].strip() if lines else "Unknown"

        chamber = "unknown"
        party = None
        if len(lines) > 1:
            info = lines[1]
            if "House" in info:
                chamber = "house"
            elif "Senate" in info:
                chamber = "senate"

            if info.startswith("Democrat"):
                party = "D"
            elif info.startswith("Republican"):
                party = "R"
            elif info.startswith("Independent"):
                party = "I"

        return (member_name, chamber, party)

    def _parse_ticker(self, issuer_cell: str) -> tuple[str, Optional[str]]:
        """
        Parse asset description and ticker.

        Format: 'The Procter & Gamble Co\nPG:US'
        Returns: (asset_description, ticker)
        """
        if not issuer_cell:
            return ("Unknown", None)

        lines = issuer_cell.split("\n")
        asset_description = lines[0].strip() if lines else issuer_cell

        ticker = None
        if len(lines) > 1:
            ticker_line = lines[1].strip()
            if ":" in ticker_line:
                ticker = ticker_line.split(":")[0]
            else:
                ticker = ticker_line

            if ticker and ticker.upper() in ("N/A", "NA", "--", ""):
                ticker = None

        return (asset_description, ticker)

    def _parse_transaction_type(self, tx_type: str) -> str:
        """Parse transaction type."""
        tx_lower = tx_type.lower().strip()
        if "buy" in tx_lower or "purchase" in tx_lower:
            return "Purchase"
        elif "sell" in tx_lower or "sale" in tx_lower:
            return "Sale"
        elif "exchange" in tx_lower:
            return "Exchange"
        return "Unknown"

    def _parse_date(self, date_str: str) -> Optional[date]:
        """
        Parse date from Capitol Trades format.

        Format: '25 Dec\n2025'
        """
        if not date_str:
            return None

        # Clean up the string
        date_str = date_str.strip().replace("\n", " ")

        formats = [
            "%d %b %Y",       # 25 Dec 2025
            "%b %d, %Y",      # Dec 25, 2025
            "%B %d, %Y",      # December 25, 2025
            "%Y-%m-%d",       # 2025-12-25
            "%m/%d/%Y",       # 12/25/2025
        ]

        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt).date()
            except ValueError:
                continue

        return None

    def _deduplicate_trades(self, trades: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Remove duplicate trades."""
        seen = set()
        unique = []

        for trade in trades:
            key = (
                trade.get("politician"),
                trade.get("ticker"),
                trade.get("disclosure_date"),
                trade.get("transaction_date"),
                trade.get("amount"),
            )
            if key not in seen:
                seen.add(key)
                unique.append(trade)

        return unique

    def _filter_trades(
        self,
        trades: List[Dict[str, Any]],
        symbol: Optional[str],
        from_date: Optional[date],
        to_date: Optional[date],
    ) -> List[Dict[str, Any]]:
        """Apply client-side filters."""
        filtered = trades

        if symbol:
            symbol_upper = symbol.upper()
            filtered = [
                t for t in filtered
                if t.get("ticker", "").upper() == symbol_upper
            ]

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
        to_date: Optional[date],
    ) -> bool:
        """Check if trade falls within date range."""
        trade_date_str = trade.get("transaction_date") or trade.get("disclosure_date")
        if not trade_date_str:
            return True

        try:
            trade_date = datetime.fromisoformat(trade_date_str).date()

            if from_date and trade_date < from_date:
                return False
            if to_date and trade_date > to_date:
                return False

            return True
        except (ValueError, TypeError):
            return True

    def _save_cache(self, trades: List[Dict[str, Any]]) -> None:
        """Save trades to cache."""
        cache_file = self.CACHE_DIR / "capitol_trades_cache.json"

        cache_data = {
            "scraped_at": datetime.now().isoformat(),
            "trades": trades,
        }

        try:
            with open(cache_file, "w") as f:
                json.dump(cache_data, f, default=str)
            logger.debug(f"Saved {len(trades)} trades to cache")
        except Exception as e:
            logger.warning(f"Failed to save cache: {e}")

    def _load_cache(self) -> Optional[List[Dict[str, Any]]]:
        """Load trades from cache if fresh."""
        cache_file = self.CACHE_DIR / "capitol_trades_cache.json"

        if not cache_file.exists():
            return None

        # Check cache age
        cache_age = time.time() - cache_file.stat().st_mtime
        if cache_age > self.CACHE_TTL_SECONDS:
            logger.debug(f"Cache expired (age: {cache_age:.0f}s)")
            return None

        try:
            with open(cache_file) as f:
                data = json.load(f)

            trades = data.get("trades", [])
            logger.debug(
                f"Cache hit (age: {cache_age:.0f}s / {self.CACHE_TTL_SECONDS}s TTL)"
            )
            return trades
        except Exception as e:
            logger.warning(f"Failed to load cache: {e}")
            return None

    def normalize_trade(self, raw_trade: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalize CapitolTrades trade to common format.

        Args:
            raw_trade: Raw trade from scraping

        Returns:
            Normalized trade dictionary
        """
        # Parse transaction type
        raw_type = raw_trade.get("transaction_type", "").lower()
        if "purchase" in raw_type or "buy" in raw_type:
            transaction_type = "BUY"
        elif "sale" in raw_type or "sell" in raw_type:
            transaction_type = "SELL"
        else:
            transaction_type = "OTHER"

        # Parse amount range (Capitol Trades uses "1K-15K" format)
        amount_low, amount_high = self._parse_amount_range(
            raw_trade.get("amount", "")
        )

        # Parse dates
        trade_date = None
        if raw_trade.get("transaction_date"):
            try:
                trade_date = datetime.fromisoformat(
                    raw_trade["transaction_date"]
                ).date()
            except (ValueError, TypeError):
                pass

        disclosure_date = None
        if raw_trade.get("disclosure_date"):
            try:
                disclosure_date = datetime.fromisoformat(
                    raw_trade["disclosure_date"]
                ).date()
            except (ValueError, TypeError):
                pass

        # Parse owner
        owner = self._normalize_owner(raw_trade.get("owner", ""))

        return {
            "source": self.get_name(),
            "member_name": raw_trade.get("politician"),
            "member_id": None,
            "ticker": raw_trade.get("ticker", "").upper() if raw_trade.get("ticker") else None,
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
        Parse Capitol Trades amount format.

        Examples:
            "1K-15K" -> (1000.0, 15000.0)
            "15K-50K" -> (15000.0, 50000.0)
            "1M-5M" -> (1000000.0, 5000000.0)
        """
        if not amount_str or amount_str in ["N/A", "Unknown"]:
            return None, None

        try:
            # Handle various dash types
            for dash in ["–", "—", "-"]:
                if dash in amount_str:
                    parts = amount_str.split(dash)
                    if len(parts) == 2:
                        low = self._parse_amount_value(parts[0].strip())
                        high = self._parse_amount_value(parts[1].strip())
                        if low and high:
                            return low, high
                    break

            # Single value
            value = self._parse_amount_value(amount_str)
            if value:
                return value, value

        except (ValueError, AttributeError):
            pass

        return None, None

    def _parse_amount_value(self, value_str: str) -> Optional[float]:
        """Parse a single amount value like '1K', '15K', '1M'."""
        if not value_str:
            return None

        value = value_str.strip().upper().replace("$", "").replace(",", "").replace("+", "")

        try:
            if value.endswith("K"):
                return float(value[:-1]) * 1000
            elif value.endswith("M"):
                return float(value[:-1]) * 1000000
            else:
                return float(value)
        except (ValueError, TypeError):
            return None

    def _normalize_owner(self, owner_str: str) -> str:
        """
        Normalize owner field.

        Maps to: "member", "spouse", "dependent", "unknown"
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
        """Check if CapitolTrades is available."""
        return self._check_playwright()

    def get_rate_limit_info(self) -> Dict[str, Any]:
        """Return rate limit information."""
        return {
            "source": self.get_name(),
            "limit_per_day": 50,  # Self-imposed
            "limit_per_minute": None,
            "requires_auth": False,
            "cost": "free",
            "cache_ttl_seconds": self.CACHE_TTL_SECONDS,
            "page_delay_seconds": self.PAGE_DELAY_SECONDS,
            "max_trades_per_scrape": self.MAX_TRADES,
            "note": "Uses Playwright for web scraping. Requires: python -m playwright install chromium",
        }

    def health_check(self) -> Dict[str, Any]:
        """Perform health check."""
        playwright_available = self._check_playwright()

        if not playwright_available:
            return {
                "source": self.get_name(),
                "available": False,
                "error": "Playwright not installed",
                "fix": (
                    "pip install playwright && "
                    "python -m playwright install chromium"
                ),
            }

        return {
            "source": self.get_name(),
            "available": True,
            "error": None,
            "cache_enabled": self.use_cache,
            "headless_mode": self.headless,
        }
