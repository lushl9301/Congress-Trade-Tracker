"""
CLI runner for Congress Trade Tracker.
Main entry point for all commands (using Typer for better UX).
"""
import sys
from datetime import datetime
from typing import Any, Optional

import typer

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

# Create Typer app
app = typer.Typer(
    name="congress-tracker",
    help="Congress Trade Tracker - Automated trading based on congressional disclosures",
    add_completion=False,
)


@app.command("init-db")
def cmd_init_db() -> None:
    """Initialize database schema."""
    logger.info("Initializing database")
    try:
        db.init_schema()
        typer.echo(f"✓ Database initialized successfully at {db.db_path}")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)


@app.command()
def ingest(
    symbol: Optional[str] = typer.Option(None, help="Filter by ticker symbol"),
    from_date: Optional[str] = typer.Option(None, help="Start date (YYYY-MM-DD)"),
    to_date: Optional[str] = typer.Option(None, help="End date (YYYY-MM-DD)"),
) -> None:
    """Fetch and ingest congressional trades from Finnhub."""
    logger.info("Running ingestion")

    try:
        result = run_ingestion(
            symbol=symbol,
            from_date=from_date,
            to_date=to_date,
        )

        typer.echo("\n=== Ingestion Summary ===")
        typer.echo(f"Status: {result['status']}")
        typer.echo(f"Fetched: {result.get('fetched', 0)} records")
        typer.echo(f"New events: {result.get('new_events', 0)}")
        typer.echo(f"Duplicates: {result.get('duplicates', 0)}")

        if result.get('errors', 0) > 0:
            typer.echo(f"Errors: {result['errors']}")

        if result["status"] != "success":
            raise typer.Exit(code=1)

    except Exception as e:
        logger.error(f"Ingestion failed: {e}", exc_info=True)
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)


@app.command()
def signals() -> None:
    """Generate trading signals from events."""
    logger.info("Generating signals")

    try:
        result = run_signal_generation()

        typer.echo("\n=== Signal Generation Summary ===")
        typer.echo(f"Status: {result['status']}")
        typer.echo(f"Processed: {result.get('processed', 0)} events")
        typer.echo("\nSignals by strength:")
        for strength, count in result.get('signals_by_strength', {}).items():
            typer.echo(f"  {strength}: {count}")

        if result["status"] != "success":
            raise typer.Exit(code=1)

    except Exception as e:
        logger.error(f"Signal generation failed: {e}", exc_info=True)
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)


@app.command()
def trade() -> None:
    """Execute trading signals (respects TRADING_ENABLED flag)."""
    logger.info("Running trade execution")

    if not config.TRADING_ENABLED:
        typer.echo("\n⚠️  WARNING: TRADING_ENABLED=false")
        typer.echo("Orders will be logged but NOT submitted to IBKR\n")

    try:
        # Get unexecuted signals
        signals = db.get_unexecuted_signals()

        if not signals:
            typer.echo("No signals to execute")
            return

        typer.echo(f"\n=== Found {len(signals)} signals to execute ===\n")

        # Get NAV for position sizing
        client = get_ibkr_client()
        if config.TRADING_ENABLED:
            if not client.connect():
                typer.echo("Error: Cannot connect to IBKR", err=True)
                raise typer.Exit(code=1)
            nav = client.get_account_value("NetLiquidation")
        else:
            nav = 100000.0  # Mock NAV for dry run

        typer.echo(f"Portfolio NAV: ${nav:,.2f}\n")

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
                    typer.echo(f"SKIP {signal.ticker}: {', '.join(reasons)}")
                    orders_skipped += 1
                    continue

                # Check daily exposure limit
                notional = qty * current_price
                allowed, reason = portfolio_manager.check_daily_exposure_limit(nav, notional)

                if not allowed:
                    typer.echo(f"SKIP {signal.ticker}: {reason}")
                    orders_skipped += 1
                    continue

                # Place order
                typer.echo(
                    f"PLACE {signal.action} {qty} {signal.ticker} @ ${current_price:.2f} "
                    f"(notional: ${notional:,.2f})"
                )
                typer.echo(f"  Signal: {signal.strength} (score={signal.score})")
                typer.echo(f"  Reasons: {', '.join(signal.reason)}")

                order = order_manager.place_order(
                    ticker=signal.ticker,
                    side=signal.action,
                    qty=qty,
                    order_type="MKT",
                    signal_id=signal.signal_id,
                )

                if order:
                    orders_placed += 1
                    typer.echo(f"  ✓ Order placed: {order.order_id}")

                    # Poll status if trading enabled
                    if config.TRADING_ENABLED and order.status != "MOCK_DISABLED":
                        status = order_manager.poll_order_status(order.order_id, timeout=30)
                        typer.echo(f"  Status: {status}\n")
                else:
                    orders_skipped += 1
                    typer.echo(f"  ✗ Order failed\n")

            except Exception as e:
                logger.error(f"Error processing signal {signal.signal_id}: {e}")
                errors.append(str(e))
                orders_skipped += 1

        # Disconnect
        if config.TRADING_ENABLED:
            client.disconnect()

        # Print summary
        typer.echo("\n=== Trade Execution Summary ===")
        typer.echo(f"Orders placed: {orders_placed}")
        typer.echo(f"Orders skipped: {orders_skipped}")
        typer.echo(f"Errors: {len(errors)}")

        if errors:
            typer.echo("\nErrors:")
            for err in errors:
                typer.echo(f"  - {err}")

    except Exception as e:
        logger.error(f"Trade execution failed: {e}", exc_info=True)
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)


@app.command()
def reconcile() -> None:
    """Reconcile IBKR state with local database."""
    logger.info("Running reconciliation")

    try:
        result = run_reconciliation()

        typer.echo("\n=== Reconciliation Summary ===")
        typer.echo(f"Status: {result['status']}")

        # Positions
        pos_result = result.get('positions', {})
        typer.echo(f"\nPositions:")
        typer.echo(f"  IBKR: {pos_result.get('ibkr_positions', 0)}")
        typer.echo(f"  Local: {pos_result.get('local_positions', 0)}")
        typer.echo(f"  Discrepancies: {pos_result.get('discrepancies', 0)}")

        if pos_result.get('discrepancies', 0) > 0:
            typer.echo("\n  Details:")
            for disc in pos_result.get('details', []):
                typer.echo(f"    {disc}")

        # Orders
        ord_result = result.get('orders', {})
        typer.echo(f"\nOpen Orders:")
        typer.echo(f"  IBKR: {ord_result.get('ibkr_open_orders', 0)}")

        # Account
        acc_result = result.get('account', {})
        if acc_result.get('status') == 'success':
            typer.echo(f"\nAccount:")
            typer.echo(f"  Net Liquidation: ${acc_result.get('net_liquidation', 0):,.2f}")
            typer.echo(f"  Cash: ${acc_result.get('total_cash', 0):,.2f}")
            typer.echo(f"  Buying Power: ${acc_result.get('buying_power', 0):,.2f}")
            typer.echo(f"  Mode: {acc_result.get('mode', 'unknown').upper()}")

    except Exception as e:
        logger.error(f"Reconciliation failed: {e}", exc_info=True)
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)


@app.command()
def daily() -> None:
    """Run daily pipeline: ingest → signals → trade (if enabled)."""
    logger.info("Running daily pipeline")

    typer.echo(f"\n{'='*60}")
    typer.echo(f"Congress Trade Tracker - Daily Pipeline")
    typer.echo(f"Date: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC")
    typer.echo(f"Mode: {config.TRADING_MODE.upper()}")
    typer.echo(f"Trading Enabled: {config.TRADING_ENABLED}")
    typer.echo(f"{'='*60}\n")

    summary: dict[str, Any] = {
        "date": datetime.utcnow().strftime('%Y-%m-%d'),
    }

    # Step 1: Ingest
    typer.echo("\n[1/3] Running ingestion...")
    ingest_result = run_ingestion()
    summary['ingestion'] = ingest_result
    typer.echo(f"  New events: {ingest_result.get('new_events', 0)}")
    typer.echo(f"  Duplicates: {ingest_result.get('duplicates', 0)}")

    # Step 2: Generate signals
    typer.echo("\n[2/3] Generating signals...")
    signals_result = run_signal_generation()
    summary['signals'] = signals_result.get('signals_by_strength', {})
    typer.echo(f"  STRONG: {signals_result.get('signals_by_strength', {}).get('STRONG', 0)}")
    typer.echo(f"  NORMAL: {signals_result.get('signals_by_strength', {}).get('NORMAL', 0)}")

    # Step 3: Execute trades (only if enabled)
    typer.echo("\n[3/3] Executing trades...")
    if config.TRADING_ENABLED:
        # Would call trade execution here
        typer.echo("  (Trade execution via 'trade' command)")
        summary['trading'] = {"note": "Run 'trade' command separately"}
    else:
        typer.echo("  Skipped (TRADING_ENABLED=false)")
        summary['trading'] = {"note": "Trading disabled"}

    # Portfolio summary
    positions = db.get_all_positions()
    summary['portfolio'] = {
        "num_positions": len(positions),
        "total_notional": sum(p.qty * p.avg_cost for p in positions),
    }

    typer.echo("\n" + "="*60)
    typer.echo("Daily pipeline complete")
    typer.echo(f"Positions: {len(positions)}")
    typer.echo("="*60 + "\n")


@app.command()
def status() -> None:
    """Show system status and portfolio summary."""
    typer.echo("\n=== Congress Trade Tracker Status ===\n")

    # Config
    typer.echo("Configuration:")
    typer.echo(f"  Database: {config.DB_PATH}")
    typer.echo(f"  Trading Mode: {config.TRADING_MODE.upper()}")
    typer.echo(f"  Trading Enabled: {config.TRADING_ENABLED}")
    typer.echo(f"  Strategy Version: {config.STRATEGY_VERSION}")
    typer.echo(f"  Email Enabled: {config.EMAIL_ENABLED}")

    # Database stats
    typer.echo("\nDatabase:")
    with db.get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM congress_trade_events")
        events_count = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM trade_signals")
        signals_count = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM orders")
        orders_count = cursor.fetchone()[0]

        typer.echo(f"  Events: {events_count}")
        typer.echo(f"  Signals: {signals_count}")
        typer.echo(f"  Orders: {orders_count}")

    # Portfolio
    typer.echo("\nPortfolio:")
    positions = db.get_all_positions()
    typer.echo(f"  Positions: {len(positions)}")

    if positions:
        total_notional = sum(p.qty * p.avg_cost for p in positions)
        typer.echo(f"  Total Value: ${total_notional:,.2f}")
        typer.echo("\n  Holdings:")
        for pos in positions:
            typer.echo(
                f"    {pos.ticker}: {pos.qty} @ ${pos.avg_cost:.2f} "
                f"(holding {pos.holding_days} days)"
            )


@app.callback()
def main(
    log_level: str = typer.Option("INFO", help="Logging level"),
    json_logs: bool = typer.Option(False, "--json-logs", help="Output logs in JSON format"),
) -> None:
    """
    Congress Trade Tracker - Automated trading based on congressional disclosures.

    Set up logging and validate configuration before running commands.
    """
    # Setup logging
    setup_logging(level=log_level, json_format=json_logs)

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
            raise typer.Exit(code=1)


def cli_main() -> None:
    """Entry point for console script."""
    app()


if __name__ == "__main__":
    app()
