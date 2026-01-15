"""Configuration loading from environment variables."""
from __future__ import annotations

import os
from dataclasses import dataclass


def _get_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class AppConfig:
    finnhub_api_key: str
    db_path: str
    ibkr_host: str
    ibkr_port: int
    ibkr_client_id: int
    trading_mode: str
    trading_enabled: bool
    email_enabled: bool


def load_config() -> AppConfig:
    return AppConfig(
        finnhub_api_key=os.getenv("FINNHUB_API_KEY", ""),
        db_path=os.getenv("DB_PATH", "./data/app.db"),
        ibkr_host=os.getenv("IBKR_HOST", "127.0.0.1"),
        ibkr_port=int(os.getenv("IBKR_PORT", "4002")),
        ibkr_client_id=int(os.getenv("IBKR_CLIENT_ID", "1")),
        trading_mode=os.getenv("TRADING_MODE", "paper"),
        trading_enabled=_get_bool(os.getenv("TRADING_ENABLED"), False),
        email_enabled=_get_bool(os.getenv("EMAIL_ENABLED"), False),
    )
