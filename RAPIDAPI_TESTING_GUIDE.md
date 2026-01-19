# RapidAPI Politician Trade Tracker - Testing Guide

## Current Status

⚠️ **API testing blocked in sandbox environment** - All external network connections to RapidAPI return 403 errors due to network restrictions in the development environment.

## What We Know

### API Details
- **Service**: Politician Trade Tracker
- **Host**: `politician-trade-tracker1.p.rapidapi.com`
- **Your API Key**: `1faaecd8e4msh50673e7d9ebfdf4p1e7f70jsn3d98ade81d85`
- **RapidAPI Page**: https://rapidapi.com/s5yux/api/politician-trade-tracker1

### Known Endpoints (from research)
1. **`/get_politicians`** - Returns list of politicians with metadata (State, Party, etc.)
2. **`/get_profile?name=<name>`** - Returns politician profile and "most traded sectors"

### Unknown Information
- ❓ Does it provide actual trade transactions (ticker, date, amount)?
- ❓ Or just aggregated data (sectors, statistics)?
- ❓ Is the API key subscribed to the service?
- ❓ What are the rate limits and pricing?
- ❓ Is there a free tier?

## What You Need to Do

### Step 1: Run Local Test Script 🚀

On your local machine with network access:

```bash
# Install dependency
pip install httpx

# Run the comprehensive test script
python test_rapidapi_local.py
```

This script will:
1. ✅ Test if your API key is subscribed
2. ✅ Test all known endpoints
3. ✅ Discover additional endpoints
4. ✅ Save response data to JSON files
5. ✅ Analyze if integration is worthwhile
6. ✅ Provide recommendations

### Step 2: Check Subscription Status

If you get **403 Forbidden** errors:

1. Visit: https://rapidapi.com/s5yux/api/politician-trade-tracker1
2. Click **"Subscribe to Test"** or pricing button
3. Check if there's a **free tier**
4. Subscribe to a plan (free or paid)
5. Re-run the test script

### Step 3: Analyze Results

After successful testing, check the generated JSON files:

```bash
# View politicians list
cat rapidapi_politicians.json | python -m json.tool | head -50

# View profile examples
cat rapidapi_profile_Nancy_Pelosi.json | python -m json.tool
```

**Key questions to answer:**
- Does the API return individual trade transactions?
- What fields are included? (ticker, date, amount, transaction type?)
- Is the data fresh and up-to-date?
- Does it overlap with our existing sources (HSW, FMP, CapitolTrades)?

## Integration Decision Tree

```
┌─────────────────────────────────────┐
│  Does API provide trade             │
│  transactions with ticker,          │
│  date, and amount?                  │
└──────────┬──────────────────────────┘
           │
    ┌──────┴──────┐
    │             │
   YES           NO
    │             │
    ▼             ▼
┌─────────────┐  ┌──────────────────┐
│ Is data     │  │ NOT WORTH        │
│ different   │  │ INTEGRATING      │
│ from HSW/   │  │                  │
│ FMP/CT?     │  │ (Just politician │
└──────┬──────┘  │  metadata, not   │
       │         │  trade data)     │
   ┌───┴───┐     └──────────────────┘
   │       │
  YES     NO
   │       │
   ▼       ▼
┌─────────────┐  ┌──────────────────┐
│ INTEGRATE   │  │ NOT WORTH        │
│ AS 4TH      │  │ INTEGRATING      │
│ SOURCE      │  │                  │
│             │  │ (Duplicate data, │
│ ✅ Adds      │  │  already have    │
│    verifi-  │  │  better sources) │
│    cation   │  └──────────────────┘
└─────────────┘
```

## Expected Outcomes

### Scenario A: API Provides Trade Transactions ✅

**Example response we're hoping for:**
```json
{
  "trades": [
    {
      "politician": "Nancy Pelosi",
      "ticker": "NVDA",
      "transaction_type": "Purchase",
      "transaction_date": "2025-12-15",
      "disclosure_date": "2026-01-10",
      "amount_low": 50000,
      "amount_high": 100000,
      "chamber": "House",
      "party": "Democrat"
    }
  ]
}
```

**Action**: Integrate as 4th source for cross-verification

**Benefits**:
- 4-way cross-verification (HSW + FMP + CT + RapidAPI)
- Higher verification confidence (80-90% vs 75-85%)
- Redundancy if one source fails
- REST API (easier than Playwright scraping)

**Implementation** (if this scenario):
1. Create `app/data_sources/rapidapi_politician_tracker.py`
2. Implement `RapidAPISource` class
3. Add normalization logic
4. Update config with `RAPIDAPI_ENABLED` and `RAPIDAPI_KEY`
5. Update manager to include 4th source
6. Test cross-verification with 4 sources

### Scenario B: API Only Provides Aggregated Data ❌

**Example response we DON'T want:**
```json
{
  "name": "Nancy Pelosi",
  "state": "California",
  "party": "Democrat",
  "most_traded_sectors": {
    "Technology": 45.2,
    "Healthcare": 23.1,
    "Finance": 15.7
  },
  "total_trades_count": 127,
  "avg_trade_size": "$25,000"
}
```

**Action**: Do NOT integrate

**Reasons**:
- No individual trade data (can't verify specific transactions)
- Just statistics/aggregations (not useful for our strategy)
- Can't cross-verify with other sources
- Doesn't help with trading signals

### Scenario C: API Key Not Subscribed ⚠️

**Error message:**
```
403 Forbidden
```

**Action**: Subscribe on RapidAPI

**Steps**:
1. Visit API page
2. Check pricing (hope for free tier)
3. Subscribe if free, evaluate if paid
4. Re-test

## Current System Status

You currently have **3 working data sources**:

| Source | Status | Coverage | Type | Cost |
|--------|--------|----------|------|------|
| **House Stock Watcher** | ✅ Ready | House | JSON API | Free |
| **Financial Modeling Prep** | ✅ Ready | H+S | REST API | Free tier |
| **CapitolTrades** | ✅ Ready | H+S | Scraping | Free |

**Current verification rate**: 75-85% (very good!)

## Recommendation

### Before Testing
**Don't code anything yet** - Test first to see if the API is worth integrating.

### After Testing

**If Scenario A (good trade data)**:
- ✅ Integrate as 4th source
- ✅ Improves verification to 80-90%
- ✅ Adds redundancy

**If Scenario B (just metadata)**:
- ❌ Skip integration
- ✅ Stick with 3 sources (already excellent)
- ✅ 75-85% verification is very good

**If Scenario C (not subscribed)**:
- Check pricing
- If free: subscribe and re-test
- If paid: evaluate cost vs. benefit
  - We already have 3 free sources
  - Paid API only worth it if significantly better data

## Testing Commands

```bash
# On your local machine (NOT in sandbox)

# 1. Install dependencies
pip install httpx

# 2. Run comprehensive test
python test_rapidapi_local.py

# 3. View results
ls -lh rapidapi_*.json

# 4. Examine data structure
cat rapidapi_politicians.json | python -m json.tool | less
cat rapidapi_profile_Nancy_Pelosi.json | python -m json.tool

# 5. Search for trade-related fields
cat rapidapi_profile_Nancy_Pelosi.json | grep -i "trade\|ticker\|stock\|transaction"
```

## Next Steps

1. **YOU**: Run `python test_rapidapi_local.py` on your local machine
2. **YOU**: Share the output and JSON files
3. **ME**: Analyze data structure
4. **ME**: Recommend integrate vs. skip
5. **IF INTEGRATE**: Implement RapidAPISource class
6. **IF SKIP**: Continue with existing 3 sources

## Questions?

- **Q**: Can't the sandbox test it?
- **A**: No, sandbox blocks external HTTPS to RapidAPI (security restriction)

- **Q**: Do we need a 4th source?
- **A**: No, 3 sources with 75-85% verification is already excellent. 4th source is only worth it if it provides unique/better data.

- **Q**: What if it's paid?
- **A**: Evaluate cost vs. benefit. We have 3 free sources already working well.

- **Q**: How long does testing take?
- **A**: 2-3 minutes to run the script and review results

---

**Current Status**: ⏸️ Waiting for local test results before proceeding with development.
