# Congress Trade Tracker

> An automated investment assistant that tracks US congressional stock trades and converts public disclosures into disciplined, explainable investment decisions.

## What Is This?

Members of Congress must publicly disclose their stock trades within 30-45 days (STOCK Act of 2012). This system:

1. **Monitors** these disclosures automatically via Finnhub API
2. **Evaluates** each trade using rule-based scoring (freshness, amount, clustering)
3. **Executes** trades via Interactive Brokers with strict risk controls
4. **Audits** every decision with full explainability

This is **not insider trading** - it's systematic extraction of signals from public information.

## Key Features

- **Emotion-Free**: Rules-based decisions, no FOMO or panic
- **Conservative**: Position limits, stop losses, profit targets
- **Explainable**: Every signal includes clear reasons
- **Safe by Default**: Trading disabled unless explicitly enabled
- **Paper Trading First**: Test strategies risk-free

## Quick Start

### 1. Install

```bash
# Clone repository
git clone <repo-url>
cd Congress-Trade-Tracker

# Create virtual environment
python3.11 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure

```bash
# Copy example environment file
cp .env.example .env

# Edit .env with your settings
nano .env
```

**Required settings:**
```bash
FINNHUB_API_KEY=your_key_here  # Get free key at finnhub.io
TRADING_ENABLED=false          # Keep false until ready!
ACCOUNT_MODE=paper             # Use paper trading first
```

### 3. Initialize Database

```bash
python -m tracker.cli init
```

### 4. Test the Pipeline

```bash
# Fetch recent congressional trades
python -m tracker.cli ingest --days-back 30

# Generate trading signals
python -m tracker.cli evaluate

# See what would be traded (dry run)
python -m tracker.cli trade --dry-run

# Check configuration
python -m tracker.cli config
```

## Commands

### `init`
Initialize the database (run once)

```bash
python -m tracker.cli init
```

### `ingest`
Fetch congressional trade disclosures

```bash
# Last 30 days (default)
python -m tracker.cli ingest

# Last 90 days
python -m tracker.cli ingest --days-back 90

# Specific ticker
python -m tracker.cli ingest --symbol AAPL

# Date range
python -m tracker.cli ingest --from-date 2024-01-01 --to-date 2024-12-31
```

### `evaluate`
Generate trading signals from disclosures

```bash
python -m tracker.cli evaluate
```

### `trade`
Execute trading signals

```bash
# Dry run (see what would be traded)
python -m tracker.cli trade --dry-run

# Actually trade (requires TRADING_ENABLED=true)
python -m tracker.cli trade
```

### `check-exits`
Check positions for exit conditions

```bash
python -m tracker.cli check-exits
```

### `status`
View current portfolio positions

```bash
python -m tracker.cli status
```

### `daily`
Run full pipeline (ingest → evaluate → check exits → trade)

```bash
python -m tracker.cli daily
```

### `config`
Show current configuration

```bash
python -m tracker.cli config
```

## How It Works

### 1. Data Ingestion

Fetches disclosures from Finnhub API and normalizes them:

```
Raw Finnhub Data → Disclosure Model → Database
- Politician name
- Ticker symbol
- BUY/SELL
- Trade date
- Disclosure date
- Amount range
```

**Deduplication**: Uses (politician, ticker, trade_date, amount) to avoid duplicates.

### 2. Signal Evaluation

Each disclosure is **filtered**, **scored**, and **mapped to action**:

#### Filters (Hard Rejections)
- Delay > 45 days → Too stale
- Amount < $5,000 → Too small
- Invalid ticker → Skip
- OTC/penny stocks → Too risky

#### Scoring (0-100)

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

**Politician** (max +15):
- Member: +15
- Spouse: +10
- Dependent: +5

**Cluster** (max +15):
- 4+ politicians bought same ticker: +15
- 3 politicians: +10
- 2 politicians: +5

#### Action Mapping

| Score | Action | Confidence | Position Size |
|-------|--------|------------|---------------|
| 85-100 | BUY | HIGH | 4% NAV |
| 70-84 | BUY | MEDIUM | 2% NAV |
| 50-69 | WATCH | LOW | No trade |
| 0-49 | IGNORE | N/A | No trade |

### 3. Portfolio Management

**Position Limits**:
- Max 8% per ticker
- Max 15 total positions
- Min $500 position size
- Max 5% new positions per day

**Exit Rules** (first triggered wins):
1. **Time**: 30 days from entry
2. **Profit**: +20% unrealized gain
3. **Stop**: -10% unrealized loss
4. **Cluster Sell**: 2+ politicians sell → exit immediately

### 4. Trade Execution

Uses `ib-insync` to connect to Interactive Brokers:

- Market orders at next session
- Full audit trail (request → response → fills)
- Position tracking and reconciliation

**Safety Controls**:
- `TRADING_ENABLED=false` by default
- Paper mode default (port 7497)
- Pre-trade checks (market open, limits, etc.)
- Read-only connection if trading disabled

## Interactive Brokers Setup

### 1. Download Software

**Option A: TWS (Trader Workstation)**
- Download from https://www.interactivebrokers.com/
- Full-featured desktop app

**Option B: IB Gateway**
- Lighter weight, headless
- Recommended for automation

### 2. Configure Paper Account

1. Log into Account Management
2. Navigate to Settings → Paper Trading
3. Enable paper trading account
4. Note your paper account credentials

### 3. Enable API Access

In TWS/Gateway:
1. Go to: **Edit → Global Configuration → API → Settings**
2. ✅ Enable ActiveX and Socket Clients
3. ✅ Read-Only API (recommended initially)
4. Trusted IPs: `127.0.0.1`
5. Socket port: `7497` (paper) or `7496` (live)

### 4. Connect

```bash
# Start TWS/Gateway first, then:
python -m tracker.cli status
```

If connected successfully, you'll see account info.

## Safety Checklist

Before going live:

- [ ] Tested in paper mode for 2+ weeks
- [ ] Reviewed all generated signals
- [ ] Verified exit rules trigger correctly
- [ ] Confirmed position limits work
- [ ] Set up email notifications
- [ ] Have monitoring/alerting
- [ ] Started with small capital
- [ ] Understand all risks

## Configuration Reference

### Environment Variables

```bash
# Trading Controls
TRADING_ENABLED=false           # Must be "true" to trade
ACCOUNT_MODE=paper              # "paper" or "live"

# Data
FINNHUB_API_KEY=xxx             # Required - get from finnhub.io

# Database
DATABASE_URL=sqlite:///./data/tracker.db

# Interactive Brokers
IBKR_HOST=127.0.0.1
IBKR_PORT=7497                  # 7497=paper, 7496=live
IBKR_CLIENT_ID=1

# Position Limits
MAX_POSITION_PCT=0.08           # 8% max per ticker
MAX_DAILY_EXPOSURE_PCT=0.05     # 5% max new per day
MAX_POSITIONS=15
MIN_POSITION_SIZE=500

# Exit Rules
MAX_HOLD_DAYS=30
PROFIT_TARGET_PCT=0.20          # 20% profit target
STOP_LOSS_PCT=0.10              # 10% stop loss

# Notifications (Optional)
EMAIL_ENABLED=false
SENDGRID_API_KEY=
EMAIL_FROM=
EMAIL_TO=

# Logging
LOG_LEVEL=INFO
```

## Deployment

### Cron Job (Linux/Mac)

```bash
# Edit crontab
crontab -e

# Run daily at 5 PM (after market close)
0 17 * * 1-5 cd /path/to/Congress-Trade-Tracker && ./venv/bin/python -m tracker.cli daily >> logs/cron.log 2>&1
```

### Systemd Service (Linux)

Create `/etc/systemd/system/congress-tracker.service`:

```ini
[Unit]
Description=Congress Trade Tracker Daily Run
After=network.target

[Service]
Type=oneshot
User=youruser
WorkingDirectory=/path/to/Congress-Trade-Tracker
ExecStart=/path/to/venv/bin/python -m tracker.cli daily
StandardOutput=append:/path/to/logs/daily.log
StandardError=append:/path/to/logs/error.log

[Install]
WantedBy=multi-user.target
```

Enable timer:
```bash
sudo systemctl enable congress-tracker.service
sudo systemctl start congress-tracker.service
```

## Troubleshooting

### "No valid price for ticker"
- Check if market is open
- Verify ticker exists and is tradeable
- Check IBKR market data subscriptions

### "Connection refused" to IBKR
- Ensure TWS/Gateway is running
- Check port matches (.env vs TWS settings)
- Verify API is enabled in TWS settings
- Check firewall rules

### "Insufficient permissions"
- Ensure account has margin/options enabled (if needed)
- Check if account is funded
- Verify you're connected to correct account (paper vs live)

### Signals not generating
- Run `ingest` first to fetch data
- Check Finnhub API key is valid
- Look at logs in `logs/tracker_YYYY-MM-DD.log`

## Development

### Run Tests

```bash
pytest
```

### Format Code

```bash
black tracker/ tests/
```

### Type Checking

```bash
mypy tracker/
```

## Architecture

```
tracker/
├── __init__.py
├── config.py          # Environment settings
├── logger.py          # Logging setup
├── models.py          # Pydantic data models
├── database.py        # SQLAlchemy ORM
├── ingest.py          # Finnhub data fetching
├── evaluate.py        # Signal scoring and generation
├── portfolio.py       # Position management
├── execute.py         # IBKR trade execution
└── cli.py             # Command-line interface
```

## Roadmap

### Phase 2 Features (Not Implemented)
- [ ] Multiple data sources (House API, Senate website)
- [ ] Committee assignment analysis
- [ ] Historical politician performance tracking
- [ ] Advanced exits (trailing stops, sector rotation)
- [ ] Web dashboard
- [ ] Backtesting framework
- [ ] Slack/Telegram notifications

## Disclaimer

**This software is for educational and research purposes.**

- Not financial advice
- Past congressional trades don't predict future returns
- You can lose money
- Only invest what you can afford to lose
- Test thoroughly in paper trading first
- Understand all risks before going live

## License

MIT License - see LICENSE file

## Support

- **Issues**: https://github.com/your-repo/issues
- **Discussions**: https://github.com/your-repo/discussions

---

Built with Python 3.11+, ib-insync, Finnhub API, SQLAlchemy, and Typer.
