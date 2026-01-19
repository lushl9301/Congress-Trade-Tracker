"""
RapidAPI Politician Trade Tracker data source implementation.

Fetches trade data via RapidAPI and normalizes to the common format.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

import requests
from loguru import logger

from app.data_sources.base import CongressDataSource


class RapidAPIPoliticianTradeTrackerSource(CongressDataSource):
    """
    RapidAPI Politician Trade Tracker client.

    API host: politician-trade-tracker1.p.rapidapi.com
    Endpoints used:
      - /get_politicians
      - /get_profile?name={politician}
    """

    DEFAULT_HOST = "politician-trade-tracker1.p.rapidapi.com"
    PROFILE_TRADE_KEY = "Trade Data"

    def __init__(
        self,
        api_key: str,
        host: str | None = None,
        profile_limit: int | None = None,
        politicians: Optional[list[str]] = None,
        timeout: int = 30,
    ):
        """
        Initialize RapidAPI client.

        Args:
            api_key: RapidAPI key (required)
            host: RapidAPI host override
            profile_limit: Optional cap on number of profiles to fetch
            politicians: Optional list of politician names to fetch
            timeout: Request timeout in seconds
        """
        self.api_key = api_key.strip() if api_key else ""
        self.host = host or self.DEFAULT_HOST
        self.base_url = f"https://{self.host}"
        self.profile_limit = profile_limit
        self.politicians = politicians or []
        self.timeout = timeout
        self._session = requests.Session()
        self._session.headers.update({"User-Agent": "Congress-Trade-Tracker/1.0"})

    def get_name(self) -> str:
        """Return source name."""
        return "rapidapi_politician_tracker"

    def get_trades(
        self,
        symbol: Optional[str] = None,
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
    ) -> List[Dict[str, Any]]:
        """
        Fetch congressional trades from RapidAPI.

        Note: RapidAPI returns trades per politician profile. This method
        iterates profiles and aggregates their trade entries.
        """
        if not self.is_available():
            raise RuntimeError("RapidAPI key not configured")

        if self.politicians:
            politicians = list(self.politicians)
        else:
            politicians = self._fetch_politicians()

        if self.profile_limit:
            politicians = politicians[: self.profile_limit]

        all_trades: list[dict[str, Any]] = []

        for name in politicians:
            try:
                profile = self._fetch_profile(name)
            except Exception as exc:
                logger.error(f"RapidAPI profile fetch failed for {name}: {exc}")
                continue

            trades = profile.get(self.PROFILE_TRADE_KEY, [])
            if not isinstance(trades, list):
                continue

            filtered = self._filter_trades(
                trades, symbol=symbol, from_date=from_date, to_date=to_date
            )
            all_trades.extend(filtered)

        logger.info(f"RapidAPI fetched {len(all_trades)} trades after filtering")
        return all_trades

    def normalize_trade(self, raw_trade: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalize RapidAPI trade to common format.

        RapidAPI format example:
        {
            "name": "Nancy Pelosi",
            "party": "Democrat",
            "chamber": "House",
            "state_abbreviation": "CA",
            "state_name": "California",
            "company": "Apple Inc",
            "ticker": "AAPL:US",
            "trade_date": "October 22, 2025",
            "days_until_disclosure": 2,
            "trade_type": "sell",
            "trade_amount": "100K-250K",
            "value_at_purchase": "$258.45"
        }
        """
        raw_type = (raw_trade.get("trade_type") or "").lower()
        if "buy" in raw_type or "purchase" in raw_type:
            transaction_type = "BUY"
        elif "sell" in raw_type or "sale" in raw_type:
            transaction_type = "SELL"
        else:
            transaction_type = "OTHER"

        amount_low, amount_high = self._parse_amount_range(
            raw_trade.get("trade_amount", "")
        )

        trade_date = self._parse_trade_date(raw_trade.get("trade_date"))
        disclosure_date = self._infer_disclosure_date(
            trade_date, raw_trade.get("days_until_disclosure")
        )

        ticker = self._extract_ticker(raw_trade.get("ticker"))

        return {
            "source": self.get_name(),
            "member_name": raw_trade.get("name"),
            "member_id": None,
            "ticker": ticker,
            "asset_description": raw_trade.get("company"),
            "transaction_type": transaction_type,
            "trade_date": trade_date,
            "disclosure_date": disclosure_date,
            "amount_low": amount_low,
            "amount_high": amount_high,
            "owner": "member",
            "raw": raw_trade,
        }

    def is_available(self) -> bool:
        """Check if RapidAPI is configured."""
        return bool(self.api_key)

    def get_rate_limit_info(self) -> Dict[str, Any]:
        """Return rate limit information (RapidAPI varies by plan)."""
        return {
            "source": self.get_name(),
            "limit_per_day": None,
            "limit_per_minute": None,
            "requires_auth": True,
            "cost": "unknown",
            "upgrade_url": "https://rapidapi.com/s5yux/api/politician-trade-tracker1",
        }

    def _fetch_politicians(self) -> list[str]:
        """Fetch politician list from RapidAPI."""
        data = self._request("/get_politicians")
        if isinstance(data, dict):
            return list(data.keys())
        return []

    def _fetch_profile(self, name: str) -> dict[str, Any]:
        """Fetch a politician profile from RapidAPI."""
        params = {"name": name}
        data = self._request("/get_profile", params=params)
        if isinstance(data, dict):
            return data
        return {}

    def _request(self, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
        """Perform an API request and return JSON."""
        headers = {
            "x-rapidapi-host": self.host,
            "x-rapidapi-key": self.api_key,
        }
        url = f"{self.base_url}{path}"
        response = self._session.get(
            url, params=params, headers=headers, timeout=self.timeout
        )

        if response.status_code == 401:
            raise RuntimeError("RapidAPI request unauthorized (401)")
        if response.status_code == 403:
            raise RuntimeError("RapidAPI request forbidden (403)")
        if response.status_code == 429:
            raise RuntimeError("RapidAPI rate limit exceeded (429)")

        response.raise_for_status()
        return response.json()

    def _filter_trades(
        self,
        trades: List[Dict[str, Any]],
        symbol: Optional[str],
        from_date: Optional[date],
        to_date: Optional[date],
    ) -> List[Dict[str, Any]]:
        """Apply client-side filters to trades."""
        filtered = trades

        if symbol:
            symbol_upper = symbol.upper()
            filtered = [
                t
                for t in filtered
                if self._extract_ticker(t.get("ticker")) == symbol_upper
            ]

        if from_date or to_date:
            filtered = [
                t
                for t in filtered
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
        trade_date = self._parse_trade_date(trade.get("trade_date"))
        if not trade_date:
            return True

        if from_date and trade_date < from_date:
            return False
        if to_date and trade_date > to_date:
            return False

        return True

    def _parse_trade_date(self, date_str: Optional[str]) -> Optional[date]:
        """Parse RapidAPI trade_date to date object."""
        if not date_str:
            return None

        for fmt in ("%B %d, %Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(date_str, fmt).date()
            except (ValueError, TypeError):
                continue

        return None

    def _infer_disclosure_date(
        self, trade_date: Optional[date], days_until_disclosure: Any
    ) -> Optional[date]:
        """Infer disclosure date if days_until_disclosure is provided."""
        if not trade_date:
            return None
        try:
            days = int(days_until_disclosure)
        except (TypeError, ValueError):
            return None
        return trade_date + timedelta(days=days)

    def _extract_ticker(self, raw_ticker: Optional[str]) -> str:
        """Normalize ticker by removing exchange suffixes."""
        if not raw_ticker or raw_ticker == "N/A":
            return ""
        return raw_ticker.split(":", 1)[0].upper()

    def _parse_amount_range(
        self, amount_str: str
    ) -> tuple[Optional[float], Optional[float]]:
        """
        Parse RapidAPI amount ranges like "100K-250K", "1M-5M", "< 1K".
        """
        if not amount_str or amount_str == "N/A":
            return None, None

        cleaned = amount_str.replace("$", "").replace(",", "").strip()
        if cleaned.startswith("<"):
            value = self._parse_amount_token(cleaned.lstrip("<").strip())
            return None, value

        if "-" in cleaned:
            parts = [p.strip() for p in cleaned.split("-", 1)]
            if len(parts) == 2:
                low = self._parse_amount_token(parts[0])
                high = self._parse_amount_token(parts[1])
                return low, high

        value = self._parse_amount_token(cleaned)
        return value, value

    def _parse_amount_token(self, token: str) -> Optional[float]:
        """Parse amount token with K/M suffixes."""
        if not token:
            return None

        multiplier = 1.0
        upper = token.upper()

        if upper.endswith("K"):
            multiplier = 1_000.0
            upper = upper[:-1]
        elif upper.endswith("M"):
            multiplier = 1_000_000.0
            upper = upper[:-1]

        try:
            return float(upper) * multiplier
        except ValueError:
            return None
