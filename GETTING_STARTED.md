# Getting Started - Congress Trade Tracker

Welcome! Your Congress Trade Tracker is fully configured and ready to use with real congressional trading data from multiple sources.

---

## ✅ Current Status

**Your Configuration**:
- ✅ House Stock Watcher (HSW) - Enabled & Free
- ✅ Financial Modeling Prep (FMP) - Enabled with API Key
- ✅ Cross-Verification Strategy - Active
- ✅ All tests passing (46/46)
- ✅ Database schema ready
- ✅ Dummy data tested successfully

**Your API Key**: Configured in `.env` file (safely gitignored)

---

## Quick Start (5 minutes)

### Step 1: Test Your Setup

Run the comprehensive test script:

```bash
python test_real_api.py
```

**Expected output**:
```
==================================
CONGRESS TRADE TRACKER - REAL API INTEGRATION TEST
==================================

1. TESTING CONFIGURATION
  ✓ HSW Enabled: True
  ✓ FMP Enabled: True
  ✓ FMP API Key: XpTKRCpxux... (length: 32)
  ✓ Strategy: verify
  ✅ Configuration looks good!

2. TESTING DATA SOURCE AVAILABILITY
  ✅ HSW Available: True
  ✅ FMP Available: True

3. TESTING SAMPLE DATA FETCH
  ✅ HSW returned 150 total trades
     Sample: AAPL - BUY
     Member: Hon. John Smith
     Amount: $15,001 - $50,000

  ✅ FMP returned 50 trades
     Sample: TSLA - BUY
     Member: Jane Doe
     Amount: $50,001 - $100,000

4. TESTING CROSS-VERIFICATION
  ✅ Retrieved 200 trades

  Verification Statistics:
    Verified:   120 (60.0%)
    Unverified: 80 (40.0%)

5. TESTING FULL INGESTION PIPELINE
  ✅ Ingestion Complete!

  Results:
    Status:         success
    Fetched:        200 trades
    New Events:     195
    Duplicates:     5
    Verified:       120 (60.0%)
    Unverified:     80 (40.0%)

🎉 All tests passed! Your multi-source system is working perfectly!
```

---

### Step 2: Run Your First Ingestion

Fetch the latest congressional trading data:

```bash
python -m app.run ingest
```

**What happens**:
1. Connects to House Stock Watcher (free, no limit)
2. Connects to Financial Modeling Prep (250 requests/day limit)
3. Fetches recent congressional trades
4. Cross-verifies trades from both sources
5. Stores in local SQLite database

**Expected output**:
```
Starting ingestion: strategy=verify
Initializing House Stock Watcher source
Initializing Financial Modeling Prep source
Initializing DataSourceManager with 2 sources, strategy=verify

Fetching from house_stock_watcher
Successfully fetched 150 trades from house_stock_watcher

Fetching from financial_modeling_prep
Successfully fetched 50 trades from financial_modeling_prep

Cross-verifying data from 2 sources

Ingestion complete:
  - Fetched: 200 trades
  - New events: 195
  - Duplicates: 5
  - Verified: 120 (60.0%)
  - Unverified: 80 (40.0%)
```

---

### Step 3: Check Status

View your system status:

```bash
python -m app.run status
```

**Expected output**:
```
Configuration:
  Data Sources:
    - HSW: ✅ Enabled & Available
    - FMP: ✅ Enabled & Available (API key configured)
    - Strategy: verify (cross-verification)
  Trading: ⚠️  Disabled (paper mode)

Database:
  Path: ./data/app.db
  Total trades: 195
  Verified: 120 (61.5%)
  Unverified: 75 (38.5%)

Rate Limits (Today):
  HSW: 3/250 requests (1.2%)
  FMP: 2/250 requests (0.8%)
```

---

## Understanding Your Data

### Verified vs Unverified Trades

**Verified Trades** (✅):
- Reported by **both** HSW and FMP
- Higher confidence (cross-checked)
- Typically members who trade frequently
- Better signal quality

**Unverified Trades** (⚠️):
- Reported by only **one** source
- Still valid, just not cross-confirmed
- Often chamber-specific (House-only or Senate-only)
- Normal and expected

### Verification Rate Expectations

| Verification Rate | Meaning |
|------------------|---------|
| 50-70% | ✅ **Excellent** - High overlap between sources |
| 30-50% | ✅ **Good** - Normal variance between chambers |
| 10-30% | ⚠️ **Low** - One source may have limited data |
| <10% | ❌ **Check** - Possible configuration issue |

---

## Daily Usage

### Recommended Schedule

For your use case (checking a few times per day):

```bash
# Morning check (before market open)
python -m app.run daily

# Afternoon check (mid-day)
python -m app.run ingest

# Evening check (after market close)
python -m app.run daily
```

The `daily` command runs:
1. `ingest` - Fetch new trades
2. `signals` - Generate trading signals
3. `reconcile` - Sync IBKR state (if enabled)
4. Creates PnL snapshot

### Rate Limit Management

With 3 runs per day, you use:

| Source | Requests/Run | Daily Total | Limit | Usage % |
|--------|-------------|-------------|-------|---------|
| HSW    | 1-2         | 3-6         | 250   | 2.4%    |
| FMP    | 1-2         | 3-6         | 250   | 2.4%    |

✅ **You're using <3% of your daily limit!**

---

## Database Queries

### View Recent Trades

```bash
sqlite3 data/app.db "
SELECT
    ticker,
    transaction_type,
    member_name,
    verified,
    verification_sources
FROM congress_trade_events
ORDER BY created_at DESC
LIMIT 10
"
```

### View Verified Trades Only

```bash
sqlite3 data/app.db "
SELECT
    ticker,
    transaction_type,
    amount_low,
    amount_high,
    verification_sources
FROM congress_trade_events
WHERE verified = 1
ORDER BY disclosure_date DESC
LIMIT 20
"
```

### Count by Verification Status

```bash
sqlite3 data/app.db "
SELECT
    verification_status,
    COUNT(*) as count,
    ROUND(COUNT(*) * 100.0 / (SELECT COUNT(*) FROM congress_trade_events), 1) as percentage
FROM congress_trade_events
GROUP BY verification_status
"
```

---

## Configuration Options

Your `.env` file is already configured optimally. Here are the settings:

### Current Configuration

```bash
# Data Sources
HSW_ENABLED=true              # ✅ Free, no API key
FMP_ENABLED=true              # ✅ Your API key configured
DATA_SOURCE_STRATEGY=verify   # ✅ Cross-verification enabled

# Database
DB_PATH=./data/app.db         # ✅ Local SQLite database

# Trading (Safe Defaults)
TRADING_MODE=paper            # ✅ Paper trading only
TRADING_ENABLED=false         # ✅ No actual trades placed
```

### Available Strategies

If you want to change strategies:

```bash
# Cross-verify (RECOMMENDED - what you're using)
DATA_SOURCE_STRATEGY=verify

# Single source only (HSW)
DATA_SOURCE_STRATEGY=primary_only
FMP_ENABLED=false

# Fallback (try HSW, use FMP if HSW fails)
DATA_SOURCE_STRATEGY=fallback

# Merge all (no deduplication)
DATA_SOURCE_STRATEGY=all
```

---

## Troubleshooting

### "No data sources available"

**Cause**: Network connectivity or API issues

**Solution**:
```bash
# Check source health
python -c "
from app.data_sources import HouseStockWatcherSource, FinancialModelingPrepSource
from app.config import Config

config = Config()
hsw = HouseStockWatcherSource()
fmp = FinancialModelingPrepSource(api_key=config.FMP_API_KEY)

print('HSW:', hsw.health_check())
print('FMP:', fmp.health_check())
"
```

---

### "FMP API key invalid"

**Cause**: Incorrect API key or expired

**Solution**:
1. Check your API key at https://financialmodelingprep.com/dashboard
2. Update `.env` file:
   ```bash
   FMP_API_KEY=your_new_key_here
   ```
3. Test: `python test_real_api.py`

---

### "Rate limit exceeded"

**Cause**: Too many requests (>250/day for FMP)

**Solution**:
- Wait until next day (limits reset at midnight UTC)
- Use HSW only temporarily:
  ```bash
  export FMP_ENABLED=false
  python -m app.run ingest
  ```

---

### Low verification rate (<30%)

**Cause**: Sources cover different data sets

**Normal**: HSW = House only, FMP = Senate/House mix

**Action**: No action needed - this is expected

---

## Next Steps

### 1. Enable Trading (When Ready)

⚠️ **CAUTION**: Only when you're ready to execute trades

```bash
# In .env
TRADING_ENABLED=true   # Enable order placement
TRADING_MODE=paper     # Keep paper trading for testing
```

Then:
```bash
python -m app.run signals  # Generate trading signals
python -m app.run trade    # Execute trades (paper)
```

### 2. Set Up Monitoring

View your positions:
```bash
python -m app.run status --verbose
```

### 3. Review Documentation

- `MULTI_SOURCE_IMPLEMENTATION.md` - Complete implementation guide
- `TESTING_RESULTS.md` - Test coverage and results
- `CLAUDE.md` - Strategy and configuration details

---

## Support

### Check Logs

```bash
# View recent logs
tail -f logs/app.log

# Search for errors
grep ERROR logs/app.log
```

### Validate Configuration

```bash
python -c "
from app.config import Config
config = Config()
errors = config.validate()
if errors:
    for error in errors:
        print(f'⚠️  {error}')
else:
    print('✅ Configuration valid!')
"
```

### Run Full Test Suite

```bash
# All 46 tests
pytest tests/ -v

# Integration tests only
pytest tests/test_integration_dummy_data.py -v

# Data source tests only
pytest tests/test_data_sources.py -v
```

---

## Summary

You're all set! Your system is:

✅ Configured with real API keys
✅ Using two free data sources
✅ Cross-verifying for data quality
✅ Ready to fetch congressional trades
✅ Safe (paper trading, orders disabled)
✅ Well-tested (46/46 tests passing)

**Start now**:
```bash
python test_real_api.py          # Verify everything works
python -m app.run ingest         # Fetch first batch of data
python -m app.run status         # Check your results
```

Enjoy tracking congressional trades! 🎉

---

**Questions?** Check the documentation in `MULTI_SOURCE_IMPLEMENTATION.md`

**Issues?** Run `python test_real_api.py` for diagnostics
