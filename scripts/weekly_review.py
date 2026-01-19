#!/usr/bin/env python3
"""
Weekly review script - aggregates all daily summaries.

Usage:
    python scripts/weekly_review.py
"""

import glob
import re
from datetime import datetime, timedelta
from pathlib import Path


def parse_summary_file(filepath):
    """Extract key metrics from daily summary file."""
    with open(filepath, 'r') as f:
        content = f.read()

    metrics = {}

    # Extract date
    if match := re.search(r'Date: (\d{4}-\d{2}-\d{2})', content):
        metrics['date'] = match.group(1)

    # Extract NAV
    if match := re.search(r'NAV: \$([0-9,]+\.\d{2})', content):
        metrics['nav'] = float(match.group(1).replace(',', ''))

    # Extract return
    if match := re.search(r'Return: \$([0-9,\-]+\.\d{2}) \(([0-9\-\.]+)%\)', content):
        metrics['return_dollars'] = float(match.group(1).replace(',', ''))
        metrics['return_pct'] = float(match.group(2))

    # Extract trades executed
    if match := re.search(r'Trades executed: (\d+)', content):
        metrics['trades_executed'] = int(match.group(1))

    # Extract positions
    if match := re.search(r'Positions: (\d+)', content):
        metrics['positions'] = int(match.group(1))

    return metrics


def main():
    """Generate weekly review."""
    logs_dir = Path('./logs')
    summary_files = sorted(logs_dir.glob('daily_summary_*.txt'))

    if not summary_files:
        print("❌ No daily summary files found!")
        print(f"   Looking in: {logs_dir.absolute()}")
        print()
        print("💡 Run paper trading first:")
        print("   python -m app.run daily --strong-only")
        return

    print("=" * 80)
    print("WEEKLY REVIEW - Paper Trading Performance")
    print("=" * 80)
    print()

    all_metrics = []
    for filepath in summary_files:
        metrics = parse_summary_file(filepath)
        if metrics:
            all_metrics.append(metrics)

    if not all_metrics:
        print("❌ Could not parse any metrics from summaries")
        return

    # Sort by date
    all_metrics.sort(key=lambda x: x.get('date', ''))

    # Print daily breakdown
    print("📅 Daily Performance:")
    print()
    print(f"{'Date':<12} {'NAV':>12} {'Return $':>12} {'Return %':>10} {'Trades':>8} {'Positions':>10}")
    print("-" * 80)

    for m in all_metrics:
        print(
            f"{m.get('date', 'N/A'):<12} "
            f"${m.get('nav', 0):>11,.2f} "
            f"${m.get('return_dollars', 0):>11,.2f} "
            f"{m.get('return_pct', 0):>9.2f}% "
            f"{m.get('trades_executed', 0):>8} "
            f"{m.get('positions', 0):>10}"
        )

    print("-" * 80)

    # Calculate weekly summary
    if all_metrics:
        first_day = all_metrics[0]
        last_day = all_metrics[-1]

        initial_nav = 10000.00  # Starting capital
        final_nav = last_day.get('nav', initial_nav)
        total_return = final_nav - initial_nav
        total_return_pct = (total_return / initial_nav) * 100

        total_trades = sum(m.get('trades_executed', 0) for m in all_metrics)

        print()
        print("📊 Weekly Summary:")
        print(f"   Trading days: {len(all_metrics)}")
        print(f"   Initial NAV:  ${initial_nav:,.2f}")
        print(f"   Final NAV:    ${final_nav:,.2f}")
        print(f"   Total Return: ${total_return:+,.2f} ({total_return_pct:+.2f}%)")
        print(f"   Total Trades: {total_trades}")
        print(f"   Avg Trades/Day: {total_trades / len(all_metrics):.1f}")
        print()

        # Performance assessment
        if total_return_pct > 5:
            print("✅ EXCELLENT: +5% in one week is very strong!")
        elif total_return_pct > 2:
            print("✅ GOOD: +2% weekly return is solid performance")
        elif total_return_pct > 0:
            print("🟡 POSITIVE: Small gains, strategy may need tuning")
        elif total_return_pct > -2:
            print("🟡 SLIGHTLY NEGATIVE: Consider analyzing losing trades")
        else:
            print("🔴 CONCERNING: Significant losses, review strategy urgently")

        print()
        print("📄 Session Logs Available:")
        session_files = sorted(logs_dir.glob('session_daily_*.log'))
        print(f"   Total sessions: {len(session_files)}")
        if session_files:
            print(f"   First: {session_files[0].name}")
            print(f"   Last:  {session_files[-1].name}")
        print()
        print("   View detailed logs:")
        print("      cat logs/session_daily_YYYYMMDD_HHMMSS.log")
        print()

        print("=" * 80)


if __name__ == '__main__':
    main()
