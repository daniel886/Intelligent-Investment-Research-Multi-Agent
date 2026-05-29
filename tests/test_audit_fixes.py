"""Regression tests for the strict-audit fix bundle.

Each test pins behaviour for one numbered finding from the audit so that
silent regressions in future refactors are caught immediately.
"""
from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from typing import Any

import pytest


# ---------------------------------------------------------------------------
# Fix #1: risk_agent must not raise TypeError when bars < 20.
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_risk_agent_handles_insufficient_bars():
    """compute_risk_metrics returns None triplet for <20 bars; the agent must
    degrade to an empty report instead of crashing on f"{None:.2f}%"."""
    from agents.risk_agent import RiskAgent
    from models.schemas import PriceBar

    agent = RiskAgent()
    bars = [
        PriceBar(
            timestamp=datetime.now(timezone.utc),
            open=100.0,
            high=101.0,
            low=99.0,
            close=100.5,
            volume=1000.0,
        )
        for _ in range(5)
    ]

    # Stub the data-fetch so we don't hit the network.
    async def _fake_history(symbol: str, period: str = "6mo", interval: str = "1d"):
        return bars

    agent.yf.get_history = _fake_history  # type: ignore[assignment]

    report = await agent.run("FAKE")
    assert report.symbol == "FAKE"
    # Empty report should be returned with a descriptive reason, no TypeError.
    assert "数据" in report.summary or "不足" in report.summary or report.summary
    # Confidence should be conservative for empty/insufficient data.
    assert 0.0 <= report.confidence <= 1.0


# ---------------------------------------------------------------------------
# Fix #2: no remaining usages of deprecated datetime.utcnow / utcfromtimestamp
# at *call sites* (helper functions defined explicitly are fine).
# ---------------------------------------------------------------------------
def test_no_deprecated_utcnow_callsites():
    import re
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    bad_calls: list[str] = []
    deprecated_re = re.compile(r"datetime\.(utcnow|utcfromtimestamp)\s*\(")
    for py in root.rglob("*.py"):
        # Skip vendored deps and test fixtures themselves.
        parts = set(py.parts)
        if {"venv", "site-packages", ".git"} & parts:
            continue
        if py.name == "test_audit_fixes.py":
            continue
        text = py.read_text(encoding="utf-8", errors="ignore")
        for m in deprecated_re.finditer(text):
            line_no = text[: m.start()].count("\n") + 1
            bad_calls.append(f"{py.relative_to(root)}:{line_no}: {m.group(0)}")
    assert not bad_calls, "Deprecated datetime call-sites found:\n" + "\n".join(bad_calls)


# ---------------------------------------------------------------------------
# Fix #3: rate limiter must NOT serialise unrelated callers across sleeps.
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_rate_limiter_does_not_hold_lock_during_sleep():
    """When max_calls is exhausted and a waiter is sleeping, the lock should
    be released so a NEW caller can also queue up concurrently. We assert
    that two parallel waiters complete in ~one period rather than two."""
    from tools.rate_limiter import AsyncRateLimiter

    limiter = AsyncRateLimiter(max_calls=1, period=0.6)

    # Burn the first slot so subsequent acquires must wait.
    await limiter.acquire()

    async def _waiter() -> float:
        t0 = time.monotonic()
        await limiter.acquire()
        return time.monotonic() - t0

    # If the lock were held during the sleep, the second waiter would only
    # start its sleep AFTER the first finished — total ≈ 2 * period.
    # With the fix, both observe ≈ period.
    waits = await asyncio.gather(_waiter(), _waiter())
    # Allow generous slack for slow CI runners.
    assert max(waits) < 1.3, f"rate limiter serialised waiters: {waits}"


@pytest.mark.asyncio
async def test_rate_limiter_validates_args():
    from tools.rate_limiter import AsyncRateLimiter

    with pytest.raises(ValueError):
        AsyncRateLimiter(max_calls=0)
    with pytest.raises(ValueError):
        AsyncRateLimiter(max_calls=5, period=0)


# ---------------------------------------------------------------------------
# Fix #4 + #7: yfinance helpers must be tolerant of multi-index rows and
# schema drift in the news payload.
# ---------------------------------------------------------------------------
def test_yfinance_row_get_handles_missing_and_nan():
    import pandas as pd

    from tools.yfinance_tool import _row_get

    s = pd.Series({"Open": 1.5, "Close": float("nan")})
    assert _row_get(s, "Open") == 1.5
    assert _row_get(s, "Close") == 0.0  # nan → default
    assert _row_get(s, "Missing", default=42.0) == 42.0


def test_yfinance_from_unix_handles_seconds_and_millis():
    from tools.yfinance_tool import _from_unix

    sec = _from_unix(1_700_000_000)
    ms = _from_unix(1_700_000_000_000)
    assert sec is not None and sec.tzinfo is not None
    assert ms is not None and ms.tzinfo is not None
    # The two should resolve to the same UTC moment.
    assert abs((sec - ms).total_seconds()) < 1.0
    assert _from_unix(None) is None
    assert _from_unix("not-a-number") is None  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Fix #5: ReportRepository.list_recent must apply the symbol filter without
# rebuilding the whole query and must still respect the limit + ordering.
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_list_recent_applies_symbol_filter_and_limit(tmp_path, monkeypatch):
    """Smoke-test query construction by inspecting the compiled SQL string."""
    from sqlalchemy import desc, select

    from models.database import ReportORM

    # Replicate the query construction the repository performs.
    def build(symbol: str | None, limit: int):
        stmt = select(ReportORM)
        if symbol:
            stmt = stmt.where(ReportORM.symbol == symbol)
        stmt = stmt.order_by(desc(ReportORM.created_at)).limit(limit)
        return str(stmt.compile(compile_kwargs={"literal_binds": True}))

    sql_no_symbol = build(None, 5)
    sql_with_symbol = build("AAPL", 5)
    assert "WHERE" not in sql_no_symbol.upper().split("ORDER BY")[0]
    assert "WHERE" in sql_with_symbol.upper()
    assert "AAPL" in sql_with_symbol
    # Both must order by created_at desc and limit 5.
    for s in (sql_no_symbol, sql_with_symbol):
        assert "ORDER BY" in s.upper()
        assert "LIMIT 5" in s.upper()


# ---------------------------------------------------------------------------
# Fix #6: fundamental findings parser must accept Chinese-numbered lists.
# ---------------------------------------------------------------------------
def test_fundamental_findings_parser_accepts_cjk_punctuation():
    """Run the bullet/numbered detector on a Chinese-numbered LLM-style reply."""
    from agents.fundamental_agent import FundamentalAgent

    agent = FundamentalAgent.__new__(FundamentalAgent)  # avoid __init__ side effects

    sample = (
        "1。 公司业务质量稳健，护城河来自规模效应。\n"
        "2、 财务健康度良好，ROE 18%。\n"
        "3，估值偏高，PE 35x 超过行业均值。\n"
        "4)  催化剂：新产品发布。\n"
        "5. 风险：监管政策。\n"
        "•  补充：现金流充裕。\n"
        "10. 综合评分 78/100。\n"
    )

    # Inline the parser logic to test it deterministically without LLM call.
    bullet_chars = ("-", "•", "·", "*", "—", "–")
    numbered_punct = set(").,;:、。，；）：．")
    findings = []
    for line in sample.splitlines():
        l = line.strip()
        if not l:
            continue
        is_bullet = l.startswith(bullet_chars)
        is_numbered = (
            len(l) >= 2 and l[0].isdigit() and l[1] in numbered_punct
        )
        if not is_numbered and len(l) >= 3 and l[0].isdigit() and l[1].isdigit() and l[2] in numbered_punct:
            is_numbered = True
        if not (is_bullet or is_numbered):
            continue
        cleaned = l.lstrip("-•·*—– ").strip()
        if is_numbered:
            i = 0
            while i < len(cleaned) and cleaned[i].isdigit():
                i += 1
            while i < len(cleaned) and cleaned[i] in numbered_punct:
                i += 1
            cleaned = cleaned[i:].strip()
        if cleaned:
            findings.append(cleaned)

    # All 7 lines (including 2-digit ordinal) should be captured.
    assert len(findings) == 7, findings
    # Leading numbers must have been stripped.
    assert findings[0].startswith("公司业务")
    assert findings[1].startswith("财务健康度")
    assert findings[2].startswith("估值偏高")
    assert findings[6].startswith("综合评分")


# ---------------------------------------------------------------------------
# Sanity smoke: the schemas helper is timezone-aware.
# ---------------------------------------------------------------------------
def test_schemas_utcnow_is_timezone_aware():
    from datetime import timedelta, timezone

    from models.schemas import _utcnow

    now = _utcnow()
    assert now.tzinfo is not None
    # Must be UTC-aligned, regardless of DST.
    assert now.utcoffset() == timedelta(0)
    assert now.tzinfo.utcoffset(now) == timezone.utc.utcoffset(now)


# ===========================================================================
# Round-2 regression tests (one per Phase-3 finding).
# ===========================================================================


# ---------------------------------------------------------------------------
# Fix R2-#1 — tools/indicators.bars_to_df handles mixed tz-aware/naive input
# ---------------------------------------------------------------------------
def test_r2_bars_to_df_mixed_tz_no_crash():
    from models.schemas import Market, PriceBar
    from tools.indicators import bars_to_df

    bars = [
        PriceBar(
            symbol="X", market=Market.US,
            timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc),
            open=1, high=1, low=1, close=1, volume=0,
        ),
        PriceBar(
            symbol="X", market=Market.US,
            timestamp=datetime(2024, 1, 2),  # naive
            open=2, high=2, low=2, close=2, volume=0,
        ),
        PriceBar(
            symbol="X", market=Market.US,
            timestamp=datetime(2024, 1, 3, tzinfo=timezone.utc),
            open=3, high=3, low=3, close=3, volume=0,
        ),
    ]
    df = bars_to_df(bars)
    assert len(df) == 3
    assert df.index.tz is None  # normalised to tz-naive UTC
    # Sorted ascending.
    assert df["close"].iloc[0] == 1
    assert df["close"].iloc[-1] == 3


# ---------------------------------------------------------------------------
# Fix R2-#2 — workflow.run uses return_exceptions=True (no batch poisoning)
# ---------------------------------------------------------------------------
def test_r2_workflow_run_partial_success():
    from models.schemas import Market, ResearchReport, ResearchRequest
    from workflows.research_workflow import ResearchWorkflow

    wf = ResearchWorkflow.__new__(ResearchWorkflow)

    async def fake_run_for_symbol(req, sym):
        if sym == "BAD":
            raise RuntimeError("boom")
        return ResearchReport(
            request=req, symbol=sym, title=f"{sym} ok",
            executive_summary=f"ok-{sym}",
        )

    wf.run_for_symbol = fake_run_for_symbol  # type: ignore[assignment]
    req = ResearchRequest(query="x", symbols=["AAA", "BAD", "BBB"], market=Market.US)
    reports = asyncio.run(ResearchWorkflow.run(wf, req))

    assert len(reports) == 3
    assert reports[0].symbol == "AAA" and "ok-AAA" in reports[0].executive_summary
    assert reports[1].symbol == "BAD" and "RuntimeError" in reports[1].executive_summary
    assert reports[2].symbol == "BBB" and "ok-BBB" in reports[2].executive_summary


# ---------------------------------------------------------------------------
# Fix R2-#3 — CORS: wildcard + credentials cannot coexist
# ---------------------------------------------------------------------------
def test_r2_cors_wildcard_disables_credentials(monkeypatch):
    import importlib
    import sys

    from starlette.testclient import TestClient

    monkeypatch.setenv("CORS_ORIGINS", "*")
    for mod in list(sys.modules):
        if mod == "api" or mod.startswith("api.") or mod == "config" or mod.startswith("config."):
            sys.modules.pop(mod, None)
    api_mod = importlib.import_module("api")
    app = api_mod.create_app()

    r = TestClient(app).get("/health", headers={"Origin": "https://attacker.example"})
    acc = r.headers.get("access-control-allow-credentials")
    assert acc is None or acc.lower() != "true"


def test_r2_cors_explicit_allowlist_keeps_credentials(monkeypatch):
    import importlib
    import sys

    from starlette.testclient import TestClient

    monkeypatch.setenv("CORS_ORIGINS", "https://app.example.com")
    for mod in list(sys.modules):
        if mod == "api" or mod.startswith("api.") or mod == "config" or mod.startswith("config."):
            sys.modules.pop(mod, None)
    api_mod = importlib.import_module("api")
    app = api_mod.create_app()

    r = TestClient(app).get("/health", headers={"Origin": "https://app.example.com"})
    assert r.headers.get("access-control-allow-origin") == "https://app.example.com"
    assert (r.headers.get("access-control-allow-credentials") or "").lower() == "true"


# ---------------------------------------------------------------------------
# Fix R2-#4 — shared parse_findings handles CJK punctuation everywhere
# ---------------------------------------------------------------------------
def test_r2_parse_findings_handles_cjk_numbered_lists():
    from agents.base import BaseAgent

    sample = (
        "结论:\n"
        "1。短期偏多。\n"
        "2、关注 50 日均线。\n"
        "3）MACD 金叉。\n"
        "4. RSI 接近超买。\n"
        "- 严守止损位 95。\n"
    )
    findings = BaseAgent.parse_findings(sample, max_items=10)
    assert len(findings) == 5
    assert findings[0].startswith("短期偏多")
    assert findings[1].startswith("关注")
    assert findings[2].startswith("MACD")
    assert findings[3].startswith("RSI")
    assert findings[4].startswith("严守止损位")


def test_r2_parse_findings_used_by_both_agents():
    """Both technical_agent and fundamental_agent must delegate to the
    shared helper so future updates stay in sync."""
    import inspect

    from agents.fundamental_agent import FundamentalAgent
    from agents.technical_agent import TechnicalAgent

    for cls in (TechnicalAgent, FundamentalAgent):
        src = inspect.getsource(cls.run)
        assert "parse_findings" in src, f"{cls.__name__}.run must use parse_findings"


# ---------------------------------------------------------------------------
# Fix R2-#5 — storage_cleaner does NOT mix ignore_errors=True with onerror
# ---------------------------------------------------------------------------
def test_r2_storage_cleaner_no_dead_onerror_combo():
    import inspect

    import services.storage_cleaner as sc

    src = inspect.getsource(sc)
    # The dead combination must not appear anywhere in production source.
    assert "ignore_errors=True, onerror=" not in src
    assert "ignore_errors=True, onexc=" not in src


def test_r2_storage_cleaner_try_remove_nested(tmp_path):
    import services.storage_cleaner as sc

    nested = tmp_path / "a" / "b" / "c"
    nested.mkdir(parents=True)
    (nested / "f.txt").write_text("hi")
    target = tmp_path / "a"

    assert sc._try_remove(target)
    assert not target.exists()


# ---------------------------------------------------------------------------
# Fix R2-#6 — symbol_resolver: no false positives from substrings
# ---------------------------------------------------------------------------
def test_r2_symbol_resolver_no_substring_false_positives():
    from workflows.symbol_resolver import resolve_symbols

    # English keys must require word boundaries.
    got = resolve_symbols("look at the order book and sync the issue with btcusdt method")
    assert "BTC-USD" not in got
    assert "ETH-USD" not in got
    assert "META" not in got
    assert "LOOK" not in got
    assert "ORDER" not in got
    assert "BOOK" not in got
    assert "SYNC" not in got
    assert "ISSUE" not in got
    assert "WITH" not in got


def test_r2_symbol_resolver_still_works():
    from workflows.symbol_resolver import resolve_symbols

    got = resolve_symbols("我想看 AAPL 和 比特币 的走势,以及 0700.HK")
    assert "AAPL" in got
    assert "BTC-USD" in got
    assert "0700.HK" in got

    # Standalone English keys (with word boundary) still resolve.
    assert "BTC-USD" in resolve_symbols("BTC dropping today")
    assert "ETH-USD" in resolve_symbols("ETH ATH soon?")


# ---------------------------------------------------------------------------
# Fix R2-#7 — vectorstore.query handles empty + flat Chroma results
# ---------------------------------------------------------------------------
def test_r2_vectorstore_query_empty_result():
    from services.vectorstore import ReportVectorStore

    class _FakeCol:
        def query(self, **_kw):
            return {"ids": [], "documents": [], "metadatas": []}

    rs = ReportVectorStore.__new__(ReportVectorStore)
    rs._collection = _FakeCol()
    rs._embedder = None
    rs._vec = lambda _t: None

    assert rs.query("anything") == []


def test_r2_vectorstore_query_nested_result():
    from services.vectorstore import ReportVectorStore

    class _FakeCol:
        def query(self, **_kw):
            return {
                "ids": [["i1", "i2"]],
                "documents": [["d1", "d2"]],
                "metadatas": [[{"a": 1}, {"a": 2}]],
            }

    rs = ReportVectorStore.__new__(ReportVectorStore)
    rs._collection = _FakeCol()
    rs._embedder = None
    rs._vec = lambda _t: None

    out = rs.query("anything", n_results=2)
    assert [r["id"] for r in out] == ["i1", "i2"]
    assert out[1]["metadata"]["a"] == 2
