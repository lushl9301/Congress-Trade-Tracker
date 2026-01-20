# CLAUDE.MD — Congress Trade Tracker + Auto-Copy Trader (Finnhub free tier + IBKR)

You are Claude Code. Build a production-lean MVP that:
1) fetches US Congress trade disclosures from Finnhub (free tier),
2) normalizes + deduplicates events,
3) generates trading signals (MVP rules),
4) executes trades via Interactive Brokers (IBKR) in PAPER first,
5) logs everything for audit + iteration,
6) notifies via email (optional but recommended).

Design for “ship fast, iterate safely”: clear modules, strong logging, strict risk controls.

---

## 0) Non-goals (for MVP)
- No PDF scraping of official House/Senate portals (Phase 2).
- No options trading (stocks/ETFs only).
- No complex ML. Use deterministic rules + scoring.
- No intraday high-frequency. This is event-driven, low turnover.

---

## 1) Core product behavior (what the bot does)
### 1.1 Data ingestion
- Poll Finnhub congressional trading endpoint on a schedule (e.g., every 30–60 minutes in market hours; daily is okay for MVP).
- Store raw responses and a normalized trade event table.

### 1.2 Event normalization
Convert each record into a canonical `CongressTradeEvent` with fields below.

### 1.3 Dedup + idempotency
- Every event must map to a stable `event_id` hash so repeated polling never triggers duplicate orders.
- Strategy engine must be idempotent: re-running it with same data must not double-trade.

### 1.4 Signal generation
- Apply filters (delay, amount, asset whitelist, liquidity constraints).
- Produce a `Signal` of type: `STRONG_BUY`, `BUY`, `WATCH`, `SELL`, `IGNORE`.

### 1.5 Execution
- Convert signals to orders via IBKR, using PAPER trading by default.
- Use position sizing + hard caps.
- Maintain a portfolio state machine: open positions, holding period, exits.

### 1.6 Observability & audit
- Persist every decision: input event, computed features, signal, order request, order response, fills, PnL snapshots.
- Make it easy to answer: “Why did we buy/sell?”

---

## 2) Tech choices (recommended)
### 2.1 Language
- Python 3.11+ (fast iteration, lots of finance tooling).

### 2.2 Libraries
- HTTP: `httpx` (async-friendly) or `requests` (simple).
- Data validation: `pydantic`.
- DB: SQLite for MVP; design so it can swap to Postgres later.
- Scheduling: simple cron + `python -m app.run` OR `APScheduler`.
- Logging: `structlog` or stdlib `logging` with JSON formatter.
- Email: SMTP (SendGrid/Mailgun) optional; stub first.

### 2.3 IBKR integration
Choose ONE path and implement cleanly:
- Option A: `ib_insync` (wrapper around TWS/IB Gateway; fastest dev).
- Option B: IBKR Client Portal Web API (more “webby” but requires gateway setup).

MVP default: use `ib_insync` + IB Gateway/TWS in PAPER mode.

---

## 3) Data model

### 3.1 Canonical event schema
Create a Pydantic model:

`CongressTradeEvent`:
- `event_id: str` (stable hash)
- `source: Literal["finnhub"]`
- `member_name: str | None`
- `member_id: str | None` (if available)
- `owner: Literal["member","spouse","dependent","unknown"]`
- `ticker: str` (e.g., "HAL")
- `asset_type: Literal["stock","etf","unknown"]` (infer if possible)
- `transaction_type: Literal["BUY","SELL","OTHER"]`
- `trade_date: date | None`
- `disclosure_date: date | None`
- `amount_low: float | None`
- `amount_high: float | None`
- `currency: str | None` (usually USD)
- `raw: dict` (full raw record)

Compute:
- `delay_days: int | None` = disclosure_date - trade_date
- `amount_mid: float | None` = (low+high)/2

### 3.2 Signal schema
`TradeSignal`:
- `signal_id: str` (hash of event_id + strategy version)
- `event_id: str`
- `ticker: str`
- `action: Literal["BUY","SELL","NONE"]`
- `strength: Literal["STRONG","NORMAL","WATCH","IGNORE"]`
- `score: int` (0–100)
- `reason: list[str]` (human-readable short reasons)
- `created_at: datetime`
- `strategy_version: str`

### 3.3 Portfolio state
Maintain tables:
- `positions`:
  - `ticker`
  - `qty`
  - `avg_cost`
  - `opened_at`
  - `last_updated_at`
  - `exit_rule` (e.g., "HOLD_30D", "STOP_TAKE", etc.)
  - `max_hold_days`
  - `stop_loss_pct`
  - `take_profit_pct`
- `orders`:
  - local `order_id`, ibkr `permId` / `orderId`, status, timestamps, request payload, response payload
- `fills`:
  - fill price, qty, commissions, timestamp

---

## 4) Strategy (MVP rules)

### 4.1 Universe & filters
Only trade:
- US equities/ETFs with a valid ticker.
- Exclude: OTC, penny stocks (use price/liquidity checks if data available; otherwise maintain a manual blacklist).

Filters:
- `delay_days` must be not null and <= `MAX_DELAY_DAYS` (default 21, relaxed from 14 to handle holiday delays).
- `amount_high` must be >= `MIN_AMOUNT_HIGH` (default 5000).
- `owner` weighting:
  - member: +10 score
  - spouse: +5 score
  - dependent: +2 score
  - unknown: +0 score

### 4.2 Scoring (0–100)
Start with base score 50 then adjust:

Freshness (graduated scoring to prefer fresher disclosures):
- if delay_days <= 2: +25
- 3–7: +15
- 8–14: +5
- 15–21: +2 (lower score for older disclosures, handles holiday delays)
- >21: reject (IGNORE)

Amount:
- if amount_high >= 250000: +15
- 50000–249999: +10
- 5000–49999: +5
- <5000: reject (IGNORE)

Owner:
- member +10, spouse +5, dependent +2

Cluster buying (optional MVP+):
- if same ticker has >=2 BUY events in last 7 days: +10

Cap:
- score = min(100, max(0, score))

### 4.3 Mapping score → signal
- score >= 80 and transaction_type==BUY → `STRONG_BUY`
- 65–79 and BUY → `BUY`
- 50–64 and BUY → `WATCH` (notify only, no trade)
- SELL events:
  - if a position exists in portfolio, generate `SELL` (strong)
  - else ignore

### 4.4 Entry rules
For BUY signals:
- Place order next market session:
  - default: Market order at next open OR Limit order near previous close (configurable).
- Position sizing:
  - `TARGET_PCT_STRONG = 0.03` (3% NAV)
  - `TARGET_PCT_NORMAL = 0.015` (1.5% NAV)
- Hard caps:
  - per-ticker max: 0.05 NAV
  - per-sector max (Phase 2)
  - max new exposure per day: 0.10 NAV
- If already holding ticker:
  - allow add only if current exposure < per-ticker max and signal is STRONG and last add > 7 days ago.

### 4.5 Exit rules (keep simple)
For every opened position set:
- `max_hold_days = 30` (time-based exit)
- `stop_loss_pct = -0.08` (8% loss)
- `take_profit_pct = +0.20` (20% gain)

Exit triggers:
- If reverse SELL disclosure from same member/ticker AND currently holding → exit at next session.
- If current return <= stop_loss_pct → exit at next session.
- If current return >= take_profit_pct → exit at next session.
- If holding days >= max_hold_days → exit at next session.

Note: Price monitoring can be done once daily at market close for MVP.

---

## 5) IBKR execution requirements

### 5.1 Safety defaults
- PAPER account only by default.
- A `--live` flag must be required to enable live trading.
- Enforce a global “kill switch” env var: `TRADING_ENABLED=false` prevents any order placement.

### 5.2 Order placement
Implement:
- `place_order(ticker, side, notional_usd or qty, order_type, tif)`
- Convert notional to shares using latest price snapshot.

### 5.3 Reconciliation
After placing orders:
- Poll order status until terminal state (Filled/Cancelled/Rejected).
- Record fills and update positions.
- On restart, reconcile from IBKR open orders + positions to local DB.

---

## 6) Config & secrets

Use environment variables + a `config.yaml` (optional). Required env vars:
- `FINNHUB_API_KEY`
- `DB_PATH` (default `./data/app.db`)
- `IBKR_HOST`, `IBKR_PORT`, `IBKR_CLIENT_ID`
- `TRADING_MODE` = `paper`|`live` (default `paper`)
- `TRADING_ENABLED` = `true|false` (default false)
- `EMAIL_ENABLED` + SMTP settings (optional)

All secrets must be read from env; never hardcode.

---

## 7) Project structure

app/
init.py
config.py
logging.py
models.py
db.py
finnhub_client.py
ingest.py
strategy.py
portfolio.py
ibkr/
init.py
client.py
orders.py
reconcile.py
notify/
email.py
run.py
migrations/ (optional)
tests/
test_dedup.py
test_scoring.py
test_signal_mapping.py
test_portfolio_rules.py
scripts/
bootstrap_db.py
README.md


---

## 8) CLI commands (must-have)
Provide a simple CLI (argparse/typer):

- `python -m app.run ingest`  
  Fetch from Finnhub, normalize, upsert events.

- `python -m app.run signals`  
  Generate signals for new events and store them.

- `python -m app.run trade`  
  Execute eligible signals (respect TRADING_ENABLED).

- `python -m app.run reconcile`  
  Sync IBKR state → local DB.

- `python -m app.run daily`  
  Runs ingest → signals → trade → PnL snapshot.

All commands should be safe to run repeatedly.

---

## 9) MVP acceptance tests (definition of done)

### 9.1 Data
- Running `ingest` twice with same upstream data does not create duplicate events.
- `event_id` stable across runs.

### 9.2 Strategy
- Given synthetic events, scoring and signal mapping match the spec.
- `WATCH` produces no order.

### 9.3 Execution (paper)
- In PAPER mode with TRADING_ENABLED=true, a BUY signal places an order and it is logged.
- If TRADING_ENABLED=false, no orders are placed, but the bot still logs “would place order”.

### 9.4 Portfolio
- Positions table updates after fills.
- Exit rules trigger correctly (time-based exit can be simulated by mocking dates).

### 9.5 Observability
- Every signal includes reasons.
- Every order has request/response persisted.

---

## 10) Phase 2 (make it “better”)
Do NOT implement now, but design so it’s easy later:
- Dual-source verification: official House/Senate portals + Finnhub.
- Committee/industry “conflict/overlap” explanation layer (non-trading factor by default).
- Sector exposure caps (GICS classification).
- Backtesting harness and parameter sweeps.
- Web UI dashboard (signals, orders, PnL, audit trail).
- Slack/Telegram notifications.

---

## 11) Implementation order (recommended)
1) DB + models + logging
2) Finnhub client + ingest + dedup hashing
3) Strategy scoring + signal mapping
4) Portfolio state machine (open/close, hold days, stop/take)
5) IBKR paper integration + order logging
6) Daily pipeline + reconcile
7) Tests for dedup + scoring + trade gating

---

## 12) Hashing / dedup specification
Define `event_id` = SHA256 of a canonical string:

`source|ticker|transaction_type|trade_date|disclosure_date|amount_low|amount_high|member_name|owner`

- Normalize to uppercase ticker.
- Use ISO date strings.
- Use empty string for missing fields.
- Round amounts to nearest dollar if needed.

This must be stable.

---

## 13) Notes & guardrails
- Always handle missing trade_date/disclosure_date gracefully (skip trading if delay cannot be computed).
- Avoid buying illiquid tickers; if you don’t have price/volume data, start with a whitelist of large-cap tickers/ETFs.
- Never “fire and forget”: always reconcile and persist.
- Keep strategy versioned (e.g., `strategy_version = "mvp_v1"`).
- Write clean, readable code with docstrings and type hints.

---

## 14) Output
After implementation, print a short run summary each time:
- new events ingested
- new signals generated
- orders placed (or skipped due to gating)
- current exposure / number of positions
- any errors with clear next actions
