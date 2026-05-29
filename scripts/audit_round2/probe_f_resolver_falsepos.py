"""Probe F: workflows.symbol_resolver matches NAME_MAP keys via substring,
producing false positives for English keys like 'btc' / 'meta'.
"""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from workflows.symbol_resolver import resolve_symbols


def main() -> int:
    cases = [
        ("look at the btcusdt order book", "should NOT include BTC-USD"),
        ("metadata sync issue", "should NOT include META"),
        ("我喜欢苹果手机", "苹果 → AAPL — desired"),
        ("doge meta-analysis report", "META = false positive risk"),
    ]
    issues = 0
    for query, expectation in cases:
        out = resolve_symbols(query)
        print(f"[probe_f] {query!r:50s} -> {out}  ({expectation})")
        if "btcusdt" in query and "BTC-USD" in out:
            issues = 1
        if "metadata" in query and "META" in out:
            issues = 1
        if "meta-analysis" in query and "META" in out:
            issues = 1
    if issues:
        print("[probe_f] CONFIRMED false positives from substring matching")
    return issues


if __name__ == "__main__":
    raise SystemExit(main())
