#!/usr/bin/env python3
"""
Bootstrap script to initialize the database.
Run this before first use.
"""
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.db import db
from app.logging import setup_logging, get_logger

setup_logging(level="INFO")
logger = get_logger(__name__)


def main():
    """Initialize database schema."""
    print("="*60)
    print("Congress Trade Tracker - Database Bootstrap")
    print("="*60)
    print()

    print(f"Database path: {db.db_path}")
    print()

    # Create parent directory if needed
    db.db_path.parent.mkdir(parents=True, exist_ok=True)

    # Initialize schema
    try:
        db.init_schema()
        print("✓ Database initialized successfully!")
        print()
        print("Next steps:")
        print("  1. Set your FINNHUB_API_KEY in .env")
        print("  2. Configure IBKR connection settings")
        print("  3. Run: python -m app.run ingest")
        print()
    except Exception as e:
        print(f"✗ Error: {e}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
