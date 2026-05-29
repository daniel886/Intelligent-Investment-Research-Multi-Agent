"""Probe E: CoinGeckoClient has no rate limiter at all.

Every other REST client (PolygonClient, AlphaVantageClient) instantiates an
AsyncRateLimiter — see tools/polygon_tool.py:23 and
tools/alpha_vantage_tool.py:22. CoinGecko's free public endpoint allows
~10-30 req/min before HTTP 429; bursty workflows will trip this.

We probe by AST-inspecting the CoinGeckoClient class for any `_limiter`
attribute or AsyncRateLimiter import.
"""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))


def main() -> int:
    src = (ROOT / "tools" / "onchain_tool.py").read_text()
    has_limiter = "AsyncRateLimiter" in src or "_limiter" in src
    print(f"[probe_e_cg_ratelimit] CoinGecko module imports AsyncRateLimiter: {has_limiter}")
    if not has_limiter:
        # Cross-check sibling modules use one.
        for sibling in ("polygon_tool.py", "alpha_vantage_tool.py"):
            txt = (ROOT / "tools" / sibling).read_text()
            assert "AsyncRateLimiter" in txt, f"{sibling} should have a limiter"
        print(
            "[probe_e_cg_ratelimit] CONFIRMED MISSING: peer clients have a limiter, "
            "this one does not"
        )
        return 1
    print("[probe_e_cg_ratelimit] OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
