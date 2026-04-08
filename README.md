# Texas Real Estate Data Explorer

Natural language interface for exploring Texas real estate data, powered by Streamlit and LLMs via the LLM endpoint.

Type a question like **"show me cash purchases in Houston above $500K in 2024"** and get an interactive chart and data table — no SQL or Python knowledge needed.

<!-- Screenshot placeholder: add a screenshot of the running app here -->

## Quick Start

```bash
git clone https://github.com/jairajsaraf/PropTalk.git
cd PropTalk
pip install -r requirements.txt
python generate_sample_data.py
cp .env.example .env
# Edit .env and add your LLM API key
streamlit run app.py
```

This runs in **demo mode** with synthetic data — no database required.

## SQL Server Mode (optional)

To connect to your own SQL Server, add these to your `.env`:

```bash
SQL_SERVER=your_server
SQL_DATABASE=demo_db
SQL_TRUSTED_CONNECTION=yes
```

The app auto-detects SQL Server availability and switches seamlessly.

## How It Works

1. You type a plain-English question about property data
2. The app sends your question + the dataset schema to an LLM (via the LLM endpoint)
3. The LLM generates a SQL query or pandas filter, which is validated and executed
4. Results appear as an interactive Plotly chart and data table

## Available Models

| Model | Notes |
|-------|-------|
| `Claude Sonnet 4` | Recommended — best balance of speed and quality |
| `gemini-2.5-flash` | Fastest and cheapest |
| `gpt-4.1` | OpenAI alternative |
| `Claude 3.7 Sonnet` | Previous-gen Claude |

## Security

- All LLM-generated SQL is validated to be **SELECT-only** before execution
- Queries are checked against a table whitelist and keyword blocklist
- Row limits are enforced automatically (max 10,000 rows)
- For production use, connect with a **read-only database account**
- No proprietary data is included in this repository — sample data is synthetically generated

## Data Confidentiality

This project is designed for use with a private property-records database. The underlying property data is licensed and is **never committed** to this repository.

The `generate_sample_data.py` script creates synthetic data with realistic distributions for demonstration purposes.

## Built With

- [Streamlit](https://streamlit.io/) — Web app framework
- Any OpenAI-compatible LLM API
- [Plotly](https://plotly.com/python/) — Interactive charts
- [pyodbc](https://github.com/mkleehammer/pyodbc) — SQL Server connectivity
