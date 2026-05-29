"""Probe D: AlphaVantageClient does not detect rate-limit / informational
envelopes.

When the free tier exceeds 5 req/min or 25 req/day AlphaVantage returns
HTTP 200 with one of these JSON envelopes:
  {"Note": "Thank you for using Alpha Vantage! ... API call frequency..."}
  {"Information": "We have detected your API key... 25 requests per day..."}

The current AlphaVantageClient._get returns the JSON as-is, so callers receive
a successful-looking dict and treat it as data. Symptom: silent loss of every
overview / time-series fetch once the quota is hit.
"""
from __future__ import annotations
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))


async def main() -> int:
    from tools.alpha_vantage_tool import AlphaVantageClient

    client = AlphaVantageClient(api_key="dummy")

    rate_envelopes = [
        {"Note": "Thank you for using Alpha Vantage! Please call after 60s."},
        {"Information": "We have detected your API key. Limit: 25 requests per day."},
    ]

    captured = []
    for env in rate_envelopes:
        async def fake_get(_self, params, env=env):
            return env

        AlphaVantageClient._get = fake_get  # type: ignore[assignment]
        result = await client.get_company_overview("AAPL")
        captured.append(result)
        print(f"[probe_d_av_throttle] envelope={env}, returned={result!r}")

    leaked = [c for c, env in zip(captured, rate_envelopes) if c == env]
    if len(leaked) == len(rate_envelopes):
        print(
            f"[probe_d_av_throttle] CONFIRMED BROKEN: {len(leaked)}/{len(rate_envelopes)} "
            "throttled envelopes passed through as data"
        )
        return 1
    print("[probe_d_av_throttle] OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
