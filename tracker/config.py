"""Configuration management."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Trading Controls
    trading_enabled: bool = False
    account_mode: str = "paper"  # paper | live

    # Data Sources
    finnhub_api_key: str

    # Database
    database_url: str = "sqlite:///./data/tracker.db"

    # Interactive Brokers
    ibkr_host: str = "127.0.0.1"
    ibkr_port: int = 7497  # 7497=paper, 7496=live
    ibkr_client_id: int = 1

    # Position Limits
    max_position_pct: float = 0.08  # 8% max per ticker
    max_daily_exposure_pct: float = 0.05  # 5% max new positions per day
    max_positions: int = 15
    min_position_size: float = 500.0

    # Exit Rules
    max_hold_days: int = 30
    profit_target_pct: float = 0.20  # 20% profit target
    stop_loss_pct: float = 0.10  # 10% stop loss

    # Notifications
    email_enabled: bool = False
    sendgrid_api_key: str = ""
    email_from: str = ""
    email_to: str = ""

    # Logging
    log_level: str = "INFO"

    def validate_safety(self) -> None:
        """Validate safety settings before allowing trading."""
        if self.trading_enabled:
            if self.account_mode == "live":
                print("⚠️  WARNING: Trading ENABLED in LIVE mode!")
                print("⚠️  Real money will be traded!")
            else:
                print("✓ Trading ENABLED in PAPER mode")
        else:
            print("✓ Trading DISABLED (safe mode)")


# Global settings instance
settings = Settings()
