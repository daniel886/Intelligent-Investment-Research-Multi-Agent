"""Probe D: confirm asyncio.gather without return_exceptions kills the batch.

We instrument run_for_symbol to raise for one symbol and see what
ResearchWorkflow.run returns when given two symbols.
"""
from __future__ import annotations
import asyncio
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

# Avoid actually constructing the LLM-backed workflow.
async def _raise_then_ok(self, request, symbol):
    if symbol == "BAD":
        raise RuntimeError("synthetic crash from probe_d")
    from models.schemas import ResearchReport
    return ResearchReport(
        request=request,
        symbol=symbol,
        title=f"{symbol} ok",
        executive_summary="probe ok",
    )


async def main() -> int:
    from models.schemas import ResearchRequest
    from workflows.research_workflow import ResearchWorkflow

    # Bypass __init__ heavy LLM/agent construction.
    wf = ResearchWorkflow.__new__(ResearchWorkflow)
    wf.run_for_symbol = _raise_then_ok.__get__(wf, ResearchWorkflow)  # type: ignore

    req = ResearchRequest(query="probe d", symbols=["GOOD", "BAD", "ANOTHER"])
    try:
        out = await wf.run(req)
        print(f"[probe_d] workflow.run returned {len(out)} reports — partial recovery works")
        return 0
    except Exception as e:
        print(f"[probe_d] CONFIRMED POISONED: workflow.run raised {type(e).__name__}: {e}")
        print("[probe_d] One bad symbol kills the entire batch (no return_exceptions=True).")
        return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
