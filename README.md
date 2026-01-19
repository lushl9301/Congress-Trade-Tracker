# Congress Trade Tracker + Auto-Copy Trader

Automated trading system that tracks US Congressional stock disclosures via Finnhub API and executes mirror trades through Interactive Brokers.

**MVP Status**: Production-lean implementation with PAPER trading by default.

**Enhanced Edition**: Now with modern Python tooling (Typer, Loguru, Alembic) for better developer experience and maintainability.

## Features

- **Data Ingestion**: Fetches congressional trading data from Finnhub API (free tier)
- **Event Normalization**: Converts raw data into canonical schema with deduplication
- **Signal Generation**: Deterministic scoring based on disclosure delay, trade size, and member identity
- **Risk Controls**: Position sizing, exposure limits, stop-loss/take-profit rules
- **IBKR Integration**: Executes trades via Interactive Brokers (ib_insync)
- **Audit Trail**: Complete logging of all decisions, orders, and fills
- **Safety First**: Paper trading by default with multiple kill switches

## Modern Tooling

- **Typer CLI**: Beautiful, auto-documented command-line interface with better error messages and help text
- **Loguru Logging**: Simplified logging with automatic exception tracing, colorized output, and JSON serialization
- **Alembic Migrations**: Database schema versioning for safe schema evolution without data loss
- **Pinned Dependencies**: Reproducible builds with exact version specifications

## Quick Start

### Prerequisites

1. Python 3.11+
2. Finnhub API key (free tier): https://finnhub.io/register
3. Interactive Brokers account with TWS or IB Gateway (Paper account recommended)

### Installation

```bash
# Clone repository
git clone <your-repo-url>
cd Congress-Trade-Tracker

# Install dependencies
pip install -r requirements.txt

# Set up environment variables
cp .env.example .env  # Edit with your credentials
```

### Environment Variables

Create a `.env` file or export these variables:

```bash
# Required
export FINNHUB_API_KEY="your_finnhub_api_key"

# IBKR Settings
export IBKR_HOST="127.0.0.1"
export IBKR_PORT="7497"  # 7497 = TWS Paper, 4001 = IB Gateway Paper
export IBKR_CLIENT_ID="1"

# Trading Controls (IMPORTANT!)
export TRADING_MODE="paper"  # paper | live
export TRADING_ENABLED="false"  # Set to "true" to enable actual trading

# Optional: Email notifications
export EMAIL_ENABLED="false"
export SMTP_HOST=""
export SMTP_PORT="587"
export SMTP_USER=""
export SMTP_PASSWORD=""
export EMAIL_FROM=""
export EMAIL_TO=""
```

### Initialize Database

```bash
python -m app.run init-db
```

### Run Commands

```bash
# Fetch congressional trades
python -m app.run ingest

# Generate trading signals
python -m app.run signals

# Execute trades (respects TRADING_ENABLED flag)
python -m app.run trade

# Run daily pipeline (ingest + signals)
python -m app.run daily

# Check status
python -m app.run status

# Reconcile IBKR positions with local database
python -m app.run reconcile
```

## Architecture

```
app/
├── config.py          # Configuration from environment
├── logging.py         # Loguru-based structured logging
├── models.py          # Pydantic data models
├── db.py              # SQLite database operations
├── finnhub_client.py  # Finnhub API client
├── ingest.py          # Data ingestion pipeline
├── strategy.py        # Signal generation
├── portfolio.py       # Position management
├── ibkr/              # IBKR integration
│   ├── client.py      # IB connection
│   ├── orders.py      # Order placement
│   └── reconcile.py   # State reconciliation
├── notify/            # Notifications
│   └── email.py       # Email alerts (SendGrid)
└── run.py             # Typer-based CLI entry point

alembic/               # Database migrations
├── versions/          # Migration scripts
├── env.py            # Migration environment
└── script.py.mako    # Migration template
```

## Strategy (MVP)

### Scoring Logic

**Base Score**: 50

**Freshness** (disclosure delay):
- ≤2 days: +25
- 3-7 days: +15
- 8-14 days: +5
- >14 days: IGNORE

**Amount**:
- ≥$250k: +15
- $50k-$250k: +10
- $5k-$50k: +5
- <$5k: IGNORE

**Owner**:
- Member: +10
- Spouse: +5
- Dependent: +2

**Clustering** (multiple BUYs of same ticker in 7 days):
- ≥2 events: +10

### Signal Mapping

- Score ≥80 + BUY → **STRONG BUY**
- Score 65-79 + BUY → **NORMAL BUY**
- Score 50-64 + BUY → **WATCH** (no trade)
- SELL + have position → **STRONG SELL**
- SELL + no position → **IGNORE**

### Position Sizing

- **STRONG**: 3% of NAV
- **NORMAL**: 1.5% of NAV
- **Max per ticker**: 5% of NAV
- **Max daily exposure**: 10% of NAV

### Exit Rules

- **Max hold**: 30 days
- **Stop loss**: -8%
- **Take profit**: +20%

## Safety Features

1. **Paper Trading Default**: `TRADING_MODE=paper` by default
2. **Kill Switch**: `TRADING_ENABLED=false` prevents all order submission
3. **Idempotent**: Re-running commands is safe (deduplication)
4. **Dry-run Mode**: When `TRADING_ENABLED=false`, orders are logged but not submitted
5. **Audit Trail**: Every decision is logged with reasoning

## Database Schema

**Tables**:
- `congress_trade_events`: Normalized congressional trades
- `trade_signals`: Generated trading signals
- `positions`: Current portfolio positions
- `orders`: Order history
- `fills`: Execution fills
- `pnl_snapshots`: Performance snapshots

## Testing

```bash
# Run all tests
pytest

# Run specific test file
pytest tests/test_dedup.py

# Run with coverage
pytest --cov=app tests/
```

## Database Migrations

This project uses **Alembic** for database schema migrations, allowing you to evolve the schema over time without data loss.

### Basic Migration Commands

```bash
# Show current database version
alembic current

# View migration history
alembic history

# Upgrade to latest version
alembic upgrade head

# Downgrade one revision
alembic downgrade -1

# Create a new migration
alembic revision -m "description of changes"
```

### Note for MVP

The MVP currently uses `python -m app.run init-db` to bootstrap the database schema. Alembic is configured for future schema changes. See `alembic/README` for more details.

## Monitoring & Observability

All operations log structured events using **Loguru** with:
- **Colorized output** for better readability in development
- **Automatic exception tracing** with full context
- **Structured logging** with contextual information
- Event ingestion counts (new/duplicate)
- Signal generation (by strength)
- Order placement attempts
- Position updates
- Errors with full stack traces

Use `--json-logs` flag for JSON-formatted logs (useful for log aggregation):

```bash
python -m app.run --json-logs daily
```

The enhanced logging includes:
- Automatic timestamps and log levels
- Module and function names
- Line numbers for debugging
- Exception backtraces with local variables (in development mode)

## Production Deployment

### Before Going Live

1. **Test thoroughly in PAPER mode** for at least 2 weeks
2. **Review all fills and positions** via `reconcile` command
3. **Verify strategy performance** meets expectations
4. **Set up monitoring and alerts**
5. **Review and understand risks**

### Enabling Live Trading

```bash
# Set environment variables
export TRADING_MODE="live"
export TRADING_ENABLED="true"

# Update IBKR port for live
export IBKR_PORT="7496"  # TWS Live or 4000 for IB Gateway Live

# Run with extreme caution
python -m app.run trade
```

⚠️ **WARNING**: Live trading involves real money and risk. Start with small position sizes and monitor closely.

## Configuration Options

See `app/config.py` for all configuration options. Key parameters:

- `MAX_DELAY_DAYS`: Maximum disclosure delay (default: 14)
- `MIN_AMOUNT_HIGH`: Minimum trade amount (default: $5,000)
- `TARGET_PCT_STRONG`: Position size for STRONG signals (default: 3%)
- `TARGET_PCT_NORMAL`: Position size for NORMAL signals (default: 1.5%)
- `MAX_HOLD_DAYS`: Maximum holding period (default: 30)
- `STOP_LOSS_PCT`: Stop loss threshold (default: -8%)
- `TAKE_PROFIT_PCT`: Take profit threshold (default: +20%)

## Troubleshooting

### Cannot connect to IBKR

- Ensure TWS or IB Gateway is running
- Check port configuration (7497 for Paper TWS, 4001 for Paper Gateway)
- Verify API connections are enabled in TWS settings
- Check `IBKR_CLIENT_ID` is unique

### No data from Finnhub

- Verify `FINNHUB_API_KEY` is set correctly
- Check API rate limits (free tier has limits)
- Try with a specific symbol: `python -m app.run ingest --symbol MSFT`

### Database errors

- Ensure database is initialized: `python -m app.run init-db`
- Check file permissions on `data/` directory
- Verify SQLite is available

## Limitations (MVP)

- **No PDF scraping**: Uses only Finnhub API data
- **No options trading**: Stocks and ETFs only
- **Simple scoring**: Deterministic rules, no ML
- **Daily frequency**: Not optimized for intraday
- **Limited asset type detection**: Basic ETF heuristics

## Future Enhancements (Phase 2)

See `CLAUDE.md` for detailed Phase 2 roadmap:

- Dual-source verification (official portals + Finnhub)
- Committee/industry analysis layer
- Sector exposure caps
- Backtesting framework
- Web UI dashboard
- Advanced notifications (Slack/Telegram)

## License

[Your License Here]

## Disclaimer

This software is for educational and research purposes. Trading stocks carries risk. Past congressional trading activity does not guarantee future performance. Use at your own risk. The authors are not responsible for any financial losses.

## Support

For bugs or feature requests, please open an issue on GitHub.
