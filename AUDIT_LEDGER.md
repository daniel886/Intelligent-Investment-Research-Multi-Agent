# Audit Ledger

Append-only record of every audit-driven change.
Format: one row per fix, with file:line, severity, the probe that proved it, and the regression test that pins it.

---

## Round 1 — commit `1f6cbee`

| # | Severity | File:line | Defect | Probe / Trigger | Pinning test |
|---|---|---|---|---|---|
| R1-1 | High | `agents/risk_agent.py` | TypeError in risk metrics serialization | manual reproduction | `tests/test_audit_fixes.py` |
| R1-2 | Medium | several | `datetime.utcnow()` deprecation | `DeprecationWarning` capture | `test_schemas_utcnow_is_timezone_aware` |
| R1-3 | Medium | `services/rate_limiter.py` | Lock held across `await sleep` | manual reproduction | `tests/test_audit_fixes.py` |
| R1-4 | Medium | `tools/yfinance_tool.py` | yfinance row access by attribute | manual reproduction | `tests/test_audit_fixes.py` |
| R1-5 | Medium | `services/repository.py` | Query rebuild on each call | manual reproduction | `tests/test_audit_fixes.py` |
| R1-6 | Medium | `agents/fundamental_agent.py` | CJK-numbered findings dropped | manual reproduction | `tests/test_audit_fixes.py` |
| R1-7 | Low | `tools/yfinance_tool.py` | yfinance news schema mismatch | manual reproduction | `tests/test_audit_fixes.py` |

---

## Round 2 — commit (this round)

| # | Severity | File:line | Defect | Probe | Pinning test |
|---|---|---|---|---|---|
| R2-1 | **Critical** | `tools/indicators.py:15` | `bars_to_df` raises `ValueError` on mixed tz-aware/naive timestamps under pandas 2.x | `scripts/audit_round2/probe_c_mixed_tz.py` | `test_r2_bars_to_df_mixed_tz_no_crash` |
| R2-2 | **High** | `workflows/research_workflow.py:234` | `asyncio.gather` without `return_exceptions=True` poisons the entire batch when one symbol fails | `scripts/audit_round2/probe_d_workflow_gather.py` | `test_r2_workflow_run_partial_success` |
| R2-3 | **High** | `api/app.py:42`, `config/settings.py:45` | CORS wildcard origin combined with `allow_credentials=True` violates Fetch spec | `scripts/audit_round2/probe_a_cors.py` | `test_r2_cors_wildcard_disables_credentials`, `test_r2_cors_explicit_allowlist_keeps_credentials` |
| R2-4 | Medium | `agents/technical_agent.py:61` | CJK-numbered findings parser absent (Round-1 fix only landed in `FundamentalAgent`) | `scripts/audit_round2/probe_e_technical_parser.py` | `test_r2_parse_findings_handles_cjk_numbered_lists`, `test_r2_parse_findings_used_by_both_agents` |
| R2-5 | Medium | `services/storage_cleaner.py:139,160` | `ignore_errors=True` defeats `onerror` callback (and `onerror` is deprecated in 3.12 / removed in 3.14) | `scripts/audit_round2/probe_b_rmtree.py` | `test_r2_storage_cleaner_no_dead_onerror_combo`, `test_r2_storage_cleaner_try_remove_nested` |
| R2-6 | Medium | `workflows/symbol_resolver.py:91-98` | Substring matching produces false-positive tickers (`LOOK`, `ORDER`, `BOOK`, `SYNC`, `ISSUE`, `META`, etc.) | `scripts/audit_round2/probe_f_resolver_falsepos.py` | `test_r2_symbol_resolver_no_substring_false_positives`, `test_r2_symbol_resolver_still_works` |
| R2-7 | Low | `services/vectorstore.py:110-112` | `IndexError` when Chroma returns flattened empty `{"ids": []}` | `scripts/audit_round2/probe_g_vectorstore.py` | `test_r2_vectorstore_query_empty_result`, `test_r2_vectorstore_query_nested_result` |

### Validation matrix (Round 2)

| Check | Result |
|---|---|
| `compileall` all packages | green |
| `pytest -x -q` | **39 passed**, 0 failed (was 27) |
| `scripts/audit_round2/validate_fixes.py` | **11/11 PASS** |
| AST scan for the `ignore_errors=True, onerror=` combo | 0 hits in production code |

### Round-2 backlog (deferred)

Items observed during Phase 1 that did not meet the bar for an atomic fix in this round:

* AlphaVantage rate-limit detection (`Note`/`Information` envelope keys not parsed).
* CoinGecko client has no rate limiter — bursts will hit 429 quickly.
* Polygon news loader discards `published_utc`, preventing time-windowed queries.

---

## Round 3 — commit (this round)

| # | Severity | File:line | Defect | Probe | Pinning verifier |
|---|---|---|---|---|---|
| R3-1 | **High** | `agents/risk_agent.py:78-83` | RiskAgent still uses the narrow `-/•/·` inline parser; CJK-numbered LLM findings (`1。`, `2、`, `3）`, `4.`) are dropped — Round-2 fix landed in Technical/Fundamental but missed Risk | `scripts/audit_round3/probe_a_risk_parser.py` | `scripts/audit_round3/probe_postfix_verify.py::check_r3_1_risk_parser` |
| R3-2 | **High** | `services/repository.py:39` | tz-aware `ResearchReport.created_at` (from `schemas._utcnow`) written into naive `ReportORM.created_at` `DateTime` column → silent representation drift between JSON blob (`+00:00`) and indexed timestamp column | `scripts/audit_round3/probe_b_repo_tz.py` | `scripts/audit_round3/probe_postfix_verify.py::check_r3_2_repo_tz` |
| R3-3 | Medium | `tools/news_tool.py:67-74` | Polygon `published_utc` ISO-8601 silently dropped; every Polygon-sourced `NewsItem.published_at == None`, breaking recency ranking and "last 24h" digests | `scripts/audit_round3/probe_c_news_published.py` | `scripts/audit_round3/probe_postfix_verify.py::check_r3_3_news_published` |
| R3-4 | Medium | `tools/alpha_vantage_tool.py:25-33` | Free-tier throttling envelopes (`{"Note": ...}` / `{"Information": ...}`) returned as HTTP 200 pass through as data; tenacity retry never fires, callers see "empty" payloads | `scripts/audit_round3/probe_d_av_throttle.py` | `scripts/audit_round3/probe_postfix_verify.py::check_r3_4_av_throttle` |
| R3-5 | Medium | `tools/onchain_tool.py:13-27` | `CoinGeckoClient` has no `AsyncRateLimiter`; bursts of concurrent `get_coin`/`get_market_chart` trip 429 with no backpressure (Polygon and AlphaVantage both gate `_get`) | `scripts/audit_round3/probe_e_cg_ratelimit.py` | `scripts/audit_round3/probe_postfix_verify.py::check_r3_5_cg_ratelimit` |
| R3-6 | Low | `tools/polygon_tool.py:25-26` | `PolygonClient._client()` defined but never invoked anywhere (every real call site builds `httpx.AsyncClient` inline); misleading dead code | `scripts/audit_round3/probe_f_polygon_dead.py` | `scripts/audit_round3/probe_postfix_verify.py::check_r3_6_polygon_dead` |

### Validation matrix (Round 3)

| Check | Result |
|---|---|
| `compileall` all packages (`agents`, `tools`, `services`, `models`, `api`, `workflows`, `config`) | green |
| `pytest -q` | **39 passed**, 1 warning, 0 failed |
| `scripts/audit_round3/probe_postfix_verify.py` | **6/6 PASS** |

### Round-3 backlog (deferred)

No high/medium-severity issues remain unfixed from Round 3. Future rounds may consider:

* Adding a coverage gate to CI so Round-2 / Round-3 regression tests cannot silently rot.
* Auditing the Playwright scrapers (`tools/playwright_scraper.py`) — they synthesize `datetime.now(timezone.utc)` per item rather than parsing site-rendered timestamps.
* Considering a typed `language` enum at the API boundary so `# type: ignore` in `api/routes.py` can be dropped.

