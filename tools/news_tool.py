"""Aggregated news fetcher across multiple sources."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import List, Optional

from config.logging import logger
from models.schemas import NewsItem
from tools.playwright_scraper import scrape_chinese_news
from tools.polygon_tool import PolygonClient
from tools.yfinance_tool import YFinanceClient


def _parse_polygon_published(raw: Optional[str]) -> Optional[datetime]:
    """Round-3 fix R3-3: Polygon's news payload includes ``published_utc``
    (ISO-8601, e.g. ``2026-04-01T13:30:00Z``) but the previous
    ``_polygon_as_newsitems`` mapping silently dropped it, so every
    Polygon-sourced ``NewsItem`` had ``published_at=None`` and any
    time-window filter (recency ranking, "last 24h" digest) excluded all
    Polygon items. Parse the field tolerantly — accept both ``Z`` and
    ``+00:00`` suffixes and fall back to ``None`` on malformed input.
    """
    if not raw:
        return None
    if not isinstance(raw, str):
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


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
                    published_at=_parse_polygon_published(n.get("published_utc")),
                )
            )
        return items
