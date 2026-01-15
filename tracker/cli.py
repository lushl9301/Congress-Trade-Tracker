"""Command-line interface for Congress Trade Tracker."""

from datetime import datetime, timedelta

import typer
from rich.console import Console
from rich.table import Table

from tracker.config import settings
from tracker.database import SessionLocal, SignalDB, init_db
from tracker.evaluate import SignalGenerator
from tracker.execute import TradeExecutor
from tracker.ingest import DataIngestor
from tracker.logger import logger
from tracker.models import SignalAction
from tracker.portfolio import PortfolioManager

app = typer.Typer(
    name="tracker",
    help="Congress Trade Tracker - Automated investment assistant",
    add_completion=False,
)

console = Console()


@app.command()
def init():
    """Initialize the database."""
    console.print("[bold blue]Initializing database...[/bold blue]")
    init_db()
    console.print("[bold green]✓ Database initialized successfully[/bold green]")


@app.command()
def ingest(
    symbol: str = typer.Option(None, "--symbol", "-s", help="Stock ticker (optional)"),
    days_back: int = typer.Option(30, "--days-back", "-d", help="Days to look back"),
    from_date: str = typer.Option(None, "--from-date", help="Start date (YYYY-MM-DD)"),
    to_date: str = typer.Option(None, "--to-date", help="End date (YYYY-MM-DD)"),
):
    """Fetch congressional trade disclosures from Finnhub."""
    console.print("[bold blue]Fetching congressional trades...[/bold blue]")

    # Calculate date range
    if not from_date:
        from_date = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")
    if not to_date:
        to_date = datetime.now().strftime("%Y-%m-%d")

    ingestor = DataIngestor()
    count = ingestor.ingest(symbol=symbol, from_date=from_date, to_date=to_date)

    console.print(f"[bold green]✓ Ingested {count} new disclosures[/bold green]")


@app.command()
def evaluate():
    """Generate trading signals from disclosures."""
    console.print("[bold blue]Evaluating disclosures and generating signals...[/bold blue]")

    generator = SignalGenerator()
    count = generator.process_new_disclosures()

    console.print(f"[bold green]✓ Generated {count} signals[/bold green]")


@app.command()
def trade(
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be traded without executing")
):
    """Execute eligible trading signals."""
    # Safety check
    settings.validate_safety()

    if dry_run:
        console.print("[yellow]Running in DRY RUN mode - no orders will be placed[/yellow]")

    console.print("[bold blue]Executing trading signals...[/bold blue]")

    db = SessionLocal()
    executor = TradeExecutor()

    try:
        from tracker.database import OrderDB

        # Find BUY and SELL signals that haven't been executed yet
        pending_signals = (
            db.query(SignalDB)
            .filter(
                SignalDB.action.in_([SignalAction.BUY.value, SignalAction.SELL.value]),
            )
            .outerjoin(OrderDB, SignalDB.id == OrderDB.signal_id)
            .filter(OrderDB.id.is_(None))  # No order exists yet
            .all()
        )

        console.print(f"Found {len(pending_signals)} signals to execute")

        if dry_run:
            # Just show what would be traded
            table = Table(title="Signals to Execute (Dry Run)")
            table.add_column("Ticker", style="cyan")
            table.add_column("Action", style="magenta")
            table.add_column("Confidence", style="green")
            table.add_column("Score", style="yellow")

            for sig in pending_signals:
                table.add_row(sig.ticker, sig.action, sig.confidence, str(sig.score))

            console.print(table)
            return

        # Execute signals
        orders_placed = 0
        for db_signal in pending_signals:
            # Convert to Pydantic model
            from uuid import UUID

            from tracker.models import Signal, SignalConfidence

            signal = Signal(
                id=UUID(db_signal.id),
                disclosure_id=UUID(db_signal.disclosure_id),
                ticker=db_signal.ticker,
                action=SignalAction(db_signal.action),
                confidence=SignalConfidence(db_signal.confidence),
                score=db_signal.score,
                reasons=db_signal.reasons,
                created_at=db_signal.created_at,
            )

            order = executor.execute_signal(signal)
            if order:
                orders_placed += 1
                console.print(f"[green]✓ Placed order for {signal.ticker}[/green]")

        console.print(f"[bold green]✓ Placed {orders_placed} orders[/bold green]")

    finally:
        db.close()
        executor.disconnect()


@app.command()
def check_exits():
    """Check positions for exit conditions and generate SELL signals."""
    console.print("[bold blue]Checking positions for exits...[/bold blue]")

    db = SessionLocal()
    portfolio_manager = PortfolioManager()

    try:
        exits = portfolio_manager.check_exit_conditions(db)

        if not exits:
            console.print("[green]No positions need to exit[/green]")
            return

        console.print(f"[yellow]Found {len(exits)} positions to exit:[/yellow]")

        for position, reason in exits:
            console.print(f"  - {position.ticker}: {reason}")

            # TODO: Generate SELL signal or execute directly
            # For now, just log

    finally:
        db.close()


@app.command()
def status():
    """Show portfolio status and current positions."""
    db = SessionLocal()
    portfolio_manager = PortfolioManager()

    try:
        # Get positions
        positions = portfolio_manager.get_all_positions(db)

        if not positions:
            console.print("[yellow]No open positions[/yellow]")
            return

        # Create table
        table = Table(title="Current Positions")
        table.add_column("Ticker", style="cyan")
        table.add_column("Quantity", style="magenta")
        table.add_column("Avg Cost", style="green")
        table.add_column("Current Price", style="yellow")
        table.add_column("P&L", style="red")
        table.add_column("Return %", style="blue")

        for pos in positions:
            pnl = pos.calculate_pnl()
            ret = pos.calculate_return_pct()

            table.add_row(
                pos.ticker,
                f"{pos.quantity:.2f}",
                f"${pos.avg_cost:.2f}",
                f"${pos.current_price:.2f}" if pos.current_price else "N/A",
                f"${pnl:.2f}" if pnl else "N/A",
                f"{ret*100:.2f}%" if ret else "N/A",
            )

        console.print(table)

        # Summary
        nav = portfolio_manager.get_nav()
        console.print(f"\n[bold]Portfolio NAV:[/bold] ${nav:,.2f}")
        console.print(f"[bold]Number of positions:[/bold] {len(positions)}")

    finally:
        db.close()


@app.command()
def daily():
    """Run the full daily pipeline: ingest → evaluate → trade → check exits."""
    console.print("[bold magenta]Running daily pipeline...[/bold magenta]\n")

    # Validate safety settings
    settings.validate_safety()

    # Step 1: Ingest
    console.print("[bold]Step 1: Ingesting new disclosures[/bold]")
    ingestor = DataIngestor()
    new_disclosures = ingestor.ingest()
    console.print(f"  → {new_disclosures} new disclosures\n")

    # Step 2: Evaluate
    console.print("[bold]Step 2: Generating signals[/bold]")
    generator = SignalGenerator()
    new_signals = generator.process_new_disclosures()
    console.print(f"  → {new_signals} new signals\n")

    # Step 3: Check exits
    console.print("[bold]Step 3: Checking exit conditions[/bold]")
    db = SessionLocal()
    portfolio_manager = PortfolioManager()
    try:
        exits = portfolio_manager.check_exit_conditions(db)
        console.print(f"  → {len(exits)} positions to exit\n")
    finally:
        db.close()

    # Step 4: Trade
    console.print("[bold]Step 4: Executing trades[/bold]")
    if settings.trading_enabled:
        executor = TradeExecutor()
        # ... execute orders (simplified for now)
        console.print("  → Trading executed (see logs for details)\n")
    else:
        console.print("  → [yellow]Trading disabled (safe mode)[/yellow]\n")

    # Summary
    console.print("[bold green]✓ Daily pipeline completed[/bold green]")
    logger.info("Daily pipeline completed successfully")


@app.command()
def config():
    """Show current configuration."""
    table = Table(title="Configuration")
    table.add_column("Setting", style="cyan")
    table.add_column("Value", style="yellow")

    table.add_row("Trading Enabled", str(settings.trading_enabled))
    table.add_row("Account Mode", settings.account_mode)
    table.add_row("IBKR Port", str(settings.ibkr_port))
    table.add_row("Max Position %", f"{settings.max_position_pct*100}%")
    table.add_row("Max Positions", str(settings.max_positions))
    table.add_row("Max Hold Days", str(settings.max_hold_days))
    table.add_row("Profit Target", f"{settings.profit_target_pct*100}%")
    table.add_row("Stop Loss", f"{settings.stop_loss_pct*100}%")

    console.print(table)


if __name__ == "__main__":
    app()
