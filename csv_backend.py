"""CSV fallback backend — load synthetic CSVs, extract schema, run pandas queries."""

import os
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


def execute_pandas(df: pd.DataFrame, code: str) -> pd.DataFrame:
    """Execute a pandas expression on a copy of the DataFrame.

    The LLM-generated code should assign results to a variable called `result`.

    Args:
        df: The source DataFrame.
        code: Pandas code string from the LLM.

    Returns:
        The result DataFrame.

    Raises:
        ValueError: If the code doesn't produce a result variable.
        Exception: On execution errors.
    """
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
