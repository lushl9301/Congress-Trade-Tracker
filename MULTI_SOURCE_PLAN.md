# Implementation Plan: Multi-Source Congressional Trading Data

**Date:** 2026-01-15
**Objective:** Implement configurable multi-source congressional trading data with cross-verification
**Sources:** House Stock Watcher (HSW) + Financial Modeling Prep (FMP)
**Usage Pattern:** Few times per day (low frequency, rate limits not a concern)

---

## Architecture Overview

### Current State
```
app/finnhub_client.py → Finnhub API (paid, not available)
    ↓
app/ingest.py → Normalization
    ↓
Database
```

### Target State
```
app/data_sources/
├── base.py              # Abstract base class
├── house_stock_watcher.py
├── fmp.py
└── manager.py           # Source selection & verification
    ↓
app/ingest.py → Normalization
    ↓
Database (with source tracking & verification flags)
```

---

## Phase 1: Architecture & Base Classes

### 1.1 Create Base Data Source Interface

**File:** `app/data_sources/base.py`

```python
from abc import ABC, abstractmethod
from datetime import date
from typing import List, Dict, Any, Optional

class CongressDataSource(ABC):
    """Abstract base class for congressional trading data sources."""

    @abstractmethod
    def get_name(self) -> str:
        """Return source name."""
        pass

    @abstractmethod
    def get_trades(
        self,
        symbol: Optional[str] = None,
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
    ) -> List[Dict[str, Any]]:
        """
        Fetch congressional trades from source.

        Returns:
            List of raw trade records from the source
        """
        pass

    @abstractmethod
    def normalize_trade(self, raw_trade: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalize raw trade data to common format.

        Returns:
            Dict with standard fields:
            - member_name
            - member_id (if available)
            - ticker
            - transaction_type (BUY/SELL)
            - trade_date
            - disclosure_date
            - amount_low
            - amount_high
            - owner (member/spouse/dependent/unknown)
        """
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check if source is available and configured."""
        pass

    @abstractmethod
    def get_rate_limit_info(self) -> Dict[str, Any]:
        """Return rate limit information."""
        pass
```

**Key Design Decisions:**
- ✅ Abstract base class for consistency
- ✅ Common interface for all sources
- ✅ Source-specific normalization
- ✅ Availability checking
- ✅ Rate limit awareness

---

### 1.2 Create Data Source Manager

**File:** `app/data_sources/manager.py`

```python
from typing import List, Dict, Any, Optional, Tuple
from enum import Enum
from datetime import date

from app.data_sources.base import CongressDataSource
from app.logging import get_logger

logger = get_logger(__name__)


class SourceStrategy(Enum):
    """Data source selection strategies."""
    PRIMARY_ONLY = "primary_only"          # Use only primary source
    PRIMARY_WITH_FALLBACK = "fallback"     # Try primary, fallback if fails
    ALL_SOURCES = "all"                    # Fetch from all sources
    CROSS_VERIFY = "verify"                # Fetch from all, compare results


class DataSourceManager:
    """Manages multiple congressional data sources."""

    def __init__(
        self,
        sources: List[CongressDataSource],
        strategy: SourceStrategy = SourceStrategy.PRIMARY_ONLY,
    ):
        self.sources = sources
        self.strategy = strategy
        self.primary_source = sources[0] if sources else None

    def fetch_trades(
        self,
        symbol: Optional[str] = None,
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
    ) -> Dict[str, Any]:
        """
        Fetch trades based on configured strategy.

        Returns:
            {
                'status': 'success' | 'partial' | 'failed',
                'trades': List[normalized_trades],
                'sources_used': List[source_names],
                'errors': List[error_messages],
                'verification': {...} if strategy == CROSS_VERIFY
            }
        """
        if self.strategy == SourceStrategy.PRIMARY_ONLY:
            return self._fetch_primary_only(symbol, from_date, to_date)

        elif self.strategy == SourceStrategy.PRIMARY_WITH_FALLBACK:
            return self._fetch_with_fallback(symbol, from_date, to_date)

        elif self.strategy == SourceStrategy.ALL_SOURCES:
            return self._fetch_all_sources(symbol, from_date, to_date)

        elif self.strategy == SourceStrategy.CROSS_VERIFY:
            return self._fetch_and_verify(symbol, from_date, to_date)

    def _fetch_primary_only(self, symbol, from_date, to_date) -> Dict[str, Any]:
        """Fetch from primary source only."""
        pass

    def _fetch_with_fallback(self, symbol, from_date, to_date) -> Dict[str, Any]:
        """Try primary, use fallback if fails."""
        pass

    def _fetch_all_sources(self, symbol, from_date, to_date) -> Dict[str, Any]:
        """Fetch from all sources, merge results."""
        pass

    def _fetch_and_verify(self, symbol, from_date, to_date) -> Dict[str, Any]:
        """Fetch from all sources, compare for verification."""
        pass

    def cross_verify_trades(
        self,
        trades_by_source: Dict[str, List[Dict]]
    ) -> Dict[str, Any]:
        """
        Compare trades from multiple sources.

        Returns:
            {
                'total_trades': int,
                'verified_trades': int,
                'source_only_trades': Dict[source_name, count],
                'discrepancies': List[{
                    'ticker': str,
                    'member': str,
                    'issue': str,
                    'sources': Dict[source_name, data]
                }]
            }
        """
        pass
```

**Key Features:**
- ✅ Multiple strategies for different use cases
- ✅ Flexible source management
- ✅ Cross-verification support
- ✅ Error handling and fallback
- ✅ Detailed result reporting

---

## Phase 2: Implement Data Sources

### 2.1 House Stock Watcher Client

**File:** `app/data_sources/house_stock_watcher.py`

```python
import requests
from typing import List, Dict, Any, Optional
from datetime import date, datetime

from app.data_sources.base import CongressDataSource
from app.logging import get_logger

logger = get_logger(__name__)


class HouseStockWatcherClient(CongressDataSource):
    """Client for House Stock Watcher API."""

    BASE_URL = "https://housestockwatcher.com/api"

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Congress-Trade-Tracker/1.0'
        })

    def get_name(self) -> str:
        return "HouseStockWatcher"

    def get_trades(
        self,
        symbol: Optional[str] = None,
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
    ) -> List[Dict[str, Any]]:
        """
        Fetch trades from House Stock Watcher.

        Note: HSW API returns all trades, filtering done client-side.
        """
        try:
            response = self.session.get(self.BASE_URL, timeout=30)
            response.raise_for_status()
            trades = response.json()

            # Client-side filtering
            filtered = self._filter_trades(trades, symbol, from_date, to_date)

            logger.info(
                f"Fetched {len(trades)} trades from HSW, "
                f"{len(filtered)} after filtering"
            )

            return filtered

        except requests.RequestException as e:
            logger.error(f"HSW API error: {e}")
            raise

    def normalize_trade(self, raw_trade: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalize HSW trade format.

        HSW Format:
        {
            "transaction_date": "2024-01-15",
            "disclosure_date": "2024-02-01",
            "ticker": "AAPL",
            "asset_description": "Apple Inc.",
            "type": "purchase",  # or "sale"
            "amount": "$1,001 - $15,000",
            "representative": "Nancy Pelosi",
            "district": "CA-11",
            "ptr_link": "..."
        }
        """
        # Parse amount range
        amount_low, amount_high = self._parse_amount(raw_trade.get('amount', ''))

        # Normalize transaction type
        tx_type = self._normalize_type(raw_trade.get('type', ''))

        # Parse dates
        trade_date = self._parse_date(raw_trade.get('transaction_date'))
        disclosure_date = self._parse_date(raw_trade.get('disclosure_date'))

        return {
            'source': 'house_stock_watcher',
            'member_name': raw_trade.get('representative'),
            'member_id': None,  # HSW doesn't provide this
            'ticker': raw_trade.get('ticker', '').upper(),
            'asset_description': raw_trade.get('asset_description'),
            'transaction_type': tx_type,
            'trade_date': trade_date,
            'disclosure_date': disclosure_date,
            'amount_low': amount_low,
            'amount_high': amount_high,
            'owner': 'member',  # HSW only tracks member trades
            'district': raw_trade.get('district'),
            'ptr_link': raw_trade.get('ptr_link'),
            'raw': raw_trade,
        }

    def is_available(self) -> bool:
        """Check if HSW API is accessible."""
        try:
            response = self.session.head(self.BASE_URL, timeout=5)
            return response.status_code == 200
        except:
            return False

    def get_rate_limit_info(self) -> Dict[str, Any]:
        """HSW doesn't publish rate limits."""
        return {
            'source': 'house_stock_watcher',
            'rate_limit': 'Unknown',
            'recommendation': 'Be conservative, ~1 request per minute',
        }

    def _filter_trades(self, trades, symbol, from_date, to_date):
        """Client-side filtering."""
        # Implementation details...
        pass

    def _parse_amount(self, amount_str: str) -> tuple[float, float]:
        """Parse amount range like '$1,001 - $15,000'."""
        # Implementation details...
        pass

    def _normalize_type(self, type_str: str) -> str:
        """Normalize 'purchase'/'sale' to 'BUY'/'SELL'."""
        # Implementation details...
        pass

    def _parse_date(self, date_str: str) -> Optional[date]:
        """Parse date string."""
        # Implementation details...
        pass
```

---

### 2.2 Financial Modeling Prep Client

**File:** `app/data_sources/fmp.py`

```python
import os
import requests
from typing import List, Dict, Any, Optional
from datetime import date

from app.data_sources.base import CongressDataSource
from app.logging import get_logger

logger = get_logger(__name__)


class FMPClient(CongressDataSource):
    """Client for Financial Modeling Prep API."""

    BASE_URL = "https://financialmodelingprep.com/api/v4"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("FMP_API_KEY")
        if not self.api_key:
            logger.warning("FMP_API_KEY not set, FMP source unavailable")

        self.session = requests.Session()

    def get_name(self) -> str:
        return "FinancialModelingPrep"

    def get_trades(
        self,
        symbol: Optional[str] = None,
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
    ) -> List[Dict[str, Any]]:
        """
        Fetch trades from FMP.

        Combines both Senate and House endpoints.
        """
        if not self.is_available():
            raise ValueError("FMP API key not configured")

        trades = []

        # Fetch Senate trades
        senate_trades = self._fetch_senate_trades(symbol, from_date, to_date)
        trades.extend(senate_trades)

        # Fetch House trades
        house_trades = self._fetch_house_trades(symbol, from_date, to_date)
        trades.extend(house_trades)

        logger.info(
            f"Fetched {len(senate_trades)} Senate + {len(house_trades)} House "
            f"trades from FMP"
        )

        return trades

    def _fetch_senate_trades(self, symbol, from_date, to_date):
        """Fetch from Senate endpoint."""
        url = f"{self.BASE_URL}/senate-trading"
        params = {"apikey": self.api_key}

        if symbol:
            params["symbol"] = symbol

        try:
            response = self.session.get(url, params=params, timeout=30)
            response.raise_for_status()
            trades = response.json()

            # Mark as Senate
            for trade in trades:
                trade['_chamber'] = 'senate'

            return trades
        except requests.RequestException as e:
            logger.error(f"FMP Senate API error: {e}")
            return []

    def _fetch_house_trades(self, symbol, from_date, to_date):
        """Fetch from House endpoint."""
        url = f"{self.BASE_URL}/senate-disclosure"  # Note: confusing name
        params = {"apikey": self.api_key}

        if symbol:
            params["symbol"] = symbol

        try:
            response = self.session.get(url, params=params, timeout=30)
            response.raise_for_status()
            trades = response.json()

            # Mark as House
            for trade in trades:
                trade['_chamber'] = 'house'

            return trades
        except requests.RequestException as e:
            logger.error(f"FMP House API error: {e}")
            return []

    def normalize_trade(self, raw_trade: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalize FMP trade format.

        FMP Format:
        {
            "firstName": "Nancy",
            "lastName": "Pelosi",
            "office": "House",
            "link": "...",
            "dateRecieved": "2024-02-01",
            "transactionDate": "2024-01-15",
            "ticker": "AAPL",
            "assetDescription": "Apple Inc.",
            "type": "Purchase",  # or "Sale"
            "amount": "$1,001 - $15,000",
            "representative": "Hon. Nancy Pelosi",
            "district": "CA-11"
        }
        """
        # Parse amount
        amount_low, amount_high = self._parse_amount(raw_trade.get('amount', ''))

        # Normalize type
        tx_type = self._normalize_type(raw_trade.get('type', ''))

        # Build member name
        first = raw_trade.get('firstName', '')
        last = raw_trade.get('lastName', '')
        member_name = f"{first} {last}".strip() or raw_trade.get('representative')

        # Parse dates
        trade_date = self._parse_date(raw_trade.get('transactionDate'))
        disclosure_date = self._parse_date(raw_trade.get('dateRecieved'))

        # Determine chamber
        chamber = raw_trade.get('_chamber', 'unknown')

        return {
            'source': 'financial_modeling_prep',
            'member_name': member_name,
            'member_id': None,
            'ticker': raw_trade.get('ticker', '').upper(),
            'asset_description': raw_trade.get('assetDescription'),
            'transaction_type': tx_type,
            'trade_date': trade_date,
            'disclosure_date': disclosure_date,
            'amount_low': amount_low,
            'amount_high': amount_high,
            'owner': self._determine_owner(raw_trade),
            'chamber': chamber,
            'district': raw_trade.get('district'),
            'link': raw_trade.get('link'),
            'raw': raw_trade,
        }

    def is_available(self) -> bool:
        """Check if FMP is configured."""
        return bool(self.api_key)

    def get_rate_limit_info(self) -> Dict[str, Any]:
        """FMP rate limit info."""
        return {
            'source': 'financial_modeling_prep',
            'free_tier': '250 requests per day',
            'rate_limit': '250/day',
            'recommendation': 'Use sparingly, cache results',
        }

    def _parse_amount(self, amount_str: str) -> tuple[float, float]:
        """Parse amount range."""
        # Implementation...
        pass

    def _normalize_type(self, type_str: str) -> str:
        """Normalize transaction type."""
        # Implementation...
        pass

    def _parse_date(self, date_str: str) -> Optional[date]:
        """Parse date string."""
        # Implementation...
        pass

    def _determine_owner(self, raw_trade: Dict) -> str:
        """Determine owner from trade data."""
        # Implementation...
        pass
```

---

## Phase 3: Configuration Updates

### 3.1 Update app/config.py

```python
# Add new configuration options

class Config:
    # ... existing config ...

    # Data Source Configuration
    DATA_SOURCE_PRIMARY: str = os.getenv(
        "DATA_SOURCE_PRIMARY", "house_stock_watcher"
    )  # Options: house_stock_watcher, fmp

    DATA_SOURCE_SECONDARY: Optional[str] = os.getenv(
        "DATA_SOURCE_SECONDARY", "fmp"
    )  # Optional fallback/verification source

    DATA_SOURCE_STRATEGY: str = os.getenv(
        "DATA_SOURCE_STRATEGY", "primary_only"
    )  # Options: primary_only, fallback, all, verify

    # FMP API Key (optional, only needed if using FMP)
    FMP_API_KEY: Optional[str] = os.getenv("FMP_API_KEY", None)

    # Data verification settings
    ENABLE_CROSS_VERIFICATION: bool = (
        os.getenv("ENABLE_CROSS_VERIFICATION", "false").lower() == "true"
    )

    VERIFICATION_MIN_SOURCES: int = int(
        os.getenv("VERIFICATION_MIN_SOURCES", "2")
    )
```

### 3.2 Update .env.example

```bash
# Data Source Configuration
DATA_SOURCE_PRIMARY=house_stock_watcher  # Options: house_stock_watcher, fmp
DATA_SOURCE_SECONDARY=fmp                # Optional fallback/verification
DATA_SOURCE_STRATEGY=primary_only        # primary_only, fallback, all, verify

# Financial Modeling Prep API (optional)
FMP_API_KEY=                             # Get from https://site.financialmodelingprep.com/

# Cross-verification (optional)
ENABLE_CROSS_VERIFICATION=false          # Set to true for dual-source verification
VERIFICATION_MIN_SOURCES=2               # Require agreement from N sources
```

---

## Phase 4: Database Updates

### 4.1 Add Source Tracking to Database

**Update:** `app/db.py` schema initialization

```python
# Add to congress_trade_events table
def init_schema(self):
    # ... existing tables ...

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS congress_trade_events (
            event_id TEXT PRIMARY KEY,
            source TEXT NOT NULL,              -- NEW: 'house_stock_watcher', 'fmp', etc.
            verified BOOLEAN DEFAULT 0,        -- NEW: Cross-verified flag
            verification_sources TEXT,         -- NEW: JSON array of sources

            -- Existing fields
            ticker TEXT NOT NULL,
            member_name TEXT,
            member_id TEXT,
            owner TEXT,
            transaction_type TEXT NOT NULL,
            trade_date TEXT,
            disclosure_date TEXT,
            amount_low REAL,
            amount_high REAL,
            amount_mid REAL,
            delay_days INTEGER,
            currency TEXT DEFAULT 'USD',
            raw TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

            -- Indexes
            INDEX idx_ticker (ticker),
            INDEX idx_trade_date (trade_date),
            INDEX idx_source (source),
            INDEX idx_verified (verified)
        )
    """)
```

### 4.2 Add Verification Tracking Table

```python
def init_schema(self):
    # ... existing tables ...

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS data_source_verification (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_date TEXT NOT NULL,
            strategy TEXT NOT NULL,
            sources_used TEXT NOT NULL,      -- JSON array
            total_trades INTEGER NOT NULL,
            verified_trades INTEGER NOT NULL,
            discrepancies INTEGER NOT NULL,
            discrepancy_details TEXT,        -- JSON
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)
```

---

## Phase 5: Update Ingestion Pipeline

### 5.1 Refactor app/ingest.py

```python
from typing import Dict, Any, Optional
from datetime import date

from app.config import config
from app.data_sources.manager import DataSourceManager, SourceStrategy
from app.data_sources.house_stock_watcher import HouseStockWatcherClient
from app.data_sources.fmp import FMPClient
from app.db import db
from app.logging import get_logger
from app.models import CongressTradeEvent

logger = get_logger(__name__)


def get_data_source_manager() -> DataSourceManager:
    """
    Create DataSourceManager based on configuration.
    """
    sources = []

    # Initialize sources based on config
    primary = config.DATA_SOURCE_PRIMARY
    secondary = config.DATA_SOURCE_SECONDARY

    if primary == "house_stock_watcher":
        sources.append(HouseStockWatcherClient())
    elif primary == "fmp":
        sources.append(FMPClient())

    if secondary and secondary != primary:
        if secondary == "house_stock_watcher":
            sources.append(HouseStockWatcherClient())
        elif secondary == "fmp":
            sources.append(FMPClient())

    # Map strategy string to enum
    strategy_map = {
        "primary_only": SourceStrategy.PRIMARY_ONLY,
        "fallback": SourceStrategy.PRIMARY_WITH_FALLBACK,
        "all": SourceStrategy.ALL_SOURCES,
        "verify": SourceStrategy.CROSS_VERIFY,
    }
    strategy = strategy_map.get(
        config.DATA_SOURCE_STRATEGY,
        SourceStrategy.PRIMARY_ONLY
    )

    return DataSourceManager(sources=sources, strategy=strategy)


def run_ingestion(
    symbol: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Run data ingestion from configured sources.

    Returns summary of ingestion results.
    """
    logger.info("Starting data ingestion")

    try:
        # Get manager
        manager = get_data_source_manager()

        # Parse dates if provided
        from_date_obj = date.fromisoformat(from_date) if from_date else None
        to_date_obj = date.fromisoformat(to_date) if to_date else None

        # Fetch trades
        result = manager.fetch_trades(
            symbol=symbol,
            from_date=from_date_obj,
            to_date=to_date_obj,
        )

        # Process and store trades
        new_events = 0
        duplicates = 0
        errors = []

        for trade in result['trades']:
            try:
                # Create event from normalized trade
                event = CongressTradeEvent(**trade)

                # Check if already exists
                if db.event_exists(event.event_id):
                    duplicates += 1
                else:
                    db.insert_event(event)
                    new_events += 1

            except Exception as e:
                logger.error(f"Error processing trade: {e}")
                errors.append(str(e))

        # Log verification results if applicable
        if 'verification' in result:
            verification = result['verification']
            db.log_verification_run(verification)
            logger.info(f"Verification: {verification}")

        return {
            'status': result['status'],
            'fetched': len(result['trades']),
            'new_events': new_events,
            'duplicates': duplicates,
            'errors': len(errors),
            'sources_used': result['sources_used'],
            'verification': result.get('verification'),
        }

    except Exception as e:
        logger.error(f"Ingestion failed: {e}", exc_info=True)
        return {
            'status': 'failed',
            'error': str(e),
        }
```

---

## Phase 6: Usage Patterns

### 6.1 Scenario 1: Start Simple (HSW Only)

**.env Configuration:**
```bash
DATA_SOURCE_PRIMARY=house_stock_watcher
DATA_SOURCE_STRATEGY=primary_only
# No FMP_API_KEY needed
```

**Usage:**
- Quick MVP start
- No API key registration
- Free and simple
- House trades only

---

### 6.2 Scenario 2: Add FMP Fallback

**.env Configuration:**
```bash
DATA_SOURCE_PRIMARY=house_stock_watcher
DATA_SOURCE_SECONDARY=fmp
DATA_SOURCE_STRATEGY=fallback
FMP_API_KEY=your_key_here
```

**Usage:**
- Try HSW first
- If HSW fails, use FMP
- Reliability improvement
- Get both House and Senate from FMP

---

### 6.3 Scenario 3: Cross-Verification (Your Choice)

**.env Configuration:**
```bash
DATA_SOURCE_PRIMARY=house_stock_watcher
DATA_SOURCE_SECONDARY=fmp
DATA_SOURCE_STRATEGY=verify
FMP_API_KEY=your_key_here
ENABLE_CROSS_VERIFICATION=true
VERIFICATION_MIN_SOURCES=2
```

**Usage:**
- Fetch from both sources
- Compare results
- Flag verified trades
- Log discrepancies
- Higher confidence in data

**Verification Report Example:**
```python
{
    'total_trades': 150,
    'verified_trades': 145,  # Found in both sources
    'source_only_trades': {
        'house_stock_watcher': 3,  # Only in HSW
        'fmp': 2,                   # Only in FMP
    },
    'discrepancies': [
        {
            'ticker': 'AAPL',
            'member': 'Nancy Pelosi',
            'issue': 'amount_mismatch',
            'sources': {
                'hsw': {'amount': '$15,001-$50,000'},
                'fmp': {'amount': '$50,001-$100,000'}
            }
        }
    ]
}
```

---

## Phase 7: Testing Strategy

### 7.1 Unit Tests

**Test Files:**
- `tests/test_data_sources/test_hsw_client.py`
- `tests/test_data_sources/test_fmp_client.py`
- `tests/test_data_sources/test_manager.py`

**Key Tests:**
- Source availability checking
- Data normalization
- Filtering logic
- Error handling
- Rate limit awareness

### 7.2 Integration Tests

**Test Scenarios:**
- Fetch from HSW (real API call)
- Fetch from FMP (mocked)
- Cross-verification logic
- Fallback behavior
- All strategies

---

## Phase 8: Documentation Updates

### 8.1 Update CLAUDE.md

**OLD:**
```markdown
1) fetches US Congress trade disclosures from Finnhub (free tier),
```

**NEW:**
```markdown
1) fetches US Congress trade disclosures from:
   - House Stock Watcher API (free, House trades only)
   - Financial Modeling Prep API (free tier available, House + Senate)
   Configurable with fallback and cross-verification support.
```

### 8.2 Update README.md

Add new sections:
- Data Sources configuration
- Cross-verification setup
- Rate limits and best practices
- Troubleshooting for each source

---

## Timeline & Milestones

### Milestone 1: Foundation (Day 1)
- ✅ Create base classes and interfaces
- ✅ Set up project structure
- ✅ Update configuration

### Milestone 2: HSW Implementation (Day 1-2)
- ✅ Implement HSW client
- ✅ Test HSW client with real API
- ✅ Verify data normalization

### Milestone 3: FMP Implementation (Day 2)
- ✅ Implement FMP client
- ✅ Test with mock data (if no API key)
- ✅ Verify data normalization

### Milestone 4: Manager & Strategies (Day 2-3)
- ✅ Implement DataSourceManager
- ✅ Implement all strategies
- ✅ Add cross-verification logic

### Milestone 5: Integration (Day 3)
- ✅ Update ingest.py
- ✅ Update database schema
- ✅ Test end-to-end flow

### Milestone 6: Testing & Docs (Day 3-4)
- ✅ Write unit tests
- ✅ Write integration tests
- ✅ Update documentation
- ✅ Update CLAUDE.md

---

## Rate Limit Management (Your Use Case)

**Your Pattern:** Few times per day

**Recommendation for "few times per day":**

### Configuration A: Simple & Reliable
```bash
DATA_SOURCE_PRIMARY=house_stock_watcher
DATA_SOURCE_STRATEGY=primary_only
```

**Reasoning:**
- HSW has no published rate limits
- Free and simple
- Perfect for low-frequency polling
- No API key management

### Configuration B: More Complete Data
```bash
DATA_SOURCE_PRIMARY=fmp
DATA_SOURCE_STRATEGY=primary_only
FMP_API_KEY=your_key
```

**Reasoning:**
- FMP free tier: 250 requests/day
- "Few times per day" = 3-5 runs
- Plenty of headroom (5 runs = 2% of limit)
- Get both House AND Senate

### Configuration C: Maximum Confidence (Recommended)
```bash
DATA_SOURCE_PRIMARY=house_stock_watcher
DATA_SOURCE_SECONDARY=fmp
DATA_SOURCE_STRATEGY=verify
FMP_API_KEY=your_key
ENABLE_CROSS_VERIFICATION=true
```

**Reasoning:**
- Best of both worlds
- Cross-verification catches data issues
- Still well within rate limits
- Highest confidence for trading decisions

**Rate Limit Math:**
- 3 times/day × 1 HSW call = 3 calls (no limit)
- 3 times/day × 2 FMP calls = 6 calls (2.4% of 250 limit)
- **Total:** Well within limits

---

## Risk Analysis & Mitigation

### Risk 1: HSW API Goes Down
**Mitigation:** Use fallback strategy with FMP

### Risk 2: FMP Rate Limit Hit
**Mitigation:**
- Cache results for 6-8 hours
- Use primary_only with HSW
- Monitor usage

### Risk 3: Data Discrepancies
**Mitigation:**
- Cross-verification strategy
- Log all discrepancies
- Manual review process

### Risk 4: Source Data Quality
**Mitigation:**
- Both sources use official STOCK Act data
- Cross-verification catches errors
- Audit trail in database

---

## Success Metrics

1. **Data Coverage**
   - Target: >95% of official trades captured
   - Measure: Compare with Capitol Trades website

2. **Data Accuracy**
   - Target: >99% accuracy on verified trades
   - Measure: Manual spot checks

3. **Reliability**
   - Target: <1% failed ingestion runs
   - Measure: Monitor logs

4. **Performance**
   - Target: <30s per ingestion run
   - Measure: Log execution time

---

## Decision Points

### Decision 1: Start with HSW or FMP?

**Recommendation:** Start with HSW
- ✅ No API key needed
- ✅ Faster to test
- ✅ Can add FMP later
- ❌ House only (but sufficient for MVP)

### Decision 2: Which strategy for production?

**Recommendation:** Cross-verification (verify)
- Given your low frequency (few times/day)
- Rate limits not a concern
- Maximum confidence for trading
- Catches data quality issues

### Decision 3: Should I get FMP API key now?

**Recommendation:** Yes, get free tier
- Takes 2 minutes to register
- Free tier sufficient
- Enables Senate data
- Enables cross-verification
- No cost, lots of benefits

---

## Next Steps

**Ready to implement?** Let me know and I'll:

1. ✅ Create all the source files
2. ✅ Implement HSW client
3. ✅ Implement FMP client (with your API key when ready)
4. ✅ Implement DataSourceManager with all strategies
5. ✅ Update configuration
6. ✅ Update database schema
7. ✅ Update ingest.py
8. ✅ Write tests
9. ✅ Update documentation

**Estimated Time:** 2-3 hours of development + testing

Would you like me to proceed with the implementation?
