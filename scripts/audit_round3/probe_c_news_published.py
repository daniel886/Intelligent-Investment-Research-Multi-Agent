"""Probe C: NewsAggregator drops Polygon's `published_utc` field.

tools/news_tool.py:_polygon_as_newsitems builds NewsItem(title, url, source,
summary) but ignores the `published_utc` field that Polygon sends. This makes
time-windowed queries impossible for Polygon-sourced news.
"""
from __future__ import annotations
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))


async def main() -> int:
    from tools.news_tool import NewsAggregator

    agg = NewsAggregator()

    # Stub the Polygon client so we don't touch the network.
    async def fake_get_news(symbol, limit=10):
        return [
            {
                "title": "Apple beats earnings",
                "article_url": "https://example.com/a",
                "publisher": {"name": "Reuters"},
                "description": "Q4 results above guidance.",
                "published_utc": "2026-04-01T13:30:00Z",
            },
            {
                "title": "Apple unveils Vision Pro 2",
                "article_url": "https://example.com/b",
                "publisher": {"name": "Bloomberg"},
                "description": None,
                "published_utc": "2026-04-02T09:00:00Z",
            },
        ]

    agg.polygon.get_news = fake_get_news  # type: ignore[assignment]
    items = await agg._polygon_as_newsitems("AAPL", 10)
    print(f"[probe_c_news_published] items={items}")
    missing = [i for i in items if i.published_at is None]
    if len(missing) == len(items) and items:
        print(
            "[probe_c_news_published] CONFIRMED: all "
            f"{len(items)} items have published_at=None (published_utc dropped)"
        )
        return 1
    print("[probe_c_news_published] OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
