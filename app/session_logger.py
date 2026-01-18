"""
Session logging utility for capturing daily operations output.

This module provides utilities to capture all CLI output (both logger and print/typer.echo)
to a session log file for later review.
"""

import sys
from datetime import datetime
from pathlib import Path
from typing import Any, TextIO

from app.logging import logger


class SessionLogger:
    """
    Captures all output (stdout + logs) to a session file.

    Usage:
        with SessionLogger("daily") as session:
            session.log("Starting daily workflow...")
            # Your code here
            session.log("Completed!")
    """

    def __init__(self, command: str, log_dir: str = "./logs"):
        """
        Initialize session logger.

        Args:
            command: Command name (e.g., "daily", "ingest", "trade")
            log_dir: Directory to store session logs
        """
        self.command = command
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(exist_ok=True)

        # Create session log file with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.session_file = self.log_dir / f"session_{command}_{timestamp}.log"
        self.file_handle: TextIO | None = None

        # Track session statistics
        self.start_time = datetime.now()
        self.end_time: datetime | None = None
        self.error_count = 0
        self.warning_count = 0

    def __enter__(self):
        """Start session logging."""
        self.file_handle = open(self.session_file, "w", encoding="utf-8")
        self._write_header()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """End session logging and write summary."""
        self.end_time = datetime.now()
        if self.file_handle:
            self._write_footer()
            self.file_handle.close()

        # Log session completion
        duration = (self.end_time - self.start_time).total_seconds()
        logger.bind(daily_operation=True).info(
            f"Session completed: {self.command} "
            f"(duration={duration:.1f}s, errors={self.error_count}, "
            f"warnings={self.warning_count}, log={self.session_file.name})"
        )

    def _write_header(self):
        """Write session header."""
        if self.file_handle:
            self.file_handle.write("=" * 80 + "\n")
            self.file_handle.write(
                f"Congress Trade Tracker - Session Log\n"
            )
            self.file_handle.write(f"Command: {self.command}\n")
            self.file_handle.write(
                f"Started: {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}\n"
            )
            self.file_handle.write("=" * 80 + "\n\n")
            self.file_handle.flush()

    def _write_footer(self):
        """Write session footer with summary."""
        if self.file_handle and self.end_time:
            duration = (self.end_time - self.start_time).total_seconds()
            self.file_handle.write("\n" + "=" * 80 + "\n")
            self.file_handle.write("Session Summary\n")
            self.file_handle.write("=" * 80 + "\n")
            self.file_handle.write(
                f"Ended: {self.end_time.strftime('%Y-%m-%d %H:%M:%S')}\n"
            )
            self.file_handle.write(f"Duration: {duration:.1f} seconds\n")
            self.file_handle.write(f"Errors: {self.error_count}\n")
            self.file_handle.write(f"Warnings: {self.warning_count}\n")
            self.file_handle.write("=" * 80 + "\n")
            self.file_handle.flush()

    def log(self, message: str, level: str = "INFO"):
        """
        Log a message to both stdout and session file.

        Args:
            message: Message to log
            level: Log level (INFO, WARNING, ERROR)
        """
        # Count warnings/errors
        if level == "WARNING":
            self.warning_count += 1
        elif level == "ERROR":
            self.error_count += 1

        # Write to session file
        if self.file_handle:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.file_handle.write(f"[{timestamp}] [{level:7}] {message}\n")
            self.file_handle.flush()

        # Also log to standard logger
        log_func = getattr(logger.bind(daily_operation=True), level.lower())
        log_func(message)

    def log_dict(self, data: dict[str, Any], title: str | None = None):
        """
        Log a dictionary in a formatted way.

        Args:
            data: Dictionary to log
            title: Optional title for the section
        """
        if title:
            self.log(f"\n{title}:")

        for key, value in data.items():
            self.log(f"  {key}: {value}")

    def log_section(self, title: str):
        """
        Log a section header.

        Args:
            title: Section title
        """
        separator = "-" * 60
        self.log(f"\n{separator}")
        self.log(title)
        self.log(separator)


def create_daily_summary(
    ingest_result: dict[str, Any],
    signals_result: dict[str, Any],
    trade_result: dict[str, Any],
    performance: dict[str, Any] | None = None,
) -> str:
    """
    Create a comprehensive daily summary report.

    Args:
        ingest_result: Result from ingestion
        signals_result: Result from signal generation
        trade_result: Result from trade execution
        performance: Optional performance metrics

    Returns:
        Formatted summary string
    """
    lines = []
    lines.append("\n" + "=" * 80)
    lines.append("DAILY RUN SUMMARY")
    lines.append("=" * 80)

    # Date
    lines.append(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")

    # Ingestion
    lines.append("📥 INGESTION:")
    lines.append(
        f"   New events: {ingest_result.get('new_events', 0)}"
    )
    lines.append(
        f"   Duplicates: {ingest_result.get('duplicates', 0)}"
    )
    lines.append(
        f"   Total events: {ingest_result.get('total_events', 0)}"
    )
    lines.append("")

    # Signals
    lines.append("🎯 SIGNALS:")
    signals_by_strength = signals_result.get("signals_by_strength", {})
    lines.append(
        f"   STRONG: {signals_by_strength.get('STRONG', 0)}"
    )
    lines.append(
        f"   NORMAL: {signals_by_strength.get('NORMAL', 0)}"
    )
    lines.append(
        f"   WATCH: {signals_by_strength.get('WATCH', 0)}"
    )
    lines.append(
        f"   IGNORE: {signals_by_strength.get('IGNORE', 0)}"
    )
    lines.append("")

    # Trading
    lines.append("💼 TRADING:")
    lines.append(
        f"   Signals processed: {trade_result.get('signals_processed', 0)}"
    )
    lines.append(
        f"   Trades executed: {trade_result.get('trades_executed', 0)}"
    )
    lines.append(
        f"   Trades skipped: {trade_result.get('trades_skipped', 0)}"
    )

    # List executed trades
    if trade_result.get("executed_trades"):
        lines.append("\n   Executed Trades:")
        for trade in trade_result.get("executed_trades", []):
            lines.append(
                f"      • {trade.get('side')} {trade.get('shares', 0):.2f} "
                f"{trade.get('ticker')} @ ${trade.get('price', 0):.2f} "
                f"(${trade.get('notional', 0):.2f})"
            )
    lines.append("")

    # Performance (if provided)
    if performance:
        lines.append("📊 PERFORMANCE:")
        lines.append(
            f"   NAV: ${performance.get('nav', 0):,.2f}"
        )
        lines.append(
            f"   Return: ${performance.get('total_return', 0):,.2f} "
            f"({performance.get('total_return_pct', 0):.2f}%)"
        )
        lines.append(
            f"   Cash: ${performance.get('cash', 0):,.2f}"
        )
        lines.append(
            f"   Equity: ${performance.get('equity', 0):,.2f}"
        )
        lines.append(
            f"   Positions: {performance.get('num_positions', 0)}"
        )
        lines.append("")

    lines.append("=" * 80)

    return "\n".join(lines)


def save_daily_summary_to_file(summary: str, log_dir: str = "./logs"):
    """
    Save daily summary to a dedicated summary file.

    Args:
        summary: Summary text to save
        log_dir: Directory to store summary files
    """
    log_path = Path(log_dir)
    log_path.mkdir(exist_ok=True)

    # Create summary file with date
    date_str = datetime.now().strftime("%Y-%m-%d")
    summary_file = log_path / f"daily_summary_{date_str}.txt"

    with open(summary_file, "w", encoding="utf-8") as f:
        f.write(summary)

    logger.bind(daily_operation=True).info(f"Daily summary saved to: {summary_file}")

    return summary_file
