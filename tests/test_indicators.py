"""Indicator function tests."""
from __future__ import annotations

from datetime import datetime, timedelta

import math

from models.schemas import PriceBar
from tools.indicators import compute_indicators, compute_risk_metrics


def _gen_bars(n: int = 60) -> list[PriceBar]:
    bars: list[PriceBar] = []
    base = datetime(2024, 1, 1)
    price = 100.0
    for i in range(n):
        # Slight uptrend with noise
        price = price * (1 + 0.001 * ((-1) ** i))
        bars.append(
            PriceBar(
                timestamp=base + timedelta(days=i),
                open=price,
                high=price * 1.01,
                low=price * 0.99,
                close=price,
                volume=1000,
            )
        )
    return bars


def test_compute_indicators_returns_snapshot():
    bars = _gen_bars(80)
    snap = compute_indicators("TEST", bars)
    assert snap is not None
    assert snap.last_price > 0
    assert snap.sma_20 is not None
    assert snap.trend in {"up", "down", "sideways"}


def test_compute_risk_metrics():
    bars = _gen_bars(120)
    vol, dd, var = compute_risk_metrics(bars)
    assert vol is not None and not math.isnan(vol)
    assert dd is not None
    assert var is not None
