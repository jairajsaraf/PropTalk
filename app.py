"""Texas Real Estate Data Explorer — Natural language interface for property data."""

import os
import time

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

import csv_backend
import db
import llm
from chart_builder import build_chart
from prompts import EXAMPLE_QUESTIONS
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
# Mode detection
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


mode = detect_mode()

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
    if mode == "sql":
        table_display_names = list(db.TABLE_WHITELIST.keys())
        selected_table = st.selectbox("Select table", table_display_names)
        table_fq_name = db.TABLE_WHITELIST[selected_table]
    else:
        dataset_names = csv_backend.get_dataset_names()
        selected_table = st.radio("Select dataset", dataset_names)
        table_fq_name = selected_table  # Used for display in prompts

    st.divider()

    # Model selector
    selected_model = st.selectbox("LLM Model", llm.AVAILABLE_MODELS)

    st.divider()

    # Schema explorer
    with st.expander("📋 Schema Explorer"):
        try:
            if mode == "sql":
                schema_info = db.get_schema(db.TABLE_WHITELIST[selected_table])
            else:
                schema_info = csv_backend.get_schema(selected_table)
            st.code(schema_info, language=None)
        except Exception as e:
            st.error(f"Could not load schema: {e}")
            schema_info = ""

    # Query history
    with st.expander("📜 Query History"):
        if st.session_state.query_history:
            for i, entry in enumerate(reversed(st.session_state.query_history)):
                st.markdown(f"**{len(st.session_state.query_history) - i}.** {entry['question']}")
                code_key = "sql" if "sql" in entry else "pandas_code"
                if code_key in entry:
                    st.code(entry[code_key], language="sql" if code_key == "sql" else "python")
        else:
            st.caption("No queries yet.")

# ---------------------------------------------------------------------------
# Main area
# ---------------------------------------------------------------------------

st.title("🏠 Texas Real Estate Data Explorer")

if mode == "csv":
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
    if mode == "sql":
        schema_info = db.get_schema(db.TABLE_WHITELIST[selected_table])
    else:
        schema_info = csv_backend.get_schema(selected_table)
except Exception as e:
    st.error(f"Could not load schema: {e}")
    st.stop()

# Question input
st.markdown("### 💬 Ask a question about the data")
question = st.text_input(
    "Type your question in plain English:",
    placeholder=f'e.g., "Show me the top 10 cities by transaction volume"',
    label_visibility="collapsed",
)

# Example question buttons
examples = EXAMPLE_QUESTIONS.get(selected_table, [])
if examples:
    st.caption("**Try an example:**")
    cols = st.columns(len(examples))
    for i, example in enumerate(examples):
        with cols[i]:
            if st.button(example, key=f"example_{i}", use_container_width=True):
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

    # Step 1: LLM query generation
    with st.status("Processing your question...", expanded=True) as status:
        st.write("🤖 Generating query...")
        try:
            if mode == "sql":
                llm_response = llm.query_llm(
                    question, schema_info, "sql", table_fq_name, selected_model
                )
                generated_code = llm_response.get("sql", "")
            else:
                llm_response = llm.query_llm(
                    question, schema_info, "csv", selected_table, selected_model
                )
                generated_code = llm_response.get("pandas_code", "")
        except ValueError as e:
            error_msg = f"Configuration error: {e}"
        except Exception as e:
            error_msg = f"LLM error: {e}"

        # Step 2: Validation (SQL mode only)
        if generated_code and mode == "sql" and not error_msg:
            st.write("🔍 Validating query...")
            is_valid, sanitized, reason = validate_query(
                generated_code, db.get_allowed_table_names()
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

        # Step 3: Execution
        if generated_code and not error_msg:
            st.write("⚡ Executing query...")
            try:
                if mode == "sql":
                    result_df = db.execute_query(generated_code)
                else:
                    df = csv_backend.load_data(selected_table)
                    result_df = csv_backend.execute_pandas(df, generated_code)
            except Exception as e:
                error_msg = f"Execution error: {e}"

        elapsed = time.time() - start_time

        if error_msg:
            status.update(label="Error", state="error")
        else:
            status.update(label=f"Done in {elapsed:.1f}s", state="complete")

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
            st.markdown("**Execution Time:**")
            st.write(f"{elapsed:.2f}s")

            if validation_result:
                st.markdown("**Validation:**")
                if validation_result["is_valid"]:
                    st.success("Passed")
                else:
                    st.error(validation_result["rejection_reason"])

        if llm_response:
            st.markdown("**Raw LLM Response:**")
            st.json(llm_response)

    # Save to history
    history_entry = {"question": question}
    if mode == "sql":
        history_entry["sql"] = generated_code or ""
    else:
        history_entry["pandas_code"] = generated_code or ""
    if llm_response:
        history_entry["explanation"] = llm_response.get("explanation", "")
    st.session_state.query_history.append(history_entry)
