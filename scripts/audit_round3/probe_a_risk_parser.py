"""Probe A: RiskAgent.run still uses the narrow `-/•/·` findings parser.

Round 2 introduced BaseAgent.parse_findings (CJK-aware) and migrated
TechnicalAgent + FundamentalAgent. RiskAgent was missed and still inlines
the old parser. Demonstrate by running its parser logic over a Chinese-
numbered LLM-style summary and counting how many findings survive.
"""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))


def _risk_agent_inline_parser(summary: str):
    """Verbatim copy of risk_agent.py:78-83 (the suspect block)."""
    findings = []
    for line in (summary or "").splitlines():
        l = line.strip()
        if l.startswith(("-", "•", "·")):
            findings.append(l.lstrip("-•· ").strip())
    return findings[:6]


def main() -> int:
    sample = (
        "结论:\n"
        "1。流动性风险高。\n"
        "2、估值偏离合理区间。\n"
        "3）建议降低仓位。\n"
        "4. 关注美元利率走势。\n"
        "- 严守 5% 止损。\n"
    )
    parsed = _risk_agent_inline_parser(sample)
    print(f"[probe_a_risk_parser] parsed = {parsed}")
    if len(parsed) < 5:
        print(f"[probe_a_risk_parser] CONFIRMED BROKEN: only {len(parsed)} of 5 findings captured")
        # Now confirm the shared parser captures all 5.
        from agents.base import BaseAgent
        good = BaseAgent.parse_findings(sample, max_items=10)
        print(f"[probe_a_risk_parser] shared parser captures: {good}")
        if len(good) >= 5:
            print("[probe_a_risk_parser] DELTA: shared parser fixes 3+ missed findings")
            return 1
    print("[probe_a_risk_parser] OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
