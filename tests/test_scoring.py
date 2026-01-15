"""
Tests for strategy scoring and signal generation.
"""
import unittest
from datetime import date

from app.models import CongressTradeEvent
from app.strategy import CongressTradeStrategy


class TestScoring(unittest.TestCase):
    """Test strategy scoring logic."""

    def setUp(self):
        """Set up test fixtures."""
        self.strategy = CongressTradeStrategy()

    def test_ignore_missing_delay(self):
        """Test that events with missing delay are ignored."""
        event = CongressTradeEvent(
            event_id="test",
            ticker="HAL",
            transaction_type="BUY",
            trade_date=None,  # Missing
            disclosure_date=date(2021, 1, 15),
            amount_low=1000,
            amount_high=15000,
        )

        signal = self.strategy.generate_signal(event)
        self.assertEqual(signal.strength, "IGNORE")

    def test_ignore_delay_too_long(self):
        """Test that events with delay > max are ignored."""
        event = CongressTradeEvent(
            event_id="test",
            ticker="HAL",
            transaction_type="BUY",
            trade_date=date(2021, 1, 1),
            disclosure_date=date(2021, 2, 1),  # 31 days
            amount_low=10000,
            amount_high=50000,
        )

        signal = self.strategy.generate_signal(event)
        self.assertEqual(signal.strength, "IGNORE")

    def test_ignore_amount_too_small(self):
        """Test that events with amount < min are ignored."""
        event = CongressTradeEvent(
            event_id="test",
            ticker="HAL",
            transaction_type="BUY",
            trade_date=date(2021, 1, 1),
            disclosure_date=date(2021, 1, 3),
            amount_low=100,
            amount_high=1000,  # Below min
        )

        signal = self.strategy.generate_signal(event)
        self.assertEqual(signal.strength, "IGNORE")

    def test_strong_buy_signal(self):
        """Test that high-scoring event generates STRONG BUY."""
        event = CongressTradeEvent(
            event_id="test",
            ticker="HAL",
            transaction_type="BUY",
            trade_date=date(2021, 1, 1),
            disclosure_date=date(2021, 1, 2),  # 1 day (very fresh)
            amount_low=250000,
            amount_high=500000,  # Large amount
            owner="member",  # Direct member
        )

        signal = self.strategy.generate_signal(event)

        # Should score high: 50 (base) + 25 (fresh) + 15 (large) + 10 (member) = 100
        self.assertGreaterEqual(signal.score, 80)
        self.assertEqual(signal.action, "BUY")
        self.assertEqual(signal.strength, "STRONG")

    def test_normal_buy_signal(self):
        """Test that medium-scoring event generates NORMAL BUY."""
        event = CongressTradeEvent(
            event_id="test",
            ticker="HAL",
            transaction_type="BUY",
            trade_date=date(2021, 1, 1),
            disclosure_date=date(2021, 1, 8),  # 7 days
            amount_low=50000,
            amount_high=100000,  # Moderate amount
            owner="spouse",
        )

        signal = self.strategy.generate_signal(event)

        # Should score medium
        self.assertGreaterEqual(signal.score, 65)
        self.assertLess(signal.score, 80)
        self.assertEqual(signal.action, "BUY")
        self.assertEqual(signal.strength, "NORMAL")

    def test_watch_signal(self):
        """Test that low-scoring event generates WATCH."""
        event = CongressTradeEvent(
            event_id="test",
            ticker="HAL",
            transaction_type="BUY",
            trade_date=date(2021, 1, 1),
            disclosure_date=date(2021, 1, 13),  # 12 days
            amount_low=5000,
            amount_high=10000,  # Small amount
            owner="dependent",
        )

        signal = self.strategy.generate_signal(event)

        # Should score low but not be ignored
        self.assertLess(signal.score, 65)
        self.assertEqual(signal.strength, "WATCH")
        self.assertEqual(signal.action, "NONE")

    def test_scoring_reasons(self):
        """Test that scoring reasons are populated."""
        event = CongressTradeEvent(
            event_id="test",
            ticker="HAL",
            transaction_type="BUY",
            trade_date=date(2021, 1, 1),
            disclosure_date=date(2021, 1, 2),
            amount_low=250000,
            amount_high=500000,
            owner="member",
        )

        signal = self.strategy.generate_signal(event)

        # Check that reasons exist
        self.assertGreater(len(signal.reason), 0)

        # Check that specific reasons are present
        reason_text = " ".join(signal.reason).lower()
        self.assertIn("disclosure", reason_text)
        self.assertIn("trade", reason_text)


if __name__ == "__main__":
    unittest.main()
