"""
Market data provider for real-time stock prices.

Uses Yahoo Finance (yfinance) for delayed price data (~15-20 minutes).
Sufficient for congressional trading strategy (not high-frequency).
"""

import time
from datetime import datetime
from typing import Dict, List, Optional

from app.config import config
from app.logging import get_logger

logger = get_logger(__name__)


class MarketDataProvider:
    """
    Fetch real-time stock prices using Yahoo Finance.

    Features:
    - Price caching (configurable TTL)
    - Batch price fetching for efficiency
    - Error handling for unavailable tickers
    - Free, unlimited requests
    - 15-20 minute delayed data
    """

    def __init__(self, cache_ttl_seconds: Optional[int] = None):
        """
        Initialize market data provider.

        Args:
            cache_ttl_seconds: Cache prices for N seconds (default from config)
        """
        self.cache_ttl = cache_ttl_seconds or config.PRICE_CACHE_TTL_SECONDS
        self.cache: Dict[str, tuple[float, float]] = {}  # {ticker: (price, timestamp)}

        # Import yfinance (lazy import to avoid dependency issues)
        try:
            import yfinance as yf

            self.yf = yf
            logger.info("MarketDataProvider initialized with yfinance")
        except ImportError:
            logger.error(
                "yfinance not installed. Install with: pip install yfinance pandas"
            )
            raise RuntimeError(
                "yfinance required for market data. Install with: pip install yfinance pandas"
            )

    def get_price(self, ticker: str) -> Optional[float]:
        """
        Get current price for a ticker.

        Args:
            ticker: Stock symbol (e.g., "AAPL", "NVDA")

        Returns:
            Current price or None if unavailable
        """
        # Normalize ticker
        ticker = ticker.upper().strip()

        # Check cache
        if ticker in self.cache:
            price, cached_at = self.cache[ticker]
            age = time.time() - cached_at
            if age < self.cache_ttl:
                logger.debug(f"Cache hit for {ticker}: ${price:.2f} (age: {age:.0f}s)")
                return price

        # Fetch fresh price
        try:
            stock = self.yf.Ticker(ticker)
            info = stock.info

            # Try multiple price fields (in order of preference)
            price = (
                info.get("currentPrice")
                or info.get("regularMarketPrice")
                or info.get("previousClose")
            )

            if price and price > 0:
                self.cache[ticker] = (price, time.time())
                logger.debug(f"Fetched price for {ticker}: ${price:.2f}")
                return price
            else:
                logger.warning(f"No valid price found for {ticker}")
                return None

        except Exception as e:
            logger.warning(f"Failed to fetch price for {ticker}: {e}")
            return None

    def get_prices_batch(
        self, tickers: List[str], use_cache: bool = True
    ) -> Dict[str, Optional[float]]:
        """
        Get prices for multiple tickers efficiently.

        Uses batch fetching for better performance.

        Args:
            tickers: List of stock symbols
            use_cache: Whether to use cached prices (default True)

        Returns:
            Dictionary mapping ticker to price (or None if unavailable)
        """
        if not tickers:
            return {}

        # Normalize tickers
        tickers = [t.upper().strip() for t in tickers]
        prices = {}

        # If using cache, check cache first
        uncached_tickers = tickers
        if use_cache:
            uncached_tickers = []
            for ticker in tickers:
                if ticker in self.cache:
                    price, cached_at = self.cache[ticker]
                    age = time.time() - cached_at
                    if age < self.cache_ttl:
                        prices[ticker] = price
                        continue
                uncached_tickers.append(ticker)

        # If all cached, return
        if not uncached_tickers:
            logger.debug(
                f"All {len(tickers)} tickers cached (TTL: {self.cache_ttl}s)"
            )
            return prices

        # Fetch uncached tickers
        logger.info(
            f"Fetching prices for {len(uncached_tickers)} tickers "
            f"({len(tickers) - len(uncached_tickers)} cached)"
        )

        try:
            # Import pandas (required by yfinance)
            import pandas as pd

            # Use yfinance download for batch fetching
            if len(uncached_tickers) == 1:
                # Single ticker
                ticker = uncached_tickers[0]
                try:
                    data = self.yf.download(
                        ticker, period="1d", progress=False, show_errors=False
                    )
                    if not data.empty and "Close" in data.columns:
                        price = float(data["Close"].iloc[-1])
                        if price > 0:
                            prices[ticker] = price
                            self.cache[ticker] = (price, time.time())
                        else:
                            prices[ticker] = None
                    else:
                        prices[ticker] = None
                except Exception as e:
                    logger.warning(f"Failed to fetch {ticker}: {e}")
                    prices[ticker] = None

            else:
                # Multiple tickers - batch fetch
                data = self.yf.download(
                    uncached_tickers, period="1d", progress=False, show_errors=False
                )

                if not data.empty:
                    # Handle multi-ticker response
                    if "Close" in data.columns:
                        # DataFrame structure depends on number of tickers
                        for ticker in uncached_tickers:
                            try:
                                if len(uncached_tickers) == 1:
                                    price = float(data["Close"].iloc[-1])
                                else:
                                    price = float(data["Close"][ticker].iloc[-1])

                                if pd.isna(price) or price <= 0:
                                    prices[ticker] = None
                                else:
                                    prices[ticker] = price
                                    self.cache[ticker] = (price, time.time())

                            except (KeyError, IndexError, ValueError) as e:
                                logger.debug(
                                    f"Price not available for {ticker}: {e}"
                                )
                                prices[ticker] = None

        except Exception as e:
            logger.error(f"Batch price fetch failed: {e}")
            # Fallback to individual fetches
            for ticker in uncached_tickers:
                if ticker not in prices:
                    prices[ticker] = self.get_price(ticker)

        # Ensure all tickers have an entry (even if None)
        for ticker in tickers:
            if ticker not in prices:
                prices[ticker] = None

        return prices

    def clear_cache(self):
        """Clear price cache."""
        cleared_count = len(self.cache)
        self.cache.clear()
        logger.info(f"Cleared price cache ({cleared_count} entries)")

    def get_cache_stats(self) -> Dict:
        """
        Get cache statistics.

        Returns:
            Dictionary with cache stats
        """
        now = time.time()
        fresh_count = 0
        stale_count = 0

        for ticker, (price, cached_at) in self.cache.items():
            age = now - cached_at
            if age < self.cache_ttl:
                fresh_count += 1
            else:
                stale_count += 1

        return {
            "total_entries": len(self.cache),
            "fresh_entries": fresh_count,
            "stale_entries": stale_count,
            "cache_ttl_seconds": self.cache_ttl,
        }


# Global instance
_market_data_provider = None


def get_market_data_provider() -> MarketDataProvider:
    """
    Get singleton market data provider instance.

    Returns:
        MarketDataProvider instance
    """
    global _market_data_provider
    if _market_data_provider is None:
        _market_data_provider = MarketDataProvider()
    return _market_data_provider
