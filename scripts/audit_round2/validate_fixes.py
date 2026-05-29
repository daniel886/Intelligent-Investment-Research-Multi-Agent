"""Phase 5 validation: exercise the FIXED code paths and assert correctness.

Each block re-imports the production module and either calls the fixed entry
point with the failing input from Phase 2 (proving the bug is gone) or asserts
the expected new behaviour. Designed to be runnable without external services
(no network, no real DB).
"""
from __future__ import annotations

import asyncio
import os
import shutil
import sys
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

# Force a deterministic test env before importing settings.
os.environ.setdefault("APP_ENV", "test")

failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    tag = "PASS" if ok else "FAIL"
    print(f"[validate] {tag}: {name} {detail}")
    if not ok:
        failures.append(name)


# ---------------------------------------------------------------------------
# Fix #1 — tools/indicators.bars_to_df no longer crashes on mixed tz
# ---------------------------------------------------------------------------
def validate_indicators_mixed_tz() -> None:
    from models.schemas import PriceBar, Market
    from tools.indicators import bars_to_df

    bars = [
        PriceBar(
            symbol="X", market=Market.US,
            timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc),
            open=1, high=1, low=1, close=1, volume=0,
        ),
        # Tz-naive on purpose — the old code raised ValueError here.
        PriceBar(
            symbol="X", market=Market.US,
            timestamp=datetime(2024, 1, 2),
            open=1, high=1, low=1, close=1, volume=0,
        ),
    ]
    try:
        df = bars_to_df(bars)
        check(
            "fix#1 bars_to_df mixed-tz",
            len(df) == 2 and df.index.tz is None,
            f"len={len(df)} tz={df.index.tz}",
        )
    except Exception as exc:  # noqa: BLE001
        check("fix#1 bars_to_df mixed-tz", False, f"raised {type(exc).__name__}: {exc}")


# ---------------------------------------------------------------------------
# Fix #2 — workflow.run no longer poisons batch on a single failure
# ---------------------------------------------------------------------------
def validate_workflow_gather() -> None:
    from models.schemas import ResearchRequest, ResearchReport, Market
    from workflows.research_workflow import ResearchWorkflow

    wf = ResearchWorkflow.__new__(ResearchWorkflow)  # bypass __init__

    async def fake_run_for_symbol(_req, sym):
        if sym == "BAD":
            raise RuntimeError("boom")
        return ResearchReport(
            symbol=sym,
            request=_req,
            title=f"{sym} ok",
            executive_summary=f"ok-{sym}",
        )

    wf.run_for_symbol = fake_run_for_symbol  # type: ignore[assignment]

    req = ResearchRequest(query="x", symbols=["AAA", "BAD", "BBB"], market=Market.US)
    try:
        reports = asyncio.run(ResearchWorkflow.run(wf, req))
        ok = (
            len(reports) == 3
            and reports[0].symbol == "AAA" and "ok-AAA" in reports[0].executive_summary
            and reports[1].symbol == "BAD" and "RuntimeError" in reports[1].executive_summary
            and reports[2].symbol == "BBB" and "ok-BBB" in reports[2].executive_summary
        )
        check(
            "fix#2 workflow.run partial success",
            ok,
            f"reports={[(r.symbol, r.executive_summary[:30]) for r in reports]}",
        )
    except Exception as exc:  # noqa: BLE001
        check(
            "fix#2 workflow.run partial success",
            False,
            f"raised {type(exc).__name__}: {exc}",
        )


# ---------------------------------------------------------------------------
# Fix #3 — CORS no longer combines `*` with credentials
# ---------------------------------------------------------------------------
def validate_cors() -> None:
    # Force wildcard origins for this validation.
    import importlib
    import sys as _sys

    def _fresh_app():
        # Drop cached modules so settings re-reads env.
        for mod in list(_sys.modules):
            if mod == "api" or mod.startswith("api.") or mod == "config" or mod.startswith("config."):
                _sys.modules.pop(mod, None)
        api_mod = importlib.import_module("api")
        # api.__init__ does `from .app import app, create_app`, so api.app
        # is the FastAPI instance, not the submodule. Call create_app fresh
        # so it picks up the new env.
        return api_mod.create_app()

    from starlette.testclient import TestClient

    os.environ["CORS_ORIGINS"] = "*"
    app1 = _fresh_app()
    client = TestClient(app1)
    r = client.get("/health", headers={"Origin": "https://attacker.example"})
    aco = r.headers.get("access-control-allow-origin")
    acc = r.headers.get("access-control-allow-credentials")
    ok = (acc is None) or (acc.lower() != "true")
    check(
        "fix#3 CORS wildcard disables credentials",
        ok,
        f"ACAO={aco!r} ACAC={acc!r}",
    )

    os.environ["CORS_ORIGINS"] = "https://app.example.com"
    app2 = _fresh_app()
    client2 = TestClient(app2)
    r2 = client2.get("/health", headers={"Origin": "https://app.example.com"})
    aco2 = r2.headers.get("access-control-allow-origin")
    acc2 = r2.headers.get("access-control-allow-credentials")
    ok2 = aco2 == "https://app.example.com" and acc2 and acc2.lower() == "true"
    check(
        "fix#3 CORS explicit allow-list keeps credentials",
        bool(ok2),
        f"ACAO={aco2!r} ACAC={acc2!r}",
    )

    os.environ.pop("CORS_ORIGINS", None)


# ---------------------------------------------------------------------------
# Fix #4 — shared parse_findings catches CJK-numbered lists
# ---------------------------------------------------------------------------
def validate_findings_parser() -> None:
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
    ok = (
        len(findings) == 5
        and findings[0].startswith("短期偏多")
        and findings[1].startswith("关注 50 日均线")
        and findings[2].startswith("MACD")
        and findings[3].startswith("RSI")
        and findings[4].startswith("严守止损位")
    )
    check("fix#4 parse_findings handles CJK punctuation", ok, f"got={findings}")


# ---------------------------------------------------------------------------
# Fix #5 — storage_cleaner no longer uses ignore_errors=True with onerror
# ---------------------------------------------------------------------------
def validate_storage_cleaner() -> None:
    import inspect
    import services.storage_cleaner as sc

    src = inspect.getsource(sc)
    # Should NOT contain the broken combination anywhere.
    bad = "ignore_errors=True, onerror=" in src or "ignore_errors=True, onexc=" in src
    check(
        "fix#5 no ignore_errors+onerror combo in source",
        not bad,
        "(broken combo absent)" if not bad else "(combo still present!)",
    )

    # Also exercise the live path: create a dir, drop a file, rmtree via
    # _try_remove. Should succeed without raising and the dir should be gone.
    tmp = Path(tempfile.mkdtemp(prefix="iir_validate_"))
    (tmp / "a.txt").write_text("hi")
    sub = tmp / "sub"
    sub.mkdir()
    (sub / "b.txt").write_text("hi")
    ok = sc._try_remove(tmp)
    check(
        "fix#5 _try_remove deletes nested dir",
        ok and not tmp.exists(),
        f"removed={ok} exists={tmp.exists()}",
    )


# ---------------------------------------------------------------------------
# Fix #6 — symbol_resolver: word-boundary on English keys, no false positives
# ---------------------------------------------------------------------------
def validate_symbol_resolver() -> None:
    from workflows.symbol_resolver import resolve_symbols

    # Sentence with English keys *embedded* in larger words and stopwords.
    text = "look at the order book and sync the issue with btcusdt method"
    got = resolve_symbols(text)
    ok = (
        "BTC-USD" not in got      # not matched in 'btcusdt'
        and "ETH-USD" not in got  # not matched in 'method'
        and "META" not in got
        and "LOOK" not in got
        and "ORDER" not in got
        and "BOOK" not in got
        and "SYNC" not in got
        and "ISSUE" not in got
    )
    check("fix#6 symbol_resolver no false positives", ok, f"got={got}")

    # Real tickers and explicit BTC keyword still work.
    text2 = "我想看 AAPL 和 比特币 的走势,以及 0700.HK"
    got2 = resolve_symbols(text2)
    ok2 = "AAPL" in got2 and "BTC-USD" in got2 and "0700.HK" in got2
    check("fix#6 symbol_resolver still resolves real tickers", ok2, f"got={got2}")

    # Standalone 'btc' should still resolve (word boundary on both sides).
    got3 = resolve_symbols("BTC dropping today")
    check("fix#6 standalone 'btc' resolves", "BTC-USD" in got3, f"got={got3}")


# ---------------------------------------------------------------------------
# Fix #7 — vectorstore.query returns [] on empty/flat Chroma result
# ---------------------------------------------------------------------------
def validate_vectorstore_empty() -> None:
    from services.vectorstore import ReportVectorStore

    class _FakeCol:
        def query(self, **_kw):
            return {"ids": [], "documents": [], "metadatas": []}

    rs = ReportVectorStore.__new__(ReportVectorStore)
    rs._collection = _FakeCol()
    rs._embedder = None  # type: ignore[attr-defined]
    rs._vec = lambda _t: None  # type: ignore[assignment]
    try:
        out = rs.query("x", n_results=3)
        check("fix#7 vectorstore.query empty result", out == [], f"got={out}")
    except Exception as exc:  # noqa: BLE001
        check("fix#7 vectorstore.query empty result", False, f"raised {type(exc).__name__}: {exc}")

    # And the normal nested shape still works.
    class _FakeCol2:
        def query(self, **_kw):
            return {
                "ids": [["id1", "id2"]],
                "documents": [["d1", "d2"]],
                "metadatas": [[{"a": 1}, {"a": 2}]],
            }

    rs._collection = _FakeCol2()
    out2 = rs.query("x", n_results=2)
    ok2 = len(out2) == 2 and out2[0]["id"] == "id1" and out2[1]["metadata"]["a"] == 2
    check("fix#7 vectorstore.query nested result", ok2, f"got={out2}")


def main() -> int:
    validate_indicators_mixed_tz()
    validate_workflow_gather()
    validate_cors()
    validate_findings_parser()
    validate_storage_cleaner()
    validate_symbol_resolver()
    validate_vectorstore_empty()

    print()
    if failures:
        print(f"[validate] {len(failures)} FAILURE(S): {failures}")
        return 1
    print("[validate] all fixes verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
