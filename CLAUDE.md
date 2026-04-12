# PropTalk — Project Context

## What this is
A Streamlit demo app for the Texas A&M Real Estate Center. Users type plain-English questions about property data, an LLM (via chat.tamu.ai) generates a query, and results render as interactive charts + tables.

## Architecture: Dual-mode
- **SQL Server mode**: activated when `SQL_SERVER` is set in `.env`. LLM generates T-SQL, validated by `sql_guard.py`, executed via pyodbc.
- **CSV mode**: activated when SQL Server is unavailable. LLM generates pandas expressions, executed against synthetic CSVs in `sample_data/`.
- Mode is auto-detected at startup. Same UI for both.

## Confidentiality rules
- Code is public on GitHub. Data is proprietary (CoreLogic, MLS) and NEVER committed.
- Server hostnames, credentials, API keys live in `.env` only (gitignored).
- `generate_sample_data.py` creates synthetic data — this IS committed.
- Column/table names are schema metadata and are safe to commit.

## chat.tamu.ai API
- OpenAI-compatible endpoint: `https://chat-api.tamu.ai/openai/chat/completions`
- Uses `requests.post` directly (NOT the openai SDK — it doesn't parse responses correctly)
- Returns SSE streaming by default; we request `"stream": false` for JSON responses
- Claude models on their Bedrock backend have extended thinking enabled, requiring `temperature=1`
- Non-Claude models (GPT, Gemini) use `temperature=0`

## Key files
- `app.py` — Streamlit UI, layout, session state
- `llm.py` — API calls to chat.tamu.ai, response parsing
- `prompts.py` — System prompts (SQL and pandas variants)
- `csv_backend.py` — CSV loading, schema extraction, pandas execution
- `db.py` — SQL Server connection, schema introspection
- `sql_guard.py` — SELECT-only validation for LLM-generated SQL
- `chart_builder.py` — Plotly chart generation from LLM chart_config
- `generate_sample_data.py` — Synthetic data generator (committed)

## Commands
- `python generate_sample_data.py` — generate synthetic CSVs
- `streamlit run app.py` — run the app
- API key required in `.env` as `TAMU_AI_API_KEY`

## Coding conventions
- Use type hints on all function signatures
- Use `@st.cache_data` for data loading, `@st.cache_resource` for connections
- All secrets come from `.env` via `python-dotenv`, never hardcoded
- Commit messages: imperative mood, concise (e.g., "Fix query history dedup")
