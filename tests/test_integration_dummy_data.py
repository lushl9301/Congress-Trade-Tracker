"""
Integration tests with dummy data for multi-source ingestion.

This test suite simulates real data from HSW and FMP sources without
requiring actual API keys or network calls.
"""

import json
import tempfile
from datetime import date, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.config import Config
from app.data_sources import (
    DataSourceManager,
    FinancialModelingPrepSource,
    HouseStockWatcherSource,
    SourceStrategy,
)
from app.db import Database
from app.ingest import CongressTradeIngester
from app.models import CongressTradeEvent


class TestIntegrationWithDummyData:
    """Integration tests using dummy congressional trading data."""

    @pytest.fixture
    def temp_db(self):
        """Create a temporary database for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = Database(db_path)
            db.init_schema()
            yield db

    @pytest.fixture
    def dummy_hsw_data(self):
        """Generate dummy House Stock Watcher data."""
        return [
            {
                "disclosure_year": "2024",
                "disclosure_date": "2024-01-15",
                "transaction_date": "2024-01-10",
                "owner": "self",
                "ticker": "AAPL",
                "asset_description": "Apple Inc. - Common Stock",
                "type": "purchase",
                "amount": "$15,001 - $50,000",
                "representative": "Hon. John Smith",
                "district": "CA-12",
                "ptr_link": "https://example.com/ptr1",
            },
            {
                "disclosure_year": "2024",
                "disclosure_date": "2024-01-16",
                "transaction_date": "2024-01-11",
                "owner": "spouse",
                "ticker": "MSFT",
                "asset_description": "Microsoft Corporation",
                "type": "sale",
                "amount": "$50,001 - $100,000",
                "representative": "Hon. Jane Doe",
                "district": "NY-14",
                "ptr_link": "https://example.com/ptr2",
            },
            {
                "disclosure_year": "2024",
                "disclosure_date": "2024-01-17",
                "transaction_date": "2024-01-12",
                "owner": "self",
                "ticker": "TSLA",
                "asset_description": "Tesla Inc",
                "type": "purchase",
                "amount": "$1,001 - $15,000",
                "representative": "Hon. Bob Wilson",
                "district": "TX-21",
                "ptr_link": "https://example.com/ptr3",
            },
        ]

    @pytest.fixture
    def dummy_fmp_data(self):
        """Generate dummy Financial Modeling Prep data."""
        return [
            {
                "firstName": "John",
                "lastName": "Smith",
                "office": "House",
                "dateRecieved": "2024-01-15",
                "transactionDate": "2024-01-10",
                "owner": "Self",
                "ticker": "AAPL",
                "assetDescription": "Apple Inc. - Common Stock",
                "assetType": "Stock",
                "type": "Purchase",
                "amount": "$15,001 - $50,000",
                "comment": None,
            },
            {
                "firstName": "Sarah",
                "lastName": "Johnson",
                "office": "Senate",
                "dateRecieved": "2024-01-18",
                "transactionDate": "2024-01-13",
                "owner": "Self",
                "ticker": "GOOGL",
                "assetDescription": "Alphabet Inc. Class A",
                "assetType": "Stock",
                "type": "Purchase",
                "amount": "$15,001 - $50,000",
                "comment": None,
            },
        ]

    def test_hsw_source_normalization(self, dummy_hsw_data):
        """Test House Stock Watcher data normalization."""
        source = HouseStockWatcherSource()

        # Normalize first trade
        normalized = source.normalize_trade(dummy_hsw_data[0])

        assert normalized["source"] == "house_stock_watcher"
        assert normalized["ticker"] == "AAPL"
        assert normalized["transaction_type"] == "BUY"
        assert normalized["owner"] == "member"
        assert normalized["amount_low"] == 15001.0
        assert normalized["amount_high"] == 50000.0
        assert normalized["member_name"] == "Hon. John Smith"
        assert normalized["trade_date"] == date(2024, 1, 10)
        assert normalized["disclosure_date"] == date(2024, 1, 15)

    def test_fmp_source_normalization(self, dummy_fmp_data):
        """Test Financial Modeling Prep data normalization."""
        source = FinancialModelingPrepSource()

        # Normalize first trade
        normalized = source.normalize_trade(dummy_fmp_data[0])

        assert normalized["source"] == "financial_modeling_prep"
        assert normalized["ticker"] == "AAPL"
        assert normalized["transaction_type"] == "BUY"
        assert normalized["owner"] == "member"
        assert normalized["amount_low"] == 15001.0
        assert normalized["amount_high"] == 50000.0
        assert normalized["member_name"] == "John Smith"
        assert normalized["trade_date"] == date(2024, 1, 10)
        assert normalized["disclosure_date"] == date(2024, 1, 15)

    def test_cross_verification_matching(self, dummy_hsw_data, dummy_fmp_data):
        """Test cross-verification matches same trade from different sources."""
        # Create mock sources
        mock_hsw = MagicMock(spec=HouseStockWatcherSource)
        mock_hsw.get_name.return_value = "house_stock_watcher"
        mock_hsw.is_available.return_value = True
        mock_hsw.get_trades.return_value = [dummy_hsw_data[0]]  # AAPL trade
        mock_hsw.normalize_trade.return_value = {
            "source": "house_stock_watcher",
            "ticker": "AAPL",
            "transaction_type": "BUY",
            "trade_date": date(2024, 1, 10),
            "disclosure_date": date(2024, 1, 15),
            "owner": "member",
            "member_name": "Hon. John Smith",
            "amount_low": 15001.0,
            "amount_high": 50000.0,
            "raw": dummy_hsw_data[0],
        }

        mock_fmp = MagicMock(spec=FinancialModelingPrepSource)
        mock_fmp.get_name.return_value = "financial_modeling_prep"
        mock_fmp.is_available.return_value = True
        mock_fmp.get_trades.return_value = [dummy_fmp_data[0]]  # Same AAPL trade
        mock_fmp.normalize_trade.return_value = {
            "source": "financial_modeling_prep",
            "ticker": "AAPL",
            "transaction_type": "BUY",
            "trade_date": date(2024, 1, 10),
            "disclosure_date": date(2024, 1, 15),
            "owner": "member",
            "member_name": "John Smith",
            "amount_low": 15001.0,
            "amount_high": 50000.0,
            "raw": dummy_fmp_data[0],
        }

        # Create manager with cross-verify strategy
        manager = DataSourceManager(
            sources=[mock_hsw, mock_fmp], strategy=SourceStrategy.CROSS_VERIFY
        )

        # Get trades with verification
        trades = manager.get_trades()

        # Should have exactly 1 verified trade (same trade from both sources)
        assert len(trades) == 1
        assert trades[0]["verified"] is True
        assert trades[0]["verification_status"] == "verified"
        assert set(trades[0]["verification_sources"]) == {
            "house_stock_watcher",
            "financial_modeling_prep",
        }
        assert trades[0]["ticker"] == "AAPL"

    def test_cross_verification_unique_trades(self, dummy_hsw_data, dummy_fmp_data):
        """Test cross-verification with unique trades from each source."""
        # Create mock sources with different trades
        mock_hsw = MagicMock(spec=HouseStockWatcherSource)
        mock_hsw.get_name.return_value = "house_stock_watcher"
        mock_hsw.is_available.return_value = True
        mock_hsw.get_trades.return_value = [dummy_hsw_data[1]]  # MSFT trade
        mock_hsw.normalize_trade.return_value = {
            "source": "house_stock_watcher",
            "ticker": "MSFT",
            "transaction_type": "SELL",
            "trade_date": date(2024, 1, 11),
            "owner": "spouse",
            "member_name": "Hon. Jane Doe",
            "amount_low": 50001.0,
            "amount_high": 100000.0,
            "raw": dummy_hsw_data[1],
        }

        mock_fmp = MagicMock(spec=FinancialModelingPrepSource)
        mock_fmp.get_name.return_value = "financial_modeling_prep"
        mock_fmp.is_available.return_value = True
        mock_fmp.get_trades.return_value = [dummy_fmp_data[1]]  # GOOGL trade
        mock_fmp.normalize_trade.return_value = {
            "source": "financial_modeling_prep",
            "ticker": "GOOGL",
            "transaction_type": "BUY",
            "trade_date": date(2024, 1, 13),
            "owner": "member",
            "member_name": "Sarah Johnson",
            "amount_low": 15001.0,
            "amount_high": 50000.0,
            "raw": dummy_fmp_data[1],
        }

        # Create manager with cross-verify strategy
        manager = DataSourceManager(
            sources=[mock_hsw, mock_fmp], strategy=SourceStrategy.CROSS_VERIFY
        )

        # Get trades
        trades = manager.get_trades()

        # Should have 2 unverified trades (different trades from each source)
        assert len(trades) == 2
        assert all(not trade["verified"] for trade in trades)
        assert all(trade["verification_status"] == "unverified" for trade in trades)

        # Check both tickers are present
        tickers = {trade["ticker"] for trade in trades}
        assert tickers == {"MSFT", "GOOGL"}

    def test_single_source_fallback(self, dummy_hsw_data):
        """Test system works with only one source available."""
        # Create mock HSW source
        mock_hsw = MagicMock(spec=HouseStockWatcherSource)
        mock_hsw.get_name.return_value = "house_stock_watcher"
        mock_hsw.is_available.return_value = True
        mock_hsw.get_trades.return_value = [dummy_hsw_data[0]]
        mock_hsw.normalize_trade.return_value = {
            "source": "house_stock_watcher",
            "ticker": "AAPL",
            "transaction_type": "BUY",
            "trade_date": date(2024, 1, 10),
            "owner": "member",
            "member_name": "Hon. John Smith",
            "amount_low": 15001.0,
            "amount_high": 50000.0,
            "raw": dummy_hsw_data[0],
        }

        # Create mock FMP source that's unavailable
        mock_fmp = MagicMock(spec=FinancialModelingPrepSource)
        mock_fmp.get_name.return_value = "financial_modeling_prep"
        mock_fmp.is_available.return_value = False

        # Create manager with cross-verify strategy
        manager = DataSourceManager(
            sources=[mock_hsw, mock_fmp], strategy=SourceStrategy.CROSS_VERIFY
        )

        # Get trades - should fall back to single source
        trades = manager.get_trades()

        # Should have 1 trade in single_source mode
        assert len(trades) == 1
        assert trades[0]["verified"] is False
        assert trades[0]["verification_status"] == "single_source"
        assert trades[0]["verification_sources"] == ["house_stock_watcher"]

    @patch("app.ingest.CongressTradeIngester._init_data_source_manager")
    def test_end_to_end_ingestion(
        self, mock_init_manager, temp_db, dummy_hsw_data, dummy_fmp_data
    ):
        """Test end-to-end ingestion with dummy data."""
        # Create mock data source manager
        mock_manager = MagicMock()
        mock_manager.get_trades.return_value = [
            {
                "source": "house_stock_watcher",
                "ticker": "AAPL",
                "transaction_type": "BUY",
                "trade_date": date(2024, 1, 10),
                "disclosure_date": date(2024, 1, 15),
                "owner": "member",
                "member_name": "Hon. John Smith",
                "member_id": None,
                "amount_low": 15001.0,
                "amount_high": 50000.0,
                "asset_description": "Apple Inc. - Common Stock",
                "raw": dummy_hsw_data[0],
                "verified": True,
                "verification_sources": ["house_stock_watcher", "financial_modeling_prep"],
                "verification_status": "verified",
                "verification_discrepancies": None,
            },
            {
                "source": "house_stock_watcher",
                "ticker": "MSFT",
                "transaction_type": "SELL",
                "trade_date": date(2024, 1, 11),
                "disclosure_date": date(2024, 1, 16),
                "owner": "spouse",
                "member_name": "Hon. Jane Doe",
                "member_id": None,
                "amount_low": 50001.0,
                "amount_high": 100000.0,
                "asset_description": "Microsoft Corporation",
                "raw": dummy_hsw_data[1],
                "verified": False,
                "verification_sources": ["house_stock_watcher"],
                "verification_status": "unverified",
                "verification_discrepancies": None,
            },
        ]

        mock_init_manager.return_value = mock_manager

        # Create ingester with temp database
        ingester = CongressTradeIngester()
        ingester.db = temp_db

        # Run ingestion
        result = ingester.ingest_latest()

        # Verify results
        assert result["status"] == "success"
        assert result["fetched"] == 2
        assert result["new_events"] == 2
        assert result["duplicates"] == 0
        assert result["verified"] == 1
        assert result["unverified"] == 1
        assert result["verification_rate"] == "50.0%"

        # Verify data in database
        with temp_db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM congress_trade_events")
            count = cursor.fetchone()[0]
            assert count == 2

            # Check verification metadata
            cursor.execute(
                """
                SELECT ticker, verified, verification_status, verification_sources
                FROM congress_trade_events
                ORDER BY ticker
                """
            )
            rows = cursor.fetchall()

            # AAPL - verified
            assert rows[0][0] == "AAPL"
            assert rows[0][1] == 1  # verified = True
            assert rows[0][2] == "verified"
            sources = json.loads(rows[0][3])
            assert set(sources) == {"house_stock_watcher", "financial_modeling_prep"}

            # MSFT - unverified
            assert rows[1][0] == "MSFT"
            assert rows[1][1] == 0  # verified = False
            assert rows[1][2] == "unverified"

    @patch("app.ingest.CongressTradeIngester._init_data_source_manager")
    def test_duplicate_detection(
        self, mock_init_manager, temp_db, dummy_hsw_data
    ):
        """Test that duplicate events are properly detected."""
        # Create mock manager that returns the same trade twice
        mock_manager = MagicMock()
        mock_manager.get_trades.return_value = [
            {
                "source": "house_stock_watcher",
                "ticker": "AAPL",
                "transaction_type": "BUY",
                "trade_date": date(2024, 1, 10),
                "disclosure_date": date(2024, 1, 15),
                "owner": "member",
                "member_name": "Hon. John Smith",
                "member_id": None,
                "amount_low": 15001.0,
                "amount_high": 50000.0,
                "asset_description": "Apple Inc.",
                "raw": dummy_hsw_data[0],
                "verified": False,
                "verification_sources": ["house_stock_watcher"],
                "verification_status": "unverified",
                "verification_discrepancies": None,
            }
        ]

        mock_init_manager.return_value = mock_manager

        # Create ingester with temp database
        ingester = CongressTradeIngester()
        ingester.db = temp_db

        # Run ingestion first time
        result1 = ingester.ingest_latest()
        assert result1["new_events"] == 1
        assert result1["duplicates"] == 0

        # Run ingestion second time with same data
        result2 = ingester.ingest_latest()
        assert result2["new_events"] == 0
        assert result2["duplicates"] == 1

        # Verify only one event in database
        with temp_db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM congress_trade_events")
            count = cursor.fetchone()[0]
            assert count == 1

    def test_amount_discrepancy_detection(self):
        """Test detection of amount discrepancies across sources."""
        # Create mock sources with same trade but different amounts
        mock_hsw = MagicMock(spec=HouseStockWatcherSource)
        mock_hsw.get_name.return_value = "house_stock_watcher"
        mock_hsw.is_available.return_value = True
        mock_hsw.get_trades.return_value = [{}]
        mock_hsw.normalize_trade.return_value = {
            "source": "house_stock_watcher",
            "ticker": "AAPL",
            "transaction_type": "BUY",
            "trade_date": date(2024, 1, 10),
            "owner": "member",
            "amount_low": 15001.0,
            "amount_high": 50000.0,  # Different amount
            "raw": {},
        }

        mock_fmp = MagicMock(spec=FinancialModelingPrepSource)
        mock_fmp.get_name.return_value = "financial_modeling_prep"
        mock_fmp.is_available.return_value = True
        mock_fmp.get_trades.return_value = [{}]
        mock_fmp.normalize_trade.return_value = {
            "source": "financial_modeling_prep",
            "ticker": "AAPL",
            "transaction_type": "BUY",
            "trade_date": date(2024, 1, 10),
            "owner": "member",
            "amount_low": 1001.0,
            "amount_high": 15000.0,  # Different amount
            "raw": {},
        }

        # Create manager
        manager = DataSourceManager(
            sources=[mock_hsw, mock_fmp], strategy=SourceStrategy.CROSS_VERIFY
        )

        trades = manager.get_trades()

        # Should detect discrepancy
        assert len(trades) == 1
        assert trades[0]["verified"] is True
        assert "verification_discrepancies" in trades[0]
        assert trades[0]["verification_discrepancies"] is not None
        assert trades[0]["verification_discrepancies"]["type"] == "amount_mismatch"


def test_run_with_config():
    """Test that configuration is properly read."""
    # This tests that Config class has the new fields
    assert hasattr(Config, "HSW_ENABLED")
    assert hasattr(Config, "FMP_ENABLED")
    assert hasattr(Config, "FMP_API_KEY")
    assert hasattr(Config, "DATA_SOURCE_STRATEGY")

    # Test configuration loads correctly
    config = Config()
    assert isinstance(config.HSW_ENABLED, bool)  # Can be True or False
    assert isinstance(config.FMP_ENABLED, bool)  # Can be True or False
    assert config.DATA_SOURCE_STRATEGY == "verify"  # Should use verify strategy
