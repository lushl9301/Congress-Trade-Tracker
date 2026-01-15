"""
Portfolio management module for Congress Trade Tracker.
Handles position sizing, risk controls, and exit rules.
"""
from datetime import datetime
from typing import Any

from app.config import config
from app.db import db
from app.logging import get_logger
from app.models import Fill, Position

logger = get_logger(__name__)


class PortfolioManager:
    """
    Manages portfolio positions, sizing, and risk controls.
    """

    def __init__(self):
        """Initialize portfolio manager."""
        self.max_ticker_pct = config.MAX_TICKER_PCT
        self.max_daily_exposure = config.MAX_DAILY_EXPOSURE
        self.target_pct_strong = config.TARGET_PCT_STRONG
        self.target_pct_normal = config.TARGET_PCT_NORMAL
        self.max_hold_days = config.MAX_HOLD_DAYS
        self.stop_loss_pct = config.STOP_LOSS_PCT
        self.take_profit_pct = config.TAKE_PROFIT_PCT

    def calculate_position_size(
        self, ticker: str, signal_strength: str, nav: float, current_price: float
    ) -> tuple[float, list[str]]:
        """
        Calculate position size in shares based on signal strength and risk controls.

        Args:
            ticker: Stock ticker
            signal_strength: "STRONG" or "NORMAL"
            nav: Net Asset Value (total portfolio value)
            current_price: Current stock price

        Returns:
            Tuple of (shares_to_buy, rejection_reasons)
            If shares_to_buy is 0, rejection_reasons will contain why
        """
        reasons: list[str] = []

        # Determine target allocation
        if signal_strength == "STRONG":
            target_pct = self.target_pct_strong
        elif signal_strength == "NORMAL":
            target_pct = self.target_pct_normal
        else:
            return 0, ["Signal strength not STRONG or NORMAL"]

        # Calculate target notional
        target_notional = nav * target_pct

        # Check existing position
        existing_position = db.get_position(ticker)
        existing_exposure_pct = 0.0

        if existing_position:
            existing_notional = existing_position.qty * current_price
            existing_exposure_pct = existing_notional / nav

            # Check if we can add to position
            if existing_exposure_pct >= self.max_ticker_pct:
                return 0, [f"Already at max ticker exposure: {existing_exposure_pct:.2%}"]

            # Only allow adding if signal is STRONG and last add was >7 days ago
            if signal_strength != "STRONG":
                return 0, ["Cannot add to position with NORMAL signal"]

            days_since_open = (datetime.utcnow() - existing_position.opened_at).days
            if days_since_open < 7:
                return 0, [f"Last position opened {days_since_open} days ago (min 7 days)"]

            # Reduce target to respect max exposure
            max_additional_notional = (nav * self.max_ticker_pct) - existing_notional
            target_notional = min(target_notional, max_additional_notional)

            reasons.append(f"Adding to existing position (current: {existing_exposure_pct:.2%})")

        # Calculate shares
        shares = int(target_notional / current_price)

        if shares <= 0:
            return 0, ["Calculated position size is 0 shares"]

        # Final validation
        final_notional = shares * current_price
        final_exposure_pct = final_notional / nav

        if existing_position:
            final_exposure_pct += existing_exposure_pct

        if final_exposure_pct > self.max_ticker_pct:
            return 0, [f"Would exceed max ticker exposure: {final_exposure_pct:.2%}"]

        reasons.append(
            f"Sized for {signal_strength}: {shares} shares = ${final_notional:,.2f} ({target_pct:.2%} NAV)"
        )

        return shares, reasons

    def check_daily_exposure_limit(self, nav: float, proposed_notional: float) -> tuple[bool, str]:
        """
        Check if proposed trade would exceed daily exposure limit.

        For MVP, this is a simple check. Could be enhanced to track intraday additions.

        Args:
            nav: Net Asset Value
            proposed_notional: Proposed trade notional value

        Returns:
            Tuple of (allowed, reason)
        """
        exposure_pct = proposed_notional / nav

        if exposure_pct > self.max_daily_exposure:
            return False, f"Would exceed daily exposure limit: {exposure_pct:.2%} > {self.max_daily_exposure:.2%}"

        return True, ""

    def open_position(self, ticker: str, qty: float, avg_cost: float) -> Position:
        """
        Open a new position or add to existing.

        Args:
            ticker: Stock ticker
            qty: Quantity to add
            avg_cost: Average cost per share

        Returns:
            Updated Position
        """
        existing = db.get_position(ticker)

        if existing:
            # Average down/up
            total_qty = existing.qty + qty
            total_cost = (existing.qty * existing.avg_cost) + (qty * avg_cost)
            new_avg_cost = total_cost / total_qty

            position = Position(
                ticker=ticker,
                qty=total_qty,
                avg_cost=new_avg_cost,
                opened_at=existing.opened_at,  # Keep original open time
                last_updated_at=datetime.utcnow(),
                exit_rule=existing.exit_rule,
                max_hold_days=self.max_hold_days,
                stop_loss_pct=self.stop_loss_pct,
                take_profit_pct=self.take_profit_pct,
            )

            logger.info(
                f"Adding to position {ticker}: {qty} @ {avg_cost}, "
                f"new total: {total_qty} @ {new_avg_cost:.2f}"
            )

        else:
            # New position
            position = Position(
                ticker=ticker,
                qty=qty,
                avg_cost=avg_cost,
                opened_at=datetime.utcnow(),
                last_updated_at=datetime.utcnow(),
                exit_rule="HOLD_30D",
                max_hold_days=self.max_hold_days,
                stop_loss_pct=self.stop_loss_pct,
                take_profit_pct=self.take_profit_pct,
            )

            logger.info(f"Opened new position {ticker}: {qty} @ {avg_cost}")

        db.upsert_position(position)
        return position

    def close_position(self, ticker: str, qty: float) -> None:
        """
        Close or reduce a position.

        Args:
            ticker: Stock ticker
            qty: Quantity to close
        """
        position = db.get_position(ticker)

        if not position:
            logger.warning(f"Attempted to close non-existent position: {ticker}")
            return

        if qty >= position.qty:
            # Full close
            db.delete_position(ticker)
            logger.info(f"Closed position {ticker}: {position.qty} shares")
        else:
            # Partial close
            new_qty = position.qty - qty
            position.qty = new_qty
            position.last_updated_at = datetime.utcnow()
            db.upsert_position(position)
            logger.info(f"Reduced position {ticker}: -{qty} shares, remaining: {new_qty}")

    def process_fill(self, fill: Fill) -> None:
        """
        Process a fill and update positions.

        Args:
            fill: Fill record
        """
        if fill.side == "BUY":
            self.open_position(fill.ticker, fill.qty, fill.price)
        elif fill.side == "SELL":
            self.close_position(fill.ticker, fill.qty)

        logger.info(f"Processed fill: {fill.side} {fill.qty} {fill.ticker} @ {fill.price}")

    def check_exit_conditions(
        self, position: Position, current_price: float
    ) -> tuple[bool, str | None]:
        """
        Check if a position should be exited based on time or price rules.

        Args:
            position: Position to check
            current_price: Current market price

        Returns:
            Tuple of (should_exit, reason)
        """
        # Check time-based exit
        if position.should_exit_time():
            return True, f"Max hold period reached: {position.holding_days} days"

        # Check price-based exit
        should_exit, reason = position.should_exit_price(current_price)
        if should_exit:
            return True, reason

        return False, None

    def get_portfolio_summary(self, prices: dict[str, float] | None = None) -> dict[str, Any]:
        """
        Get portfolio summary with current positions and exposure.

        Args:
            prices: Optional dict of ticker -> current_price

        Returns:
            Summary dictionary
        """
        positions = db.get_all_positions()

        if not positions:
            return {
                "num_positions": 0,
                "total_notional": 0.0,
                "positions": [],
            }

        positions_detail = []
        total_notional = 0.0

        for pos in positions:
            current_price = prices.get(pos.ticker) if prices else pos.avg_cost
            notional = pos.qty * current_price
            pnl = (current_price - pos.avg_cost) * pos.qty
            pnl_pct = (current_price - pos.avg_cost) / pos.avg_cost

            positions_detail.append(
                {
                    "ticker": pos.ticker,
                    "qty": pos.qty,
                    "avg_cost": pos.avg_cost,
                    "current_price": current_price,
                    "notional": notional,
                    "pnl": pnl,
                    "pnl_pct": pnl_pct,
                    "holding_days": pos.holding_days,
                    "max_hold_days": pos.max_hold_days,
                }
            )

            total_notional += notional

        return {
            "num_positions": len(positions),
            "total_notional": total_notional,
            "positions": positions_detail,
        }


# Global portfolio manager instance
portfolio_manager = PortfolioManager()
