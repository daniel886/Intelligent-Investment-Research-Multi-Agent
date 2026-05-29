"""Playwright scraper for 雪球 / 东方财富 (best-effort, gracefully degrades)."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import List, Optional

from config.logging import logger
from models.schemas import NewsItem


class XueqiuScraper:
    """Headless-Chromium scraper. Falls back to empty list on failure."""

    USER_AGENT = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    )

    async def fetch_xueqiu_news(self, symbol: str, limit: int = 8) -> List[NewsItem]:
        """Fetch news mentions for a stock from xueqiu.com."""
        try:
            from playwright.async_api import async_playwright
        except Exception as e:  # noqa: BLE001
            logger.warning("Playwright not available: {}", e)
            return []

        url = f"https://xueqiu.com/k?q={symbol}"
        items: List[NewsItem] = []
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                ctx = await browser.new_context(user_agent=self.USER_AGENT)
                page = await ctx.new_page()
                await page.goto(url, wait_until="domcontentloaded", timeout=20000)
                await page.wait_for_timeout(2000)
                # Try a couple of selectors
                anchors = await page.query_selector_all("a.status__title, a.title")
                for a in anchors[:limit]:
                    title = (await a.inner_text() or "").strip()
                    href = await a.get_attribute("href")
                    if title:
                        items.append(
                            NewsItem(
                                title=title,
                                url=f"https://xueqiu.com{href}" if href and href.startswith("/") else href,
                                source="xueqiu",
                                published_at=datetime.now(timezone.utc),
                            )
                        )
                await browser.close()
        except Exception as e:  # noqa: BLE001
            logger.warning("Xueqiu scrape failed for {}: {}", symbol, e)
        return items


class EastMoneyScraper:
    """Scrape 东方财富 / Eastmoney newsfeed."""

    USER_AGENT = XueqiuScraper.USER_AGENT

    async def fetch_eastmoney_news(self, symbol: str, limit: int = 8) -> List[NewsItem]:
        try:
            from playwright.async_api import async_playwright
        except Exception as e:  # noqa: BLE001
            logger.warning("Playwright not available: {}", e)
            return []

        # eastmoney uses {SH600000|SZ000001|HK00700|US.AAPL}
        norm = symbol.replace(".", "").upper()
        url = f"https://so.eastmoney.com/news/s?keyword={norm}"
        items: List[NewsItem] = []
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                ctx = await browser.new_context(user_agent=self.USER_AGENT)
                page = await ctx.new_page()
                await page.goto(url, wait_until="domcontentloaded", timeout=20000)
                await page.wait_for_timeout(1500)
                anchors = await page.query_selector_all("div.news_item a.title, a.news_title")
                for a in anchors[:limit]:
                    title = (await a.inner_text() or "").strip()
                    href = await a.get_attribute("href")
                    if title:
                        items.append(
                            NewsItem(
                                title=title,
                                url=href,
                                source="eastmoney",
                                published_at=datetime.now(timezone.utc),
                            )
                        )
                await browser.close()
        except Exception as e:  # noqa: BLE001
            logger.warning("Eastmoney scrape failed for {}: {}", symbol, e)
        return items


async def scrape_chinese_news(symbol: str, limit: int = 8) -> List[NewsItem]:
    """Aggregate xueqiu + eastmoney."""
    xq = XueqiuScraper()
    em = EastMoneyScraper()
    results = await asyncio.gather(
        xq.fetch_xueqiu_news(symbol, limit),
        em.fetch_eastmoney_news(symbol, limit),
        return_exceptions=True,
    )
    items: List[NewsItem] = []
    for r in results:
        if isinstance(r, list):
            items.extend(r)
    return items[: limit * 2]
