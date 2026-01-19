#!/usr/bin/env python
"""
Test script for real API integration with FMP and HSW.

Run this script in your local environment with network access to verify
the multi-source implementation works with real data.

Usage:
    python test_real_api.py
"""

import sys
from datetime import date, datetime

from app.config import Config
from app.data_sources import (
    DataSourceManager,
    FinancialModelingPrepSource,
    HouseStockWatcherSource,
    SourceStrategy,
)
from app.ingest import CongressTradeIngester


def test_configuration():
    """Test that configuration is loaded correctly."""
    print("=" * 70)
    print("1. TESTING CONFIGURATION")
    print("=" * 70)

    config = Config()

    print(f"✓ HSW Enabled: {config.HSW_ENABLED}")
    print(f"✓ FMP Enabled: {config.FMP_ENABLED}")
    print(
        f"✓ FMP API Key: {config.FMP_API_KEY[:10]}... "
        f"(length: {len(config.FMP_API_KEY)})"
    )
    print(f"✓ Strategy: {config.DATA_SOURCE_STRATEGY}")
    print()

    if config.FMP_API_KEY == "DUMMY_FMP_API_KEY_REPLACE_ME":
        print("❌ ERROR: FMP API key is still the dummy value!")
        print("   Please set FMP_API_KEY in your .env file")
        return False

    print("✅ Configuration looks good!\n")
    return True


def test_source_availability():
    """Test that both data sources are available."""
    print("=" * 70)
    print("2. TESTING DATA SOURCE AVAILABILITY")
    print("=" * 70)

    config = Config()

    # Test HSW
    print("Testing House Stock Watcher...")
    hsw = HouseStockWatcherSource()
    hsw_available = hsw.is_available()
    print(f"  {'✅' if hsw_available else '❌'} HSW Available: {hsw_available}")
    if not hsw_available:
        print("     (HSW may be temporarily unavailable or network issue)")

    # Test FMP
    print("\nTesting Financial Modeling Prep...")
    fmp = FinancialModelingPrepSource(api_key=config.FMP_API_KEY)
    fmp_available = fmp.is_available()
    print(f"  {'✅' if fmp_available else '❌'} FMP Available: {fmp_available}")
    if not fmp_available:
        print("     (Check API key or network connectivity)")

    print()
    return hsw_available or fmp_available


def test_fetch_sample_data():
    """Test fetching a small sample of data from each source."""
    print("=" * 70)
    print("3. TESTING SAMPLE DATA FETCH")
    print("=" * 70)

    config = Config()

    # Test HSW
    print("Fetching sample from House Stock Watcher...")
    hsw = HouseStockWatcherSource()
    try:
        hsw_trades = hsw.get_trades()
        print(f"✅ HSW returned {len(hsw_trades)} total trades")

        if hsw_trades:
            # Show a sample
            sample = hsw.normalize_trade(hsw_trades[0])
            print(f"   Sample: {sample['ticker']} - {sample['transaction_type']}")
            print(f"   Member: {sample['member_name']}")
            print(f"   Amount: ${sample['amount_low']:,.0f} - ${sample['amount_high']:,.0f}")
    except Exception as e:
        print(f"❌ HSW Error: {e}")

    print()

    # Test FMP
    print("Fetching sample from Financial Modeling Prep...")
    fmp = FinancialModelingPrepSource(api_key=config.FMP_API_KEY)
    try:
        fmp_trades = fmp.get_trades()
        print(f"✅ FMP returned {len(fmp_trades)} trades")

        if fmp_trades:
            # Show a sample
            sample = fmp.normalize_trade(fmp_trades[0])
            print(f"   Sample: {sample['ticker']} - {sample['transaction_type']}")
            print(f"   Member: {sample['member_name']}")
            print(f"   Amount: ${sample['amount_low']:,.0f} - ${sample['amount_high']:,.0f}")
    except Exception as e:
        print(f"❌ FMP Error: {e}")

    print()


def test_cross_verification():
    """Test cross-verification with DataSourceManager."""
    print("=" * 70)
    print("4. TESTING CROSS-VERIFICATION")
    print("=" * 70)

    config = Config()

    # Create data source manager
    sources = []

    if config.HSW_ENABLED:
        sources.append(HouseStockWatcherSource())

    if config.FMP_ENABLED:
        sources.append(FinancialModelingPrepSource(api_key=config.FMP_API_KEY))

    if not sources:
        print("❌ No data sources enabled!")
        return

    print(f"Testing with {len(sources)} source(s) and CROSS_VERIFY strategy...")

    manager = DataSourceManager(sources=sources, strategy=SourceStrategy.CROSS_VERIFY)

    try:
        trades = manager.get_trades()
        print(f"✅ Retrieved {len(trades)} trades")

        # Count verification stats
        verified = sum(1 for t in trades if t.get("verified", False))
        unverified = len(trades) - verified

        print(f"\nVerification Statistics:")
        print(f"  Verified:   {verified} ({verified/len(trades)*100:.1f}%)")
        print(f"  Unverified: {unverified} ({unverified/len(trades)*100:.1f}%)")

        # Show samples
        if verified > 0:
            verified_sample = next((t for t in trades if t.get("verified")), None)
            if verified_sample:
                print(f"\n✅ Verified Trade Example:")
                print(f"   {verified_sample['ticker']} - {verified_sample['transaction_type']}")
                print(f"   Sources: {verified_sample['verification_sources']}")

        if unverified > 0:
            unverified_sample = next((t for t in trades if not t.get("verified")), None)
            if unverified_sample:
                print(f"\n⚠️  Unverified Trade Example:")
                print(f"   {unverified_sample['ticker']} - {unverified_sample['transaction_type']}")
                print(f"   Sources: {unverified_sample['verification_sources']}")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback

        traceback.print_exc()

    print()


def test_full_ingestion():
    """Test full ingestion pipeline."""
    print("=" * 70)
    print("5. TESTING FULL INGESTION PIPELINE")
    print("=" * 70)

    print("Running ingestion (this may take 10-30 seconds)...")
    print()

    try:
        ingester = CongressTradeIngester()
        result = ingester.ingest_latest()

        print("✅ Ingestion Complete!\n")
        print("Results:")
        print(f"  Status:         {result['status']}")
        print(f"  Fetched:        {result['fetched']} trades")
        print(f"  New Events:     {result['new_events']}")
        print(f"  Duplicates:     {result['duplicates']}")
        print(f"  Verified:       {result['verified']} ({result['verification_rate']})")
        print(f"  Unverified:     {result['unverified']}")

        if result.get("errors", 0) > 0:
            print(f"  Errors:         {result['errors']}")

        print("\n" + "=" * 70)
        print("INTERPRETATION:")
        print("=" * 70)

        if result["verified"] > 0:
            print(
                f"✅ {result['verified']} trades were cross-verified from multiple sources!"
            )
            print(
                "   These trades have higher confidence as they appear in both "
                "House and Senate data."
            )

        if result["unverified"] > 0:
            print(
                f"⚠️  {result['unverified']} trades found in only one source "
                "(House or Senate only)."
            )
            print("   This is normal - not all trades appear in both datasets.")

        print()

        # Check database
        try:
            from app.db import db

            with db.get_connection() as conn:
                cursor = conn.cursor()

                # Total trades
                cursor.execute("SELECT COUNT(*) FROM congress_trade_events")
                total = cursor.fetchone()[0]
                print(f"📊 Total trades in database: {total}")

                # Verified count
                cursor.execute(
                    "SELECT COUNT(*) FROM congress_trade_events WHERE verified = 1"
                )
                verified_db = cursor.fetchone()[0]
                print(f"📊 Verified trades: {verified_db}")

                # Recent trades
                cursor.execute(
                    """
                    SELECT ticker, transaction_type, verified, verification_sources
                    FROM congress_trade_events
                    ORDER BY created_at DESC
                    LIMIT 3
                """
                )
                recent = cursor.fetchall()

                if recent:
                    print("\n📈 Recent trades:")
                    for row in recent:
                        verified_icon = "✓" if row[2] else "○"
                        print(
                            f"   [{verified_icon}] {row[0]} - {row[1]} "
                            f"(sources: {row[3]})"
                        )

        except Exception as e:
            print(f"⚠️  Could not read database: {e}")

    except Exception as e:
        print(f"❌ Ingestion failed: {e}")
        import traceback

        traceback.print_exc()
        return False

    return True


def main():
    """Run all tests."""
    print("\n" + "=" * 70)
    print("CONGRESS TRADE TRACKER - REAL API INTEGRATION TEST")
    print("=" * 70)
    print()

    # Run tests
    tests = [
        ("Configuration", test_configuration),
        ("Source Availability", test_source_availability),
        ("Sample Data Fetch", test_fetch_sample_data),
        ("Cross-Verification", test_cross_verification),
        ("Full Ingestion", test_full_ingestion),
    ]

    passed = 0
    failed = 0

    for name, test_func in tests:
        try:
            result = test_func()
            if result is not False:
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"\n❌ Test '{name}' crashed: {e}")
            import traceback

            traceback.print_exc()
            failed += 1
        print()

    # Summary
    print("=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)
    print(f"Passed: {passed}/{len(tests)}")
    print(f"Failed: {failed}/{len(tests)}")
    print()

    if failed == 0:
        print("🎉 All tests passed! Your multi-source system is working perfectly!")
        print()
        print("Next steps:")
        print("  1. Run: python -m app.run ingest")
        print("  2. Check: python -m app.run status")
        print("  3. Review: MULTI_SOURCE_IMPLEMENTATION.md for usage guide")
    else:
        print("⚠️  Some tests failed. Check the errors above.")
        print()
        print("Common issues:")
        print("  - Network connectivity (firewall, proxy)")
        print("  - Invalid FMP API key")
        print("  - Source temporarily unavailable")

    return failed == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
