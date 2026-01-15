"""
CLI runner for Congress Trade Tracker.
Main entry point for all commands.
"""
import argparse
import sys
from datetime import datetime
from typing import Any

from app.config import config
from app.db import db
from app.ibkr.client import get_ibkr_client
from app.ibkr.orders import order_manager
from app.ibkr.reconcile import run_reconciliation
from app.ingest import run_ingestion
from app.logging import get_logger, setup_logging
from app.portfolio import portfolio_manager
from app.strategy import run_signal_generation

logger = get_logger(__name__)


def cmd_init_db(args: argparse.Namespace) -> int:
    """Initialize database schema."""
    logger.info("Initializing database")
    try:
        db.init_schema()
        print(f"Database initialized successfully at {db.db_path}")
        return 0
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        print(f"Error: {e}")
        return 1


def cmd_ingest(args: argparse.Namespace) -> int:
    """Run ingestion pipeline."""
    logger.info("Running ingestion")

    try:
        result = run_ingestion(
            symbol=args.symbol,
            from_date=args.from_date,
            to_date=args.to_date,
        )

        print("\n=== Ingestion Summary ===")
        print(f"Status: {result['status']}")
        print(f"Fetched: {result.get('fetched', 0)} records")
        print(f"New events: {result.get('new_events', 0)}")
        print(f"Duplicates: {result.get('duplicates', 0)}")

        if result.get('errors', 0) > 0:
            print(f"Errors: {result['errors']}")

        return 0 if result["status"] == "success" else 1

    except Exception as e:
        logger.error(f"Ingestion failed: {e}", exc_info=True)
        print(f"Error: {e}")
        return 1


def cmd_signals(args: argparse.Namespace) -> int:
    """Generate trading signals."""
    logger.info("Generating signals")

    try:
        result = run_signal_generation()

        print("\n=== Signal Generation Summary ===")
        print(f"Status: {result['status']}")
        print(f"Processed: {result.get('processed', 0)} events")
        print("\nSignals by strength:")
        for strength, count in result.get('signals_by_strength', {}).items():
            print(f"  {strength}: {count}")

        return 0 if result["status"] == "success" else 1

    except Exception as e:
        logger.error(f"Signal generation failed: {e}", exc_info=True)
        print(f"Error: {e}")
        return 1


def cmd_trade(args: argparse.Namespace) -> int:
    """Execute trading signals."""
    logger.info("Running trade execution")

    if not config.TRADING_ENABLED:
        print("\n⚠️  WARNING: TRADING_ENABLED=false")
        print("Orders will be logged but NOT submitted to IBKR\n")

    try:
        # Get unexecuted signals
        signals = db.get_unexecuted_signals()

        if not signals:
            print("No signals to execute")
            return 0

        print(f"\n=== Found {len(signals)} signals to execute ===\n")

        # Get NAV for position sizing
        client = get_ibkr_client()
        if config.TRADING_ENABLED:
            if not client.connect():
                print("Error: Cannot connect to IBKR")
                return 1
            nav = client.get_account_value("NetLiquidation")
        else:
            nav = 100000.0  # Mock NAV for dry run

        print(f"Portfolio NAV: ${nav:,.2f}\n")

        orders_placed = 0
        orders_skipped = 0
        errors = []

        for signal in signals:
            try:
                # Get current price
                if config.TRADING_ENABLED:
                    current_price = client.get_market_price(signal.ticker)
                else:
                    current_price = 100.0  # Mock price

                if not current_price:
                    logger.warning(f"Cannot get price for {signal.ticker}, skipping")
                    orders_skipped += 1
                    continue

                # Calculate position size
                qty, reasons = portfolio_manager.calculate_position_size(
                    signal.ticker, signal.strength, nav, current_price
                )

                if qty == 0:
                    print(f"SKIP {signal.ticker}: {', '.join(reasons)}")
                    orders_skipped += 1
                    continue

                # Check daily exposure limit
                notional = qty * current_price
                allowed, reason = portfolio_manager.check_daily_exposure_limit(nav, notional)

                if not allowed:
                    print(f"SKIP {signal.ticker}: {reason}")
                    orders_skipped += 1
                    continue

                # Place order
                print(
                    f"PLACE {signal.action} {qty} {signal.ticker} @ ${current_price:.2f} "
                    f"(notional: ${notional:,.2f})"
                )
                print(f"  Signal: {signal.strength} (score={signal.score})")
                print(f"  Reasons: {', '.join(signal.reason)}")

                order = order_manager.place_order(
                    ticker=signal.ticker,
                    side=signal.action,
                    qty=qty,
                    order_type="MKT",
                    signal_id=signal.signal_id,
                )

                if order:
                    orders_placed += 1
                    print(f"  ✓ Order placed: {order.order_id}")

                    # Poll status if trading enabled
                    if config.TRADING_ENABLED and order.status != "MOCK_DISABLED":
                        status = order_manager.poll_order_status(order.order_id, timeout=30)
                        print(f"  Status: {status}\n")
                else:
                    orders_skipped += 1
                    print(f"  ✗ Order failed\n")

            except Exception as e:
                logger.error(f"Error processing signal {signal.signal_id}: {e}")
                errors.append(str(e))
                orders_skipped += 1

        # Disconnect
        if config.TRADING_ENABLED:
            client.disconnect()

        # Print summary
        print("\n=== Trade Execution Summary ===")
        print(f"Orders placed: {orders_placed}")
        print(f"Orders skipped: {orders_skipped}")
        print(f"Errors: {len(errors)}")

        if errors:
            print("\nErrors:")
            for err in errors:
                print(f"  - {err}")

        return 0

    except Exception as e:
        logger.error(f"Trade execution failed: {e}", exc_info=True)
        print(f"Error: {e}")
        return 1


def cmd_reconcile(args: argparse.Namespace) -> int:
    """Reconcile IBKR state with local database."""
    logger.info("Running reconciliation")

    try:
        result = run_reconciliation()

        print("\n=== Reconciliation Summary ===")
        print(f"Status: {result['status']}")

        # Positions
        pos_result = result.get('positions', {})
        print(f"\nPositions:")
        print(f"  IBKR: {pos_result.get('ibkr_positions', 0)}")
        print(f"  Local: {pos_result.get('local_positions', 0)}")
        print(f"  Discrepancies: {pos_result.get('discrepancies', 0)}")

        if pos_result.get('discrepancies', 0) > 0:
            print("\n  Details:")
            for disc in pos_result.get('details', []):
                print(f"    {disc}")

        # Orders
        ord_result = result.get('orders', {})
        print(f"\nOpen Orders:")
        print(f"  IBKR: {ord_result.get('ibkr_open_orders', 0)}")

        # Account
        acc_result = result.get('account', {})
        if acc_result.get('status') == 'success':
            print(f"\nAccount:")
            print(f"  Net Liquidation: ${acc_result.get('net_liquidation', 0):,.2f}")
            print(f"  Cash: ${acc_result.get('total_cash', 0):,.2f}")
            print(f"  Buying Power: ${acc_result.get('buying_power', 0):,.2f}")
            print(f"  Mode: {acc_result.get('mode', 'unknown').upper()}")

        return 0

    except Exception as e:
        logger.error(f"Reconciliation failed: {e}", exc_info=True)
        print(f"Error: {e}")
        return 1


def cmd_daily(args: argparse.Namespace) -> int:
    """Run daily pipeline: ingest -> signals -> trade."""
    logger.info("Running daily pipeline")

    print(f"\n{'='*60}")
    print(f"Congress Trade Tracker - Daily Pipeline")
    print(f"Date: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC")
    print(f"Mode: {config.TRADING_MODE.upper()}")
    print(f"Trading Enabled: {config.TRADING_ENABLED}")
    print(f"{'='*60}\n")

    summary: dict[str, Any] = {
        "date": datetime.utcnow().strftime('%Y-%m-%d'),
    }

    # Step 1: Ingest
    print("\n[1/3] Running ingestion...")
    ingest_result = run_ingestion()
    summary['ingestion'] = ingest_result
    print(f"  New events: {ingest_result.get('new_events', 0)}")
    print(f"  Duplicates: {ingest_result.get('duplicates', 0)}")

    # Step 2: Generate signals
    print("\n[2/3] Generating signals...")
    signals_result = run_signal_generation()
    summary['signals'] = signals_result.get('signals_by_strength', {})
    print(f"  STRONG: {signals_result.get('signals_by_strength', {}).get('STRONG', 0)}")
    print(f"  NORMAL: {signals_result.get('signals_by_strength', {}).get('NORMAL', 0)}")

    # Step 3: Execute trades (only if enabled)
    print("\n[3/3] Executing trades...")
    if config.TRADING_ENABLED:
        # Would call trade execution here
        print("  (Trade execution via 'trade' command)")
        summary['trading'] = {"note": "Run 'trade' command separately"}
    else:
        print("  Skipped (TRADING_ENABLED=false)")
        summary['trading'] = {"note": "Trading disabled"}

    # Portfolio summary
    positions = db.get_all_positions()
    summary['portfolio'] = {
        "num_positions": len(positions),
        "total_notional": sum(p.qty * p.avg_cost for p in positions),
    }

    print("\n" + "="*60)
    print("Daily pipeline complete")
    print(f"Positions: {len(positions)}")
    print("="*60 + "\n")

    return 0


def cmd_status(args: argparse.Namespace) -> int:
    """Show system status and portfolio summary."""
    print("\n=== Congress Trade Tracker Status ===\n")

    # Config
    print("Configuration:")
    print(f"  Database: {config.DB_PATH}")
    print(f"  Trading Mode: {config.TRADING_MODE.upper()}")
    print(f"  Trading Enabled: {config.TRADING_ENABLED}")
    print(f"  Strategy Version: {config.STRATEGY_VERSION}")
    print(f"  Email Enabled: {config.EMAIL_ENABLED}")

    # Database stats
    print("\nDatabase:")
    with db.get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM congress_trade_events")
        events_count = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM trade_signals")
        signals_count = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM orders")
        orders_count = cursor.fetchone()[0]

        print(f"  Events: {events_count}")
        print(f"  Signals: {signals_count}")
        print(f"  Orders: {orders_count}")

    # Portfolio
    print("\nPortfolio:")
    positions = db.get_all_positions()
    print(f"  Positions: {len(positions)}")

    if positions:
        total_notional = sum(p.qty * p.avg_cost for p in positions)
        print(f"  Total Value: ${total_notional:,.2f}")
        print("\n  Holdings:")
        for pos in positions:
            print(
                f"    {pos.ticker}: {pos.qty} @ ${pos.avg_cost:.2f} "
                f"(holding {pos.holding_days} days)"
            )

    return 0


def main() -> int:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Congress Trade Tracker - Automated trading based on congressional disclosures"
    )

    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level",
    )

    parser.add_argument(
        "--json-logs",
        action="store_true",
        help="Output logs in JSON format",
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # init-db command
    subparsers.add_parser("init-db", help="Initialize database schema")

    # ingest command
    ingest_parser = subparsers.add_parser("ingest", help="Fetch and ingest congressional trades")
    ingest_parser.add_argument("--symbol", help="Filter by ticker symbol")
    ingest_parser.add_argument("--from-date", help="Start date (YYYY-MM-DD)")
    ingest_parser.add_argument("--to-date", help="End date (YYYY-MM-DD)")

    # signals command
    subparsers.add_parser("signals", help="Generate trading signals")

    # trade command
    subparsers.add_parser("trade", help="Execute trading signals")

    # reconcile command
    subparsers.add_parser("reconcile", help="Reconcile IBKR state with database")

    # daily command
    subparsers.add_parser("daily", help="Run daily pipeline (ingest + signals)")

    # status command
    subparsers.add_parser("status", help="Show system status")

    args = parser.parse_args()

    # Setup logging
    setup_logging(level=args.log_level, json_format=args.json_logs)

    # Validate config
    errors = config.validate()
    if errors:
        for error in errors:
            if error.startswith("WARNING"):
                logger.warning(error)
            else:
                logger.error(error)

        # Don't fail on warnings
        if any(not e.startswith("WARNING") for e in errors):
            return 1

    # Route to command
    if not args.command:
        parser.print_help()
        return 1

    commands = {
        "init-db": cmd_init_db,
        "ingest": cmd_ingest,
        "signals": cmd_signals,
        "trade": cmd_trade,
        "reconcile": cmd_reconcile,
        "daily": cmd_daily,
        "status": cmd_status,
    }

    cmd_func = commands.get(args.command)
    if not cmd_func:
        print(f"Unknown command: {args.command}")
        return 1

    return cmd_func(args)


if __name__ == "__main__":
    sys.exit(main())
