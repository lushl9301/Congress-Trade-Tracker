# Logging and Review Guide

**All your daily runs are automatically logged for review!**

This guide explains what gets logged, where to find logs, and how to review your testing week.

---

## 📂 Log Files Location

All logs are stored in `./logs/` directory:

```
Congress-Trade-Tracker/
├── logs/
│   ├── app.log                                    # Main application log (rotated)
│   ├── daily_operations_2026-01-17.log           # Daily operations (one per day)
│   ├── session_daily_20260117_090000.log         # Each daily run (detailed)
│   ├── session_daily_20260117_160000.log         # Second run same day
│   ├── daily_summary_2026-01-17.txt              # Daily summary (easy review)
│   └── ...
```

---

## 📊 Log File Types

### 1. Session Logs (`session_daily_YYYYMMDD_HHMMSS.log`)

**What**: Complete capture of each `daily` command run
**Created**: Every time you run `python -m app.run daily`
**Contains**:
- Full workflow execution log
- All 4 steps (ingest, signals, trade, report)
- Every trade executed with details
- Performance report
- Daily summary
- Errors/warnings
- Execution time

**Example filename**: `session_daily_20260117_143052.log`

**Best for**: Detailed review of specific run

**Sample content**:
```
================================================================================
Congress Trade Tracker - Session Log
Command: daily
Started: 2026-01-17 14:30:52
================================================================================

------------------------------------------------------------
DAILY WORKFLOW START
------------------------------------------------------------
[2026-01-17 14:30:52] [INFO   ] Date: 2026-01-17 14:30:52
[2026-01-17 14:30:52] [INFO   ] Mode: STRONG_ONLY
[2026-01-17 14:30:52] [INFO   ] Reset DB: False
[2026-01-17 14:30:52] [INFO   ] Reset Cache: False

------------------------------------------------------------
Step 1/4: Ingesting Congressional Trades
------------------------------------------------------------

Ingestion Results:
[2026-01-17 14:30:55] [INFO   ]   New events: 12
[2026-01-17 14:30:55] [INFO   ]   Duplicates: 3
[2026-01-17 14:30:55] [INFO   ]   Total events: 145

... (continues)
```

---

### 2. Daily Summary (`daily_summary_YYYY-MM-DD.txt`)

**What**: Concise summary of the day's activity
**Created**: At the end of each `daily` command
**Contains**:
- Date of run
- Ingestion stats (new events)
- Signal generation stats (STRONG, NORMAL, etc.)
- Trading stats (executed, skipped)
- List of all trades executed with prices
- Performance metrics (NAV, return %, P/L)

**Example filename**: `daily_summary_2026-01-17.txt`

**Best for**: Quick daily review, week-at-a-glance

**Sample content**:
```
================================================================================
DAILY RUN SUMMARY
================================================================================
Date: 2026-01-17 14:30:52

📥 INGESTION:
   New events: 12
   Duplicates: 3
   Total events: 145

🎯 SIGNALS:
   STRONG: 3
   NORMAL: 5
   WATCH: 8
   IGNORE: 15

💼 TRADING:
   Signals processed: 3
   Trades executed: 2
   Trades skipped: 1

   Executed Trades:
      • BUY 6.90 HAL @ $43.50 ($300.15)
      • BUY 3.45 NVDA @ $870.20 ($3,002.19)

📊 PERFORMANCE:
   NAV: $10,303.34
   Return: $303.34 (3.03%)
   Cash: $6,697.66
   Equity: $3,605.68
   Positions: 5

================================================================================
```

---

### 3. Daily Operations Log (`daily_operations_YYYY-MM-DD.log`)

**What**: All daily operations in chronological order
**Created**: One file per day (rotates at midnight)
**Contains**:
- All daily runs for that day
- System events
- Application logs
- Errors and warnings

**Example filename**: `daily_operations_2026-01-17.log`

**Best for**: Debugging issues, seeing all activity for a day

---

### 4. Main Application Log (`app.log`)

**What**: Complete application log with rotation
**Created**: Always (rotates at 10MB)
**Contains**:
- Everything from all components
- All function calls and operations
- Detailed debug information
- Stack traces for errors

**Best for**: Deep debugging, technical troubleshooting

---

## 📅 Weekly Review Process

### Step 1: Check Daily Summaries (5 minutes)

```bash
# View all daily summaries from this week
ls -lh logs/daily_summary_*.txt

# Quick read of each day
cat logs/daily_summary_2026-01-17.txt
cat logs/daily_summary_2026-01-18.txt
cat logs/daily_summary_2026-01-19.txt
# ... etc
```

**What to look for**:
- ✅ How many trades executed each day?
- ✅ What's the NAV progression?
- ✅ What's the return % trajectory?
- ✅ Which tickers were traded?

---

### Step 2: Review Session Logs (10 minutes)

```bash
# List all daily sessions
ls -lh logs/session_daily_*.log

# Read specific session if you saw something interesting
less logs/session_daily_20260117_143052.log
```

**What to look for**:
- 🔍 Why were certain trades executed?
- 🔍 What signals triggered them?
- 🔍 Were there any errors or warnings?
- 🔍 How long did each step take?

---

### Step 3: Aggregate Weekly Stats (Python script)

I've created a helper script for you:

```bash
# Create this script: scripts/weekly_review.py
```

```python
#!/usr/bin/env python3
"""
Weekly review script - aggregates all daily summaries.
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
        print("=" * 80)


if __name__ == '__main__':
    main()
```

**Usage**:
```bash
python scripts/weekly_review.py
```

**Output**:
```
================================================================================
WEEKLY REVIEW - Paper Trading Performance
================================================================================

📅 Daily Performance:

Date         NAV         Return $   Return %   Trades  Positions
--------------------------------------------------------------------------------
2026-01-17   $10,303.34  $303.34      3.03%       2          5
2026-01-18   $10,456.78  $456.78      4.57%       3          7
2026-01-19   $10,321.45  $321.45      3.21%       1          6
2026-01-20   $10,589.23  $589.23      5.89%       2          8
2026-01-21   $10,712.00  $712.00      7.12%       1          8
--------------------------------------------------------------------------------

📊 Weekly Summary:
   Trading days: 5
   Initial NAV:  $10,000.00
   Final NAV:    $10,712.00
   Total Return: +$712.00 (+7.12%)
   Total Trades: 9
   Avg Trades/Day: 1.8

✅ EXCELLENT: +5% in one week is very strong!

================================================================================
```

---

## 🔍 Common Review Questions

### Q: What was my total return this week?

**Answer**:
```bash
# Run weekly review script
python scripts/weekly_review.py

# Or manually:
cat logs/daily_summary_2026-01-21.txt | grep "Return:"
# Compare last NAV to $10,000 starting capital
```

---

### Q: Which trades made money? Which lost?

**Answer**: Check session logs for individual trades, then look up current prices

```bash
# Find all trades
grep "BUY.*@" logs/session_daily_*.log

# Example: You bought HAL @ $43.50
# Current price: $45.80
# Profit: +5.3%
```

---

### Q: Why did I buy/sell this ticker?

**Answer**: Search session logs for the ticker

```bash
grep -A 10 "HAL" logs/session_daily_20260117_143052.log
```

You'll see:
- Signal score and reasons
- Who traded it (politician)
- Amount disclosed
- Delay days

---

### Q: Were there any errors or warnings?

**Answer**:
```bash
# Check all errors
grep "ERROR" logs/app.log

# Check all warnings
grep "WARNING" logs/app.log

# Check specific session
grep -E "ERROR|WARNING" logs/session_daily_20260117_143052.log
```

---

### Q: How long does the daily workflow take?

**Answer**: Session log footer shows duration

```bash
tail -20 logs/session_daily_20260117_143052.log
```

Shows:
```
================================================================================
Session Summary
================================================================================
Ended: 2026-01-17 14:31:15
Duration: 23.5 seconds
Errors: 0
Warnings: 1
================================================================================
```

---

## 📈 Best Practices

### Daily (2 minutes)
1. Run `python -m app.run daily --strong-only`
2. Note the summary output (NAV, return %, trades)
3. Done! (Logs are automatic)

### Weekly (15 minutes)
1. Run `python scripts/weekly_review.py`
2. Review aggregate stats
3. Check if profitable / on track
4. Read 1-2 session logs to understand decisions

### If Issues Arise
1. Check `app.log` for errors
2. Check specific session log for that day
3. Review daily_operations log for context

---

## 🗂️ Log Retention

**Automatic cleanup**:
- `session_daily_*.log`: Kept forever (manual cleanup)
- `daily_summary_*.txt`: Kept for 90 days
- `daily_operations_*.log`: Kept for 90 days
- `app.log`: Rotated at 10MB, kept for 30 days

**To manually clean old logs**:
```bash
# Delete session logs older than 90 days
find logs/ -name "session_daily_*.log" -mtime +90 -delete

# Archive old logs
tar -czf logs_backup_$(date +%Y%m%d).tar.gz logs/
```

---

## 💡 Tips for Effective Review

### 1. Create a Spreadsheet

Track key metrics in Google Sheets or Excel:

| Date | NAV | Return % | Trades | Winners | Losers | Notes |
|------|-----|----------|--------|---------|--------|-------|
| 1/17 | $10,303 | +3.03% | 2 | HAL +5% | - | Good start |
| 1/18 | $10,456 | +4.57% | 3 | NVDA +8% | MSFT -2% | Tech strong |
| ... | | | | | | |

### 2. Tag Interesting Days

```bash
# Add comment to daily summary
echo "# NOTE: Strong rally day, tech stocks up 5%" >> logs/daily_summary_2026-01-17.txt
```

### 3. Screenshot Reports

Save performance reports as images for easy comparison:
```bash
python -m app.run report > daily_report_$(date +%Y%m%d).txt
```

---

## ⚙️ Advanced: Export to CSV

```python
# scripts/export_to_csv.py
import csv
from pathlib import Path
from weekly_review import parse_summary_file

summary_files = sorted(Path('./logs').glob('daily_summary_*.txt'))
metrics = [parse_summary_file(f) for f in summary_files]

with open('paper_trading_results.csv', 'w', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=['date', 'nav', 'return_dollars', 'return_pct', 'trades_executed', 'positions'])
    writer.writeheader()
    writer.writerows(metrics)

print("✅ Exported to paper_trading_results.csv")
```

Then import into Excel/Google Sheets for charts and analysis.

---

## 📞 Troubleshooting

### Issue: No logs being created

**Check**:
```bash
ls -la logs/
```

If directory doesn't exist:
```bash
mkdir -p logs
```

Then run daily workflow again.

---

### Issue: Logs are too large

**Solution**: Rotate or compress old logs
```bash
# Compress logs older than 7 days
find logs/ -name "session_daily_*.log" -mtime +7 -exec gzip {} \;

# View compressed logs
zless logs/session_daily_20260110_143052.log.gz
```

---

### Issue: Can't find specific information

**Search across all logs**:
```bash
# Search all session logs for ticker
grep -r "NVDA" logs/session_*.log

# Search for dates
grep -r "2026-01-17" logs/

# Search for errors
grep -r "ERROR" logs/
```

---

## 📋 Summary

**You now have automatic logging for**:
- ✅ Every daily run (full session log)
- ✅ Every day's summary (easy review)
- ✅ All operations (daily operations log)
- ✅ Everything (main app log)

**For weekly review**:
1. Run `python scripts/weekly_review.py`
2. Check daily summaries
3. Review specific sessions if needed

**All logs saved in `./logs/` directory**

No manual work needed - everything is captured automatically!

---

**Last Updated**: 2026-01-16
**Ready to use**: Yes, logs will be created automatically on first `daily` run
