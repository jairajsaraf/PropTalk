"""CSV fallback backend — load synthetic CSVs, extract schema, run pandas queries."""

from __future__ import annotations

import builtins
import multiprocessing
import os
import pickle
import queue
import re
import time

import pandas as pd

try:
    import streamlit as st
    HAS_STREAMLIT = True
except ImportError:
    HAS_STREAMLIT = False

SAMPLE_DIR = os.path.join(os.path.dirname(__file__), "sample_data")

# Date columns to parse per dataset
DATE_COLUMNS = {
    "Deed Transactions": ["sale_date"],
    "MLS Listings": ["ListingContractDate", "CloseDate"],
}


def _load_data(filename: str, date_cols: list[str]) -> pd.DataFrame:
    """Load a CSV from sample_data/."""
    path = os.path.join(SAMPLE_DIR, filename)
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"Sample data not found at {path}. "
            "Run 'python generate_sample_data.py' first."
        )
    return pd.read_csv(path, parse_dates=date_cols)


if HAS_STREAMLIT:
    _load_data = st.cache_data(_load_data)


def _get_schema_str(df: pd.DataFrame) -> str:
    """Build schema string from a DataFrame: column names, dtypes, sample values."""
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


class CsvBackend:
    """CSV-based backend conforming to the DataBackend protocol."""

    def __init__(self, tables: list[dict]) -> None:
        """Initialize with a list of {display_name, table_id, csv_filename} dicts."""
        self._tables = tables
        self._file_map = {t["table_id"]: t["csv_filename"] for t in tables}

    def get_tables(self) -> list[dict]:
        return [{"display_name": t["display_name"], "table_id": t["table_id"]}
                for t in self._tables]

    def get_schema(self, table_id: str) -> str:
        df = self.load_data(table_id)
        return _get_schema_str(df)

    def execute(self, query: str, table_id: str) -> pd.DataFrame:
        df = self.load_data(table_id)
        return execute_pandas(df, query)

    def get_query_language(self) -> str:
        return "pandas"

    def get_allowed_table_names(self) -> list[str]:
        return list(self._file_map.keys())

    def load_data(self, table_id: str) -> pd.DataFrame:
        """Load CSV for a given table_id."""
        filename = self._file_map.get(table_id)
        if not filename:
            raise ValueError(f"Unknown dataset: {table_id}")
        date_cols = DATE_COLUMNS.get(table_id, [])
        return _load_data(filename, date_cols)


# Patterns that should never appear in LLM-generated pandas code —
# imports, I/O, dynamic attribute access, network, and execution primitives.
_BLOCKED_PATTERNS = [
    r"\bimport\b",
    r"\bopen\s*\(",  # file access
    r"\bos\b",
    r"\bsys\b",
    r"\bsubprocess\b",
    r"\b__\w+__\b",  # dunder attributes (__class__, __import__, etc.)
    r"\beval\s*\(",
    r"\bexec\s*\(",
    r"\bcompile\s*\(",
    r"\bglobals\s*\(",
    r"\blocals\s*\(",
    r"\bgetattr\s*\(",
    r"\bsetattr\s*\(",
    r"\bdelattr\s*\(",
    r"\bbreakpoint\s*\(",
    r"\bsocket\b",
    r"\brequests\b",
    r"\burllib\b",
    r"\.to_csv\s*\(",
    r"\.to_excel\s*\(",
    r"\.to_json\s*\(",
    r"\.to_sql\s*\(",
    r"\.to_parquet\s*\(",
    r"\.to_pickle\s*\(",
    r"\.to_hdf\s*\(",
    r"\.to_feather\s*\(",
    r"\.to_stata\s*\(",
    r"\.to_gbq\s*\(",
    r"\.to_latex\s*\(",
    r"\.to_html\s*\(",
    r"\.to_clipboard\s*\(",
    r"\.to_markdown\s*\(",
    r"\bread_pickle\b",  # unsafe deserialization
    r"\bread_csv\b",
    r"\bread_excel\b",
    r"\bread_json\b",
    r"\bread_sql\b",
    r"\bread_parquet\b",
    r"\bread_html\b",
    r"\bread_fwf\b",
    r"\bread_clipboard\b",
    r"\bread_table\b",
]


def _validate_pandas_code(code: str) -> str | None:
    """Check pandas code for dangerous patterns. Returns rejection reason or None."""
    for pattern in _BLOCKED_PATTERNS:
        match = re.search(pattern, code, re.IGNORECASE)
        if match:
            return f"Blocked pattern in generated code: {match.group()}"
    return None


_EXEC_TIMEOUT = 30  # seconds

# Version of the execution contract, recorded in every eval report so a saved
# report can be re-scored under the rules it was produced with.
#   1: no builtins at all; a result that is not a DataFrame/Series is an error.
#   2: a small allowlist of builtins; a scalar result becomes a one-cell frame.
#   3: one namespace for globals and locals, so lambdas, generator expressions
#      and nested functions can see df, pd and the code's own variables.
EXEC_CONTRACT = 3

# Harmless builtins that ordinary pandas code reaches for. Deliberately absent:
# type, object, getattr/setattr/delattr, hasattr, vars, dir, globals, locals,
# open, input, print, eval, exec, compile, __import__, breakpoint, memoryview,
# bytearray, bytes, map, filter, iter, next, callable, isinstance, issubclass.
SAFE_BUILTIN_NAMES = (
    "abs", "all", "any", "bool", "dict", "enumerate", "float", "int", "len",
    "list", "max", "min", "range", "reversed", "round", "set", "sorted", "str",
    "sum", "tuple", "zip",
)


def _builtins_for(contract: int) -> dict:
    if contract <= 1:
        return {}
    return {name: getattr(builtins, name) for name in SAFE_BUILTIN_NAMES}


def _exec_worker(code: str, df_bytes: bytes, result_queue: multiprocessing.Queue,
                 contract: int = EXEC_CONTRACT) -> None:
    """Worker function that runs in a subprocess to execute pandas code."""
    try:
        df = pickle.loads(df_bytes)
        namespace = {"df": df, "pd": pd}
        builtins_env = {"__builtins__": _builtins_for(contract)}
        if contract >= 3:
            namespace.update(builtins_env)
            exec(code, namespace)
        else:  # separate globals/locals: nested scopes cannot see namespace
            exec(code, builtins_env, namespace)
        result = namespace.get("result")
        result_queue.put(("ok", pickle.dumps(result)))
    except Exception as exc:
        result_queue.put(("error", str(exc)))


def _stop_process(proc: multiprocessing.Process) -> None:
    """Terminate, then kill, a worker process that is still running."""
    if proc.is_alive():
        proc.terminate()
        proc.join(timeout=5)
        if proc.is_alive():
            proc.kill()
            proc.join(timeout=2)


def _wait_for_result(proc: multiprocessing.Process, result_queue: multiprocessing.Queue,
                     timeout: float) -> tuple[str, object]:
    """Read the worker's (status, payload), reading before joining.

    A child that has put a large result cannot exit until the parent drains
    the pipe, so join-then-read would report any result over the pipe buffer
    (~64 KB) as a timeout. Polling instead of one long get() also notices a
    worker that died without a result (crash, OOM kill) without waiting out
    the whole timeout.
    """
    deadline = time.monotonic() + timeout
    while True:
        try:
            return result_queue.get(timeout=0.2)
        except queue.Empty:
            if not proc.is_alive():
                try:  # its result may have raced its exit
                    return result_queue.get(timeout=1)
                except queue.Empty:
                    _stop_process(proc)
                    raise ValueError("Execution produced no result.") from None
            if time.monotonic() > deadline:
                _stop_process(proc)
                raise ValueError(
                    f"Query execution timed out after {timeout} seconds. "
                    "Try a simpler query."
                ) from None


def execute_pandas(
    df: pd.DataFrame, code: str, timeout: float = _EXEC_TIMEOUT,
    contract: int = EXEC_CONTRACT,
) -> pd.DataFrame:
    """Execute a pandas expression on a copy of the DataFrame.

    The LLM-generated code should assign results to a variable called `result`.
    Code is scanned for dangerous patterns before execution. Execution runs in
    a subprocess with a timeout — the process is terminated on timeout, so
    infinite loops or heavy computation cannot accumulate.

    Args:
        df: The source DataFrame.
        code: Pandas code string from the LLM.
        timeout: Seconds before the worker process is terminated.
        contract: Execution contract version (see EXEC_CONTRACT). Only the
            eval's offline re-score passes anything but the default, to
            reproduce reports made under an earlier contract.

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

    # Serialize DataFrame for the subprocess
    df_bytes = pickle.dumps(df.copy())
    result_queue = multiprocessing.Queue()

    proc = multiprocessing.Process(
        target=_exec_worker, args=(code, df_bytes, result_queue, contract), daemon=True
    )
    proc.start()
    status, payload = _wait_for_result(proc, result_queue, timeout)
    proc.join(timeout=5)
    _stop_process(proc)

    if status == "error":
        raise ValueError(f"Execution error: {payload}")

    result = pickle.loads(payload)

    if result is None:
        raise ValueError(
            "The generated code did not assign output to 'result'. "
            "Code must include: result = ..."
        )

    if isinstance(result, pd.Series):
        result = result.to_frame()
    elif contract >= 2 and pd.api.types.is_scalar(result):
        # "How many ...?" naturally yields a number, not a frame.
        result = pd.DataFrame({"result": [result]})

    if not isinstance(result, pd.DataFrame):
        raise ValueError(f"Expected DataFrame result, got {type(result).__name__}")

    return result.head(10000)
