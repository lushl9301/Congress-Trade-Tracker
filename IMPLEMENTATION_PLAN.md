# Implementation Plan: Congress Trade Tracker + Auto-Copy Trader

> **Note (Legacy Plan):** This document reflects the original Finnhub + IBKR MVP
> scope and architecture. The project has since shifted to multi-source
> congressional trade ingestion and paper trading workflows. For the current
> roadmap and status, see `task_plan.md`, `MULTI_SOURCE_PLAN.md`, and
> `PHASE_3_COMPLETE.md`.

## Executive Summary

Building a production-lean MVP that monitors US Congress trade disclosures via Finnhub (free tier) and executes disciplined, automated trades through Interactive Brokers in PAPER mode first.

**Core Philosophy:** Ship fast, iterate safely - clear modules, strong logging, strict risk controls.

---

## 1. Technology Stack

### Core Language & Runtime
- **Python 3.11+** - Fast iteration, rich finance ecosystem

### Key Dependencies
```
# Data & API
finnhub-python==2.4.x        # Official Finnhub client
httpx==0.27.x                # Async HTTP client
pydantic==2.x                # Data validation
pydantic-settings==2.x       # Config management

# Database
sqlalchemy==2.0.x            # ORM for SQLite/Postgres
alembic==1.x                 # Database migrations

# Trading
ib_insync==0.9.x             # IBKR integration (mature, well-tested)

# Scheduling & Logging
apscheduler==3.x             # Task scheduling
structlog==24.x              # Structured logging

# CLI & Utilities
typer==0.12.x                # Modern CLI framework
python-dotenv==1.x           # Environment management
rich==13.x                   # Beautiful terminal output

# Optional: Notifications
sendgrid==6.x                # Email notifications
```

### Why These Choices?
- **ib_insync** over ib_async: More mature, better documentation, proven in production
- **SQLite** for MVP: Zero-config, easy to deploy, sufficient performance
- **Typer** over argparse: Better UX, automatic help generation, type safety
- **structlog**: JSON logging for easy parsing and monitoring

---

## 2. Project Structure

```
Congress-Trade-Tracker/
├── app/
│   ├── __init__.py
│   ├── config.py              # Environment & settings
│   ├── logging.py             # Structured logging setup
│   ├── models.py              # Pydantic models
│   ├── db/
│   │   ├── __init__.py
│   │   ├── schema.py          # SQLAlchemy models
│   │   ├── session.py         # DB connection management
│   │   └── migrations/        # Alembic migrations
│   ├── data/
│   │   ├── __init__.py
│   │   ├── finnhub_client.py  # Finnhub API wrapper
│   │   └── ingest.py          # Data ingestion & normalization
│   ├── strategy/
│   │   ├── __init__.py
│   │   ├── scoring.py         # Signal scoring logic
│   │   ├── filters.py         # Data filters
│   │   └── signals.py         # Signal generation
│   ├── portfolio/
│   │   ├── __init__.py
│   │   ├── manager.py         # Portfolio state machine
│   │   ├── position.py        # Position tracking
│   │   └── risk.py            # Position sizing & risk limits
│   ├── ibkr/
│   │   ├── __init__.py
│   │   ├── client.py          # IBKR connection management
│   │   ├── orders.py          # Order placement & tracking
│   │   └── reconcile.py       # State reconciliation
│   ├── notify/
│   │   ├── __init__.py
│   │   └── email.py           # Email notifications
│   └── cli.py                 # Main CLI entrypoint
├── tests/
│   ├── __init__.py
│   ├── conftest.py            # Pytest fixtures
│   ├── test_dedup.py
│   ├── test_scoring.py
│   ├── test_signals.py
│   ├── test_portfolio.py
│   └── test_integration.py
├── scripts/
│   ├── bootstrap_db.py        # Initialize database
│   └── sample_data.py         # Generate test data
├── data/                      # SQLite DB & logs (gitignored)
├── .env.example               # Sample environment variables
├── .gitignore
├── pyproject.toml             # Poetry/pip dependencies
├── README.md
├── CLAUDE.md                  # Project specification
└── IMPLEMENTATION_PLAN.md     # This file
```

---

## 3. Database Schema

### Tables

#### `congress_events` (raw + normalized events)
```sql
CREATE TABLE congress_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT UNIQUE NOT NULL,           -- SHA256 hash
    source TEXT NOT NULL,                    -- 'finnhub'
    member_name TEXT,
    member_id TEXT,
    owner TEXT,                              -- 'member', 'spouse', etc.
    ticker TEXT NOT NULL,
    asset_type TEXT,                         -- 'stock', 'etf', 'unknown'
    transaction_type TEXT NOT NULL,          -- 'BUY', 'SELL', 'OTHER'
    trade_date DATE,
    disclosure_date DATE,
    amount_low REAL,
    amount_high REAL,
    amount_mid REAL,                         -- Computed: (low+high)/2
    delay_days INTEGER,                      -- Computed: disclosure - trade
    currency TEXT DEFAULT 'USD',
    raw_data JSON NOT NULL,                  -- Full Finnhub response
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_events_ticker ON congress_events(ticker);
CREATE INDEX idx_events_trade_date ON congress_events(trade_date);
CREATE INDEX idx_events_disclosure_date ON congress_events(disclosure_date);
```

#### `trade_signals`
```sql
CREATE TABLE trade_signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_id TEXT UNIQUE NOT NULL,          -- Hash of event_id + strategy_version
    event_id TEXT NOT NULL,
    ticker TEXT NOT NULL,
    action TEXT NOT NULL,                    -- 'BUY', 'SELL', 'NONE'
    strength TEXT NOT NULL,                  -- 'STRONG', 'NORMAL', 'WATCH', 'IGNORE'
    score INTEGER NOT NULL,                  -- 0-100
    reasons JSON NOT NULL,                   -- List of scoring reasons
    strategy_version TEXT NOT NULL,          -- 'mvp_v1'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (event_id) REFERENCES congress_events(event_id)
);

CREATE INDEX idx_signals_ticker ON trade_signals(ticker);
CREATE INDEX idx_signals_action ON trade_signals(action);
CREATE INDEX idx_signals_created ON trade_signals(created_at);
```

#### `positions`
```sql
CREATE TABLE positions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT UNIQUE NOT NULL,
    quantity REAL NOT NULL,
    avg_cost REAL NOT NULL,
    current_price REAL,
    unrealized_pnl REAL,
    opened_at TIMESTAMP NOT NULL,
    last_updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    -- Exit rules
    max_hold_days INTEGER DEFAULT 30,
    stop_loss_pct REAL DEFAULT -0.08,
    take_profit_pct REAL DEFAULT 0.20,
    exit_rule TEXT DEFAULT 'HOLD_30D',
    -- Tracking
    signal_ids JSON,                         -- List of signals that contributed
    status TEXT DEFAULT 'OPEN'               -- 'OPEN', 'CLOSED'
);

CREATE INDEX idx_positions_ticker ON positions(ticker);
CREATE INDEX idx_positions_status ON positions(status);
```

#### `orders`
```sql
CREATE TABLE orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id TEXT UNIQUE NOT NULL,           -- Internal UUID
    ibkr_order_id INTEGER,                   -- IBKR orderId
    ibkr_perm_id INTEGER,                    -- IBKR permId
    signal_id TEXT,
    ticker TEXT NOT NULL,
    side TEXT NOT NULL,                      -- 'BUY', 'SELL'
    quantity REAL NOT NULL,
    order_type TEXT NOT NULL,                -- 'MARKET', 'LIMIT'
    limit_price REAL,
    status TEXT NOT NULL,                    -- 'PENDING', 'SUBMITTED', 'FILLED', 'CANCELLED', 'REJECTED'
    request_payload JSON NOT NULL,
    response_payload JSON,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    submitted_at TIMESTAMP,
    filled_at TIMESTAMP,
    FOREIGN KEY (signal_id) REFERENCES trade_signals(signal_id)
);

CREATE INDEX idx_orders_ticker ON orders(ticker);
CREATE INDEX idx_orders_status ON orders(status);
CREATE INDEX idx_orders_created ON orders(created_at);
```

#### `fills`
```sql
CREATE TABLE fills (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id TEXT NOT NULL,
    ticker TEXT NOT NULL,
    quantity REAL NOT NULL,
    fill_price REAL NOT NULL,
    commission REAL DEFAULT 0,
    filled_at TIMESTAMP NOT NULL,
    raw_data JSON,
    FOREIGN KEY (order_id) REFERENCES orders(order_id)
);

CREATE INDEX idx_fills_order ON fills(order_id);
CREATE INDEX idx_fills_filled_at ON fills(filled_at);
```

#### `pnl_snapshots`
```sql
CREATE TABLE pnl_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_date DATE NOT NULL,
    total_value REAL NOT NULL,
    cash REAL NOT NULL,
    positions_value REAL NOT NULL,
    unrealized_pnl REAL NOT NULL,
    realized_pnl REAL NOT NULL,
    num_positions INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_pnl_date ON pnl_snapshots(snapshot_date);
```

---

## 4. Implementation Phases

### Phase 1: Foundation (Days 1-2)
**Goal:** Core infrastructure & data pipeline

#### Tasks:
1. **Project Setup**
   - Initialize Python project with pyproject.toml
   - Set up virtual environment
   - Configure .env.example with all required variables
   - Create .gitignore

2. **Config & Logging**
   - `app/config.py`: Load env vars using pydantic-settings
   - `app/logging.py`: Configure structlog with JSON output
   - Validate all safety defaults (TRADING_ENABLED=false, TRADING_MODE=paper)

3. **Database Layer**
   - Create SQLAlchemy models in `app/db/schema.py`
   - Set up Alembic for migrations
   - Implement `scripts/bootstrap_db.py`
   - Create sample data generator for testing

4. **Pydantic Models**
   - `CongressTradeEvent` with all fields from spec
   - `TradeSignal` with validation
   - `Position`, `Order`, `Fill` models

**Acceptance:**
- `python scripts/bootstrap_db.py` creates database
- Config loads from .env correctly
- Logging outputs structured JSON

---

### Phase 2: Data Ingestion (Days 3-4)
**Goal:** Reliable Finnhub integration with deduplication

#### Tasks:
1. **Finnhub Client**
   - Wrap finnhub-python library
   - Implement `fetch_congressional_trades(symbol=None, from_date, to_date)`
   - Add retry logic with exponential backoff
   - Rate limiting for free tier (60 calls/min)

2. **Event Normalization**
   - Parse Finnhub response → `CongressTradeEvent`
   - Compute `delay_days`, `amount_mid`
   - Handle missing fields gracefully

3. **Deduplication**
   - Implement stable `event_id` hashing:
     ```python
     def compute_event_id(event: CongressTradeEvent) -> str:
         canonical = f"{event.source}|{event.ticker.upper()}|{event.transaction_type}|"
         canonical += f"{event.trade_date or ''}|{event.disclosure_date or ''}|"
         canonical += f"{event.amount_low or 0}|{event.amount_high or 0}|"
         canonical += f"{event.member_name or ''}|{event.owner or ''}"
         return hashlib.sha256(canonical.encode()).hexdigest()
     ```
   - Upsert logic to prevent duplicates

4. **Ingest Command**
   - `python -m app.cli ingest --from-date YYYY-MM-DD --to-date YYYY-MM-DD`
   - Idempotent: can run multiple times safely

**Acceptance:**
- Running `ingest` twice with same data creates no duplicates
- `event_id` is stable across runs
- Missing dates handled without crashes

---

### Phase 3: Strategy Engine (Days 5-6)
**Goal:** Score events and generate actionable signals

#### Tasks:
1. **Filters**
   - `delay_days <= MAX_DELAY_DAYS` (14)
   - `amount_high >= MIN_AMOUNT_HIGH` (5000)
   - Asset type whitelist (stocks/ETFs only)
   - Manual ticker blacklist (OTC, penny stocks)

2. **Scoring Logic**
   ```python
   def score_event(event: CongressTradeEvent) -> tuple[int, list[str]]:
       score = 50
       reasons = []

       # Freshness
       if event.delay_days <= 2:
           score += 25
           reasons.append("FRESH_DISCLOSURE_2D")
       elif event.delay_days <= 7:
           score += 15
           reasons.append("FRESH_DISCLOSURE_7D")
       elif event.delay_days <= 14:
           score += 5
           reasons.append("FRESH_DISCLOSURE_14D")
       else:
           return 0, ["STALE_DISCLOSURE"]

       # Amount
       if event.amount_high >= 250000:
           score += 15
           reasons.append("LARGE_POSITION_250K")
       elif event.amount_high >= 50000:
           score += 10
           reasons.append("MEDIUM_POSITION_50K")
       elif event.amount_high >= 5000:
           score += 5
           reasons.append("SMALL_POSITION_5K")
       else:
           return 0, ["AMOUNT_TOO_SMALL"]

       # Owner
       if event.owner == "member":
           score += 10
           reasons.append("MEMBER_DIRECT")
       elif event.owner == "spouse":
           score += 5
           reasons.append("SPOUSE")
       elif event.owner == "dependent":
           score += 2
           reasons.append("DEPENDENT")

       # Cluster buying (check DB for similar recent events)
       # ... implementation

       return min(100, max(0, score)), reasons
   ```

3. **Signal Mapping**
   ```python
   def map_score_to_signal(score: int, event: CongressTradeEvent, portfolio) -> TradeSignal:
       if event.transaction_type == "BUY":
           if score >= 80:
               return TradeSignal(action="BUY", strength="STRONG", ...)
           elif score >= 65:
               return TradeSignal(action="BUY", strength="NORMAL", ...)
           elif score >= 50:
               return TradeSignal(action="NONE", strength="WATCH", ...)
       elif event.transaction_type == "SELL":
           if portfolio.has_position(event.ticker):
               return TradeSignal(action="SELL", strength="STRONG", ...)

       return TradeSignal(action="NONE", strength="IGNORE", ...)
   ```

4. **Signals Command**
   - `python -m app.cli signals`
   - Process all events without signals
   - Store in `trade_signals` table

**Acceptance:**
- Scoring matches spec examples
- `WATCH` signals don't trigger trades
- Signal generation is idempotent

---

### Phase 4: Portfolio Management (Days 7-8)
**Goal:** Track positions, enforce risk limits, manage exits

#### Tasks:
1. **Position Manager**
   - Open/close positions
   - Update from fills
   - Calculate unrealized P&L

2. **Position Sizing**
   ```python
   def calculate_position_size(signal: TradeSignal, nav: float) -> float:
       if signal.strength == "STRONG":
           target_pct = 0.03  # 3% NAV
       elif signal.strength == "NORMAL":
           target_pct = 0.015  # 1.5% NAV
       else:
           return 0

       target_notional = nav * target_pct

       # Check limits
       current_exposure = portfolio.get_ticker_exposure(signal.ticker)
       max_per_ticker = nav * 0.05

       if current_exposure + target_notional > max_per_ticker:
           target_notional = max(0, max_per_ticker - current_exposure)

       return target_notional
   ```

3. **Exit Rules Engine**
   - Check each open position daily:
     - Holding period > max_hold_days → exit
     - Unrealized return <= stop_loss_pct → exit
     - Unrealized return >= take_profit_pct → exit
     - New SELL disclosure for same ticker → exit
   - Generate SELL signals for exits

4. **Risk Limits**
   - Per-ticker max: 5% NAV
   - Daily new exposure cap: 10% NAV
   - Global kill switch check before every order

**Acceptance:**
- Position sizing respects all limits
- Exit rules trigger correctly (use mocked dates for testing)
- Cannot exceed risk limits

---

### Phase 5: IBKR Integration (Days 9-11)
**Goal:** Execute trades in PAPER mode with full audit trail

#### Tasks:
1. **IBKR Client Setup**
   - Connect to TWS/IB Gateway using ib_insync
   - Implement connection management with reconnect logic
   - Support PAPER and LIVE modes (default PAPER)

2. **Order Execution**
   ```python
   async def place_order(
       ticker: str,
       side: Literal["BUY", "SELL"],
       notional_usd: float,
       order_type: Literal["MARKET", "LIMIT"] = "MARKET"
   ) -> Order:
       # Safety checks
       if not config.TRADING_ENABLED:
           logger.info("TRADING_DISABLED: Would place order", ...)
           return None

       # Get current price
       price = await get_latest_price(ticker)
       quantity = notional_usd / price

       # Create IBKR order
       contract = Stock(ticker, "SMART", "USD")
       order = MarketOrder(side, quantity)

       # Place order
       trade = ib.placeOrder(contract, order)

       # Save to DB
       db_order = persist_order(trade, signal_id, ...)

       return db_order
   ```

3. **Order Tracking**
   - Poll order status until terminal state
   - Handle partial fills
   - Record all state transitions

4. **Reconciliation**
   - On startup, fetch IBKR positions and open orders
   - Compare with local DB
   - Log discrepancies (don't auto-fix in MVP)

5. **Trade Command**
   - `python -m app.cli trade --dry-run`
   - Process all eligible signals
   - Respect TRADING_ENABLED flag

**Acceptance:**
- In PAPER mode with TRADING_ENABLED=true, orders are placed
- Order status updates are logged
- With TRADING_ENABLED=false, logs "would place order" but doesn't execute

---

### Phase 6: Pipeline & Commands (Days 12-13)
**Goal:** Complete CLI with daily automation

#### Tasks:
1. **CLI Structure**
   ```python
   # app/cli.py
   import typer

   app = typer.Typer()

   @app.command()
   def ingest(
       from_date: str = None,
       to_date: str = None,
       ticker: str = None
   ):
       """Fetch and normalize congressional trades from Finnhub."""
       ...

   @app.command()
   def signals():
       """Generate trading signals for new events."""
       ...

   @app.command()
   def trade(dry_run: bool = False):
       """Execute eligible signals (respects TRADING_ENABLED)."""
       ...

   @app.command()
   def reconcile():
       """Sync IBKR state with local database."""
       ...

   @app.command()
   def daily():
       """Run full daily pipeline: ingest → signals → trade → snapshot."""
       ...
   ```

2. **Daily Pipeline**
   - Run all steps in sequence
   - Generate P&L snapshot
   - Send summary email (if configured)

3. **Scheduler Setup**
   - Document cron setup for production
   - Example: `0 10 * * 1-5 cd /app && python -m app.cli daily`

**Acceptance:**
- All commands run successfully
- `daily` command orchestrates full pipeline
- Commands are idempotent

---

### Phase 7: Testing & Docs (Days 14-15)
**Goal:** Ensure reliability and usability

#### Tasks:
1. **Unit Tests**
   - `test_dedup.py`: Event ID hashing stability
   - `test_scoring.py`: Scoring logic with fixtures
   - `test_signals.py`: Signal mapping edge cases
   - `test_portfolio.py`: Position sizing and exits

2. **Integration Tests**
   - End-to-end: mock Finnhub response → signal → mock order
   - Database persistence
   - Idempotency checks

3. **Documentation**
   - README.md with setup instructions
   - Environment variables guide
   - IBKR setup guide (TWS/Gateway configuration)
   - Deployment checklist

4. **Safety Audit**
   - Verify all safety defaults
   - Test kill switch
   - Confirm PAPER mode is default

**Acceptance:**
- All tests pass
- README enables new user to set up project
- Safety controls verified

---

## 5. Environment Configuration

### Required Environment Variables

```bash
# Finnhub
FINNHUB_API_KEY=your_key_here

# Database
DB_PATH=./data/app.db

# IBKR
IBKR_HOST=127.0.0.1
IBKR_PORT=7497                    # 7497 for paper, 7496 for live
IBKR_CLIENT_ID=1
TRADING_MODE=paper                # paper | live
TRADING_ENABLED=false             # MUST be explicitly set to true

# Strategy
MAX_DELAY_DAYS=14
MIN_AMOUNT_HIGH=5000
TARGET_PCT_STRONG=0.03
TARGET_PCT_NORMAL=0.015
MAX_PER_TICKER_PCT=0.05
MAX_DAILY_EXPOSURE_PCT=0.10
MAX_HOLD_DAYS=30
STOP_LOSS_PCT=-0.08
TAKE_PROFIT_PCT=0.20

# Notifications (optional)
EMAIL_ENABLED=false
SENDGRID_API_KEY=
EMAIL_FROM=
EMAIL_TO=

# Logging
LOG_LEVEL=INFO
LOG_FILE=./data/app.log
```

---

## 6. Safety Checklist

### Before Every Run
- [ ] `TRADING_MODE=paper` (unless explicitly testing live)
- [ ] `TRADING_ENABLED=false` (until ready to trade)
- [ ] IBKR Gateway/TWS connected to PAPER account
- [ ] Database backup exists
- [ ] Sufficient margin in IBKR account

### Before Going Live
- [ ] Backtested strategy on historical data
- [ ] Tested full pipeline in PAPER for 1+ week
- [ ] Reviewed all open positions and orders
- [ ] Set conservative position sizes
- [ ] Confirmed email notifications work
- [ ] Set up monitoring/alerting

---

## 7. Success Metrics (MVP)

### Functional
- ✅ Ingest runs without errors
- ✅ No duplicate events in database
- ✅ Signals generated with correct scores
- ✅ Orders placed in PAPER mode
- ✅ Positions tracked accurately
- ✅ Exit rules trigger correctly

### Observability
- ✅ Every signal includes reasons
- ✅ Every order has full audit trail
- ✅ Can answer: "Why did we buy X on date Y?"

### Safety
- ✅ TRADING_ENABLED=false prevents orders
- ✅ Position limits never exceeded
- ✅ No trades when market is closed

---

## 8. Phase 2 Considerations (Not Implementing Now)

Design decisions that enable future enhancements:

1. **Database**: SQLite → Postgres migration path
   - Use SQLAlchemy ORM (no raw SQL)
   - Keep schema simple

2. **Data Sources**: Single → Multiple sources
   - All events have `source` field
   - Normalization layer abstracts source

3. **Strategy**: Rules → ML
   - All features stored in database
   - Scoring function is versioned

4. **UI**: CLI → Web dashboard
   - All logic in service layer (not CLI)
   - Database has full history

---

## 9. Development Workflow

### Daily Development
```bash
# Setup
python -m venv venv
source venv/bin/activate
pip install -e ".[dev]"

# Run checks
pytest
black app/ tests/
mypy app/

# Test commands
python -m app.cli ingest --from-date 2024-01-01 --to-date 2024-01-31
python -m app.cli signals
python -m app.cli trade --dry-run
```

### Deployment
```bash
# Production server
git clone <repo>
cp .env.example .env
# Edit .env with real values
python scripts/bootstrap_db.py
crontab -e  # Add daily job
```

---

## 10. Next Steps

Ready to proceed? Here's the execution order:

1. **Create project structure** (30 min)
2. **Set up dependencies** (30 min)
3. **Implement config & logging** (1 hour)
4. **Build database schema** (2 hours)
5. **Finnhub integration** (3 hours)
6. **Strategy engine** (4 hours)
7. **Portfolio manager** (4 hours)
8. **IBKR integration** (6 hours)
9. **CLI commands** (2 hours)
10. **Testing** (4 hours)

**Total Estimate: ~27 hours of focused development**

---

## Sources

Research sources used in this plan:
- [Finnhub Congressional Trading API](https://finnhub.io/docs/api/congressional-trading)
- [Finnhub Python Client](https://github.com/Finnhub-Stock-API/finnhub-python)
- [Congress Stock Trading Tracker](https://github.com/burd5/congress_stock_trading)
- [ib_insync Framework](https://github.com/erdewit/ib_insync)
- [ib_async Documentation](https://ib-api-reloaded.github.io/ib_async/)
- [MMR Trading Platform](https://github.com/9600dev/mmr)
- [Medium: Tracking Congress Stock Trades in Python](https://medium.com/@crisvelasquez/tracking-congress-stock-trades-in-python-5daa88ff9d8b)
- [Medium: A Free Way to Track Politician Stock Trades](https://medium.com/@katherinerossil/a-free-and-simple-way-to-track-politician-stock-trades-in-python-eb7208eda9aa)
