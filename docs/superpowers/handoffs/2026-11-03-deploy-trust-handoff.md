# Deploy-with-trust: progress handoff

**Written:** 2026-11-03, after Task 3 (live deploy) and before the UI rethink.
**Read this first, then the plan and spec. Nothing here replaces them.**

- Plan: `docs/superpowers/plans/2026-11-03-deploy-trust.md` (boxes are ticked as tasks finish)
- Spec: `docs/superpowers/specs/2026-11-03-deploy-trust-design.md`
- Project rules: `CLAUDE.md` (public repo, synthetic data only, no employer/vendor/institution references, commit messages imperative with no attribution trailers, ask before any live LLM call, never touch `evals/` or `results/`)
- Branch: `claude/clever-ptolemy-ehvssl` (pushed after every task; Streamlit Cloud deploys from it)
- Live app: https://proptalk.streamlit.app/

## Goal (from the spec)

A reviewer opens the public link cold and the first click works. Example questions work even with no LLM key or quota; every answer shows how it was produced. Depth over breadth. Anti-goals: a link that errors or hangs, a UI number that is not read from `results/metrics.json`, cached output passed off as live, animated chrome, any employer/institution reference.

## State of the plan

| Task | Status | Notes |
|---|---|---|
| 1 Data bootstrap | Done | `bootstrap.py`; cold start regenerates identical CSVs (diffed). |
| 2 Saved answers, cap, plain errors | Done | `demo_cache.py`, `session_budget.py`, `llm.describe_llm_error`, `scripts/build_demo_cache.py`. Owner built `demo_cache.json` locally (16 entries); re-verified offline 16/16 through guard + engine, none dropped. |
| 3 Deploy | Done | Owner deployed; smoke test passed on the live URL (desktop and 390 px); README links it. |
| 4 Mockups | Skipped, replaced | Owner asked for ONE best-effort Streamlit-only redesign instead of three mockups. See "UI direction" below. If they are unhappy with it, the next phase plans a larger effort with 3 mockups. |
| 5 Trust panel + theme | Panel done; theme see below | `trust_panel.py` is live and tested. |
| 6 Verify live | Script done and passing | `scripts/smoke_live.py`. Step 3 (cold-open lines for a friend) and the final live re-run are still to do. |
| 7 Final check | Not started | Full suite, live smoke, three "do differently next time" lines for the owner, session notes. |

## Decisions and rulings so far (all recorded in the ledger; cost if wrong in brackets)

- Plan boxes are ticked in the next commit, not in separate commits. [none]
- Smoke script written during Task 3 instead of Task 6, because Task 3 needed it. [none]
- Trust panel built before the theme pick, at the owner's request. [Task 5 incomplete until the theme lands]
- `.superpowers/` (the SDD ledger workspace) is excluded through `.git/info/exclude`, local only. The next agent should recreate the ledger or just use this file.
- Python Playwright was pip-installed as a dev tool in the cloud container only; it is not in `requirements*.txt`. Default launch fails on the preinstalled browser revision, so `smoke_live.py` falls back to `/opt/pw-browsers/chromium --no-sandbox`.
- Per-session cap is 8 live calls and resets on reload. README Limitations says so.

## What the owner wants (their words, condensed)

- Found two useless parts on the live app: the **"Done in 0.1s" dropdown** (a `st.status` widget left behind) and **empty cells in Results** (a 4-row result padded by `st.dataframe(height=400)`).
- Biggest issue: **the generic look undersells the app's capabilities**, and **the results area is dense and static-looking**.
- Open to options beyond Streamlit **only if the deployment stays live and everything keeps working**. First find out how far Streamlit alone goes.
- Do NOT produce three mockups now. Build one best design with the existing stack. If still dissatisfied, plan something larger with 3 mockups.
- The owner wants challenge, not agreement: push back where an idea is weak.

## Facts the next agent needs

- Stack: Streamlit 1.66.1, pandas 3.1.0, Plotly 7.1.0, Python 3.13. Theme options available in this Streamlit (check `streamlit config show`): fonts via Google CSS URL, `headingFont`, `baseRadius`, `buttonRadius`, `dataframeHeaderBackgroundColor`, `dataframeBorderColor`, `chartCategoricalColors`/`Sequential`/`Diverging`, `metricValueFontSize`, `[theme.sidebar]`. `st.dataframe(height="auto")` is the default and shows at most ten rows. Badge syntax `:green-badge[text]` exists.
- Tests: `python -m pytest -q` runs in about 30 s on Linux (306 passed, 1 xfailed at the last full run; the xfail is the deliberate pandas-blocklist gap). `python -m ruff check .` and `python -m evals.publish --check` must stay clean.
- The cloud container has no `LLM_API_KEY`. The app still works there because examples are served from `demo_cache.json`. `streamlit run app.py` then needs no key for the 8 example questions.
- Smoke test: `python scripts/smoke_live.py <url> [--mobile]`. It checks that elements exist (chart, table, panel text, no exception). It does not judge appearance, which is how the empty-cells issue got through. Screenshots land in `.mockups/` (gitignored).
- The trust panel's numbers come from code constants and `results/metrics.json`, never literals. Keep it that way.
- Screenshots at 390 px: the four example buttons stack one per row (no bad wrap); one label truncates.

## Open items

1. UI direction: see the section below (appended after the redesign attempt).
2. Task 6 step 3: cold-open message for a friend ("open in a private window on your phone, tap an example, you should see a chart, a table and 'How this answer was produced'; then type 'delete all the rows' and report back"). Expected: an answer for the example, a refusal or "Query rejected" for the delete.
3. Task 7: full suite, live smoke after the last push, three "what I'd do differently" lines for the owner's email (nothing goes in the repo), session notes.
4. Whole-branch review has not been run yet (the executing-plans skill asks for one fresh-context review at the end).

## How to resume

```bash
git fetch origin claude/clever-ptolemy-ehvssl && git checkout claude/clever-ptolemy-ehvssl && git pull
pip install -r requirements-dev.txt
python -m pytest -q && python -m ruff check . && python -m evals.publish --check
streamlit run app.py        # no key needed for the 8 example questions
```
