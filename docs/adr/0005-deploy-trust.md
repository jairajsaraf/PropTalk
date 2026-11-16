# 5. Deploy publicly, and show how each answer was produced

## Context

A first-time visitor opens the public link with no setup. The first click has to work even when the LLM key is missing or its shared quota is used up, and the page must not overstate what the app does. Three things could go wrong: an example that fails, a cached answer passed off as live, and a number on the page that does not come from the evaluation.

## Decision

- **Example questions use saved model output.** `demo_cache.json` stores only what the model returned (code, chart config, explanation) for the example questions in both engines. The code still goes through the guard and the engine on every request, so the result is "saved model output, executed live". The file is built by `scripts/build_demo_cache.py`; its `--verify` mode re-runs every entry offline and does not rewrite the file when nothing is dropped.
- **Typed questions are capped per session.** `session_budget.MAX_LIVE_CALLS_PER_SESSION` is 8. The count lives in Streamlit session state, so it resets on a page reload. It is a courtesy cap that keeps one visitor from draining the shared quota by accident, not abuse protection.
- **Each answer shows a proof strip and a collapsed "How this answer was produced" panel** (`trust_panel.py`). Limits are read from code constants (`sql_guard.MAX_ROWS`, `sqlite_backend.QUERY_TIME_BUDGET_SECONDS`, `csv_backend._EXEC_TIMEOUT`), so the panel cannot drift from what the engine enforces. The one quality sentence is built from `results/metrics.json` (SQL from the v1 report, pandas from v2) and is omitted if the file or a key is missing. When the pandas executor contract differs from the one the eval measured, the sentence says so.
- **First start generates the data.** `sample_data/*.csv` is gitignored, so `bootstrap.ensure_sample_data` runs `generate_sample_data.py` when any CSV is missing. The output is the same seeded data as a manual setup.

## Consequences

- Examples work with no key and no quota, except the SQL "Price distribution by property type": its saved query kept only the 100 cheapest listings, so the entry was removed and that example runs live. Saved answers are labeled as saved; live answers are labeled as live.
- A saved answer can go stale if the prompt, schema or guard changes. `--verify` catches entries that no longer pass the guard and engine or return no rows. It does not catch a wrong but valid answer.
- The session cap does not stop a determined user: reloading resets it, and it is per session, not per client or per key.
- A live call counts against the cap only after the model returns, so a rate limit, rejected key or timeout does not use one up.
- The eval sentence applies to the engine and contract named in it. The pandas number was measured under an older executor contract, and the panel says so rather than implying it carries over unchanged.
- The first request on a fresh deployment is slower while the data is generated.
