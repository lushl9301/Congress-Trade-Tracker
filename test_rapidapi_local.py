#!/usr/bin/env python3
"""
RapidAPI Politician Trade Tracker - Local Testing Script

⚠️  RUN THIS ON YOUR LOCAL MACHINE (not in sandbox)

This script tests the RapidAPI Politician Trade Tracker to determine:
1. If the API key is subscribed and working
2. What data the API returns
3. If it's suitable as a 4th data source for our system

API Details:
- Host: politician-trade-tracker1.p.rapidapi.com
- Key: 1faaecd8e4msh50673e7d9ebfdf4p1e7f70jsn3d98ade81d85
- Docs: https://rapidapi.com/s5yux/api/politician-trade-tracker1

Prerequisites:
    pip install httpx
"""

import json
import sys
from typing import Dict, Any, List, Optional
from datetime import datetime

try:
    import httpx
except ImportError:
    print("❌ ERROR: httpx not installed")
    print("Install it with: pip install httpx")
    sys.exit(1)

# API Configuration
RAPIDAPI_KEY = "1faaecd8e4msh50673e7d9ebfdf4p1e7f70jsn3d98ade81d85"
RAPIDAPI_HOST = "politician-trade-tracker1.p.rapidapi.com"
BASE_URL = f"https://{RAPIDAPI_HOST}"

HEADERS = {
    "x-rapidapi-host": RAPIDAPI_HOST,
    "x-rapidapi-key": RAPIDAPI_KEY,
}


def print_section(title: str):
    """Print a formatted section header."""
    print(f"\n{'='*80}")
    print(f"  {title}")
    print(f"{'='*80}\n")


def print_success(message: str):
    """Print success message."""
    print(f"✅ {message}")


def print_error(message: str):
    """Print error message."""
    print(f"❌ {message}")


def print_info(message: str):
    """Print info message."""
    print(f"ℹ️  {message}")


def test_subscription_status() -> bool:
    """
    Test if the API key is subscribed to the service.

    Returns:
        True if subscribed and working, False otherwise
    """
    print_section("TEST 1: Subscription & Authentication Check")

    url = f"{BASE_URL}/get_politicians"

    print(f"Endpoint: {url}")
    print(f"API Key: {RAPIDAPI_KEY[:20]}...{RAPIDAPI_KEY[-10:]}")

    try:
        response = httpx.get(url, headers=HEADERS, timeout=30)

        print(f"\nHTTP Status: {response.status_code}")

        if response.status_code == 200:
            print_success("API key is valid and subscribed!")
            return True
        elif response.status_code == 403:
            print_error("403 Forbidden - Possible reasons:")
            print("   1. API key not subscribed to this API on RapidAPI")
            print("   2. Free tier limit exceeded")
            print("   3. API requires paid subscription")
            print("\n   ACTION REQUIRED:")
            print("   → Visit https://rapidapi.com/s5yux/api/politician-trade-tracker1")
            print("   → Click 'Subscribe to Test' or 'Subscribe'")
            print("   → Choose a pricing plan (check if free tier exists)")
            return False
        elif response.status_code == 401:
            print_error("401 Unauthorized - API key is invalid")
            return False
        elif response.status_code == 429:
            print_error("429 Too Many Requests - Rate limit exceeded")
            return False
        else:
            print_error(f"Unexpected status code: {response.status_code}")
            print(f"Response: {response.text}")
            return False

    except httpx.ConnectError as e:
        print_error(f"Connection failed: {e}")
        print_info("Check your internet connection")
        return False
    except Exception as e:
        print_error(f"Unexpected error: {e}")
        return False


def test_get_politicians() -> Optional[Dict[str, Any]]:
    """
    Test the /get_politicians endpoint.

    Returns:
        Dictionary of politicians if successful, None otherwise
    """
    print_section("TEST 2: Get Politicians List")

    url = f"{BASE_URL}/get_politicians"

    print(f"Endpoint: {url}\n")

    try:
        response = httpx.get(url, headers=HEADERS, timeout=30)

        if response.status_code == 200:
            data = response.json()
            print_success(f"Retrieved politicians data")

            if isinstance(data, dict):
                print(f"\n📊 Total politicians: {len(data)}")

                print("\n👥 Sample politicians:")
                for i, (name, info) in enumerate(list(data.items())[:5]):
                    print(f"\n  {i+1}. {name}")
                    if isinstance(info, dict):
                        for key, value in info.items():
                            print(f"     • {key}: {value}")

                # Save to file
                with open("rapidapi_politicians.json", "w") as f:
                    json.dump(data, f, indent=2)
                print_info("Full data saved to: rapidapi_politicians.json")

                return data
            else:
                print_info(f"Data type: {type(data)}")
                print(json.dumps(data, indent=2)[:500])
                return data

        else:
            print_error(f"Request failed with status {response.status_code}")
            print(f"Response: {response.text}")
            return None

    except Exception as e:
        print_error(f"Error: {e}")
        return None


def test_get_profile(name: str = "Nancy Pelosi") -> Optional[Dict[str, Any]]:
    """
    Test the /get_profile endpoint.

    Args:
        name: Politician name

    Returns:
        Profile data if successful, None otherwise
    """
    print_section(f"TEST 3: Get Profile - {name}")

    url = f"{BASE_URL}/get_profile"
    params = {"name": name}

    print(f"Endpoint: {url}")
    print(f"Params: {params}\n")

    try:
        response = httpx.get(url, params=params, headers=HEADERS, timeout=30)

        if response.status_code == 200:
            data = response.json()
            print_success(f"Retrieved profile for {name}")

            print("\n📋 Profile data:")
            print(json.dumps(data, indent=2))

            # Check for trade-related fields
            trade_fields = []
            if isinstance(data, dict):
                for key in data.keys():
                    if any(word in key.lower() for word in
                           ['trade', 'transaction', 'stock', 'ticker', 'buy', 'sell']):
                        trade_fields.append(key)

            if trade_fields:
                print_success(f"Found trade-related fields: {trade_fields}")
            else:
                print_info("No obvious trade fields in profile response")
                print_info("This endpoint may only return politician metadata")

            # Save to file
            filename = f"rapidapi_profile_{name.replace(' ', '_')}.json"
            with open(filename, "w") as f:
                json.dump(data, f, indent=2)
            print_info(f"Data saved to: {filename}")

            return data

        else:
            print_error(f"Request failed with status {response.status_code}")
            print(f"Response: {response.text}")
            return None

    except Exception as e:
        print_error(f"Error: {e}")
        return None


def explore_endpoints() -> Dict[str, bool]:
    """
    Try to discover available endpoints.

    Returns:
        Dictionary mapping endpoint names to availability
    """
    print_section("TEST 4: Endpoint Discovery")

    endpoints_to_test = [
        # Based on common congressional trading API patterns
        "/get_trades",
        "/trades",
        "/recent_trades",
        "/get_recent_trades",
        "/politician_trades",
        "/get_politician_trades",
        "/congressional_trades",
        "/stock_trades",
        "/transactions",
        "/get_transactions",
        # With politician parameter
        ("/get_trades", {"politician": "Nancy Pelosi"}),
        ("/trades", {"name": "Nancy Pelosi"}),
        ("/recent_trades", {"limit": "10"}),
    ]

    results = {}

    for endpoint_info in endpoints_to_test:
        if isinstance(endpoint_info, tuple):
            endpoint, params = endpoint_info
            url = f"{BASE_URL}{endpoint}"
            print(f"\nTrying: {endpoint} with params {params}")
        else:
            endpoint = endpoint_info
            params = {}
            url = f"{BASE_URL}{endpoint}"
            print(f"\nTrying: {endpoint}")

        try:
            response = httpx.get(url, params=params, headers=HEADERS, timeout=10)

            if response.status_code == 200:
                print_success(f"FOUND: {endpoint} - Status 200")
                results[endpoint] = True

                # Try to parse response
                try:
                    data = response.json()
                    print(f"Response preview: {json.dumps(data, indent=2)[:300]}")
                except:
                    print(f"Response text: {response.text[:200]}")

            elif response.status_code == 404:
                print(f"   Status 404 - Not found")
                results[endpoint] = False
            else:
                print(f"   Status {response.status_code}")
                results[endpoint] = False

        except Exception as e:
            print(f"   Error: {e}")
            results[endpoint] = False

    # Summary
    working_endpoints = [ep for ep, working in results.items() if working]
    if working_endpoints:
        print_success(f"\n✨ Working endpoints found: {working_endpoints}")
    else:
        print_info("\nNo additional endpoints discovered")

    return results


def analyze_for_integration(politicians_data: Optional[Dict], profile_data: Optional[Dict]):
    """
    Analyze API responses to determine integration feasibility.

    Args:
        politicians_data: Response from /get_politicians
        profile_data: Response from /get_profile
    """
    print_section("TEST 5: Integration Feasibility Analysis")

    print("Analyzing API for suitability as a 4th data source...\n")

    # Check 1: Does it provide trade data?
    has_trades = False
    trade_source = None

    if profile_data:
        if isinstance(profile_data, dict):
            # Look for trade-related keys
            for key in profile_data.keys():
                if any(word in key.lower() for word in
                       ['trade', 'transaction', 'stock', 'ticker']):
                    has_trades = True
                    trade_source = "profile endpoint"
                    break

    # Check 2: Data structure analysis
    print("📊 Data Structure Analysis:")

    if politicians_data:
        print("\n1. Politicians List (/get_politicians):")
        print(f"   ✓ Available")
        print(f"   ✓ Contains {len(politicians_data)} politicians" if isinstance(politicians_data, dict) else "   ✓ Data returned")
        print(f"   {'✓' if has_trades else '✗'} Contains trade data: {has_trades}")

    if profile_data:
        print("\n2. Profile Data (/get_profile):")
        print(f"   ✓ Available")
        if isinstance(profile_data, dict):
            print(f"   ✓ Fields: {list(profile_data.keys())}")

    # Check 3: Comparison with existing sources
    print("\n\n📈 Comparison with Existing Sources:")
    print("┌─────────────────────┬──────────┬──────────┬──────────┬─────────────┐")
    print("│ Source              │ Coverage │ API Type │ Cost     │ Trade Data  │")
    print("├─────────────────────┼──────────┼──────────┼──────────┼─────────────┤")
    print("│ House Stock Watcher │ House    │ JSON     │ Free     │ ✓ Yes       │")
    print("│ FMP                 │ H+S      │ REST     │ Free/Paid│ ✓ Yes       │")
    print("│ CapitolTrades       │ H+S      │ Scraping │ Free     │ ✓ Yes       │")
    print(f"│ RapidAPI PTT        │ ???      │ REST     │ ???      │ {'✓ Yes' if has_trades else '✗ Unknown'}       │")
    print("└─────────────────────┴──────────┴──────────┴──────────┴─────────────┘")

    # Recommendation
    print("\n\n💡 RECOMMENDATION:")

    if not has_trades:
        print("❌ NOT RECOMMENDED for integration")
        print("\nReasons:")
        print("  • No clear trade transaction data found in API responses")
        print("  • Appears to only provide politician metadata (name, state, party)")
        print("  • Would not add value for trade tracking/verification")
        print("\nSuggestion:")
        print("  • Continue with existing 3 sources (HSW + FMP + CapitolTrades)")
        print("  • These sources already provide comprehensive coverage")
    else:
        print("✅ POTENTIALLY USEFUL for integration")
        print(f"\nTrade data found in: {trade_source}")
        print("\nNext steps:")
        print("  1. Examine the trade data structure in saved JSON files")
        print("  2. Compare fields with our CongressTradeEvent model")
        print("  3. Check API rate limits and pricing")
        print("  4. Implement RapidAPISource class if data is compatible")


def main():
    """Run all tests."""
    print("\n" + "="*80)
    print("  RAPIDAPI POLITICIAN TRADE TRACKER - COMPREHENSIVE API TEST")
    print("="*80)
    print(f"\n⏰ Test started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"🔑 API Key: {RAPIDAPI_KEY[:20]}...{RAPIDAPI_KEY[-10:]}")
    print(f"🌐 Host: {RAPIDAPI_HOST}")

    # Test 1: Check subscription
    is_subscribed = test_subscription_status()

    if not is_subscribed:
        print("\n" + "="*80)
        print("⚠️  TESTS STOPPED - API Key Not Subscribed")
        print("="*80)
        print("\nYou need to subscribe to this API on RapidAPI first:")
        print("1. Visit: https://rapidapi.com/s5yux/api/politician-trade-tracker1")
        print("2. Click 'Subscribe to Test' or pricing button")
        print("3. Choose a plan (check if free tier is available)")
        print("4. Re-run this test script")
        return

    # Test 2: Get politicians list
    politicians_data = test_get_politicians()

    # Test 3: Get specific profiles
    pelosi_data = test_get_profile("Nancy Pelosi")
    mccarthy_data = test_get_profile("Kevin McCarthy")

    # Test 4: Discover endpoints
    endpoint_results = explore_endpoints()

    # Test 5: Integration analysis
    analyze_for_integration(politicians_data, pelosi_data)

    # Final summary
    print_section("TEST SUMMARY")

    print("Tests completed successfully!")
    print("\n📁 Output files generated:")
    print("   • rapidapi_politicians.json (if /get_politicians worked)")
    print("   • rapidapi_profile_*.json (if /get_profile worked)")

    print("\n📋 Next steps:")
    print("   1. Review the JSON files to understand data structure")
    print("   2. Check if trade data is present and useful")
    print("   3. Decide if integration as 4th source is worthwhile")
    print("   4. If yes, share JSON files with developer for implementation")

    print(f"\n⏰ Test completed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")


if __name__ == "__main__":
    main()
