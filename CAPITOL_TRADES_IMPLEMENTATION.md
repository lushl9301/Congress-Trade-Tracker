# CapitolTrades Data Source - Implementation Guide

## Overview

**CapitolTrades.com** (https://www.capitoltrades.com/trades) is a popular aggregator of congressional trading data. They scrape official STOCK Act disclosures and present them in a clean, searchable format.

This guide explains how to integrate CapitolTrades as a third data source for your Congress Trade Tracker.

---

## Data Source Comparison

### Current Sources

| Feature | House Stock Watcher (HSW) | Financial Modeling Prep (FMP) | CapitolTrades (CT) |
|---------|--------------------------|-------------------------------|-------------------|
| **Cost** | Free | Free (250/day) or $29/month | Free (web scraping) |
| **API** | ✅ JSON (S3 bucket) | ✅ REST API | ❌ No official API |
| **Auth** | None | API key | None |
| **Coverage** | House only | House + Senate | House + Senate |
| **Rate Limit** | ~250/day | 250/day (free) or higher (paid) | Self-imposed (~50/day) |
| **Data Format** | JSON | JSON | HTML (requires scraping) |
| **Freshness** | Daily updates | Daily updates | Daily updates |
| **Implementation** | ✅ Complete | ✅ Complete | ⚠️  Requires scraping |
| **Recent Data** | All trades | All trades | ~500 recent (2-3 weeks) |

### Why Add CapitolTrades?

**Pros**:
- ✅ **Aggregated data**: Combines House + Senate in one place
- ✅ **No API key required**: Public data, no registration
- ✅ **High-quality data**: Well-maintained, clean format
- ✅ **Additional context**: Includes politician info (chamber, party, district)
- ✅ **Third source for verification**: Cross-check HSW and FMP data

**Cons**:
- ❌ **Requires web scraping**: No official API
- ❌ **Implementation complexity**: Needs Playwright/Selenium
- ❌ **Maintenance burden**: HTML structure may change
- ❌ **Rate limiting concerns**: Must be respectful of their servers
- ❌ **Limited historical data**: Only ~500 recent trades by default

### Recommendation

**For most users**: Stick with **HSW + FMP**
- No scraping complexity
- Official APIs
- Better for production

**Add CapitolTrades if**:
- You want maximum data coverage (third source verification)
- You're comfortable with web scraping
- You want FMP data but haven't purchased the paid tier yet
- You need the aggregated House + Senate view

---

## Implementation Options

### Option 1: Use congress-cli Library (EASIEST)

**Recommended for most users**

The `congress-cli` tool by austron24 already handles the scraping complexity.

#### Install

```bash
pip install congress-cli
# Install Playwright for web scraping
python -m playwright install chromium
```

#### Usage in Your Code

```python
import subprocess
import json

def fetch_via_congress_cli(limit=500):
    """Fetch trades using congress-cli as subprocess."""
    result = subprocess.run(
        ['congress', 'trades', '--format', 'json', '--limit', str(limit)],
        capture_output=True,
        text=True
    )

    if result.returncode == 0:
        return json.loads(result.stdout)
    else:
        raise RuntimeError(f"congress-cli failed: {result.stderr}")

# Example
trades = fetch_via_congress_cli(limit=100)
```

#### Pros
- ✅ Maintained by someone else
- ✅ Handles HTML parsing
- ✅ Implements caching
- ✅ Respects rate limits

#### Cons
- ❌ External dependency
- ❌ CLI overhead (subprocess calls)
- ❌ Less control over caching strategy

---

### Option 2: Implement Direct Scraping with Playwright (FLEXIBLE)

**Recommended if you want full control**

#### Install

```bash
pip install playwright beautifulsoup4 lxml
python -m playwright install chromium
```

#### Implementation

```python
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
import time

class CapitolTradesScraper:
    def __init__(self):
        self.base_url = "https://www.capitoltrades.com/trades"

    def fetch_trades(self, limit=500):
        """Fetch trades using Playwright."""
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()

            # Visit trades page
            page.goto(self.base_url)

            # Wait for trades to load
            page.wait_for_selector('.trade-row', timeout=10000)

            # Scroll to load more (if needed)
            for _ in range(5):  # Load ~500 trades
                page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
                time.sleep(1)  # Wait for lazy loading

            # Get HTML
            html = page.content()
            browser.close()

        # Parse HTML
        soup = BeautifulSoup(html, 'lxml')
        trades = []

        for trade_element in soup.select('.trade-row'):
            trade = {
                'politician': trade_element.select_one('.politician-name').text,
                'ticker': trade_element.select_one('.ticker').text,
                'transaction_type': trade_element.select_one('.transaction-type').text,
                'amount': trade_element.select_one('.amount').text,
                # ... parse other fields
            }
            trades.append(trade)

        return trades[:limit]
```

#### Pros
- ✅ Full control over scraping logic
- ✅ Custom caching strategy
- ✅ Better error handling
- ✅ Can be optimized for your needs

#### Cons
- ❌ More code to maintain
- ❌ HTML structure may change (requires updates)
- ❌ Must handle edge cases yourself

---

### Option 3: Use Requests + BeautifulSoup (SIMPLEST, MAY NOT WORK)

**Only if the site doesn't require JavaScript**

```bash
pip install requests beautifulsoup4 lxml
```

**Note**: CapitolTrades likely requires JavaScript, so this may not work. Worth trying first for simplicity.

```python
import requests
from bs4 import BeautifulSoup

def fetch_simple():
    response = requests.get('https://www.capitoltrades.com/trades')
    soup = BeautifulSoup(response.text, 'lxml')
    # Parse trades...
    return trades
```

---

## Integration Steps

### Step 1: Choose Implementation Method

Pick one of the options above based on your needs.

### Step 2: Update CapitolTradesSource

Edit `app/data_sources/capitol_trades.py`:

```python
def get_trades(self, symbol=None, from_date=None, to_date=None):
    """Fetch trades from CapitolTrades."""

    # Option 1: Use congress-cli
    from congress_cli import fetch_trades  # If using as library
    raw_trades = fetch_trades(limit=500)

    # Option 2: Use Playwright (implement fetch_via_playwright)
    # raw_trades = self._fetch_via_playwright(limit=500)

    # Option 3: Use requests (if it works)
    # raw_trades = self._fetch_via_requests(limit=500)

    # Filter by symbol/dates if needed
    filtered = self._apply_filters(raw_trades, symbol, from_date, to_date)

    # Cache results
    if self.use_cache:
        self._cache_trades(filtered)

    return filtered
```

### Step 3: Test the Implementation

```python
from app.data_sources import CapitolTradesSource

ct = CapitolTradesSource()
trades = ct.get_trades(limit=10)  # Fetch 10 trades

for trade in trades:
    normalized = ct.normalize_trade(trade)
    print(f"{normalized['ticker']} - {normalized['transaction_type']}")
```

### Step 4: Enable in Configuration

```bash
# .env
CT_ENABLED=true
CT_USE_CACHE=true
```

### Step 5: Test Multi-Source Integration

```bash
python -m app.run ingest
```

Expected output:
```
Initializing House Stock Watcher source
Initializing Financial Modeling Prep source
Initializing CapitolTrades source
Initializing DataSourceManager with 3 sources, strategy=verify

Fetched 150 trades from house_stock_watcher
Fetched 50 trades from financial_modeling_prep
Fetched 100 trades from capitol_trades

Cross-verifying data from 3 sources
Verification complete: 180 trades, 140 verified (77.8%)
```

---

## Ethical Scraping Guidelines

### Rate Limiting

```python
class CapitolTradesScraper:
    MIN_REQUEST_DELAY = 3  # seconds
    MAX_REQUESTS_PER_HOUR = 20

    def _enforce_rate_limit(self):
        """Enforce rate limiting between requests."""
        if self.last_request_time:
            elapsed = time.time() - self.last_request_time
            if elapsed < self.MIN_REQUEST_DELAY:
                time.sleep(self.MIN_REQUEST_DELAY - elapsed)
        self.last_request_time = time.time()
```

### Caching

```python
# Cache for 1 hour (following congress-cli pattern)
CACHE_TTL = 3600

def _is_cache_fresh(self, cache_time):
    return (time.time() - cache_time) < CACHE_TTL
```

### User-Agent

```python
headers = {
    'User-Agent': 'Congress-Trade-Tracker/1.0 (Educational; +github.com/yourrepo)'
}
```

### Robots.txt Compliance

Check https://www.capitoltrades.com/robots.txt before implementing.

### Consider Supporting CapitolTrades

If you use their data heavily, consider:
- Donating to support their work
- Following their rate limits
- Caching aggressively
- Using their RSS feed if available

---

## Testing

### Unit Test

```python
def test_capitol_trades_scraping():
    """Test CapitolTrades scraping."""
    ct = CapitolTradesSource()

    # Test fetching
    trades = ct.get_trades(limit=10)
    assert len(trades) > 0

    # Test normalization
    normalized = ct.normalize_trade(trades[0])
    assert 'ticker' in normalized
    assert 'transaction_type' in normalized
    assert normalized['source'] == 'capitol_trades'
```

### Integration Test

```python
def test_three_source_verification():
    """Test cross-verification with all 3 sources."""
    from app.ingest import CongressTradeIngester

    ingester = CongressTradeIngester()
    result = ingester.ingest_latest()

    # Should have data from 3 sources
    assert result['status'] == 'success'
    assert result['fetched'] > 0

    # Check verification rate
    verification_pct = result['verified'] / result['fetched']
    assert verification_pct > 0.5  # Expect >50% verified with 3 sources
```

---

## Troubleshooting

### Issue: "403 Forbidden" error

**Cause**: CapitolTrades blocking your requests

**Solutions**:
1. Use proper User-Agent header
2. Add delays between requests (3+ seconds)
3. Use Playwright (looks more like real browser)
4. Rotate User-Agent strings

### Issue: HTML parsing fails

**Cause**: CapitolTrades changed their HTML structure

**Solutions**:
1. Inspect the page source
2. Update CSS selectors
3. Add fallback selectors
4. Consider using congress-cli (they maintain selectors)

### Issue: Slow performance

**Cause**: Playwright/browser overhead

**Solutions**:
1. Enable caching (1-hour TTL)
2. Use headless mode: `browser.launch(headless=True)`
3. Fetch in batches, cache results
4. Consider background job for fetching

### Issue: congress-cli not found

**Cause**: Not installed or not in PATH

**Solution**:
```bash
pip install congress-cli
# Or if using venv:
source venv/bin/activate && pip install congress-cli
```

---

## Comparison: congress-cli vs Direct Scraping

| Aspect | congress-cli | Direct Scraping |
|--------|-------------|-----------------|
| **Ease of Use** | ⭐⭐⭐⭐⭐ Very easy | ⭐⭐⭐ Moderate |
| **Control** | ⭐⭐ Limited | ⭐⭐⭐⭐⭐ Full control |
| **Maintenance** | ⭐⭐⭐⭐⭐ Maintained by others | ⭐⭐ You maintain |
| **Performance** | ⭐⭐⭐ Subprocess overhead | ⭐⭐⭐⭐ Direct calls |
| **Caching** | ⭐⭐⭐⭐ Built-in | ⭐⭐⭐⭐⭐ Custom |
| **Reliability** | ⭐⭐⭐⭐ Well-tested | ⭐⭐⭐ Depends on implementation |

**Recommendation**: Start with `congress-cli`, switch to direct scraping if you need more control.

---

## Migration Path

### Phase 1: Add CapitolTrades (Optional)
- Implement using congress-cli
- Test with HSW + FMP + CT
- Monitor verification rates

### Phase 2: Consider FMP Paid Tier
- If verification rate is high with CT
- If you want official API instead of scraping
- $29/month gets you:
  - Higher rate limits
  - Faster response times
  - Official support

### Phase 3: Optimize for Your Needs
- Keep the sources that work best for you
- Disable sources you don't need
- Fine-tune verification strategy

---

## Recommended Configuration

### For Maximum Data Quality (3 sources)
```bash
HSW_ENABLED=true
FMP_ENABLED=true  # Paid tier recommended
CT_ENABLED=true   # Use congress-cli
DATA_SOURCE_STRATEGY=verify
```

### For Free Tier (2 sources)
```bash
HSW_ENABLED=true
FMP_ENABLED=true  # Free tier
CT_ENABLED=false  # Optional: enable if you implement scraping
DATA_SOURCE_STRATEGY=verify
```

### For Simplicity (1 source)
```bash
HSW_ENABLED=true
FMP_ENABLED=false
CT_ENABLED=false
DATA_SOURCE_STRATEGY=primary_only
```

---

## Example: Complete Implementation

See `app/data_sources/capitol_trades.py` for the complete placeholder implementation.

To make it functional, replace the `get_trades` method with one of:

1. **congress-cli integration** (recommended)
2. **Playwright scraping** (more control)
3. **Requests + BeautifulSoup** (if it works)

---

## Summary

✅ **CapitolTrades is a great third source** for verification
✅ **congress-cli makes it easy** to implement
✅ **HSW + FMP already work great** - CT is optional
✅ **Consider FMP paid tier** ($29/month) instead of scraping
✅ **Scraping requires maintenance** - weigh the trade-offs

**Status**: Placeholder implementation ready, full scraping requires:
- congress-cli installation OR
- Playwright implementation OR
- Alternative scraping method

---

**Questions?** See `MULTI_SOURCE_IMPLEMENTATION.md` for overall architecture details.

**Ready to implement?** Choose an option above and update `app/data_sources/capitol_trades.py`.
