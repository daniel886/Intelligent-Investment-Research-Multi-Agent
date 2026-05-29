"""Polygon.io REST client wrapper (async)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from config import settings
from config.logging import logger
from models.schemas import PriceBar
from tools.rate_limiter import AsyncRateLimiter


class PolygonClient:
    """Lightweight async wrapper for Polygon REST endpoints."""

    BASE_URL = "https://api.polygon.io"

    def __init__(self, api_key: Optional[str] = None) -> None:
        self.api_key = api_key or settings.polygon_api_key
        self._limiter = AsyncRateLimiter(max_calls=settings.rate_limit_per_minute)

    # Round-3 fix R3-6: previously this class also defined ``async def
    # _client(self)`` returning a fresh ``httpx.AsyncClient`` — but it was
    # never invoked anywhere (every real call site constructs the client
    # inline via ``async with httpx.AsyncClient(...)``). Dead helpers like
    # this are misleading during reviews (suggests the class owns a long-
    # lived client) and inflate coverage noise. Deleted.

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
    async def _get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if not self.api_key:
            raise RuntimeError("POLYGON_API_KEY missing")
        params = dict(params or {})
        params["apiKey"] = self.api_key
        await self._limiter.acquire()
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(f"{self.BASE_URL}{path}", params=params)
            resp.raise_for_status()
            return resp.json()

    async def get_aggregates(
        self,
        symbol: str,
        multiplier: int = 1,
        timespan: str = "day",
        days: int = 120,
    ) -> List[PriceBar]:
        end = datetime.now(timezone.utc).date()
        start = end - timedelta(days=days)
        path = f"/v2/aggs/ticker/{symbol}/range/{multiplier}/{timespan}/{start}/{end}"
        try:
            data = await self._get(path, {"adjusted": "true", "sort": "asc", "limit": 5000})
        except Exception as e:  # noqa: BLE001
            logger.warning("Polygon aggregates failed for {}: {}", symbol, e)
            return []
        bars: List[PriceBar] = []
        for r in data.get("results", []) or []:
            bars.append(
                PriceBar(
                    timestamp=datetime.fromtimestamp(r["t"] / 1000, tz=timezone.utc),
                    open=float(r["o"]),
                    high=float(r["h"]),
                    low=float(r["l"]),
                    close=float(r["c"]),
                    volume=float(r.get("v", 0)),
                )
            )
        return bars

    async def get_ticker_details(self, symbol: str) -> Dict[str, Any]:
        try:
            return await self._get(f"/v3/reference/tickers/{symbol}")
        except Exception as e:  # noqa: BLE001
            logger.warning("Polygon ticker details failed for {}: {}", symbol, e)
            return {}

    async def get_news(self, symbol: str, limit: int = 10) -> List[Dict[str, Any]]:
        try:
            data = await self._get(
                "/v2/reference/news",
                {"ticker": symbol, "limit": limit, "order": "desc"},
            )
            return data.get("results", []) or []
        except Exception as e:  # noqa: BLE001
            logger.warning("Polygon news failed for {}: {}", symbol, e)
            return []
