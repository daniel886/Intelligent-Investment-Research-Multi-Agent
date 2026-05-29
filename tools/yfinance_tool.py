"""yfinance wrapper – multi-market quotes & fundamentals (US/HK/A股/Crypto)."""
from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any, Dict, List, Optional

import pandas as pd
import yfinance as yf

from config.logging import logger
from models.schemas import FundamentalSnapshot, Market, NewsItem, PriceBar


def _to_market(symbol: str) -> Market:
    s = symbol.upper()
    if s.endswith(".HK") or s.endswith(".HKG"):
        return Market.HK
    if s.endswith(".SS") or s.endswith(".SZ") or s.endswith(".SH"):
        return Market.A_SHARE
    if "-USD" in s or "USDT" in s or s in {"BTC", "ETH"}:
        return Market.CRYPTO
    if s.isdigit() and len(s) == 6:
        return Market.A_SHARE
    return Market.US


def _normalize_symbol(symbol: str) -> str:
    """Normalize Chinese A-share / HK conventions for yfinance."""
    s = symbol.strip().upper()
    if s.isdigit() and len(s) == 6:
        return f"{s}.SS" if s.startswith(("6", "9")) else f"{s}.SZ"
    if s.isdigit() and len(s) == 5:
        return f"{s}.HK"
    return s


class YFinanceClient:
    """Synchronous yfinance methods exposed via asyncio.to_thread."""

    async def get_fundamentals(self, symbol: str) -> FundamentalSnapshot:
        norm = _normalize_symbol(symbol)
        try:
            info: Dict[str, Any] = await asyncio.to_thread(self._info_safe, norm)
        except Exception as e:  # noqa: BLE001
            logger.warning("yfinance info failed for {}: {}", symbol, e)
            info = {}
        return FundamentalSnapshot(
            symbol=symbol,
            name=info.get("longName") or info.get("shortName"),
            market=_to_market(norm),
            market_cap=info.get("marketCap"),
            pe_ratio=info.get("trailingPE"),
            pb_ratio=info.get("priceToBook"),
            eps=info.get("trailingEps"),
            revenue=info.get("totalRevenue"),
            revenue_growth=info.get("revenueGrowth"),
            net_income=info.get("netIncomeToCommon"),
            profit_margin=info.get("profitMargins"),
            debt_to_equity=info.get("debtToEquity"),
            roe=info.get("returnOnEquity"),
            dividend_yield=info.get("dividendYield"),
            sector=info.get("sector"),
            industry=info.get("industry"),
            summary=info.get("longBusinessSummary"),
        )

    @staticmethod
    def _info_safe(symbol: str) -> Dict[str, Any]:
        ticker = yf.Ticker(symbol)
        try:
            return dict(ticker.info or {})
        except Exception:  # noqa: BLE001
            return {}

    async def get_history(self, symbol: str, period: str = "6mo", interval: str = "1d") -> List[PriceBar]:
        norm = _normalize_symbol(symbol)

        def _hist() -> pd.DataFrame:
            return yf.Ticker(norm).history(period=period, interval=interval, auto_adjust=True)

        try:
            df = await asyncio.to_thread(_hist)
        except Exception as e:  # noqa: BLE001
            logger.warning("yfinance history failed for {}: {}", symbol, e)
            return []

        bars: List[PriceBar] = []
        if df is None or df.empty:
            return bars
        for ts, row in df.iterrows():
            bars.append(
                PriceBar(
                    timestamp=ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else datetime.utcnow(),
                    open=float(row["Open"]),
                    high=float(row["High"]),
                    low=float(row["Low"]),
                    close=float(row["Close"]),
                    volume=float(row.get("Volume", 0) or 0),
                )
            )
        return bars

    async def get_news(self, symbol: str, limit: int = 8) -> List[NewsItem]:
        norm = _normalize_symbol(symbol)

        def _news() -> List[Dict[str, Any]]:
            try:
                return yf.Ticker(norm).news or []
            except Exception:  # noqa: BLE001
                return []

        raw = await asyncio.to_thread(_news)
        items: List[NewsItem] = []
        for n in raw[:limit]:
            published = n.get("providerPublishTime")
            items.append(
                NewsItem(
                    title=n.get("title", ""),
                    url=n.get("link"),
                    source=n.get("publisher"),
                    published_at=(
                        datetime.utcfromtimestamp(published) if published else None
                    ),
                    summary=n.get("summary"),
                )
            )
        return items
