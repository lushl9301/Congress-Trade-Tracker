# IBKR Paper Trading Setup and Testing Guide

**Status**: ✅ IBKR integration code COMPLETE, ready for testing

This guide helps you set up and test Interactive Brokers (IBKR) paper trading integration.

---

## Overview

The Congress Trade Tracker now supports **TWO paper trading modes**:

1. **Virtual Paper Trading** (app/paper_account.py)
   - Fully virtual, no broker needed
   - Uses Yahoo Finance for prices
   - $10,000 starting capital
   - ✅ Ready to use immediately
   - **Currently configured in .env**

2. **IBKR Paper Trading** (app/ibkr/)
   - Uses Interactive Brokers Paper Trading account
   - Real broker simulation
   - Live market data from IBKR
   - More realistic execution
   - ⚠️ Requires IBKR account + TWS/Gateway setup

---

## Why Use IBKR Paper Trading?

**Advantages over Virtual Paper Trading**:
- More realistic order execution
- Real broker simulation (fills, rejections, partial fills)
- Live market data from IBKR
- Tests the full execution pipeline before live trading
- Same code path as live trading

**When to Use**:
- After virtual paper trading shows promising results
- Before moving to live trading
- To validate broker integration works
- To test order execution edge cases

---

## Prerequisites

### 1. IBKR Account Setup

**Step 1: Create IBKR Paper Trading Account**
1. Go to [https://www.interactivebrokers.com](https://www.interactivebrokers.com)
2. Sign up for a **Paper Trading Account** (free)
3. Complete account registration
4. You'll receive paper trading credentials (username/password)

**Step 2: Download TWS or IB Gateway**

Choose ONE:

**Option A: Trader Workstation (TWS)** - Full GUI
- Download: [https://www.interactivebrokers.com/en/trading/tws.php](https://www.interactivebrokers.com/en/trading/tws.php)
- Pros: Visual interface, easy to monitor
- Cons: Heavy, requires GUI

**Option B: IB Gateway** - Lightweight headless
- Download: [https://www.interactivebrokers.com/en/trading/ibgateway-stable.php](https://www.interactivebrokers.com/en/trading/ibgateway-stable.php)
- Pros: Lightweight, can run headless
- Cons: No GUI

**Recommendation**: Start with TWS for testing, switch to IB Gateway for 24/7 automation.

### 2. Python Dependencies

```bash
pip install ib_insync
```

---

## Configuration

### Step 1: Start TWS/Gateway in Paper Trading Mode

**For TWS**:
1. Launch Trader Workstation
2. Login with **PAPER TRADING** credentials
3. Go to File → Global Configuration → API → Settings
4. Enable API connections:
   - ✅ Enable ActiveX and Socket Clients
   - ✅ Allow connections from localhost
   - Socket port: **7497** (paper trading)
   - ⚠️ DO NOT use port 7496 (that's live trading!)
5. Click OK and restart TWS

**For IB Gateway**:
1. Launch IB Gateway
2. Select **Paper Trading** mode
3. Login with paper trading credentials
4. Configure API settings (same as TWS above)

**CRITICAL**: Always verify you're in **PAPER TRADING MODE** before connecting!

### Step 2: Update .env Configuration

```bash
# IBKR Settings
IBKR_HOST=127.0.0.1
IBKR_PORT=7497              # Paper trading port
IBKR_CLIENT_ID=1            # Unique client ID

# Trading Mode
TRADING_MODE=paper          # MUST be 'paper' for paper trading
TRADING_ENABLED=true        # Enable actual order placement

# Data Sources (keep as-is from virtual paper trading)
CT_ENABLED=true
HSW_ENABLED=false
FMP_ENABLED=false

# Paper Trading (virtual mode - can keep for comparison)
PAPER_TRADING_ENABLED=true
PAPER_INITIAL_CASH=10000
```

### Step 3: Verify Configuration

**Critical Settings**:
- `IBKR_PORT=7497` ← Paper trading port (NOT 7496!)
- `TRADING_MODE=paper` ← Ensures paper trading mode
- `TRADING_ENABLED=true` ← Actually place orders

---

## Testing Plan

### Test 1: Connection Test

**Objective**: Verify connection to IBKR

**Steps**:
```bash
python -c "from app.ibkr import get_ibkr_client; client = get_ibkr_client(); print('✅ Connected' if client.connect() else '❌ Failed')"
```

**Expected Output**:
```
INFO - Connecting to IBKR at 127.0.0.1:7497 (client_id=1, mode=paper)
INFO - Successfully connected to IBKR
INFO - Connected accounts: ['DU123456']
✅ Connected
```

**If it fails**:
- Verify TWS/Gateway is running
- Check TWS/Gateway is in PAPER mode (not live!)
- Verify port 7497 in .env and TWS settings
- Check API is enabled in TWS Global Configuration

---

### Test 2: Market Data Test

**Objective**: Fetch live price from IBKR

**Steps**:
```python
from app.ibkr import get_ibkr_client

client = get_ibkr_client()
client.connect()

# Test getting price
price = client.get_market_price("AAPL")
print(f"AAPL Price: ${price:.2f}")

client.disconnect()
```

**Expected Output**:
```
INFO - Successfully connected to IBKR
AAPL Price: $178.45
INFO - Disconnected from IBKR
```

---

### Test 3: Account Value Test

**Objective**: Verify paper account balance

**Steps**:
```python
from app.ibkr import get_ibkr_client

client = get_ibkr_client()
client.connect()

# Get account value
nav = client.get_account_value("NetLiquidation")
cash = client.get_account_value("TotalCashValue")

print(f"Account NAV: ${nav:,.2f}")
print(f"Available Cash: ${cash:,.2f}")

client.disconnect()
```

**Expected Output**:
```
Account NAV: $1,000,000.00
Available Cash: $1,000,000.00
```

**Note**: IBKR paper accounts typically start with $1M USD

---

### Test 4: Position Test

**Objective**: Get current positions

**Steps**:
```python
from app.ibkr import get_ibkr_client

client = get_ibkr_client()
client.connect()

positions = client.get_positions()
print(f"Positions: {len(positions)}")
for pos in positions:
    print(f"  {pos['ticker']}: {pos['qty']} shares @ ${pos['avg_cost']:.2f}")

client.disconnect()
```

**Expected Output** (if no positions):
```
Positions: 0
```

---

### Test 5: Order Placement Test (DRY RUN)

**Objective**: Test order placement logic WITHOUT submitting

**Steps**:
1. Set `TRADING_ENABLED=false` in .env
2. Run:
```bash
python -m app.run trade
```

**Expected Output**:
```
⚠️  WARNING: TRADING_ENABLED=false
Orders will be logged but NOT submitted to IBKR

=== Found 3 signals to execute ===

Portfolio NAV: $100,000.00

Processing signal: STRONG_BUY NVDA (score: 85)
  Would place order: BUY 3.5 shares @ ~$850.23
  Notional: $2,975.81 (3.0% of NAV)
  ℹ️  Order logged, not submitted (TRADING_ENABLED=false)

...
```

---

### Test 6: Order Placement Test (LIVE to IBKR Paper)

**Objective**: Actually submit order to IBKR paper account

**⚠️ CRITICAL SAFETY CHECKS**:
- ✅ TWS/Gateway is in PAPER mode (not live!)
- ✅ `TRADING_MODE=paper` in .env
- ✅ `IBKR_PORT=7497` (not 7496!)
- ✅ You're comfortable placing a real (paper) order

**Steps**:
1. Set `TRADING_ENABLED=true` in .env
2. Ensure you have signals to trade:
```bash
python -m app.run signals  # Generate signals first
```
3. Place orders:
```bash
python -m app.run trade
```

**Expected Output**:
```
=== Found 2 signals to execute ===

Portfolio NAV: $1,000,000.00

Processing signal: STRONG_BUY HAL (score: 82)
  Price: $43.50
  Position size: 689 shares ($29,971.50 - 3.0% of NAV)
  Placing order: BUY 689 HAL @ MKT (mode=paper)
  ✅ Order placed successfully
     Order ID: abc123
     IBKR Order ID: 12345
     Status: Submitted

...
```

4. **Verify in TWS/Gateway**:
   - Open TWS → Portfolio → Orders
   - You should see the order with status "Submitted" or "Filled"

---

### Test 7: Reconciliation Test

**Objective**: Verify local DB matches IBKR state

**Steps**:
```bash
python -m app.run reconcile
```

**Expected Output**:
```
=== Reconciliation Summary ===
Status: success

Positions:
  IBKR: 2
  Local: 2
  Discrepancies: 0

Open Orders:
  IBKR: 0

Account:
  Net Liquidation: $1,025,450.00
  Total Cash: $950,000.00
  Buying Power: $3,800,000.00
  Mode: PAPER
```

---

## Common Issues

### Issue 1: Connection Refused

**Error**:
```
ConnectionRefusedError: [Errno 111] Connection refused
```

**Solutions**:
- Check TWS/Gateway is running
- Verify API is enabled in TWS settings
- Check port matches (7497 for paper, 7496 for live)
- Try restarting TWS/Gateway

---

### Issue 2: Wrong Trading Mode

**Error**:
```
ERROR - Connected to LIVE account but TRADING_MODE=paper
```

**Solution**:
- **STOP IMMEDIATELY**
- You're connected to LIVE trading account by mistake!
- Check you're using port 7497 (paper) not 7496 (live)
- Verify TWS/Gateway is in Paper Trading mode
- Restart TWS in Paper mode

---

### Issue 3: Market Data Not Available

**Error**:
```
ERROR - No market data available for ticker AAPL
```

**Solutions**:
- IBKR paper accounts may have delayed data
- Subscribe to market data in IBKR account settings
- Wait 2-3 seconds for data to arrive
- Some tickers may not be available in paper trading

---

### Issue 4: Order Rejected

**Error**:
```
Order rejected: Insufficient funds
```

**Solutions**:
- Check account has sufficient cash
- Reduce position size in config
- Check margin requirements
- Verify IBKR paper account is funded ($1M default)

---

## Safety Checklist

Before placing ANY orders with IBKR:

- [ ] I have an IBKR PAPER trading account (not live)
- [ ] TWS/Gateway is running in PAPER mode
- [ ] `TRADING_MODE=paper` in .env
- [ ] `IBKR_PORT=7497` (paper port, NOT 7496!)
- [ ] I tested connection successfully
- [ ] I tested with `TRADING_ENABLED=false` first
- [ ] I can see TWS/Gateway account shows "PAPER" mode
- [ ] I'm comfortable proceeding

**NEVER SKIP THESE CHECKS**

---

## Next Steps

### After Successful IBKR Paper Trading

1. **Run for 1 week** with IBKR paper trading
2. **Compare results** with virtual paper trading
3. **Review performance**:
   - What's the return %?
   - How many trades were profitable?
   - Were there execution issues?
   - Did orders fill as expected?

4. **If profitable and stable**:
   - Consider increasing capital
   - Run for 1 month
   - Evaluate moving to live trading

5. **If issues arise**:
   - Debug execution problems
   - Tune strategy parameters
   - Fix edge cases

---

## Switching Between Virtual and IBKR Paper Trading

You can run BOTH modes simultaneously for comparison:

**Virtual Paper Trading** (default):
```bash
python -m app.run init-paper      # Initialize $10k virtual account
python -m app.run daily           # Run with virtual trading
python -m app.run report          # View virtual performance
```

**IBKR Paper Trading**:
```bash
# Set TRADING_ENABLED=true in .env
# Start TWS/Gateway in paper mode
python -m app.run trade           # Uses IBKR when TRADING_ENABLED=true
python -m app.run reconcile       # Check IBKR state
```

**Both modes use the same signals** - just different execution backends!

---

## Troubleshooting

### Check IBKR Logs

TWS/Gateway logs location:
- **Windows**: `C:\Users\<username>\Jts\`
- **Mac**: `~/Jts/`
- **Linux**: `~/Jts/`

Look for files: `api.*.log`, `tws.*.log`

### Check App Logs

```bash
# View app logs
tail -f logs/app.log  # If logging to file

# Or run with debug logging
python -m app.run --log-level DEBUG trade
```

---

## Reference

### IBKR Ports

| Port | Mode | Use |
|------|------|-----|
| 7496 | LIVE | Real money trading (DANGER!) |
| 7497 | PAPER | Paper trading (SAFE) |
| 4001 | LIVE (Gateway) | Real money via Gateway |
| 4002 | PAPER (Gateway) | Paper via Gateway |

**Always use 7497 or 4002 for paper trading!**

### Configuration Variables

```bash
IBKR_HOST=127.0.0.1        # Localhost
IBKR_PORT=7497             # Paper port
IBKR_CLIENT_ID=1           # Unique ID (1-32)
TRADING_MODE=paper         # paper or live
TRADING_ENABLED=true       # Enable orders
```

---

## Support

**IBKR Documentation**:
- [API Documentation](https://www.interactivebrokers.com/en/trading/ib-api.php)
- [TWS API Guide](https://interactivebrokers.github.io/tws-api/)
- [ib_insync Documentation](https://ib-insync.readthedocs.io/)

**Common IBKR Help**:
- [Enable API](https://www.interactivebrokers.com/en/software/api/apiguide/tables/enable_api.htm)
- [Paper Trading](https://www.interactivebrokers.com/en/trading/paper-trading.php)

---

**Last Updated**: 2026-01-16
**Status**: Ready for user testing
**Tested**: Connection logic verified, order placement code complete
**Cannot test in sandbox**: Network restrictions prevent IBKR connection
**User action required**: Setup IBKR account and test on local machine
