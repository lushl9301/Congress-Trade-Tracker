"""
Paper trading execution engine.

Filters signals, calculates position sizes, and executes paper trades
based on configurable signal strength criteria.
"""

from datetime import datetime
from typing import Dict, List

from app.config import config
from app.db import db
from app.logging import get_logger
from app.market_data import get_market_data_provider
from app.models import TradeSignal
from app.paper_account import get_paper_account
from app.portfolio import portfolio_manager

logger = get_logger(__name__)


class PaperTrader:
    """
    Execute paper trades based on signals.

    Features:
    - Configurable signal filtering (STRONG_BUY only OR STRONG + NORMAL)
    - Position sizing with risk controls
    - Trade execution with price validation
    - Signal tracking to prevent duplicates
    """

    def __init__(
        self,
        signal_filter_mode: str | None = None,
    ):
        """
        Initialize paper trader.

        Args:
            signal_filter_mode: Signal filter mode (strong_only, strong_and_normal)
                               Defaults to config.SIGNAL_FILTER_MODE
        """
        self.signal_filter_mode = signal_filter_mode or config.SIGNAL_FILTER_MODE
        self.account = get_paper_account()
        self.market_data = get_market_data_provider()
        self.portfolio_manager = portfolio_manager

        logger.info(f"PaperTrader initialized (filter_mode: {self.signal_filter_mode})")

    def get_tradeable_signals(self) -> List[TradeSignal]:
        """
        Get untraded signals matching the filter criteria.

        Returns:
            List of signals ready to trade
        """
        # Get all signals from database
        all_signals = db.get_all_signals()

        tradeable = []

        for sig in all_signals:
            # Skip if already traded
            if db.signal_already_traded(sig.signal_id):
                continue

            # Only trade BUY signals
            if sig.action != "BUY":
                continue

            # Filter by strength based on mode
            if self.signal_filter_mode == "strong_only":
                if sig.strength == "STRONG":
                    tradeable.append(sig)
            elif self.signal_filter_mode == "strong_and_normal":
                if sig.strength in ["STRONG", "NORMAL"]:
                    tradeable.append(sig)
            else:
                logger.warning(
                    f"Unknown signal_filter_mode: {self.signal_filter_mode}"
                )

        logger.info(
            f"Found {len(tradeable)} tradeable signals "
            f"(mode: {self.signal_filter_mode}, total: {len(all_signals)})"
        )

        return tradeable

    def execute_signal(self, signal: TradeSignal) -> Dict:
        """
        Execute a single signal as paper trade.

        Args:
            signal: TradeSignal to execute

        Returns:
            Dictionary with execution result
        """
        ticker = signal.ticker
        result = {
            "signal_id": signal.signal_id,
            "ticker": ticker,
            "strength": signal.strength,
            "score": signal.score,
            "executed": False,
            "reason": None,
            "shares": 0,
            "price": 0.0,
            "notional": 0.0,
        }

        # Get current price
        price = self.market_data.get_price(ticker)
        if not price:
            result["reason"] = "No price available"
            logger.warning(f"❌ {ticker}: No price available, skipping")
            return result

        result["price"] = price

        # Get NAV
        nav = self.account.get_nav(self.market_data)

        # Calculate position size
        shares, reasons = self.portfolio_manager.calculate_position_size(
            ticker=ticker,
            signal_strength=signal.strength,
            nav=nav,
            current_price=price,
        )

        if shares == 0:
            result["reason"] = "; ".join(reasons)
            logger.info(f"⏭️  {ticker}: Rejected - {result['reason']}")
            return result

        result["shares"] = shares
        result["notional"] = shares * price

        # Execute paper trade
        success = self.account.execute_trade(
            ticker=ticker,
            side="BUY",
            shares=shares,
            price=price,
            signal_id=signal.signal_id,
            commission=0.0,  # No commission in paper trading
        )

        if success:
            # Mark signal as traded
            db.mark_signal_traded(signal.signal_id)
            result["executed"] = True
            result["reason"] = f"Executed: {shares} shares @ ${price:.2f}"
            logger.info(
                f"✅ {ticker}: BUY {shares} @ ${price:.2f} "
                f"(${result['notional']:,.2f}, strength: {signal.strength})"
            )
        else:
            result["reason"] = "Trade execution failed"
            logger.error(f"❌ {ticker}: Execution failed")

        return result

    def run_trading_session(self) -> Dict:
        """
        Run a complete trading session.

        Process all tradeable signals and execute eligible trades.

        Returns:
            Dictionary with session statistics
        """
        logger.info("=" * 80)
        logger.info("PAPER TRADING SESSION START")
        logger.info(f"Filter mode: {self.signal_filter_mode}")
        logger.info(f"Account: {self.account.account_id}")
        logger.info("=" * 80)

        # Get tradeable signals
        signals = self.get_tradeable_signals()

        if not signals:
            logger.info("No tradeable signals found")
            return {
                "signals_evaluated": 0,
                "trades_executed": 0,
                "trades_skipped": 0,
                "total_notional": 0.0,
                "nav_before": self.account.get_nav(self.market_data),
                "nav_after": self.account.get_nav(self.market_data),
            }

        # Get NAV before trading
        nav_before = self.account.get_nav(self.market_data)

        executed_count = 0
        skipped_count = 0
        total_notional = 0.0
        execution_results = []

        logger.info(f"\n📊 Evaluating {len(signals)} signals...")

        for signal in signals:
            result = self.execute_signal(signal)
            execution_results.append(result)

            if result["executed"]:
                executed_count += 1
                total_notional += result["notional"]
            else:
                skipped_count += 1

        # Get NAV after trading
        nav_after = self.account.get_nav(self.market_data)

        # Get current cash and equity
        cash = self.account.get_cash()
        equity = self.account.get_equity(self.market_data)

        # Build session summary
        session_summary = {
            "signals_evaluated": len(signals),
            "trades_executed": executed_count,
            "trades_skipped": skipped_count,
            "total_notional": total_notional,
            "nav_before": nav_before,
            "nav_after": nav_after,
            "cash": cash,
            "equity": equity,
            "execution_results": execution_results,
            "timestamp": datetime.utcnow().isoformat(),
        }

        logger.info("\n" + "=" * 80)
        logger.info("PAPER TRADING SESSION COMPLETE")
        logger.info("=" * 80)
        logger.info(f"Signals evaluated: {len(signals)}")
        logger.info(f"Trades executed:   {executed_count}")
        logger.info(f"Trades skipped:    {skipped_count}")
        logger.info(f"Total deployed:    ${total_notional:,.2f}")
        logger.info(f"NAV before:        ${nav_before:,.2f}")
        logger.info(f"NAV after:         ${nav_after:,.2f}")
        logger.info(f"Current cash:      ${cash:,.2f}")
        logger.info(f"Current equity:    ${equity:,.2f}")
        logger.info("=" * 80)

        return session_summary


# Global instance
_paper_trader = None


def get_paper_trader(signal_filter_mode: str | None = None) -> PaperTrader:
    """
    Get paper trader instance.

    Args:
        signal_filter_mode: Override default filter mode

    Returns:
        PaperTrader instance
    """
    global _paper_trader
    if _paper_trader is None or (
        signal_filter_mode and _paper_trader.signal_filter_mode != signal_filter_mode
    ):
        _paper_trader = PaperTrader(signal_filter_mode=signal_filter_mode)
    return _paper_trader
