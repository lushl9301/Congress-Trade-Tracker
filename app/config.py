"""
Configuration management for Congress Trade Tracker.
All secrets must be read from environment variables.
"""
import os
from pathlib import Path
from typing import Literal


class Config:
    """Application configuration loaded from environment variables."""

    # Finnhub API
    FINNHUB_API_KEY: str = os.getenv("FINNHUB_API_KEY", "")
    FINNHUB_BASE_URL: str = "https://finnhub.io/api/v1"

    # Database
    DB_PATH: Path = Path(os.getenv("DB_PATH", "./data/app.db"))

    # IBKR Settings
    IBKR_HOST: str = os.getenv("IBKR_HOST", "127.0.0.1")
    IBKR_PORT: int = int(os.getenv("IBKR_PORT", "7497"))  # 7497 = TWS paper, 4001 = IB Gateway paper
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
    TARGET_PCT_NORMAL: float = float(os.getenv("TARGET_PCT_NORMAL", "0.015"))  # 1.5% NAV
    MAX_TICKER_PCT: float = float(os.getenv("MAX_TICKER_PCT", "0.05"))  # 5% max per ticker
    MAX_DAILY_EXPOSURE: float = float(os.getenv("MAX_DAILY_EXPOSURE", "0.10"))  # 10% max new exposure per day

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

        if not cls.FINNHUB_API_KEY:
            errors.append("FINNHUB_API_KEY is required")

        if cls.TRADING_MODE not in ["paper", "live"]:
            errors.append(f"TRADING_MODE must be 'paper' or 'live', got '{cls.TRADING_MODE}'")

        if cls.TRADING_ENABLED and cls.TRADING_MODE == "live":
            errors.append("WARNING: TRADING_ENABLED=true with TRADING_MODE=live. This will place real trades!")

        if cls.EMAIL_ENABLED:
            if not all([cls.SMTP_HOST, cls.SMTP_USER, cls.SMTP_PASSWORD, cls.EMAIL_FROM, cls.EMAIL_TO]):
                errors.append("EMAIL_ENABLED=true but SMTP settings incomplete")

        return errors

    @classmethod
    def get_summary(cls) -> dict:
        """Get configuration summary (without secrets)."""
        return {
            "db_path": str(cls.DB_PATH),
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
