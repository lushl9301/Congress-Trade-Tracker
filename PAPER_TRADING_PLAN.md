# Paper Trading Implementation Plan

## Overview

Implement a complete paper trading system to:
1. ✅ Get real-time stock price data
2. ✅ Initialize paper account with starting capital
3. ✅ Filter for STRONG_BUY signals only
4. ✅ Execute virtual trades
5. ✅ Track performance over time
6. ✅ Generate performance reports

## Current Status (Historical Plan)

This plan describes the original gaps prior to Phase 3 implementation. The paper
trading system is now implemented and ready for user testing; see `PHASE_3_COMPLETE.md`
and `task_plan.md` for the current status and instructions.

### ✅ Already Implemented (at time of this plan)
- **Strategy Engine**: Scoring and signal generation (`app/strategy.py`)
- **Portfolio Manager**: Position sizing and risk controls (`app/portfolio.py`)
- **Database**: Tables for events, signals, positions, orders, fills, PnL (`app/db.py`)
- **Multi-source Data**: HSW + FMP + CapitolTrades ingestion
- **CLI Commands**: `ingest`, `signals`, etc. (`app/run.py`)

### ✅ Components Implemented Since This Plan
1. **Market Data Integration**: Real stock prices with caching
2. **Paper Account State**: Virtual cash/equity tracking
3. **Signal Filtering CLI**: STRONG_BUY filtering flags
4. **Virtual Order Execution**: Paper trading simulation
5. **Performance Reports**: PnL tracking and daily reporting

## Phase 1: Market Data Integration 📈

### Goal
Get real-time (or near-real-time) stock prices for paper trading simulation.

### Options Analysis

| API | Cost | Delay | Rate Limit | Coverage | Recommendation |
|-----|------|-------|------------|----------|----------------|
| **Yahoo Finance (yfinance)** | Free | 15-20 min | Unlimited | US stocks | ✅ **Best for MVP** |
| **Alpha Vantage** | Free | Real-time | 5 req/min | US + global | ⚠️ Too slow for multi-ticker |
| **IEX Cloud** | Free tier | Real-time | 50k/month | US stocks | ✅ Good alternative |
| **Polygon.io** | Free tier | 15 min | Limited | US stocks | ⚠️ Complex setup |
| **IBKR Market Data** | Requires IBKR | Real-time | N/A | Global | ❌ Overkill for paper |

### Recommended: Yahoo Finance (yfinance)

**Why:**
- ✅ Completely free, no API key required
- ✅ 15-20 min delayed data (sufficient for paper trading)
- ✅ Unlimited requests (no rate limiting)
- ✅ Easy Python library: `pip install yfinance`
- ✅ Covers all US stocks and ETFs
- ✅ Simple API: `yf.Ticker("AAPL").info['currentPrice']`

**Drawbacks:**
- ⚠️ 15-20 minute delay (acceptable for congressional trading strategy)
- ⚠️ Unofficial API (could break, but stable for years)

### Implementation Plan

**File**: `app/market_data.py`

```python
"""Market data provider using Yahoo Finance."""

import yfinance as yf
from typing import Dict, Optional, List
from datetime import datetime
import time

class MarketDataProvider:
    """Fetch real-time stock prices using Yahoo Finance."""

    def __init__(self, cache_ttl_seconds: int = 300):
        """
        Initialize market data provider.

        Args:
            cache_ttl_seconds: Cache prices for N seconds (default 5 min)
        """
        self.cache = {}  # {ticker: (price, timestamp)}
        self.cache_ttl = cache_ttl_seconds

    def get_price(self, ticker: str) -> Optional[float]:
        """
        Get current price for a ticker.

        Args:
            ticker: Stock symbol (e.g., "AAPL")

        Returns:
            Current price or None if unavailable
        """
        # Check cache
        if ticker in self.cache:
            price, cached_at = self.cache[ticker]
            age = time.time() - cached_at
            if age < self.cache_ttl:
                return price

        # Fetch fresh price
        try:
            stock = yf.Ticker(ticker)
            info = stock.info

            # Try multiple price fields (currentPrice, regularMarketPrice, etc.)
            price = (
                info.get('currentPrice') or
                info.get('regularMarketPrice') or
                info.get('previousClose')
            )

            if price and price > 0:
                self.cache[ticker] = (price, time.time())
                return price
        except Exception as e:
            logger.warning(f"Failed to fetch price for {ticker}: {e}")

        return None

    def get_prices_batch(self, tickers: List[str]) -> Dict[str, Optional[float]]:
        """
        Get prices for multiple tickers efficiently.

        Args:
            tickers: List of stock symbols

        Returns:
            Dictionary mapping ticker to price
        """
        # Use yfinance download for batch fetching
        try:
            data = yf.download(tickers, period="1d", progress=False, show_errors=False)
            if len(tickers) == 1:
                price = data['Close'].iloc[-1]
                return {tickers[0]: float(price) if not pd.isna(price) else None}
            else:
                prices = {}
                for ticker in tickers:
                    try:
                        price = data['Close'][ticker].iloc[-1]
                        prices[ticker] = float(price) if not pd.isna(price) else None
                    except:
                        prices[ticker] = None
                return prices
        except Exception as e:
            logger.error(f"Batch price fetch failed: {e}")
            # Fall back to individual fetches
            return {ticker: self.get_price(ticker) for ticker in tickers}
```

**Add to config** (`app/config.py`):
```python
# Market Data
MARKET_DATA_PROVIDER: str = "yfinance"  # yfinance, iex, alpha_vantage
PRICE_CACHE_TTL_SECONDS: int = 300  # 5 minutes
```

**Dependencies**:
```bash
pip install yfinance pandas
```

---

## Phase 2: Paper Account State 💰

### Goal
Track virtual cash, equity, and positions in a paper trading account.

### Database Schema

**New table**: `paper_account`
```sql
CREATE TABLE paper_account (
    account_id TEXT PRIMARY KEY DEFAULT 'default',
    initial_cash REAL NOT NULL,
    current_cash REAL NOT NULL,
    current_equity REAL NOT NULL,  -- sum of position values
    total_value REAL NOT NULL,      -- cash + equity
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
```

**New table**: `paper_trades`
```sql
CREATE TABLE paper_trades (
    trade_id TEXT PRIMARY KEY,
    signal_id TEXT NOT NULL,
    ticker TEXT NOT NULL,
    side TEXT NOT NULL,              -- BUY, SELL
    shares REAL NOT NULL,
    price REAL NOT NULL,
    notional REAL NOT NULL,          -- shares * price
    commission REAL DEFAULT 0,
    executed_at TEXT NOT NULL,
    notes TEXT,
    FOREIGN KEY (signal_id) REFERENCES trade_signals(signal_id)
);
```

**Update `positions` table** (add paper account tracking):
```sql
ALTER TABLE positions ADD COLUMN account_type TEXT DEFAULT 'paper'; -- paper, live
```

### Implementation Plan

**File**: `app/paper_account.py`

```python
"""Paper trading account manager."""

from datetime import datetime
from typing import Optional, Dict, List
from app.db import db
from app.logging import get_logger
from app.models import Position

logger = get_logger(__name__)

class PaperAccount:
    """Manages paper trading account state."""

    def __init__(self, account_id: str = "default", initial_cash: float = 100000):
        """
        Initialize paper account.

        Args:
            account_id: Account identifier
            initial_cash: Starting cash (default $100,000)
        """
        self.account_id = account_id
        self.initial_cash = initial_cash

        # Load or create account
        self._load_or_create()

    def _load_or_create(self):
        """Load existing account or create new one."""
        account = db.get_paper_account(self.account_id)

        if account is None:
            # Create new paper account
            db.create_paper_account(
                account_id=self.account_id,
                initial_cash=self.initial_cash
            )
            logger.info(f"Created paper account '{self.account_id}' with ${self.initial_cash:,.2f}")
        else:
            logger.info(f"Loaded paper account '{self.account_id}'")

    def get_cash(self) -> float:
        """Get available cash."""
        account = db.get_paper_account(self.account_id)
        return account['current_cash']

    def get_equity(self, market_data) -> float:
        """
        Calculate current equity (position values).

        Args:
            market_data: MarketDataProvider instance

        Returns:
            Total equity value
        """
        positions = db.get_all_positions()
        equity = 0.0

        for pos in positions:
            price = market_data.get_price(pos.ticker)
            if price:
                equity += pos.qty * price

        return equity

    def get_nav(self, market_data) -> float:
        """
        Get Net Asset Value (total portfolio value).

        Returns:
            Cash + equity
        """
        cash = self.get_cash()
        equity = self.get_equity(market_data)
        return cash + equity

    def execute_trade(
        self,
        ticker: str,
        side: str,  # BUY or SELL
        shares: float,
        price: float,
        signal_id: str,
        commission: float = 0.0
    ) -> bool:
        """
        Execute a paper trade.

        Args:
            ticker: Stock symbol
            side: BUY or SELL
            shares: Number of shares
            price: Execution price
            signal_id: Related signal ID
            commission: Trading commission (default $0)

        Returns:
            True if trade executed successfully
        """
        notional = shares * price

        if side == "BUY":
            cost = notional + commission
            cash = self.get_cash()

            if cash < cost:
                logger.error(f"Insufficient cash for BUY: need ${cost:,.2f}, have ${cash:,.2f}")
                return False

            # Deduct cash
            db.update_paper_account_cash(self.account_id, -cost)

            # Update position
            db.upsert_position(ticker, shares, price, "paper")

        elif side == "SELL":
            # Check position
            position = db.get_position(ticker)
            if not position or position.qty < shares:
                logger.error(f"Insufficient shares for SELL: need {shares}, have {position.qty if position else 0}")
                return False

            # Add cash
            proceeds = notional - commission
            db.update_paper_account_cash(self.account_id, proceeds)

            # Update position
            db.reduce_position(ticker, shares)

        # Record trade
        trade_id = f"PT-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}-{ticker}"
        db.insert_paper_trade(
            trade_id=trade_id,
            signal_id=signal_id,
            ticker=ticker,
            side=side,
            shares=shares,
            price=price,
            notional=notional,
            commission=commission
        )

        logger.info(f"Executed paper trade: {side} {shares} {ticker} @ ${price:.2f} (${notional:,.2f})")
        return True

    def get_performance(self, market_data) -> Dict:
        """
        Calculate account performance metrics.

        Returns:
            Dictionary with performance stats
        """
        account = db.get_paper_account(self.account_id)
        nav = self.get_nav(market_data)

        total_return = nav - account['initial_cash']
        total_return_pct = (total_return / account['initial_cash']) * 100

        # Get trades
        trades = db.get_paper_trades(self.account_id)

        return {
            'initial_cash': account['initial_cash'],
            'current_cash': self.get_cash(),
            'current_equity': self.get_equity(market_data),
            'nav': nav,
            'total_return': total_return,
            'total_return_pct': total_return_pct,
            'num_trades': len(trades),
            'num_positions': len(db.get_all_positions()),
            'created_at': account['created_at'],
            'days_active': (datetime.utcnow() - datetime.fromisoformat(account['created_at'])).days
        }
```

**CLI command** to initialize paper account:
```bash
python -m app.run init-paper --cash 100000
```

---

## Phase 3: Signal Filtering & Execution 🎯

### Goal
Filter for STRONG_BUY signals only and execute paper trades.

### Implementation Plan

**File**: `app/paper_trader.py`

```python
"""Paper trading execution engine."""

from typing import List, Dict
from app.db import db
from app.models import TradeSignal
from app.paper_account import PaperAccount
from app.market_data import MarketDataProvider
from app.portfolio import portfolio_manager
from app.logging import get_logger

logger = get_logger(__name__)

class PaperTrader:
    """Execute paper trades based on signals."""

    def __init__(self, account: PaperAccount, market_data: MarketDataProvider):
        """
        Initialize paper trader.

        Args:
            account: PaperAccount instance
            market_data: MarketDataProvider instance
        """
        self.account = account
        self.market_data = market_data
        self.portfolio_manager = portfolio_manager

    def get_strong_buy_signals(self) -> List[TradeSignal]:
        """
        Get unprocessed STRONG_BUY signals.

        Returns:
            List of STRONG signals with action=BUY
        """
        # Get all signals not yet traded
        all_signals = db.get_all_signals()

        strong_buys = [
            sig for sig in all_signals
            if sig.action == "BUY"
            and sig.strength == "STRONG"
            and not db.signal_already_traded(sig.signal_id)
        ]

        return strong_buys

    def execute_signal(self, signal: TradeSignal) -> bool:
        """
        Execute a single signal as paper trade.

        Args:
            signal: TradeSignal to execute

        Returns:
            True if executed successfully
        """
        ticker = signal.ticker

        # Get current price
        price = self.market_data.get_price(ticker)
        if not price:
            logger.warning(f"No price available for {ticker}, skipping")
            return False

        # Get NAV
        nav = self.account.get_nav(self.market_data)

        # Calculate position size
        shares, reasons = self.portfolio_manager.calculate_position_size(
            ticker=ticker,
            signal_strength=signal.strength,
            nav=nav,
            current_price=price
        )

        if shares == 0:
            logger.info(f"Rejected {ticker}: {reasons}")
            return False

        # Execute trade
        success = self.account.execute_trade(
            ticker=ticker,
            side="BUY",
            shares=shares,
            price=price,
            signal_id=signal.signal_id,
            commission=0.0  # No commissions in paper trading
        )

        if success:
            # Mark signal as traded
            db.mark_signal_traded(signal.signal_id)
            logger.info(f"✅ Executed: BUY {shares} {ticker} @ ${price:.2f}")

        return success

    def run_trading_session(self) -> Dict:
        """
        Run a complete trading session.

        Process all STRONG_BUY signals and execute eligible trades.

        Returns:
            Dictionary with session statistics
        """
        logger.info("Starting paper trading session")

        # Get strong buy signals
        signals = self.get_strong_buy_signals()
        logger.info(f"Found {len(signals)} STRONG_BUY signals to evaluate")

        executed = 0
        skipped = 0

        for signal in signals:
            if self.execute_signal(signal):
                executed += 1
            else:
                skipped += 1

        # Get performance
        performance = self.account.get_performance(self.market_data)

        results = {
            'signals_evaluated': len(signals),
            'trades_executed': executed,
            'trades_skipped': skipped,
            'nav': performance['nav'],
            'cash': performance['current_cash'],
            'equity': performance['current_equity'],
            'return_pct': performance['total_return_pct']
        }

        logger.info(f"Session complete: {executed} executed, {skipped} skipped")
        return results
```

**CLI command**:
```bash
# Execute STRONG_BUY signals only
python -m app.run trade --strong-only

# Or execute all qualifying signals (STRONG + NORMAL)
python -m app.run trade
```

---

## Phase 4: Performance Tracking & Reporting 📊

### Goal
Generate performance reports showing PnL over time.

### Implementation Plan

**CLI command**: `python -m app.run report`

**Output example**:
```
================================================================================
PAPER TRADING PERFORMANCE REPORT
Generated: 2026-01-15 14:30:00
================================================================================

ACCOUNT SUMMARY
  Account ID:        default
  Initial Capital:   $100,000.00
  Current Cash:      $85,432.10
  Current Equity:    $16,891.45
  Total NAV:         $102,323.55

  Total Return:      $2,323.55 (+2.32%)
  Days Active:       7
  Daily Return:      +0.33%

POSITIONS (5 active)
┌────────┬────────┬──────────────┬──────────────┬──────────────┬──────────┐
│ Ticker │ Shares │ Avg Cost     │ Current Price│ Market Value │ P/L      │
├────────┼────────┼──────────────┼──────────────┼──────────────┼──────────┤
│ NVDA   │  10.00 │   $850.23    │   $865.50    │   $8,655.00  │  +1.80%  │
│ HAL    │  50.00 │    $42.10    │    $43.85    │   $2,192.50  │  +4.16%  │
│ AAPL   │  25.00 │   $182.50    │   $185.20    │   $4,630.00  │  +1.48%  │
│ MSFT   │   8.00 │   $410.00    │   $412.30    │   $3,298.40  │  +0.56%  │
│ PG     │  15.00 │   $155.20    │   $153.80    │   $2,307.00  │  -0.90%  │
└────────┴────────┴──────────────┴──────────────┴──────────────┴──────────┘

RECENT TRADES (last 10)
┌────────────────────┬────────┬──────┬────────┬───────────┬──────────────┐
│ Date               │ Ticker │ Side │ Shares │ Price     │ Notional     │
├────────────────────┼────────┼──────┼────────┼───────────┼──────────────┤
│ 2026-01-15 09:35   │ NVDA   │ BUY  │  10.00 │  $850.23  │   $8,502.30  │
│ 2026-01-14 10:20   │ HAL    │ BUY  │  50.00 │   $42.10  │   $2,105.00  │
│ 2026-01-14 09:45   │ AAPL   │ BUY  │  25.00 │  $182.50  │   $4,562.50  │
│ 2026-01-13 14:10   │ MSFT   │ BUY  │   8.00 │  $410.00  │   $3,280.00  │
│ 2026-01-12 11:30   │ PG     │ BUY  │  15.00 │  $155.20  │   $2,328.00  │
└────────────────────┴────────┴──────┴────────┴───────────┴──────────────┘

SIGNAL STATISTICS
  Total Signals:           47
  Strong Buy:              12
  Normal Buy:              18
  Watch:                   15
  Ignore:                   2

  Signals Traded:           5 / 12 (41.7% of STRONG_BUY)
  Avg Signal Score:        78.5

RISK METRICS
  Largest Position:        NVDA ($8,655.00, 8.46% of NAV)
  Total Exposure:          16.51% of NAV
  Cash Allocation:         83.49%
  Number of Positions:      5

NOTES
  • Paper trading mode (virtual account)
  • Price data delayed 15-20 minutes
  • No commissions charged
  • Report generated from real congressional trade data

================================================================================
```

**Implementation**:

```python
# app/reporting.py

def generate_paper_trading_report(account: PaperAccount, market_data: MarketDataProvider) -> str:
    """Generate comprehensive paper trading report."""

    performance = account.get_performance(market_data)
    positions = db.get_all_positions()
    trades = db.get_paper_trades(account.account_id, limit=10)
    signals = db.get_all_signals()

    # Build report...
    report = []
    report.append("="*80)
    report.append("PAPER TRADING PERFORMANCE REPORT")
    report.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report.append("="*80)

    # Account summary
    report.append("\nACCOUNT SUMMARY")
    report.append(f"  Initial Capital:   ${performance['initial_cash']:,.2f}")
    report.append(f"  Current Cash:      ${performance['current_cash']:,.2f}")
    report.append(f"  Current Equity:    ${performance['current_equity']:,.2f}")
    report.append(f"  Total NAV:         ${performance['nav']:,.2f}")
    report.append(f"  Total Return:      ${performance['total_return']:,.2f} ({performance['total_return_pct']:+.2f}%)")

    # Positions table
    # Trades table
    # Signal statistics
    # Risk metrics

    return "\n".join(report)
```

---

## Implementation Timeline

### Week 1: Core Infrastructure
- **Day 1-2**: Market data integration (yfinance)
  - Implement `MarketDataProvider`
  - Test price fetching for 100+ tickers
  - Add caching logic

- **Day 3-4**: Paper account system
  - Database schema updates
  - Implement `PaperAccount` class
  - CLI command to initialize account

- **Day 5**: Paper trading execution
  - Implement `PaperTrader` class
  - Signal filtering (STRONG_BUY only)
  - Trade execution logic

### Week 2: Testing & Reporting
- **Day 6-7**: Testing
  - Unit tests for market data
  - Integration tests for paper trading
  - End-to-end test with real signals

- **Day 8-9**: Reporting system
  - Implement performance reports
  - Position tracking
  - PnL calculations

- **Day 10**: Documentation & polish
  - User guide for paper trading
  - Configuration examples
  - Troubleshooting guide

---

## Configuration Updates

Add to `.env`:
```bash
# Paper Trading
PAPER_TRADING_ENABLED=true
PAPER_INITIAL_CASH=100000
MARKET_DATA_PROVIDER=yfinance
PRICE_CACHE_TTL_SECONDS=300

# Signal Filtering
TRADE_STRONG_SIGNALS_ONLY=true  # If true, only trade STRONG_BUY signals
```

---

## CLI Commands

```bash
# Initialize paper account
python -m app.run init-paper --cash 100000

# Run full pipeline (ingest -> signals -> trade)
python -m app.run daily --strong-only

# Execute pending signals
python -m app.run trade --strong-only

# Generate performance report
python -m app.run report

# Show current positions
python -m app.run positions

# Show trade history
python -m app.run trades --days 7
```

---

## Testing Strategy

### Unit Tests
- `test_market_data.py`: Price fetching, caching, batch operations
- `test_paper_account.py`: Account state, cash management, trade execution
- `test_paper_trader.py`: Signal filtering, position sizing, trade logic

### Integration Tests
- End-to-end: Ingest → Signals → Paper Trading → Report
- Multi-day simulation with historical data
- Edge cases: insufficient cash, position limits, etc.

### Manual Testing Checklist
- [ ] Initialize paper account with $100k
- [ ] Ingest congressional trades
- [ ] Generate signals (should have some STRONG_BUY)
- [ ] Execute paper trades
- [ ] Verify cash deducted correctly
- [ ] Verify positions created
- [ ] Generate performance report
- [ ] Wait 1 week, run again
- [ ] Verify PnL tracking works

---

## Next Steps

1. **YOU**: Approve this plan
2. **ME**: Implement Phase 1 (Market Data)
3. **ME**: Implement Phase 2 (Paper Account)
4. **ME**: Implement Phase 3 (Signal Execution)
5. **ME**: Implement Phase 4 (Reporting)
6. **YOU**: Test with real data for 1 week
7. **BOTH**: Review results and iterate

---

## Success Criteria

After 1 week of paper trading:
- ✅ Paper account initialized with $100,000
- ✅ At least 5-10 STRONG_BUY trades executed
- ✅ Positions tracked with live prices
- ✅ Performance report generated
- ✅ Can answer: "Which congressional trades made money?"
- ✅ Can answer: "What's our paper trading return?"
- ✅ Ready to evaluate: Should we move to real trading?

---

## Risk Controls (Already Implemented)

- ✅ Max 3% NAV per STRONG signal
- ✅ Max 5% NAV per ticker
- ✅ Max 10% new exposure per day
- ✅ Stop loss: -8%
- ✅ Take profit: +20%
- ✅ Max hold: 30 days

---

## Future Enhancements (Phase 2+)

- [ ] Web dashboard for visualizing performance
- [ ] Email alerts for executed trades
- [ ] Backtesting with historical congressional data
- [ ] Sector exposure tracking
- [ ] Correlation analysis with market indices
- [ ] Trade attribution (which politician's trades are most profitable?)
- [ ] Advanced exit strategies (trailing stops, etc.)

---

**Ready to implement?** Let me know and I'll start with Phase 1 (Market Data Integration).
