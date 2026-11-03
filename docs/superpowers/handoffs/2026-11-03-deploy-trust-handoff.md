# Deploy-with-trust: progress handoff

**Written:** 2026-11-03. **Final state:** all plan tasks done; the owner accepted the Streamlit-only redesign ("satisfied for now"). Live app verified after a reboot. Read "UI direction" if a larger effort is ever planned.
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
| 4 Mockups | Skipped, replaced | Owner asked for ONE best-effort Streamlit-only redesign instead of three mockups. Built and ACCEPTED by the owner for now. A larger effort with 3 mockups is only needed if they change their mind. |
| 5 Trust panel + theme | Done | Panel plus strip live and tested; theme applied (one direction, chosen by me, not picked by the owner from mockups). Owner accepted it. |
| 6 Verify live | Script done and passing | `scripts/smoke_live.py` (now clicks the Table tab and fails if a "Done in ..." widget returns). Live runs pass at desktop and 390 px after the redesign and a Cloud reboot. Cold-open lines for a friend were given to the owner in chat. |
| 7 Final check | Done | 323 passed, 1 xfailed; ruff and `evals.publish --check` clean; live smoke passes. Self-review (no fresh-context reviewer was dispatched) found and fixed one defect: proof badges were shown after a failed model call. |

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
- Tests: `python -m pytest -q` runs in about 30 s on Linux (323 passed, 1 xfailed at the last full run; the xfail is the deliberate pandas-blocklist gap). `python -m ruff check .` and `python -m evals.publish --check` must stay clean.
- The cloud container has no `LLM_API_KEY`. The app still works there because examples are served from `demo_cache.json`. `streamlit run app.py` then needs no key for the 8 example questions.
- Smoke test: `python scripts/smoke_live.py <url> [--mobile]`. It checks that elements exist (chart, table, panel text, no exception). It does not judge appearance, which is how the empty-cells issue got through. Screenshots land in `.mockups/` (gitignored).
- The trust panel's numbers come from code constants and `results/metrics.json`, never literals. Keep it that way.
- Screenshots at 390 px: the four example buttons stack one per row (no bad wrap); one label truncates.

## Open items

1. Nothing blocking. The owner accepted the UI. If they later want more: plan the larger effort with 3 mockups (see "UI direction").
2. DONE (given to the owner in chat): Task 6 step 3 cold-open message for a friend ("open in a private window on your phone, tap an example, you should see a chart, a table and 'How this answer was produced'; then type 'delete all the rows' and report back"). Expected: an answer for the example, a refusal or "Query rejected" for the delete.
3. DONE: Task 7 checks. The owner's "do differently" lines were given in chat, not committed.
4. Whole-branch review was a self-review by the implementer, not a fresh-context reviewer. If you want the stronger check, dispatch a reviewer on the range `086c6e5..HEAD`.
5. Deferred minors: README intro says the app needs "nothing but an API key" (examples need none); the owner's `.devcontainer/devcontainer.json` (GitHub template) uses Python 3.11 and disables CORS/XSRF protection for the dev container; the explanation is rendered as a markdown heading; a failed live call still uses one of the 8 session calls.

## How to resume

```bash
git fetch origin claude/clever-ptolemy-ehvssl && git checkout claude/clever-ptolemy-ehvssl && git pull
pip install -r requirements-dev.txt
python -m pytest -q && python -m ruff check . && python -m evals.publish --check
streamlit run app.py        # no key needed for the 8 example questions
```

## UI direction: attempt 1 (Streamlit only, "ledger")

**Brief from the owner:** generic look undersells the app; results area dense and static. One best design with the existing stack, no mockups.

**What was built**
- **Theme** (`.streamlit/config.toml`): warm paper background, ink text, ONE deep-green accent (`#1E6B52`) that also means "verified". Serif headings (Source Serif 4) over IBM Plex Sans, both from Google Fonts. Pill buttons. Chart and table colors from the same palette (`chartCategoricalColors` must have the colors you list; `chartSequentialColors` must have exactly 10).
- **Answer layout** (`app.py`): lead sentence (the model's explanation, as a serif headline) -> one line of proof badges -> tabs `Chart | Table (N rows) | Query` -> collapsed "How this answer was produced" with every control and its limit plus the eval sentence. Replaces the info box, the long scroll and the `st.status` widget (now a spinner that exists only while working, so saved answers show nothing).
- **Proof strip** (`trust_panel.strip`, `render_strip`): badges "Saved model output · executed live" (blue) or "Live model output", "Guard passed" (green) / "Guard rejected" (red), "Read-only engine" or "Isolated process", "N rows · time". Limits stay out of the strip.
- **Table** (`table_view.py`): `height` left at the default `"auto"` (fixes the blank rows), index hidden, date-only columns shown as `YYYY-MM-DD`.
- **Examples:** 2-wide grid built row by row (order survives stacking on a phone), `wrap=True` so labels are not cut, icons.
- **Chart:** modebar hidden (it overlapped the title).
- **CSS** (`ui_style.py`, about 6 rules): serif on h1-h4, 1100 px max content width, larger question input. `use_container_width` replaced by `width="stretch"` throughout (it is deprecated in this Streamlit).
- Emoji removed from headings and the sidebar title; sidebar is the engine, table, schema and history only.

**Findings worth knowing**
- `theme.headingFont` is delivered to the browser but this Streamlit build applies it to no heading; it only registers the font face. `ui_style.py` applies the serif with CSS. Re-check on upgrade.
- Inactive tab content is not visible to Playwright; the smoke test clicks the Table tab.
- `st.dataframe` AppTest proto does not expose height; the test spies on the call's kwargs instead.
- Theme/CSS are verified by screenshots in `.mockups/` (not unit-tested; configuration).

**Honest limits of this attempt (what a larger plan should weigh)**
- Still unmistakably Streamlit: header bar, sidebar, widget chrome. The "Deploy" button shows locally (visitors on Community Cloud see less).
- The first-open screen is calm but sparse below the examples. No preview of the proof strip before a question is asked.
- Chart axes show raw column names (`txn_count`) and the chart title repeats the headline.
- The table is behind a tab; some users want it visible by default.
- Fonts come from Google's CDN at view time; offline or blocked viewers fall back to system fonts.
- CSS selectors target Streamlit 1.66.1 test ids and may break on upgrade.

**If the owner wants more than this:** the reusable, framework-independent parts are the backend modules (`sql_guard`, `sqlite_backend`, `csv_backend`, `llm`, `demo_cache`, `session_budget`, `trust_panel.build_checks/strip/eval_line`, `table_view`). A larger plan should keep the Streamlit deployment live as the fallback while any new front end is built and verified, keep `scripts/smoke_live.py`'s contract (open cold, click first example, chart + table + proof visible, no exception), and honor the spec's anti-goals (no animated chrome, no UI number not read from `results/metrics.json`, cached output always labeled). Three mockups, each buildable with the chosen stack, then one owner pick, as the original Task 4 intended.
