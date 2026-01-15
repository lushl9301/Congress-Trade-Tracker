"""Initialize the SQLite database schema."""
from __future__ import annotations

from app.config import load_config
from app.db import Database
from app.logging import setup_logging


def main() -> None:
    setup_logging()
    config = load_config()
    db = Database(config.db_path)
    db.init_schema()
    db.close()
    print(f"Initialized database at {config.db_path}")


if __name__ == "__main__":
    main()
