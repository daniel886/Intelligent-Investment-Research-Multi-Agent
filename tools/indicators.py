"""Technical indicator helpers using pandas / `ta`."""
from __future__ import annotations

from typing import List, Optional, Tuple

import pandas as pd

from models.schemas import PriceBar, TechnicalSnapshot


def bars_to_df(bars: List[PriceBar]) -> pd.DataFrame:
    if not bars:
        return pd.DataFrame()
    df = pd.DataFrame([b.model_dump() for b in bars])
    # Round-2 fix #1 (tools/indicators.py:15): pandas 2.x raises
    # `ValueError: Cannot mix tz-aware with tz-naive values` when a Series mixes
    # both kinds of datetimes. Mixed sources (yfinance returns tz-aware UTC, while
    # AlphaVantage/CoinGecko emit tz-naive strings) routinely trigger this.
    # Coerce everything to tz-aware UTC, then drop tzinfo so downstream pandas/ta
    # operations behave identically regardless of upstream source.
    ts = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
    df["timestamp"] = ts.dt.tz_convert("UTC").dt.tz_localize(None)
    df = df.dropna(subset=["timestamp"])
    df = df.sort_values("timestamp").set_index("timestamp")
    return df


def compute_indicators(symbol: str, bars: List[PriceBar]) -> Optional[TechnicalSnapshot]:
    df = bars_to_df(bars)
    if df.empty or len(df) < 20:
        return None
    close = df["close"].astype(float)
    sma20 = close.rolling(20).mean().iloc[-1]
    sma50 = close.rolling(50).mean().iloc[-1] if len(df) >= 50 else None
    sma200 = close.rolling(200).mean().iloc[-1] if len(df) >= 200 else None

    # RSI
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = -delta.clip(upper=0).rolling(14).mean()
    rs = gain / loss.replace(0, 1e-9)
    rsi = (100 - 100 / (1 + rs)).iloc[-1]

    # MACD
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd_line = (ema12 - ema26).iloc[-1]
    signal_line = (ema12 - ema26).ewm(span=9, adjust=False).mean().iloc[-1]

    # Bollinger
    bb_mid = close.rolling(20).mean()
    bb_std = close.rolling(20).std()
    bb_upper = (bb_mid + 2 * bb_std).iloc[-1]
    bb_lower = (bb_mid - 2 * bb_std).iloc[-1]

    last_price = float(close.iloc[-1])
    prev_price = float(close.iloc[-2]) if len(close) > 1 else last_price
    change_pct = ((last_price - prev_price) / prev_price * 100) if prev_price else 0.0

    signals: List[str] = []
    trend = "sideways"
    if sma50 is not None and last_price > sma50:
        trend = "up"
        signals.append("价格站上 50 日均线，中期趋势偏多")
    elif sma50 is not None and last_price < sma50:
        trend = "down"
        signals.append("价格跌破 50 日均线，中期趋势偏空")

    if pd.notna(rsi):
        if rsi > 70:
            signals.append(f"RSI={rsi:.1f}，处于超买区间，警惕回调")
        elif rsi < 30:
            signals.append(f"RSI={rsi:.1f}，处于超卖区间，关注反弹机会")

    if pd.notna(macd_line) and pd.notna(signal_line):
        if macd_line > signal_line:
            signals.append("MACD 金叉形成，动量偏多")
        else:
            signals.append("MACD 死叉形成，动量偏空")

    return TechnicalSnapshot(
        symbol=symbol,
        last_price=last_price,
        change_pct=float(change_pct),
        sma_20=float(sma20) if pd.notna(sma20) else None,
        sma_50=float(sma50) if sma50 is not None and pd.notna(sma50) else None,
        sma_200=float(sma200) if sma200 is not None and pd.notna(sma200) else None,
        rsi_14=float(rsi) if pd.notna(rsi) else None,
        macd=float(macd_line) if pd.notna(macd_line) else None,
        macd_signal=float(signal_line) if pd.notna(signal_line) else None,
        bb_upper=float(bb_upper) if pd.notna(bb_upper) else None,
        bb_lower=float(bb_lower) if pd.notna(bb_lower) else None,
        volume_avg=float(df["volume"].rolling(20).mean().iloc[-1]) if "volume" in df else None,
        trend=trend,
        signals=signals,
    )


def compute_risk_metrics(bars: List[PriceBar]) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    """Returns (volatility%, max_drawdown%, var_95%)."""
    df = bars_to_df(bars)
    if df.empty or len(df) < 20:
        return None, None, None
    close = df["close"].astype(float)
    returns = close.pct_change().dropna()
    volatility = float(returns.std() * (252 ** 0.5) * 100)
    cum = (1 + returns).cumprod()
    rolling_max = cum.cummax()
    drawdown = (cum / rolling_max - 1.0).min()
    max_drawdown = float(drawdown * 100)
    var_95 = float(returns.quantile(0.05) * 100)
    return volatility, max_drawdown, var_95
