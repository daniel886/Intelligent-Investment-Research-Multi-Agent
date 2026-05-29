"""Probe C: indicators.bars_to_df behaviour with mixed tz-aware/naive PriceBars.

Round 1's yfinance change emits tz-aware datetimes, but other sources (mocks,
older saved data) may still produce naive datetimes. pd.to_datetime on a Series
containing both raises in pandas 2.x unless utc=True is set.
"""
from __future__ import annotations
import sys
import warnings
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from models.schemas import PriceBar
from tools.indicators import bars_to_df, compute_risk_metrics


def main() -> int:
    aware = datetime(2026, 1, 1, tzinfo=timezone.utc)
    naive = datetime(2026, 1, 2)
    bars = [
        PriceBar(timestamp=aware, open=1, high=1, low=1, close=1, volume=1),
        PriceBar(timestamp=naive, open=2, high=2, low=2, close=2, volume=1),
    ]
    issues = 0
    print("[probe_c] Pydantic stored tz-info:")
    for b in bars:
        print(f"  {b.timestamp.isoformat()}  tzinfo={b.timestamp.tzinfo}")

    with warnings.catch_warnings(record=True) as warned:
        warnings.simplefilter("always")
        try:
            df = bars_to_df(bars)
            print(f"[probe_c] bars_to_df ok, dtype={df.index.dtype}")
        except Exception as e:
            print(f"[probe_c] CONFIRMED CRASH: bars_to_df raised {type(e).__name__}: {e}")
            return 1
        if warned:
            for w in warned:
                msg = f"{w.category.__name__}: {w.message}"
                print(f"[probe_c] warning: {msg}")
                if "FutureWarning" in w.category.__name__ or "Deprecat" in w.category.__name__:
                    issues = 1

    # Also verify compute_risk_metrics still works with 30 mixed-tz bars.
    bars30 = []
    for i in range(30):
        ts = datetime(2026, 1, 1, tzinfo=timezone.utc) if i % 2 == 0 else datetime(2026, 1, 2)
        bars30.append(PriceBar(timestamp=ts, open=100 + i, high=100 + i, low=99, close=100 + i, volume=10))
    try:
        v = compute_risk_metrics(bars30)
        print(f"[probe_c] compute_risk_metrics={v}")
    except Exception as e:
        print(f"[probe_c] CONFIRMED CRASH compute_risk_metrics: {type(e).__name__}: {e}")
        issues = 1

    return issues


if __name__ == "__main__":
    raise SystemExit(main())
