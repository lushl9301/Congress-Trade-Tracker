"""
Tests for event deduplication and event_id hashing.
"""

import unittest
from datetime import date

from app.models import CongressTradeEvent


class TestDeduplication(unittest.TestCase):
    """Test event deduplication logic."""

    def test_event_id_stable(self):
        """Test that event_id is stable across multiple generations."""
        event_id_1 = CongressTradeEvent.generate_event_id(
            source="finnhub",
            ticker="HAL",
            transaction_type="BUY",
            trade_date=date(2021, 1, 1),
            disclosure_date=date(2021, 1, 15),
            amount_low=1001.0,
            amount_high=15000.0,
            member_name="John Doe",
            owner="member",
        )

        event_id_2 = CongressTradeEvent.generate_event_id(
            source="finnhub",
            ticker="HAL",
            transaction_type="BUY",
            trade_date=date(2021, 1, 1),
            disclosure_date=date(2021, 1, 15),
            amount_low=1001.0,
            amount_high=15000.0,
            member_name="John Doe",
            owner="member",
        )

        self.assertEqual(event_id_1, event_id_2)

    def test_event_id_different_for_different_data(self):
        """Test that different data produces different event_id."""
        event_id_1 = CongressTradeEvent.generate_event_id(
            source="finnhub",
            ticker="HAL",
            transaction_type="BUY",
            trade_date=date(2021, 1, 1),
            disclosure_date=date(2021, 1, 15),
            amount_low=1001.0,
            amount_high=15000.0,
            member_name="John Doe",
            owner="member",
        )

        # Different ticker
        event_id_2 = CongressTradeEvent.generate_event_id(
            source="finnhub",
            ticker="MSFT",  # Changed
            transaction_type="BUY",
            trade_date=date(2021, 1, 1),
            disclosure_date=date(2021, 1, 15),
            amount_low=1001.0,
            amount_high=15000.0,
            member_name="John Doe",
            owner="member",
        )

        self.assertNotEqual(event_id_1, event_id_2)

    def test_event_id_normalized(self):
        """Test that event_id normalizes case and formatting."""
        event_id_1 = CongressTradeEvent.generate_event_id(
            source="finnhub",
            ticker="hal",  # lowercase
            transaction_type="buy",  # lowercase
            trade_date=date(2021, 1, 1),
            disclosure_date=date(2021, 1, 15),
            amount_low=1001.0,
            amount_high=15000.0,
            member_name="john doe",  # lowercase
            owner="member",
        )

        event_id_2 = CongressTradeEvent.generate_event_id(
            source="finnhub",
            ticker="HAL",  # uppercase
            transaction_type="BUY",  # uppercase
            trade_date=date(2021, 1, 1),
            disclosure_date=date(2021, 1, 15),
            amount_low=1001.0,
            amount_high=15000.0,
            member_name="JOHN DOE",  # uppercase
            owner="member",
        )

        self.assertEqual(event_id_1, event_id_2)

    def test_event_delay_calculation(self):
        """Test delay_days calculation."""
        event = CongressTradeEvent(
            event_id="test",
            source="house_stock_watcher",
            ticker="HAL",
            transaction_type="BUY",
            trade_date=date(2021, 1, 1),
            disclosure_date=date(2021, 1, 15),
            amount_low=1000,
            amount_high=15000,
        )

        self.assertEqual(event.delay_days, 14)

    def test_event_amount_mid_calculation(self):
        """Test amount_mid calculation."""
        event = CongressTradeEvent(
            event_id="test",
            source="house_stock_watcher",
            ticker="HAL",
            transaction_type="BUY",
            amount_low=1000,
            amount_high=15000,
        )

        self.assertEqual(event.amount_mid, 8000.0)


if __name__ == "__main__":
    unittest.main()
