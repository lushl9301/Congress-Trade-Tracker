"""
Paper trading account manager.

Manages virtual cash, equity, positions, and trade execution for paper trading.
No real money involved - purely for strategy validation and performance tracking.
"""

from datetime import datetime
from typing import Dict, List, Optional

from app.config import config
from app.db import db
from app.logging import get_logger
from app.models import Position

logger = get_logger(__name__)


class PaperAccount:
    """
    Manages paper trading account state.

    Features:
    - Virtual cash tracking
    - Equity calculation with live prices
    - Trade execution (buy/sell with virtual funds)
    - Position management
    - Performance metrics
    """

    def __init__(self, account_id: str = "default", initial_cash: Optional[float] = None):
        """
        Initialize paper account.

        Args:
            account_id: Account identifier
            initial_cash: Starting cash (default from config)
        """
        self.account_id = account_id
        self.initial_cash = initial_cash or config.PAPER_INITIAL_CASH

        # Load or create account
        self._load_or_create()

    def _load_or_create(self):
        """Load existing account or create new one."""
        account = db.get_paper_account(self.account_id)

        if account is None:
            # Create new paper account
            db.create_paper_account(
                account_id=self.account_id, initial_cash=self.initial_cash
            )
            logger.info(
                f"Created paper account '{self.account_id}' with ${self.initial_cash:,.2f}"
            )
        else:
            logger.info(
                f"Loaded paper account '{self.account_id}' "
                f"(cash: ${account['current_cash']:,.2f})"
            )

    def get_cash(self) -> float:
        """Get available cash."""
        account = db.get_paper_account(self.account_id)
        if account is None:
            logger.error(f"Account {self.account_id} not found!")
            return 0.0
        return account["current_cash"]

    def get_equity(self, market_data) -> float:
        """
        Calculate current equity (position values).

        Args:
            market_data: MarketDataProvider instance

        Returns:
            Total equity value
        """
        positions = db.get_all_positions(account_type="paper")
        equity = 0.0

        for pos in positions:
            price = market_data.get_price(pos.ticker)
            if price:
                equity += pos.qty * price
            else:
                logger.warning(
                    f"No price for {pos.ticker}, using avg_cost for equity calc"
                )
                equity += pos.qty * pos.avg_cost

        return equity

    def get_nav(self, market_data) -> float:
        """
        Get Net Asset Value (total portfolio value).

        Args:
            market_data: MarketDataProvider instance

        Returns:
            Cash + equity
        """
        cash = self.get_cash()
        equity = self.get_equity(market_data)
        return cash + equity

    def execute_trade(
        self,
        ticker: str,
        side: str,  # BUY or SELL
        shares: float,
        price: float,
        signal_id: Optional[str] = None,
        commission: float = 0.0,
    ) -> bool:
        """
        Execute a paper trade.

        Args:
            ticker: Stock symbol
            side: BUY or SELL
            shares: Number of shares
            price: Execution price
            signal_id: Related signal ID (optional)
            commission: Trading commission (default $0 for paper)

        Returns:
            True if trade executed successfully
        """
        notional = shares * price

        if side == "BUY":
            cost = notional + commission
            cash = self.get_cash()

            if cash < cost:
                logger.error(
                    f"Insufficient cash for BUY: need ${cost:,.2f}, have ${cash:,.2f}"
                )
                return False

            # Deduct cash
            db.update_paper_account_cash(self.account_id, -cost)

            # Update or create position
            self._update_position_buy(ticker, shares, price)

            logger.info(
                f"✅ Paper BUY: {shares} {ticker} @ ${price:.2f} = ${notional:,.2f}"
            )

        elif side == "SELL":
            # Check position
            position = db.get_position(ticker, account_type="paper")
            if not position or position.qty < shares:
                have_qty = position.qty if position else 0
                logger.error(
                    f"Insufficient shares for SELL: need {shares}, have {have_qty}"
                )
                return False

            # Add cash (proceeds)
            proceeds = notional - commission
            db.update_paper_account_cash(self.account_id, proceeds)

            # Reduce or close position
            self._update_position_sell(ticker, shares, price)

            logger.info(
                f"✅ Paper SELL: {shares} {ticker} @ ${price:.2f} = ${notional:,.2f}"
            )

        else:
            logger.error(f"Invalid side: {side} (must be BUY or SELL)")
            return False

        # Record trade
        trade_id = f"PT-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}-{ticker}"
        db.insert_paper_trade(
            trade_id=trade_id,
            ticker=ticker,
            side=side,
            shares=shares,
            price=price,
            notional=notional,
            signal_id=signal_id,
            account_id=self.account_id,
            commission=commission,
        )

        return True

    def _update_position_buy(self, ticker: str, shares: float, price: float):
        """Update position after buying shares."""
        position = db.get_position(ticker, account_type="paper")

        if position:
            # Add to existing position (average cost)
            new_qty = position.qty + shares
            new_avg_cost = (
                (position.qty * position.avg_cost) + (shares * price)
            ) / new_qty

            position.qty = new_qty
            position.avg_cost = new_avg_cost
            position.last_updated_at = datetime.utcnow()

            db.upsert_position(position, account_type="paper")
            logger.debug(
                f"Updated position {ticker}: {new_qty} @ ${new_avg_cost:.2f}"
            )
        else:
            # Create new position
            new_position = Position(
                ticker=ticker,
                qty=shares,
                avg_cost=price,
                opened_at=datetime.utcnow(),
                last_updated_at=datetime.utcnow(),
                exit_rule="HOLD_30D",
                max_hold_days=config.MAX_HOLD_DAYS,
                stop_loss_pct=config.STOP_LOSS_PCT,
                take_profit_pct=config.TAKE_PROFIT_PCT,
            )
            db.upsert_position(new_position, account_type="paper")
            logger.debug(f"Created position {ticker}: {shares} @ ${price:.2f}")

    def _update_position_sell(self, ticker: str, shares: float, price: float):
        """Update position after selling shares."""
        position = db.get_position(ticker, account_type="paper")

        if not position:
            logger.error(f"Cannot sell {ticker}: no position found")
            return

        new_qty = position.qty - shares

        if new_qty <= 0:
            # Close position completely
            # In a real system, we'd move this to a closed_positions table
            # For now, we'll delete it (trade history preserved in paper_trades)
            with db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "DELETE FROM positions WHERE ticker = ? AND account_type = ?",
                    (ticker, "paper"),
                )
            logger.debug(f"Closed position {ticker}")
        else:
            # Reduce position
            position.qty = new_qty
            position.last_updated_at = datetime.utcnow()
            db.upsert_position(position, account_type="paper")
            logger.debug(
                f"Reduced position {ticker}: {new_qty} @ ${position.avg_cost:.2f}"
            )

    def get_performance(self, market_data) -> Dict:
        """
        Calculate account performance metrics.

        Args:
            market_data: MarketDataProvider instance

        Returns:
            Dictionary with performance stats
        """
        account = db.get_paper_account(self.account_id)
        if not account:
            return {}

        cash = account["current_cash"]
        equity = self.get_equity(market_data)
        nav = cash + equity

        total_return = nav - account["initial_cash"]
        total_return_pct = (total_return / account["initial_cash"]) * 100

        # Get trades
        trades = db.get_paper_trades(self.account_id)

        # Get positions
        positions = db.get_all_positions(account_type="paper")

        # Calculate days active
        created_at = datetime.fromisoformat(account["created_at"])
        days_active = (datetime.utcnow() - created_at).days
        if days_active == 0:
            days_active = 1  # Avoid division by zero

        # Calculate position details
        position_details = []
        for pos in positions:
            price = market_data.get_price(pos.ticker)
            if price:
                market_value = pos.qty * price
                cost_basis = pos.qty * pos.avg_cost
                pnl = market_value - cost_basis
                pnl_pct = (pnl / cost_basis) * 100 if cost_basis > 0 else 0

                position_details.append(
                    {
                        "ticker": pos.ticker,
                        "qty": pos.qty,
                        "avg_cost": pos.avg_cost,
                        "current_price": price,
                        "market_value": market_value,
                        "cost_basis": cost_basis,
                        "pnl": pnl,
                        "pnl_pct": pnl_pct,
                        "days_held": (datetime.utcnow() - pos.opened_at).days,
                    }
                )

        return {
            "account_id": self.account_id,
            "initial_cash": account["initial_cash"],
            "current_cash": cash,
            "current_equity": equity,
            "nav": nav,
            "total_return": total_return,
            "total_return_pct": total_return_pct,
            "num_trades": len(trades),
            "num_positions": len(positions),
            "created_at": account["created_at"],
            "days_active": days_active,
            "daily_return_pct": total_return_pct / days_active,
            "position_details": position_details,
        }

    def get_position_summary(self, market_data) -> List[Dict]:
        """
        Get summary of all positions with current P/L.

        Args:
            market_data: MarketDataProvider instance

        Returns:
            List of position summaries
        """
        positions = db.get_all_positions(account_type="paper")
        summaries = []

        for pos in positions:
            price = market_data.get_price(pos.ticker)
            if price:
                market_value = pos.qty * price
                cost_basis = pos.qty * pos.avg_cost
                pnl = market_value - cost_basis
                pnl_pct = (pnl / cost_basis) * 100 if cost_basis > 0 else 0

                summaries.append(
                    {
                        "ticker": pos.ticker,
                        "qty": pos.qty,
                        "avg_cost": pos.avg_cost,
                        "current_price": price,
                        "market_value": market_value,
                        "pnl": pnl,
                        "pnl_pct": pnl_pct,
                        "days_held": (datetime.utcnow() - pos.opened_at).days,
                    }
                )

        return summaries


# Global instance
_paper_account = None


def get_paper_account() -> PaperAccount:
    """
    Get singleton paper account instance.

    Returns:
        PaperAccount instance
    """
    global _paper_account
    if _paper_account is None:
        _paper_account = PaperAccount()
    return _paper_account
