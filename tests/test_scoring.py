"""Tests for signal scoring logic."""

from datetime import date
from uuid import uuid4

import pytest

from tracker.evaluate import SignalGenerator
from tracker.models import Disclosure, TransactionType


@pytest.fixture
def generator():
    return SignalGenerator()


def test_filter_stale_disclosure(generator):
    """Test that stale disclosures are filtered out."""
    disclosure = Disclosure(
        id=uuid4(),
        source="test",
        politician="Test Person",
        ticker="AAPL",
        transaction_type=TransactionType.BUY,
        trade_date=date(2024, 1, 1),
        disclosure_date=date(2024, 3, 1),  # 60 days later
        amount_min=10000,
        amount_max=50000,
        amount_estimate=30000,
        delay_days=60,
        raw_data={},
    )

    should_process, reason = generator.filter_disclosure(disclosure)
    assert not should_process
    assert "STALE" in reason


def test_filter_small_amount(generator):
    """Test that small amounts are filtered out."""
    disclosure = Disclosure(
        id=uuid4(),
        source="test",
        politician="Test Person",
        ticker="AAPL",
        transaction_type=TransactionType.BUY,
        trade_date=date(2024, 1, 1),
        disclosure_date=date(2024, 1, 5),
        amount_min=1000,
        amount_max=3000,  # Less than $5,000
        amount_estimate=2000,
        delay_days=4,
        raw_data={},
    )

    should_process, reason = generator.filter_disclosure(disclosure)
    assert not should_process
    assert "AMOUNT_TOO_SMALL" in reason


def test_score_fresh_large_disclosure(generator):
    """Test scoring for fresh, large disclosure."""
    disclosure = Disclosure(
        id=uuid4(),
        source="test",
        politician="Test Person",
        ticker="AAPL",
        transaction_type=TransactionType.BUY,
        trade_date=date(2024, 1, 1),
        disclosure_date=date(2024, 1, 5),  # 4 days
        amount_min=500000,
        amount_max=1000000,  # $500K-$1M
        amount_estimate=750000,
        delay_days=4,
        raw_data={},
    )

    # Mock database session
    class MockDB:
        def query(self, *args):
            return self

        def filter(self, *args):
            return self

        def scalar(self):
            return 0  # No cluster

    score, reasons = generator.score_disclosure(disclosure, MockDB())

    # Base: 50
    # Freshness (0-7 days): +30
    # Amount ($500K-$1M): +20
    # Member: +15
    # Expected: ~115, capped at 100

    assert score == 100
    assert "FRESH_4D" in reasons
    assert "AMOUNT_500K+" in reasons
    assert "MEMBER_TRADE" in reasons


def test_score_moderate_disclosure(generator):
    """Test scoring for moderate disclosure."""
    disclosure = Disclosure(
        id=uuid4(),
        source="test",
        politician="Test Person",
        ticker="AAPL",
        transaction_type=TransactionType.BUY,
        trade_date=date(2024, 1, 1),
        disclosure_date=date(2024, 1, 20),  # 19 days
        amount_min=50000,
        amount_max=100000,  # $50K-$100K
        amount_estimate=75000,
        delay_days=19,
        raw_data={},
    )

    score, reasons = generator.score_disclosure(disclosure, MockDB())

    # Base: 50
    # Freshness (15-30 days): +10
    # Amount ($50K-$100K): +5
    # Member: +15
    # Expected: 80

    assert 75 <= score <= 85
    assert any("MODERATE" in r or "OLDER" in r for r in reasons)


class MockDB:
    def query(self, *args):
        return self

    def filter(self, *args):
        return self

    def scalar(self):
        return 0


def test_map_score_to_action_high(generator):
    """Test action mapping for high score BUY."""
    from tracker.models import SignalAction, SignalConfidence

    disclosure = Disclosure(
        id=uuid4(),
        source="test",
        politician="Test",
        ticker="AAPL",
        transaction_type=TransactionType.BUY,
        trade_date=date(2024, 1, 1),
        disclosure_date=date(2024, 1, 2),
        amount_min=1000000,
        amount_max=2000000,
        amount_estimate=1500000,
        delay_days=1,
        raw_data={},
    )

    action, confidence = generator.map_score_to_action(90, disclosure, has_position=False)

    assert action == SignalAction.BUY
    assert confidence == SignalConfidence.HIGH


def test_map_score_to_action_sell(generator):
    """Test action mapping for SELL with position."""
    from tracker.models import SignalAction, SignalConfidence

    disclosure = Disclosure(
        id=uuid4(),
        source="test",
        politician="Test",
        ticker="AAPL",
        transaction_type=TransactionType.SELL,
        trade_date=date(2024, 1, 1),
        disclosure_date=date(2024, 1, 2),
        amount_min=100000,
        amount_max=250000,
        amount_estimate=175000,
        delay_days=1,
        raw_data={},
    )

    action, confidence = generator.map_score_to_action(80, disclosure, has_position=True)

    assert action == SignalAction.SELL
    assert confidence == SignalConfidence.HIGH


def test_map_score_to_action_watch(generator):
    """Test action mapping for low score (WATCH)."""
    from tracker.models import SignalAction, SignalConfidence

    disclosure = Disclosure(
        id=uuid4(),
        source="test",
        politician="Test",
        ticker="AAPL",
        transaction_type=TransactionType.BUY,
        trade_date=date(2024, 1, 1),
        disclosure_date=date(2024, 1, 2),
        amount_min=10000,
        amount_max=50000,
        amount_estimate=30000,
        delay_days=1,
        raw_data={},
    )

    action, confidence = generator.map_score_to_action(60, disclosure, has_position=False)

    assert action == SignalAction.WATCH
    assert confidence == SignalConfidence.LOW
