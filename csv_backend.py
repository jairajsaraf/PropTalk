"""CSV fallback backend — load synthetic CSVs, extract schema, run pandas queries."""

import os
import re
import pandas as pd

try:
    import streamlit as st
    HAS_STREAMLIT = True
except ImportError:
    HAS_STREAMLIT = False

SAMPLE_DIR = os.path.join(os.path.dirname(__file__), "sample_data")

DATASETS = {
    "Deed Transactions": "deed_transactions_sample.csv",
    "HAR Listings": "har_listings_sample.csv",
}

# Date columns to parse per dataset
DATE_COLUMNS = {
    "Deed Transactions": ["SALE_DERIVED_DATE"],
    "HAR Listings": ["ListingContractDate", "CloseDate"],
}


def get_dataset_names() -> list[str]:
    """Return available dataset display names."""
    return list(DATASETS.keys())


def load_data(dataset_name: str) -> pd.DataFrame:
    """Load a CSV dataset from sample_data/.

    Cached with @st.cache_data when running inside Streamlit.
    """
    filename = DATASETS.get(dataset_name)
    if not filename:
        raise ValueError(f"Unknown dataset: {dataset_name}")

    path = os.path.join(SAMPLE_DIR, filename)
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"Sample data not found at {path}. "
            "Run 'python generate_sample_data.py' first."
        )

    date_cols = DATE_COLUMNS.get(dataset_name, [])
    df = pd.read_csv(path, parse_dates=date_cols)
    return df


# Apply Streamlit caching if available
if HAS_STREAMLIT:
    load_data = st.cache_data(load_data)


def get_schema(dataset_name: str) -> str:
    """Get schema info from a loaded CSV: column names, dtypes, and sample values.

    Returns the same format as db.get_schema() for seamless mode switching.
    """
    df = load_data(dataset_name)
    lines = []

    for col in df.columns:
        dtype = str(df[col].dtype)
        non_null = df[col].dropna()
        samples = non_null.unique()[:3]
        sample_str = ", ".join(str(v) for v in samples)

        line = f"- {col} ({dtype})"
        if sample_str:
            line += f" — examples: {sample_str}"
        lines.append(line)

    return "\n".join(lines)


# Patterns that should never appear in LLM-generated pandas code
_BLOCKED_PATTERNS = [
    r"\bimport\b",        # no imports
    r"\bopen\s*\(",       # no file access
    r"\bos\b",            # no os module
    r"\bsys\b",           # no sys module
    r"\bsubprocess\b",    # no subprocess
    r"\b__\w+__\b",       # no dunder attributes (__class__, __import__, etc.)
    r"\beval\s*\(",       # no eval
    r"\bexec\s*\(",       # no nested exec
    r"\bcompile\s*\(",    # no compile
    r"\bglobals\s*\(",    # no globals access
    r"\blocals\s*\(",     # no locals access
    r"\bgetattr\s*\(",    # no dynamic attribute access
    r"\bsetattr\s*\(",    # no dynamic attribute setting
    r"\bdelattr\s*\(",    # no dynamic attribute deletion
    r"\bbreakpoint\s*\(", # no debugger
    r"\bsocket\b",        # no network access
    r"\brequests\b",      # no HTTP requests
    r"\burllib\b",        # no URL access
    r"\.to_csv\s*\(",     # no writing files
    r"\.to_excel\s*\(",   # no writing files
    r"\.to_json\s*\(",    # no writing files
    r"\.to_sql\s*\(",     # no writing to databases
    r"\.to_parquet\s*\(", # no writing files
    r"\bread_csv\b",      # no reading files via pd.read_csv
    r"\bread_excel\b",    # no reading files via pd.read_excel
    r"\bread_json\b",     # no reading files via pd.read_json
    r"\bread_sql\b",      # no reading from databases
    r"\bread_parquet\b",  # no reading parquet files
    r"\bread_html\b",     # no reading HTML
    r"\bread_fwf\b",      # no reading fixed-width files
    r"\bread_clipboard\b", # no reading clipboard
    r"\bread_table\b",    # no reading tables from files
]


def _validate_pandas_code(code: str) -> str | None:
    """Check pandas code for dangerous patterns. Returns rejection reason or None."""
    for pattern in _BLOCKED_PATTERNS:
        match = re.search(pattern, code, re.IGNORECASE)
        if match:
            return f"Blocked pattern in generated code: {match.group()}"
    return None


def execute_pandas(df: pd.DataFrame, code: str) -> pd.DataFrame:
    """Execute a pandas expression on a copy of the DataFrame.

    The LLM-generated code should assign results to a variable called `result`.
    Code is scanned for dangerous patterns before execution.

    Args:
        df: The source DataFrame.
        code: Pandas code string from the LLM.

    Returns:
        The result DataFrame.

    Raises:
        ValueError: If the code doesn't produce a result variable or is unsafe.
        Exception: On execution errors.
    """
    # Validate code before execution
    rejection = _validate_pandas_code(code)
    if rejection:
        raise ValueError(rejection)

    # Work on a copy to prevent mutations
    df = df.copy()

    # Restricted namespace — only pandas and the DataFrame
    namespace = {"df": df, "pd": pd}

    exec(code, {"__builtins__": {}}, namespace)

    result = namespace.get("result")
    if result is None:
        raise ValueError(
            "The generated code did not assign output to 'result'. "
            "Code must include: result = ..."
        )

    if isinstance(result, pd.Series):
        result = result.to_frame()

    if not isinstance(result, pd.DataFrame):
        raise ValueError(f"Expected DataFrame result, got {type(result).__name__}")

    return result.head(10000)
