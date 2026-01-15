#!/usr/bin/env python3
"""
Test RapidAPI Politician Trade Tracker API

API Key: 1faaecd8e4msh50673e7d9ebfdf4p1e7f70jsn3d98ade81d85
Host: politician-trade-tracker1.p.rapidapi.com

This script tests the API endpoints to understand the data structure.
"""

import json
import httpx
from typing import Dict, Any

# API Configuration
RAPIDAPI_KEY = "1faaecd8e4msh50673e7d9ebfdf4p1e7f70jsn3d98ade81d85"
RAPIDAPI_HOST = "politician-trade-tracker1.p.rapidapi.com"
BASE_URL = f"https://{RAPIDAPI_HOST}"

HEADERS = {
    "x-rapidapi-host": RAPIDAPI_HOST,
    "x-rapidapi-key": RAPIDAPI_KEY,
}


def test_get_profile(name: str = "Nancy Pelosi") -> Dict[str, Any]:
    """
    Test the /get_profile endpoint.

    Args:
        name: Politician name

    Returns:
        API response data
    """
    print(f"\n{'='*80}")
    print(f"TEST 1: GET PROFILE - {name}")
    print(f"{'='*80}")

    url = f"{BASE_URL}/get_profile"
    params = {"name": name}

    print(f"URL: {url}")
    print(f"Params: {params}")
    print(f"Headers: {HEADERS}")

    try:
        response = httpx.get(url, params=params, headers=HEADERS, timeout=30)
        print(f"\nStatus Code: {response.status_code}")

        if response.status_code == 200:
            data = response.json()
            print(f"\n✅ SUCCESS - Response data:")
            print(json.dumps(data, indent=2))
            return data
        else:
            print(f"\n❌ FAILED - Response:")
            print(response.text)
            return {}

    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        return {}


def test_get_politicians() -> Dict[str, Any]:
    """
    Test the /get_politicians endpoint.

    Returns:
        API response data
    """
    print(f"\n{'='*80}")
    print(f"TEST 2: GET POLITICIANS LIST")
    print(f"{'='*80}")

    url = f"{BASE_URL}/get_politicians"

    print(f"URL: {url}")
    print(f"Headers: {HEADERS}")

    try:
        response = httpx.get(url, headers=HEADERS, timeout=30)
        print(f"\nStatus Code: {response.status_code}")

        if response.status_code == 200:
            data = response.json()
            print(f"\n✅ SUCCESS - Response data:")

            # If it's a dict of politicians, show first 5
            if isinstance(data, dict):
                print(f"Total politicians: {len(data)}")
                print(f"\nFirst 5 politicians:")
                for i, (name, info) in enumerate(list(data.items())[:5]):
                    print(f"\n{i+1}. {name}")
                    print(f"   {json.dumps(info, indent=6)}")
            else:
                print(json.dumps(data, indent=2))

            return data
        else:
            print(f"\n❌ FAILED - Response:")
            print(response.text)
            return {}

    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        return {}


def test_trades_endpoint() -> Dict[str, Any]:
    """
    Test potential trades endpoint (guessing based on common API patterns).

    Returns:
        API response data
    """
    print(f"\n{'='*80}")
    print(f"TEST 3: EXPLORE TRADES ENDPOINT (if exists)")
    print(f"{'='*80}")

    # Try various possible endpoints
    possible_endpoints = [
        "/get_trades",
        "/trades",
        "/get_recent_trades",
        "/politician_trades",
    ]

    for endpoint in possible_endpoints:
        url = f"{BASE_URL}{endpoint}"
        print(f"\nTrying: {url}")

        try:
            response = httpx.get(url, headers=HEADERS, timeout=10)
            print(f"Status: {response.status_code}")

            if response.status_code == 200:
                data = response.json()
                print(f"✅ FOUND WORKING ENDPOINT: {endpoint}")
                print(json.dumps(data, indent=2))
                return data
            elif response.status_code == 404:
                print("❌ Not found")
            else:
                print(f"Response: {response.text[:200]}")

        except Exception as e:
            print(f"Error: {e}")

    return {}


def test_profile_with_parameters(name: str = "Nancy Pelosi") -> Dict[str, Any]:
    """
    Test /get_profile with different query parameters to find trades.

    Args:
        name: Politician name

    Returns:
        API response data
    """
    print(f"\n{'='*80}")
    print(f"TEST 4: GET PROFILE WITH VARIOUS PARAMETERS")
    print(f"{'='*80}")

    url = f"{BASE_URL}/get_profile"

    # Try different parameter combinations
    param_sets = [
        {"name": name},
        {"name": name, "include_trades": "true"},
        {"name": name, "trades": "true"},
        {"name": name, "limit": "10"},
    ]

    for params in param_sets:
        print(f"\n--- Testing params: {params} ---")

        try:
            response = httpx.get(url, params=params, headers=HEADERS, timeout=10)
            print(f"Status: {response.status_code}")

            if response.status_code == 200:
                data = response.json()

                # Check if response has trades data
                if isinstance(data, dict):
                    print(f"Keys in response: {list(data.keys())}")

                    # Look for trade-related keys
                    for key in data.keys():
                        if any(word in key.lower() for word in ['trade', 'transaction', 'stock', 'ticker']):
                            print(f"\n🎯 Found trade-related key: {key}")
                            print(json.dumps(data[key], indent=2))

                print(json.dumps(data, indent=2)[:500] + "...")

        except Exception as e:
            print(f"Error: {e}")

    return {}


def analyze_data_structure():
    """
    Run all tests and analyze the data structure.
    """
    print(f"\n{'#'*80}")
    print(f"# RAPIDAPI POLITICIAN TRADE TRACKER - API TESTING")
    print(f"# API Key: {RAPIDAPI_KEY[:20]}...")
    print(f"{'#'*80}")

    # Test 1: Get profile for Nancy Pelosi
    profile_data = test_get_profile("Nancy Pelosi")

    # Test 2: Get all politicians
    politicians_data = test_get_politicians()

    # Test 3: Try to find trades endpoint
    trades_data = test_trades_endpoint()

    # Test 4: Try profile with different parameters
    test_profile_with_parameters("Nancy Pelosi")

    # Test with another politician
    test_get_profile("Kevin McCarthy")

    print(f"\n{'='*80}")
    print(f"TESTING COMPLETE")
    print(f"{'='*80}")

    # Summary
    print(f"\n📊 SUMMARY:")
    print(f"  - Profile endpoint working: {bool(profile_data)}")
    print(f"  - Politicians endpoint working: {bool(politicians_data)}")
    print(f"  - Trades endpoint found: {bool(trades_data)}")

    if profile_data:
        print(f"\n📋 Profile data keys:")
        if isinstance(profile_data, dict):
            for key in profile_data.keys():
                print(f"     - {key}")

    if politicians_data:
        print(f"\n👥 Politicians available: {len(politicians_data) if isinstance(politicians_data, dict) else 'unknown'}")


if __name__ == "__main__":
    analyze_data_structure()
