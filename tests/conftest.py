"""
Pytest configuration and fixtures for Congress Trade Tracker tests.
"""

import os
import tempfile
from pathlib import Path

import pytest

from app.db import db


@pytest.fixture(scope="session", autouse=True)
def setup_test_database():
    """
    Set up a test database for the entire test session.

    Creates a temporary database and initializes the schema.
    """
    # Create a temporary directory for the test database
    with tempfile.TemporaryDirectory() as tmpdir:
        test_db_path = Path(tmpdir) / "test.db"

        # Set the DB_PATH environment variable
        original_db_path = os.environ.get("DB_PATH")
        os.environ["DB_PATH"] = str(test_db_path)

        # Force reload of the db module with the new path
        db.__init__()

        # Initialize the database schema
        db.init_schema()

        yield

        # Restore original DB_PATH
        if original_db_path:
            os.environ["DB_PATH"] = original_db_path
        else:
            os.environ.pop("DB_PATH", None)


@pytest.fixture(autouse=True)
def clean_database():
    """
    Clean up database tables before each test.

    This ensures test isolation by clearing all data between tests.
    """
    with db.get_connection() as conn:
        cursor = conn.cursor()

        # Clear all tables
        cursor.execute("DELETE FROM fills")
        cursor.execute("DELETE FROM orders")
        cursor.execute("DELETE FROM positions")
        cursor.execute("DELETE FROM trade_signals")
        cursor.execute("DELETE FROM congress_trade_events")
        cursor.execute("DELETE FROM pnl_snapshots")

        conn.commit()

    yield
