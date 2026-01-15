"""
Database module for Congress Trade Tracker.
Uses SQLite for MVP with design that can migrate to Postgres later.
"""
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Generator

from app.config import config
from app.logging import get_logger
from app.models import CongressTradeEvent, Fill, Order, Position, TradeSignal

logger = get_logger(__name__)


class Database:
    """Database manager for SQLite operations."""

    def __init__(self, db_path: Path | None = None):
        """Initialize database connection."""
        self.db_path = db_path or config.DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        logger.info(f"Database initialized at {self.db_path}")

    @contextmanager
    def get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        """
        Context manager for database connections.
        Automatically commits on success and rolls back on error.
        """
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row  # Enable column access by name
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def init_schema(self) -> None:
        """Create all database tables if they don't exist."""
        logger.info("Initializing database schema")

        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Congress trade events table
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS congress_trade_events (
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
                    delay_days INTEGER,
                    amount_low REAL,
                    amount_high REAL,
                    amount_mid REAL,
                    currency TEXT,
                    raw TEXT,
                    created_at TEXT NOT NULL,
                    UNIQUE(event_id)
                )
                """
            )

            # Index for querying by ticker and date
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_events_ticker_date
                ON congress_trade_events(ticker, trade_date)
                """
            )

            # Index for querying by disclosure date
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_events_disclosure_date
                ON congress_trade_events(disclosure_date)
                """
            )

            # Trade signals table
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS trade_signals (
                    signal_id TEXT PRIMARY KEY,
                    event_id TEXT NOT NULL,
                    ticker TEXT NOT NULL,
                    action TEXT NOT NULL,
                    strength TEXT NOT NULL,
                    score INTEGER NOT NULL,
                    reason TEXT,
                    strategy_version TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (event_id) REFERENCES congress_trade_events(event_id),
                    UNIQUE(signal_id)
                )
                """
            )

            # Index for querying signals by ticker and strength
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_signals_ticker_strength
                ON trade_signals(ticker, strength, created_at)
                """
            )

            # Positions table
            cursor.execute(
                """
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
                )
                """
            )

            # Orders table
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS orders (
                    order_id TEXT PRIMARY KEY,
                    ibkr_order_id INTEGER,
                    ibkr_perm_id INTEGER,
                    ticker TEXT NOT NULL,
                    side TEXT NOT NULL,
                    qty REAL NOT NULL,
                    order_type TEXT NOT NULL,
                    limit_price REAL,
                    tif TEXT NOT NULL,
                    status TEXT NOT NULL,
                    request_payload TEXT,
                    response_payload TEXT,
                    signal_id TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (signal_id) REFERENCES trade_signals(signal_id)
                )
                """
            )

            # Index for querying orders by status and ticker
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_orders_status_ticker
                ON orders(status, ticker, created_at)
                """
            )

            # Fills table
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS fills (
                    fill_id TEXT PRIMARY KEY,
                    order_id TEXT NOT NULL,
                    ibkr_exec_id TEXT,
                    ticker TEXT NOT NULL,
                    side TEXT NOT NULL,
                    qty REAL NOT NULL,
                    price REAL NOT NULL,
                    commission REAL NOT NULL DEFAULT 0.0,
                    filled_at TEXT NOT NULL,
                    FOREIGN KEY (order_id) REFERENCES orders(order_id)
                )
                """
            )

            # Index for querying fills by order
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_fills_order
                ON fills(order_id, filled_at)
                """
            )

            # PnL snapshots table
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS pnl_snapshots (
                    snapshot_id TEXT PRIMARY KEY,
                    snapshot_at TEXT NOT NULL,
                    total_equity REAL NOT NULL,
                    cash REAL NOT NULL,
                    positions_value REAL NOT NULL,
                    realized_pnl REAL NOT NULL DEFAULT 0.0,
                    unrealized_pnl REAL NOT NULL DEFAULT 0.0,
                    num_positions INTEGER NOT NULL DEFAULT 0,
                    positions_detail TEXT
                )
                """
            )

            # Index for querying snapshots by time
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_snapshots_time
                ON pnl_snapshots(snapshot_at DESC)
                """
            )

            logger.info("Database schema initialized successfully")

    # ==================== Congress Trade Events ====================

    def upsert_event(self, event: CongressTradeEvent) -> bool:
        """
        Insert or update a congress trade event.
        Returns True if new event was inserted, False if duplicate.
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Check if event already exists
            cursor.execute(
                "SELECT event_id FROM congress_trade_events WHERE event_id = ?",
                (event.event_id,),
            )
            exists = cursor.fetchone() is not None

            if exists:
                logger.debug(f"Event {event.event_id} already exists, skipping")
                return False

            # Insert new event
            cursor.execute(
                """
                INSERT INTO congress_trade_events (
                    event_id, source, member_name, member_id, owner,
                    ticker, asset_type, transaction_type,
                    trade_date, disclosure_date, delay_days,
                    amount_low, amount_high, amount_mid, currency,
                    raw, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    event.delay_days,
                    event.amount_low,
                    event.amount_high,
                    event.amount_mid,
                    event.currency,
                    json.dumps(event.raw),
                    event.created_at.isoformat(),
                ),
            )

            logger.info(f"Inserted new event {event.event_id} for {event.ticker}")
            return True

    def get_events_without_signals(self, strategy_version: str) -> list[CongressTradeEvent]:
        """Get events that don't have signals generated yet for given strategy version."""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT e.* FROM congress_trade_events e
                LEFT JOIN trade_signals s
                    ON e.event_id = s.event_id
                    AND s.strategy_version = ?
                WHERE s.signal_id IS NULL
                ORDER BY e.disclosure_date DESC
                """,
                (strategy_version,),
            )

            events = []
            for row in cursor.fetchall():
                events.append(self._row_to_event(dict(row)))

            return events

    def get_recent_events_by_ticker(
        self, ticker: str, days: int = 7
    ) -> list[CongressTradeEvent]:
        """Get recent events for a specific ticker within N days."""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT * FROM congress_trade_events
                WHERE ticker = ?
                AND trade_date >= date('now', '-' || ? || ' days')
                ORDER BY trade_date DESC
                """,
                (ticker, days),
            )

            events = []
            for row in cursor.fetchall():
                events.append(self._row_to_event(dict(row)))

            return events

    # ==================== Trade Signals ====================

    def insert_signal(self, signal: TradeSignal) -> None:
        """Insert a trade signal."""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute(
                """
                INSERT OR REPLACE INTO trade_signals (
                    signal_id, event_id, ticker, action, strength,
                    score, reason, strategy_version, created_at
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
                    signal.strategy_version,
                    signal.created_at.isoformat(),
                ),
            )

            logger.info(f"Inserted signal {signal.signal_id} for {signal.ticker}: {signal.action}")

    def get_unexecuted_signals(self) -> list[TradeSignal]:
        """Get signals that haven't been executed yet (no order placed)."""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT s.* FROM trade_signals s
                LEFT JOIN orders o ON s.signal_id = o.signal_id
                WHERE o.order_id IS NULL
                AND s.action IN ('BUY', 'SELL')
                AND s.strength IN ('STRONG', 'NORMAL')
                ORDER BY s.created_at ASC
                """
            )

            signals = []
            for row in cursor.fetchall():
                signals.append(self._row_to_signal(dict(row)))

            return signals

    # ==================== Positions ====================

    def upsert_position(self, position: Position) -> None:
        """Insert or update a position."""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute(
                """
                INSERT OR REPLACE INTO positions (
                    ticker, qty, avg_cost, opened_at, last_updated_at,
                    exit_rule, max_hold_days, stop_loss_pct, take_profit_pct
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    position.ticker,
                    position.qty,
                    position.avg_cost,
                    position.opened_at.isoformat(),
                    position.last_updated_at.isoformat(),
                    position.exit_rule,
                    position.max_hold_days,
                    position.stop_loss_pct,
                    position.take_profit_pct,
                ),
            )

            logger.info(f"Upserted position for {position.ticker}: {position.qty} @ {position.avg_cost}")

    def get_position(self, ticker: str) -> Position | None:
        """Get current position for a ticker."""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("SELECT * FROM positions WHERE ticker = ?", (ticker,))
            row = cursor.fetchone()

            if row:
                return self._row_to_position(dict(row))
            return None

    def get_all_positions(self) -> list[Position]:
        """Get all current positions."""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("SELECT * FROM positions ORDER BY ticker")

            positions = []
            for row in cursor.fetchall():
                positions.append(self._row_to_position(dict(row)))

            return positions

    def delete_position(self, ticker: str) -> None:
        """Delete a position (when fully closed)."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM positions WHERE ticker = ?", (ticker,))
            logger.info(f"Deleted position for {ticker}")

    # ==================== Orders ====================

    def insert_order(self, order: Order) -> None:
        """Insert a new order."""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute(
                """
                INSERT INTO orders (
                    order_id, ibkr_order_id, ibkr_perm_id,
                    ticker, side, qty, order_type, limit_price, tif,
                    status, request_payload, response_payload,
                    signal_id, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    order.order_id,
                    order.ibkr_order_id,
                    order.ibkr_perm_id,
                    order.ticker,
                    order.side,
                    order.qty,
                    order.order_type,
                    order.limit_price,
                    order.tif,
                    order.status,
                    json.dumps(order.request_payload),
                    json.dumps(order.response_payload),
                    order.signal_id,
                    order.created_at.isoformat(),
                    order.updated_at.isoformat(),
                ),
            )

            logger.info(f"Inserted order {order.order_id} for {order.ticker}: {order.side} {order.qty}")

    def update_order_status(
        self,
        order_id: str,
        status: str,
        response_payload: dict | None = None,
        ibkr_order_id: int | None = None,
        ibkr_perm_id: int | None = None,
    ) -> None:
        """Update order status and response."""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            updates = ["status = ?", "updated_at = ?"]
            params: list[Any] = [status, datetime.utcnow().isoformat()]

            if response_payload is not None:
                updates.append("response_payload = ?")
                params.append(json.dumps(response_payload))

            if ibkr_order_id is not None:
                updates.append("ibkr_order_id = ?")
                params.append(ibkr_order_id)

            if ibkr_perm_id is not None:
                updates.append("ibkr_perm_id = ?")
                params.append(ibkr_perm_id)

            params.append(order_id)

            cursor.execute(
                f"UPDATE orders SET {', '.join(updates)} WHERE order_id = ?",
                params,
            )

            logger.info(f"Updated order {order_id} status to {status}")

    def get_order(self, order_id: str) -> Order | None:
        """Get order by ID."""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("SELECT * FROM orders WHERE order_id = ?", (order_id,))
            row = cursor.fetchone()

            if row:
                return self._row_to_order(dict(row))
            return None

    # ==================== Fills ====================

    def insert_fill(self, fill: Fill) -> None:
        """Insert a fill record."""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute(
                """
                INSERT INTO fills (
                    fill_id, order_id, ibkr_exec_id,
                    ticker, side, qty, price, commission, filled_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    fill.fill_id,
                    fill.order_id,
                    fill.ibkr_exec_id,
                    fill.ticker,
                    fill.side,
                    fill.qty,
                    fill.price,
                    fill.commission,
                    fill.filled_at.isoformat(),
                ),
            )

            logger.info(f"Inserted fill {fill.fill_id}: {fill.side} {fill.qty} {fill.ticker} @ {fill.price}")

    def get_fills_for_order(self, order_id: str) -> list[Fill]:
        """Get all fills for an order."""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute(
                "SELECT * FROM fills WHERE order_id = ? ORDER BY filled_at",
                (order_id,),
            )

            fills = []
            for row in cursor.fetchall():
                fills.append(self._row_to_fill(dict(row)))

            return fills

    # ==================== Helper methods ====================

    def _row_to_event(self, row: dict) -> CongressTradeEvent:
        """Convert database row to CongressTradeEvent."""
        from datetime import date as date_type

        return CongressTradeEvent(
            event_id=row["event_id"],
            source=row["source"],
            member_name=row["member_name"],
            member_id=row["member_id"],
            owner=row["owner"],
            ticker=row["ticker"],
            asset_type=row["asset_type"],
            transaction_type=row["transaction_type"],
            trade_date=date_type.fromisoformat(row["trade_date"]) if row["trade_date"] else None,
            disclosure_date=(
                date_type.fromisoformat(row["disclosure_date"]) if row["disclosure_date"] else None
            ),
            amount_low=row["amount_low"],
            amount_high=row["amount_high"],
            currency=row["currency"],
            raw=json.loads(row["raw"]) if row["raw"] else {},
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    def _row_to_signal(self, row: dict) -> TradeSignal:
        """Convert database row to TradeSignal."""
        return TradeSignal(
            signal_id=row["signal_id"],
            event_id=row["event_id"],
            ticker=row["ticker"],
            action=row["action"],
            strength=row["strength"],
            score=row["score"],
            reason=json.loads(row["reason"]) if row["reason"] else [],
            strategy_version=row["strategy_version"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    def _row_to_position(self, row: dict) -> Position:
        """Convert database row to Position."""
        return Position(
            ticker=row["ticker"],
            qty=row["qty"],
            avg_cost=row["avg_cost"],
            opened_at=datetime.fromisoformat(row["opened_at"]),
            last_updated_at=datetime.fromisoformat(row["last_updated_at"]),
            exit_rule=row["exit_rule"],
            max_hold_days=row["max_hold_days"],
            stop_loss_pct=row["stop_loss_pct"],
            take_profit_pct=row["take_profit_pct"],
        )

    def _row_to_order(self, row: dict) -> Order:
        """Convert database row to Order."""
        return Order(
            order_id=row["order_id"],
            ibkr_order_id=row["ibkr_order_id"],
            ibkr_perm_id=row["ibkr_perm_id"],
            ticker=row["ticker"],
            side=row["side"],
            qty=row["qty"],
            order_type=row["order_type"],
            limit_price=row["limit_price"],
            tif=row["tif"],
            status=row["status"],
            request_payload=json.loads(row["request_payload"]) if row["request_payload"] else {},
            response_payload=json.loads(row["response_payload"]) if row["response_payload"] else {},
            signal_id=row["signal_id"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    def _row_to_fill(self, row: dict) -> Fill:
        """Convert database row to Fill."""
        return Fill(
            fill_id=row["fill_id"],
            order_id=row["order_id"],
            ibkr_exec_id=row["ibkr_exec_id"],
            ticker=row["ticker"],
            side=row["side"],
            qty=row["qty"],
            price=row["price"],
            commission=row["commission"],
            filled_at=datetime.fromisoformat(row["filled_at"]),
        )


# Global database instance
db = Database()
