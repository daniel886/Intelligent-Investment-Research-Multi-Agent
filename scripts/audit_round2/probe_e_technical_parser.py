"""Probe E: confirm technical_agent's findings parser drops Chinese-numbered lines."""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))


def main() -> int:
    sample = (
        "1。 短期趋势上行\n"
        "2、 RSI 进入超买\n"
        "3，MACD 死叉\n"
        "- 均线多头排列\n"
        "• 量能放大\n"
    )
    # Replicate technical_agent's exact parser logic.
    findings = []
    for line in sample.splitlines():
        l = line.strip().lstrip("-•· ").strip()
        if l and (line.strip().startswith(("-", "•", "·"))):
            findings.append(l)
    print(f"[probe_e] technical_agent parser captured {len(findings)} findings: {findings}")
    if len(findings) < 5:
        print("[probe_e] CONFIRMED: technical_agent drops CJK-numbered findings (same bug as Round 1 Fix #6)")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
