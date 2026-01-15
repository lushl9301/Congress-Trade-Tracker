"""
Configuration management for Congress Trade Tracker.
All secrets must be read from environment variables.
"""

import os
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


class Config:
    """Application configuration loaded from environment variables."""

    # Data Sources
    # Finnhub API (DEPRECATED - requires paid tier for congressional data)
    FINNHUB_API_KEY: str = os.getenv("FINNHUB_API_KEY", "")
    FINNHUB_BASE_URL: str = "https://finnhub.io/api/v1"

    # House Stock Watcher (Free, no API key required)
    HSW_ENABLED: bool = os.getenv("HSW_ENABLED", "true").lower() == "true"

    # Financial Modeling Prep (Free tier: 250 requests/day)
    # TODO: Get API key from https://financialmodelingprep.com/register
    FMP_API_KEY: str = os.getenv("FMP_API_KEY", "DUMMY_FMP_API_KEY_REPLACE_ME")
    FMP_ENABLED: bool = os.getenv("FMP_ENABLED", "false").lower() == "true"

    # CapitolTrades (Free, requires web scraping)
    # Aggregated data from capitoltrades.com
    # Requires implementation: See CAPITOL_TRADES_IMPLEMENTATION.md
    CT_ENABLED: bool = os.getenv("CT_ENABLED", "false").lower() == "true"
    CT_USE_CACHE: bool = os.getenv("CT_USE_CACHE", "true").lower() == "true"

    # Multi-source strategy: primary_only, fallback, all, verify
    DATA_SOURCE_STRATEGY: str = os.getenv("DATA_SOURCE_STRATEGY", "verify")

    # Database
    DB_PATH: Path = Path(os.getenv("DB_PATH", "./data/app.db"))

    # IBKR Settings
    IBKR_HOST: str = os.getenv("IBKR_HOST", "127.0.0.1")
    IBKR_PORT: int = int(
        os.getenv("IBKR_PORT", "7497")
    )  # 7497 = TWS paper, 4001 = IB Gateway paper
    IBKR_CLIENT_ID: int = int(os.getenv("IBKR_CLIENT_ID", "1"))

    # Trading mode and safety
    TRADING_MODE: Literal["paper", "live"] = os.getenv("TRADING_MODE", "paper")  # type: ignore
    TRADING_ENABLED: bool = os.getenv("TRADING_ENABLED", "false").lower() == "true"

    # Email/Notifications
    EMAIL_ENABLED: bool = os.getenv("EMAIL_ENABLED", "false").lower() == "true"
    SMTP_HOST: str = os.getenv("SMTP_HOST", "")
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USER: str = os.getenv("SMTP_USER", "")
    SMTP_PASSWORD: str = os.getenv("SMTP_PASSWORD", "")
    EMAIL_FROM: str = os.getenv("EMAIL_FROM", "")
    EMAIL_TO: str = os.getenv("EMAIL_TO", "")

    # Strategy parameters
    STRATEGY_VERSION: str = "mvp_v1"
    MAX_DELAY_DAYS: int = int(os.getenv("MAX_DELAY_DAYS", "14"))
    MIN_AMOUNT_HIGH: float = float(os.getenv("MIN_AMOUNT_HIGH", "5000"))

    # Position sizing
    TARGET_PCT_STRONG: float = float(os.getenv("TARGET_PCT_STRONG", "0.03"))  # 3% NAV
    TARGET_PCT_NORMAL: float = float(
        os.getenv("TARGET_PCT_NORMAL", "0.015")
    )  # 1.5% NAV
    MAX_TICKER_PCT: float = float(
        os.getenv("MAX_TICKER_PCT", "0.05")
    )  # 5% max per ticker
    MAX_DAILY_EXPOSURE: float = float(
        os.getenv("MAX_DAILY_EXPOSURE", "0.10")
    )  # 10% max new exposure per day

    # Exit rules
    MAX_HOLD_DAYS: int = int(os.getenv("MAX_HOLD_DAYS", "30"))
    STOP_LOSS_PCT: float = float(os.getenv("STOP_LOSS_PCT", "-0.08"))  # -8%
    TAKE_PROFIT_PCT: float = float(os.getenv("TAKE_PROFIT_PCT", "0.20"))  # +20%

    # Polling frequency (minutes)
    POLL_INTERVAL_MINUTES: int = int(os.getenv("POLL_INTERVAL_MINUTES", "60"))

    @classmethod
    def validate(cls) -> list[str]:
        """Validate configuration and return list of errors."""
        errors = []

        # Data source validation
        if not cls.HSW_ENABLED and not cls.FMP_ENABLED and not cls.CT_ENABLED:
            errors.append(
                "At least one data source must be enabled "
                "(HSW_ENABLED, FMP_ENABLED, or CT_ENABLED)"
            )

        if cls.FMP_ENABLED and cls.FMP_API_KEY == "DUMMY_FMP_API_KEY_REPLACE_ME":
            errors.append(
                "FMP_ENABLED=true but using dummy API key. "
                "Get real API key from https://financialmodelingprep.com/register "
                "and set FMP_API_KEY environment variable"
            )

        if cls.CT_ENABLED:
            errors.append(
                "WARNING: CapitolTrades source enabled but requires full implementation. "
                "See CAPITOL_TRADES_IMPLEMENTATION.md for details. "
                "The source will not fetch data until scraping is implemented."
            )

        if cls.DATA_SOURCE_STRATEGY not in ["primary_only", "fallback", "all", "verify"]:
            errors.append(
                f"DATA_SOURCE_STRATEGY must be one of: primary_only, fallback, all, verify. "
                f"Got: '{cls.DATA_SOURCE_STRATEGY}'"
            )

        # Finnhub is deprecated for congressional data (requires paid tier)
        if cls.FINNHUB_API_KEY:
            errors.append(
                "WARNING: Finnhub API key detected but congressional trading data "
                "requires PAID tier (~$50/month). Consider using HSW or FMP instead."
            )

        if cls.TRADING_MODE not in ["paper", "live"]:
            errors.append(
                f"TRADING_MODE must be 'paper' or 'live', got '{cls.TRADING_MODE}'"
            )

        if cls.TRADING_ENABLED and cls.TRADING_MODE == "live":
            errors.append(
                "WARNING: TRADING_ENABLED=true with TRADING_MODE=live. This will place real trades!"
            )

        if cls.EMAIL_ENABLED:
            if not all(
                [
                    cls.SMTP_HOST,
                    cls.SMTP_USER,
                    cls.SMTP_PASSWORD,
                    cls.EMAIL_FROM,
                    cls.EMAIL_TO,
                ]
            ):
                errors.append("EMAIL_ENABLED=true but SMTP settings incomplete")

        return errors

    @classmethod
    def get_summary(cls) -> dict:
        """Get configuration summary (without secrets)."""
        return {
            "db_path": str(cls.DB_PATH),
            "data_sources": {
                "hsw_enabled": cls.HSW_ENABLED,
                "fmp_enabled": cls.FMP_ENABLED,
                "fmp_configured": cls.FMP_API_KEY != "DUMMY_FMP_API_KEY_REPLACE_ME",
                "ct_enabled": cls.CT_ENABLED,
                "ct_use_cache": cls.CT_USE_CACHE,
                "strategy": cls.DATA_SOURCE_STRATEGY,
            },
            "trading_mode": cls.TRADING_MODE,
            "trading_enabled": cls.TRADING_ENABLED,
            "strategy_version": cls.STRATEGY_VERSION,
            "max_delay_days": cls.MAX_DELAY_DAYS,
            "min_amount_high": cls.MIN_AMOUNT_HIGH,
            "ibkr_configured": bool(cls.IBKR_HOST and cls.IBKR_PORT),
            "email_enabled": cls.EMAIL_ENABLED,
        }


# Global config instance
config = Config()
