"""Portfolio management and position tracking."""

from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy.orm import Session

from tracker.config import settings
from tracker.database import PositionDB, SessionLocal, SignalDB
from tracker.logger import logger
from tracker.models import Position, PositionStatus, Signal, SignalAction, SignalConfidence


class PortfolioManager:
    """Manage portfolio positions and risk limits."""

    def __init__(self):
        self.settings = settings

    def get_nav(self) -> float:
        """Get current net asset value (NAV) of portfolio.

        TODO: Integrate with IBKR to get real account value.
        For now, return a placeholder.
        """
        # Placeholder - will be replaced with real IBKR integration
        return 100_000.0

    def get_position(self, ticker: str, db: Session) -> Position | None:
        """Get current position for a ticker.

        Args:
            ticker: Stock ticker
            db: Database session

        Returns:
            Position if exists and open, None otherwise
        """
        db_position = (
            db.query(PositionDB)
            .filter(PositionDB.ticker == ticker, PositionDB.status == PositionStatus.OPEN.value)
            .first()
        )

        if not db_position:
            return None

        return Position(
            id=UUID(db_position.id),
            ticker=db_position.ticker,
            quantity=db_position.quantity,
            avg_cost=db_position.avg_cost,
            current_price=db_position.current_price,
            unrealized_pnl=db_position.unrealized_pnl,
            opened_at=db_position.opened_at,
            opened_by_signals=[UUID(sid) for sid in db_position.opened_by_signals],
            exit_strategy=db_position.exit_strategy,
            status=PositionStatus(db_position.status),
        )

    def get_all_positions(self, db: Session) -> list[Position]:
        """Get all open positions."""
        db_positions = db.query(PositionDB).filter(PositionDB.status == PositionStatus.OPEN.value).all()

        positions = []
        for db_pos in db_positions:
            positions.append(
                Position(
                    id=UUID(db_pos.id),
                    ticker=db_pos.ticker,
                    quantity=db_pos.quantity,
                    avg_cost=db_pos.avg_cost,
                    current_price=db_pos.current_price,
                    unrealized_pnl=db_pos.unrealized_pnl,
                    opened_at=db_pos.opened_at,
                    opened_by_signals=[UUID(sid) for sid in db_pos.opened_by_signals],
                    exit_strategy=db_pos.exit_strategy,
                    status=PositionStatus(db_pos.status),
                )
            )

        return positions

    def get_ticker_exposure(self, ticker: str, db: Session) -> float:
        """Get current dollar exposure to a ticker.

        Returns:
            Dollar value of position (quantity * current_price)
        """
        position = self.get_position(ticker, db)
        if not position or not position.current_price:
            return 0.0

        return position.quantity * position.current_price

    def calculate_position_size(
        self, signal: Signal, current_price: float, db: Session
    ) -> float | None:
        """Calculate position size in dollars for a signal.

        Args:
            signal: Trading signal
            current_price: Current stock price
            db: Database session

        Returns:
            Dollar amount to invest, or None if shouldn't trade
        """
        if signal.action not in [SignalAction.BUY]:
            return None

        nav = self.get_nav()

        # Determine target percentage based on confidence
        if signal.confidence == SignalConfidence.HIGH:
            target_pct = 0.04  # 4%
        elif signal.confidence == SignalConfidence.MEDIUM:
            target_pct = 0.02  # 2%
        else:
            return None  # Don't trade WATCH/IGNORE

        target_notional = nav * target_pct

        # Check limits
        current_exposure = self.get_ticker_exposure(signal.ticker, db)
        max_per_ticker = nav * self.settings.max_position_pct

        if current_exposure >= max_per_ticker:
            logger.warning(
                f"Already at max exposure for {signal.ticker}",
                current=current_exposure,
                max=max_per_ticker,
            )
            return None

        available = max_per_ticker - current_exposure
        position_size = min(target_notional, available)

        # Check minimum position size
        if position_size < self.settings.min_position_size:
            logger.info(
                f"Position size too small for {signal.ticker}",
                size=position_size,
                min=self.settings.min_position_size,
            )
            return None

        # Check max positions
        num_positions = len(self.get_all_positions(db))
        if num_positions >= self.settings.max_positions:
            logger.warning(
                f"Already at max number of positions",
                current=num_positions,
                max=self.settings.max_positions,
            )
            return None

        return position_size

    def check_exit_conditions(self, db: Session) -> list[tuple[Position, str]]:
        """Check all positions for exit conditions.

        Returns:
            List of (position, exit_reason) tuples for positions that should exit
        """
        positions = self.get_all_positions(db)
        exits = []

        for position in positions:
            # Update current price (placeholder - will integrate with real price data)
            if position.current_price is None:
                logger.warning(f"No current price for {position.ticker}, skipping exit check")
                continue

            # Check time-based exit
            days_held = (datetime.utcnow() - position.opened_at).days
            if days_held >= self.settings.max_hold_days:
                exits.append((position, f"MAX_HOLD_DAYS_{days_held}"))
                continue

            # Check profit target
            return_pct = position.calculate_return_pct()
            if return_pct and return_pct >= self.settings.profit_target_pct:
                exits.append((position, f"PROFIT_TARGET_{return_pct:.2%}"))
                continue

            # Check stop loss
            if return_pct and return_pct <= -self.settings.stop_loss_pct:
                exits.append((position, f"STOP_LOSS_{return_pct:.2%}"))
                continue

            # Check for new SELL disclosures
            # Look for recent SELL signals for this ticker
            recent_sell_signals = (
                db.query(SignalDB)
                .filter(
                    SignalDB.ticker == position.ticker,
                    SignalDB.action == SignalAction.SELL.value,
                    SignalDB.created_at >= datetime.utcnow() - timedelta(days=7),
                )
                .count()
            )

            if recent_sell_signals >= 2:
                exits.append((position, f"CLUSTER_SELL_{recent_sell_signals}_SIGNALS"))
                continue

        if exits:
            logger.info(f"Found {len(exits)} positions to exit")

        return exits

    def create_position(
        self, ticker: str, quantity: float, avg_cost: float, signal_id: UUID, db: Session
    ) -> Position:
        """Create a new position.

        Args:
            ticker: Stock ticker
            quantity: Number of shares
            avg_cost: Average cost per share
            signal_id: Signal that triggered this position
            db: Database session

        Returns:
            Created position
        """
        position = Position(
            ticker=ticker,
            quantity=quantity,
            avg_cost=avg_cost,
            opened_by_signals=[signal_id],
            exit_strategy={
                "max_hold_days": self.settings.max_hold_days,
                "profit_target_pct": self.settings.profit_target_pct,
                "stop_loss_pct": self.settings.stop_loss_pct,
            },
            status=PositionStatus.OPEN,
        )

        db_position = PositionDB(
            id=str(position.id),
            ticker=position.ticker,
            quantity=position.quantity,
            avg_cost=position.avg_cost,
            opened_by_signals=[str(sid) for sid in position.opened_by_signals],
            exit_strategy=position.exit_strategy,
            status=position.status.value,
        )

        db.add(db_position)
        db.commit()

        logger.info(
            f"Created position",
            ticker=ticker,
            quantity=quantity,
            avg_cost=avg_cost,
            signal_id=str(signal_id),
        )

        return position

    def update_position_price(self, ticker: str, price: float, db: Session) -> None:
        """Update position with current price and recalculate P&L."""
        db_position = (
            db.query(PositionDB)
            .filter(PositionDB.ticker == ticker, PositionDB.status == PositionStatus.OPEN.value)
            .first()
        )

        if not db_position:
            return

        db_position.current_price = price
        db_position.unrealized_pnl = (price - db_position.avg_cost) * db_position.quantity

        db.commit()

    def close_position(self, ticker: str, reason: str, db: Session) -> None:
        """Close a position.

        Args:
            ticker: Stock ticker
            reason: Reason for closing
            db: Database session
        """
        db_position = (
            db.query(PositionDB)
            .filter(PositionDB.ticker == ticker, PositionDB.status == PositionStatus.OPEN.value)
            .first()
        )

        if not db_position:
            logger.warning(f"Cannot close position {ticker} - not found")
            return

        db_position.status = PositionStatus.CLOSED.value
        db.commit()

        logger.info(f"Closed position {ticker}", reason=reason)
