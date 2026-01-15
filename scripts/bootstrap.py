"""Bootstrap script to initialize the database and validate setup."""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from tracker.config import settings
from tracker.database import init_db
from tracker.logger import logger


def main():
    """Initialize database and validate configuration."""
    print("=" * 60)
    print("Congress Trade Tracker - Bootstrap")
    print("=" * 60)

    # Validate configuration
    print("\n1. Validating configuration...")
    settings.validate_safety()

    if not settings.finnhub_api_key or settings.finnhub_api_key == "your_key_here":
        print("⚠️  WARNING: FINNHUB_API_KEY not set!")
        print("   Get a free key at https://finnhub.io/")
        print("   Add it to your .env file")

    print(f"   Database: {settings.database_url}")
    print(f"   IBKR: {settings.ibkr_host}:{settings.ibkr_port}")
    print(f"   Mode: {settings.account_mode}")

    # Create data directory
    print("\n2. Creating data directory...")
    data_dir = Path("data")
    data_dir.mkdir(exist_ok=True)
    print(f"   ✓ {data_dir} ready")

    logs_dir = Path("logs")
    logs_dir.mkdir(exist_ok=True)
    print(f"   ✓ {logs_dir} ready")

    # Initialize database
    print("\n3. Initializing database...")
    try:
        init_db()
        print("   ✓ Database initialized successfully")
    except Exception as e:
        print(f"   ✗ Database initialization failed: {e}")
        return 1

    # Test logger
    print("\n4. Testing logger...")
    logger.info("Bootstrap completed successfully")
    print(f"   ✓ Logs will be written to logs/tracker_*.log")

    print("\n" + "=" * 60)
    print("✓ Bootstrap complete!")
    print("=" * 60)
    print("\nNext steps:")
    print("  1. Set FINNHUB_API_KEY in .env")
    print("  2. Run: python -m tracker.cli ingest --days-back 7")
    print("  3. Run: python -m tracker.cli evaluate")
    print("  4. Run: python -m tracker.cli trade --dry-run")
    print("\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
