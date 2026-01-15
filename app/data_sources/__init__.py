"""
Congressional trading data sources.

Supports multiple sources with configurable strategies.
"""

from app.data_sources.base import CongressDataSource
from app.data_sources.fmp import FinancialModelingPrepSource
from app.data_sources.house_stock_watcher import HouseStockWatcherSource
from app.data_sources.manager import DataSourceManager, SourceStrategy

__all__ = [
    "CongressDataSource",
    "HouseStockWatcherSource",
    "FinancialModelingPrepSource",
    "DataSourceManager",
    "SourceStrategy",
]
