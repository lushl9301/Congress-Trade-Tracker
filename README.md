# Congress Trade Tracker (MVP)

This repository contains a production-lean MVP for ingesting U.S. congressional trade disclosures, generating trading signals, and executing paper trades with IBKR. It follows the specification in `CLAUDE.md`.

## Quickstart

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Set environment variables:

```bash
export FINNHUB_API_KEY=your_key
export DB_PATH=./data/app.db
export TRADING_MODE=paper
export TRADING_ENABLED=false
```

Initialize the database:

```bash
python scripts/bootstrap_db.py
```

Run the CLI:

```bash
python -m app.run ingest
python -m app.run signals
python -m app.run trade
python -m app.run daily
```

## Notes

- Trading is gated by `TRADING_ENABLED=false` by default.
- Paper trading is enforced unless `TRADING_MODE=live` is explicitly set.
