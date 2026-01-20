"""
Daily reporting system for paper trading.

Generates comprehensive reports with:
- Performance summary
- Current portfolio with live P/L
- Trading history
- Actionable suggestions
"""

from datetime import datetime, timedelta
from typing import Dict, List

from app.config import config
from app.db import db
from app.logging import get_logger
from app.market_data import get_market_data_provider
from app.models import Position
from app.paper_account import get_paper_account
from app.rejection_stats import get_rejection_summary_from_db

logger = get_logger(__name__)


class DailyReporter:
    """
    Generate daily performance reports.

    Features:
    - Performance metrics (return %, P/L)
    - Position analysis with live prices
    - Trading history
    - Exit suggestions (stop loss, take profit, time-based)
    - New signal opportunities
    - Risk metrics
    """

    def __init__(self):
        """Initialize daily reporter."""
        self.account = get_paper_account()
        self.market_data = get_market_data_provider()

    def generate_report(self, include_suggestions: bool = True) -> str:
        """
        Generate comprehensive daily report.

        Args:
            include_suggestions: Include actionable suggestions

        Returns:
            Formatted report string
        """
        report = []
        report.append("=" * 80)
        report.append("CONGRESS TRADE TRACKER - DAILY REPORT")
        report.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report.append("=" * 80)

        # Performance Summary
        report.append("\n" + self._section_performance())

        # Signal Generation Stats
        report.append("\n" + self._section_signal_stats())

        # Current Portfolio
        report.append("\n" + self._section_portfolio())

        # Trading History
        report.append("\n" + self._section_history())

        # Suggestions
        if include_suggestions:
            report.append("\n" + self._section_suggestions())

        # Risk Metrics
        report.append("\n" + self._section_risk_metrics())

        report.append("\n" + "=" * 80)
        report.append("END OF REPORT")
        report.append("=" * 80)

        return "\n".join(report)

    def _section_performance(self) -> str:
        """Generate performance summary section."""
        lines = []
        lines.append("📊 PERFORMANCE SUMMARY")
        lines.append("-" * 80)

        perf = self.account.get_performance(self.market_data)

        lines.append(f"  Account:          {perf['account_id']}")
        lines.append(f"  Days Active:      {perf['days_active']} days")
        lines.append("")
        lines.append(f"  Initial Capital:  ${perf['initial_cash']:>12,.2f}")
        lines.append(f"  Current Cash:     ${perf['current_cash']:>12,.2f}")
        lines.append(f"  Current Equity:   ${perf['current_equity']:>12,.2f}")
        lines.append(f"  Total NAV:        ${perf['nav']:>12,.2f}")
        lines.append("")
        lines.append(
            f"  Total Return:     ${perf['total_return']:>12,.2f} "
            f"({perf['total_return_pct']:+.2f}%)"
        )

        if perf['days_active'] > 0:
            lines.append(f"  Daily Avg Return: {perf['daily_return_pct']:>12,.2f}%")

        lines.append("")
        lines.append(f"  Total Trades:     {perf['num_trades']:>12,d}")
        lines.append(f"  Open Positions:   {perf['num_positions']:>12,d}")

        return "\n".join(lines)

    def _section_signal_stats(self) -> str:
        """Generate signal generation statistics section."""
        lines = []
        lines.append("📊 SIGNAL GENERATION STATS (Last 7 days)")
        lines.append("-" * 80)

        stats = get_rejection_summary_from_db(days=7)

        lines.append(f"  Total events ingested:     {stats['total_events']:>6,d}")
        lines.append(f"  Total signals generated:   {stats['total_signals']:>6,d}")
        lines.append("")
        lines.append(f"  Rejected (IGNORE):         {stats['rejected_ignore']:>6,d} ({stats['rejection_rate']:.1f}%)")
        lines.append(f"  Passed filters:            {stats['passed_filters']:>6,d}")
        lines.append("")
        lines.append(f"  Generated BUY signals:     {stats['buy_signals']:>6,d}")
        lines.append(f"  Generated SELL signals:    {stats['sell_signals']:>6,d}")
        lines.append(f"  Generated WATCH signals:   {stats['watch']:>6,d}")

        # Add context if high rejection rate
        if stats['rejection_rate'] > 80 and stats['total_signals'] > 10:
            lines.append("")
            lines.append(f"  ⚠️  High rejection rate - most events filtered out")
            lines.append(f"      Common reasons: disclosure delays, low amounts, or unsuitable tickers")

        return "\n".join(lines)

    def _section_portfolio(self) -> str:
        """Generate current portfolio section."""
        lines = []
        lines.append("💼 CURRENT PORTFOLIO")
        lines.append("-" * 80)

        positions = db.get_all_positions(account_type="paper")

        if not positions:
            lines.append("  No open positions")
            return "\n".join(lines)

        # Header
        lines.append(
            f"{'Ticker':<8} {'Shares':>8} {'Avg Cost':>10} {'Current':>10} "
            f"{'Value':>12} {'P/L $':>12} {'P/L %':>8} {'Days':>6}"
        )
        lines.append("-" * 80)

        total_value = 0.0
        total_cost = 0.0

        for pos in positions:
            price = self.market_data.get_price(pos.ticker)
            if not price:
                price = pos.avg_cost  # Fallback

            market_value = pos.qty * price
            cost_basis = pos.qty * pos.avg_cost
            pnl = market_value - cost_basis
            pnl_pct = (pnl / cost_basis * 100) if cost_basis > 0 else 0
            days_held = (datetime.utcnow() - pos.opened_at).days

            total_value += market_value
            total_cost += cost_basis

            # Format P/L with color indicators
            pnl_str = f"${pnl:>11,.2f}"
            pnl_pct_str = f"{pnl_pct:>7.2f}%"

            lines.append(
                f"{pos.ticker:<8} {pos.qty:>8.2f} ${pos.avg_cost:>9.2f} "
                f"${price:>9.2f} ${market_value:>11,.2f} {pnl_str} "
                f"{pnl_pct_str} {days_held:>6d}"
            )

        # Total row
        total_pnl = total_value - total_cost
        total_pnl_pct = (total_pnl / total_cost * 100) if total_cost > 0 else 0

        lines.append("-" * 80)
        lines.append(
            f"{'TOTAL':<8} {'':<8} {'':<10} {'':<10} "
            f"${total_value:>11,.2f} ${total_pnl:>11,.2f} {total_pnl_pct:>7.2f}% {'':<6}"
        )

        return "\n".join(lines)

    def _section_history(self, days: int = 7) -> str:
        """Generate recent trading history section."""
        lines = []
        lines.append(f"📜 RECENT TRADES (Last {days} days)")
        lines.append("-" * 80)

        all_trades = db.get_paper_trades(self.account.account_id)

        # Filter trades from last N days
        cutoff = datetime.utcnow() - timedelta(days=days)
        recent_trades = [
            t
            for t in all_trades
            if datetime.fromisoformat(t["executed_at"]) > cutoff
        ]

        if not recent_trades:
            lines.append(f"  No trades in last {days} days")
            return "\n".join(lines)

        # Header
        lines.append(
            f"{'Date':<12} {'Time':<8} {'Ticker':<8} {'Side':<6} "
            f"{'Shares':>8} {'Price':>10} {'Total':>12}"
        )
        lines.append("-" * 80)

        total_bought = 0.0
        total_sold = 0.0

        for trade in reversed(recent_trades[-20:]):  # Last 20 trades max
            executed_at = datetime.fromisoformat(trade["executed_at"])
            date_str = executed_at.strftime("%Y-%m-%d")
            time_str = executed_at.strftime("%H:%M:%S")

            lines.append(
                f"{date_str:<12} {time_str:<8} {trade['ticker']:<8} "
                f"{trade['side']:<6} {trade['shares']:>8.2f} "
                f"${trade['price']:>9.2f} ${trade['notional']:>11,.2f}"
            )

            if trade["side"] == "BUY":
                total_bought += trade["notional"]
            else:
                total_sold += trade["notional"]

        lines.append("-" * 80)
        lines.append(f"Total Bought: ${total_bought:,.2f}")
        lines.append(f"Total Sold:   ${total_sold:,.2f}")
        lines.append(f"Net:          ${total_bought - total_sold:,.2f}")

        return "\n".join(lines)

    def _section_suggestions(self) -> str:
        """Generate actionable suggestions section."""
        lines = []
        lines.append("💡 SUGGESTIONS")
        lines.append("-" * 80)

        suggestions = []

        # Check positions for exit triggers
        positions = db.get_all_positions(account_type="paper")
        for pos in positions:
            price = self.market_data.get_price(pos.ticker)
            if not price:
                continue

            # Calculate returns
            cost = pos.avg_cost
            return_pct = ((price - cost) / cost) * 100

            # Check exit triggers
            if return_pct <= pos.stop_loss_pct * 100:
                suggestions.append(
                    f"🛑 SELL {pos.ticker}: Hit stop loss "
                    f"({return_pct:.1f}% ≤ {pos.stop_loss_pct*100:.0f}%)"
                )

            if return_pct >= pos.take_profit_pct * 100:
                suggestions.append(
                    f"🎯 SELL {pos.ticker}: Hit take profit target "
                    f"({return_pct:.1f}% ≥ {pos.take_profit_pct*100:.0f}%)"
                )

            # Check time-based exit
            days_held = (datetime.utcnow() - pos.opened_at).days
            if days_held >= pos.max_hold_days:
                suggestions.append(
                    f"⏰ SELL {pos.ticker}: Max hold period reached "
                    f"({days_held} ≥ {pos.max_hold_days} days)"
                )
            elif days_held >= pos.max_hold_days * 0.8:
                remaining = pos.max_hold_days - days_held
                suggestions.append(
                    f"⏳ WATCH {pos.ticker}: Approaching max hold "
                    f"({remaining} days remaining)"
                )

        # Check for new trading opportunities
        signals = db.get_all_signals()
        untraded_strong = [
            s
            for s in signals
            if s.action == "BUY"
            and s.strength == "STRONG"
            and not db.signal_already_traded(s.signal_id)
        ]

        if untraded_strong:
            suggestions.append(
                f"\n🎯 {len(untraded_strong)} new STRONG_BUY signals available"
            )
            suggestions.append("   Run: python -m app.run trade --strong-only")

        # Risk warnings
        nav = self.account.get_nav(self.market_data)
        equity = self.account.get_equity(self.market_data)
        exposure_pct = (equity / nav * 100) if nav > 0 else 0

        if exposure_pct > 80:
            suggestions.append(
                f"\n⚠️  High exposure: {exposure_pct:.1f}% of NAV in stocks"
            )
        elif exposure_pct < 20:
            suggestions.append(
                f"\n💰 Low exposure: {exposure_pct:.1f}% of NAV in stocks "
                "(consider trading new signals)"
            )

        # Display suggestions
        if suggestions:
            for suggestion in suggestions:
                lines.append(f"  {suggestion}")
        else:
            lines.append("  ✅ No immediate actions required")
            lines.append("  📊 Portfolio is within normal parameters")

        return "\n".join(lines)

    def _section_risk_metrics(self) -> str:
        """Generate risk metrics section."""
        lines = []
        lines.append("⚖️  RISK METRICS")
        lines.append("-" * 80)

        nav = self.account.get_nav(self.market_data)
        cash = self.account.get_cash()
        equity = self.account.get_equity(self.market_data)

        cash_pct = (cash / nav * 100) if nav > 0 else 0
        equity_pct = (equity / nav * 100) if nav > 0 else 0

        lines.append(f"  Cash Allocation:    {cash_pct:>6.1f}%")
        lines.append(f"  Stock Exposure:     {equity_pct:>6.1f}%")

        # Find largest position
        positions = db.get_all_positions(account_type="paper")
        if positions:
            largest_value = 0.0
            largest_ticker = ""

            for pos in positions:
                price = self.market_data.get_price(pos.ticker) or pos.avg_cost
                value = pos.qty * price
                if value > largest_value:
                    largest_value = value
                    largest_ticker = pos.ticker

            largest_pct = (largest_value / nav * 100) if nav > 0 else 0
            lines.append(
                f"  Largest Position:   {largest_ticker} "
                f"(${largest_value:,.2f}, {largest_pct:.1f}%)"
            )

            # Check concentration risk
            if largest_pct > config.MAX_TICKER_PCT * 100:
                lines.append(
                    f"  ⚠️  Concentration risk: {largest_ticker} exceeds "
                    f"{config.MAX_TICKER_PCT*100:.0f}% limit"
                )

        lines.append(f"\n  Position Limits:")
        lines.append(f"    Max per ticker:   {config.MAX_TICKER_PCT*100:>6.1f}%")
        lines.append(f"    Max daily add:    {config.MAX_DAILY_EXPOSURE*100:>6.1f}%")
        lines.append(f"    Stop loss:        {config.STOP_LOSS_PCT*100:>6.1f}%")
        lines.append(f"    Take profit:      {config.TAKE_PROFIT_PCT*100:>6.1f}%")
        lines.append(f"    Max hold days:    {config.MAX_HOLD_DAYS:>6d}")

        return "\n".join(lines)


# Global instance
_daily_reporter = None


def get_daily_reporter() -> DailyReporter:
    """
    Get singleton daily reporter instance.

    Returns:
        DailyReporter instance
    """
    global _daily_reporter
    if _daily_reporter is None:
        _daily_reporter = DailyReporter()
    return _daily_reporter


def generate_daily_report() -> str:
    """
    Generate and return daily report.

    Returns:
        Formatted report string
    """
    reporter = get_daily_reporter()
    return reporter.generate_report()
