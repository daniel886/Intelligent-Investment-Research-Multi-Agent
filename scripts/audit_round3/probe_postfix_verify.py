"""Post-fix verification probe for Round-3 fixes.

Runs against the *actual* fixed modules (not bug-reproducer copies) and
asserts each Round-3 finding is resolved.
"""
from __future__ import annotations

import ast
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))


def check_r3_1_risk_parser() -> bool:
    """RiskAgent.run delegates to BaseAgent.parse_findings."""
    src = (ROOT / "agents" / "risk_agent.py").read_text()
    tree = ast.parse(src)
    has_call = False
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            f = node.func
            if isinstance(f, ast.Attribute) and f.attr == "parse_findings":
                has_call = True
    # And the old startswith("-", "•", "·") inline filter is gone.
    has_old_inline = "startswith((\"-\", \"•\", \"·\"))" in src or "startswith(('-','•','·'))" in src
    print(f"[R3-1] parse_findings called={has_call}, old inline filter present={has_old_inline}")
    return has_call and not has_old_inline


def check_r3_2_repo_tz() -> bool:
    """services.repository._to_naive_utc converts tz-aware to naive UTC."""
    from services.repository import _to_naive_utc, _utcnow_naive  # type: ignore

    aware = datetime(2026, 5, 29, 12, 0, 0, tzinfo=timezone.utc)
    out = _to_naive_utc(aware)
    print(f"[R3-2] _to_naive_utc({aware}) -> {out} tz={out.tzinfo}")
    if out.tzinfo is not None:
        return False
    if out.year != 2026 or out.hour != 12:
        return False
    # None path falls back to current naive UTC.
    fallback = _to_naive_utc(None)
    if fallback.tzinfo is not None:
        return False
    return True


def check_r3_3_news_published() -> bool:
    """tools.news_tool maps Polygon published_utc -> NewsItem.published_at."""
    import asyncio

    from tools.news_tool import NewsAggregator, _parse_polygon_published

    parsed = _parse_polygon_published("2026-04-01T13:30:00Z")
    if parsed is None or parsed.tzinfo is None:
        print("[R3-3] _parse_polygon_published failed on Z suffix")
        return False
    print(f"[R3-3] parsed Polygon published_utc -> {parsed}")

    agg = NewsAggregator()

    async def fake_get_news(symbol, limit=10):
        return [
            {
                "title": "X",
                "article_url": "u",
                "publisher": {"name": "P"},
                "description": "d",
                "published_utc": "2026-04-01T13:30:00Z",
            }
        ]

    agg.polygon.get_news = fake_get_news  # type: ignore[assignment]
    items = asyncio.run(agg._polygon_as_newsitems("AAPL", 5))
    print(f"[R3-3] mapped item.published_at = {items[0].published_at}")
    return items[0].published_at is not None


def check_r3_4_av_throttle() -> bool:
    """tools.alpha_vantage_tool._get raises on Note/Information envelopes."""
    import asyncio

    import tools.alpha_vantage_tool as av
    from tools.alpha_vantage_tool import AlphaVantageClient

    class FakeResp:
        def __init__(self, payload):
            self._payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self._payload

    class FakeClient:
        def __init__(self, payload):
            self._payload = payload

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return None

        async def get(self, *a, **kw):
            return FakeResp(self._payload)

    async def run() -> bool:
        cli = AlphaVantageClient(api_key="dummy")
        # Tenacity stores the original on .retry.fn; fall back to
        # __wrapped__ if available.
        wrapped = getattr(cli._get, "__wrapped__", None) or cli._get.retry.fn  # type: ignore[attr-defined]
        for env in ({"Note": "Throttled"}, {"Information": "Limit"}):
            av.httpx.AsyncClient = lambda *a, **kw: FakeClient(env)  # type: ignore
            try:
                await wrapped(cli, {"function": "OVERVIEW"})
                print(f"[R3-4] envelope {env} did NOT raise — fix incomplete")
                return False
            except RuntimeError as e:
                if "throttled" not in str(e).lower():
                    print(f"[R3-4] unexpected error: {e!r}")
                    return False
        print("[R3-4] both Note/Information envelopes correctly raised RuntimeError")
        return True

    return asyncio.run(run())


def check_r3_5_cg_ratelimit() -> bool:
    """tools.onchain_tool.CoinGeckoClient owns an AsyncRateLimiter."""
    import asyncio

    from tools.onchain_tool import CoinGeckoClient
    from tools.rate_limiter import AsyncRateLimiter

    async def run() -> bool:
        cli = CoinGeckoClient(api_key="x")
        ok = isinstance(getattr(cli, "_limiter", None), AsyncRateLimiter)
        print(f"[R3-5] CoinGeckoClient._limiter is AsyncRateLimiter: {ok}")
        return ok

    return asyncio.run(run())


def check_r3_6_polygon_dead() -> bool:
    """tools.polygon_tool.PolygonClient no longer defines _client."""
    from tools.polygon_tool import PolygonClient

    has = hasattr(PolygonClient, "_client")
    print(f"[R3-6] PolygonClient has _client attr: {has}")
    return not has


def main() -> int:
    checks = [
        ("R3-1", check_r3_1_risk_parser),
        ("R3-2", check_r3_2_repo_tz),
        ("R3-3", check_r3_3_news_published),
        ("R3-4", check_r3_4_av_throttle),
        ("R3-5", check_r3_5_cg_ratelimit),
        ("R3-6", check_r3_6_polygon_dead),
    ]
    results = []
    for name, fn in checks:
        try:
            ok = fn()
        except Exception as e:  # noqa: BLE001
            print(f"[{name}] EXCEPTION: {e!r}")
            ok = False
        results.append((name, ok))
        print()
    print("=== Summary ===")
    for name, ok in results:
        print(f"  {name}: {'PASS' if ok else 'FAIL'}")
    return 0 if all(ok for _, ok in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
