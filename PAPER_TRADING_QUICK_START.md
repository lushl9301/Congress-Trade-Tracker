# Paper Trading - Quick Start Guide 🚀

## ✅ Implementation Complete!

All your requirements have been implemented:
1. ✅ Real-time stock price data (Yahoo Finance)
2. ✅ $10,000 starting capital (configurable)
3. ✅ STRONG_BUY signal filtering (configurable)
4. ✅ On-demand execution (not 24/7)
5. ✅ Daily reports with suggestions

---

## Prerequisites

### 1. Install Dependencies

```bash
pip install yfinance pandas
```

### 2. Install Playwright Chromium (for CapitolTrades scraping)

```bash
python -m playwright install chromium
```

### 3. Verify Configuration

Your `.env` file should have:
```bash
# Data Sources (only CT enabled - HSW/FMP now paid)
HSW_ENABLED=false
FMP_ENABLED=false
CT_ENABLED=true
CT_USE_CACHE=true

# Paper Trading
PAPER_TRADING_ENABLED=true
PAPER_INITIAL_CASH=10000
MARKET_DATA_PROVIDER=yfinance
SIGNAL_FILTER_MODE=strong_only
```

---

## 🎯 First Time Setup (3 commands)

```bash
# 1. Initialize database
python -m app.run init-db

# 2. Initialize paper account with $10,000
python -m app.run init-paper

# 3. Run first daily workflow
python -m app.run daily --strong-only
```

**That's it!** You now have paper trading running.

---

## 📅 On-Demand Usage (Your Workflow)

### Option A: One-Command Daily Run (Recommended)

```bash
# Complete workflow: ingest → signals → trade → report
python -m app.run daily --strong-only
```

This single command:
1. ✅ Fetches latest congressional trades (CapitolTrades)
2. ✅ Generates trading signals
3. ✅ Executes STRONG_BUY trades
4. ✅ Shows performance report with suggestions

**When to run**: Whenever you want to check for updates and trade

### Option B: Step-by-Step (Manual Control)

```bash
# 1. Fetch new congressional trades
python -m app.run ingest

# 2. Generate trading signals
python -m app.run signals

# 3. Execute trades (STRONG_BUY only)
python -m app.run trade --strong-only

# 4. View performance report
python -m app.run report
```

### Option C: Include NORMAL_BUY Signals

```bash
# Trade both STRONG and NORMAL signals
python -m app.run trade --include-normal

# Or in daily workflow
python -m app.run daily  # Uses config (strong_only by default)
```

---

## 📊 Example Output

### After Running Daily Workflow

```
================================================================================
CONGRESS TRADE TRACKER - DAILY REPORT
Generated: 2026-01-16 14:30:00
================================================================================

📊 PERFORMANCE SUMMARY
--------------------------------------------------------------------------------
  Account:          default
  Days Active:      7 days

  Initial Capital:  $   10,000.00
  Current Cash:     $    7,500.00
  Current Equity:   $    2,650.00
  Total NAV:        $   10,150.00

  Total Return:     $      150.00 (+1.50%)
  Daily Avg Return:         0.21%

  Total Trades:               5
  Open Positions:             3

💼 CURRENT PORTFOLIO
--------------------------------------------------------------------------------
Ticker   Shares   Avg Cost   Current      Value         P/L $    P/L %   Days
--------------------------------------------------------------------------------
NVDA       3.00  $  850.23  $  865.50  $  2,596.50  $    45.81   +1.80%      4
HAL       15.00  $   42.10  $   43.85  $    657.75  $    26.25   +4.16%      6
PG         2.00  $  155.20  $  153.80  $    307.60  $    -2.80   -0.90%      2
--------------------------------------------------------------------------------
TOTAL                                   $  3,561.85  $    69.26   +1.98%

📜 RECENT TRADES (Last 7 days)
--------------------------------------------------------------------------------
Date         Time     Ticker  Side   Shares      Price        Total
--------------------------------------------------------------------------------
2026-01-16   09:35    NVDA    BUY      3.00   $ 850.23   $  2,550.69
2026-01-15   10:20    HAL     BUY     15.00   $  42.10   $    631.50
2026-01-14   11:15    PG      BUY      2.00   $ 155.20   $    310.40
--------------------------------------------------------------------------------
Total Bought: $3,492.59
Total Sold:   $0.00
Net:          $3,492.59

💡 SUGGESTIONS
--------------------------------------------------------------------------------
  🎯 SELL HAL: Hit take profit target (+4.16% ≥ +20%)

  🎯 3 new STRONG_BUY signals available
     Run: python -m app.run trade --strong-only

  💰 Low exposure: 25.6% of NAV in stocks (consider trading new signals)

⚖️  RISK METRICS
--------------------------------------------------------------------------------
  Cash Allocation:     74.4%
  Stock Exposure:      25.6%
  Largest Position:   NVDA ($2,596.50, 25.6%)

  Position Limits:
    Max per ticker:     5.0%
    Max daily add:     10.0%
    Stop loss:         -8.0%
    Take profit:       +20.0%
    Max hold days:        30

================================================================================
END OF REPORT
================================================================================
```

---

## 🎮 Available Commands

### Setup Commands

```bash
# Initialize database schema
python -m app.run init-db

# Initialize paper account (default $10,000)
python -m app.run init-paper

# Initialize with custom amount
python -m app.run init-paper --cash 5000
```

### Trading Commands

```bash
# Fetch congressional trades (CapitolTrades)
python -m app.run ingest

# Generate trading signals
python -m app.run signals

# Execute trades - STRONG only (default)
python -m app.run trade --strong-only

# Execute trades - STRONG + NORMAL
python -m app.run trade --include-normal

# View performance report
python -m app.run report

# Full daily workflow
python -m app.run daily --strong-only
```

### Information Commands

```bash
# Show system status
python -m app.run status

# Help
python -m app.run --help
```

---

## 🔧 Configuration Options

Edit `.env` to customize:

```bash
# Initial capital
PAPER_INITIAL_CASH=10000  # Change to any amount

# Default signal filter
SIGNAL_FILTER_MODE=strong_only  # or strong_and_normal

# Price cache TTL
PRICE_CACHE_TTL_SECONDS=300  # 5 minutes

# Position sizing (already configured)
TARGET_PCT_STRONG=0.03    # 3% NAV per STRONG trade
TARGET_PCT_NORMAL=0.015   # 1.5% NAV per NORMAL trade
MAX_TICKER_PCT=0.05       # 5% max per ticker
MAX_DAILY_EXPOSURE=0.10   # 10% max new exposure per day

# Exit rules
MAX_HOLD_DAYS=30
STOP_LOSS_PCT=-0.08       # -8%
TAKE_PROFIT_PCT=0.20      # +20%
```

---

## 💡 Usage Tips

### When to Run

Since you don't have 24/7 execution yet:
- **Daily**: Run `python -m app.run daily --strong-only` once per day
- **Multiple times**: Run whenever you want to check for new trades
- **After major news**: Congress members might file disclosures

### Understanding Suggestions

The daily report gives you actionable suggestions:
- **🛑 SELL**: Stop loss triggered (protect capital)
- **🎯 SELL**: Take profit triggered (lock in gains)
- **⏰ SELL**: Max hold period reached (time-based exit)
- **🎯 New signals**: STRONG_BUY opportunities available
- **⚠️ Risk warnings**: Concentration, exposure issues

### Performance Tracking

- Reports show **daily P/L** for each position
- **Total return %** since account creation
- **Days active** to track long-term performance
- **Trade history** to review past decisions

---

## 🐛 Troubleshooting

### "yfinance not installed"

```bash
pip install yfinance pandas
```

### "Playwright not installed" or "chromium not found"

```bash
pip install playwright
python -m playwright install chromium
```

### "No trades in last 7 days"

This is normal if:
- No new congressional disclosures
- No signals met STRONG_BUY criteria (score ≥ 80)
- All signals already traded

**Solution**: Wait for new disclosures or lower filter to include NORMAL:
```bash
python -m app.run trade --include-normal
```

### "Insufficient cash"

You've deployed most of your $10k capital. Options:
1. Wait for positions to exit (stop/take/time)
2. Manually sell a position (future feature)
3. Reset account (delete DB, re-initialize)

---

## 📈 Example Daily Routine

### Morning Routine (5 minutes)

```bash
# 1. Run daily workflow
python -m app.run daily --strong-only

# 2. Review the report
# - Check new trades
# - Review suggestions
# - Note any exit triggers

# 3. Done!
```

That's it! The system:
- ✅ Fetches latest congressional trades
- ✅ Filters for STRONG_BUY signals only
- ✅ Executes trades automatically
- ✅ Shows you what happened
- ✅ Gives you suggestions

---

## 🎯 Next Steps

### Short Term (This Week)

1. ✅ Run daily workflow for 7 days
2. ✅ Review performance each day
3. ✅ Note which congressional trades are profitable
4. ✅ Adjust strategy if needed (lower threshold, include NORMAL)

### Medium Term (This Month)

1. Compare STRONG_ONLY vs STRONG+NORMAL performance
2. Track verification rates (CT vs RapidAPI when integrated)
3. Identify best-performing politicians
4. Analyze sector trends

### Long Term (Future)

1. Move to cloud server for 24/7 execution
2. Integrate RapidAPI as 2nd source
3. Add backtesting with historical data
4. Consider live trading if profitable

---

## ❓ FAQ

**Q: How often should I run the daily workflow?**
A: Once per day is fine. Congressional disclosures don't change that frequently.

**Q: What if I want to trade more aggressively?**
A: Use `--include-normal` to trade both STRONG and NORMAL signals (more trades, potentially lower quality).

**Q: Can I change the starting capital?**
A: Yes, but you need to reset the database:
```bash
rm data/app.db
python -m app.run init-db
python -m app.run init-paper --cash 5000
```

**Q: How do I know if my strategy is working?**
A: Check the daily report's "Total Return %" - if positive after 1+ months, it's working.

**Q: When will 24/7 automation be ready?**
A: It's a TODO for when you have a cloud server or Mac mini. The code is ready, just needs deployment.

---

## 📞 Support

For issues or questions:
1. Check this guide first
2. Review the logs in `app/logging.py`
3. Check database at `data/app.db` with SQLite browser
4. Review code in `app/paper_*.py` files

---

**Happy Paper Trading!** 🎉

Your system is ready to:
- Track congressional trades
- Generate signals automatically
- Execute paper trades
- Report performance daily
- Suggest actions

All with $10,000 virtual capital and STRONG_BUY filtering.

Run `python -m app.run daily --strong-only` to get started! 🚀
