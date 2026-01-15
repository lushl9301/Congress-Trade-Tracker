"""
Tests for portfolio management and position sizing.
"""
import unittest
from datetime import datetime, timedelta

from app.models import Position
from app.portfolio import PortfolioManager


class TestPortfolioRules(unittest.TestCase):
    """Test portfolio management rules."""

    def setUp(self):
        """Set up test fixtures."""
        self.pm = PortfolioManager()
        self.nav = 100000.0  # $100k portfolio

    def test_position_size_strong_signal(self):
        """Test position sizing for STRONG signal."""
        qty, reasons = self.pm.calculate_position_size(
            ticker="HAL",
            signal_strength="STRONG",
            nav=self.nav,
            current_price=50.0,
        )

        # Should size for 3% of NAV = $3000 / $50 = 60 shares
        self.assertEqual(qty, 60)

    def test_position_size_normal_signal(self):
        """Test position sizing for NORMAL signal."""
        qty, reasons = self.pm.calculate_position_size(
            ticker="HAL",
            signal_strength="NORMAL",
            nav=self.nav,
            current_price=50.0,
        )

        # Should size for 1.5% of NAV = $1500 / $50 = 30 shares
        self.assertEqual(qty, 30)

    def test_position_size_watch_rejected(self):
        """Test that WATCH signal is rejected."""
        qty, reasons = self.pm.calculate_position_size(
            ticker="HAL",
            signal_strength="WATCH",
            nav=self.nav,
            current_price=50.0,
        )

        self.assertEqual(qty, 0)
        self.assertGreater(len(reasons), 0)

    def test_daily_exposure_limit(self):
        """Test daily exposure limit check."""
        # Within limit
        allowed, reason = self.pm.check_daily_exposure_limit(
            nav=self.nav,
            proposed_notional=5000.0,  # 5% of NAV
        )
        self.assertTrue(allowed)

        # Exceeds limit
        allowed, reason = self.pm.check_daily_exposure_limit(
            nav=self.nav,
            proposed_notional=15000.0,  # 15% of NAV (> 10% limit)
        )
        self.assertFalse(allowed)

    def test_position_exit_time_rule(self):
        """Test time-based exit rule."""
        # Position opened 31 days ago
        position = Position(
            ticker="HAL",
            qty=100,
            avg_cost=50.0,
            opened_at=datetime.utcnow() - timedelta(days=31),
            max_hold_days=30,
            stop_loss_pct=-0.08,
            take_profit_pct=0.20,
        )

        self.assertTrue(position.should_exit_time())

        # Position opened 20 days ago
        position_new = Position(
            ticker="MSFT",
            qty=50,
            avg_cost=100.0,
            opened_at=datetime.utcnow() - timedelta(days=20),
            max_hold_days=30,
            stop_loss_pct=-0.08,
            take_profit_pct=0.20,
        )

        self.assertFalse(position_new.should_exit_time())

    def test_position_exit_stop_loss(self):
        """Test stop loss exit rule."""
        position = Position(
            ticker="HAL",
            qty=100,
            avg_cost=50.0,
            opened_at=datetime.utcnow(),
            stop_loss_pct=-0.08,  # -8%
            take_profit_pct=0.20,
        )

        # Price down 10% -> should exit
        should_exit, reason = position.should_exit_price(45.0)
        self.assertTrue(should_exit)
        self.assertIn("STOP_LOSS", reason)

        # Price down 5% -> should hold
        should_exit, reason = position.should_exit_price(47.5)
        self.assertFalse(should_exit)

    def test_position_exit_take_profit(self):
        """Test take profit exit rule."""
        position = Position(
            ticker="HAL",
            qty=100,
            avg_cost=50.0,
            opened_at=datetime.utcnow(),
            stop_loss_pct=-0.08,
            take_profit_pct=0.20,  # +20%
        )

        # Price up 25% -> should exit
        should_exit, reason = position.should_exit_price(62.5)
        self.assertTrue(should_exit)
        self.assertIn("TAKE_PROFIT", reason)

        # Price up 15% -> should hold
        should_exit, reason = position.should_exit_price(57.5)
        self.assertFalse(should_exit)

    def test_position_notional_value(self):
        """Test notional value calculation."""
        position = Position(
            ticker="HAL",
            qty=100,
            avg_cost=50.0,
            opened_at=datetime.utcnow(),
        )

        self.assertEqual(position.notional_value, 5000.0)

    def test_position_holding_days(self):
        """Test holding days calculation."""
        position = Position(
            ticker="HAL",
            qty=100,
            avg_cost=50.0,
            opened_at=datetime.utcnow() - timedelta(days=10),
        )

        self.assertEqual(position.holding_days, 10)


if __name__ == "__main__":
    unittest.main()
