# Audit Report — Round 3

**Date:** 2026-05-29
**Scope:** evidence-based deep audit (six-phase loop) over the Intelligent-Investment-Research-Multi-Agent codebase, building on Rounds 1 (commit `1f6cbee`) and 2 (commit `cc39816`).
**Outcome:** 6 defects identified with executable probes, all fixed atomically, full test suite green (39/39), zero new compileall errors, post-fix verifier 6/6 PASS.

---

## Phase 1 — Context re-establishment

Eleven modules not deeply inspected in earlier rounds were read end-to-end to surface fresh suspects:

* `tools/alpha_vantage_tool.py`, `tools/onchain_tool.py`, `tools/news_tool.py`, `tools/polygon_tool.py`, `tools/yfinance_tool.py`, `tools/playwright_scraper.py`, `tools/rate_limiter.py`
* `agents/risk_agent.py`
* `services/repository.py`, `services/scheduler.py`
* `models/schemas.py`, `models/database.py`, `api/routes.py`

The Round-2 backlog (AlphaVantage throttle, CoinGecko rate-limit, Polygon `published_utc`) was carried forward as suspects; three additional issues (RiskAgent parser drift, repository tz mixing, dead `PolygonClient._client`) emerged from the read.

## Phase 2 — Empirical probes

Six bug-reproducer probes were authored in `scripts/audit_round3/`:

| Probe | What it proves |
|---|---|
| `probe_a_risk_parser.py` | RiskAgent's verbatim inline parser captures only 1 of 5 CJK-numbered findings; the shared `BaseAgent.parse_findings` captures all 5. |
| `probe_b_repo_tz.py` | A tz-aware `ResearchReport.created_at` round-trips through `ReportORM` as a *naive* timestamp, losing the `+00:00` offset stored in the JSON blob. |
| `probe_c_news_published.py` | Every Polygon news payload's `published_utc` is dropped; resulting `NewsItem.published_at` is always `None`. |
| `probe_d_av_throttle.py` | AlphaVantage `{"Note": "..."}` and `{"Information": "..."}` HTTP 200 envelopes pass through `_get` unchanged — no retry, no error. |
| `probe_e_cg_ratelimit.py` | `tools.onchain_tool` does not import `AsyncRateLimiter`; `CoinGeckoClient` has no per-instance `_limiter`. |
| `probe_f_polygon_dead.py` | `PolygonClient._client()` has 0 invocations across the entire repo. |

All six probes returned the predicted "broken/dead" verdict.

## Phase 3 — Catalog (with file:line evidence)

| # | Severity | Site | One-line summary |
|---|---|---|---|
| R3-1 | High | `agents/risk_agent.py:78-83` | RiskAgent inline parser drops CJK findings (Round-2 leak — fix landed in Technical/Fundamental only). |
| R3-2 | High | `services/repository.py:39` | tz-aware datetime written to naive `DateTime` column → silent representation drift. |
| R3-3 | Medium | `tools/news_tool.py:67-74` | Polygon `published_utc` discarded; recency filters break for Polygon-sourced items. |
| R3-4 | Medium | `tools/alpha_vantage_tool.py:25-33` | Free-tier throttle envelopes treated as data; retry never fires. |
| R3-5 | Medium | `tools/onchain_tool.py:13-27` | CoinGecko has no rate limiter; concurrent bursts trip 429. |
| R3-6 | Low | `tools/polygon_tool.py:25-26` | `_client()` is dead code — defined but never called. |

## Phase 4 — Fixes (one change = one rationale)

### R3-1  `agents/risk_agent.py`

* **Reason:** Round 2 introduced `BaseAgent.parse_findings` (CJK-aware: handles `1。 / 2、 / 3） / 4. / -/•/·`) and migrated `TechnicalAgent` + `FundamentalAgent`. `RiskAgent` was missed and still inlined the narrow `-/•/·` parser.
* **Change:** Replaced the inline loop with `findings = self.parse_findings(summary, max_items=6)`.
* **Blast radius:** RiskAgent only. The shared parser is a strict superset of the old behavior — no findings disappear, more are surfaced.
* **Validation:** `probe_postfix_verify.check_r3_1_risk_parser` parses the source AST, asserts `parse_findings` is called and the old `startswith(("-", "•", "·"))` literal is gone.

### R3-2  `services/repository.py`

* **Reason:** `ResearchReport.created_at` defaults to a tz-aware UTC value via `schemas._utcnow`. `ReportORM.created_at = Column(DateTime, default=_utcnow_naive)` is naive. SQLAlchemy silently drops the tzinfo, but the report's JSON blob still serializes with `+00:00`. The two views of "when was this created" diverge.
* **Change:** Added `_to_naive_utc(dt)` helper that converts tz-aware → naive UTC and falls back to `_utcnow_naive()` on `None`. Wired it into `ReportORM(...)` construction.
* **Blast radius:** Repository write path only; reads were already returning naive datetimes (now consistent with the JSON blob normalized via the helper at the boundary).
* **Validation:** `probe_postfix_verify.check_r3_2_repo_tz` round-trips a tz-aware datetime and asserts a naive output with the original wall-clock hour preserved.

### R3-3  `tools/news_tool.py`

* **Reason:** Polygon's news endpoint returns ISO-8601 `published_utc`. `_polygon_as_newsitems` mapped `title / url / source / summary` but not `published_at`, so every Polygon `NewsItem` had `published_at=None` — silently breaking any "last 24h" or recency-sort downstream.
* **Change:** Added module-level `_parse_polygon_published(raw)` that tolerantly parses both `Z` and `+00:00` suffixes, returns `None` on malformed input. Wired into the `NewsItem(...)` constructor.
* **Blast radius:** Polygon mapping only. yfinance and Chinese-scraper paths were already populating `published_at`.
* **Validation:** `probe_postfix_verify.check_r3_3_news_published` injects a fake Polygon payload and asserts `items[0].published_at is not None`.

### R3-4  `tools/alpha_vantage_tool.py`

* **Reason:** AlphaVantage's free tier signals throttling with HTTP 200 + `{"Note": "..."}` or `{"Information": "..."}`. Without detection, callers (`get_company_overview`, `get_news_sentiment`, `get_daily`) treat the throttle response as valid data and degrade silently to `{}` (their generic exception path).
* **Change:** After `resp.json()`, detect a single-key `Note`/`Information` envelope and `raise RuntimeError(...)`. Tenacity's `@retry(stop=stop_after_attempt(3), wait=wait_exponential(...))` then retries; if still throttled after the third attempt, the public method's `except Exception → return {}` keeps the contract intact.
* **Blast radius:** `_get` only. Successful responses (which never include only `Note`/`Information`) are unaffected.
* **Validation:** `probe_postfix_verify.check_r3_4_av_throttle` injects both envelope variants via a fake `httpx.AsyncClient` and asserts `RuntimeError("…throttled…")` is raised.

### R3-5  `tools/onchain_tool.py`

* **Reason:** Sister clients (`PolygonClient`, `AlphaVantageClient`) all gate `_get` with `AsyncRateLimiter`. CoinGecko did not. The free public tier is roughly 10–30 calls/min; demo keys quote 30/min. Bursts of concurrent `get_coin`/`get_market_chart` from the parallel agent stage could trip 429 with no backpressure.
* **Change:** Imported `AsyncRateLimiter`, instantiated `self._limiter = AsyncRateLimiter(max_calls=15, period=60.0)` (conservative — well under the demo ceiling), called `await self._limiter.acquire()` at the top of `_get`.
* **Blast radius:** Single client. Adds at most a per-call sliding-window check; no behavior change under normal load.
* **Validation:** `probe_postfix_verify.check_r3_5_cg_ratelimit` instantiates the client and asserts `isinstance(cli._limiter, AsyncRateLimiter)`.

### R3-6  `tools/polygon_tool.py`

* **Reason:** `async def _client(self) -> httpx.AsyncClient: return httpx.AsyncClient(timeout=30.0)` was defined but had zero callers — every real call site (`_get`) builds the client inline via `async with httpx.AsyncClient(...)`. Dead helpers like this mislead reviewers (suggests the class owns a long-lived client) and inflate coverage noise.
* **Change:** Deleted the method. Replaced with a comment block citing the Round-3 audit so future readers understand the intent.
* **Blast radius:** Zero — confirmed by `probe_f_polygon_dead` and AST search.
* **Validation:** `probe_postfix_verify.check_r3_6_polygon_dead` asserts `not hasattr(PolygonClient, "_client")`.

## Phase 5 — Validation matrix

| Check | Result |
|---|---|
| `python3 -m compileall -q agents tools services models api workflows config` | green (exit 0) |
| `./venv/bin/pytest tests/ -q` | **39 passed**, 1 warning, 0 failed (2.19s) |
| `./venv/bin/python scripts/audit_round3/probe_postfix_verify.py` | **6/6 PASS** |

## Phase 6 — Backlog

Round 3 found no further high/medium issues that warranted an atomic fix in this round. Suggested future rounds:

* Add a coverage threshold gate to CI so Round-2 and Round-3 regression assertions cannot silently rot.
* Audit `tools/playwright_scraper.py` — it stamps `datetime.now(timezone.utc)` rather than parsing the site-rendered timestamps; symmetrical to R3-3.
* Convert `payload.language` to a typed enum at the API boundary in `api/routes.py` so the `# type: ignore` on the Literal coercion can go.
