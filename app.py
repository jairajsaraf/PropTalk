"""Texas Real Estate Data Explorer — Natural language interface for property data."""

import os
import time

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

import config
import csv_backend
import db
import llm
from chart_builder import build_chart
from sql_guard import validate_query

load_dotenv()

# ---------------------------------------------------------------------------
# Page configuration
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Texas Real Estate Data Explorer",
    page_icon="🏠",
    layout="wide",
)

# ---------------------------------------------------------------------------
# Session state initialization
# ---------------------------------------------------------------------------

if "query_history" not in st.session_state:
    st.session_state.query_history = []
if "current_question" not in st.session_state:
    st.session_state.current_question = ""

# ---------------------------------------------------------------------------
# Backend initialization
# ---------------------------------------------------------------------------

@st.cache_data(ttl=60)
def detect_mode() -> str:
    """Detect whether SQL Server is available; fall back to CSV."""
    if db.is_available():
        try:
            conn = db.get_connection()
            conn.cursor().execute("SELECT 1")
            return "sql"
        except Exception:
            return "csv"
    return "csv"


def _build_backend():
    """Instantiate the appropriate backend based on mode detection."""
    mode = detect_mode()
    if mode == "sql":
        return db.SqlBackend(config.get_sql_tables())
    else:
        return csv_backend.CsvBackend(config.get_csv_tables())


backend = _build_backend()
mode = backend.get_query_language()  # "sql" or "pandas"

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

with st.sidebar:
    # Mode indicator
    if mode == "sql":
        st.markdown("### 🟢 Live: SQL Server")
    else:
        st.markdown("### 🟡 Demo Mode: Synthetic Data")

    st.divider()

    # Table / dataset selector
    available_tables = backend.get_tables()
    table_display_names = [t["display_name"] for t in available_tables]
    table_ids = {t["display_name"]: t["table_id"] for t in available_tables}

    if mode == "sql":
        selected_display = st.selectbox("Select table", table_display_names)
    else:
        selected_display = st.radio("Select dataset", table_display_names)

    selected_table_id = table_ids[selected_display]

    st.divider()

    # Model selector
    model_names = [m["name"] for m in config.AVAILABLE_MODELS]
    model_ids = {m["name"]: m["id"] for m in config.AVAILABLE_MODELS}
    selected_model_name = st.selectbox("LLM Model", model_names)
    selected_model = model_ids[selected_model_name]

    st.divider()

    # Schema explorer
    with st.expander("📋 Schema Explorer"):
        try:
            schema_info = backend.get_schema(selected_table_id)
            st.code(schema_info, language=None)
        except Exception as e:
            st.error(f"Could not load schema: {e}")
            schema_info = ""

    # Query history
    with st.expander("📜 Query History"):
        if st.session_state.query_history:
            if st.button("Clear History", key="clear_history"):
                st.session_state.query_history = []
                st.rerun()
            for i, entry in enumerate(reversed(st.session_state.query_history)):
                idx = len(st.session_state.query_history) - 1 - i
                if st.button(
                    f"**{idx + 1}.** {entry['question']}",
                    key=f"history_{idx}",
                    use_container_width=True,
                ):
                    st.session_state.current_question = entry["question"]
                    st.rerun()
                code_key = "sql" if "sql" in entry else "pandas_code"
                if code_key in entry:
                    st.code(entry[code_key], language="sql" if code_key == "sql" else "python")
        else:
            st.caption("No queries yet.")

# ---------------------------------------------------------------------------
# Main area
# ---------------------------------------------------------------------------

st.title("🏠 Texas Real Estate Data Explorer")

if mode == "pandas":
    st.info(
        "**Running in demo mode with synthetic data.** "
        "To use real data, set SQL_SERVER in your .env file.",
        icon="🟡",
    )

# Check for API key
api_key = os.getenv("TAMU_AI_API_KEY")
if not api_key:
    st.error(
        "**TAMU_AI_API_KEY not found.** "
        "Copy `.env.example` to `.env` and add your chat.tamu.ai API key to get started."
    )
    st.stop()

# Load schema for LLM context (may already be cached from sidebar)
try:
    schema_info = backend.get_schema(selected_table_id)
except Exception as e:
    st.error(f"Could not load schema: {e}")
    st.stop()

# Resolve the table name for prompts
if mode == "sql":
    table_name_for_prompt = backend.get_fq_name(selected_table_id)
else:
    table_name_for_prompt = selected_display

# Question input
st.markdown("### 💬 Ask a question about the data")
question = st.text_input(
    "Type your question in plain English:",
    placeholder=f'e.g., "Show me the top 10 cities by transaction volume"',
    label_visibility="collapsed",
)

# Example question buttons (keyed by dataset so they re-render on switch)
examples = config.get_example_questions(selected_display)
if examples:
    st.caption("**Try an example:**")
    cols = st.columns(len(examples))
    for i, example in enumerate(examples):
        with cols[i]:
            if st.button(example, key=f"example_{selected_table_id}_{i}", use_container_width=True):
                st.session_state.current_question = example
                st.rerun()

# Use example question if one was clicked
if st.session_state.current_question and not question:
    question = st.session_state.current_question
    st.session_state.current_question = ""

# ---------------------------------------------------------------------------
# Query execution flow
# ---------------------------------------------------------------------------

if question:
    start_time = time.time()
    llm_response = None
    generated_code = None
    validation_result = None
    result_df = None
    error_msg = None
    query_elapsed = 0.0

    code_key = "sql" if mode == "sql" else "pandas_code"

    with st.status("Generating query...", expanded=True, state="running") as status:
        # Step 1: LLM query generation
        try:
            llm_response = llm.query_llm(
                question, schema_info, mode, table_name_for_prompt, selected_model
            )
            generated_code = llm_response.get(code_key, "")
        except ValueError as e:
            error_msg = f"Configuration error: {e}"
        except Exception as e:
            error_msg = f"LLM error: {e}"

        # Step 2: Validation + Execution
        if generated_code and not error_msg:
            if mode == "sql":
                status.update(label="Validating query...", state="running")
                is_valid, sanitized, reason = validate_query(
                    generated_code, backend.get_allowed_table_names()
                )
                validation_result = {
                    "is_valid": is_valid,
                    "sanitized_query": sanitized,
                    "rejection_reason": reason,
                }
                if not is_valid:
                    error_msg = f"Query rejected: {reason}"
                else:
                    generated_code = sanitized

            if not error_msg:
                status.update(label="Executing query...", state="running")
                query_start = time.time()
                try:
                    if mode == "sql":
                        result_df = db.execute_query(generated_code)
                    else:
                        df = backend.load_data(selected_table_id)
                        result_df = csv_backend.execute_pandas(df, generated_code)
                except Exception as e:
                    error_msg = f"Execution error: {e}"
                query_elapsed = time.time() - query_start

        elapsed = time.time() - start_time

        if error_msg:
            status.update(label="Error", state="error", expanded=True)
        else:
            status.update(label=f"Done in {elapsed:.1f}s", state="complete", expanded=False)

    # ---------------------------------------------------------------------------
    # Display results
    # ---------------------------------------------------------------------------

    if error_msg:
        st.error(error_msg)
    elif result_df is not None:
        if result_df.empty:
            st.warning("No rows matched. Try broadening your filters.")
        else:
            # Chart
            chart_config = llm_response.get("chart_config") if llm_response else None
            fig = build_chart(result_df, chart_config)
            if fig:
                st.plotly_chart(fig, use_container_width=True)

            # Results table
            st.markdown(f"### 📋 Results ({len(result_df):,} rows)")
            st.dataframe(result_df, use_container_width=True, height=400)

            # Download button
            csv_data = result_df.to_csv(index=False)
            st.download_button(
                label="Download results as CSV",
                data=csv_data,
                file_name="proptalk_results.csv",
                mime="text/csv",
            )

            # Explanation
            explanation = llm_response.get("explanation", "") if llm_response else ""
            if explanation:
                st.info(f"💡 {explanation}")

    # Debug expander
    with st.expander("🔍 Debug Details"):
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**Generated Code:**")
            code_lang = "sql" if mode == "sql" else "python"
            st.code(generated_code or "N/A", language=code_lang)
        with col2:
            st.markdown("**Timing:**")
            llm_time = llm_response.get("_debug", {}).get("llm_elapsed", 0) if llm_response else 0
            st.write(f"LLM: {llm_time:.1f}s | Query: {query_elapsed:.1f}s | Total: {elapsed:.1f}s")

            if validation_result:
                st.markdown("**Validation:**")
                if validation_result["is_valid"]:
                    st.success("Passed")
                else:
                    st.error(validation_result["rejection_reason"])

        if llm_response:
            st.markdown("**Raw LLM Response:**")
            st.json(llm_response)

        # Show API debug info if available
        debug_info = llm_response.get("_debug") if llm_response else None
        if debug_info:
            st.markdown("**API Debug:**")
            st.write(f"Status: {debug_info.get('status_code')}")
            st.write(f"Content-Type: {debug_info.get('content_type')}")
            if debug_info.get("parse_error"):
                st.warning("Response was not standard OpenAI format")
            st.code(debug_info.get("raw_body", "N/A"), language=None)

    # Save to history (dedup: remove prior entry with same question text)
    history_entry = {"question": question}
    history_entry[code_key] = generated_code or ""
    if llm_response:
        history_entry["explanation"] = llm_response.get("explanation", "")
    st.session_state.query_history = [
        e for e in st.session_state.query_history
        if e["question"].lower() != question.lower()
    ]
    st.session_state.query_history.append(history_entry)
