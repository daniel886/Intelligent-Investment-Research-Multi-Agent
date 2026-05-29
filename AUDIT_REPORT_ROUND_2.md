# Audit Report — Round 2

**Project:** Intelligent-Investment-Research-Multi-Agent
**Date:** 2026-05-29
**Scope:** Files not deeply inspected during Round 1 (`api/`, `config/`, `services/`, plus `tools/`, `agents/`, `workflows/` modules previously skimmed).
**Methodology:** `evidence-based-audit` — every claim backed by an executable probe under `scripts/audit_round2/` and pinned by a regression test under `tests/test_audit_fixes.py`.

## Summary

Seven defects confirmed and fixed. All defects had reproducible, deterministic probes; all fixes have dedicated regression tests. The full pytest suite goes from 27 passing → 39 passing (12 new tests added) with zero regressions.

| Severity | Count |
|---|---|
| Critical | 1 |
| High     | 2 |
| Medium   | 3 |
| Low      | 1 |
| **Total** | **7** |

## Phase 1 — Context

Files newly read this round (15 files, ~1.4 kLoC):
`main.py`, `api/app.py`, `api/routes.py`, `config/settings.py`, `config/logging.py`,
`services/notifier.py`, `services/storage_cleaner.py`, `services/vectorstore.py`,
`agents/technical_agent.py`, `tools/news_tool.py`, `tools/alpha_vantage_tool.py`,
`tools/onchain_tool.py`, `tools/indicators.py`,
`workflows/symbol_resolver.py`, `workflows/research_workflow.py`.

## Phase 2 — Empirical probes

All seven probes were executed and produced the expected failure signature before any fix was applied. Probes live under `scripts/audit_round2/` and are runnable standalone.

| Probe | Target | Reproduces |
|---|---|---|
| `probe_a_cors.py` | CORS middleware | `Access-Control-Allow-Origin: *` AND `Access-Control-Allow-Credentials: true` (browser-rejected per Fetch spec) |
| `probe_b_rmtree.py` | `shutil.rmtree(ignore_errors=True, onerror=…)` | `onerror` invoked 0 times — callback is dead code |
| `probe_c_mixed_tz.py` | `tools.indicators.bars_to_df` | `ValueError: Cannot mix tz-aware with tz-naive values, at position 1` |
| `probe_d_workflow_gather.py` | `ResearchWorkflow.run` | One failing symbol cancels every other in-flight task |
| `probe_e_technical_parser.py` | `TechnicalAgent.run` findings parser | Drops 3 of 5 CJK-numbered findings |
| `probe_f_resolver_falsepos.py` | `workflows.symbol_resolver.resolve_symbols` | False-positive tickers (`LOOK`, `ORDER`, `BOOK`, `SYNC`, `ISSUE`, `META`, `BTC-USD` from substrings) |
| `probe_g_vectorstore.py` | `ReportVectorStore.query` | `IndexError` when Chroma returns flattened empty `{"ids": []}` |

## Phase 3 — Findings

| # | Severity | File:line | Probe | Disposition |
|---|---|---|---|---|
| 1 | **Critical** | `tools/indicators.py:15` | C | Normalise to UTC then drop tzinfo |
| 2 | **High** | `workflows/research_workflow.py:234` | D | `return_exceptions=True` + per-symbol placeholder |
| 3 | **High** | `api/app.py:42` + `config/settings.py:45` | A | Disable credentials when origin is `*`; warn |
| 4 | Medium | `agents/technical_agent.py:61` | E | Reuse `BaseAgent.parse_findings`; CJK-aware |
| 5 | Medium | `services/storage_cleaner.py:139,160` | B | Drop `ignore_errors=True`; dispatch `onexc`/`onerror` by Python version |
| 6 | Medium | `workflows/symbol_resolver.py:91-98` | F | Word-boundary check for ASCII keys; expand `STOPWORDS` |
| 7 | Low | `services/vectorstore.py:110-112` | G | Defensive `_first_or_empty` accepts both shapes |

## Phase 4 — Fixes

### Fix R2-#1 — `tools/indicators.py:15` (Critical)
**Reason.** `pd.to_datetime` over a Series mixing tz-aware (yfinance returns UTC) and tz-naive (AlphaVantage / CoinGecko emit naive ISO strings) datetimes raises `ValueError` in pandas 2.x. The crash was reachable from every code path that called `compute_indicators` or `compute_risk_metrics`, i.e. every technical/risk evaluation that mixed sources.
**Blast radius.** Confined to `bars_to_df`. Output schema unchanged: still tz-naive `DatetimeIndex` sorted ascending. Existing callers see identical numerics.
**Validation.** `test_r2_bars_to_df_mixed_tz_no_crash` builds a 3-bar fixture mixing tz-aware and tz-naive timestamps and asserts no exception, three sorted rows, and naive index.

### Fix R2-#2 — `workflows/research_workflow.py:234` (High)
**Reason.** `await asyncio.gather(*tasks)` re-raises the first exception and cancels the other tasks. A single bad symbol caused the API to return 500 even when other symbols had usable data.
**Blast radius.** `ResearchWorkflow.run`. Now returns one `ResearchReport` per symbol; failed symbols receive a placeholder report whose `executive_summary` carries the exception type+message. Successful reports are unchanged.
**Validation.** `test_r2_workflow_run_partial_success` asserts `["AAA","BAD","BBB"]` with a deliberate `RuntimeError("boom")` on `BAD` produces three reports in order, with the failure preserved as `RuntimeError` text in the placeholder.

### Fix R2-#3 — `api/app.py:42` + `config/settings.py:45` (High)
**Reason.** Default config (`CORS_ORIGINS=*`) plus `allow_credentials=True` violates the Fetch spec. Browsers reject the response, so credentialed AJAX calls fail silently — and worse, *any* explicit allow-list with `*` mixed in becomes a wildcard-credentials misconfiguration.
**Blast radius.** Only the CORS middleware is touched. When `CORS_ORIGINS` lists explicit origins (no `*`), credentials remain enabled and behaviour is unchanged. When `*` is present (including the default), credentials are disabled and a startup warning logs the resolution.
**Validation.** Two tests: `test_r2_cors_wildcard_disables_credentials` and `test_r2_cors_explicit_allowlist_keeps_credentials`. Both spin up a fresh app via `create_app` after monkey-patching `CORS_ORIGINS` and inspect the real response headers.

### Fix R2-#4 — `agents/technical_agent.py:61` (Medium)
**Reason.** Round 1 fixed CJK-punctuation handling in `FundamentalAgent` only; the same bug remained in `TechnicalAgent` because each agent owned its own copy-pasted parser. CJK-numbered findings (`1。`, `2、`, `3）`) were silently dropped.
**Blast radius.** Parser logic moves to `BaseAgent.parse_findings`, used by both subclasses. Fundamental_agent loses ~30 LoC of duplicated logic. Risk_agent did not implement the parser; future agents inherit the correct one for free.
**Validation.** `test_r2_parse_findings_handles_cjk_numbered_lists` exercises the helper with mixed CJK punctuation and dashes. `test_r2_parse_findings_used_by_both_agents` AST-greps the source of `TechnicalAgent.run` and `FundamentalAgent.run` to confirm both delegate to `parse_findings`.

### Fix R2-#5 — `services/storage_cleaner.py:139, 160` (Medium)
**Reason.** `shutil.rmtree(p, ignore_errors=True, onerror=_on_rmtree_error)` is a no-op for the callback: `ignore_errors=True` short-circuits to a swallow-everything handler in CPython, so the chmod-and-retry path was never executed. Worse, `onerror=` is deprecated in Python 3.12 and removed in 3.14, replaced by `onexc=`.
**Blast radius.** Only deletion plumbing. New helper `_rmtree_safe` dispatches to `onexc` on Python ≥ 3.12, `onerror` otherwise; the callback semantics (chmod + retry, never raise) are preserved by the no-re-raise contract. Behaviour-equivalent to the previous *intent*; finally matches the *implementation*.
**Validation.** `test_r2_storage_cleaner_no_dead_onerror_combo` AST-greps the source to ensure the `ignore_errors=True, onerror=` (and `onexc=`) combination cannot be re-introduced. `test_r2_storage_cleaner_try_remove_nested` removes a real nested temp tree and asserts the directory is gone.

### Fix R2-#6 — `workflows/symbol_resolver.py:91-98` (Medium)
**Reason.** `if name in lowered or name in text:` substring-matched ASCII keys, so `btc` matched inside `btcusdt`, `eth` inside `method`, `meta` inside `metadata`. Combined with an incomplete `STOPWORDS`, all-caps English words like `LOOK`, `ORDER`, `BOOK`, `SYNC`, `ISSUE` were resolved as tickers.
**Blast radius.** `resolve_symbols` only. ASCII NAME_MAP keys now require word-boundaries (`(?<![A-Za-z0-9])key(?![A-Za-z0-9])`); CJK keys still substring-match because Chinese has no whitespace separators. STOPWORDS gains 30+ common English words. Real tickers (`AAPL`, `0700.HK`, `BTC-USD` from `比特币` or standalone `BTC`) still resolve.
**Validation.** `test_r2_symbol_resolver_no_substring_false_positives` and `test_r2_symbol_resolver_still_works` cover both the negative and positive cases, including the standalone-keyword path.

### Fix R2-#7 — `services/vectorstore.py:110-112` (Low)
**Reason.** Chroma usually returns nested-list shapes (`{"ids": [["…"]]}`), but on an empty collection or some flat-result paths returns `{"ids": []}`. The previous `res.get("ids", [[]])[0]` raised `IndexError` on the flattened shape.
**Blast radius.** `ReportVectorStore.query` only. The new `_first_or_empty` static method accepts both shapes and returns `[]` for any empty/flattened result. Standard nested results still iterate correctly.
**Validation.** `test_r2_vectorstore_query_empty_result` (flattened empty) and `test_r2_vectorstore_query_nested_result` (standard nested two-row) cover both code paths.

## Phase 5 — Validation matrix

| Check | Result |
|---|---|
| `python -m compileall agents api config models services tools workflows main.py` | green |
| `python -m pytest -x -q` | **39 passed**, 0 failed (was 27) |
| `scripts/audit_round2/validate_fixes.py` | **11/11 PASS** |
| AST scan for `ignore_errors=True, onerror=` in production tree | 0 hits (probe scripts excluded) |

## Phase 6 — Backlog (not fixed this round)

These are design issues observed during Phase 1 but deemed too large for an atomic fix in this round. They are tracked for Round 3.

* **AlphaVantage rate-limit detection.** `AlphaVantageClient` does not parse the `"Note"` / `"Information"` envelope keys that the API returns when it throttles. Today such responses are treated as "no data" and silently retried.
* **CoinGecko has no rate limiter.** Other clients use a shared limiter; CoinGecko hits the public API directly. Bursting will earn a 429 quickly.
* **Polygon news drops `published_utc`.** The publication timestamp is discarded on conversion to the internal schema, preventing time-windowed queries.

## Sign-off

All seven Round-2 fixes are committed in a single atomic commit so a rollback is one revert away. Tests are pinned. Probes are kept under `scripts/audit_round2/` for future re-runs. No production behaviour change beyond the seven items above.
