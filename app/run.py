"""CLI entrypoint for Congress Trade Tracker."""
from __future__ import annotations

import argparse
import logging

from app.config import load_config
from app.db import Database
from app.finnhub_client import FinnhubClient
from app.ibkr.client import IbkrClient
from app.ibkr.orders import execute_signals
from app.ibkr.reconcile import reconcile
from app.ingest import ingest_congress_trades
from app.logging import setup_logging
from app.strategy import generate_signals

logger = logging.getLogger(__name__)


def _print_summary(summary: dict[str, int]) -> None:
    for key, value in summary.items():
        print(f"{key}: {value}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Congress Trade Tracker CLI")
    parser.add_argument(
        "command",
        choices=["ingest", "signals", "trade", "reconcile", "daily"],
        help="command to run",
    )
    args = parser.parse_args()

    setup_logging()
    config = load_config()
    db = Database(config.db_path)
    db.init_schema()

    summary: dict[str, int] = {}
    if args.command == "ingest":
        client = FinnhubClient(config.finnhub_api_key)
        summary = ingest_congress_trades(client, db)
    elif args.command == "signals":
        summary = generate_signals(db)
    elif args.command == "trade":
        client = IbkrClient(config)
        summary = execute_signals(db, client)
    elif args.command == "reconcile":
        summary = reconcile(db)
    elif args.command == "daily":
        client = FinnhubClient(config.finnhub_api_key)
        ingest_summary = ingest_congress_trades(client, db)
        signal_summary = generate_signals(db)
        trade_summary = execute_signals(db, IbkrClient(config))
        summary = {
            "ingest_new": ingest_summary.get("inserted", 0),
            "signals_new": signal_summary.get("inserted", 0),
            "orders": trade_summary.get("orders", 0),
        }

    _print_summary(summary)
    db.close()


if __name__ == "__main__":
    main()
