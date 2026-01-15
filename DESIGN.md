# Congress Trade Tracker - Design Document

## Vision

An automated investment assistant that converts public congressional trade disclosures into disciplined, explainable investment decisions with minimal human intervention.

**Not insider trading** - following publicly disclosed information with systematic rules.

---

## Core Principles

1. **Emotion-Free**: Rules, not intuition
2. **Explainable**: Every decision has a clear rationale
3. **Conservative**: Position limits, clear exits, safety controls
4. **Low-Maintenance**: Set it and monitor occasionally
5. **Durable**: Handle errors gracefully, keep running

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Congress Trade Tracker                    │
└─────────────────────────────────────────────────────────────┘

┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│   INGEST     │───▶│   EVALUATE   │───▶│   EXECUTE    │
│              │    │              │    │              │
│ - Finnhub    │    │ - Filter     │    │ - Paper      │
│ - House API  │    │ - Score      │    │ - Live       │
│ - Dedup      │    │ - Decide     │    │ - Audit      │
└──────────────┘    └──────────────┘    └──────────────┘
       │                   │                   │
       └───────────────────┴───────────────────┘
                          ▼
                  ┌──────────────┐
                  │   STORAGE    │
                  │              │
                  │ - Events     │
                  │ - Signals    │
                  │ - Positions  │
                  │ - Orders     │
                  └──────────────┘
```

---

## Technology Stack

### Language: Python 3.11+
**Why:** Fast iteration, rich ecosystem for finance, data, and APIs

### Core Dependencies
```
# Data
pandas              # Data manipulation
pydantic            # Data validation
sqlalchemy          # Database ORM

# APIs
finnhub-python      # Congress trade data
ib-insync           # Interactive Brokers
requests            # HTTP fallback

# Infrastructure
python-dotenv       # Config
loguru              # Simple, beautiful logging
schedule            # Task scheduling
typer               # CLI framework

# Optional
sendgrid            # Notifications
plotly              # Visualization
pytest              # Testing
```

**Why these choices:**
- **ib-insync**: Mature, well-documented, synchronous (easier to reason about)
- **loguru**: Dead simple logging with automatic JSON support
- **schedule**: Lightweight scheduler (no cron dependency for development)
- **typer**: Modern CLI with great UX

### Database: SQLite → PostgreSQL
- Start with SQLite (zero config)
- Use SQLAlchemy (easy migration to Postgres later)

---

## Data Model

### Three Core Tables

#### 1. `disclosures` - Raw congressional trades
```python
- id: UUID
- source: str (finnhub, house_api, etc.)
- politician: str
- ticker: str
- transaction_type: BUY | SELL
- trade_date: date
- disclosure_date: date
- amount_min: float
- amount_max: float
- amount_estimate: float  # (min + max) / 2
- delay_days: int  # disclosure - trade
- raw_data: json
- created_at: timestamp
```

#### 2. `signals` - Evaluated decisions
```python
- id: UUID
- disclosure_id: UUID (FK)
- ticker: str
- action: BUY | SELL | WATCH | IGNORE
- confidence: HIGH | MEDIUM | LOW
- score: int (0-100)
- reasons: list[str]  # ["FRESH_2D", "LARGE_250K", "MEMBER_DIRECT"]
- created_at: timestamp
```

#### 3. `positions` - Portfolio state
```python
- id: UUID
- ticker: str
- quantity: float
- avg_cost: float
- current_price: float
- unrealized_pnl: float
- opened_at: timestamp
- opened_by_signals: list[UUID]
- exit_strategy: dict  # {"type": "time", "days": 30} or {"type": "profit", "pct": 0.15}
- status: OPEN | CLOSED
```

#### 4. `orders` - Execution audit trail
```python
- id: UUID
- signal_id: UUID (FK)
- ticker: str
- side: BUY | SELL
- quantity: float
- order_type: MARKET | LIMIT
- status: PENDING | FILLED | REJECTED | CANCELLED
- broker_order_id: str
- filled_price: float
- filled_at: timestamp
- created_at: timestamp
```

---

## Evaluation Logic

### Step 1: Filter Out Noise

**Hard Filters** (discard if fails):
- Delay > 45 days → IGNORE (too stale)
- Amount < $5,000 → IGNORE (too small)
- Ticker is OTC/penny stock → IGNORE (illiquid)
- Unknown transaction type → IGNORE

### Step 2: Score Remaining Disclosures

Start with base score: **50**

**Freshness** (max +30):
- 0-7 days: +30
- 8-14 days: +20
- 15-30 days: +10
- 31-45 days: +5

**Amount** (max +25):
- $1M+: +25
- $500K-$1M: +20
- $250K-$500K: +15
- $100K-$250K: +10
- $50K-$100K: +5
- $5K-$50K: +2

**Who Traded** (max +15):
- Member themselves: +15
- Spouse: +10
- Dependent: +5

**Cluster Signal** (max +15):
- 3+ politicians bought same ticker in 14 days: +15
- 2 politicians: +10

**Transaction Type** (modifier):
- BUY: Use score as-is
- SELL: Only actionable if we own the ticker

### Step 3: Map Score → Action

| Score | Action | Confidence | Behavior |
|-------|--------|------------|----------|
| 85-100 | BUY | HIGH | Take 3-5% position |
| 70-84 | BUY | MEDIUM | Take 1-2% position |
| 50-69 | WATCH | LOW | Log but don't trade |
| 0-49 | IGNORE | N/A | Discard |

**SELL signals**:
- If we own ticker + new SELL disclosure → Generate SELL signal with HIGH confidence
- If we don't own → IGNORE

---

## Position Management

### Entry Rules

**Position Sizing**:
```python
def calculate_position_size(signal, portfolio_value):
    if signal.confidence == "HIGH":
        target_pct = 0.04  # 4%
    elif signal.confidence == "MEDIUM":
        target_pct = 0.02  # 2%
    else:
        return 0

    # Apply limits
    current_exposure = portfolio.get_exposure(signal.ticker)
    max_per_ticker = portfolio_value * 0.08  # Max 8% in one ticker

    target = portfolio_value * target_pct
    available = max_per_ticker - current_exposure

    return min(target, available, portfolio_value * 0.05)  # Also cap at 5%/day
```

**Limits**:
- Max per ticker: 8% of portfolio
- Max new positions per day: 5% of portfolio
- Max total positions: 15 stocks
- Min position size: $500 (avoid tiny positions)

### Exit Rules

**Every position has 3 exit conditions** (first triggered wins):

1. **Time-based**: 30 calendar days from entry
   - Rationale: Congress info gets stale

2. **Profit target**: +20% unrealized gain
   - Rationale: Lock in wins

3. **Stop loss**: -10% unrealized loss
   - Rationale: Cut losers quickly

**Additional exit trigger**:
- New SELL disclosure from 2+ politicians → Exit immediately

**Check frequency**: Daily after market close (or real-time if you want)

---

## Safety Controls

### Global Kill Switch
```python
TRADING_ENABLED = os.getenv("TRADING_ENABLED", "false")

if TRADING_ENABLED != "true":
    log.info("Trading disabled - would have placed order", order=order_details)
    return None
```

### Account Mode
```python
ACCOUNT_MODE = os.getenv("ACCOUNT_MODE", "paper")  # paper | live

# Connect to different ports
IBKR_PORT = 7497 if ACCOUNT_MODE == "paper" else 7496
```

### Pre-Trade Checks
Before every order:
- [ ] Market is open
- [ ] Not exceeding position limits
- [ ] Sufficient buying power
- [ ] Ticker is tradeable (not halted, delisted, etc.)
- [ ] Price is reasonable (not 10x expected)

---

## Implementation Modules

### 1. `ingest.py` - Data Collection
```python
class DataIngestor:
    def fetch_finnhub(from_date, to_date):
        """Fetch congressional trades from Finnhub"""

    def deduplicate(disclosures):
        """Remove duplicates based on (politician, ticker, trade_date, amount)"""

    def save_to_db(disclosures):
        """Upsert into disclosures table"""
```

### 2. `evaluate.py` - Signal Generation
```python
class SignalGenerator:
    def filter(disclosure):
        """Apply hard filters, return bool"""

    def score(disclosure):
        """Return score (0-100) and reasons list"""

    def map_to_action(score, disclosure, portfolio):
        """Return Signal object"""
```

### 3. `portfolio.py` - Position Management
```python
class PortfolioManager:
    def get_nav():
        """Current portfolio value"""

    def get_exposure(ticker):
        """Current $ exposure to ticker"""

    def calculate_position_size(signal):
        """Return $ amount to trade"""

    def check_exit_conditions():
        """Check all positions, generate SELL signals if needed"""
```

### 4. `execute.py` - Trade Execution
```python
class TradeExecutor:
    def connect_to_broker():
        """Connect to IBKR via ib-insync"""

    def place_order(signal, size):
        """Execute trade, return Order object"""

    def track_order_status(order):
        """Poll until filled/rejected"""

    def update_position(fill):
        """Update positions table after fill"""
```

### 5. `audit.py` - Logging & Reporting
```python
class AuditLogger:
    def log_disclosure(disclosure):
        """Log incoming data"""

    def log_signal(signal):
        """Log decision with reasons"""

    def log_order(order):
        """Log execution details"""

    def daily_summary():
        """Generate daily report"""
```

---

## CLI Interface

```bash
# Ingest data
python -m tracker ingest --days-back 30

# Generate signals (doesn't trade)
python -m tracker evaluate

# Execute trades (respects TRADING_ENABLED)
python -m tracker trade

# Check positions and exits
python -m tracker check-exits

# Full pipeline (run daily)
python -m tracker daily

# Manual operations
python -m tracker close-position AAPL --reason "manual"
python -m tracker status  # Show portfolio, pending orders, etc.
```

---

## Deployment Strategy

### Phase 1: Development (Local, Paper Trading)
```bash
# .env
TRADING_ENABLED=false
ACCOUNT_MODE=paper
FINNHUB_API_KEY=xxx
```

Run manually, observe behavior:
```bash
python -m tracker daily
```

### Phase 2: Staging (Scheduled, Paper Trading)
```bash
# .env
TRADING_ENABLED=true
ACCOUNT_MODE=paper
```

Set up cron:
```cron
0 17 * * 1-5 cd /path && python -m tracker daily >> logs/daily.log 2>&1
```

Run for 2-4 weeks, monitor:
- Are signals reasonable?
- Are exits working?
- Any errors?

### Phase 3: Production (Scheduled, Live Trading)
```bash
# .env
TRADING_ENABLED=true
ACCOUNT_MODE=live
```

Start with small capital, monitor closely.

---

## Monitoring & Alerts

### Daily Summary Email
After each run, send email with:
- New disclosures ingested
- Signals generated (BUY/SELL/WATCH counts)
- Trades executed (with reasons)
- Current positions (count, total value, P&L)
- Positions approaching exit conditions
- Any errors

### Weekly Report
- Total return vs S&P 500
- Win rate (% profitable positions)
- Avg holding period
- Largest winners/losers
- Most traded tickers

### Critical Alerts
- Order rejected by broker
- Position down >15%
- Unable to connect to broker
- Database error

---

## Testing Strategy

### Unit Tests
- Scoring logic with fixtures
- Position sizing calculations
- Exit condition checks
- Deduplication logic

### Integration Tests
- Mock Finnhub → Signal generation
- Mock IBKR → Order execution
- Full pipeline with test data

### Manual Testing
- Run in paper mode for 2+ weeks
- Verify all signals make sense
- Check exits trigger correctly
- Confirm audit trail is complete

---

## Future Enhancements (Phase 2)

1. **Multiple Data Sources**
   - House stock watcher API
   - Senate disclosure website
   - Cross-validate sources

2. **Advanced Scoring**
   - Committee assignments (relevant sectors get bonus)
   - Historical politician performance
   - Market conditions (VIX, sector strength)

3. **Better Exits**
   - Trailing stops
   - Sector rotation (exit weak sectors early)
   - Tax loss harvesting

4. **Web Dashboard**
   - View disclosures and signals
   - Portfolio performance charts
   - Manual override buttons

5. **Backtesting**
   - Historical disclosure data
   - Simulate different scoring rules
   - Optimize parameters

---

## File Structure

```
congress-trade-tracker/
├── src/
│   ├── __init__.py
│   ├── cli.py              # Typer CLI
│   ├── config.py           # Load .env
│   ├── database.py         # SQLAlchemy setup
│   ├── models.py           # Data models (Pydantic + SQLAlchemy)
│   ├── ingest.py           # Data collection
│   ├── evaluate.py         # Signal generation
│   ├── portfolio.py        # Position management
│   ├── execute.py          # Trade execution
│   └── audit.py            # Logging & reporting
├── tests/
│   ├── test_scoring.py
│   ├── test_positions.py
│   └── test_integration.py
├── .env.example
├── .gitignore
├── README.md
├── DESIGN.md               # This file
└── requirements.txt
```

---

## Key Decisions & Rationale

### Why not ML/AI?
**Start with rules.** They're explainable, debuggable, and good enough for MVP. Add ML later if needed.

### Why 30-day exits?
Congressional information has a shelf life. After a month, the market has likely absorbed it.

### Why limit to 15 positions?
Stay focused. Too many positions = hard to manage, high transaction costs.

### Why market orders?
Simplicity for MVP. Limit orders can add complexity (what if they don't fill?). Accept minor slippage.

### Why no options?
Options require more capital, more risk management, more complexity. Stocks only for MVP.

---

## Success Metrics

### Functional (Must Have)
- ✅ Ingests new disclosures daily without errors
- ✅ Generates signals with clear reasons
- ✅ Places orders in paper mode
- ✅ Tracks positions accurately
- ✅ Exits trigger correctly
- ✅ Never exceeds position limits

### Operational (Should Have)
- ✅ Runs unattended for 1+ week without manual intervention
- ✅ Email summaries sent daily
- ✅ Complete audit trail (can answer "why did we buy X?")

### Performance (Nice to Have)
- Portfolio doesn't underperform S&P 500 by >10% annually
- Win rate >40%
- No position loses >15% (stops should prevent this)

---

## Getting Started

Ready to build? Here's the execution order:

1. Set up project structure (30 min)
2. Database models (1 hour)
3. Finnhub ingestion (2 hours)
4. Scoring logic (2 hours)
5. Portfolio manager (2 hours)
6. IBKR execution (3 hours)
7. CLI commands (1 hour)
8. Testing (2 hours)

**Total: ~13-15 hours of focused work**

Let's build this!
