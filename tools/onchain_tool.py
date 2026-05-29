"""Lightweight on-chain crypto data via CoinGecko (no key needed)."""
from __future__ import annotations

from typing import Any, Dict, Optional

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from config import settings
from config.logging import logger


class CoinGeckoClient:
    BASE_URL = "https://api.coingecko.com/api/v3"

    def __init__(self, api_key: Optional[str] = None) -> None:
        self.api_key = api_key or settings.coingecko_api_key

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
    async def _get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        params = dict(params or {})
        if self.api_key:
            params["x_cg_demo_api_key"] = self.api_key
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(f"{self.BASE_URL}{path}", params=params)
            resp.raise_for_status()
            return resp.json()

    async def get_coin(self, coin_id: str) -> Dict[str, Any]:
        try:
            return await self._get(f"/coins/{coin_id}", {"localization": "false"})
        except Exception as e:  # noqa: BLE001
            logger.warning("CoinGecko fetch failed for {}: {}", coin_id, e)
            return {}

    async def get_market_chart(self, coin_id: str, days: int = 90) -> Dict[str, Any]:
        try:
            return await self._get(
                f"/coins/{coin_id}/market_chart",
                {"vs_currency": "usd", "days": days, "interval": "daily"},
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("CoinGecko chart failed for {}: {}", coin_id, e)
            return {}
