"""Finnhub API client for congressional trades."""
from __future__ import annotations

import logging
from typing import Any

import requests


class FinnhubClient:
    def __init__(self, api_key: str) -> None:
        self.api_key = api_key
        self.base_url = "https://finnhub.io/api/v1"
        self._logger = logging.getLogger(__name__)

    def fetch_congress_trades(self) -> list[dict[str, Any]]:
        if not self.api_key:
            self._logger.warning("FINNHUB_API_KEY missing; returning empty list")
            return []
        url = f"{self.base_url}/stock/congressional-trading"
        response = requests.get(url, params={"token": self.api_key}, timeout=30)
        response.raise_for_status()
        payload = response.json()
        if isinstance(payload, list):
            return payload
        return payload.get("data", [])
