"""Probe F: PolygonClient._client is dead code.

tools/polygon_tool.py:25-26 defines:
    async def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=30.0)

But every actual call constructs `async with httpx.AsyncClient(timeout=30.0)`
inline. AST-grep the repo for any caller of `._client(`.
"""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent


def main() -> int:
    callers = []
    for p in ROOT.rglob("*.py"):
        # Skip the file itself.
        if p.name == "polygon_tool.py":
            continue
        # Skip venv / probes.
        if "venv" in p.parts or "audit_round3" in p.parts or "audit_round2" in p.parts:
            continue
        text = p.read_text(errors="ignore")
        if "._client(" in text:
            callers.append(str(p.relative_to(ROOT)))
    print(f"[probe_f_polygon_dead] external callers of ._client(): {callers}")
    # Inside the file itself, check uses.
    src = (ROOT / "tools" / "polygon_tool.py").read_text()
    inline_uses = src.count("._client(")
    print(f"[probe_f_polygon_dead] inline ._client( usages: {inline_uses}")
    if not callers and inline_uses == 0:
        print("[probe_f_polygon_dead] CONFIRMED DEAD: defined but never called")
        return 1
    print("[probe_f_polygon_dead] OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
