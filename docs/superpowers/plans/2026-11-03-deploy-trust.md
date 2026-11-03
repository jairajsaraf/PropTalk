# Deploy PropTalk with Visible Trust — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A public Streamlit Community Cloud deployment whose example questions work on first open even with no LLM quota, and where every answer shows how it was produced.

**Architecture:** Four small new modules (`bootstrap.py`, `demo_cache.py`, `session_budget.py`, `trust_panel.py`) plus one helper in `llm.py`, wired into `app.py`'s existing query flow (`app.py:192-285`). Saved model output for the 8 example questions lives in `demo_cache.json` and still runs through the guard and engine live. The look comes from `.streamlit/config.toml` and minimal CSS, chosen from static mockups.

**Tech Stack:** Python 3.13, Streamlit 1.66.1 (`streamlit.testing.v1.AppTest` for tests), pandas, Plotly, Playwright (smoke test only, not a runtime dependency).

**Spec:** `docs/superpowers/specs/2026-11-03-deploy-trust-design.md`

## Resume protocol (cloud → local teleport)

This session may move from the cloud container to the owner's Windows machine partway through.

- **Push after every task** to `claude/clever-ptolemy-ehvssl`, and tick that task's boxes in this file in the same commit. The ticked boxes are the progress record.
- **Locally, first:** `git fetch origin claude/clever-ptolemy-ehvssl` then `git checkout claude/clever-ptolemy-ehvssl` and `git pull`. Read this file and resume at the first unticked box.
- **Windows:** no `make`. Use `python -m ruff check .` and the targeted `pytest` commands in each task. The full suite takes about 10 minutes there (CLAUDE.md), so run it only once, in Task 7.
- **Before Task 4, when running locally, take stock of the local frontend resources** and write what you find into the "Local resources found" list below:
  - `claude plugin list` and `claude mcp list` (CLI subcommands; if one doesn't exist in the installed version, skip it and say so)
  - `Get-ChildItem $HOME\.claude\skills, $HOME\.claude\plugins -Directory`
  - `Get-ChildItem $HOME -Recurse -Filter components.json -ErrorAction SilentlyContinue -Depth 4`. These are shadcn projects; a `registries` entry with `@cult-ui` means cult-ui is set up there.
  - Prefer a local shadcn MCP server or a cult-ui checkout for building the mockups (Task 4). If you find none, use the `web-artifacts-builder`, `no-ai-slop` and `artifact-design` skills.
- **In the cloud**, the Artifact tool publishes mockups. **Locally**, if the Artifact tool is missing, write the mockups to `.mockups/` (add it to `.gitignore`) and open them in a browser.

**Local resources found:** _(fill in at teleport)_

## Global Constraints

- Deadline: 2 hours from plan approval. If Task 3 (deploy) is not verified by T+60 min, skip Task 5 and go straight to Task 6.
- No numbers in the UI except those read from `results/metrics.json` at runtime.
- No employer, institution or vendor references anywhere in the repo (CLAUDE.md).
- Secrets only via `.env` locally and Streamlit Cloud secrets in deployment. Never commit `.streamlit/secrets.toml` (already gitignored).
- **Ask the owner before** any live LLM call, adding a runtime dependency, or touching `evals/` or `results/`.
- Do not change `generate_sample_data.py` output; the evals depend on it.
- Commit messages: imperative, concise, no attribution trailers (CLAUDE.md overrides the harness default).
- Type hints on every function signature.
- `python -m ruff check .` is clean before every push.

## Review Focus

1. **Cold start with no `sample_data/`:** the first load generates the CSVs once and renders; it never shows `FileNotFoundError`. Test lives in Task 1.
2. **Quota exhausted (HTTP 429) on a typed question:** a plain message saying examples still work, not a stack trace. Test lives in Task 2.
3. **No `LLM_API_KEY` at all:** the page still renders and the examples still answer. Today `app.py:141-146` calls `st.stop()`. Test lives in Task 2.
4. **An example retyped with different case or trailing spaces:** still served from the cache, not a live call. Test lives in Task 2.
5. **Phone-width first open:** the 4 example buttons sit in `st.columns(4)` (`app.py:181`), which wraps badly on narrow screens. Checked by the Task 6 cold-open checklist at 390 px width.

---

### Task 1: Data bootstrap and deploy config

**Files:**
- Create: `bootstrap.py`, `tests/test_bootstrap.py`, `.streamlit/config.toml` (placeholder theme; Task 5 replaces its values)
- Modify: `app.py:16` (call bootstrap right after `load_dotenv()`, before `_BACKENDS`)

**Interfaces:**
- Produces: `bootstrap.ensure_sample_data() -> bool`. It returns `True` if it generated the data and `False` if all CSVs already existed. It runs `[sys.executable, <repo>/generate_sample_data.py]` via `subprocess.run(check=True)`, which is exactly the documented command, so the seeded output is identical. The file list comes from `config.TABLE_REGISTRY[*].csv_filename` inside `csv_backend.SAMPLE_DIR`.
- In `app.py`: `st.cache_resource(bootstrap.ensure_sample_data)()` so it runs once per server process.

- [x] **Step 1: Write failing tests** in `tests/test_bootstrap.py`
  - `test_noop_when_all_csvs_present`: monkeypatch `os.path.exists` → `True`, spy `subprocess.run`; assert it returns `False` and the spy was never called.
  - `test_generates_when_any_csv_missing`: monkeypatch `os.path.exists` → `False` for one filename; assert it returns `True` and the spy was called once with `[sys.executable, path ending "generate_sample_data.py"]` and `check=True`.
- [x] **Step 2:** `python -m pytest tests/test_bootstrap.py -q`. Expected: FAIL (module missing).
- [x] **Step 3:** Implement `ensure_sample_data`, wire it into `app.py`, and add `.streamlit/config.toml` with `[theme] base = "light"` only.
- [x] **Step 4:** `python -m pytest tests/test_bootstrap.py tests/test_app.py -q`. Expected: PASS.
- [x] **Step 5: Real cold start:** move `sample_data/` aside, run `streamlit run app.py --server.headless true` for about 20 s, and confirm the CSVs reappear and the log has no traceback. Restore if needed.
- [x] **Step 6:** Commit `Generate sample data on first start` and push.

### Task 2: Saved example answers, per-session cap, plain errors

**Files:**
- Create: `demo_cache.py`, `session_budget.py`, `scripts/build_demo_cache.py`, `demo_cache.json` (from Step 6), `tests/test_demo_cache.py`, `tests/test_session_budget.py`
- Modify: `llm.py` (add `describe_llm_error`), `app.py:139-146` (remove the hard `st.stop()` on a missing key), `app.py:206-224` (choose the answer's source), `tests/test_app.py` (new cases)

**Interfaces:**
- `demo_cache.CACHE_PATH: str` = `<repo>/demo_cache.json`
- `demo_cache.normalize(question: str) -> str`: strip, collapse internal whitespace, casefold.
- `demo_cache.lookup(question: str, table_id: str, mode: str) -> dict | None` returns a copy of the stored response (`sql` or `pandas_code`, `chart_config`, `explanation`) with no `_debug`. JSON shape: `{"model": str, "generated_at": ISO str, "entries": [{"question", "table_id", "mode", "response"}]}`. Cache it with `st.cache_data` the same way `csv_backend` does (`HAS_STREAMLIT` pattern).
- `session_budget.MAX_LIVE_CALLS_PER_SESSION: int = 8`; `remaining(state: MutableMapping) -> int`; `consume(state: MutableMapping) -> None`. The state key is `"live_calls_used"`. (It resets on page reload. It's a courtesy cap, not abuse protection; the README says so.)
- `llm.describe_llm_error(exc: Exception) -> str`. The copy is fixed:
  - `requests.HTTPError` with status 429 → `"The model's rate limit is reached right now. The example questions above still work: they use saved model output, executed live against the data."`
  - status 401/403 → `"The model API rejected the key. The example questions above still work."`
  - `requests.Timeout` → `"The model took too long to answer. Try again, or use an example question."`
  - anything else → `f"LLM error: {exc}"`
- In `app.py`, the source decision goes in this order: `demo_cache.lookup(...)` hit → `source = "cached"`; else no key → `st.info("Live questions are off in this deployment. Try an example question.")`, no call; else `remaining(...) == 0` → `st.info` naming the cap, no call; else live call, `consume(...)`, `source = "live"`. Put `source` into `st.session_state.last_result` so Task 5 can read it. Cached answers do not consume the budget.
- `scripts/build_demo_cache.py`: for each `TableConfig` × mode in `("sql", "pandas")` × example question, call `llm.query_llm` with a 5 s sleep between calls (the eval's `min_interval_s`). Drop `_debug` and write JSON. 16 calls in total.

- [x] **Step 1: Write failing tests.**
  - `test_demo_cache.py`: `test_lookup_hit_ignores_case_and_spaces` (write a temp cache, point `CACHE_PATH` at it, look up `"  show ME the top 10 cities by transaction volume "` → dict), `test_lookup_miss_returns_none`, `test_lookup_strips_debug`.
  - `test_session_budget.py`: `test_remaining_starts_at_max`, `test_consume_decrements_and_floors_at_zero`.
  - `tests/test_app.py`: `test_example_served_from_cache_without_key`: no `LLM_API_KEY`; `llm.query_llm` patched to raise; cache contains the question with valid SQL. Assert no exception, one `plotly_chart`, and `query_llm` never called. `test_429_shows_plain_message`: patch `query_llm` to raise `requests.HTTPError` with `response.status_code = 429` and assert the 429 copy appears in `at.error` or `at.info`.
- [x] **Step 2:** Run the three test files. Expected: FAIL.
- [x] **Step 3:** Implement the modules, `describe_llm_error`, and the `app.py` source logic.
- [x] **Step 4:** Run the three test files plus `tests/test_app.py`. Expected: PASS.
- [x] **Step 5: ASK THE OWNER:** "Run 16 live calls to build `demo_cache.json`?" Wait for a yes.
- [x] **Step 6:** `python scripts/build_demo_cache.py`. Then run every cached entry through `validate_query` + `execute_query` (SQL) and `execute_pandas` (pandas) offline. Every entry must return a non-empty DataFrame. Any entry that fails is dropped from the JSON and listed for the owner.
- [x] **Step 7:** Commit `Serve example questions from saved model output; cap live calls per session` and push.

### Task 3: Deploy (owner clicks; Claude verifies)

**Files:** Modify `README.md` (live link under the title; one line under Limitations about the per-session cap and saved example output).

- [x] **Step 1:** Give the owner these steps:
  1. share.streamlit.io → **Create app** → repo `jairajsaraf/PropTalk`, branch `claude/clever-ptolemy-ehvssl`, main file `app.py`.
  2. **Advanced settings** → Python version **3.13** (the pins were resolved on 3.13; if 3.13 isn't offered, stop and tell Claude) → Secrets: `LLM_API_KEY = "..."`, plus `LLM_MODEL = "gemini-3.5-flash-lite"`.
  3. Pick a custom subdomain, e.g. `proptalk-<yourname>`. Deploy.
- [x] **Step 2:** Once the owner pastes the URL, run Task 6's smoke script against it now (a first pass). If it fails, read the Cloud logs the owner pastes and fix the problem before anything else.
- [x] **Step 3:** Add the link to the README, commit `Link the live deployment` and push. **Checkpoint: this must be done by T+60 min.**

### Task 4: Mockups (in parallel with Task 3's deploy wait)

> **Replaced by owner decision (2026-11-03):** one implemented Streamlit-only design instead of three mockups. If the owner is unhappy, plan a larger effort with three mockups. See `docs/superpowers/handoffs/2026-11-03-deploy-trust-handoff.md`.

**Files:** none committed. Mockups are artifacts in the cloud, or files in `.mockups/` locally.

- [ ] **Step 1:** If running locally, complete the resume protocol's resource inventory first.
- [ ] **Step 2:** Build 3 static HTML directions of the main screen (sidebar, question box, examples, chart, table, "How this answer was produced" panel). Use the real copy and a real result from `demo_cache.json`. **Hard limit:** each may use only what Streamlit can reproduce: theme fonts and colors, `borderRadius`, spacing via `st.container(border=True)`, and at most about 30 lines of CSS. No motion. Directions: (a) *Terminal-quiet*: monospace accents, near-black on off-white; (b) *Research note*: serif headings, generous whitespace; (c) *Desk tool*: dense, tabular, small type. cult-ui may inform type and spacing only.
- [ ] **Step 3:** Show all three. **CHECKPOINT: the owner picks one** (or says "skip, keep default") before Task 5.

### Task 5: Trust panel and chosen look

**Files:**
- Create: `trust_panel.py`, `tests/test_trust_panel.py`
- Modify: `app.py` (render the panel above "Debug Details", `app.py:285`), `.streamlit/config.toml` (chosen theme), optionally drop emoji from headings if the chosen mockup does

**Interfaces:**
- `@dataclass(frozen=True) TrustCheck(label: str, detail: str)`
- `trust_panel.build_checks(mode: str, source: str, validation_result: dict | None, row_count: int, query_elapsed: float) -> list[TrustCheck]`. Every limit comes from the code's constants, never a literal:
  - sql: `"Model output"` (`"saved, executed live"` when cached / `"generated live"`), `"Guard"` (SELECT-only, table whitelist; pass/fail from `validation_result`), `"Row cap"` (`sql_guard.MAX_ROWS`), `"Engine"` (`read-only: authorizer allowlist + PRAGMA query_only`), `"Time budget"` (`sqlite_backend.QUERY_TIME_BUDGET_SECONDS` s), `"Rows returned"`.
  - pandas: `"Model output"`, `"Blocklist"`, `"Isolation"` (`"separate process, copy of the data"`), `"Timeout"` (`csv_backend._EXEC_TIMEOUT` s), `"Rows returned"`.
- `trust_panel.eval_line(mode: str, metrics_path: str = "results/metrics.json") -> str | None`
  - sql → `reports.v1.summary.sql`: `f"In the preregistered eval this engine answered {round(acc*n)}/{n} questions correctly (95% CI {lo:.2f}–{hi:.2f})."` using `accuracy_rep0`, `accuracy_rep0_n`, `accuracy_rep0_wilson95`.
  - pandas → `reports.v2.summary.pandas`, same sentence; if `reports.v2.run.pandas_exec_contract != csv_backend.EXEC_CONTRACT`, append `f" Measured under executor contract {old}; this app runs contract {new}."`
  - Returns `None` if the file or a key is missing (never crash the panel).
- Render: `st.expander("How this answer was produced", expanded=True)` with one row per check, then the eval line as a caption with a link to the README's evaluation section on GitHub.

- [x] **Step 1: Write failing tests:** `test_sql_checks_use_code_constants` (monkeypatch `sql_guard.MAX_ROWS` to 123 → a detail contains `"123"`), `test_cached_source_is_labeled`, `test_eval_line_sql_reads_metrics` (temp metrics file → `"23/25"` appears), `test_eval_line_flags_contract_mismatch`, `test_eval_line_missing_file_returns_none`.
- [x] **Step 2:** Run `pytest tests/test_trust_panel.py -q`. Expected: FAIL.
- [x] **Step 3:** Implement, wire into `app.py`, and apply the chosen theme. _(theme: one direction chosen by Claude, pending owner verdict)_
- [x] **Step 4:** Run `pytest tests/test_trust_panel.py tests/test_app.py -q` and `python -m evals.publish --check`. Expected: PASS.
- [x] **Step 5:** Commit `Show how each answer was produced` (+ `Apply chosen theme`) and push. Streamlit Cloud redeploys on push.

### Task 6: Verify the live deployment

**Files:** Create `scripts/smoke_live.py` (not collected by pytest; imports Playwright inside `main`).

**Interfaces:** `python scripts/smoke_live.py <url>` exits 0 on pass and 1 on failure, printing the failed step. Steps: open the URL; if a "wake up" button is present (sleeping app), click it and wait up to 120 s; find the frame that contains the app (Community Cloud may serve it inside an iframe, so search all frames); click the first example button; wait up to 60 s for `.js-plotly-plot` and `[data-testid="stDataFrame"]`; assert the text "How this answer was produced" is present; screenshot to the scratchpad or `.mockups/`. In the cloud, Playwright is preinstalled. Locally: `pip install playwright` then `python -m playwright install chromium` (ask first; dev-only, not added to requirements).

- [ ] **Step 1:** Write the script. Run it against the live URL. Expected: exit 0.
- [ ] **Step 2:** Run it again at 390×844 viewport (`--mobile` flag) and look at the screenshot for the Review Focus #5 wrap problem. If the examples wrap badly, switch `st.columns(len(examples))` to a 2-column grid, then commit and push.
- [ ] **Step 3: Cold-open kit for a human.** Give the owner these lines to send a friend: "Open <url> in a private window on your phone. Tap any example. Within a minute you should see a chart, a table, and 'How this answer was produced.' Then type 'delete all the rows' and tell me what it says." Expected: an answer for the example; a refusal or a "Query rejected" for the delete.
- [ ] **Step 4:** Commit `Add live smoke test` and push.

### Task 7: Final check and handoff

- [ ] **Step 1:** Full `python -m pytest -q`, `python -m ruff check .` and `python -m evals.publish --check`. Expected: all pass.
- [ ] **Step 2:** Run the smoke test once more against the live URL.
- [ ] **Step 3:** Draft three lines of "what I'd do differently next time" for the owner's email, from the Limitations section and the Review Focus items that remain open (e.g. the per-session cap resets on reload, the schema sits in the prompt, the guard is regex-based). The owner edits them; nothing goes in the repo.
- [ ] **Step 4:** Tick the boxes, commit and push. Give the owner a session-notes summary: what changed, what's open, what's next.
