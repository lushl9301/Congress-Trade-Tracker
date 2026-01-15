"""SQLite database helpers."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Iterable

from app.models import CongressTradeEvent, TradeSignal


class Database:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path)
        self._conn.row_factory = sqlite3.Row

    def close(self) -> None:
        self._conn.close()

    def init_schema(self) -> None:
        cursor = self._conn.cursor()
        cursor.executescript(
            """
            CREATE TABLE IF NOT EXISTS events (
                event_id TEXT PRIMARY KEY,
                source TEXT NOT NULL,
                member_name TEXT,
                member_id TEXT,
                owner TEXT NOT NULL,
                ticker TEXT NOT NULL,
                asset_type TEXT NOT NULL,
                transaction_type TEXT NOT NULL,
                trade_date TEXT,
                disclosure_date TEXT,
                amount_low REAL,
                amount_high REAL,
                currency TEXT,
                delay_days INTEGER,
                amount_mid REAL,
                raw_json TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS signals (
                signal_id TEXT PRIMARY KEY,
                event_id TEXT NOT NULL,
                ticker TEXT NOT NULL,
                action TEXT NOT NULL,
                strength TEXT NOT NULL,
                score INTEGER NOT NULL,
                reason_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                strategy_version TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS orders (
                order_id INTEGER PRIMARY KEY AUTOINCREMENT,
                signal_id TEXT,
                ticker TEXT NOT NULL,
                side TEXT NOT NULL,
                qty REAL,
                notional REAL,
                status TEXT NOT NULL,
                request_json TEXT NOT NULL,
                response_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS positions (
                ticker TEXT PRIMARY KEY,
                qty REAL NOT NULL,
                avg_cost REAL NOT NULL,
                opened_at TEXT NOT NULL,
                last_updated_at TEXT NOT NULL,
                exit_rule TEXT NOT NULL,
                max_hold_days INTEGER NOT NULL,
                stop_loss_pct REAL NOT NULL,
                take_profit_pct REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS fills (
                fill_id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id INTEGER NOT NULL,
                ticker TEXT NOT NULL,
                qty REAL NOT NULL,
                fill_price REAL NOT NULL,
                commissions REAL NOT NULL,
                fill_time TEXT NOT NULL
            );
            """
        )
        self._conn.commit()

    def upsert_events(self, events: Iterable[CongressTradeEvent]) -> int:
        cursor = self._conn.cursor()
        inserted = 0
        for event in events:
            cursor.execute(
                """
                INSERT OR IGNORE INTO events (
                    event_id, source, member_name, member_id, owner, ticker,
                    asset_type, transaction_type, trade_date, disclosure_date,
                    amount_low, amount_high, currency, delay_days, amount_mid, raw_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.event_id,
                    event.source,
                    event.member_name,
                    event.member_id,
                    event.owner,
                    event.ticker,
                    event.asset_type,
                    event.transaction_type,
                    event.trade_date.isoformat() if event.trade_date else None,
                    event.disclosure_date.isoformat() if event.disclosure_date else None,
                    event.amount_low,
                    event.amount_high,
                    event.currency,
                    event.delay_days,
                    event.amount_mid,
                    json.dumps(event.raw),
                ),
            )
            if cursor.rowcount:
                inserted += 1
        self._conn.commit()
        return inserted

    def fetch_events_without_signals(self) -> list[sqlite3.Row]:
        cursor = self._conn.cursor()
        cursor.execute(
            """
            SELECT * FROM events
            WHERE event_id NOT IN (SELECT event_id FROM signals)
            ORDER BY disclosure_date DESC
            """
        )
        return cursor.fetchall()

    def insert_signals(self, signals: Iterable[TradeSignal]) -> int:
        cursor = self._conn.cursor()
        inserted = 0
        for signal in signals:
            cursor.execute(
                """
                INSERT OR IGNORE INTO signals (
                    signal_id, event_id, ticker, action, strength, score,
                    reason_json, created_at, strategy_version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    signal.signal_id,
                    signal.event_id,
                    signal.ticker,
                    signal.action,
                    signal.strength,
                    signal.score,
                    json.dumps(signal.reason),
                    signal.created_at.isoformat(),
                    signal.strategy_version,
                ),
            )
            if cursor.rowcount:
                inserted += 1
        self._conn.commit()
        return inserted

    def fetch_signals_for_trade(self) -> list[sqlite3.Row]:
        cursor = self._conn.cursor()
        cursor.execute(
            """
            SELECT * FROM signals
            WHERE strength IN ('STRONG', 'NORMAL') AND action IN ('BUY', 'SELL')
            ORDER BY created_at DESC
            """
        )
        return cursor.fetchall()

    def fetch_positions(self) -> list[sqlite3.Row]:
        cursor = self._conn.cursor()
        cursor.execute("SELECT * FROM positions")
        return cursor.fetchall()

    def record_order(self, payload: dict, response: dict) -> int:
        cursor = self._conn.cursor()
        cursor.execute(
            """
            INSERT INTO orders (
                signal_id, ticker, side, qty, notional, status,
                request_json, response_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload.get("signal_id"),
                payload["ticker"],
                payload["side"],
                payload.get("qty"),
                payload.get("notional"),
                response.get("status", "unknown"),
                json.dumps(payload),
                json.dumps(response),
                response.get("timestamp"),
            ),
        )
        self._conn.commit()
        return int(cursor.lastrowid)

    def upsert_position(self, ticker: str, qty: float, avg_cost: float, metadata: dict) -> None:
        cursor = self._conn.cursor()
        cursor.execute(
            """
            INSERT INTO positions (
                ticker, qty, avg_cost, opened_at, last_updated_at, exit_rule,
                max_hold_days, stop_loss_pct, take_profit_pct
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(ticker) DO UPDATE SET
                qty = excluded.qty,
                avg_cost = excluded.avg_cost,
                last_updated_at = excluded.last_updated_at,
                exit_rule = excluded.exit_rule,
                max_hold_days = excluded.max_hold_days,
                stop_loss_pct = excluded.stop_loss_pct,
                take_profit_pct = excluded.take_profit_pct
            """,
            (
                ticker,
                qty,
                avg_cost,
                metadata["opened_at"],
                metadata["last_updated_at"],
                metadata["exit_rule"],
                metadata["max_hold_days"],
                metadata["stop_loss_pct"],
                metadata["take_profit_pct"],
            ),
        )
        self._conn.commit()

    def record_fill(self, order_id: int, fill: dict) -> None:
        cursor = self._conn.cursor()
        cursor.execute(
            """
            INSERT INTO fills (order_id, ticker, qty, fill_price, commissions, fill_time)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                order_id,
                fill["ticker"],
                fill["qty"],
                fill["fill_price"],
                fill.get("commissions", 0.0),
                fill["fill_time"],
            ),
        )
        self._conn.commit()
