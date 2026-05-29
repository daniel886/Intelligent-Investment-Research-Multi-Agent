"""Alpha Vantage REST wrapper (async)."""
from __future__ import annotations

from typing import Any, Dict, Optional

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from config import settings
from config.logging import logger
from tools.rate_limiter import AsyncRateLimiter


class AlphaVantageClient:
    """Async Alpha Vantage client – key endpoints only."""

    BASE_URL = "https://www.alphavantage.co/query"

    def __init__(self, api_key: Optional[str] = None) -> None:
        self.api_key = api_key or settings.alpha_vantage_key
        # Free tier = 5 req/min
        self._limiter = AsyncRateLimiter(max_calls=5, period=60.0)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
    async def _get(self, params: Dict[str, Any]) -> Dict[str, Any]:
        if not self.api_key:
            raise RuntimeError("ALPHA_VANTAGE_KEY missing")
        params = {**params, "apikey": self.api_key}
        await self._limiter.acquire()
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(self.BASE_URL, params=params)
            resp.raise_for_status()
            data = resp.json()
        # Round-3 fix R3-4: AlphaVantage's free tier returns HTTP 200 with a
        # ``{"Note": ...}`` or ``{"Information": ...}`` envelope when the
        # 5-req/min cap is exceeded. Previously this envelope was passed
        # through as if it were valid data, so callers (overview / news /
        # daily) silently saw "empty" responses instead of triggering the
        # tenacity retry. Detect the envelope and raise so retry fires; if
        # we are still throttled after the final attempt, the existing
        # ``except Exception`` in the public methods downgrades it to ``{}``
        # which is the same shape the tests already expect.
        if isinstance(data, dict):
            note = data.get("Note") or data.get("Information")
            if note and len(data) == 1:
                raise RuntimeError(f"AlphaVantage throttled: {note}")
        return data

    async def get_company_overview(self, symbol: str) -> Dict[str, Any]:
        try:
            return await self._get({"function": "OVERVIEW", "symbol": symbol})
        except Exception as e:  # noqa: BLE001
            logger.warning("AlphaVantage OVERVIEW failed for {}: {}", symbol, e)
            return {}

    async def get_news_sentiment(self, symbol: str) -> Dict[str, Any]:
        try:
            return await self._get(
                {"function": "NEWS_SENTIMENT", "tickers": symbol, "limit": 20}
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("AlphaVantage NEWS_SENTIMENT failed for {}: {}", symbol, e)
            return {}

    async def get_daily(self, symbol: str) -> Dict[str, Any]:
        try:
            return await self._get(
                {"function": "TIME_SERIES_DAILY", "symbol": symbol, "outputsize": "compact"}
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("AlphaVantage TIME_SERIES_DAILY failed for {}: {}", symbol, e)
            return {}
