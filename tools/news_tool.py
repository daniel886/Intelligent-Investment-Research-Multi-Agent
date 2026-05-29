"""Aggregated news fetcher across multiple sources."""
from __future__ import annotations

import asyncio
from typing import List

from config.logging import logger
from models.schemas import NewsItem
from tools.playwright_scraper import scrape_chinese_news
from tools.polygon_tool import PolygonClient
from tools.yfinance_tool import YFinanceClient


class NewsAggregator:
    """Aggregates news from yfinance, polygon and Chinese scrapers."""

    def __init__(self) -> None:
        self.yf = YFinanceClient()
        self.polygon = PolygonClient()

    async def fetch_all(self, symbol: str, limit: int = 12) -> List[NewsItem]:
        tasks = [
            self.yf.get_news(symbol, limit=limit),
            self._polygon_as_newsitems(symbol, limit),
            scrape_chinese_news(symbol, limit=8),
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        items: List[NewsItem] = []
        seen = set()
        for r in results:
            if isinstance(r, list):
                for n in r:
                    key = (n.title or "").strip().lower()
                    if key and key not in seen:
                        seen.add(key)
                        items.append(n)
        logger.info("Fetched {} news items for {}", len(items), symbol)
        return items[:limit]

    async def _polygon_as_newsitems(self, symbol: str, limit: int) -> List[NewsItem]:
        raw = await self.polygon.get_news(symbol, limit=limit)
        items: List[NewsItem] = []
        for n in raw or []:
            items.append(
                NewsItem(
                    title=n.get("title", ""),
                    url=n.get("article_url"),
                    source=n.get("publisher", {}).get("name") if isinstance(n.get("publisher"), dict) else None,
                    summary=n.get("description"),
                )
            )
        return items
