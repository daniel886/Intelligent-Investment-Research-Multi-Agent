"""Probe A: CORS allow_origins=['*'] + allow_credentials=True is invalid.

CORS spec: when credentials are sent, the server must echo a SPECIFIC origin,
not '*'. Browsers will reject the response. Starlette's CORSMiddleware behavior:
- Some versions emit Access-Control-Allow-Origin: '*' regardless → broken.
- Newer versions emit the request's Origin → effectively wildcard with creds,
  which defeats the point of allowing credentials at all.

This probe spins up the real CORSMiddleware with the project's settings and
inspects the response headers for a request with Origin set.
"""
from __future__ import annotations
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient


async def hello(request):
    return JSONResponse({"ok": True})


def main() -> int:
    # Reproduce app.py's settings: allow_origins=['*'], allow_credentials=True.
    app = Starlette(
        routes=[Route("/", hello, methods=["GET"])],
        middleware=[
            Middleware(
                CORSMiddleware,
                allow_origins=["*"],
                allow_methods=["*"],
                allow_headers=["*"],
                allow_credentials=True,
            )
        ],
    )
    client = TestClient(app)
    r = client.get("/", headers={"Origin": "https://attacker.example"})
    aco = r.headers.get("access-control-allow-origin")
    acc = r.headers.get("access-control-allow-credentials")
    print(f"[probe_a_cors] Access-Control-Allow-Origin={aco!r}")
    print(f"[probe_a_cors] Access-Control-Allow-Credentials={acc!r}")
    if aco == "*" and acc and acc.lower() == "true":
        print("[probe_a_cors] CONFIRMED BROKEN: spec violation, browsers will reject")
        return 1
    if aco == "https://attacker.example" and acc and acc.lower() == "true":
        print("[probe_a_cors] CONFIRMED RISK: wildcard reflects arbitrary Origin AND sends credentials")
        return 1
    print("[probe_a_cors] OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
