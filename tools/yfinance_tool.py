"""yfinance wrapper – multi-market quotes & fundamentals (US/HK/A股/Crypto)."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import pandas as pd
import yfinance as yf

from config.logging import logger
from models.schemas import FundamentalSnapshot, Market, NewsItem, PriceBar


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _from_unix(ts: Optional[float]) -> Optional[datetime]:
    """Robustly convert a unix timestamp (seconds OR milliseconds) to tz-aware UTC."""
    if ts is None:
        return None
    try:
        ts_f = float(ts)
    except (TypeError, ValueError):
        return None
    # Heuristic: yfinance/news APIs may emit either seconds or milliseconds.
    if ts_f > 1e12:
        ts_f = ts_f / 1000.0
    try:
        return datetime.fromtimestamp(ts_f, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None


def _row_get(row: Any, key: str, default: float = 0.0) -> float:
    """Safe field accessor for pandas Series or dict; tolerant of multi-index columns."""
    try:
        # row is typically a pd.Series
        if hasattr(row, "get"):
            val = row.get(key, None)
            if val is None and hasattr(row, "index"):
                # Multi-index columns: pick the first matching field name.
                for idx in row.index:
                    if (isinstance(idx, tuple) and key in idx) or idx == key:
                        val = row[idx]
                        break
        else:
            val = row[key]
    except Exception:  # noqa: BLE001
        val = None
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return default
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


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
            try:
                # to_pydatetime() may yield tz-aware (e.g. America/New_York) or naive;
                # normalize to tz-aware UTC for downstream consistency.
                if hasattr(ts, "to_pydatetime"):
                    py_ts = ts.to_pydatetime()
                    if py_ts.tzinfo is None:
                        py_ts = py_ts.replace(tzinfo=timezone.utc)
                    else:
                        py_ts = py_ts.astimezone(timezone.utc)
                else:
                    py_ts = _utcnow()
                close = _row_get(row, "Close")
                # Skip rows with invalid OHLC.
                if close == 0.0 and _row_get(row, "Open") == 0.0:
                    continue
                bars.append(
                    PriceBar(
                        timestamp=py_ts,
                        open=_row_get(row, "Open"),
                        high=_row_get(row, "High"),
                        low=_row_get(row, "Low"),
                        close=close,
                        volume=_row_get(row, "Volume", 0.0),
                    )
                )
            except Exception as e:  # noqa: BLE001
                logger.debug("yfinance row skipped for {}: {}", symbol, e)
                continue
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
            if not isinstance(n, dict):
                continue
            # yfinance schema drift: newer versions wrap the payload in {"content": {...}}.
            content = n.get("content") if isinstance(n.get("content"), dict) else n
            published = (
                content.get("providerPublishTime")
                or content.get("pubDate")
                or content.get("publishedAt")
                or content.get("displayTime")
            )
            published_dt = _from_unix(published) if isinstance(published, (int, float)) else None
            if published_dt is None and isinstance(published, str):
                # ISO-8601 fallback (e.g. "2025-04-15T12:30:00Z")
                try:
                    published_dt = datetime.fromisoformat(published.replace("Z", "+00:00"))
                    if published_dt.tzinfo is None:
                        published_dt = published_dt.replace(tzinfo=timezone.utc)
                except ValueError:
                    published_dt = None
            title = content.get("title") or n.get("title") or ""
            # url: prefer explicit link, fall back to canonicalUrl.url, then top-level link.
            url = content.get("link")
            if not url:
                canonical = content.get("canonicalUrl")
                if isinstance(canonical, dict):
                    url = canonical.get("url")
            if not url:
                url = n.get("link")
            # publisher: try flat field, then nested provider.displayName.
            publisher = content.get("publisher")
            if not publisher:
                provider = content.get("provider")
                if isinstance(provider, dict):
                    publisher = provider.get("displayName")
            summary = content.get("summary") or content.get("description")
            items.append(
                NewsItem(
                    title=title,
                    url=url,
                    source=publisher,
                    published_at=published_dt,
                    summary=summary,
                )
            )
        return items
