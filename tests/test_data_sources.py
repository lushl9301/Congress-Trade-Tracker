"""
Tests for congressional data sources.
"""

from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from app.data_sources import (
    DataSourceManager,
    FinancialModelingPrepSource,
    HouseStockWatcherSource,
    SourceStrategy,
)


class TestHouseStockWatcherSource:
    """Tests for House Stock Watcher data source."""

    def test_get_name(self):
        """Test source name."""
        source = HouseStockWatcherSource()
        assert source.get_name() == "house_stock_watcher"

    def test_normalize_trade_purchase(self):
        """Test normalizing a purchase trade."""
        source = HouseStockWatcherSource()

        raw_trade = {
            "disclosure_year": "2021",
            "disclosure_date": "2021-01-15",
            "transaction_date": "2021-01-01",
            "owner": "self",
            "ticker": "AAPL",
            "asset_description": "Apple Inc.",
            "type": "purchase",
            "amount": "$1,001 - $15,000",
            "representative": "Hon. John Doe",
            "district": "CA-12",
            "ptr_link": "https://...",
        }

        normalized = source.normalize_trade(raw_trade)

        assert normalized["source"] == "house_stock_watcher"
        assert normalized["ticker"] == "AAPL"
        assert normalized["transaction_type"] == "BUY"
        assert normalized["owner"] == "member"
        assert normalized["amount_low"] == 1001.0
        assert normalized["amount_high"] == 15000.0
        assert normalized["member_name"] == "Hon. John Doe"
        assert normalized["trade_date"] == date(2021, 1, 1)
        assert normalized["disclosure_date"] == date(2021, 1, 15)

    def test_normalize_trade_sale(self):
        """Test normalizing a sale trade."""
        source = HouseStockWatcherSource()

        raw_trade = {
            "disclosure_date": "2021-01-15",
            "transaction_date": "2021-01-01",
            "owner": "spouse",
            "ticker": "TSLA",
            "asset_description": "Tesla Inc.",
            "type": "sale",
            "amount": "$15,001 - $50,000",
            "representative": "Hon. Jane Smith",
        }

        normalized = source.normalize_trade(raw_trade)

        assert normalized["transaction_type"] == "SELL"
        assert normalized["owner"] == "spouse"
        assert normalized["amount_low"] == 15001.0
        assert normalized["amount_high"] == 50000.0

    def test_parse_amount_range(self):
        """Test parsing amount ranges."""
        source = HouseStockWatcherSource()

        # Test various amount formats
        assert source._parse_amount_range("$1,001 - $15,000") == (1001.0, 15000.0)
        assert source._parse_amount_range("$15,001 - $50,000") == (15001.0, 50000.0)
        assert source._parse_amount_range("$50,001 - $100,000") == (
            50001.0,
            100000.0,
        )
        assert source._parse_amount_range("N/A") == (None, None)
        assert source._parse_amount_range("") == (None, None)

    def test_normalize_owner(self):
        """Test owner normalization."""
        source = HouseStockWatcherSource()

        assert source._normalize_owner("self") == "member"
        assert source._normalize_owner("spouse") == "spouse"
        assert source._normalize_owner("joint") == "spouse"
        assert source._normalize_owner("child") == "dependent"
        assert source._normalize_owner("other") == "unknown"

    def test_rate_limit_info(self):
        """Test rate limit information."""
        source = HouseStockWatcherSource()
        info = source.get_rate_limit_info()

        assert info["source"] == "house_stock_watcher"
        assert info["requires_auth"] is False
        assert info["cost"] == "free"


class TestFinancialModelingPrepSource:
    """Tests for Financial Modeling Prep data source."""

    def test_get_name(self):
        """Test source name."""
        source = FinancialModelingPrepSource()
        assert source.get_name() == "financial_modeling_prep"

    def test_dummy_api_key_warning(self, caplog):
        """Test that dummy API key produces warning."""
        source = FinancialModelingPrepSource(api_key="DUMMY_FMP_API_KEY_REPLACE_ME")
        assert "DUMMY API key" in caplog.text

    def test_is_available_with_dummy_key(self):
        """Test that source is not available with dummy API key."""
        source = FinancialModelingPrepSource(api_key="DUMMY_FMP_API_KEY_REPLACE_ME")
        assert source.is_available() is False

    def test_normalize_trade_purchase(self):
        """Test normalizing a purchase trade."""
        source = FinancialModelingPrepSource()

        raw_trade = {
            "firstName": "John",
            "lastName": "Doe",
            "office": "Senate",
            "dateRecieved": "2021-01-15",
            "transactionDate": "2021-01-01",
            "owner": "Self",
            "ticker": "AAPL",
            "assetDescription": "Apple Inc.",
            "assetType": "Stock",
            "type": "Purchase",
            "amount": "$1,001 - $15,000",
        }

        normalized = source.normalize_trade(raw_trade)

        assert normalized["source"] == "financial_modeling_prep"
        assert normalized["ticker"] == "AAPL"
        assert normalized["transaction_type"] == "BUY"
        assert normalized["owner"] == "member"
        assert normalized["amount_low"] == 1001.0
        assert normalized["amount_high"] == 15000.0
        assert normalized["member_name"] == "John Doe"
        assert normalized["trade_date"] == date(2021, 1, 1)
        assert normalized["disclosure_date"] == date(2021, 1, 15)

    def test_rate_limit_info(self):
        """Test rate limit information."""
        source = FinancialModelingPrepSource()
        info = source.get_rate_limit_info()

        assert info["source"] == "financial_modeling_prep"
        assert info["limit_per_day"] == 250
        assert info["requires_auth"] is True
        assert info["cost"] == "free"


class TestDataSourceManager:
    """Tests for DataSourceManager."""

    def test_init_requires_sources(self):
        """Test that manager requires at least one source."""
        with pytest.raises(ValueError, match="At least one data source"):
            DataSourceManager(sources=[])

    def test_strategy_cross_verify_single_source(self):
        """Test cross-verify strategy with single available source."""
        # Create a mock source
        mock_source = MagicMock()
        mock_source.get_name.return_value = "test_source"
        mock_source.is_available.return_value = True
        mock_source.get_trades.return_value = [
            {"ticker": "AAPL", "transaction_type": "BUY", "trade_date": date(2021, 1, 1)}
        ]
        mock_source.normalize_trade.side_effect = lambda x: {
            **x,
            "source": "test_source",
            "owner": "member",
        }

        manager = DataSourceManager(
            sources=[mock_source], strategy=SourceStrategy.CROSS_VERIFY
        )

        trades = manager.get_trades()

        # Should get trades with single_source verification status
        assert len(trades) == 1
        assert trades[0]["verified"] is False
        assert trades[0]["verification_status"] == "single_source"
        assert "test_source" in trades[0]["verification_sources"]

    def test_strategy_cross_verify_multiple_sources(self):
        """Test cross-verify strategy with multiple sources."""
        # Create two mock sources that report the same trade
        mock_source1 = MagicMock()
        mock_source1.get_name.return_value = "source1"
        mock_source1.is_available.return_value = True
        mock_source1.get_trades.return_value = [
            {"ticker": "AAPL", "transaction_type": "BUY"}
        ]
        mock_source1.normalize_trade.return_value = {
            "source": "source1",
            "ticker": "AAPL",
            "transaction_type": "BUY",
            "trade_date": date(2021, 1, 1),
            "owner": "member",
            "amount_low": 1000.0,
            "amount_high": 15000.0,
        }

        mock_source2 = MagicMock()
        mock_source2.get_name.return_value = "source2"
        mock_source2.is_available.return_value = True
        mock_source2.get_trades.return_value = [
            {"ticker": "AAPL", "transaction_type": "BUY"}
        ]
        mock_source2.normalize_trade.return_value = {
            "source": "source2",
            "ticker": "AAPL",
            "transaction_type": "BUY",
            "trade_date": date(2021, 1, 1),
            "owner": "member",
            "amount_low": 1000.0,
            "amount_high": 15000.0,
        }

        manager = DataSourceManager(
            sources=[mock_source1, mock_source2], strategy=SourceStrategy.CROSS_VERIFY
        )

        trades = manager.get_trades()

        # Should get one verified trade
        assert len(trades) == 1
        assert trades[0]["verified"] is True
        assert trades[0]["verification_status"] == "verified"
        assert set(trades[0]["verification_sources"]) == {"source1", "source2"}

    def test_strategy_fallback(self):
        """Test fallback strategy when primary fails."""
        # Primary source that fails
        mock_primary = MagicMock()
        mock_primary.get_name.return_value = "primary"
        mock_primary.is_available.return_value = False

        # Fallback source that succeeds
        mock_fallback = MagicMock()
        mock_fallback.get_name.return_value = "fallback"
        mock_fallback.is_available.return_value = True
        mock_fallback.get_trades.return_value = [
            {"ticker": "AAPL", "transaction_type": "BUY"}
        ]
        mock_fallback.normalize_trade.return_value = {
            "source": "fallback",
            "ticker": "AAPL",
            "transaction_type": "BUY",
            "owner": "member",
        }

        manager = DataSourceManager(
            sources=[mock_primary, mock_fallback],
            strategy=SourceStrategy.FALLBACK,
            primary_source_index=0,
        )

        trades = manager.get_trades()

        # Should use fallback source
        assert len(trades) == 1
        assert trades[0]["source"] == "fallback"

    def test_get_source_health(self):
        """Test source health check."""
        mock_source = MagicMock()
        mock_source.get_name.return_value = "test_source"
        mock_source.health_check.return_value = {
            "source": "test_source",
            "available": True,
            "error": None,
        }
        mock_source.get_rate_limit_info.return_value = {
            "limit_per_day": 250,
            "requires_auth": False,
        }

        manager = DataSourceManager(sources=[mock_source])
        health = manager.get_source_health()

        assert health["strategy"] == "verify"
        assert len(health["sources"]) == 1
        assert health["sources"][0]["name"] == "test_source"
        assert health["sources"][0]["available"] is True
